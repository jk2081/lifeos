"""Writing to Google Calendar (issue 31). Off until the person chooses which of their calendars Life OS writes to.

Two things are written: an accepted Event proposal and a goal block made in the weekly review. Each is created in the chosen
calendar through the same connection that reads (`gcal`), private, with no attendees unless the person put some on the
proposal, and a link back to Life OS in the description. The Google ID is kept on the record (`Event.google_calendar_event_id`,
`Life Task.google_event_id`); moving or deleting the record in Life OS updates or deletes it in Google. Changes made in Google
come back with the hourly read, which never writes. A failure of Google never fails the save: it is logged and the record stays.

The choice is a per-user default, `life_write_calendar` (the calendar's ID); empty is off. Tests replace `service_for` with a
recording stand-in; on a site with `lifeos_fake_calendar` set, a stand-in answers instead of Google.
"""
import json
import re
from datetime import timedelta

import frappe
from frappe.utils import add_days, cint, get_datetime, get_system_timezone, get_url

from lifeos.pane_refs import ref_of
from lifeos.review import gcal

KEY = "life_write_calendar"
EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


# ---- the setting ----

def chosen(user):
	return frappe.defaults.get_user_default(KEY, user) or None


def choose(user, calendar_id):
	"""Save the calendar to write to; empty or None turns writing off. The calendar must be one of the account's."""
	calendar_id = (calendar_id or "").strip() or None
	if calendar_id and calendar_id not in [c["id"] for c in gcal.source_for(gcal.account(user)).calendars()]:
		frappe.throw(frappe._("That is not one of your calendars."), title=frappe._("Calendar is not yours"))
	if calendar_id:
		frappe.defaults.set_user_default(KEY, calendar_id, user)
	else:
		frappe.defaults.clear_default(KEY, parent=user)
	return gcal.state(user)


# ---- the client ----

class FakeService:
	"""Stands in for Google on a site with the fixture calendar: answers like Google, keeps nothing."""

	def events(self):
		return self

	def insert(self, **kw):
		return _Done({"id": "fake-" + frappe.generate_hash(length=12)})

	def update(self, **kw):
		return _Done({"id": kw.get("eventId")})

	def delete(self, **kw):
		return _Done({})


class _Done:
	def __init__(self, out):
		self.out = out

	def execute(self):
		return self.out


def service_for(user):
	if frappe.conf.get("lifeos_fake_calendar"):
		return FakeService()
	return gcal.GoogleSource.for_account(gcal.account(user)).service


# ---- building and sending ----

def link(doctype, name):
	ref = ref_of(doctype, name)
	return f"{get_url()}/life/calendar?open={ref}" if ref else get_url() + "/life"


def body(subject, starts, ends, all_day, description, ref, attendees=()):
	text = ((frappe.utils.strip_html(description or "")).strip() + "\n\n" if description else "") + f"Life OS: {ref}"
	starts = get_datetime(starts)
	ends = get_datetime(ends) if ends else starts
	if all_day:
		first, last = starts.date(), ends.date()
		when = {"start": {"date": str(first)}, "end": {"date": str(add_days(last, 1))}}
	else:
		if ends <= starts:
			ends = starts + timedelta(minutes=30)
		tz = get_system_timezone()
		when = {"start": {"dateTime": starts.isoformat(), "timeZone": tz}, "end": {"dateTime": ends.isoformat(), "timeZone": tz}}
	out = {"summary": subject, "description": text, "visibility": "private", "transparency": "opaque", **when,
		"extendedProperties": {"private": {"lifeos": "1"}}}
	if attendees:
		out["attendees"] = [{"email": e} for e in attendees]
	return out


def emails(value):
	"""Attendee emails from a list or a comma, semicolon or line separated string; anything that is not an email is left out."""
	if isinstance(value, str):
		value = re.split(r"[,;\n]", value)
	return list(dict.fromkeys(e.strip().lower() for e in value or [] if EMAIL.match((e or "").strip())))


def _who(doc):
	"""The user whose calendar and choice apply: the person at the keyboard, else the record's owner."""
	for user in (frappe.session.user, doc.owner):
		if user and user != "Administrator" and chosen(user):
			return user
	return None


def _safe(fn):
	try:
		return fn()
	except Exception:
		frappe.log_error(title="Life OS Google Calendar write")
		return None


def _create(user, payload):
	cal = chosen(user)
	send = "all" if payload.get("attendees") else "none"
	res = service_for(user).events().insert(calendarId=cal, body=payload, sendUpdates=send).execute()
	return cal, res.get("id")


# ---- Event ----

def push_event(doc, attendees=None):
	"""Create a new Life OS event in the chosen calendar. Does nothing with writing off or for an event read from Google."""
	user = _who(doc)
	if not user or doc.get("pulled_from_google_calendar") or doc.get("google_calendar_event_id"):
		return None
	guests = emails(attendees)

	def go():
		cal, gid = _create(user, body(doc.subject, doc.starts_on, doc.ends_on, doc.all_day, doc.description, link("Event", doc.name), guests))
		doc.db_set({"google_calendar_event_id": gid, "google_calendar_id": cal, "life_attendees": json.dumps([{"email": e, "name": ""} for e in guests]) if guests else None},
			update_modified=False)
		return gid
	return _safe(go)


def _ours(doc):
	return bool(doc.get("google_calendar_event_id") and doc.get("google_calendar_id") and not doc.get("pulled_from_google_calendar"))


def event_updated(doc, method=None):
	"""Core Event on_update: a moved or renamed event is updated in Google."""
	if not _ours(doc) or doc.flags.in_insert:
		return
	user = _who(doc)
	if not user:
		return
	guests = [a["email"] for a in json.loads(doc.get("life_attendees") or "[]") if a.get("email")]
	_safe(lambda: service_for(user).events().update(calendarId=doc.google_calendar_id, eventId=doc.google_calendar_event_id,
		body=body(doc.subject, doc.starts_on, doc.ends_on, doc.all_day, doc.description, link("Event", doc.name), guests), sendUpdates="none").execute())


def event_trashed(doc, method=None):
	if _ours(doc) and (user := _who(doc)):
		_safe(lambda: service_for(user).events().delete(calendarId=doc.google_calendar_id, eventId=doc.google_calendar_event_id, sendUpdates="none").execute())


# ---- goal blocks (a scheduled Life Task) ----

def push_task(doc):
	"""A goal block from the weekly review: created in Google when scheduled, updated when moved, deleted when unscheduled."""
	user = _who(doc)
	if not user:
		return None
	gid = doc.get("google_event_id")
	if not doc.scheduled_at:
		return task_unscheduled(doc, user) if gid else None
	end = get_datetime(doc.scheduled_at) + timedelta(minutes=cint(doc.duration_min) or 30)
	payload = body(doc.title, doc.scheduled_at, end, False, None, link("Life Task", doc.name))

	def go():
		if gid:
			service_for(user).events().update(calendarId=doc.get("google_calendar_id") or chosen(user), eventId=gid, body=payload, sendUpdates="none").execute()
			return gid
		cal, new = _create(user, payload)
		doc.db_set({"google_event_id": new, "google_calendar_id": cal}, update_modified=False)
		return new
	return _safe(go)


def task_unscheduled(doc, user=None):
	user = user or _who(doc)
	if user and doc.get("google_event_id"):
		_safe(lambda: service_for(user).events().delete(calendarId=doc.get("google_calendar_id") or chosen(user), eventId=doc.google_event_id, sendUpdates="none").execute())
		doc.db_set({"google_event_id": None, "google_calendar_id": None}, update_modified=False)


def task_updated(doc, method=None):
	"""Life Task on_update: a block already in Google follows the task (moved, renamed, unscheduled, finished)."""
	if not doc.get("google_event_id") or doc.flags.in_insert:
		return
	if doc.status in ("Done", "Dropped", "Someday") or not doc.scheduled_at:
		task_unscheduled(doc)
	else:
		push_task(doc)


def task_trashed(doc, method=None):
	if doc.get("google_event_id") and (user := _who(doc)):
		_safe(lambda: service_for(user).events().delete(calendarId=doc.get("google_calendar_id") or chosen(user), eventId=doc.google_event_id, sendUpdates="none").execute())
