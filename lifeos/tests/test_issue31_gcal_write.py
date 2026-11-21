"""Issue 31: accepted Event proposals and goal blocks are written to the chosen Google calendar, private and without guests;
moving or deleting them updates or deletes them there. Nothing calls Google: a recording stand-in takes its place."""
import json
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.utils import add_days, get_datetime, today

from lifeos.api import calendar as calendar_api
from lifeos.api import gcal as gcal_api
from lifeos.api import goals, review
from lifeos.review import gcal, gcal_write
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase


class Recorder:
	"""Stands in for googleapiclient's service: records every events() call and answers with an ID."""

	def __init__(self):
		self.calls = []

	def events(self):
		return self

	def _call(self, verb, kw):
		self.calls.append((verb, kw))
		rec = self

		class Done:
			def execute(self):
				return {"id": kw.get("eventId") or f"g{len(rec.calls)}"}
		return Done()

	def insert(self, **kw):
		return self._call("insert", kw)

	def update(self, **kw):
		return self._call("update", kw)

	def delete(self, **kw):
		return self._call("delete", kw)


class WriteCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.sql("delete from `tabEvent` where life_space=%s", PRIVATE)
		self.rec = Recorder()
		p = patch.object(gcal_write, "service_for", lambda user: self.rec)
		p.start()
		self.addCleanup(p.stop)
		self.addCleanup(lambda: frappe.defaults.clear_default(gcal_write.KEY, parent=OWNER))

	def turn_on(self):
		frappe.defaults.set_user_default(gcal_write.KEY, "cal-1", OWNER)

	def accept_event(self, **extra):
		item = self.make("Life Inbox Item", title="issue31 invite", source_type="Voice Note", raw_text="x", status="To Review")
		payload = {"subject": "Lunch with Arjun", "starts_on": f"{add_days(today(), 3)} 13:00:00", "ends_on": f"{add_days(today(), 3)} 14:00:00",
			"description": "at the club", **extra}
		prop = frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": item.name, "kind": "Event", "preview": "Lunch",
			"payload": json.dumps(payload), "status": "Pending"}).insert()
		out = review.decide(prop.name, "accept")
		return frappe.get_doc("Event", out["created_name"])


class TestWriteEvents(WriteCase):
	def test_1_accepting_an_event_creates_one_private_event_in_google(self):
		self.turn_on()
		ev = self.accept_event()
		self.assertEqual([c[0] for c in self.rec.calls], ["insert"])
		kw = self.rec.calls[0][1]
		body = kw["body"]
		self.assertEqual((kw["calendarId"], body["summary"], body["visibility"]), ("cal-1", "Lunch with Arjun", "private"))
		self.assertEqual(get_datetime(body["start"]["dateTime"]), get_datetime(f"{add_days(today(), 3)} 13:00:00"))
		self.assertEqual(get_datetime(body["end"]["dateTime"]), get_datetime(f"{add_days(today(), 3)} 14:00:00"))
		self.assertNotIn("attendees", body)
		self.assertEqual(kw["sendUpdates"], "none")
		self.assertIn(f"/life/calendar?open=event:{ev.name}", body["description"])
		self.assertIn("at the club", body["description"])
		self.assertEqual(frappe.db.get_value("Event", ev.name, ["google_calendar_event_id", "google_calendar_id"]), ("g1", "cal-1"))

	def test_1b_guests_are_invited_only_when_given(self):
		self.turn_on()
		self.accept_event(attendees="arjun@example.com, not an email")
		kw = self.rec.calls[0][1]
		self.assertEqual(kw["body"]["attendees"], [{"email": "arjun@example.com"}])
		self.assertEqual(kw["sendUpdates"], "all")

	def test_2_with_writing_off_nothing_is_sent(self):
		ev = self.accept_event()
		self.assertEqual(self.rec.calls, [])
		self.assertFalse(frappe.db.get_value("Event", ev.name, "google_calendar_event_id"))

	def test_2b_an_event_read_from_google_is_never_written_back(self):
		self.turn_on()
		gcal.upsert(OWNER, PRIVATE, "primary", {"id": "theirs", "status": "confirmed", "summary": "Their meeting",
			"start": {"dateTime": f"{today()}T10:00:00"}, "end": {"dateTime": f"{today()}T11:00:00"}})
		doc = frappe.get_doc("Event", {"google_calendar_event_id": "theirs"})
		doc.subject = "Renamed here"
		doc.flags.ignore_permissions = True
		doc.save()
		doc.delete(ignore_permissions=True)
		self.assertEqual(self.rec.calls, [])

	def test_3_moving_updates_and_deleting_deletes(self):
		self.turn_on()
		ev = self.accept_event()
		ev.starts_on, ev.ends_on = f"{add_days(today(), 4)} 09:00:00", f"{add_days(today(), 4)} 10:00:00"
		ev.save(ignore_permissions=True)
		verb, kw = self.rec.calls[-1]
		self.assertEqual((verb, kw["eventId"], kw["calendarId"]), ("update", "g1", "cal-1"))
		self.assertEqual(get_datetime(kw["body"]["start"]["dateTime"]), get_datetime(f"{add_days(today(), 4)} 09:00:00"))
		calendar_api.delete_event(ev.name)
		verb, kw = self.rec.calls[-1]
		self.assertEqual((verb, kw["eventId"]), ("delete", "g1"))

	def test_a_google_failure_does_not_fail_the_accept(self):
		self.turn_on()
		self.rec.insert = lambda **kw: (_ for _ in ()).throw(RuntimeError("Google is down"))
		ev = self.accept_event()
		self.assertTrue(frappe.db.exists("Event", ev.name))
		self.assertFalse(frappe.db.get_value("Event", ev.name, "google_calendar_event_id"))


class TestWriteGoalBlocks(WriteCase):
	def block(self, **kw):
		g = goals.create("issue31 goal", "Open", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		at = get_datetime(f"{add_days(today(), 7)} 10:00:00")
		return g, at, __import__("lifeos.weekplan", fromlist=["add"]).add(g, title="issue31 draft", scheduled_at=at, duration_min=90, **kw)

	def test_4_a_goal_block_is_written_to_google(self):
		self.turn_on()
		g, at, task = self.block()
		self.assertEqual([c[0] for c in self.rec.calls], ["insert"])
		body = self.rec.calls[0][1]["body"]
		self.assertEqual((body["summary"], body["visibility"]), ("issue31 draft", "private"))
		self.assertEqual(get_datetime(body["start"]["dateTime"]), at)
		self.assertEqual(get_datetime(body["end"]["dateTime"]), at + timedelta(minutes=90))
		self.assertIn(f"open=task:{task.name}", body["description"])
		self.assertEqual(frappe.db.get_value("Life Task", task.name, "google_event_id"), "g1")

	def test_4b_off_sends_nothing_and_moving_updates_the_block(self):
		g, at, task = self.block()
		self.assertEqual(self.rec.calls, [])
		self.turn_on()
		task = frappe.get_doc("Life Task", task.name)
		from lifeos import weekplan
		weekplan.add(g, task=task.name, scheduled_at=at + timedelta(hours=2), duration_min=60)
		self.assertEqual([c[0] for c in self.rec.calls], ["insert"])
		weekplan.add(g, task=task.name, scheduled_at=at + timedelta(hours=4), duration_min=60)
		self.assertEqual(self.rec.calls[-1][0], "update")
		weekplan.add(g, task=task.name, scheduled_at="", duration_min=60)
		self.assertEqual(self.rec.calls[-1][0], "delete")
		self.assertFalse(frappe.db.get_value("Life Task", task.name, "google_event_id"))


class TestChoice(LifeTestCase):
	def test_5_the_choice_is_saved_listed_and_can_be_turned_off(self):
		self.addCleanup(lambda: frappe.defaults.clear_default(gcal_write.KEY, parent=OWNER))
		with patch.object(gcal, "source_for", lambda acc: gcal.FakeSource()):
			self.assertIsNone(gcal_api.state()["write"])
			self.assertEqual(gcal_api.set_write("primary")["write"], "primary")
			self.assertEqual(gcal_api.calendars()["write"], "primary")
			with self.assertRaises(frappe.ValidationError):
				gcal_api.set_write("someone-elses")
			self.assertIsNone(gcal_api.set_write("")["write"])
