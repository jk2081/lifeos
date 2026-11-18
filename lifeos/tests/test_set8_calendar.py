"""Set 8, step 2: reading Google Calendar. Meetings that matter (each part of the rule and the owner's override), meeting links
(time, people, both, by hand), follow-ups and Not captured as findings, a reading cleared everywhere, and that reading the
calendar never writes to Google."""
import json
from datetime import timedelta

import frappe
from frappe.utils import add_days, get_datetime, now_datetime, today

from lifeos.api import calendar as calendar_api
from lifeos.api import goals as goal_api
from lifeos.review import findings, followups, gcal, meetings
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase
from lifeos.tests.test_ux5_ask import set_key

ME = "owner@lifeos.test"


def gevent(key, start, minutes, title, emails, recurring=False):
	start = get_datetime(start)
	return {"id": f"s8-{key}", "status": "confirmed", "summary": title, "start": {"dateTime": start.isoformat()},
		"end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat()},
		"attendees": [{"email": e, "displayName": e.split("@")[0].title()} for e in emails], **({"recurringEventId": "s8-rec"} if recurring else {})}


class Recorder:
	"""Stands in for googleapiclient's service: records every call, answers lists only."""

	def __init__(self, events):
		self.calls, self._events = [], events

	def __getattr__(self, name):
		return lambda **kw: _Chain(self, name)


class _Chain:
	def __init__(self, rec, resource):
		self.rec, self.resource, self.method = rec, resource, None

	def __getattr__(self, name):
		def call(**kw):
			self.rec.calls.append(f"{self.resource}.{name}")
			self.method = name
			return self
		return call

	def execute(self):
		return {"items": self.rec._events if self.resource == "events" else [{"id": "primary", "summary": "Me", "primary": True}]}


class CalCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		set_key("")
		frappe.set_user(OWNER)
		frappe.db.sql("delete from `tabEvent` where life_space=%s", PRIVATE)
		frappe.db.delete("Life Meeting Link", {"space": PRIVATE})
		frappe.db.delete("Life Insight", {"space": PRIVATE})
		frappe.db.set_single_value("Life Settings", "own_domains", "lifeos.test")
		self.day = add_days(today(), -2)

	def tearDown(self):
		frappe.db.set_single_value("Life Settings", "own_domains", "")
		super().tearDown()

	def read(self, *events):
		for e in events:
			gcal.upsert(OWNER, PRIVATE, "primary", e)
		return {e["summary"]: frappe.db.get_value("Event", {"google_calendar_event_id": e["id"]}, ["name", "life_matters", "life_matters_set_by"], as_dict=True)
			for e in events}

	def capture(self, title, at, kind="Voice Note", text=""):
		doc = self.make("Life Inbox Item", title=title, source_type=kind, raw_text=text, status="Done")
		frappe.db.set_value("Life Inbox Item", doc.name, "received_on", at, update_modified=False)
		return doc.name


class TestMatters(CalCase):
	def test_each_part_of_the_rule(self):
		got = self.read(
			gevent("ext", f"{self.day} 10:00", 60, "Dalmia", [ME, "mithun@dalmia.example"]),
			gevent("short", f"{self.day} 12:00", 15, "Quick", [ME, "ruchi@ca.example"]),
			gevent("int", f"{self.day} 13:00", 60, "Internal", [ME, "kunal@lifeos.test"]),
			gevent("recint", f"{self.day} 14:00", 30, "Stand-up", [ME, "kunal@lifeos.test"], recurring=True),
			gevent("recext", f"{self.day} 15:00", 30, "Weekly with client", [ME, "a@client.example"], recurring=True),
			gevent("none", f"{self.day} 16:00", 120, "Golf", []))
		self.assertEqual({k: v.life_matters for k, v in got.items()},
			{"Dalmia": 1, "Quick": 0, "Internal": 0, "Stand-up": 0, "Weekly with client": 1, "Golf": 0})
		self.assertTrue(all(v.life_matters_set_by == "Rule" for v in got.values()))

	def test_owner_override_survives_a_new_read(self):
		e = gevent("golf", f"{self.day} 07:00", 120, "Golf", [])
		name = self.read(e)["Golf"].name
		meetings.mark(name, True)
		self.read(e)  # read again from Google
		self.assertEqual(frappe.db.get_value("Event", name, ["life_matters", "life_matters_set_by"]), (1, "Owner"))
		meetings.mark(name, None)
		self.assertEqual(frappe.db.get_value("Event", name, ["life_matters", "life_matters_set_by"]), (0, "Rule"))


class TestLinks(CalCase):
	def test_time_people_both_and_by_hand(self):
		m = self.read(gevent("d", f"{self.day} 15:00", 60, "Dalmia: blend sheet", [ME, "mithun@dalmia.example"]))["Dalmia: blend sheet"].name
		end = get_datetime(f"{self.day} 16:00")
		voice = self.capture("2 min, recorded 16:20", end + timedelta(minutes=20))
		late = self.capture("Voice 17:30", end + timedelta(minutes=90))  # time alone, but too late
		note = self.make("Life Note", title="Dalmia blend sheet design", content_md="Mithun wants the Jan lots.")
		frappe.db.set_value("Life Note", note.name, "creation", end + timedelta(minutes=40), update_modified=False)
		email = self.capture("Revised mix for the Jan lots", end + timedelta(hours=20), kind="Email", text="From: mithun@dalmia.example")
		other = self.capture("Unrelated email", end + timedelta(hours=20), kind="Email", text="From: someone@else.example")
		meetings.link_period(PRIVATE, self.day, today())
		how = {r.record_name: r.how for r in frappe.get_all("Life Meeting Link", filters={"event": m}, fields=["record_name", "how"])}
		self.assertEqual(how.get(voice), "Time")
		self.assertEqual(how.get(note.name), "Both")
		self.assertEqual(how.get(email), "People")
		self.assertNotIn(late, how)
		self.assertNotIn(other, how)
		# by hand: link the late one, unlink the note; the rule does not link the note again
		meetings.link(m, "Life Inbox Item", late)
		link = frappe.db.get_value("Life Meeting Link", {"event": m, "record_name": note.name})
		meetings.unlink(link)
		meetings.link_period(PRIVATE, self.day, today())
		self.assertEqual(frappe.db.get_value("Life Meeting Link", {"event": m, "record_name": late}, "how"), "Owner")
		self.assertEqual({r.record_name for r in meetings.linked(m)}, {voice, email, late})


class TestFindings(CalCase):
	def test_followups_and_one_finding_cleared_everywhere(self):
		set_key("fake-site-model")
		frappe.set_user(OWNER)
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 1)
		m = self.read(gevent("d2", f"{self.day} 15:00", 60, "Dalmia", [ME, "mithun@dalmia.example"]))["Dalmia"].name
		self.capture("Voice after Dalmia", get_datetime(f"{self.day} 16:10"), text="I will send the revised blend sheet to Mithun. Next tasting on 2 December.")
		followups.refresh(PRIVATE, OWNER, self.day, today(), ai=True)
		got = findings.for_meeting(m)
		self.assertEqual(sorted(f.kind for f in got), ["Date", "Promise"])
		promise = next(f for f in got if f.kind == "Promise")
		out = findings.act(promise.name, 0)
		self.assertEqual(frappe.db.get_value("Life Task", out["task"], "title"), "Send the revised blend sheet to Mithun")
		self.assertTrue(frappe.db.exists("Life Meeting Link", {"event": m, "record_name": out["task"], "how": "Owner"}))
		self.assertEqual([f.kind for f in findings.for_meeting(m)], ["Date"])  # gone from the meeting's drawer
		self.assertNotIn(promise.name, findings.pool(PRIVATE, self.day))  # and from the revelations
		date = findings.for_meeting(m)[0]
		out = findings.act(date.name, 0)
		self.assertEqual(str(frappe.db.get_value("Life Task", out["task"], "due_date"))[5:], "12-02")
		# read once: a second refresh asks nothing more about this meeting
		followups.refresh(PRIVATE, OWNER, self.day, today(), ai=True)
		self.assertEqual(frappe.db.count("Life Insight", {"meeting": m}), 2)
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 0)

	def test_not_captured_is_one_finding_kept_current(self):
		a = self.read(gevent("n1", f"{self.day} 10:00", 60, "Vivek: ITR-U", [ME, "vivek@ca.example"]))["Vivek: ITR-U"].name
		self.read(gevent("n2", f"{self.day} 12:00", 60, "Foxin: dealer portal", [ME, "ops@foxin.example"]))
		findings.detect_not_captured(PRIVATE, self.day, today())
		rows = frappe.get_all("Life Insight", filters={"space": PRIVATE, "kind": "Not captured"}, fields=["name", "title"])
		self.assertEqual(len(rows), 1)
		self.assertIn("2 meetings that matter left nothing: Vivek: ITR-U, Foxin: dealer portal", rows[0].title)
		meetings.link(a, "Life Inbox Item", self.capture("Vivek notes", now_datetime(), kind="Message"))
		findings.detect_not_captured(PRIVATE, self.day, today())
		self.assertIn("1 meeting that matters left nothing: Foxin", frappe.db.get_value("Life Insight", rows[0].name, "title"))

	def test_a_reading_confirmed_on_the_goal_clears_its_finding(self):
		goal = self.make("Life Goal", title="Ghillidary yield", goal_type="Open", measure_kind="Number", measure="yield", unit="kg/ha",
			start_value=1000, target_value=1800)
		r = frappe.get_doc({"doctype": "Life Goal Reading", "space": PRIVATE, "goal": goal.name, "date": today(), "value": 1460, "status": "Suggested",
			"suggested_by": "Agent", "excerpt": "yield 1460 kg/ha for October"}).insert()
		findings.detect_readings(PRIVATE)
		ins = frappe.db.get_value("Life Insight", {"reading": r.name}, ["name", "kind", "status"], as_dict=True)
		self.assertEqual((ins.kind, ins.status), ("Goal reading", "New"))
		goal_api.confirm_reading(r.name)
		self.assertEqual(frappe.db.get_value("Life Insight", ins.name, "status"), "Acted")
		self.assertEqual(frappe.db.get_value("Life Goal", goal.name, "current_value"), 1460)


class TestNeverWritesToGoogle(CalCase):
	def test_reading_makes_list_calls_only(self):
		svc = Recorder([gevent("g1", f"{self.day} 10:00", 60, "Board call", [ME, "rao@greenfields.example"])])
		src = gcal.GoogleSource(svc)
		self.assertEqual(src.calendars()[0]["id"], "primary")
		n = gcal.sync_user(OWNER, source=src, space=PRIVATE)
		self.assertEqual(n, 1)
		self.assertEqual(set(svc.calls), {"calendarList.list", "events.list"})
		ev = frappe.db.get_value("Event", {"google_calendar_event_id": "s8-g1"}, ["life_space", "sync_with_google_calendar", "pulled_from_google_calendar",
			"life_matters", "owner"], as_dict=True)
		self.assertEqual((ev.life_space, ev.sync_with_google_calendar, ev.pulled_from_google_calendar, ev.life_matters, ev.owner),
			(PRIVATE, 0, 1, 1, OWNER))
		self.assertEqual(json.loads(frappe.db.get_value("Event", {"google_calendar_event_id": "s8-g1"}, "life_attendees"))[1]["email"], "rao@greenfields.example")

	def test_events_made_in_life_os_are_not_pushed(self):
		out = calendar_api.add_event(space=PRIVATE, subject="s8 local", starts_on=f"{today()} 10:00:00")
		self.assertFalse(out["synced_to_google"])
		self.assertEqual(frappe.db.get_value("Event", out["name"], "sync_with_google_calendar"), 0)

	def test_the_fixture_source(self):
		n = gcal.sync_user(OWNER, source=gcal.FakeSource(), space=PRIVATE)
		self.assertGreaterEqual(n, 7)
		self.assertEqual(frappe.db.count("Event", {"life_space": PRIVATE, "life_matters": 1}), 4)  # Board, ITR-U, Dalmia, Foxin
