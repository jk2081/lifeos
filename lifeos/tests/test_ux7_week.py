"""Set 7, step 3: working hours and the weekly review. Slot suggestion within working hours without overlaps, goal cards, Add
(scheduled, delegated), the review's key results, and scheduled tasks on Today and the calendar."""
from datetime import datetime, timedelta

import frappe
from frappe.utils import add_days, get_datetime, getdate, today

from lifeos import readings, weekplan
from lifeos.api import calendar, goals, settings, week
from lifeos.api import today as today_api
from lifeos.tests.base import AGENT, OWNER, PRIVATE, LifeTestCase


def monday_at(hour, weeks=1):
	d = getdate(today())
	m = d - timedelta(days=d.weekday()) + timedelta(days=7 * weeks)
	return datetime(m.year, m.month, m.day, hour, 0)


class WeekCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		s = frappe.get_single("Life Settings")
		s.work_days, s.work_start, s.work_end = "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday", "09:00:00", "19:00:00"
		s.save(ignore_permissions=True)
		frappe.clear_document_cache("Life Settings", "Life Settings")


class TestSlots(WeekCase):
	def test_working_intervals_skip_sunday_and_clip_to_hours(self):
		a = monday_at(7) - timedelta(days=1)  # Sunday 07:00
		got = weekplan.working(a, a + timedelta(days=2))
		self.assertEqual(got[0], (monday_at(9), monday_at(19)))
		self.assertEqual(len(got), 1)  # Sunday is not a working day; Tuesday starts after the window

	def test_first_slot_avoids_events_and_scheduled_tasks(self):
		start = monday_at(9)
		free = weekplan.subtract([(start, monday_at(19))], [(monday_at(9), monday_at(10)), (start + timedelta(minutes=90), monday_at(12))])
		self.assertEqual(weekplan.first_slot(free, 60), monday_at(12))  # 10:00 to 10:30 is too short for an hour
		self.assertEqual(weekplan.first_slot(free, 30), monday_at(10))
		self.assertIsNone(weekplan.first_slot([(monday_at(18), monday_at(19))], 90))

	def test_cards_take_slots_inside_hours_without_overlaps(self):
		now = monday_at(8)
		frappe.get_doc({"doctype": "Event", "subject": "ux7 meeting", "starts_on": monday_at(9), "ends_on": monday_at(11), "event_type": "Private",
			"life_space": PRIVATE}).insert(ignore_permissions=True)
		blocker = frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 planned", "status": "Open", "scheduled_at": monday_at(11),
			"duration_min": 60, "area": self.areas["Tea"]}).insert()
		for i in range(3):
			goals.create(f"ux7 plan goal {i}", "Open", space=PRIVATE, area=self.areas["Tea"], done_when="x")
		out = weekplan.cards(PRIVATE, now=now, ai=False)
		slots = [(get_datetime(c["slot"]), c["minutes"]) for c in out["cards"] if c["slot"]]
		self.assertTrue(slots)
		taken = [(monday_at(9), monday_at(11)), (monday_at(11), monday_at(12))]
		mine = []
		h = weekplan.hours()
		for s, m in slots:
			e = s + timedelta(minutes=m)
			self.assertIn(weekplan.DAYS[s.weekday()], h["days"])
			self.assertGreaterEqual((s.hour, s.minute), h["start"])
			self.assertLessEqual((e.hour, e.minute), h["end"])
			for a, b in taken + mine:
				self.assertFalse(s < b and a < e, f"{s} overlaps {a}")
			mine.append((s, e))
		self.assertGreater(out["free_minutes"], 0)
		self.assertNotIn(blocker.name, [c["task"] for c in out["cards"]])

	def test_working_hours_setting(self):
		settings.save({"work_days": "Tuesday,Monday", "work_start": "10:00:00", "work_end": "16:00:00"})
		frappe.clear_document_cache("Life Settings", "Life Settings")
		self.assertEqual(weekplan.hours(), {"days": ["Monday", "Tuesday"], "start": (10, 0), "end": (16, 0)})
		self.assertRaises(frappe.ValidationError, settings.save, {"work_end": "08:00:00"})
		self.assertRaises(frappe.ValidationError, settings.save, {"work_days": ""})


class TestAddGoalWork(WeekCase):
	def test_add_creates_a_scheduled_task_under_the_goal(self):
		g = goals.create("ux7 add goal", "Open", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		at = monday_at(10)
		out = week.add_goal_work(g, title="ux7 draft the plan", scheduled_at=str(at), duration_min=90, note="the soil report")
		t = frappe.get_doc("Life Task", out["task"])
		self.assertEqual((t.goal, t.area, get_datetime(t.scheduled_at), t.duration_min, t.status), (g, self.areas["Tea"], at, 90, "Open"))
		self.assertIn("the soil report", t.notes_md)
		# Add again updates the same task
		week.add_goal_work(g, task=t.name, title="ux7 draft the plan", scheduled_at="", duration_min=30)
		t.reload()
		self.assertIsNone(t.scheduled_at)
		self.assertEqual(t.notes_md.count("the soil report"), 1)

	def test_someone_else_makes_it_waiting_and_delegated(self):
		g = goals.create("ux7 delegate goal", "Open", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		out = week.add_goal_work(g, title="ux7 get the quotes", scheduled_at=str(monday_at(11)), duration_min=60, who="Mithun")
		self.assertEqual((out["status"], out["waiting_on"]), ("Waiting", "Mithun"))
		self.assertEqual(frappe.get_all("Life Exit", filters={"record_name": out["task"], "reversed": 0}, pluck="pile"), ["Delegated"])
		mine = week.add_goal_work(g, title="ux7 mine", who="Me")
		self.assertEqual(mine["status"], "Open")

	def test_cards_prefill_the_oldest_open_task(self):
		g = goals.create("ux7 oldest goal", "Open", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		first = frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 first step", "goal": g, "status": "Open", "area": self.areas["Tea"]}).insert()
		frappe.db.set_value("Life Task", first.name, "creation", add_days(today(), -10))
		frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 second step", "goal": g, "status": "Open", "area": self.areas["Tea"]}).insert()
		card = next(c for c in weekplan.cards(PRIVATE, ai=False)["cards"] if c["goal"] == g)
		self.assertEqual((card["task"], card["next_action"], card["minutes"]), (first.name, "ux7 first step", 60))

	def test_people_only(self):
		g = goals.create("ux7 agent goal", "Open", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, week.add_goal_work, g, title="x")
		self.assertRaises(frappe.PermissionError, week.goal_plan, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, week.key_results, space=PRIVATE)


class TestKeyResults(WeekCase):
	def test_readings_finish_lines_and_stale_goals(self):
		n = goals.create("ux7 kr number", "Open", space=PRIVATE, area=self.areas["Tea"], measure_kind="Number", measure="Yield", unit="kg/ha",
			start_value=1200, target_value=1800)["name"]
		r = readings.suggest(n, 1500, today(), "Yield came to 1500", by="Agent")
		old = frappe.get_doc({"doctype": "Life Goal", "space": PRIVATE, "title": "ux7 kr no line", "goal_type": "Open", "area": self.areas["Tea"]}).insert()
		out = week.key_results(space=PRIVATE)
		self.assertIn(r.name, [x["name"] for x in out["readings"]])
		self.assertEqual(next(x for x in out["readings"] if x["name"] == r.name)["goal_title"], "ux7 kr number")
		self.assertIn(old.name, [g["name"] for g in out["needs_finish_line"]])
		self.assertIn(n, [g["name"] for g in out["stale"]])
		goals.confirm_reading(r.name)
		out = week.key_results(space=PRIVATE)
		self.assertNotIn(n, [g["name"] for g in out["stale"]])
		self.assertNotIn(r.name, [x["name"] for x in out["readings"]])


class TestScheduledOnTodayAndCalendar(WeekCase):
	def test_today_and_calendar(self):
		at = get_datetime(f"{today()} 15:30:00")
		t = frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 at half three", "status": "Open", "scheduled_at": at,
			"duration_min": 45, "area": self.areas["Tea"]}).insert()
		d = today_api.get(space=PRIVATE)
		rows = next(g for g in d["next"]["groups"] if g["key"] == "today")["rows"]
		row = next(r for r in rows if r["name"] == t.name)
		self.assertEqual((row["why"], row["lead"]), ("Scheduled", "15:30"))
		self.assertIn(t.name, [e["name"] for e in d["rail"]["events"] if e.get("source") == "task"])
		cal = calendar.get(space=PRIVATE, from_date=today(), to_date=add_days(today(), 6))
		item = next(i for i in cal["items"] if i["name"] == t.name)
		self.assertEqual((item["all_day"], item["start"][11:16], item["end"][11:16]), (0, "15:30", "16:15"))
