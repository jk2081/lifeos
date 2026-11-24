"""Tests for calendar."""
from datetime import timedelta
import json
from unittest.mock import patch

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

from lifeos.api import calendar, calendar as calendar_api, gcal as gcal_api, goals, goals as goal_api, review
from lifeos.calendar import notes
from lifeos.review import findings, followups, gcal, gcal_write, meetings
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import CalCase, gevent, item, ME, set_key, task


def titles(items, source=None):
	return [i["title"] for i in items if not source or i["source"] == source]


class TestCalendar(LifeTestCase):
	def test_important_dates_repeat_every_year(self):
		made = calendar.add_important_date(space=PRIVATE, title="Ruchi m6", day=14, month=1, kind="Birthday")["name"]
		event = frappe.get_doc("Event", made)  # an important date is an all-day Event that repeats yearly (issue 72)
		self.assertEqual((event.all_day, event.repeat_on, event.life_space), (1, "Yearly", PRIVATE))
		for year in (2010, 2026, 2027, 2031):
			items = calendar.get(space=PRIVATE, from_date=f"{year}-01-10", to_date=f"{year}-01-20")["items"]
			hits = [i for i in items if i["source"] == "important" and i["title"] == "Ruchi m6"]
			self.assertEqual([h["date"] for h in hits], [f"{year}-01-14"])

	def test_29_february_shows_every_year(self):
		calendar.add_important_date(space=PRIVATE, title="Leap day m6", day=29, month=2)
		leap = calendar.get(space=PRIVATE, from_date="2028-02-25", to_date="2028-03-02")["items"]
		self.assertEqual([i["date"] for i in leap if i["title"] == "Leap day m6"], ["2028-02-29"])
		common = calendar.get(space=PRIVATE, from_date="2027-02-25", to_date="2027-03-02")["items"]
		self.assertEqual([i["date"] for i in common if i["title"] == "Leap day m6"], ["2027-02-28"])
		self.assertIn("Leap day m6", [e["title"] for e in calendar.year(space=PRIVATE, year=2027)["days"]["2027-02-28"]])

	def test_year_of_first_occurrence(self):
		calendar.add_important_date(space=PRIVATE, title="Wedding m6", day=23, month=11, year=2010, kind="Anniversary")
		items = calendar.get(space=PRIVATE, from_date="2026-11-20", to_date="2026-11-25")["items"]
		self.assertEqual([i["label"] for i in items if i["title"] == "Wedding m6"], ["Wedding m6"])
		self.assertEqual([i for i in calendar.get(space=PRIVATE, from_date="2009-11-20", to_date="2009-11-25")["items"] if i["title"] == "Wedding m6"], [])

	def test_calendar_merges_four_sources(self):
		day = add_days(getdate(today()), 3)
		calendar.add_event(space=PRIVATE, subject="Meeting m6", starts_on=f"{day} 10:00:00", ends_on=f"{day} 11:00:00")
		calendar.add_important_date(space=PRIVATE, title="Birthday m6", day=day.day, month=day.month)
		self.make("Life Task", title="Task due m6", due_date=day)
		self.make("Life Task", title="Done task m6", due_date=day, status="Done")
		self.make("Life Vault Document", title="Passport m6", expiry_date=day)
		data = calendar.get(space=PRIVATE, from_date=str(day), to_date=str(day))
		self.assertEqual(titles(data["items"], "event"), ["Meeting m6"])
		self.assertEqual(titles(data["items"], "important"), ["Birthday m6"])
		self.assertEqual(titles(data["items"], "task"), ["Task due m6"])
		self.assertEqual(titles(data["items"], "vault"), ["Passport m6 expires"])
		self.assertEqual(data["google"]["connected"], False)  # works without the Google connection
		wide = calendar.get(space=PRIVATE, from_date="2026-01-01", to_date="2027-12-31")
		self.assertLessEqual((getdate(wide["to_date"]) - getdate(wide["from_date"])).days, 100)

	def test_year_view_rules(self):
		calendar.add_event(space=PRIVATE, subject="Phuket m6", starts_on="2029-01-07", ends_on="2029-01-11", all_day=1)
		calendar.add_event(space=PRIVATE, subject="Board day m6", starts_on="2029-02-26", all_day=1)
		calendar.add_event(space=PRIVATE, subject="Timed meeting m6", starts_on="2029-03-03 10:00:00", ends_on="2029-03-03 11:00:00")
		calendar.add_important_date(space=PRIVATE, title="Jai m6", day=20, month=1)
		self.make("Life Vault Document", title="Licence m6", expiry_date="2029-12-12")
		cycle = self.make("Life Cycle", title="Y cycle", start_date="2029-10-01", status="Planned")
		data = calendar.year(space=PRIVATE, year=2029)
		days = data["days"]
		for d in ("07", "08", "09", "10", "11"):  # a multi-day event marks each of its days
			self.assertIn(("trip", "Phuket m6"), [(e["type"], e["title"]) for e in days[f"2029-01-{d}"]])
		self.assertNotIn("2029-01-12", [k for k, v in days.items() if any(e["title"] == "Phuket m6" for e in v)])
		self.assertIn(("event", "Board day m6"), [(e["type"], e["title"]) for e in days["2029-02-26"]])
		self.assertNotIn("Timed meeting m6", [e["title"] for v in days.values() for e in v])  # timed meetings are left out
		self.assertIn("Jai m6", [e["title"] for e in days["2029-01-20"]])
		self.assertIn(("vault", "Licence m6 expires"), [(e["type"], e["title"]) for e in days["2029-12-12"]])
		self.assertIn("12WY starts", [e["title"] for e in days["2029-10-01"]])
		self.assertIn("12WY ends", [e["title"] for e in days["2029-12-23"]])
		self.assertEqual([c["name"] for c in data["cycles"]], [cycle.name])
		self.assertIn("Jai m6", [e["title"] for e in calendar.year(space=PRIVATE, year=2030)["days"]["2030-01-20"]])  # in every year

	def test_agent_event_is_visible_to_the_owner_and_not_to_outsiders(self):
		self.as_user(AGENT)
		out = calendar.add_event(space=PRIVATE, subject="Agent event m6", starts_on="2026-11-20 09:00:00")
		event = frappe.get_doc("Event", out["name"])
		self.assertEqual((event.owner, event.life_space), (AGENT, PRIVATE))
		self.as_user(OWNER)
		self.assertIn(out["name"], frappe.get_list("Event", pluck="name", limit=0))
		self.assertTrue(frappe.get_doc("Event", out["name"]).has_permission("read"))
		self.assertIn("Agent event m6", titles(calendar.get(space=PRIVATE, from_date="2026-11-20", to_date="2026-11-20")["items"]))
		self.as_user(FAMILY)
		self.assertNotIn(out["name"], frappe.get_list("Event", pluck="name", limit=0))
		self.assertFalse(frappe.get_doc("Event", out["name"]).has_permission("read"))
		self.assertRaises(frappe.PermissionError, calendar.get, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, calendar.year, space=PRIVATE)
		self.assertNotIn("Agent event m6", titles(calendar.get(space=SHARED, from_date="2026-11-20", to_date="2026-11-20")["items"]))
		self.assertRaises(frappe.PermissionError, calendar.delete_event, out["name"])
		self.assertRaises(frappe.PermissionError, calendar.add_event, space=PRIVATE, subject="x", starts_on="2026-11-20")
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, calendar.delete_event, out["name"])  # agents never delete
		self.as_user(OWNER)
		calendar.delete_event(out["name"])

	def test_event_from_a_user_takes_their_default_space(self):
		# the family member owns no space, so the site default applies when they belong to it
		before = frappe.db.get_single_value("Life Settings", "default_space")
		frappe.db.set_single_value("Life Settings", "default_space", SHARED)
		self.addCleanup(frappe.db.set_single_value, "Life Settings", "default_space", before)
		self.as_user(FAMILY)
		# set 3: a Life User has no desk access, so core Event's own create permission (Desk User) is not theirs; the
		# Google sync writes the event for them, which is what this stands for
		event = frappe.get_doc({"doctype": "Event", "subject": "Synced from Google m6", "starts_on": "2026-11-21 09:00:00"}).insert(ignore_permissions=True)
		self.assertEqual(event.life_space, SHARED)
		self.as_user(OWNER)
		self.assertIn("Synced from Google m6", titles(calendar.get(space=SHARED, from_date="2026-11-21", to_date="2026-11-21")["items"]))


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
		g = goals.create("issue31 goal", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		at = get_datetime(f"{add_days(today(), 7)} 10:00:00")
		return g, at, __import__("lifeos.tasks.weekplan", fromlist=["add"]).add(g, title="issue31 draft", scheduled_at=at, duration_min=90, **kw)

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
		from lifeos.tasks import weekplan
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
		with patch.object(gcal, "source_for", lambda acc: gcal.FakeSource()), patch.dict(frappe.local.conf, {"lifeos_fake_calendar": 1}):
			self.assertIsNone(gcal_api.state()["write"])
			self.assertEqual(gcal_api.set_write("primary")["write"], "primary")
			self.assertEqual(gcal_api.calendars()["write"], "primary")
			with self.assertRaises(frappe.ValidationError):
				gcal_api.set_write("someone-elses")
			self.assertIsNone(gcal_api.set_write("")["write"])


class SetRecorder:
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
		goal = self.make("Life Goal", title="Ghillidary yield", horizon="Long term", measure_kind="Number", measure="yield", unit="kg/ha",
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
		svc = SetRecorder([gevent("g1", f"{self.day} 10:00", 60, "Board call", [ME, "rao@greenfields.example"])])
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


class TestEventNotes(CalCase):
	"""Issue 99: notes on an event are Frappe Comments, kept through every re-sync, never written to Google."""

	def google_event(self, key="n1", title="Wedding n99"):
		ev = gevent(key, f"{today()} 10:00:00", 60, title, [])
		return self.read(ev)[title]["name"]

	def test_a_note_is_a_comment_and_survives_a_resync(self):
		name = self.google_event()
		note = calendar_api.add_note(name, "Bring the gift")
		row = frappe.get_doc("Comment", note["name"])
		self.assertEqual((row.comment_type, row.reference_doctype, row.reference_name, row.content), ("Comment", "Event", name, "Bring the gift"))
		self.read(gevent("n1", f"{today()} 11:00:00", 60, "Wedding n99 moved", []))  # Google changed the event
		self.assertEqual([n["text"] for n in notes.listing(name)], ["Bring the gift"])
		self.assertEqual(calendar_api.entry("event", name)["notes"][0]["by"], "You")

	def test_each_repeat_has_its_own_notes(self):
		first = calendar_api.add_event(space=PRIVATE, subject="Weekly n99", starts_on=f"{today()} 09:00:00")["name"]
		frappe.db.set_value("Event", first, {"repeat_this_event": 1, "repeat_on": "Weekly", "monday": 1, "tuesday": 1, "wednesday": 1,
			"thursday": 1, "friday": 1, "saturday": 1, "sunday": 1})
		later = str(add_days(today(), 1))
		calendar_api.add_note(first, "today only", occurrence=str(today()))
		calendar_api.add_note(first, "tomorrow only", occurrence=later)
		self.assertEqual([n["text"] for n in notes.listing(first, str(today()))], ["today only"])
		self.assertEqual([n["text"] for n in notes.listing(first, later)], ["tomorrow only"])
		self.assertEqual(calendar_api.entry("event", f"{first}@{later}")["occurrence"], later)

	def test_an_agent_adds_notes_but_cannot_change_the_owners(self):
		name = self.google_event()
		mine = calendar_api.add_note(name, "owner's note")["name"]
		self.as_user(AGENT)
		theirs = calendar_api.add_note(name, "agent's note")
		self.assertTrue(theirs["agent"])
		with self.assertRaises(frappe.PermissionError):
			calendar_api.update_note(mine, "changed")
		with self.assertRaises(frappe.PermissionError):
			calendar_api.delete_note(mine)
		with self.assertRaises(frappe.PermissionError):
			calendar_api.delete_note(theirs["name"])
		self.assertEqual(frappe.db.get_value("Comment", mine, "content"), "owner's note")
		self.as_user(OWNER)
		self.assertEqual([n["agent"] for n in notes.listing(name)], [False, True])
		calendar_api.update_note(mine, "edited")
		calendar_api.delete_note(theirs["name"])
		self.assertEqual([n["text"] for n in notes.listing(name)], ["edited"])

	def test_make_a_task_from_a_note(self):
		name = self.google_event()
		note = calendar_api.add_note(name, "Book the flights")["name"]
		out = calendar_api.note_to_task(note)
		task = frappe.get_doc("Life Task", out["task"])
		self.assertEqual((task.title, task.event, task.space), ("Book the flights", name, PRIVATE))
		self.assertEqual(calendar_api.note_to_task(note), {"task": task.name, "made": False})  # once for each note
		self.assertEqual(notes.listing(name)[0]["task"], task.name)

	def test_hide_in_life_os_sets_a_flag_and_never_calls_google(self):
		name = self.google_event()
		rec = Recorder()
		with patch.object(gcal_write, "service_for", lambda user: rec):
			frappe.defaults.set_user_default(gcal_write.KEY, "cal-1", OWNER)
			self.addCleanup(lambda: frappe.defaults.clear_default(gcal_write.KEY, parent=OWNER))
			calendar_api.hide_event(name)
			with self.assertRaises(frappe.ValidationError):
				calendar_api.delete_event(name)  # an event from Google is never deleted here
		self.assertEqual(rec.calls, [])
		self.assertEqual(frappe.db.get_value("Event", name, "life_hidden"), 1)
		week = (str(today()), str(today()))
		shown = lambda **kw: titles(calendar_api.get(space=PRIVATE, from_date=week[0], to_date=week[1], **kw)["items"], "event")
		self.assertEqual(shown(), [])
		self.assertEqual(shown(show_hidden=1), ["Wedding n99"])
		self.read(gevent("n1", f"{today()} 12:00:00", 60, "Wedding n99", []))  # a re-sync keeps it hidden
		self.assertEqual(shown(), [])
		calendar_api.hide_event(name, hidden=0)
		self.assertEqual(shown(), ["Wedding n99"])

	def test_events_made_here_can_be_deleted_and_a_core_pulled_all_day_end_reads_as_the_last_day(self):
		mine = calendar_api.add_event(space=PRIVATE, subject="Mine n99", starts_on=f"{today()} 10:00:00")["name"]
		calendar_api.delete_event(mine)
		self.assertFalse(frappe.db.exists("Event", mine))
		wed = frappe.get_doc({"doctype": "Event", "subject": "Core pulled n99", "starts_on": f"{today()} 00:00:00", "ends_on": f"{add_days(today(), 1)} 00:00:00",
			"all_day": 1, "event_type": "Public", "life_space": PRIVATE, "pulled_from_google_calendar": 1}).insert()
		out = calendar_api.entry("event", wed.name)
		self.assertEqual((out["starts_on"][:10], out["ends_on"][:10], out["from_google"]), (str(today()), str(today()), True))
		item = [i for i in calendar_api.get(space=PRIVATE, from_date=str(today()), to_date=str(today()))["items"] if i["title"] == "Core pulled n99"][0]
		self.assertFalse(item["multi_day"])
