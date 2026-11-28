"""Proposal payloads: the schema per kind, field-by-field validation, and creating the record on accept."""
import json

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, today

from lifeos.calendar import calendar_data
from lifeos.goals import cycles, habits, readings
from lifeos.web import gone_names

TITLE_FIELDS = {
	"Life Area": "area_name", "Life Goal": "title",
	"Life Person": "full_name", "Life Habit": "title", "Life Note": "title",
}
PRIORITY = ["", "I", "II", "III", "IV"]


def F(type_, required=False, help="", **kw):
	return {"type": type_, "required": required, "help": help, **kw}


ORG = {
	"area": F("link", help="The one area where the record lives. Name or title of a Life Area in the item's space.", doctype="Life Area"),
	"also_in": F("links", help="Other areas where the record is relevant.", doctype="Life Area"),
	"goal": F("link", help="Optional. The goal the record belongs to.", doctype="Life Goal"),
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
			"attendees": F("text", help="Emails to invite, comma separated. Nobody is invited unless given."),
		},
		"example": {"subject": "Call with Vivek on the ITR", "starts_on": "2026-11-14 16:30:00"},
	},
	"Important Date": {
		"target": "Event", "filed": False,
		"fields": {
			"title": F("text", True), "day": F("int", True), "month": F("int", True), "year": F("int", help="Optional year it first happened."),
			"kind": F("select", options=["Birthday", "Anniversary", "Other"]),
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
	"Goal": {
		"target": "Life Goal", "filed": False,
		"fields": {
			"title": F("text", True), "horizon": F("select", options=["Year", "12 weeks", "Month"],
				help="Optional. Worked out from target_date when left out. A 12-weeks goal joins the active cycle. Ongoing work is a focus, which only a person creates."),
			"target_date": F("date", help="ISO date. A Year or Month goal needs one."), "area": ORG["area"],
			"serves": F("link", help="Optional. The longer goal it serves, one horizon up.", doctype="Life Goal"),
			"done_when": F("text", help="The finish line, in one line."),
		},
		"example": {"title": "GHL visit", "horizon": "Month", "target_date": "2026-11-30", "area": "Tea & Coffee"},
	},
	# accepted as a Goal with horizon Month, for one release
	"Month Goal": {
		"target": "Life Goal", "filed": False,
		"fields": {"title": F("text", True), "year": F("int", True), "month": F("int", True), "area": ORG["area"], "done_when": F("text", help="The finish line, in one line.")},
		"example": {"title": "GHL visit", "year": 2026, "month": 11, "area": "Tea & Coffee"},
	},
	"Habit Log": {
		"target": "Life Habit Log", "filed": False,
		"fields": {"habit": F("link", True, "Name or title of a Life Habit.", doctype="Life Habit"), "date": F("date", True), "done": F("bool")},
		"example": {"habit": "Japa", "date": "2026-11-14", "done": True},
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
	# a photographed journal page: a note in My notes, with the photo, the transcript and the day it was written
	"Journal Page": {
		"target": "Life Note", "filed": True,
		"fields": {"page_date": F("date", True), "page_number": F("text", help="For example 187 or 187-188."), "transcript_md": F("markdown"), **ORG},
		"example": {"page_date": "2026-11-14", "page_number": "187-188", "transcript_md": "Goal Oct to Dec ..."},
	},
	# UX fixes, set 5: an agent may propose parking something; only a person's Accept parks it
	"Someday": {
		"target": "Life Task", "filed": False,
		"fields": {
			"record_type": F("text", True, "Task, Goal or Note to park an existing record; New task or New note to park something new."),
			"record": F("text", help="For Task, Goal and Note: the name (id) or exact title of the record to park."),
			"title": F("text", help="For New task and New note: the title, in one line.", max_length=140),
			"body_md": F("markdown", help="For New task and New note: more detail."),
			"area": F("link", help="For New task and New note: the area it belongs to.", doctype="Life Area"),
			"note": F("text", help="Why it can wait. Shown on the Someday list."),
		},
		"example": {"record_type": "Task", "record": "Get quotes for a solar dryer pilot", "note": "Not before the monsoon."},
	},
	# set 7: a value of a number goal's measure, read from the item. It does not wait in the Inbox: it is stored at once as a
	# Suggested reading, which the owner confirms or rejects in the weekly review or on the goal
	"Reading": {
		"target": "Life Goal Reading", "filed": False, "direct": True,
		"fields": {
			"goal": F("link", True, "Name or exact title of a goal measured by a number (measure_kind Number in the context).", doctype="Life Goal"),
			"value": F("float", True, "The value, in the goal's unit."),
			"date": F("date", help="ISO date the value is for. Defaults to the item's date."),
			"excerpt": F("text", True, "The exact words the value was read from, at most 300 characters.", max_length=300),
			"source": F("text", help="Optional. The record it came from as Doctype:name; defaults to this inbox item."),
		},
		"example": {"goal": "Ghillidary yield to 1,800 kg/ha", "value": 1640, "date": "2026-11-14", "excerpt": "Yield this flush came to 1,640 kg/ha"},
	},
}
# issue 111: a page for a new sender, and the question "is this the same as ..?"; the Brain proposes, only a person's Accept makes or joins
SCHEMA["New Subject"] = {
	"target": "Life Person", "filed": False,
	"fields": {"name": F("text", True, "The company's name, or the person's when there is no company."), "kind": F("select", options=["Person", "Organisation"]),
		"person": F("text", help="The person who wrote, when the page is for their company."), "email": F("text"), "role": F("text"), "address": F("text")},
	"example": {"name": "Shri Ambaji Food Products", "kind": "Organisation", "person": "Anirudh Poddar", "email": "anirudh@example.com"},
}
SCHEMA["Same Subject"] = {
	"target": "Life Person", "filed": False,
	"fields": {"name": F("text", True, "The name seen in the email."), "same_as": F("link", True, "The existing person or company it may be: its name (id) or exact title.", doctype="Life Person"),
		"address": F("text"), "kind": F("select", options=["Person", "Organisation"])},
	"example": {"name": "Shakambhari Foods", "same_as": "abc123"},
}
AREA_REQUIRED = ("Task", "Note", "Vault Document")
# kinds stored straight away instead of waiting in the Inbox for review
DIRECT = tuple(k for k, s in SCHEMA.items() if s.get("direct"))


class PayloadError(frappe.ValidationError):
	pass


# beside the payload, a proposal carries these two optional fields (issue 17)
EXTRAS = {
	"reason": F("text", help="One short line on why this was proposed, or what made you unsure. Shown to the owner on Needs you.", max_length=200),
	"alt_area": F("link", help="Only when two areas are both likely: the second choice. It must be an area that is on, in the same space, "
		"and not the payload's area. The owner picks one.", doctype="Life Area"),
}


def schema():
	"""The allowed payload fields and an example for each proposal kind. `beside_payload` names the optional fields a proposal
	carries next to its payload (reason, alt_area), the same for every kind."""
	return {kind: {"target": s["target"], "fields": s["fields"], "example": s["example"], "beside_payload": EXTRAS} for kind, s in SCHEMA.items()}


def extras(row, payload, space):
	"""Validate `reason` and `alt_area` of a proposal row (beside its payload). Returns {"reason", "alt_area"}, each None when not sent."""
	reason = row.get("reason")
	reason = None if reason is None else " ".join(str(reason).split())
	if reason and len(reason) > EXTRAS["reason"]["max_length"]:
		raise PayloadError(_("reason can hold at most {0} characters.").format(EXTRAS["reason"]["max_length"]))
	alt = row.get("alt_area")
	if alt in (None, ""):
		return {"reason": reason or None, "alt_area": None}
	if not payload.get("area"):
		raise PayloadError(_("alt_area needs an area in the payload: it is the second choice to that area."))
	alt = _switched_on("Life Area", resolve_link("Life Area", alt, space), space)
	if alt == payload["area"]:
		raise PayloadError(_("alt_area must be a different area from the payload's area."))
	return {"reason": reason or None, "alt_area": alt}


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


def _switched_on(doctype, name, space):
	"""Nothing is filed into an area that is switched off, or a part of one (issue 11)."""
	from lifeos.goals import areas

	if doctype == "Life Area" and areas.is_off(space, name):
		area = frappe.db.get_value("Life Area", name, ["area_name", "parent_area", "is_on"], as_dict=True)
		life = area.area_name if area.is_on == 0 or not area.parent_area else frappe.db.get_value("Life Area", area.parent_area, "area_name")
		raise PayloadError(_("The area {0} is switched off, so nothing can be filed there. Choose an area that is on, or ask the "
			"owner to switch {1} on in Settings > Areas.").format(area.area_name, life))
	return name


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
	if t == "float":
		try:
			value = float(value)
		except (TypeError, ValueError):
			raise PayloadError(_("{0} must be a number.").format(name))
		if value != value or value in (float("inf"), float("-inf")):
			raise PayloadError(_("{0} must be a number.").format(name))
		return value
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
		return _switched_on(spec["doctype"], resolve_link(spec["doctype"], value, space, extra), space)
	if t == "links":
		if isinstance(value, str):
			value = [value]
		if not isinstance(value, list):
			raise PayloadError(_("{0} must be a list.").format(name))
		return [_switched_on(spec["doctype"], resolve_link(spec["doctype"], v, space), space) for v in value if v]
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
	gone_names.refuse(payload)
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
	if kind in ("Important Date", "Month Goal") and not 1 <= p["month"] <= 12:
		raise PayloadError(_("month must be 1 to 12."))
	if kind == "Important Date" and not 1 <= p["day"] <= 31:
		raise PayloadError(_("day must be 1 to 31."))
	if kind == "Week Tick":
		p["action"] = _find_action(p["goal"], p["action"])
		if p.get("week") is not None and not 1 <= p["week"] <= 12:
			raise PayloadError(_("week must be 1 to 12."))
	if kind == "Reading" and frappe.db.get_value("Life Goal", p["goal"], "measure_kind") != "Number":
		raise PayloadError(_("goal must be a goal measured by a number."))
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

def _org(p, space):
	return {
		"area": p.get("area"), "goal": p.get("goal"),
		"also_in": [{"area": a} for a in p.get("also_in") or []],
	}


def _item_files(item):
	from lifeos.library import files
	return files.attachments("Life Inbox Item", item)


def _attach_copy(file_url, doctype, name, fieldname):
	"""Attach the same stored file to another record. The original stays on the inbox item."""
	src = frappe.db.get_value("File", {"file_url": file_url}, ["file_name", "is_private"], as_dict=True)
	if not src:
		return None
	frappe.get_doc({"doctype": "File", "file_url": file_url, "file_name": src.file_name, "is_private": 1,
		"attached_to_doctype": doctype, "attached_to_name": name, "attached_to_field": fieldname}).insert()
	return file_url


def apply(kind, payload, item) -> tuple:
	"""Create the target record for an accepted proposal. Returns (doctype, name)."""
	space = item.space
	p = validate(kind, payload, space, {})
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
		from lifeos.review import gcal_write
		gcal_write.push_event(doc, p.get("attendees"))
	elif kind == "Important Date":
		doc = calendar_data.add_yearly_date(space, p["title"], p["day"], p["month"], p.get("year"), p.get("kind") or "Birthday")
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
		from lifeos.library import index
		index.update(frappe.get_doc("Life Inbox Item", item.name))
	elif kind in ("Goal", "Month Goal"):
		if kind == "Month Goal":
			first, last = cycles.month_bounds(p["year"], p["month"])
			p = {**p, "horizon": "Month", "target_date": str(last)}
		if not p.get("horizon") and not p.get("target_date"):  # no horizon and no date would be an Open goal, which is retired (issue 57)
			raise PayloadError(_("Give the goal a horizon (Year, 12 weeks or Month) or a target date."))
		doc = frappe.get_doc({"doctype": "Life Goal", "space": space, "title": p["title"], "horizon": p.get("horizon"), "area": p.get("area"),
			"target_date": p.get("target_date"), "serves": p.get("serves"), "done_when": p.get("done_when")}).insert()
	elif kind == "Habit Log":
		habits.toggle_habit(p["habit"], p["date"], bool(p.get("done", 1)))
		name = frappe.db.get_value("Life Habit Log", {"habit": p["habit"], "date": p["date"]})
		if name:
			frappe.db.set_value("Life Habit Log", name, "inbox_item", item.name, update_modified=False)
			return "Life Habit Log", name
		return "Life Habit", p["habit"]
	elif kind == "Week Tick":
		goal = frappe.get_doc("Life Goal", p["goal"])
		cycle = frappe.get_doc("Life Cycle", goal.cycle)
		week = p.get("week") or cycles.current_week(cycle)
		cycles.set_tick(p["action"], week, p.get("count") if p.get("count") is not None else 1, inbox_item=item.name)
		if p.get("mark_done"):
			cycles.set_action_status(p["action"], "Done")
		return "Life Goal", goal.name
	elif kind == "Someday":
		return _apply_someday(p, item)
	elif kind in ("New Subject", "Same Subject"):
		from lifeos.library import subjects

		return "Life Person", (subjects.accept_new if kind == "New Subject" else subjects.accept_same)(space, p, item)[1]
	elif kind == "Journal Page":
		title = f"Journal page {p['page_number']}" if p.get("page_number") else "Journal page"
		doc = frappe.get_doc({"doctype": "Life Note", **base, "title": f"{title}, {p['page_date']}", "collection": "My notes", "page_date": p["page_date"],
			"content_md": p.get("transcript_md") or item.transcript_md, **_org(p, space)}).insert()
		images = [f for f in _item_files(item.name) if (f.file_name or "").lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"))]
		if images:
			doc.db_set("image", _attach_copy(images[0].file_url, doc.doctype, doc.name, "image"), update_modified=False)
	return doc.doctype, doc.name


SOMEDAY_TYPES = {"Task": "Life Task", "Goal": "Life Goal", "Note": "Life Note"}


def _apply_someday(p, item):
	"""Accepting a Someday proposal parks the record it names, or makes a new Someday task or note."""
	from lifeos import permissions
	from lifeos.api import someday

	kind = str(p.get("record_type") or "").strip().title()
	if kind in ("New Task", "New Note"):
		if not p.get("title"):
			raise PayloadError(_("Something to park needs a title."))
		task = kind == "New Task"
		doc = frappe.get_doc({"doctype": "Life Task" if task else "Life Note", "space": item.space, "title": p["title"],
			"notes_md" if task else "content_md": p.get("body_md"), "area": p.get("area"), "inbox_item": item.name,
			**({"status": "Someday"} if task else {"is_someday": 1}), "someday_on": today(), "someday_review_on": someday.review_date(),
			"someday_note": p.get("note")}).insert()
		return doc.doctype, doc.name
	doctype = SOMEDAY_TYPES.get(kind)
	if not doctype or not p.get("record"):
		raise PayloadError(_("Say which task or goal to park. record_type is Task, Goal, New task or New note."))
	value = str(p["record"]).strip()
	name = value if frappe.db.exists(doctype, {"name": value, "space": item.space}) else frappe.db.get_value(doctype, {"title": value, "space": item.space})
	if not name:
		raise PayloadError(_("{0} '{1}' was not found in this space.").format(kind, value))
	doc = permissions.get_doc_checked(doctype, name, "write")
	someday.park_doc(doc, p.get("note"))
	return doctype, name


def store_reading(p, item):
	"""A Reading proposal: stored at once as a Suggested reading of the goal, citing the inbox item (or the record named in
	`source` when it is in the same space). Returns the reading."""
	from lifeos.goals import readings

	src_dt, src_name = "Life Inbox Item", item.name
	if p.get("source") and ":" in p["source"]:
		dt, name = (x.strip() for x in p["source"].split(":", 1))
		if dt in ("Life Inbox Item", "Life Chat Log", "Life Note") and frappe.db.get_value(dt, name, "space") == item.space:
			src_dt, src_name = dt, name
	on = p.get("date") or str(item.get("received_on") or item.creation or today())[:10]
	return readings.suggest(p["goal"], p["value"], min(getdate(on), getdate(today())), p["excerpt"], src_dt, src_name, by="Agent")
