"""Proposal payloads: the schema per kind, field-by-field validation, and creating the record on accept."""
import json

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, today

from lifeos import journal
from lifeos.life.doctype.life_check_in.life_check_in import parse_range

TITLE_FIELDS = {
	"Life Area": "area_name", "Life Project": "title", "Life Tag": "tag_name", "Life Goal": "title",
	"Life Person": "full_name", "Life Habit": "title", "Life Dimension": "dimension_name", "Life Note": "title",
}
PRIORITY = ["", "I", "II", "III", "IV"]


def F(type_, required=False, help="", **kw):
	return {"type": type_, "required": required, "help": help, **kw}


ORG = {
	"area": F("link", help="The one area where the record lives. Name or title of a Life Area in the item's space.", doctype="Life Area"),
	"also_in": F("links", help="Other areas where the record is relevant.", doctype="Life Area"),
	"project": F("link", help="Optional. Must belong to area or to one of also_in.", doctype="Life Project"),
	"tags": F("tags", help="Reuse existing tags. At most one new tag per inbox item.", doctype="Life Tag"),
}

SCHEMA = {
	"Task": {
		"target": "Life Task", "filed": True,
		"fields": {
			"title": F("text", True), "priority": F("select", options=PRIORITY, help="I to IV as written in the journal."),
			"due_date": F("date", help="ISO date. Never invent one."), "status": F("select", options=["Open", "Doing", "Waiting"]),
			"waiting_on": F("text"), "goal": F("link", doctype="Life Goal"), "source_url": F("text"), "notes_md": F("markdown"), **ORG,
		},
		"example": {"title": "Meet Arjun Singh for PMS", "priority": "I", "area": "Money & Legal", "goal": "Money"},
	},
	"Event": {
		"target": "Event", "filed": False,
		"fields": {
			"subject": F("text", True), "starts_on": F("datetime", True, "ISO date and time, site time zone."),
			"ends_on": F("datetime"), "all_day": F("bool"), "description": F("markdown"),
		},
		"example": {"subject": "Call with Vivek on the ITR", "starts_on": "2026-11-14 16:30:00"},
	},
	"Important Date": {
		"target": "Life Important Date", "filed": False,
		"fields": {
			"title": F("text", True), "day": F("int", True), "month": F("int", True), "year": F("int", help="Optional year it first happened."),
			"kind": F("select", options=["Birthday", "Anniversary", "Other"]), "person": F("link", doctype="Life Person"),
		},
		"example": {"title": "Ruchi", "day": 14, "month": 1, "kind": "Birthday"},
	},
	"Note": {
		"target": "Life Note", "filed": True,
		"fields": {"title": F("text", True), "content_md": F("markdown"), "parent_note": F("link", doctype="Life Note"), **ORG},
		"example": {"title": "Estate training programme outline", "content_md": "## Aim\n...", "area": "Tea & Coffee"},
	},
	"Vault Document": {
		"target": "Life Vault Document", "filed": True,
		"fields": {
			"title": F("text", True), "doc_type": F("select", options=["ID", "Travel", "Insurance", "Property", "Tax", "Medical", "Other"]),
			"holder": F("link", doctype="Life Person"), "number_last4": F("text", help="Only the last four characters. Never the full number.", max_length=4),
			"issue_date": F("date"), "expiry_date": F("date"), "remind_days_before": F("int"), "notes_md": F("markdown"),
			"file_url": F("text", help="One of the inbox item's file URLs. Defaults to its first file."), **ORG,
		},
		"example": {"title": "Driving licence", "doc_type": "ID", "expiry_date": "2026-12-12", "number_last4": "4821", "area": "Personal"},
	},
	"Month Goal": {
		"target": "Life Month Plan", "filed": False,
		"fields": {
			"title": F("text", True), "year": F("int", True), "month": F("int", True), "priority": F("select", options=PRIORITY),
			"status": F("select", options=["Open", "Done", "Carried", "Dropped"]), "area": ORG["area"],
		},
		"example": {"title": "GHL visit", "year": 2026, "month": 11, "priority": "I", "area": "Tea & Coffee"},
	},
	"Habit Log": {
		"target": "Life Habit Log", "filed": False,
		"fields": {"habit": F("link", True, "Name or title of a Life Habit.", doctype="Life Habit"), "date": F("date", True), "done": F("bool")},
		"example": {"habit": "Japa", "date": "2026-11-14", "done": True},
	},
	"Check-in": {
		"target": "Life Check-in", "filed": False,
		"fields": {
			"date": F("date", True),
			"scores": F("scores", True, "List of {dimension, habits, situation, note}. A score is 0 to 10, as a number or a range such as '2-3'."),
			"reflection_md": F("markdown"),
		},
		"example": {"date": "2026-11-14", "scores": [{"dimension": "Money", "habits": "2-3", "situation": 7, "note": "PMS pending"}]},
	},
	"Week Tick": {
		"target": "Life Goal", "filed": False,
		"fields": {
			"goal": F("link", True, "Name or title of a Life Goal in the active cycle.", doctype="Life Goal"),
			"action": F("text", True, "Title or id of one of the goal's actions."),
			"week": F("int", help="1 to 12. Defaults to the current week."), "count": F("int", help="Ticks in that week. Defaults to 1."),
			"mark_done": F("bool", help="True when the action is finished once and for all (struck through in the journal)."),
		},
		"example": {"goal": "Close open loops", "action": "Anya passport", "mark_done": True},
	},
	"Journal Page": {
		"target": "Life Journal Page", "filed": True,
		"fields": {"page_date": F("date", True), "page_number": F("text", help="For example 187 or 187-188."), "transcript_md": F("markdown"), **ORG},
		"example": {"page_date": "2026-11-14", "page_number": "187-188", "transcript_md": "Goal Oct to Dec ..."},
	},
}
AREA_REQUIRED = ("Task", "Note", "Vault Document")


class PayloadError(frappe.ValidationError):
	pass


def schema():
	"""The allowed payload fields and an example for each proposal kind."""
	return {kind: {"target": s["target"], "fields": s["fields"], "example": s["example"]} for kind, s in SCHEMA.items()}


def resolve_link(doctype, value, space, extra_filters=None):
	"""Accept a record name or its title and return the name, checked to be in the space."""
	value = str(value).strip()
	if frappe.db.get_value(doctype, {"name": value, "space": space}):
		return value
	matches = frappe.get_all(doctype, filters={TITLE_FIELDS[doctype]: value, "space": space, **(extra_filters or {})}, pluck="name", order_by="creation desc")
	if not matches and extra_filters:
		matches = frappe.get_all(doctype, filters={TITLE_FIELDS[doctype]: value, "space": space}, pluck="name", order_by="creation desc")
	if not matches:
		raise PayloadError(_("{0} '{1}' was not found in this space.").format(doctype.replace("Life ", ""), value))
	return matches[0]


def _coerce(name, spec, value, space, ctx):
	t = spec["type"]
	if t in ("text", "markdown"):
		if not isinstance(value, (str, int, float)):
			raise PayloadError(_("{0} must be text.").format(name))
		value = str(value)
		if spec.get("max_length") and len(value) > spec["max_length"]:
			raise PayloadError(_("{0} can hold at most {1} characters.").format(name, spec["max_length"]))
		return value
	if t == "select":
		if value not in spec["options"]:
			raise PayloadError(_("{0} must be one of: {1}.").format(name, ", ".join(o or "blank" for o in spec["options"])))
		return value
	if t == "date":
		try:
			return str(getdate(str(value)))
		except Exception:
			raise PayloadError(_("{0} must be a date in ISO form, such as 2026-11-14.").format(name))
	if t == "datetime":
		try:
			return str(get_datetime(str(value)).replace(microsecond=0))
		except Exception:
			raise PayloadError(_("{0} must be a date and time in ISO form.").format(name))
	if t == "int":
		try:
			return int(value)
		except (TypeError, ValueError):
			raise PayloadError(_("{0} must be a whole number.").format(name))
	if t == "bool":
		if isinstance(value, str):
			return 1 if value.strip().lower() in ("1", "true", "yes", "y", "done") else 0
		return 1 if value else 0
	if t == "link":
		extra = None
		if spec["doctype"] == "Life Goal":
			active = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"})
			extra = {"cycle": active} if active else None
		return resolve_link(spec["doctype"], value, space, extra)
	if t == "links":
		if isinstance(value, str):
			value = [value]
		if not isinstance(value, list):
			raise PayloadError(_("{0} must be a list.").format(name))
		return [resolve_link(spec["doctype"], v, space) for v in value if v]
	if t == "tags":
		if isinstance(value, str):
			value = [value]
		if not isinstance(value, list):
			raise PayloadError(_("{0} must be a list.").format(name))
		out = []
		for v in value:
			v = str(v.get("new") if isinstance(v, dict) else v or "").strip()
			if not v:
				continue
			try:
				out.append(resolve_link("Life Tag", v, space))
			except PayloadError:
				new = ctx.setdefault("new_tags", set())
				if v.lower() not in new and len(new) >= 1 and not ctx.get("allow_new_tags"):
					raise PayloadError(_("Only one new tag may be proposed per item. '{0}' is a second new tag.").format(v))
				new.add(v.lower())
				out.append({"new": v})
		return out
	if t == "scores":
		if not isinstance(value, list) or not value:
			raise PayloadError(_("scores must be a list with at least one dimension."))
		out = []
		for row in value:
			if not isinstance(row, dict) or not row.get("dimension"):
				raise PayloadError(_("Each score needs a dimension."))
			unknown = set(row) - {"dimension", "habits", "situation", "note", "habits_low", "habits_high", "situation_low", "situation_high"}
			if unknown:
				raise PayloadError(_("Unknown score field: {0}.").format(", ".join(sorted(unknown))))
			item = {"dimension": resolve_link("Life Dimension", row["dimension"], space), "note": str(row.get("note") or "")}
			for kind in ("habits", "situation"):
				raw = row.get(kind)
				if raw is None and row.get(f"{kind}_low") is not None:
					raw = [row.get(f"{kind}_low"), row.get(f"{kind}_high", row.get(f"{kind}_low"))]
				low, high = parse_range(raw)
				if low is not None and not (0 <= low <= 10 and 0 <= high <= 10):
					raise PayloadError(_("Scores are 0 to 10."))
				item[f"{kind}_low"], item[f"{kind}_high"] = low, high
			out.append(item)
		return out
	raise PayloadError(_("Unknown field type for {0}.").format(name))


def validate(kind, payload, space, ctx=None) -> dict:
	"""Check a payload field by field and return it normalised. Raises PayloadError with a clear message."""
	ctx = {} if ctx is None else ctx
	if kind not in SCHEMA:
		raise PayloadError(_("Unknown proposal kind '{0}'. Kinds are: {1}.").format(kind, ", ".join(SCHEMA)))
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			raise PayloadError(_("payload is not valid JSON."))
	if not isinstance(payload, dict):
		raise PayloadError(_("payload must be an object of field values."))
	fields = SCHEMA[kind]["fields"]
	if "owner" in payload:
		raise PayloadError(_("A payload cannot set owner."))
	if "space" in payload:
		if payload["space"] != space:
			raise PayloadError(_("A payload cannot set a space other than the inbox item's space."))
		payload = {k: v for k, v in payload.items() if k != "space"}
	unknown = [k for k in payload if k not in fields]
	if unknown:
		raise PayloadError(_("Field '{0}' is not allowed for {1}. Allowed: {2}.").format(unknown[0], kind, ", ".join(fields)))
	out = {}
	for name, spec in fields.items():
		value = payload.get(name)
		if value is None or value == "" or value == []:
			if spec["required"]:
				raise PayloadError(_("{0} is required for {1}.").format(name, kind))
			continue
		out[name] = _coerce(name, spec, value, space, ctx)
	_cross_checks(kind, out, space)
	return out


def _cross_checks(kind, p, space):
	if p.get("project"):
		project_area = frappe.db.get_value("Life Project", p["project"], "area")
		if project_area not in [p.get("area"), *(p.get("also_in") or [])]:
			raise PayloadError(_("The project must belong to the proposal's area or to one of its other areas."))
	if kind in ("Important Date", "Month Goal") and not 1 <= p["month"] <= 12:
		raise PayloadError(_("month must be 1 to 12."))
	if kind == "Important Date" and not 1 <= p["day"] <= 31:
		raise PayloadError(_("day must be 1 to 31."))
	if kind == "Week Tick":
		p["action"] = _find_action(p["goal"], p["action"])
		if p.get("week") is not None and not 1 <= p["week"] <= 12:
			raise PayloadError(_("week must be 1 to 12."))
	if kind == "Event" and p.get("ends_on") and p["ends_on"] < p["starts_on"]:
		raise PayloadError(_("ends_on is before starts_on."))


def _find_action(goal, action):
	action = str(action).strip()
	rows = frappe.get_all("Life Goal Action", filters={"parent": goal, "parenttype": "Life Goal"}, fields=["name", "title"])
	for r in rows:
		if r.name == action or r.title.lower() == action.lower():
			return r.name
	raise PayloadError(_("Action '{0}' was not found on that goal.").format(action))


# ---------- creating the record ----------

def _tag_names(tags, space):
	out = []
	for t in tags or []:
		if isinstance(t, dict):
			existing = frappe.db.get_value("Life Tag", {"space": space, "tag_name": t["new"]})
			out.append(existing or frappe.get_doc({"doctype": "Life Tag", "space": space, "tag_name": t["new"]}).insert(ignore_permissions=True).name)
		else:
			out.append(t)
	return out


def _org(p, space):
	return {
		"area": p.get("area"), "project": p.get("project"),
		"also_in": [{"area": a} for a in p.get("also_in") or []],
		"tags": [{"tag": t} for t in _tag_names(p.get("tags"), space)],
	}


def _item_files(item):
	from lifeos import files
	return files.attachments("Life Inbox Item", item)


def _attach_copy(file_url, doctype, name, fieldname):
	"""Attach the same stored file to another record. The original stays on the inbox item."""
	src = frappe.db.get_value("File", {"file_url": file_url}, ["file_name", "is_private"], as_dict=True)
	if not src:
		return None
	frappe.get_doc({"doctype": "File", "file_url": file_url, "file_name": src.file_name, "is_private": 1,
		"attached_to_doctype": doctype, "attached_to_name": name, "attached_to_field": fieldname}).insert(ignore_permissions=True)
	return file_url


def apply(kind, payload, item) -> tuple:
	"""Create the target record for an accepted proposal. Returns (doctype, name)."""
	space = item.space
	p = validate(kind, payload, space, {"allow_new_tags": True})
	if kind in AREA_REQUIRED and not p.get("area"):
		raise PayloadError(_("Choose an area before accepting this {0}.").format(kind.lower()))
	base = {"space": space, "inbox_item": item.name}

	if kind == "Task":
		doc = frappe.get_doc({"doctype": "Life Task", **base, **{k: p.get(k) for k in
			("title", "priority", "due_date", "status", "waiting_on", "goal", "notes_md")}, **_org(p, space),
			"source_url": p.get("source_url") or item.source_url})
		doc.status = doc.status or "Open"
		doc.insert()
	elif kind == "Event":
		doc = frappe.get_doc({"doctype": "Event", "subject": p["subject"], "starts_on": p["starts_on"], "ends_on": p.get("ends_on"),
			"all_day": p.get("all_day") or 0, "description": p.get("description"), "event_type": "Public", "life_space": space})
		doc.insert()
	elif kind == "Important Date":
		doc = frappe.get_doc({"doctype": "Life Important Date", **base, **{k: p.get(k) for k in ("title", "day", "month", "year", "person")},
			"kind": p.get("kind") or "Birthday"}).insert()
	elif kind == "Note":
		doc = frappe.get_doc({"doctype": "Life Note", **base, "title": p["title"], "content_md": p.get("content_md"),
			"parent_note": p.get("parent_note"), **_org(p, space)}).insert()
	elif kind == "Vault Document":
		files = _item_files(item.name)
		urls = [f.file_url for f in files]
		file_url = p.get("file_url") or (urls[0] if urls else None)
		if file_url and file_url not in urls:
			raise PayloadError(_("file_url must be one of the inbox item's files."))
		doc = frappe.get_doc({"doctype": "Life Vault Document", **base, **{k: p.get(k) for k in
			("title", "holder", "number_last4", "issue_date", "expiry_date", "notes_md")}, "doc_type": p.get("doc_type") or "Other",
			"remind_days_before": p.get("remind_days_before") if p.get("remind_days_before") is not None else 60, **_org(p, space)}).insert()
		if file_url:
			doc.db_set("file", _attach_copy(file_url, doc.doctype, doc.name, "file"), update_modified=False)
		# the source now follows Vault access (UX fixes, set 4)
		frappe.db.set_value("Life Inbox Item", item.name, "vault_document", doc.name, update_modified=False)
		from lifeos import index
		index.update(frappe.get_doc("Life Inbox Item", item.name))
	elif kind == "Month Goal":
		plan = journal.get_month_plan(space, p["year"], p["month"], create=True)
		plan.check_permission("write")
		plan.append("goals", {"title": p["title"], "priority": p.get("priority"), "status": p.get("status") or "Open", "area": p.get("area")})
		plan.save()
		doc = plan
	elif kind == "Habit Log":
		journal.toggle_habit(p["habit"], p["date"], bool(p.get("done", 1)))
		name = frappe.db.get_value("Life Habit Log", {"habit": p["habit"], "date": p["date"]})
		if name:
			frappe.db.set_value("Life Habit Log", name, "inbox_item", item.name, update_modified=False)
			return "Life Habit Log", name
		return "Life Habit", p["habit"]
	elif kind == "Check-in":
		doc = frappe.get_doc({"doctype": "Life Check-in", **base, "date": p["date"], "scores": p["scores"],
			"reflection_md": p.get("reflection_md")}).insert()
	elif kind == "Week Tick":
		goal = frappe.get_doc("Life Goal", p["goal"])
		cycle = frappe.get_doc("Life Cycle", goal.cycle)
		week = p.get("week") or journal.current_week(cycle)
		journal.set_tick(p["action"], week, p.get("count") if p.get("count") is not None else 1, inbox_item=item.name)
		if p.get("mark_done"):
			journal.set_action_status(p["action"], "Done")
		return "Life Goal", goal.name
	elif kind == "Journal Page":
		doc = frappe.get_doc({"doctype": "Life Journal Page", **base, "page_date": p["page_date"], "page_number": p.get("page_number"),
			"transcript_md": p.get("transcript_md") or item.transcript_md, **_org(p, space)}).insert()
		images = [f for f in _item_files(item.name) if (f.file_name or "").lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"))]
		if images:
			doc.db_set("image", _attach_copy(images[0].file_url, doc.doctype, doc.name, "image"), update_modified=False)
	return doc.doctype, doc.name
