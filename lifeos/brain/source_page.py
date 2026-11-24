"""Sources as pages (issue 84): channels (where a thing comes from) and kinds (what it is), each with one skill in one template.

The numbers on a source's strip, its Rules (the skill's sections, saved as skill versions), its settings (the confidence above which it
files without the owner; which agents may read it) and Try it (what it would do with a sample, without filing).
"""
import json
import re

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder import functions as fn
from frappe.utils import add_to_date, flt, getdate, nowdate

from lifeos import permissions
from lifeos.skills import filing, store, template

KIND_PREFIX = "kind-"
# the channels every site shows, in order; every other connection is an agent
CHANNELS = (("upload", "Upload", "Files, photos, voice and text you add yourself", "Always on"),
	("phone", "Phone", "Captured on your phone", "Always on"),
	("gmail", "Gmail", "Email from real people", "Read only"),
	("google-calendar", "Google Calendar", "Meetings and events", "Read only"),
	("email", "Email-in address", "Mail you forward to Life OS", "Forwarded"))
ALWAYS_ON = ("upload", "phone")
HOW_TO_CONNECT = {"upload": "Drop a file or + Capture anywhere in Life OS.", "phone": "Capture from your phone with + Capture or the share sheet.",
	"gmail": "Connect Gmail in Brain › Sources. Life OS only reads.", "google-calendar": "Connect Google Calendar in Brain › Sources.",
	"email": "Set the email-in address below, then forward an email to it."}
KIND_LINES = {"document": "PDFs, scans and office files", "photo": "Photos, receipts and whiteboards", "video": "Recordings and clips, up to 500 MB",
	"link": "Links and saved articles", "voice": "Voice notes", "email": "Email threads"}
SOURCE_TYPE_OF = {"document": "Upload", "photo": "Upload", "video": "Upload", "link": "Web", "voice": "Voice Note", "email": "Email"}


def is_kind(key: str) -> bool:
	return key.startswith(KIND_PREFIX) and key[len(KIND_PREFIX):] in template.KINDS


def skill_of(key: str) -> str:
	return template.KINDS[key[len(KIND_PREFIX):]][0] if is_kind(key) else template.channel_skill(key)


def known(space: str, key: str) -> bool:
	"""A kind, one of the channels, or an agent the space has a connection for."""
	return is_kind(key) or key in (c[0] for c in CHANNELS) or bool(frappe.db.exists("Life Connection", {"space": space, "system": key}))


def title_of(space: str, key: str) -> str:
	if is_kind(key):
		return template.KINDS[key[len(KIND_PREFIX):]][1]
	for system, label, *_rest in CHANNELS:
		if system == key:
			return label
	from lifeos.agents import limits

	from lifeos.brain import agent_page

	if agent_page.is_agent_key(space, key):  # an agent is shown under the name the owner gave it, else "Your assistant" (issue 85)
		return limits.display_name(limits.config(space, key))
	return frappe.db.get_value("Life Connection", {"space": space, "system": key}, "label") or key.title()


# ---- counts ----
def _week_start():
	d = getdate(nowdate())
	return add_to_date(d, days=-d.weekday())


def _items(space: str, key: str):
	"""A query on this week's inbox items from a source: (query builder table, the query so far)."""
	i = frappe.qb.DocType("Life Inbox Item")
	if is_kind(key):
		kinds = [template.KINDS[key[len(KIND_PREFIX):]][2], *(["Email Digest"] if key == "kind-email" else [])]
		cond = i.media_kind.isin(kinds)
	elif key == "upload":
		cond = i.source_system.isnull() | i.source_system.isin(["", "upload"])
	else:
		cond = i.source_system == key
	return i, frappe.qb.get_query("Life Inbox Item", fields=[i.name], ignore_permissions=False).where((i.space == space) & (i.creation >= _week_start()) & cond)


def week_numbers(space: str, key: str) -> dict:
	"""This week: how many came in, the share of the Brain's proposals filed without the owner, and what reading them cost."""
	i, q = _items(space, key)
	names = q.run(pluck=True)
	out = {"count": len(names), "filed_without_you": None, "cost": 0.0}
	if not names:
		return out
	p, r = frappe.qb.DocType("Life Proposal"), frappe.qb.DocType("Life Skill Run")
	total, auto = frappe.qb.from_(p).select(fn.Count("*"), fn.Coalesce(fn.Sum(Case().when(fn.IfNull(p.filed_by, "") != "", 1).else_(0)), 0)).where(
		p.inbox_item.isin(names)).run()[0]
	if total:
		out["filed_without_you"] = round(100 * int(auto) / int(total))
	out["cost"] = round(flt(frappe.qb.from_(r).select(fn.Coalesce(fn.Sum(r.cost), 0)).where((r.input_doctype == "Life Inbox Item") & r.input_name.isin(names)).run()[0][0]), 4)
	return out


# ---- settings ----
def setting(space: str, key: str) -> dict:
	row = frappe.db.get_value("Life Source Setting", {"space": space, "source": key}, ["name", "auto_file_confidence", "readers"], as_dict=True)
	default = round(100 * (filing.settings()["threshold"]))
	readers = json.loads(row.readers) if row and row.readers else None
	return {"auto_file_confidence": row.auto_file_confidence if row else default, "default_confidence": default, "own": bool(row), "readers": readers}


def threshold_for(item) -> float | None:
	"""The confidence (0 to 1) above which what this capture brought is filed without the owner: its kind's own setting, else its channel's, else
	None (the setting in Settings)."""
	kind = next((k for k, v in template.KINDS.items() if v[2] == item.media_kind or (k == "email" and item.media_kind == "Email Digest")), None)
	keys = [f"{KIND_PREFIX}{kind}"] if kind else []
	keys.append((item.source_system or "upload").strip().lower())
	for key in keys:
		value = frappe.db.get_value("Life Source Setting", {"space": item.space, "source": key}, "auto_file_confidence")
		if value is not None:
			return value / 100
	return None


def agents() -> list:
	"""The agents (people with the Life Agent role, other than the Brain itself): [{user, name}]."""
	users = [u for u in frappe.get_all("Has Role", filters={"role": "Life Agent", "parenttype": "User"}, pluck="parent") if u != permissions.BRAIN_USER]
	rows = frappe.get_all("User", filters={"name": ("in", users), "enabled": 1}, fields=["name", "full_name"], order_by="full_name") if users else []  # system: user names for the agent list
	return [{"user": r.name, "name": r.full_name or r.name} for r in rows]


def agent_blocked(space: str, x) -> list:
	"""Criteria on Life Index rows that leave out what the signed-in agent may not read (the owner's choice on a source's page)."""
	user, out = frappe.session.user, []
	for row in frappe.get_all("Life Source Setting", filters={"space": space, "readers": ("is", "set")}, fields=["source", "readers"]):  # system: the agent's own limits
		if user in (json.loads(row.readers) or []):
			continue
		if row.source.startswith(KIND_PREFIX):
			kind = template.KINDS.get(row.source[len(KIND_PREFIX):])
			if kind:
				out.append(fn.IfNull(x.media_kind, "") != kind[2])
		elif row.source == "upload":
			out.append(~fn.IfNull(x.source_system, "").isin(["", "upload"]))
		else:
			out.append(fn.IfNull(x.source_system, "") != row.source)
	return out


def save_settings(space: str, key: str, auto_file_confidence: int | None, readers: list | None) -> dict:
	row = frappe.db.get_value("Life Source Setting", {"space": space, "source": key})
	doc = frappe.get_doc("Life Source Setting", row) if row else frappe.get_doc({"doctype": "Life Source Setting", "space": space, "source": key})
	if auto_file_confidence is not None:
		doc.auto_file_confidence = int(auto_file_confidence)
	if readers is not None:
		known_agents = {a["user"] for a in agents()}
		chosen = [u for u in readers if u in known_agents]
		doc.readers = None if len(chosen) == len(known_agents) else json.dumps(chosen)  # every agent allowed is the same as no list
	doc.save(ignore_permissions=True) if row else doc.insert(ignore_permissions=True)  # system: the space write check is in the API
	return setting(space, key)


# ---- the page ----
def page(space: str, key: str) -> dict:
	slug = skill_of(key)
	skill = frappe.get_doc("Life Skill", slug)
	kind = is_kind(key)
	conn = None if kind else frappe.db.get_value("Life Connection", {"space": space, "system": key}, ["name", "active", "label", "last_received_on", "last_received_what"], as_dict=True,
		order_by="active desc, creation asc")
	nums = week_numbers(space, key)
	active = 1 if kind or key in ALWAYS_ON else int(bool(conn and conn.active))
	channel_line = next((c[3] for c in CHANNELS if c[0] == key), "Agent")
	sets = setting(space, key)
	from lifeos.brain import agent_page

	return {"key": key, "group": "kind" if kind else "channel", "is_agent": int(agent_page.is_agent_key(space, key)), "title": title_of(space, key), "skill": slug, "version": skill.version,
		"skill_active": int(bool(skill.active)), "connection": dict(conn) if conn else None,
		"strip": {"active": active, "always_on": int(kind or key in ALWAYS_ON), "arrives_from": KIND_LINES[key[len(KIND_PREFIX):]] if kind else channel_line,
			"this_week": nums["count"], "filed_without_you": nums["filed_without_you"], "cost_week": nums["cost"], "skill_label": store.label(slug, skill.version)},
		"description": template.sections_of(skill.instructions).get("What arrives", ""), "rules": template.rules_of(slug, skill.instructions),
		"settings": {**sets, "agents": [{**a, "allowed": sets["readers"] is None or a["user"] in sets["readers"]} for a in agents()]},
		"how_to_connect": None if kind else HOW_TO_CONNECT.get(key, "Add it under Add more, then switch it on."),
		"versions": versions(slug), "examples": examples_of(slug), "lessons_text": lessons_in(skill.instructions), "recent": recent(space, key)}


def versions(slug: str) -> list:
	rows = frappe.get_list("Life Skill Version", filters={"skill": slug}, fields=["version", "changed_by", "changed_on", "note"], order_by="version desc", limit=30)
	names = {u.name: u.full_name for u in frappe.get_all("User", filters={"name": ("in", [r.changed_by for r in rows if r.changed_by])}, fields=["name", "full_name"])}  # system: user names
	return [{"version": r.version, "changed_by": names.get(r.changed_by) or r.changed_by, "changed_on": str(r.changed_on)[:16], "note": r.note} for r in rows]


def examples_of(slug: str) -> list:
	return [{"title": e.title, "last_result": e.last_result, "source": e.source} for e in frappe.get_all("Life Skill Example", filters={"skill": slug},
		fields=["title", "last_result", "source"], order_by="creation asc")]


def recent(space: str, key: str, limit: int = 20) -> list:
	i, q = _items(space, key)
	names = q.orderby(i.creation, order=frappe.qb.desc).limit(limit).run(pluck=True)
	rows = frappe.get_all("Life Inbox Item", filters={"name": ("in", names)}, fields=["name", "title", "status", "creation", "media_kind", "processed_by"], order_by="creation desc") if names else []
	return [{"name": r.name, "title": r.title or "Untitled", "status": r.status, "received": str(r.creation)[:16], "kind": r.media_kind, "processed_by": r.processed_by} for r in rows]


# ---- Rules ----
def save_rules(key: str, sections: dict, anything_else: str | None) -> dict:
	slug = skill_of(key)
	doc = frappe.get_doc("Life Skill", slug)
	text = template.with_rules(slug, doc.instructions, sections, anything_else)
	saved = store.save(slug, {"instructions": text}, _("Rules edited"))
	return {"skill": slug, "version": saved.version, "rules": template.rules_of(slug, saved.instructions)}


# ---- Try it ----
def sample_of(key: str, title: str | None, text: str | None, url: str | None, file_url: str | None):
	"""(a capture the way the runner reads one, the File documents it carries)."""
	file_docs = []
	if file_url:
		f = frappe.db.get_value("File", {"file_url": file_url}, "name")
		if not f:
			frappe.throw(_("Upload the sample first."), title=_("Sample missing"))
		doc = frappe.get_doc("File", f)
		doc.check_permission("read")
		file_docs.append(doc)
	if not (text or "").strip() and not file_docs and not (url or "").strip():
		frappe.throw(_("Drop a file, paste some text or a link to try it on."), title=_("Nothing to try"))
	kind = key[len(KIND_PREFIX):] if is_kind(key) else None
	system = None if kind else key
	item = frappe._dict(source_type=SOURCE_TYPE_OF.get(kind, "Phone" if system == "phone" else "Email" if system == "email" else "Upload"), received_on=nowdate(), intent="Process", name="TRY-IT",
		title=(title or (file_docs[0].file_name if file_docs else "") or "Sample")[:140], instruction="", source_url=(url or "").strip(), raw_text=text or "",
		source_system=system, media_kind=template.KINDS[kind][2] if kind else None)
	if file_docs:
		from lifeos.brain.sources import media_kind

		item.media_kind = media_kind(item.source_type, [file_docs[0].file_name], item.source_url)
	elif item.source_url and not item.media_kind:
		item.media_kind = "Article"
	return item, file_docs


def try_it(space: str, key: str, title: str | None = None, text: str | None = None, url: str | None = None, file_url: str | None = None) -> dict:
	"""What the source's rules would do with a sample: its summary, filing, proposals and what it skipped. Nothing is filed."""
	from lifeos.ai import client
	from lifeos.skills import runner

	item, file_docs = sample_of(key, title, text, url, file_url)
	base = frappe.get_doc("Life Skill", template.BASE)
	skill = runner.skill_values(base)
	skill["instructions"], more = template.put_together(skill["instructions"], template.channel_skill(item.source_system), template.kind_skill(item.media_kind))
	used = ", ".join(store.label(s, frappe.db.get_value("Life Skill", s, "version")) for s in (base.name, *more))
	try:
		client.check(f"Try it: {key}")
	except client.NotSetUp:
		frappe.throw(_("Life OS has no AI key yet, so it cannot try a sample. Add one in Settings."), title=_("No AI key"))
	except client.CapReached as e:
		frappe.throw(str(e)[:200], title=_("Over the spending cap"))
	try:
		blocks = runner._blocks_of(item, with_files=False, extra_files=file_docs)
		skill["patient"] = False
		state = runner.generate(skill, space, blocks, intent="Process", lenient=True)
	except runner.SkillError as e:
		frappe.throw(e.reason, title=_("It could not read the sample"))
	out = state["output"] if isinstance(state["output"], dict) else {}
	threshold = threshold_for(frappe._dict(media_kind=item.media_kind, source_system=item.source_system, space=space)) or filing.settings()["threshold"]
	rule = filing.settings()
	rows = [{"kind": p["kind"], "title": (p.get("payload") or {}).get("title") or p.get("preview") or p["kind"], "area": (p.get("payload") or {}).get("area"),
		"confidence": round(100 * flt(p.get("confidence"))), "reason": p.get("reason"),
		"files_alone": bool(p["kind"] in rule["kinds"] and flt(p.get("confidence")) >= threshold)} for p in state["proposals"]]
	return {"summary": out.get("summary_md") or "", "transcript": out.get("transcript_md") or "", "skipped": out.get("skipped") or [], "proposals": rows,
		"skills_used": used, "lessons_used": lessons_in(skill["instructions"]), "cost": state["cost"], "threshold": round(100 * threshold)}


def lessons_in(instructions: str) -> list:
	"""The lessons in the text a run was given: the lines under each Lessons heading."""
	lines = [line for t, body in template.parse(instructions)[1] if t == template.LESSONS for line in template.items_of(body)]
	return [re.sub(r"\s*<!--.*?-->", "", line).strip() for line in lines]


def file_for_real(space: str, key: str, title: str | None, text: str | None, url: str | None, file_url: str | None) -> dict:
	"""File the sample as a capture, which the Brain reads like any other (the same rules, the same Needs you)."""
	from lifeos.api import inbox

	item, file_docs = sample_of(key, title, text, url, file_url)
	made = inbox.create_item(title=item.title, source_type=item.source_type, space=space, raw_text=text or None, source_url=url or None, source_system=item.source_system)
	for f in file_docs:
		f.attached_to_doctype, f.attached_to_name, f.attached_to_field = "Life Inbox Item", made["name"], None
		f.save(ignore_permissions=True)  # system: the sample was uploaded by this person and the space write check is in the API
	return {"name": made["name"], "title": made["title"]}



# ---- Brain > Sources: the two groups ----
def _row(space: str, key: str, line: str, active: int, always_on: int, connected: bool) -> dict:
	slug = skill_of(key)
	return {"key": key, "title": title_of(space, key), "line": line, "active": active, "always_on": always_on, "connected": int(connected),
		"this_week": week_numbers(space, key)["count"], "skill": slug, "version": frappe.db.get_value("Life Skill", slug, "version"),
		"how_to": None if key.startswith(KIND_PREFIX) else HOW_TO_CONNECT.get(key, "Add it under Add more, then switch it on.")}


def groups(space: str) -> dict:
	"""{channels, kinds}: each row has its count this week; a channel not yet connected is listed with how to connect it."""
	conns = {c.system: c for c in frappe.get_list("Life Connection", filters={"space": space}, fields=["system", "active"], order_by="creation asc")}
	fixed = [c[0] for c in CHANNELS]
	channels = [_row(space, system, line, 1 if system in ALWAYS_ON else int(bool(conns.get(system) and conns[system].active)), int(system in ALWAYS_ON),
		system in ALWAYS_ON or system in conns) for system, _label, line, _kind in CHANNELS]
	channels += [_row(space, system, "Agent", int(bool(c.active)), 0, True) for system, c in conns.items() if system not in fixed]
	kinds = [_row(space, f"{KIND_PREFIX}{k}", KIND_LINES[k], 1, 1, True) for k in template.KINDS]
	return {"channels": channels, "kinds": kinds}


def teach(key: str, text: str) -> dict:
	"""Try it's "That's wrong… teach it": the owner's correction, in one or two plain sentences, becomes a line under the source's Lessons."""
	from lifeos.skills import lessons

	line = lessons.clean(text)
	if not line:
		frappe.throw(_("Say in a sentence what it should have done."), title=_("Nothing to teach"))
	slug = skill_of(key)
	doc = frappe.get_doc("Life Skill", slug)
	saved = store.save(slug, {"instructions": lessons.apply(doc.instructions, f"try-it-{frappe.generate_hash(length=6)}", line)}, _("Lesson from Try it"))
	return {"skill": slug, "version": saved.version, "lessons": lessons_in(saved.instructions)}
