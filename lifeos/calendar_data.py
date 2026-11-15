"""Calendar sources for one space: events, important dates, task due dates, vault expiry dates, cycle bounds."""
import calendar
from datetime import date, timedelta

import frappe
from frappe.utils import add_days, get_datetime, getdate

from lifeos import permissions


def events_between(space, start, end):
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
		})
	return out


def date_in_year(day, month, year):
	"""An important date in a given year. 29 February falls on 28 February outside leap years."""
	if month == 2 and day == 29 and not calendar.isleap(year):
		return date(year, 2, 28)
	return date(year, month, day)


def important_dates_between(space, start, end):
	start, end = getdate(start), getdate(end)
	rows = frappe.get_all("Life Important Date", filters={"space": space}, fields=["name", "title", "day", "month", "year", "kind", "person"], limit=2000)
	out = []
	for r in rows:
		for year in range(start.year, end.year + 1):
			if r.year and year < r.year:
				continue
			d = date_in_year(r.day, r.month, year)
			if start <= d <= end:
				label = r.title
				if r.year and year > r.year:
					label = f"{r.title} ({year - r.year})"
				out.append({"source": "important", "name": r.name, "title": r.title, "label": label, "date": str(d), "kind": r.kind, "all_day": 1})
	return out


def task_dues_between(space, start, end):
	rows = frappe.get_all("Life Task", filters={"space": space, "is_archived": 0, "status": ("in", ["Open", "Doing", "Waiting"]),
		"due_date": ("between", [start, end])}, fields=["name", "title", "due_date", "priority"], limit=1000)
	return [{"source": "task", "name": r.name, "title": r.title, "date": str(r.due_date), "priority": r.priority, "all_day": 1} for r in rows]


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
