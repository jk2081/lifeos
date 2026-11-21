"""Keeping the review's findings current (set 8): link records to meetings, read the meetings that matter for follow-ups
(Promise, Date) with the assistant, and store the rule findings (Goal reading, Not captured).

Runs nightly with the insights job, and when the review is opened (for the review's period). The model sees only what the
owner may read, never a sensitive record unless the space allows Ask to read sensitive items, and each meeting once.
"""
import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

from lifeos.review import findings, meetings

MAX_MEETINGS = 12
MAX_TEXT = 3000
NIGHT_DAYS = 14


def nightly(space, user, ai=True):
	start = add_days(getdate(today()), -NIGHT_DAYS)
	refresh(space, user, start, today(), ai=ai)


def refresh(space, user, start, end, ai=True):
	"""Everything the Library tab's findings need for a period."""
	meetings.link_period(space, start, end)
	findings.detect_readings(space)
	if ai:
		read_meetings(space, user, start, end)
	findings.detect_not_captured(space, start, end)


def read_meetings(space, user, start, end):
	"""Ask the model for the follow-ups of the period's meetings that matter that have links and were not read yet."""
	from lifeos.skills import call

	if not frappe.db.get_value("Life Space", space, "ask_enabled"):
		return 0
	readable = bool(frappe.db.get_value("Life Space", space, "ask_can_read_vault"))
	todo = [m for m in meetings.in_period(space, start, end, only_matter=True) if not m.life_followups_on][:MAX_MEETINGS]
	payload, refs = [], {}
	for i, m in enumerate(todo):
		recs = []
		for link in meetings.linked(m.name):
			doc = frappe.get_doc(link.record_doctype, link.record_name)
			if (doc.get("is_sensitive") and not readable) or not frappe.has_permission(link.record_doctype, "read", doc=doc, user=user):
				continue
			rid = f"R{len(refs) + 1}"
			refs[rid] = (link.record_doctype, link.record_name)
			recs.append({"record": rid, "kind": meetings.label_of(link.record_doctype, link.record_name), "title": doc.get("title"), "text": _text(doc)})
		if recs:
			payload.append({"meeting": f"M{i + 1}", "title": m.subject, "when": str(m.starts_on)[:16],
				"attendees": [a.get("name") or a["email"] for a in meetings.attendees(m)], "records": recs})
	if not payload:
		_mark(todo)
		return 0
	got = call.ask("notice", {"request": "follow_ups", "meetings": payload}, space=space, user=user)
	if not got:
		return 0
	by_id = {f"M{i + 1}": m for i, m in enumerate(todo)}
	n = 0
	for f in got.get("follow_ups") or []:
		m, rec = by_id.get(f.get("meeting")), refs.get(f.get("record"))
		if not m or not rec or f.get("kind") not in ("Promise", "Date") or not (f.get("title") or "").strip():
			continue
		_store(space, m, rec, f, got.label)
		n += 1
	_mark(todo)
	return n


def _text(doc):
	parts = [doc.get(k) for k in ("raw_text", "transcript_md", "summary_md", "content_md") if doc.get(k)]
	return "\n".join(parts)[:MAX_TEXT]


def _store(space, m, rec, f, by):
	label = meetings.label_of(*rec)
	when = get_datetime(m.starts_on)
	line = f"{m.subject} meeting, {when.strftime('%a %-d')} · from the {label.lower()} · suggested by {by}"
	due = _date(f.get("date"))
	if f["kind"] == "Promise":
		actions = [{"kind": "make_task", "label": "Make task", "title": (f.get("task_title") or f["title"])[:140]}, {"kind": "dismiss", "label": "Not needed"}]
	else:
		actions = [{"kind": "make_task", "label": "Add as a dated task", "title": (f.get("task_title") or f["title"])[:140], "due_date": due},
			{"kind": "dismiss", "label": "Not needed"}]
	findings.add(space, f["kind"], f["title"].strip(), [{"ref_doctype": rec[0], "ref_name": rec[1], "label": label}], actions, meeting=m.name,
		source="AI", source_line=line, body=(f.get("excerpt") or "")[:500])


def _date(text):
	try:
		return str(getdate(text)) if text else None
	except Exception:
		return None


def _mark(rows):
	for m in rows:
		frappe.db.set_value("Event", m.name, "life_followups_on", now_datetime(), update_modified=False)
