"""Issue 8: one call for an agent to file a piece of work.

A job (a deck made from three files, an analysis) is one inbox item: its outputs are the item's files, its reusable inputs
are kept once each as their own inbox items (assets, found again by `reusable_as`) and linked to the job as inputs, and its
summary and proposals wait for the owner on the item. Wiki pages and a chat log are written in the same call and cite the
item. Filing the same `job_id` again updates the job. Everything is checked before anything is written, and the writes run
under one savepoint: when one fails, nothing is saved and the error names the field.

`job_id` is the name issue 3 (Agent Jobs) uses for a request, so a request can later be linked to the job it was filed as."""
import base64
import binascii
import builtins
import json
import os
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import get_url, now_datetime

from lifeos import files, links, permissions
from lifeos import proposals as rules
from lifeos.api.utils import parse
from lifeos.constants import SPACE_DOCTYPES

MAX_ITEMS = 50  # inputs, outputs, proposals or wiki pages in one call
DEFAULT_SYSTEM = "agent"
JOB = "Life Inbox Item"


@frappe.whitelist(methods=["POST"])
def file_job(job_id: str, space: str | None = None, title: str | None = None, area: str | None = None, goal: str | None = None,
		instruction: str | None = None, raw_text: str | None = None, inputs: str | builtins.list | None = None,
		outputs: str | builtins.list | None = None, transcript_md: str | None = None, summary_md: str | None = None,
		proposals: str | builtins.list | None = None, wiki: str | builtins.list | None = None, chat: str | builtins.dict | None = None,
		source_system: str | None = None):
	"""File a finished piece of work as one inbox item, in one call. See agent/FILE_WORK.md.

	job_id: stable; the same job_id again updates the job. instruction: the owner's own words. raw_text: the brief.
	inputs: [{name, file, reusable_as?, title?, transcript_md?}]; outputs: [{name, file}]. `file` is base64 (a data: URL is fine)
	or the URL of a file already in this space (/private/files/...). An input with `reusable_as` (a stable asset id such as
	btw-standard-deck) is kept once as its own item and linked; without `file` it links the asset already kept under that id.
	proposals: as submit_result (kind, preview, payload, confidence, reason, alt_area); they wait for the owner. wiki: [{title, summary?, content_md, base_version?}] pages to create
	or merge. chat: {title, summary_md?, open_items?, source_system?, assistant?, date?, transcript_md?}.
	Answers {item, url, created, changed_fields, inputs, outputs, proposals, wiki, chat}."""
	if not permissions.has_app_permission():
		frappe.throw(_("Only Life OS users and agents can file work."), frappe.PermissionError)
	space = permissions.resolve_space(space, write=True)
	plan = _check(space, job_id, title, area, goal, inputs, outputs, proposals, wiki, chat)
	plan.update(instruction=instruction, raw_text=raw_text, transcript_md=transcript_md, summary_md=summary_md,
		system=(source_system or "").strip().lower()[:40] or DEFAULT_SYSTEM)
	savepoint = "lifeos_file_job"
	frappe.db.savepoint(savepoint)
	written = []  # stored copies this call put on disk, removed again if the call fails
	try:
		return _write(space, plan, written)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		_remove_unused(written)
		raise


# ---------- checking: nothing is written until every part is valid ----------

@contextmanager
def _at(field):
	"""Name the field in any error raised inside: `proposals[1]: due_date must be a date.`"""
	try:
		yield
	except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as e:
		message = str(e) or _("is not valid.")
		if message.startswith(f"{field}"):
			raise
		log = getattr(frappe.local, "message_log", None) or []
		if log and message in str(log[-1]):  # frappe.throw logged it once already; the named error replaces it
			frappe.clear_last_message()
		frappe.throw(f"{field}: {message}", type(e))


def _list(value, field):
	rows = parse(value, []) if not isinstance(value, builtins.list) else value
	if rows is None:
		return []
	if not isinstance(rows, builtins.list) or not all(isinstance(r, builtins.dict) for r in rows):
		frappe.throw(_("{0} must be a list of objects.").format(field))
	if len(rows) > MAX_ITEMS:
		frappe.throw(_("{0}: at most {1} in one call.").format(field, MAX_ITEMS))
	return rows


def _text(row, key, field, required=True, limit=140):
	value = row.get(key)
	value = str(value).strip() if value is not None else ""
	if required and not value:
		frappe.throw(_("{0}.{1} is required.").format(field, key))
	if len(value) > limit:
		frappe.throw(_("{0}.{1} can hold at most {2} characters.").format(field, key, limit))
	return value or None


def _check(space, job_id, title, area, goal, inputs, outputs, proposals, wiki, chat):
	job_id = (job_id or "").strip()
	if not job_id:
		frappe.throw(_("job_id is required: a stable id for the work, for example mehi-motors-pitch-2026-11-19."))
	if len(job_id) > 140:
		frappe.throw(_("job_id can hold at most 140 characters."))
	plan = {"job_id": job_id, "title": (title or "").strip()[:140] or None}
	plan["existing"] = _find_job(space, job_id)
	if not plan["title"] and not plan["existing"]:
		frappe.throw(_("title is required for a new job."))
	with _at("area"):
		plan["area"] = rules.resolve_link("Life Area", area, space) if area else None
	with _at("goal"):
		plan["goal"] = rules.resolve_link("Life Goal", goal, space) if goal else None
	if plan["goal"] and not plan["area"]:
		plan["area"] = frappe.db.get_value("Life Goal", plan["goal"], "area")
	plan["outputs"] = [_check_file_row(space, row, f"outputs[{i}]") for i, row in enumerate(_list(outputs, "outputs"))]
	plan["inputs"] = [_check_input(space, row, f"inputs[{i}]") for i, row in enumerate(_list(inputs, "inputs"))]
	for field, rows in (("inputs", plan["inputs"]), ("outputs", plan["outputs"])):
		names = [r["name"] for r in rows]
		if len(names) != len(set(names)):
			frappe.throw(_("{0}: two files have the same name.").format(field))
	plan["proposals"] = _check_proposals(space, proposals)
	plan["chat"] = _check_chat(chat)
	plan["wiki"] = _check_wiki(space, wiki)
	return plan


def _find_job(space, job_id):
	"""The item of this job, or an item filed the old way (agent/FILE_WORK.md before issue 8) with the job id as external_id.
	The lookup on the indexed job_id is locked, so a second call for a new job waits for the first instead of making a twin."""
	return frappe.db.get_value(JOB, {"space": space, "job_id": job_id}, for_update=True) or \
		frappe.db.get_value(JOB, {"space": space, "external_id": job_id, "job_id": ["is", "not set"]})


def _check_file_row(space, row, field):
	out = {"name": _text(row, "name", field, limit=140)}
	if "/" in out["name"] or "\\" in out["name"]:
		frappe.throw(_("{0}.name is a file name, not a path.").format(field))
	with _at(f"{field}.file"):
		out.update(_source(space, row.get("file")))
	return out


def _source(space, value):
	"""What a `file` value names: {"content": bytes} for base64, {"from": File row} for a file already in the space."""
	if not isinstance(value, str) or not value.strip():
		frappe.throw(_("is required: base64 content or the URL of a file in this space."))
	value = value.strip()
	if value.startswith(("/private/files/", "/files/")):
		return {"from": _file_in_space(space, value)}
	if value.startswith("data:"):
		value = value.split(",", 1)[-1]
	try:
		content = base64.b64decode("".join(value.split()), validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("is neither base64 nor the URL of a file (/private/files/...)."))
	if not content:
		frappe.throw(_("is empty."))
	return {"content": content}


def _file_in_space(space, file_url):
	"""A File row with this URL on a record of this space that the caller can read."""
	for row in frappe.get_all("File", filters={"file_url": file_url, "attached_to_doctype": ["in", SPACE_DOCTYPES]},
			fields=["name", "attached_to_doctype", "attached_to_name", "life_sha256"], order_by="creation asc"):
		if files.record_space(row.attached_to_doctype, row.attached_to_name) == space \
				and frappe.get_doc("File", row.name).has_permission("read"):
			return row
	frappe.throw(_("no file at {0} in this space that you can read.").format(file_url), frappe.DoesNotExistError)


def _check_input(space, row, field):
	reusable_as = _text(row, "reusable_as", field, required=False, limit=255)
	if reusable_as and row.get("file") is None:
		name = _text(row, "name", field)
		with _at(f"{field}.reusable_as"):
			asset = _find_asset(space, reusable_as)
			if not asset:
				frappe.throw(_("nothing is kept as {0} yet; send its file.").format(reusable_as), frappe.DoesNotExistError)
		out = {"name": name}
	else:
		out = _check_file_row(space, row, field)
	out.update(reusable_as=reusable_as, title=_text(row, "title", field, required=False),
		transcript_md=row.get("transcript_md") if isinstance(row.get("transcript_md"), str) else None)
	return out


def _find_asset(space, reusable_as):
	"""The item a reusable input is kept as: filed under this id by any agent (agent/FILE_WORK.md used external_id)."""
	return frappe.db.get_value(JOB, {"space": space, "external_id": reusable_as, "job_id": ["is", "not set"]})


def _check_proposals(space, value):
	out, ctx = [], {}
	for i, row in enumerate(_list(value, "proposals")):
		field = f"proposals[{i}]"
		kind = row.get("kind")
		if kind in rules.DIRECT:
			frappe.throw(_("{0}: a {1} is not filed with a piece of work.").format(field, kind))
		try:
			payload = rules.validate(kind, row.get("payload") or {}, space, ctx)
			confidence = 0.5 if row.get("confidence") is None else float(row.get("confidence"))
			extra = rules.extras(row, payload, space)
		except (rules.PayloadError, ValueError, TypeError) as e:
			frappe.throw(f"{field}: {e}", rules.PayloadError)
		if not 0 <= confidence <= 1:
			frappe.throw(_("{0}: confidence must be between 0 and 1.").format(field), rules.PayloadError)
		preview = (str(row.get("preview") or "").strip() or payload.get("title") or payload.get("subject") or kind)[:500]
		out.append({"kind": kind, "payload": payload, "confidence": confidence, "preview": preview, "key": _key(kind, payload), **extra})
	return out


def _key(kind, payload):
	return kind + json.dumps(payload, sort_keys=True, default=str)


def _check_chat(value):
	if value in (None, "", {}):
		return None
	chat = parse(value, None) if isinstance(value, str) else value
	if not isinstance(chat, builtins.dict):
		frappe.throw(_("chat must be an object."))
	_text(chat, "title", "chat")
	items = chat.get("open_items")
	if items is not None and not isinstance(items, builtins.list):
		frappe.throw(_("chat.open_items must be a list of text."))
	return chat


def _check_wiki(space, value):
	from lifeos.api import wiki as wiki_api

	out = []
	for i, row in enumerate(_list(value, "wiki")):
		field = f"wiki[{i}]"
		page = {"title": _text(row, "title", field), "summary": _text(row, "summary", field, required=False, limit=500),
			"content_md": row.get("content_md") if isinstance(row.get("content_md"), str) else None,
			"base_version": _text(row, "base_version", field, required=False)}
		if page["content_md"] is None:
			frappe.throw(_("{0}.content_md is required.").format(field))
		with _at(f"{field}.content_md"):
			wiki_api._check_text(page["content_md"])
		page["existing"] = _wiki_page(space, page["title"])
		if page["base_version"] and page["existing"]:
			with _at(field):
				doc = permissions.get_doc_checked("Life Note", page["existing"], "write")
				if page["base_version"] != wiki_api.version_of(doc):
					frappe.throw(_("base_version: the page changed since you read it. Read it again with wiki.get_page and merge."))
		out.append(page)
	if len({p["title"].lower() for p in out}) != len(out):
		frappe.throw(_("wiki: two pages have the same title."))
	return out


def _wiki_page(space, title):
	rows = frappe.db.sql("select name from `tabLife Note` where space=%s and collection='Wiki' and lower(title)=lower(%s) limit 1", (space, title))
	return rows[0][0] if rows else None


# ---------- writing ----------

def _write(space, plan, written):
	from lifeos.api import connections

	item, created, changed = _job_item(space, plan)
	outputs = [_output(item, row, written) for row in plan["outputs"]]
	inputs = [_input(space, item, plan, row, written) for row in plan["inputs"]]
	waiting = _proposals(item, plan["proposals"])
	chat = _chat(space, item, plan)
	if chat and item.job_chat != chat["name"]:
		item.job_chat = chat["name"]
	# attaching a file sets these in the database (files.after_insert, sources.on_file_attached); keep what it set
	item.update(frappe.db.get_value(JOB, item.name, ["preview_image", "thumbnail", "media_kind"], as_dict=True))
	item.status = "To Review" if waiting["waiting"] else "Done"
	item.error = None
	item.save()
	pages = [_wiki(space, item, chat, page) for page in plan["wiki"]]
	connections.touch(space, item.source_system, item.title)
	return {"item": item.name, "title": item.title, "status": item.status,
		"url": get_url("/life" + links.route_of(JOB, item.name)), "created": created, "updated": not created,
		"changed_fields": changed, "outputs": outputs, "inputs": inputs, "proposals": waiting, "wiki": pages, "chat": chat}


def _job_item(space, plan):
	"""Create the job's item, or update the one filed before. Returns (doc, created, changed_fields)."""
	values = {"title": plan["title"], "instruction": plan["instruction"], "raw_text": plan["raw_text"], "area": plan["area"],
		"goal": plan["goal"], "transcript_md": plan["transcript_md"], "summary_md": plan["summary_md"]}
	user = frappe.session.user
	if not plan["existing"]:
		item = frappe.get_doc({"doctype": JOB, "space": space, "source_type": "Upload", "intent": "Process", "status": "Processing",
			"source_system": plan["system"], "external_id": plan["job_id"], "job_id": plan["job_id"], "claimed_by": user,
			"claimed_on": now_datetime(), **{k: v for k, v in values.items() if v is not None}})
		item.insert()
		return item, True, []
	with _at("job_id"):
		item = permissions.get_doc_checked(JOB, plan["existing"], "write")
	changed = [k for k, v in values.items() if v is not None and (item.get(k) or "") != v]
	for k in changed:
		item.set(k, values[k])
	if item.intent != "Process":
		item.intent = "Process"
		changed.append("intent")
	item.job_id = plan["job_id"]
	if not item.external_id:  # an earlier file of the same name is kept as a version (issue 7) only on an item with an id
		item.source_system, item.external_id = plan["system"], plan["job_id"]
	item.claimed_by, item.claimed_on = user, now_datetime()
	if changed:
		item.add_comment("Info", _("Filed again as job {0} ({1}).").format(plan["job_id"], ", ".join(changed)))
	item.save()
	return item, False, changed


def _attach(doctype, name, file_name, source, written):
	"""Attach a file to a record unless the same bytes are already on it. Returns (File row, attached now)."""
	if "content" in source:
		digest = files.sha256(files.stored_bytes(file_name, source["content"]))
	else:
		digest = source["from"].life_sha256
	same = files.same_on_record(doctype, name, digest)
	if same:
		return frappe.get_doc("File", same), False
	doc = {"doctype": "File", "file_name": file_name, "attached_to_doctype": doctype, "attached_to_name": name, "is_private": 1}
	if "content" in source:
		doc["content"] = source["content"]
	else:
		doc["file_url"] = frappe.db.get_value("File", source["from"].name, "file_url")
	stored_before = bool(digest) and frappe.db.exists("File", {"life_sha256": digest})
	# the caller's write access to the record was checked; Frappe's own File permission would ask for the File role
	f = frappe.get_doc(doc).insert(ignore_permissions=True)
	if not stored_before and not frappe.db.exists("File", {"file_url": f.file_url, "name": ["!=", f.name]}):
		written.append(f.file_url)
	return f, True


def _file_out(f, attached):
	return {"name": f.file_name, "file": f.name, "file_url": f.file_url, "attached": attached}


def _output(item, row, written):
	with _at(f"outputs[{row['name']}]"):
		f, attached = _attach(JOB, item.name, row["name"], row, written)
	return _file_out(f, attached)


def _input(space, item, plan, row, written):
	"""A reusable input is kept once as its own item; any other input is attached to the job but listed as an input."""
	field = f"inputs[{row['name']}]"
	with _at(field):
		if row["reusable_as"]:
			asset, made = _asset(space, plan, row)
			f, attached = _attach(JOB, asset.name, row["name"], row, written) if ("content" in row or "from" in row) else (None, False)
			link = {"label": row["name"], "reusable_as": row["reusable_as"], "asset": asset.name, "file": None}
			out = {"name": row["name"], "reusable_as": row["reusable_as"], "asset": asset.name, "asset_created": made}
		else:
			f, attached = _attach(JOB, item.name, row["name"], row, written)
			link = {"label": row["name"], "reusable_as": None, "asset": None, "file": f.name}
			out = {"name": row["name"], "reusable_as": None, "asset": None, "asset_created": False}
	current = next((r for r in item.job_inputs if r.label == row["name"]), None)
	if current:
		current.update(link)
	else:
		item.append("job_inputs", link)
	if f:
		out.update(file=f.name, file_url=f.file_url, attached=attached)
	return out


def _asset(space, plan, row):
	"""The item a reusable input is kept as, made the first time: Just keep, processed at once (there is nothing to propose)."""
	name = _find_asset(space, row["reusable_as"])
	if name:
		asset = permissions.get_doc_checked(JOB, name, "write")
		if row["transcript_md"] is not None and asset.transcript_md != row["transcript_md"]:
			asset.transcript_md = row["transcript_md"]
			asset.save()
		return asset, False
	title = row["title"] or os.path.splitext(row["name"])[0]
	asset = frappe.get_doc({"doctype": JOB, "space": space, "title": title[:140], "source_type": "Upload", "intent": "Just keep",
		"status": "Done", "source_system": plan["system"], "external_id": row["reusable_as"], "area": plan["area"],
		"transcript_md": row["transcript_md"], "claimed_by": frappe.session.user, "claimed_on": now_datetime(),
		"summary_md": _("Kept as a reusable input ({0}).").format(row["reusable_as"])})
	asset.insert()
	return asset, True


def _proposals(item, wanted):
	"""The proposals of this call wait for the owner. One already there (by kind and payload) is kept, whatever its status;
	a pending one this call no longer sends is removed. Nothing is ever decided here."""
	have = frappe.get_all("Life Proposal", filters={"inbox_item": item.name},
		fields=["name", "kind", "payload", "status", "preview", "confidence", "reason", "alt_area"], order_by="sort_order asc, creation asc")
	by_key = {}
	for p in have:
		by_key.setdefault(_key(p.kind, frappe.parse_json(p.payload) if p.payload else {}), p)
	kept, made, used = [], [], set()
	for i, w in enumerate(wanted):
		p = by_key.get(w["key"])
		if p and p.name not in used:
			used.add(p.name)
			if p.status == "Pending" and (p.preview != w["preview"] or float(p.confidence or 0) != w["confidence"]
					or p.reason != w["reason"] or p.alt_area != w["alt_area"]):
				frappe.db.set_value("Life Proposal", p.name, {"preview": w["preview"], "confidence": w["confidence"], "sort_order": i,
					"reason": w["reason"], "alt_area": w["alt_area"]})
			kept.append(p.name)
			continue
		with _at(f"proposals[{i}]"):
			doc = frappe.get_doc({"doctype": "Life Proposal", "space": item.space, "inbox_item": item.name, "kind": w["kind"],
				"preview": w["preview"], "payload": frappe.as_json(w["payload"]), "confidence": w["confidence"], "status": "Pending",
				"sort_order": i, "reason": w["reason"], "alt_area": w["alt_area"]}).insert()
		made.append(doc.name)
	removed = [p.name for p in have if p.status == "Pending" and p.name not in used]
	for name in removed:
		frappe.delete_doc("Life Proposal", name, ignore_permissions=True, force=True)
	waiting = frappe.get_all("Life Proposal", filters={"inbox_item": item.name, "status": "Pending"},
		fields=["name", "kind", "preview"], order_by="sort_order asc, creation asc")
	return {"created": made, "kept": kept, "removed": removed, "waiting": waiting}


def _chat(space, item, plan):
	from lifeos.api import chats

	chat = plan["chat"]
	if not chat:
		return None
	with _at("chat"):
		out = chats.log(space=space, title=chat.get("title"), summary_md=chat.get("summary_md"), open_items=chat.get("open_items"),
			assistant=chat.get("assistant") or "Other", date=chat.get("date"), transcript_md=chat.get("transcript_md"),
			area=item.area, goal=item.goal, source_system=(chat.get("source_system") or item.source_system),
			external_id=plan["job_id"], url=chat.get("url"))
	return {"name": out["name"], "created": out["created"]}


def _wiki(space, item, chat, page):
	"""Create the page, or merge into the one there: the text replaces the page's own when this job wrote it last or the
	caller read the current version (`base_version`); otherwise it is added below, unless the page already holds it."""
	from lifeos.api import wiki as wiki_api

	sources = [{"doctype": JOB, "name": item.name}] + ([{"doctype": "Life Chat Log", "name": chat["name"]}] if chat else [])
	field = f"wiki[{page['title']}]"
	with _at(field):
		if not page["existing"]:
			out = wiki_api.create_page(space=space, title=page["title"], content_md=page["content_md"], summary=page["summary"],
				area=item.area, goal=item.goal, sources=sources, source={"doctype": JOB, "name": item.name},
				change_note=_("Filed with {0}.").format(item.title))
			return {"name": out["name"], "title": out["title"], "created": True, "changed": True}
		doc = permissions.get_doc_checked("Life Note", page["existing"], "write")
		text = doc.content_md or ""
		if page["base_version"] or _last_written_by(doc.name, item.name):
			new_text = page["content_md"]
		elif page["content_md"].strip() in text:
			new_text = text
		else:
			new_text = text.rstrip() + "\n\n" + page["content_md"].strip() + "\n"
		summary = page["summary"] if page["summary"] and page["summary"] != doc.summary else None
		have = {(r.source_doctype, r.source_name) for r in doc.sources}
		missing = [s for s in sources if (s["doctype"], s["name"]) not in have]
		if new_text == text and summary is None and not missing:
			return {"name": doc.name, "title": doc.title, "created": False, "changed": False}
		wiki_api.update_page(name=doc.name, content_md=new_text, base_version=wiki_api.version_of(doc), summary=summary,
			sources_add=missing, source={"doctype": JOB, "name": item.name}, change_note=_("Filed with {0}.").format(item.title))
	return {"name": doc.name, "title": doc.title, "created": False, "changed": True}


def _last_written_by(note, item):
	last = frappe.get_all("Life Wiki Change", filters={"note": note}, fields=["source_doctype", "source_name"],
		order_by="changed_on desc, creation desc", limit=1)
	return bool(last) and last[0].source_doctype == JOB and last[0].source_name == item


def _remove_unused(written):
	"""After a rollback: a stored copy this call wrote that no File row points to any more leaves the disk."""
	for url in written:
		if frappe.db.exists("File", {"file_url": url}):
			continue
		path = frappe.get_site_path(url.lstrip("/"))
		if url.startswith(("/private/files/", "/files/")) and os.path.isfile(path):
			os.remove(path)
