"""Calendar sources for one space: events, important dates, task due dates, vault expiry dates, cycle bounds.

An important date (a birthday, an anniversary) is an all-day Event that repeats every year; core's own get_events expands it.
"""
import calendar
from datetime import date, timedelta

import frappe
from frappe.utils import add_days, get_datetime, getdate

from lifeos import permissions


DATE_KINDS = ("Birthday", "Anniversary", "Other")
UNKNOWN_YEAR = 2000  # a leap year, long before anything the calendar shows


def _events(space, start, end):
	"""Core Event records of a space between two dates, with repeats expanded by core's own get_events."""
	from frappe.desk.doctype.event.event import get_events

	out = []
	for e in get_events(start, end, filters={"life_space": space}):
		starts = get_datetime(e.starts_on)
		ends = get_datetime(e.ends_on) if e.ends_on else starts
		if ends < starts:
			ends = starts
		multi = ends.date() > starts.date()
		out.append({
			"source": "event", "name": e.name, "title": e.subject, "start": str(starts)[:19], "end": str(ends)[:19],
			"date": str(starts.date()), "end_date": str(ends.date()), "all_day": 1 if (e.all_day or multi) else 0,
			"multi_day": multi, "description": e.description, "repeats": bool(e.repeat_this_event),
			"yearly_date": bool(e.all_day and not multi and e.repeat_this_event and e.repeat_on == "Yearly"),
		})
	return out


def events_between(space, start, end):
	"""The Events of a space between two dates, without its important dates."""
	return [e for e in _events(space, start, end) if not e["yearly_date"]]


def important_dates_between(space, start, end):
	"""The important dates of a space between two dates: its all-day yearly Events, one entry for each year."""
	out = []
	for e in _events(space, start, end):
		if e["yearly_date"]:
			kind = frappe.utils.strip_html(e["description"] or "").strip()
			out.append({"source": "important", "name": e["name"], "title": e["title"], "label": e["title"], "date": e["date"],
				"kind": kind if kind in DATE_KINDS else "Other", "all_day": 1})
	return out


def add_yearly_date(space, title, day, month, year=None, kind=None):
	"""Add an important date as an all-day Event that repeats every year. `year` is the year it first happened; left out, the
	Event starts in 2000, so every year anyone looks at shows it. Core repeats 29 February on 28 February outside leap years."""
	day, month = int(day or 0), int(month or 0)
	if not 1 <= month <= 12 or not 1 <= day <= 31:
		frappe.throw(frappe._("Give a day and a month."))
	first = int(year) if year else UNKNOWN_YEAR
	if (month, day) == (2, 29) and not calendar.isleap(first):
		day = 28  # a first occurrence in a year with no 29 February
	try:
		starts = date(first, month, day)
	except ValueError:
		frappe.throw(frappe._("That day does not exist in that month."))
	doc = frappe.get_doc({"doctype": "Event", "subject": title, "starts_on": f"{starts} 00:00:00", "all_day": 1, "event_type": "Public",
		"repeat_this_event": 1, "repeat_on": "Yearly", "description": kind if kind in DATE_KINDS else "Other", "life_space": space})
	doc.insert()
	return doc


def task_dues_between(space, start, end):
	rows = frappe.get_all("Life Task", filters={"space": space, "is_archived": 0, "status": ("in", ["Open", "Doing", "Waiting"]),
		"due_date": ("between", [start, end])}, fields=["name", "title", "due_date", "priority", "scheduled_at"], limit=1000)
	# a task planned at a time on its due day shows once, at its time (task_slots_between)
	return [{"source": "task", "name": r.name, "title": r.title, "date": str(r.due_date), "priority": r.priority, "all_day": 1} for r in rows
		if not (r.scheduled_at and str(r.scheduled_at)[:10] == str(r.due_date))]


def task_slots_between(space, start, end):
	"""Open tasks planned at a time (set 7): on the calendar at that time, for their length."""
	rows = frappe.get_all("Life Task", filters={"space": space, "is_archived": 0, "status": ("in", ["Open", "Doing", "Waiting"]),
		"scheduled_at": ("between", [get_datetime(start), get_datetime(add_days(end, 1))])},
		fields=["name", "title", "scheduled_at", "duration_min", "priority", "status"], limit=1000)
	out = []
	for r in rows:
		s = get_datetime(r.scheduled_at)
		e = s + timedelta(minutes=r.duration_min or 60)
		out.append({"source": "task", "name": r.name, "title": r.title, "date": str(s.date()), "start": str(s)[:19], "end": str(e)[:19],
			"end_date": str(e.date()), "all_day": 0, "scheduled": 1, "priority": r.priority, "status": r.status})
	return out


def vault_expiries_between(space, start, end):
	if permissions.vault_hidden(space):
		return []
	rows = frappe.get_all("Life Vault Document", filters={"space": space, "is_archived": 0, "expiry_date": ("between", [start, end])},
		fields=["name", "title", "expiry_date"], limit=1000)
	return [{"source": "vault", "name": r.name, "title": f"{r.title} expires", "date": str(r.expiry_date), "all_day": 1} for r in rows]


def cycles_between(space, start, end):
	rows = frappe.get_all("Life Cycle", filters={"space": space, "start_date": ("<=", end), "end_date": (">=", start)},
		fields=["name", "title", "start_date", "end_date", "status"], limit=50)
	return [{"name": r.name, "title": r.title, "start": str(r.start_date), "end": str(r.end_date), "status": r.status} for r in rows]


def expiring_documents(space, on):
	"""Vault documents inside their own reminder window, soonest first. Expired ones are included."""
	if permissions.vault_hidden(space):
		return []
	on = getdate(on)
	rows = frappe.db.sql(
		"""select name, title, expiry_date, remind_days_before, doc_type from `tabLife Vault Document`
		where space=%s and is_archived=0 and expiry_date is not null
		and datediff(expiry_date, %s) <= ifnull(remind_days_before, 60) order by expiry_date asc limit 20""", (space, on), as_dict=True)
	return [{"name": r.name, "title": r.title, "expiry_date": str(r.expiry_date), "days": (getdate(r.expiry_date) - on).days, "doc_type": r.doc_type} for r in rows]
