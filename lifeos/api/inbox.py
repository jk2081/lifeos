"""Inbox pipeline: capture, claim, submit, fail, retry. See section 5 of the spec."""
import builtins

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder import functions as fn
from frappe.utils import add_to_date, now_datetime

from lifeos.library import extract, files, links
from lifeos import permissions
from lifeos.brain import proposals
from lifeos.api.utils import (area_criterion, count_by, count_tabs, count_where, filter_criteria, flag, group_summary, in_order_of, list_query, names_map, order_terms,
	page, parse, sort_terms, user_names)

CLAIM_MINUTES = 30
LIST = list  # this module defines its own `list` method below
SOURCE_TYPES = ["Upload", "Journal Photo", "Voice Note", "Email", "Email Digest", "Chat", "Message", "Web", "Phone"]


def _item_dict(item, with_files=True):
	d = {k: item.get(k) for k in ("name", "space", "title", "source_type", "received_on", "instruction", "raw_text", "transcript_md",
		"summary_md", "source_url", "status", "claimed_by", "claimed_on", "error", "area", "goal", "is_archived", "owner", "preview_image",
		"intent", "media_kind", "source_system", "external_id", "thumbnail", "is_sensitive", "job_id")}
	d["received_on"] = str(d["received_on"]) if d["received_on"] else None
	d["claimed_on"] = str(d["claimed_on"]) if d["claimed_on"] else None
	if with_files:
		d["files"] = [{**_file_dict(f), "versions": [_file_dict(v) for v in f.versions]}
			for f in files.attachments("Life Inbox Item", item.name)]
		if item.get("job_id"):
			d.update(_job_parts(item))
	return d


def _job_parts(item):
	"""Issue 8: a job's inputs (each kept asset or file used only here), its chat log and the wiki pages that cite it."""
	inputs = []
	for row in item.job_inputs:
		entry = {"name": row.label, "reusable_as": row.reusable_as, "asset": row.asset, "asset_title": None, "file": None}
		if row.asset:
			entry["asset_title"] = frappe.db.get_value("Life Inbox Item", row.asset, "title")
			entry["asset_route"] = links.route_of("Life Inbox Item", row.asset)
			current = [f for f in files.attachments("Life Inbox Item", row.asset) if f.file_name == row.label] \
				or files.attachments("Life Inbox Item", row.asset)
			if current:
				entry["file"] = {**_file_dict(current[0]), "versions": [_file_dict(v) for v in current[0].versions]}
		elif row.file:
			f = frappe.db.get_value("File", row.file, ["file_name", "file_url", "file_size", "creation"], as_dict=True)
			entry["file"] = {**_file_dict(f), "versions": []} if f else None
		inputs.append(entry)
	chat = frappe.db.get_value("Life Chat Log", item.job_chat, ["name", "title"], as_dict=True) if item.job_chat else None
	if chat:
		chat["route"] = links.route_of("Life Chat Log", chat.name)
	n, ns = frappe.qb.DocType("Life Note"), frappe.qb.DocType("Life Note Source")
	where = [ns.parenttype == "Life Note", ns.source_doctype == "Life Inbox Item", ns.source_name == item.name, n.collection == "Wiki"]
	pages = frappe.qb.get_query("Life Note", fields=[n.name, n.title], ignore_permissions=False).join(ns).on(ns.parent == n.name)  # the pages the user may read
	for crit in where:
		pages = pages.where(crit)
	pages = pages.orderby(n.title).limit(50).run(as_dict=True)
	for wiki_page in pages:
		wiki_page["route"] = links.route_of("Life Note", wiki_page.name)
	return {"inputs": inputs, "job_chat": chat, "wiki_pages": pages}


def _file_dict(f):
	return {"file_name": f.file_name, "file_url": f.file_url, "file_size": f.file_size, "added": str(f.creation)}


INTENTS = ("Process", "Add to wiki", "Just keep")


@frappe.whitelist(methods=["POST"])
def create_item(title: str | None = None, source_type: str = "Upload", space: str | None = None, raw_text: str | None = None,
		instruction: str | None = None, source_url: str | None = None, intent: str | None = None, source_system: str | None = None,
		external_id: str | None = None, area: str | None = None, goal: str | None = None):
	"""Create an inbox item. Attach files afterwards with /api/method/upload_file (doctype, docname, is_private=1).

	intent: Process (the default), Add to wiki or Just keep. With source_system (gmail, claude, upload…) the space's connection for
	that system gives the default intent, area and goal. With source_system and external_id (the original's ID in that system)
	an item that already exists is updated instead of created: every argument passed (title, raw_text, source_url, instruction,
	intent, area, goal) replaces the old value and an argument left out keeps it. A Done item whose content changed, or a Done or
	Failed item whose intent changed, goes back to New so the agent processes it again. The answer carries `created` and `updated`
	(true or false), and on an update `changed_fields`."""
	from lifeos.api import connections

	space = permissions.resolve_space(space, write=True)
	if source_type not in SOURCE_TYPES:
		frappe.throw(_("source_type must be one of: {0}.").format(", ".join(SOURCE_TYPES)), title=_("Unknown source type"))
	if intent and intent not in INTENTS:
		frappe.throw(_("intent must be one of: {0}.").format(", ".join(INTENTS)), title=_("Unknown intent"))
	system = (source_system or "").strip().lower() or None
	connections.require_on(space, system)
	existing = frappe.db.get_value("Life Inbox Item", {"space": space, "source_system": system, "external_id": external_id.strip()}) \
		if system and (external_id or "").strip() else None
	if existing:
		return _refile(existing, system, source_type, {"title": (title or "").strip()[:140] or None, "raw_text": raw_text,
			"source_url": source_url, "instruction": instruction, "intent": intent, "area": area, "goal": goal})
	conn = connections.connection(space, system) if system else None
	title = (title or "").strip() or f"{source_type}, {frappe.utils.format_datetime(now_datetime(), 'd MMM HH:mm')}"
	item = frappe.get_doc({"doctype": "Life Inbox Item", "space": space, "title": title[:140], "source_type": source_type,
		"raw_text": raw_text, "instruction": instruction, "source_url": source_url, "status": "New",
		"intent": intent or (conn.default_intent if conn and conn.active else None) or "Process",
		"source_system": system, "external_id": (external_id or "").strip() or None,
		"area": area or (conn.default_area if conn else None),
		"goal": goal or (conn.default_goal if conn else None)})
	item.insert()
	if system:
		connections.touch(space, system, item.title)
	return {**_item_dict(item), "created": True, "updated": False}


CONTENT_FIELDS = ("title", "raw_text", "source_url", "instruction")


def _refile(name, system, source_type, values):
	"""Update an item filed again with the same source_system and external_id. `values` left as None keep the old value."""
	from lifeos.api import connections

	item = permissions.get_doc_checked("Life Inbox Item", name, "write")
	item.source_type = source_type
	changed_fields = []
	for field, value in values.items():
		if value is not None and (item.get(field) or "") != value:
			item.set(field, value)
			changed_fields.append(field)
	content_changed = any(f in CONTENT_FIELDS for f in changed_fields)
	intent_changed = "intent" in changed_fields
	if (content_changed and item.status == "Done") or (intent_changed and item.status in ("Done", "Failed")):
		if item.status == "Failed":  # as retry does: the old attempt's pending proposals go
			for proposal in frappe.get_list("Life Proposal", filters={"inbox_item": item.name, "status": "Pending"}, pluck="name"):
				frappe.delete_doc("Life Proposal", proposal, ignore_permissions=True, force=True)  # system: inbox processing is the Brain's and agents' own work; the space check is above
		item.status, item.error = "New", None
		item.add_comment("Info", _("Updated from {0} ({1}), so it went back to the agent.").format(system, ", ".join(changed_fields)))
	elif changed_fields:
		item.add_comment("Info", _("Updated from {0} ({1}).").format(system, ", ".join(changed_fields)))
	item.save()
	if item.status == "New" and changed_fields:  # back with the Brain, or with the agent that filed it (issue 58)
		from lifeos.skills import triggers

		triggers.capture_created(item)
	connections.touch(item.space, system, item.title)
	return {**_item_dict(item), "created": False, "updated": True, "changed": bool(changed_fields), "changed_fields": changed_fields}


def release_stale_claims():
	"""A claim older than 30 minutes goes back to New. Runs every five minutes and before each claim."""
	cutoff = add_to_date(now_datetime(), minutes=-CLAIM_MINUTES)
	stale = frappe.get_all("Life Inbox Item", filters={"status": "Processing", "claimed_on": ("<", cutoff)}, pluck="name")  # system: the stale-claim sweep covers every user's items
	for name in stale:
		frappe.db.set_value("Life Inbox Item", name, {"status": "New", "claimed_by": None, "claimed_on": None})
	return len(stale)


@frappe.whitelist(methods=["POST"])
def claim_next(space: str | None = None):
	"""Claim the oldest New item. Returns it with its file URLs and the filing context, or nothing."""
	permissions.require_login()
	release_stale_claims()
	if space:
		spaces = [permissions.require_space(space, write=True)]
	else:
		spaces = [s for s, access in permissions.user_spaces().items() if access == "Write"]
	if not spaces:
		return None
	# a source a Vault document was made from is hidden from an agent while that Vault is closed to it
	closed = [sp for sp in spaces if permissions.vault_hidden(sp)] or [""]
	i = frappe.qb.DocType("Life Inbox Item")
	hidden = fn.IfNull(i.vault_document, "") != ""
	rows = (frappe.qb.from_(i).select(i.name).where((i.status == "New") & (i.is_archived == 0) & i.space.isin(spaces) & ~((hidden | (i.is_sensitive == 1)) & i.space.isin(closed)))
		.orderby(i.received_on).orderby(i.creation).limit(1).for_update(skip_locked=True).run())  # system: the queue is claimed by whoever asks, the spaces were chosen above
	if not rows:
		return None
	item = frappe.get_doc("Life Inbox Item", rows[0][0])
	item.status = "Processing"
	item.claimed_by = frappe.session.user
	item.claimed_on = now_datetime()
	item.error = None
	item.save()
	out = _item_dict(item)
	out.update(extract.of_item(item))
	out["context"] = space_context(item.space)
	# what the agent must respect: the intent, and the filing defaults of the system it came from
	from lifeos.api import connections

	out["connection"] = connections.defaults(item.space, item.source_system) if item.source_system else None
	out["rules"] = {
		"Process": "Use extracted_text, summarise and propose records for review.",
		"Add to wiki": "Use extracted_text, then create or edit wiki pages directly with lifeos.api.wiki (cite this item). Propose tasks or events "
			"for review as usual; do not propose notes.",
		"Just keep": "The text is already read and searchable (extracted_text). Propose nothing.",
	}[item.intent or "Process"] + " Life OS has read the files on its own server: read a file yourself only when needs_closer_read is true, or when " \
		"extraction_pending is true and you cannot wait."
	return out


def space_context(space):
	"""What an agent needs to file proposals: the space's areas, people, habits and goals in progress.
	`areas` (issue 11) holds the areas of life that are on, each followed by its parts: file only into these. `areas_off`
	names the areas of life that are switched off; nothing may be filed there, and their goals are left out."""
	from lifeos.goals import areas as life

	areas = life.ordered(space, fields=["name", "area_name", "parent_area", "is_life_area", "description", "colour", "is_pinned", "is_focus", "standard"])
	principles = {}
	focus_names = [a.name for a in areas if a.is_focus]
	if focus_names:
		for row in frappe.get_list("Life Area Principle", filters={"parent": ("in", focus_names), "parenttype": "Life Area"}, fields=["parent", "line"],
				order_by="idx", parent_doctype="Life Area", limit=0):
			principles.setdefault(row.parent, []).append(row.line)
	for a in areas:  # focuses (issue 57) only when the owner uses them: the standard and principles agents work within
		if a.is_focus:
			a["principles"] = principles.get(a.name, [])
		else:
			a.pop("is_focus", None), a.pop("standard", None)
	off = set(life.off(space))
	areas_off = [a.area_name for a in life.ordered(space, include_off=True, fields=["name", "area_name"]) if a.is_life_area and a.name in off]
	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "title", "start_date"], as_dict=True)
	# every goal in progress, of every type, for filing a task under it; 12 Week Year goals of the active cycle carry their actions
	goals = []
	g, c = frappe.qb.DocType("Life Goal"), frappe.qb.DocType("Life Cycle")
	where = [g.space == space, g.outcome == "In Progress", (fn.IfNull(g.cycle, "") == "") | c.status.isin(["Active", "Planned"])]
	fields = ["name", "title", "area", "horizon", "cycle", "measure_kind", "measure", "unit", "start_value", "target_value", "current_value", "current_on"]
	rows = list_query("Life Goal", fields, where, [(in_order_of(g.horizon, ("12 weeks", "Month", "Year", "Long term")), Order.asc), (g.sort_order, Order.asc), (g.title, Order.asc)])
	rows = rows.left_join(c).on(c.name == g.cycle).run(as_dict=True)
	cycle_goals = [g.name for g in rows if g.cycle and g.area not in off]
	actions = {}
	if cycle_goals:
		for row in frappe.get_list("Life Goal Action", filters={"parent": ("in", cycle_goals)}, fields=["parent", "name", "title", "status", "per_week"],
				order_by="idx", parent_doctype="Life Goal", limit=0):
			actions.setdefault(row.pop("parent"), []).append(row)
	for g in rows:
		if g.area in off:  # the goals of an area that is off are hidden
			continue
		g["actions"] = actions.get(g.name, []) if g.cycle else []
		if g.measure_kind == "Number":  # a number goal: what a Reading proposal reports (set 7)
			g["measure"] = {"measure": g.measure, "unit": g.unit, "start": g.start_value, "target": g.target_value, "current": g.current_value if g.current_on else None}
		g.pop("unit", None), g.pop("start_value", None), g.pop("target_value", None), g.pop("current_value", None), g.pop("current_on", None)
		goals.append(g)
	return {
		"space": space,
		"areas": areas,
		"areas_off": areas_off,
		"people": frappe.get_list("Life Person", filters={"space": space}, fields=["name", "full_name", "relation"], limit=500),
		"habits": frappe.get_list("Life Habit", filters={"space": space, "is_archived": 0}, fields=["name", "title"], limit=200),
		"cycle": ({"name": cycle.name, "title": cycle.title, "start_date": str(cycle.start_date)} if cycle else None),
		"goals": goals,
	}


def _claimed_item(item_name):
	item = permissions.get_doc_checked("Life Inbox Item", item_name, "write")
	if item.status != "Processing":
		frappe.throw(_("This item is not being processed. Claim it first."), title=_("Item not claimed"))
	if item.claimed_by != frappe.session.user and not permissions.is_admin():
		frappe.throw(_("This item is claimed by someone else."), frappe.PermissionError, title=_("Item claimed by someone else"))
	return item


@frappe.whitelist(methods=["POST"])
def submit_result(item: str, transcript_md: str | None = None, summary_md: str | None = None, proposals: str | builtins.list | None = None):
	"""Store the transcript, summary and proposals, and set the item To Review.

	Each proposal is {kind, preview, payload, confidence, reason, alt_area}; the last two are optional (see meta.proposal_schema). An invalid proposal is refused with a clear error; the rest are kept.
	"""
	from lifeos.brain import proposals as rules

	doc = _claimed_item(item)
	rows = parse(proposals, []) or []
	if not isinstance(rows, LIST):
		frappe.throw(_("proposals must be a list."), title=_("Proposals must be a list"))
	if rows and doc.intent == "Just keep":
		frappe.throw(_("This item is to be kept only (intent Just keep). Send its text with no proposals."), title=_("Item is kept only"))
	if doc.intent == "Add to wiki" and any(isinstance(r, dict) and r.get("kind") == "Note" for r in rows):
		frappe.throw(_("This item is for the wiki (intent Add to wiki). Write wiki pages with lifeos.api.wiki instead of proposing notes."), title=_("Item is for the wiki"))
	created, errors, ctx, readings_made = [], [], {}, []
	for i, row in enumerate(rows):
		try:
			if not isinstance(row, dict):
				raise rules.PayloadError(_("Each proposal must be an object."))
			kind = row.get("kind")
			payload = rules.validate(kind, row.get("payload") or {}, doc.space, ctx)
			confidence = row.get("confidence")
			confidence = 0.5 if confidence is None else float(confidence)
			if not 0 <= confidence <= 1:
				raise rules.PayloadError(_("confidence must be between 0 and 1."))
			extra = rules.extras(row, payload, doc.space)
			if kind in rules.DIRECT:  # a Reading is stored at once as a Suggested reading for the weekly review (set 7)
				r = rules.store_reading(payload, doc)
				readings_made.append({"index": i, "name": r.name, "kind": kind})
				continue
			preview = (row.get("preview") or payload.get("title") or payload.get("subject") or kind)[:500]
			p = frappe.get_doc({"doctype": "Life Proposal", "space": doc.space, "inbox_item": doc.name, "kind": kind, "preview": preview,
				"payload": frappe.as_json(payload), "confidence": confidence, "status": "Pending", "sort_order": i, **extra}).insert()
			created.append({"index": i, "name": p.name, "kind": kind})
		except (rules.PayloadError, ValueError, TypeError) as e:
			errors.append({"index": i, "kind": row.get("kind") if isinstance(row, dict) else None,
				"preview": row.get("preview") if isinstance(row, dict) else None, "error": str(e)})
	doc.transcript_md = transcript_md if transcript_md is not None else doc.transcript_md
	doc.summary_md = summary_md if summary_md is not None else doc.summary_md
	doc.status = "To Review" if created or readings_made or not rows or doc.summary_md or doc.transcript_md else "Failed"
	if doc.status == "Failed":
		doc.error = _("Every proposal was invalid.")
	doc.save()
	if doc.status == "To Review" and not created:
		_finish_if_decided(doc)
	return {"item": doc.name, "status": doc.status, "created": created, "errors": errors, "readings": readings_made}


def _finish_if_decided(doc):
	"""An item with no pending proposal is Done."""
	if doc.status != "To Review":
		return doc.status
	if not frappe.db.exists("Life Proposal", {"inbox_item": doc.name, "status": "Pending"}):
		# saved, not set: the Outbox hooks record the item leaving the Inbox (set 7)
		doc.reload()
		doc.status, doc.finished_on = "Done", frappe.utils.today()
		doc.save(ignore_permissions=True)  # system: inbox processing is the Brain's and agents' own work; the space check is above
	return doc.status


@frappe.whitelist(methods=["POST"])
def fail_item(item: str, error: str | None = None):
	"""Mark a claimed item Failed, with the reason."""
	doc = _claimed_item(item)
	doc.status = "Failed"
	doc.error = (error or _("Processing failed."))[:1000]
	doc.save()
	return {"item": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def retry(item: str):
	"""Send a Failed item back to New so an agent picks it up again. Pending proposals of the old attempt are removed."""
	doc = permissions.get_doc_checked("Life Inbox Item", item, "write")
	if permissions.is_agent():
		frappe.throw(_("Only a person can retry an item."), frappe.PermissionError, title=_("Only a person can retry"))
	if doc.status not in ("Failed", "To Review", "Processing"):
		frappe.throw(_("Only a failed item can be retried."), title=_("Item has not failed"))
	for name in frappe.get_list("Life Proposal", filters={"inbox_item": doc.name, "status": "Pending"}, pluck="name"):
		frappe.delete_doc("Life Proposal", name, ignore_permissions=True, force=True)  # system: inbox processing is the Brain's and agents' own work; the space check is above
	doc.status = "New"
	doc.error = None
	doc.save()
	from lifeos.skills import triggers

	triggers.capture_created(doc)  # the Brain's skill, when it is on, takes it again
	return {"item": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def file_myself(item: str):
	"""The owner takes a capture the Brain could not process (Needs you, Unfiled): it leaves the queue as Done, and they file it by hand
	from its page. Its pending proposals, if any, are removed. People only."""
	if permissions.is_agent():
		frappe.throw(_("Only a person can file a capture by hand."), frappe.PermissionError, title=_("Only a person can file"))
	doc = permissions.get_doc_checked("Life Inbox Item", item, "write")
	if doc.status not in ("Failed", "New"):
		frappe.throw(_("Only a capture that was not processed can be filed by hand."), title=_("Capture was processed"))
	for name in frappe.get_list("Life Proposal", filters={"inbox_item": doc.name, "status": "Pending"}, pluck="name"):
		frappe.delete_doc("Life Proposal", name, ignore_permissions=True, force=True)  # system: inbox processing is the Brain's and agents' own work; the space check is above
	doc.status, doc.error = "Done", None
	doc.add_comment("Info", _("Filed by hand: the Brain did not process it."))
	doc.save()
	return {"item": doc.name, "status": doc.status}


SORTS = {k: (lambda i, k=k: [i[k]]) for k in ("received_on", "title", "status", "source_type")}


def tab_criteria(i):
	"""The state tabs of the Inbox screen: it is a queue (UX fixes, set 4), so its tabs are what is not finished. Done items are in
	Sources; `Done` and `all` stay here for agents and old links."""
	return {"To Review": i.status == "To Review", "Waiting": i.status.isin(["New", "Processing"]), "Failed": i.status == "Failed", "Done": i.status == "Done",
		"all": None}


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, status: str | builtins.list | None = None, include_archived: bool | int = 0, start: int = 0,
		page_length: int = 30, source_type: str | None = None, area: str | None = None, from_date: str | None = None,
		to_date: str | None = None, sort: str | None = None, dir: str | None = None, filters: str | builtins.list | builtins.dict | None = None,
		order_by: str | None = None, summary: str | builtins.dict | None = None):
	"""Inbox items of a space, newest first, with proposal counts.
	Filters: status (one status or a JSON list), source_type, area (with its sub-areas, or "none"), from_date and to_date on the day received.
	`total` is the number of items the filters match; `pending_total` is the pending proposals of those items.
	`tabs` counts the items on each state tab of the Inbox screen (To Review, Waiting = New and Processing, Failed, Done, all)
	under the same filters, whatever status was asked for."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	i = frappe.qb.DocType("Life Inbox Item")
	where = [i.space == space]
	if permissions.vault_hidden(space):  # an agent never lists the source a Vault document was made from (pre-step 6 audit)
		where.append((fn.IfNull(i.vault_document, "") == "") & (i.is_sensitive == 0))
	if not flag(include_archived):
		where.append(i.is_archived == 0)
	if source_type:
		where.append(i.source_type == source_type)
	if area:
		where.append(area_criterion(space, area, i, also_in="Life Inbox Item"))
	if from_date:
		where.append(fn.Date(i.received_on) >= frappe.utils.getdate(from_date))
	if to_date:
		where.append(fn.Date(i.received_on) <= frappe.utils.getdate(to_date))
	where += filter_criteria("Life Inbox Item", filters, i)
	# the state tabs of the Inbox screen, counted under every filter but the status itself
	tabs = count_tabs("Life Inbox Item", where, tab_criteria(i))
	if status:
		statuses = parse(status) if str(status).startswith("[") else [status]
		where.append(i.status.isin(statuses or [""]))
	if summary:
		return {"summary": group_summary("Life Inbox Item", where, summary, start, page_length), "tabs": tabs}
	terms = order_terms("Life Inbox Item", order_by, i, SORTS) or sort_terms(sort, dir, SORTS, i, [(i.received_on, Order.desc)])
	fields = ["name", "title", "source_type", "status", "received_on", "instruction", "claimed_by", "error", "owner", "area", "summary_md", "transcript_md"]
	rows = list_query("Life Inbox Item", fields, where, [*terms, (i.creation, Order.desc)]).limit(page_length).offset(start).run(as_dict=True)
	total = count_where("Life Inbox Item", where)
	p = frappe.qb.DocType("Life Proposal")
	pending = frappe.qb.get_query("Life Proposal", fields=[fn.Count("*")], ignore_permissions=False).join(i).on(i.name == p.inbox_item).where(p.status == "Pending")
	for crit in where:
		pending = pending.where(crit)
	pending_total = pending.run()[0][0]
	counts = {}
	if rows:
		per = frappe.qb.get_query("Life Proposal", fields=[p.inbox_item, p.status, fn.Count("*")], ignore_permissions=False).where(p.inbox_item.isin([r.name for r in rows]))
		for item, st, n in per.groupby(p.inbox_item, p.status).run():
			counts.setdefault(item, {})[st] = n
	users = user_names([r.owner for r in rows] + [r.claimed_by for r in rows])
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	for r in rows:
		c = counts.get(r.name, {})
		r["proposals"] = sum(c.values())
		r["pending"] = c.get("Pending", 0)
		r["has_transcript"] = bool(r.pop("transcript_md"))
		r["has_summary"] = bool(r.pop("summary_md"))
		r["received_on"] = str(r.received_on) if r.received_on else None
		r["filed_by"] = users.get(r.owner)
		r["processed_by"] = users.get(r.claimed_by)
		r["area_name"] = areas.get(r.area)
	totals = count_by("Life Inbox Item", "status", [i.space == space, i.is_archived == 0])
	return {"items": rows, "total": total, "pending_total": pending_total, "totals": totals, "tabs": tabs, "start": start, "page_length": page_length}


@frappe.whitelist(methods=["GET"])
def get(item: str):
	"""One inbox item with its files, proposals and the choices for the filing chips."""
	doc = permissions.get_doc_checked("Life Inbox Item", item)
	out = _item_dict(doc)
	out.update(extract.of_item(doc))
	users = user_names([doc.owner, doc.claimed_by])
	out["filed_by"], out["processed_by"] = users.get(doc.owner), users.get(doc.claimed_by)
	out["area_name"] = frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None
	out["goal_title"] = frappe.db.get_value("Life Goal", doc.goal, "title") if doc.goal else None
	props = frappe.get_list("Life Proposal", filters={"inbox_item": doc.name},
		fields=["name", "kind", "preview", "payload", "confidence", "reason", "alt_area", "status", "created_doctype", "created_name", "decided_on"],
		order_by="sort_order asc, creation asc", limit=100)
	for p in props:
		p["payload"] = frappe.parse_json(p.payload) if p.payload else {}
		p["filed"] = proposals.SCHEMA[p.kind]["filed"]
		if p.created_doctype and p.created_name:
			p["route"] = links.route_of(p.created_doctype, p.created_name)
			p["exists"] = bool(frappe.db.exists(p.created_doctype, p.created_name))
	out["proposals"] = props
	out["context"] = space_context(doc.space)
	return out


@frappe.whitelist(methods=["GET"])
def item_page(item: str):
	"""Issue 10: one item's page. Everything `get` returns, plus `came_of_it` (the records made from it, each with its state),
	`related` (wiki pages and chat logs that cite it, the meetings it is linked to) and the space's name. An item the user may
	not read is answered as not found, so its page says nothing about it."""
	from lifeos.library import item_page

	if not frappe.db.exists("Life Inbox Item", item) or not frappe.has_permission("Life Inbox Item", "read", doc=item):
		raise frappe.DoesNotExistError(_("Not found"))
	out = get(item)
	doc = frappe.get_doc("Life Inbox Item", item)
	out["space_name"] = frappe.db.get_value("Life Space", doc.space, "space_name") or doc.space
	out["filed_by_agent"] = permissions.is_agent(doc.owner)
	out["came_of_it"] = item_page.came_of_it(doc)
	out["related"] = item_page.related(doc)
	return out


