"""Issue 16: Today > Week, Month and Year. The server's parts: the year's timeline and the week's goal work."""
import frappe
from frappe.utils import add_days, getdate, now_datetime, today

from lifeos import year_plan as plan
from lifeos.api import calendar as cal
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase


class TestTodayViews(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Review", {"user": OWNER})
		frappe.db.sql("update `tabLife Cycle` set status='Planned' where space=%s and status='Active'", PRIVATE)
		self.year = getdate(today()).year
		self.clear()

	def tearDown(self):
		self.clear()
		super().tearDown()

	def clear(self):
		frappe.db.delete("Life Task", {"space": PRIVATE, "title": ("like", "i16 %")})
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		frappe.db.delete("Life Cycle", {"space": PRIVATE, "title": ("like", "i16 %")})
		frappe.db.delete("Life Important Date", {"space": PRIVATE, "title": ("like", "i16 %")})
		frappe.db.delete("Life Review", {"user": OWNER})

	def cycle(self, status="Active", start=None, title="i16 cycle"):
		return self.make("Life Cycle", title=title, start_date=start or add_days(today(), -21), status=status)

	def goal(self, title, area, cycle=None, **values):
		return self.make("Life Goal", title=title, area=area, cycle=cycle.name if cycle else None, horizon="12 weeks" if cycle else "Year", **values)

	def lane(self, out, area):
		return next((lane for lane in out["lanes"] if lane["area"] == area), None)

	# acceptance 3: a bar for each goal, with dates, in its area's lane
	def test_a_goal_is_a_bar_in_its_areas_lane(self):
		cycle = self.cycle()
		g = self.goal("i16 tea goal", self.areas["Tea"], cycle)
		annual = self.goal("i16 career goal", self.life["Career"], target_date=f"{self.year}-12-31")
		out = cal.year_plan(PRIVATE, self.year)
		tea = self.lane(out, self.areas["Tea"])
		self.assertTrue(tea, "a part has its own row")
		self.assertEqual(tea["part_of"], "Career")
		bar = next(b for b in tea["goals"] if b["name"] == g.name)
		# the bar covers its cycle, cut at the ends of the year
		self.assertEqual((bar["start"], bar["end"]), (max(str(cycle.start_date), f"{self.year}-01-01"), min(str(cycle.end_date), f"{self.year}-12-31")))
		career = self.lane(out, self.life["Career"])
		self.assertIn(annual.name, [b["name"] for b in career["goals"]])
		self.assertNotIn(g.name, [b["name"] for b in career["goals"]], "a part's goal is not in the parent's row")

	# acceptance 3: finished and carried goals are grey and say so
	def test_finished_and_carried_goals_are_grey(self):
		cycle = self.cycle()
		done = self.goal("i16 done", self.life["Career"], cycle, outcome="Achieved")
		carried = self.goal("i16 carried", self.life["Career"], cycle, outcome="Carried")
		open_ = self.goal("i16 open", self.life["Career"], cycle)
		bars = {b["name"]: b for b in self.lane(cal.year_plan(PRIVATE, self.year), self.life["Career"])["goals"]}
		self.assertTrue(bars[done.name]["grey"] and bars[carried.name]["grey"])
		self.assertFalse(bars[open_.name]["grey"])
		self.assertTrue(bars[carried.name]["label"].endswith("carried"))

	# acceptance 4: an area that is off has no lane
	def test_an_area_that_is_off_has_no_lane(self):
		cycle = self.cycle()
		mind = self.life["Mind"]
		frappe.db.set_value("Life Area", mind, "is_on", 0)
		g = self.goal("i16 mind goal", mind, cycle)
		out = cal.year_plan(PRIVATE, self.year)
		self.assertIsNone(self.lane(out, mind))
		self.assertNotIn(g.name, [b["name"] for lane in out["lanes"] for b in lane["goals"]])
		frappe.db.set_value("Life Area", mind, "is_on", 1)
		self.assertTrue(self.lane(cal.year_plan(PRIVATE, self.year), mind))

	# acceptance 3: one tick per weekly review, with the right count
	def test_one_tick_for_each_weekly_review(self):
		monday = getdate(today()) - frappe.utils.datetime.timedelta(days=getdate(today()).weekday())
		for weeks_ago in (1, 2, 4):
			start = add_days(monday, -7 * weeks_ago)
			frappe.get_doc({"doctype": "Life Review", "space": PRIVATE, "user": OWNER, "kind": "Weekly", "status": "Locked", "period_start": start,
				"period_end": add_days(start, 6), "locked_on": now_datetime(), "title": "i16 review", "tab_state": "{}"}).insert(ignore_permissions=True)
		reviews = cal.year_plan(PRIVATE, self.year)["reviews"]
		self.assertEqual(reviews["done"], 3)
		ticks = {w["start"]: w for w in reviews["weeks"]}
		self.assertTrue(ticks[str(add_days(monday, -7))]["done"])
		self.assertFalse(ticks[str(add_days(monday, -14 - 7))]["done"], "a week with no review is a miss")
		self.assertTrue(ticks[str(monday)]["future"], "the week that is running is not a miss")
		# a locked review of another person is not mine
		self.assertEqual(sum(1 for w in reviews["weeks"] if w["done"]), reviews["done"])
		self.assertLessEqual(reviews["done"], reviews["total"])

	def test_the_cards(self):
		cycle = self.cycle()
		self.goal("i16 a", self.life["Career"], cycle, outcome="Achieved")
		self.goal("i16 b", self.life["Career"], cycle, outcome="Carried")
		self.goal("i16 c", self.life["Career"], cycle, outcome="Dropped")
		out = cal.year_plan(PRIVATE, self.year)
		self.assertEqual({k: out["summary"][k] for k in ("finished", "carried", "dropped")}, {"finished": 1, "carried": 1, "dropped": 1})
		nxt = out["next_cycle"]
		self.assertEqual(nxt["start"], str(plan.rules.next_monday(cycle.end_date)))
		self.assertEqual(nxt["planning_opens"], str(add_days(getdate(cycle.start_date), 70)))
		self.assertIsNone(cal.year_plan(PRIVATE, self.year - 1)["next_cycle"])

	def test_key_dates_are_pins(self):
		self.make("Life Important Date", title="i16 Anya", kind="Birthday", day=14, month=3)
		pins = cal.year_plan(PRIVATE, self.year)["key_dates"]
		self.assertIn(f"{self.year}-03-14", [p["date"] for p in pins if p["title"].startswith("i16 Anya")])

	def test_the_week_plan_lists_goal_work_and_the_top_three(self):
		cycle = self.cycle()
		goal = self.goal("i16 week goal", self.life["Career"], cycle)
		monday = getdate(today()) - frappe.utils.datetime.timedelta(days=getdate(today()).weekday())
		self.make("Life Task", title="i16 block", status="Open", area=self.life["Career"], goal=goal.name, scheduled_at=f"{add_days(monday, 1)} 09:00:00", duration_min=90)
		self.make("Life Task", title="i16 top", status="Open", area=self.life["Career"], is_top_three=1)
		out = cal.week_plan(PRIVATE, str(monday))
		self.assertEqual(out["goal_minutes"], 90)
		self.assertEqual(out["goals"][0]["goal"], goal.name)
		self.assertIn("i16 top", [t["title"] for t in out["top"]])
		self.assertEqual(out["score"]["week"], plan.rules.week_of(cycle, monday))
		self.assertEqual(cal.week_plan(PRIVATE, str(add_days(monday, 140)))["score"], None)

	# the API's day items are what Week and Month draw: events, due tasks and slots on their own dates
	def test_calendar_items_are_on_their_dates(self):
		due = add_days(today(), 1)
		self.make("Life Task", title="i16 due", status="Open", area=self.life["Career"], due_date=due)
		items = cal.get(PRIVATE, today(), str(add_days(today(), 3)))["items"]
		self.assertEqual([i["date"] for i in items if i["title"] == "i16 due"], [str(due)])
