"""The calendar screen: core Event records, important dates, task due dates and vault expiry dates, merged."""
import calendar as pycal
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, today

from lifeos import calendar_data as data
from lifeos import permissions
from lifeos.api.utils import flag, in_area, lens_area

MAX_RANGE_DAYS = 100


def google_status():
	"""Whether the session user has connected Google Calendar through Frappe's built-in integration (set 8: read only; the
	screens link to Settings > Me > Calendar to connect)."""
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
		"setup_url": "/settings?tab=calendar"}


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None, from_date: str | None = None, to_date: str | None = None, area: str | None = None):
	"""Everything on the calendar between two dates (at most 100 days): events, important dates, tasks due and documents expiring.
	`area` is the lens: tasks and documents keep to the area; events and important dates have no area and always show."""
	space = permissions.resolve_space(space)
	area = lens_area(area)
	start = getdate(from_date or today())
	end = getdate(to_date) if to_date else add_days(start, 31)
	if end < start:
		start, end = end, start
	if (end - start).days > MAX_RANGE_DAYS:
		end = add_days(start, MAX_RANGE_DAYS)
	items = (data.events_between(space, start, end) + data.important_dates_between(space, start, end)
		+ lens_items(space, area, data.task_dues_between(space, start, end) + data.task_slots_between(space, start, end)
		+ data.vault_expiries_between(space, start, end)))
	items.sort(key=lambda i: (i["date"], 0 if i.get("all_day") else 1, i.get("start") or "", i["title"]))
	return {"space": space, "from_date": str(start), "to_date": str(end), "today": today(), "items": items,
		"cycles": data.cycles_between(space, start, end), "google": google_status()}


def lens_items(space, area, items):
	"""Calendar items of tasks and documents, narrowed to the lens."""
	if not area:
		return items
	keep = {src: in_area(space, area, dt, [i["name"] for i in items if i.get("source") == src])
		for src, dt in (("task", "Life Task"), ("vault", "Life Vault Document"))}
	return [i for i in items if i.get("name") in keep.get(i.get("source"), ())]


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


@frappe.whitelist(methods=["GET"])
def year(space: str | None = None, year: int | None = None):
	"""The year view: important dates, all-day and multi-day events, vault expiry dates and the start and end of each 12 Week Year."""
	space = permissions.resolve_space(space)
	y = int(year or getdate(today()).year)
	days, cycles = year_entries(space, y)
	return {"space": space, "year": y, "today": today(), "days": days, "cycles": cycles,
		"active_ranges": [{"start": c["start"], "end": c["end"]} for c in cycles if c["status"] == "Active"]}


@frappe.whitelist(methods=["GET"])
def year_plan(space: str | None = None, year: int | None = None, area: str | None = None):
	"""Today > Year: the 12 Week Years with their scores, a lane for each area that is on with its goals as bars, key dates, one tick
	for each weekly review, and the cards underneath. `area` is the lens."""
	from lifeos import year_plan as plan

	space = permissions.resolve_space(space)
	return plan.year_plan(space, int(year or getdate(today()).year), lens_area(area))


@frappe.whitelist(methods=["GET"])
def week_plan(space: str | None = None, week_start: str | None = None, area: str | None = None):
	"""Today > Week: the week's score in the 12 Week Year, the top three and the goal work planned, by goal."""
	from lifeos import year_plan as plan

	space = permissions.resolve_space(space)
	return plan.week_plan(space, week_start or today(), lens_area(area))


@frappe.whitelist(methods=["POST"])
def add_event(space: str | None = None, subject: str | None = None, starts_on: str | None = None, ends_on: str | None = None, all_day: bool | int = 0, description: str | None = None):
	"""Create a core Event in a space. Set 8 reads Google Calendar and never writes to it, so the event stays in Life OS
	(writing to Google comes with set 9)."""
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
	# the space check above is the rule; core Event asks for the Desk User role, which Life User and Life Agent do not have
	doc.insert(ignore_permissions=True)  # system: the event is made for the person after the space check above
	return {"name": doc.name, "synced_to_google": False}


@frappe.whitelist(methods=["POST"])
def delete_event(event: str):
	"""Delete an event of a space the user can write to."""
	# Core Event lets only its creator delete it. In a space, any person with Write access may, so an
	# event filed by an agent can be removed by the owner. The checks below replace the core one.
	doc = permissions.get_doc_checked("Event", event, "read")
	if not doc.get("life_space"):
		frappe.throw(_("This event does not belong to a Life OS space."), frappe.PermissionError)
	permissions.require_space(doc.life_space, write=True)
	if permissions.is_agent():
		frappe.throw(_("Agents cannot delete records."), frappe.PermissionError)
	# an accepted proposal still names the event it made; that is a record of what happened, not a reason to keep the event
	frappe.delete_doc("Event", doc.name, force=True, ignore_permissions=True)  # system: the event is made for the person after the space check above
	return {"deleted": event}


@frappe.whitelist(methods=["POST"])
def add_important_date(space: str | None = None, title: str | None = None, day: int | None = None, month: int | None = None, year: int | str | None = None, kind: str | None = "Birthday"):
	"""Add a birthday, anniversary or other date that repeats every year: an all-day Event that repeats yearly."""
	space = permissions.resolve_space(space, write=True)
	doc = data.add_yearly_date(space, title, day, month, year, kind or "Birthday")
	return {"name": doc.name}


@frappe.whitelist(methods=["GET"])
def entry(kind: str, name: str):
	"""One calendar entry for the record pane: kind is "event" or "date" (an important date)."""
	if kind == "event":
		doc = permissions.get_doc_checked("Event", name, "read")
		return {"kind": "event", "name": doc.name, "title": doc.subject, "space": doc.get("life_space"), "all_day": bool(doc.all_day),
			"starts_on": str(doc.starts_on)[:16] if doc.starts_on else None, "ends_on": str(doc.ends_on)[:16] if doc.ends_on else None,
			"description": frappe.utils.strip_html(doc.description or ""), "repeats": bool(doc.repeat_this_event),
			"synced_to_google": bool(doc.get("pulled_from_google_calendar"))}
	if kind == "date":
		doc = permissions.get_doc_checked("Event", name, "read")
		first = getdate(doc.starts_on)
		note = frappe.utils.strip_html(doc.description or "").strip()
		return {"kind": "date", "name": doc.name, "title": doc.subject, "space": doc.get("life_space"), "day": first.day, "month": first.month,
			"year": None, "date_kind": note if note in data.DATE_KINDS else "Other"}
	frappe.throw(_("kind must be event or date."))
