"""Reading Google Calendar (set 8). Reading only lists; writing, when the person turns it on, is `gcal_write` (issue 31).

The connection is Frappe's own: Google Settings (the OAuth client, entered by the owner) and a core `Google Calendar` record per
user, authorised through core's flow. Core's own sync is left off on that record (pull and push both off), because it writes to
Google in two places (it creates a calendar when the record names none, and pushes events that are saved with sync on) and keeps
no attendees. Life OS reads instead, with the record's credentials, through `events.list` and `calendarList.list` only: the last
21 days and the next 14, hourly and when the review opens, into core `Event` records in the user's private space, with the
attendees on the event.

In tests and on the acceptance site (site config `lifeos_fake_calendar`) a fake source of fixture events stands in for Google.
"""
import json

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from lifeos.review import meetings

BACK_DAYS, AHEAD_DAYS = 21, 14
RECORD_NAME = "Life OS"


# ---- the connection ----

def configured():
	s = frappe.get_cached_doc("Google Settings")
	return bool(s.enable and s.client_id and s.get_password("client_secret", raise_exception=False))


def account(user):
	name = frappe.db.get_value("Google Calendar", {"user": user, "calendar_name": RECORD_NAME}) or frappe.db.get_value("Google Calendar", {"user": user})
	return frappe.get_doc("Google Calendar", name) if name else None


def is_connected(user) -> bool:
	"""The person's own Google Calendar is connected: Frappe's record is enabled and holds a refresh token."""
	acc = account(user)
	return bool(acc and acc.enable and acc.get_password("refresh_token", raise_exception=False))


def last_sync(user):
	"""(when the calendar was last read, why the last read failed or None): from Frappe's record, or from the fake source's marker on a site that uses it."""
	acc = account(user)
	if acc and (acc.get("life_last_synced") or acc.get("life_sync_error")):
		return acc.get("life_last_synced"), acc.get("life_sync_error")
	return _fake_synced(user), None


def state(user):
	"""What Settings > Me > Calendar shows."""
	fake = bool(frappe.conf.get("lifeos_fake_calendar"))
	acc = account(user)
	token = bool(acc and acc.get_password("refresh_token", raise_exception=False))
	return {"configured": configured() or fake, "connected": fake or bool(acc and acc.enable and token), "fake": fake,
		"read": read_ids(acc) if acc else ["primary"], "last_synced": acc.get("life_last_synced") if acc else _fake_synced(user),
		"error": acc.get("life_sync_error") if acc else None, "write": frappe.defaults.get_user_default("life_write_calendar", user), "domains": meetings.own_domains()}


def connect(user):
	"""Create (or reuse) the user's Google Calendar record, read-only, and start Frappe's OAuth flow. Returns {"url"}."""
	from frappe.integrations.doctype.google_calendar.google_calendar import authorize_access

	acc = account(user) or frappe.get_doc({"doctype": "Google Calendar", "calendar_name": RECORD_NAME, "user": user})
	acc.enable, acc.pull_from_google_calendar, acc.push_to_google_calendar = 1, 0, 0
	if not acc.get("life_read_calendars"):
		acc.life_read_calendars = json.dumps(["primary"])
	acc.save(ignore_permissions=True) if not acc.is_new() else acc.insert(ignore_permissions=True)  # system: the sync job keeps the person's own calendar account up to date
	return authorize_access(acc.name, reauthorize=True)


def disconnect(user):
	"""Stop reading: the record is switched off and its tokens cleared. Events already read stay."""
	acc = account(user)
	frappe.defaults.clear_default("life_write_calendar", parent=user)
	if acc:
		acc.enable = 0
		acc.refresh_token = acc.authorization_code = acc.next_sync_token = None
		acc.save(ignore_permissions=True)  # system: the sync job keeps the person's own calendar account up to date
	return state(user)


def set_read(user, ids):
	acc = account(user)
	if not acc:
		frappe.throw(frappe._("Connect Google Calendar first."), title=frappe._("Google Calendar not connected"))
	ids = [i for i in ids if isinstance(i, str) and i.strip()][:20] or ["primary"]
	acc.life_read_calendars = json.dumps(ids)
	acc.save(ignore_permissions=True)  # system: the sync job keeps the person's own calendar account up to date
	return state(user)


def read_ids(acc):
	try:
		ids = json.loads(acc.get("life_read_calendars") or "[]")
	except ValueError:
		ids = []
	return [i for i in ids if isinstance(i, str)] or ["primary"]


# ---- sources: Google (read-only) or the fixture ----

class GoogleSource:
	"""Google Calendar through a built API client. Only list calls are made."""

	def __init__(self, service):
		self.service = service

	def calendars(self):
		out, token = [], None
		while True:
			res = self.service.calendarList().list(pageToken=token).execute()
			out += [{"id": c.get("id"), "summary": c.get("summary"), "primary": bool(c.get("primary"))} for c in res.get("items", [])]
			token = res.get("nextPageToken")
			if not token:
				return out

	def events(self, calendar_id, start, end):
		out, token = [], None
		while True:
			res = self.service.events().list(calendarId=calendar_id, timeMin=start.isoformat() + "Z", timeMax=end.isoformat() + "Z",
				singleEvents=True, showDeleted=True, maxResults=2500, pageToken=token).execute()
			out += res.get("items", [])
			token = res.get("nextPageToken")
			if not token:
				return out

	@classmethod
	def for_account(cls, acc):
		"""The API client from the record's credentials, built as core builds it but without core's calendar check (which
		creates a calendar on Google when the record names none)."""
		import google.oauth2.credentials
		from frappe.integrations.google_oauth import GoogleOAuth
		from frappe.integrations.doctype.google_calendar.google_calendar import SCOPES
		from googleapiclient.discovery import build

		gs = frappe.get_cached_doc("Google Settings")
		creds = google.oauth2.credentials.Credentials(token=acc.get_access_token(), refresh_token=acc.get_password("refresh_token", raise_exception=False),
			token_uri=GoogleOAuth.OAUTH_URL, client_id=gs.client_id, client_secret=gs.get_password("client_secret", raise_exception=False), scopes=[SCOPES])
		return cls(build(serviceName="calendar", version="v3", credentials=creds, static_discovery=False))


class FakeSource:
	"""Fixture events with attendees, for tests and the acceptance site."""

	def __init__(self, events=None):
		self._events = events

	def calendars(self):
		return [{"id": "primary", "summary": "Fixture calendar", "primary": True}]

	def events(self, calendar_id, start, end):
		rows = self._events if self._events is not None else fixture_events()
		return [e for e in rows if start <= get_datetime(_when(e["start"])) < end]


def fixture_events(today=None):
	"""A week of meetings shaped like the owner's, around `today`: outside attendees, an internal stand-up, a short call."""
	first = add_days(getdate(today or frappe.utils.today()), -6)  # the six days before today: the period of a first review

	def ev(key, day, hh, minutes, title, emails, recurring=False):
		start = get_datetime(f"{add_days(first, day)} {hh}:00")
		end = start + frappe.utils.datetime.timedelta(minutes=minutes)
		return {"id": f"fixture-{key}", "status": "confirmed", "summary": title, "start": {"dateTime": start.isoformat()},
			"end": {"dateTime": end.isoformat()}, "attendees": [{"email": e, "displayName": e.split("@")[0].title()} for e in emails],
			**({"recurringEventId": "fixture-standup"} if recurring else {})}

	me = "owner@lifeos.test"
	return [ev("board", 0, "10:00", 60, "Board call", [me, "rao@greenfields.example"]),
		ev("standup-1", 0, "12:00", 30, "Team stand-up", [me, "kunal@lifeos.test"], recurring=True),
		ev("itr", 1, "11:00", 45, "Vivek: ITR-U", [me, "vivek@ca-firm.example"]),
		ev("dalmia", 2, "15:00", 60, "Dalmia: blend sheet", [me, "mithun@dalmia.example", "arvind@dalmia.example"]),
		ev("standup-2", 2, "12:00", 30, "Team stand-up", [me, "kunal@lifeos.test"], recurring=True),
		ev("foxin", 3, "16:00", 45, "Foxin: dealer portal", [me, "ops@foxin.example"]),
		ev("quick", 3, "17:00", 15, "Quick call with the CA", [me, "ca@ca-firm.example"]),
		ev("golf", 5, "07:00", 120, "Golf: round", [])]


def _when(d):
	return d.get("dateTime") or d.get("date")


def source_for(acc):
	if frappe.conf.get("lifeos_fake_calendar"):
		return FakeSource()
	return GoogleSource.for_account(acc)


# ---- syncing ----

def sync_user(user, source=None, now=None, space=None):
	"""Read the window from every chosen calendar into Events in the user's private space. Returns the number read."""
	acc = account(user)
	if source is None:
		if not frappe.conf.get("lifeos_fake_calendar") and not (acc and acc.enable and acc.get_password("refresh_token", raise_exception=False)):
			return 0
		source = source_for(acc)
	space = space or private_space(user)
	if not space:
		return 0  # events from a calendar are private to whoever connected it: never read into a shared space
	now = get_datetime(now or now_datetime())
	start, end = now - frappe.utils.datetime.timedelta(days=BACK_DAYS), now + frappe.utils.datetime.timedelta(days=AHEAD_DAYS)
	n = 0
	for cal in (read_ids(acc) if acc else ["primary"]):
		for ev in source.events(cal, start.replace(tzinfo=None), end.replace(tzinfo=None)):
			upsert(user, space, cal, ev)
			n += 1
	if acc:
		frappe.db.set_value("Google Calendar", acc.name, {"life_last_synced": now_datetime(), "life_sync_error": None}, update_modified=False)
		from lifeos.api import connections

		connections.ensure(space, "google-calendar")  # Brain > Sources lists a calendar that is really connected, however it was connected
	else:
		frappe.cache.set_value(f"lifeos_fake_calendar_synced:{user}", str(now_datetime())[:19])
	return n


def _fake_synced(user):
	return frappe.cache.get_value(f"lifeos_fake_calendar_synced:{user}") if frappe.conf.get("lifeos_fake_calendar") else None


CHANGED_FIELDS = ("subject", "description", "starts_on", "ends_on", "all_day", "google_calendar_id", "life_attendees", "life_recurring", "status", "life_matters")


def upsert(user, space, calendar_id, ev):
	"""One Google event into a core Event: never with sync to Google on, always marked as pulled."""
	key = ev.get("id")
	name = frappe.db.get_value("Event", {"google_calendar_event_id": key, "life_space": space})
	if ev.get("status") == "cancelled":
		if name:
			frappe.db.set_value("Event", name, "status", "Cancelled")
		return None
	all_day = "date" in (ev.get("start") or {}) and "dateTime" not in (ev.get("start") or {})
	starts = get_datetime(_when(ev["start"])).replace(tzinfo=None)
	ends = get_datetime(_when(ev.get("end") or ev["start"])).replace(tzinfo=None)
	attendees = [{"email": (a.get("email") or "").lower(), "name": a.get("displayName") or ""} for a in ev.get("attendees") or [] if a.get("email")]
	doc = frappe.get_doc("Event", name) if name else frappe.new_doc("Event")
	before = {k: doc.get(k) for k in CHANGED_FIELDS} if name else None
	doc.update({"subject": (ev.get("summary") or "No title")[:140], "description": ev.get("description"), "starts_on": starts,
		"ends_on": add_days(ends, -1) if all_day and ends > starts else ends, "all_day": 1 if all_day else 0, "life_space": space,
		"google_calendar_event_id": key, "google_calendar_id": calendar_id, "pulled_from_google_calendar": 1, "sync_with_google_calendar": 0,
		"life_attendees": json.dumps(attendees), "life_recurring": 1 if ev.get("recurringEventId") else 0, "status": "Open"})
	meetings.apply_rule(doc)
	if before is not None and all(str(before[k] or "") == str(doc.get(k) or "") for k in CHANGED_FIELDS):
		return doc.name  # unchanged: leave `modified` alone, so "synced in the last 7 days" counts what was created or changed (issue 101)
	doc.flags.ignore_permissions = True  # system: the sync job keeps the person's own calendar account up to date
	doc.save() if name else doc.insert()
	if not name:
		doc.db_set("owner", user, update_modified=False)
	return doc.name


def sync_all():
	"""Hourly: every user who connected Google Calendar through Life OS (or every owner on a site with the fake source)."""
	users = frappe.get_all("Google Calendar", filters={"enable": 1, "calendar_name": RECORD_NAME}, pluck="user")
	if frappe.conf.get("lifeos_fake_calendar"):
		users = list(set(users) | set(frappe.get_all("Life Space", pluck="owner_user")))
	for user in [u for u in users if u]:
		frappe.db.savepoint("lifeos_gcal")
		try:
			sync_user(user)
		except Exception as e:
			frappe.db.rollback(save_point="lifeos_gcal")
			acc = account(user)
			if acc:
				frappe.db.set_value("Google Calendar", acc.name, "life_sync_error", str(e)[:500], update_modified=False)
			frappe.log_error(title="Life OS Google Calendar read")


def private_space(user):
	"""The user's own space: one he owns where no other person is a member (agents and Administrator may be); "Private" first."""
	from lifeos import permissions

	own = []
	for name in frappe.get_all("Life Space", filters={"owner_user": user}, pluck="name", order_by="creation asc"):
		people = {m for m in frappe.get_all("Life Space Member", filters={"parent": name, "parenttype": "Life Space"}, pluck="user")
			if m != "Administrator" and not permissions.is_agent(m)}
		if people <= {user}:
			own.append(name)
	return "Private" if "Private" in own else (own[0] if own else None)
