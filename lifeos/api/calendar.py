"""The calendar screen: core Event records, important dates, task due dates and vault expiry dates, merged."""
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, today

from lifeos.calendar import calendar_data as data
from lifeos.calendar import key_dates, notes
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
def get(space: str | None = None, from_date: str | None = None, to_date: str | None = None, area: str | None = None, show_hidden: bool | int = 0):
	"""Everything on the calendar between two dates (at most 100 days): events, important dates, tasks due and documents expiring.
	`area` is the lens: tasks and documents keep to the area; events and important dates have no area and always show.
	`show_hidden` brings back the events that were hidden in Life OS (issue 99)."""
	space = permissions.resolve_space(space)
	area = lens_area(area)
	start = getdate(from_date or today())
	end = getdate(to_date) if to_date else add_days(start, 31)
	if end < start:
		start, end = end, start
	if (end - start).days > MAX_RANGE_DAYS:
		end = add_days(start, MAX_RANGE_DAYS)
	items = (data.events_between(space, start, end, flag(show_hidden)) + data.important_dates_between(space, start, end)
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
def year_months(space: str | None = None, year: int | None = None):
	"""Today > Year, Calendar: the twelve months of a year, each with how many key dates it holds and the next one or two (from today in the
	current month, the first of the month otherwise)."""
	from lifeos.goals import year_plan as plan

	space = permissions.resolve_space(space)
	y = int(year or getdate(today()).year)
	keys = plan.key_dates(space, date(y, 1, 1), date(y, 12, 31))
	now = str(getdate(today()))
	months = []
	for m in range(1, 13):
		mine = sorted((k for k in keys if getdate(k["date"]).month == m), key=lambda k: str(k["date"]))
		coming = [k for k in mine if str(k["date"]) >= now] if str(now)[:7] == f"{y}-{m:02d}" else mine
		months.append({"month": m, "count": len(mine), "next": [{"title": k["title"], "date": str(k["date"]), "ref": k["ref"]} for k in coming[:2]]})
	return {"year": y, "today": now, "months": months}


@frappe.whitelist(methods=["GET"])
def year_plan(space: str | None = None, shift: int | None = 0, area: str | None = None):
	"""Today > Year: four columns of cycles around today (the last, this, the next and the one after; four quarters when no 12 Week Year is
	running), each with its score, a row for each area that is on with its goals as bars, key dates by week, and the weekly reviews since
	setup. `shift` moves the columns by whole cycles; `area` is the lens."""
	from lifeos.goals import year_plan as plan

	space = permissions.resolve_space(space)
	return plan.year_plan(space, int(shift or 0), lens_area(area))


@frappe.whitelist(methods=["GET"])
def week_plan(space: str | None = None, week_start: str | None = None, area: str | None = None):
	"""Today > Week: the week's score in the 12 Week Year, the top three and the goal work planned, by goal."""
	from lifeos.goals import year_plan as plan

	space = permissions.resolve_space(space)
	return plan.week_plan(space, week_start or today(), lens_area(area))


@frappe.whitelist(methods=["POST"])
def add_event(space: str | None = None, subject: str | None = None, starts_on: str | None = None, ends_on: str | None = None, all_day: bool | int = 0, description: str | None = None):
	"""Create a core Event in a space. Set 8 reads Google Calendar and never writes to it, so the event stays in Life OS
	(writing to Google comes with set 9)."""
	space = permissions.resolve_space(space, write=True)
	if not (subject or "").strip() or not starts_on:
		frappe.throw(_("An event needs a title and a start."), title=_("Event needs title and start"))
	starts = get_datetime(starts_on)
	ends = get_datetime(ends_on) if ends_on else None
	if flag(all_day):
		starts = starts.replace(hour=0, minute=0, second=0)
		ends = (ends or starts).replace(hour=23, minute=59, second=59)
	if ends and ends < starts:
		frappe.throw(_("The end is before the start."), title=_("Event ends before start"))
	doc = frappe.get_doc({"doctype": "Event", "subject": subject.strip(), "starts_on": starts, "ends_on": ends, "all_day": 1 if flag(all_day) else 0,
		"description": description, "event_type": "Public", "life_space": space})
	# the space check above is the rule; core Event asks for the Desk User role, which Life User and Life Agent do not have
	doc.insert(ignore_permissions=True)  # system: the event is made for the person after the space check above
	return {"name": doc.name, "synced_to_google": False}


def _event_to_change(event):
	"""An event of a space the user can write to."""
	doc = permissions.get_doc_checked("Event", event, "read")
	if not doc.get("life_space"):
		frappe.throw(_("This event does not belong to a Life OS space."), frappe.PermissionError, title=_("Event is not in a space"))
	permissions.require_space(doc.life_space, write=True)
	return doc


@frappe.whitelist(methods=["POST"])
def delete_event(event: str):
	"""Delete an event made in Life OS, in a space the user can write to. An event that came from Google is never deleted here:
	Frappe's sync could write the deletion to Google, or bring the event back (issue 99). Hide it instead (`hide_event`)."""
	# Core Event lets only its creator delete it. In a space, any person with Write access may, so an
	# event filed by an agent can be removed by the owner. The checks below replace the core one.
	doc = _event_to_change(event)
	if permissions.is_agent():
		frappe.throw(_("Agents cannot delete records."), frappe.PermissionError, title=_("Agents cannot delete"))
	if doc.get("pulled_from_google_calendar"):  # one Life OS wrote to Google itself (issue 31) is still Life OS's, and deleting it deletes it there
		frappe.throw(_("This event comes from Google Calendar. Hide it in Life OS instead."), title=_("Event is from Google"))
	# an accepted proposal still names the event it made; that is a record of what happened, not a reason to keep the event
	frappe.delete_doc("Event", doc.name, force=True, ignore_permissions=True)  # system: the event is made for the person after the space check above
	return {"deleted": event}


@frappe.whitelist(methods=["POST"])
def hide_event(event: str, hidden: bool | int = 1):
	"""Hide an event in Life OS (or show it again): sets `life_hidden`. The Event stays and nothing is sent to Google."""
	doc = _event_to_change(event)
	# a flag only: db_set skips the Event's save hooks, which are the ones that push to Google
	doc.db_set("life_hidden", 1 if flag(hidden) else 0, update_modified=False)
	return {"name": doc.name, "hidden": bool(flag(hidden))}


@frappe.whitelist(methods=["POST"])
def add_note(event: str, text: str, occurrence: str | None = None):
	"""Add a note to an event: a Frappe Comment on it, never written to Google. Agents may add notes."""
	return notes.add(event, text, occurrence)


@frappe.whitelist(methods=["POST"])
def update_note(note: str, text: str):
	"""Change a note. Agents may not."""
	return notes.update(note, text)


@frappe.whitelist(methods=["POST"])
def delete_note(note: str):
	"""Delete a note. Agents may not."""
	return notes.remove(note)


@frappe.whitelist(methods=["POST"])
def note_to_task(note: str):
	"""Make a task titled with the note, linked to its event."""
	return notes.make_task(note)


@frappe.whitelist(methods=["POST"])
def set_key_date(event: str, key: bool | int = 1):
	"""The star in an event's drawer: make the event a key date, or not. The owner's word is final, and it is kept as a correction of the
	`key-date` skill (issue 100)."""
	doc = _event_to_change(event.partition("@")[0])
	return {"name": doc.name, "key_date": key_dates.set_by_owner(doc, bool(flag(key)))}


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
		name, _sep, occurrence = name.partition("@")  # a repeat of a repeating event is `name@date`
		doc = permissions.get_doc_checked("Event", name, "read")
		starts = get_datetime(doc.starts_on)
		ends = data.last_moment(starts, get_datetime(doc.ends_on) if doc.ends_on else starts, doc.all_day, bool(doc.get("pulled_from_google_calendar") and not doc.get("life_attendees")))
		if occurrence and doc.repeat_this_event:  # the repeat's own day, the length of the first one
			shift = getdate(occurrence) - starts.date()
			starts, ends = starts + shift, ends + shift
		google = bool(doc.get("pulled_from_google_calendar"))
		return {"kind": "event", "name": doc.name, "title": doc.subject, "space": doc.get("life_space"), "all_day": bool(doc.all_day),
			"starts_on": str(starts)[:16], "ends_on": str(ends)[:16], "occurrence": str(starts.date()) if doc.repeat_this_event else None,
			"description": frappe.utils.strip_html(doc.description or ""), "repeats": bool(doc.repeat_this_event),
			"from_google": google, "hidden": bool(doc.get("life_hidden")), "key_date": bool(doc.get("life_key_date")),
			"notes": notes.listing(doc.name, str(starts.date()) if doc.repeat_this_event else None)}
	if kind == "date":
		doc = permissions.get_doc_checked("Event", name, "read")
		first = getdate(doc.starts_on)
		note = frappe.utils.strip_html(doc.description or "").strip()
		return {"kind": "date", "name": doc.name, "title": doc.subject, "space": doc.get("life_space"), "day": first.day, "month": first.month,
			"year": None, "date_kind": note if note in data.DATE_KINDS else "Other"}
	frappe.throw(_("kind must be event or date."), title=_("Kind is not valid"))
