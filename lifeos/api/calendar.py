"""The calendar screen: core Event records, important dates, task due dates and vault expiry dates, merged."""
import calendar as pycal
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, today

from lifeos import calendar_data as data
from lifeos import permissions
from lifeos.api.utils import flag

MAX_RANGE_DAYS = 100


def google_status():
	"""Whether the session user has connected Google Calendar through Frappe's built-in integration."""
	try:
		enabled = frappe.db.get_single_value("Google Settings", "enable")
		name = frappe.db.get_value("Google Calendar", {"user": frappe.session.user, "enable": 1}, "name")
	except Exception:
		enabled, name = 0, None
	connected = False
	if name:
		from frappe.utils.password import get_decrypted_password
		connected = bool(get_decrypted_password("Google Calendar", name, "refresh_token", raise_exception=False))
	return {"enabled": bool(enabled), "connected": connected, "calendar": name if connected else None,
		"setup_url": "/app/google-calendar" if enabled else "/app/google-settings"}


@frappe.whitelist()
def get(space=None, from_date=None, to_date=None):
	"""Everything on the calendar between two dates (at most 100 days): events, important dates, tasks due and documents expiring."""
	space = permissions.resolve_space(space)
	start = getdate(from_date or today())
	end = getdate(to_date) if to_date else add_days(start, 31)
	if end < start:
		start, end = end, start
	if (end - start).days > MAX_RANGE_DAYS:
		end = add_days(start, MAX_RANGE_DAYS)
	items = (data.events_between(space, start, end) + data.important_dates_between(space, start, end)
		+ data.task_dues_between(space, start, end) + data.vault_expiries_between(space, start, end))
	items.sort(key=lambda i: (i["date"], 0 if i.get("all_day") else 1, i.get("start") or "", i["title"]))
	return {"space": space, "from_date": str(start), "to_date": str(end), "today": today(), "items": items,
		"cycles": data.cycles_between(space, start, end), "google": google_status()}


def year_entries(space, year):
	"""The year view: one list of entries per day. Timed meetings are left out so the year stays readable."""
	year = int(year)
	start, end = date(year, 1, 1), date(year, 12, 31)
	days = {}

	def add(day, entry):
		days.setdefault(str(day), []).append(entry)

	for d in data.important_dates_between(space, start, end):
		add(d["date"], {"type": "important", "kind": d["kind"], "title": d["title"], "label": d["label"], "name": d["name"]})
	for e in data.events_between(space, start, end):
		if not e["all_day"]:
			continue  # a timed meeting
		first, last = max(getdate(e["date"]), start), min(getdate(e["end_date"]), end)
		day = first
		while day <= last:
			add(day, {"type": "trip" if e["multi_day"] else "event", "title": e["title"], "name": e["name"]})
			day += timedelta(days=1)
	for v in data.vault_expiries_between(space, start, end):
		add(v["date"], {"type": "vault", "title": v["title"], "name": v["name"]})
	cycles = data.cycles_between(space, start, end)
	for c in cycles:
		if start <= getdate(c["start"]) <= end:
			add(c["start"], {"type": "cycle", "title": "12WY starts", "name": c["name"]})
		if start <= getdate(c["end"]) <= end:
			add(c["end"], {"type": "cycle", "title": "12WY ends", "name": c["name"]})
	order = {"important": 0, "trip": 1, "vault": 2, "event": 3, "cycle": 4}
	for entries in days.values():
		entries.sort(key=lambda e: order[e["type"]])
	return days, cycles


@frappe.whitelist()
def year(space=None, year=None):
	"""The year view: important dates, all-day and multi-day events, vault expiry dates and the start and end of each 12 Week Year."""
	space = permissions.resolve_space(space)
	y = int(year or getdate(today()).year)
	days, cycles = year_entries(space, y)
	return {"space": space, "year": y, "today": today(), "days": days, "cycles": cycles,
		"active_ranges": [{"start": c["start"], "end": c["end"]} for c in cycles if c["status"] == "Active"]}


@frappe.whitelist(methods=["POST"])
def add_event(space=None, subject=None, starts_on=None, ends_on=None, all_day=0, description=None):
	"""Create a core Event in a space. If the user has connected Google Calendar, the built-in integration pushes it there."""
	space = permissions.resolve_space(space, write=True)
	if not (subject or "").strip() or not starts_on:
		frappe.throw(_("An event needs a title and a start."))
	starts = get_datetime(starts_on)
	ends = get_datetime(ends_on) if ends_on else None
	if flag(all_day):
		starts = starts.replace(hour=0, minute=0, second=0)
		ends = (ends or starts).replace(hour=23, minute=59, second=59)
	if ends and ends < starts:
		frappe.throw(_("The end is before the start."))
	doc = frappe.get_doc({"doctype": "Event", "subject": subject.strip(), "starts_on": starts, "ends_on": ends, "all_day": 1 if flag(all_day) else 0,
		"description": description, "event_type": "Public", "life_space": space})
	google = google_status()
	if google["connected"]:
		doc.sync_with_google_calendar = 1
		doc.google_calendar = google["calendar"]
	# the space check above is the rule; core Event asks for the Desk User role, which Life User and Life Agent do not have
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "synced_to_google": bool(google["connected"])}


@frappe.whitelist(methods=["POST"])
def delete_event(event):
	"""Delete an event of a space the user can write to."""
	# Core Event lets only its creator delete it. In a space, any person with Write access may, so an
	# event filed by an agent can be removed by the owner. The checks below replace the core one.
	doc = permissions.get_doc_checked("Event", event, "read")
	if not doc.get("life_space"):
		frappe.throw(_("This event does not belong to a Life OS space."), frappe.PermissionError)
	permissions.require_space(doc.life_space, write=True)
	if permissions.is_agent():
		frappe.throw(_("Agents cannot delete records."), frappe.PermissionError)
	doc.delete(ignore_permissions=True)
	return {"deleted": event}


@frappe.whitelist(methods=["POST"])
def add_important_date(space=None, title=None, day=None, month=None, year=None, kind="Birthday", person=None):
	"""Add a birthday, anniversary or other date that repeats every year."""
	space = permissions.resolve_space(space, write=True)
	doc = frappe.get_doc({"doctype": "Life Important Date", "space": space, "title": title, "day": day, "month": month,
		"year": year or None, "kind": kind or "Birthday", "person": person}).insert()
	return {"name": doc.name}


@frappe.whitelist()
def entry(kind, name):
	"""One calendar entry for the record pane: kind is "event" or "date" (an important date)."""
	if kind == "event":
		doc = permissions.get_doc_checked("Event", name, "read")
		return {"kind": "event", "name": doc.name, "title": doc.subject, "space": doc.get("life_space"), "all_day": bool(doc.all_day),
			"starts_on": str(doc.starts_on)[:16] if doc.starts_on else None, "ends_on": str(doc.ends_on)[:16] if doc.ends_on else None,
			"description": frappe.utils.strip_html(doc.description or ""), "repeats": bool(doc.repeat_this_event),
			"synced_to_google": bool(doc.get("sync_with_google_calendar"))}
	if kind == "date":
		doc = permissions.get_doc_checked("Life Important Date", name)
		return {"kind": "date", "name": doc.name, "title": doc.title, "space": doc.space, "day": doc.day, "month": doc.month, "year": doc.year,
			"date_kind": doc.kind, "person": doc.person,
			"person_name": frappe.db.get_value("Life Person", doc.person, "full_name") if doc.person else None}
	frappe.throw(_("kind must be event or date."))
