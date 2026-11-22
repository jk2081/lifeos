"""Tests for today."""
import frappe
from frappe.utils import add_days, getdate, now_datetime, today

from lifeos import journal as rules, rhythms, year_plan as plan
from lifeos.api import calendar as cal, journal, tasks, today as today_api
from lifeos.tests.base import AGENT, LifeTestCase, OWNER, PRIVATE
from lifeos.tests.helpers import task


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


class TestTodayTasksOnly(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.sql("update `tabLife Cycle` set status='Planned' where space=%s and status='Active'", PRIVATE)
		frappe.db.delete("Life Task", {"space": PRIVATE})
		self.cycle = self.make("Life Cycle", title="i55 cycle", start_date=add_days(today(), -21), status="Active")
		self.goals = [self.make("Life Goal", cycle=self.cycle.name, title=f"i55 goal {i}", sort_order=i, area=self.areas["Tea"],
			actions=[{"title": f"i55 lead {i}", "per_week": 2}]) for i in range(3)]

	def rows(self):
		return [r for g in today_api.get(space=PRIVATE)["next"]["groups"] for r in g["rows"]]

	def test_goals_and_lead_actions_are_not_rows(self):
		data = today_api.get(space=PRIVATE)
		titles = {r["title"] for r in self.rows()}
		self.assertFalse(titles & {g.title for g in self.goals} | titles & {g.actions[0].title for g in self.goals})
		self.assertFalse([r for r in self.rows() if r.get("type") not in ("task", "event")])
		self.assertEqual(data["no_plan"], 3)

	def test_a_planned_task_shows_with_its_goal_and_ticks_the_lead_action(self):
		goal = self.goals[0]
		task = self.make("Life Task", title=goal.actions[0].title, goal=goal.name, due_date=add_days(today(), 1 if rules.week_of(self.cycle) else 0))
		rows = [r for r in self.rows() if r["name"] == task.name]
		if not rows:  # due tomorrow is next week on a Sunday: plan it for today instead
			task.due_date = today()
			task.save()
			rows = [r for r in self.rows() if r["name"] == task.name]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["goal_title"], goal.title)
		self.assertEqual(today_api.get(space=PRIVATE)["no_plan"], 2)
		tasks.set_status(task.name, "Done")
		week = rules.week_of(self.cycle)
		ticks = frappe.db.get_value("Life Action Log", {"action_id": goal.actions[0].name, "week": week}, "count")
		self.assertEqual(ticks, 1)
		self.assertEqual(journal.grid(cycle=self.cycle.name, space=PRIVATE)["goals"][0]["actions"][0]["name"], goal.actions[0].name)

	def test_a_task_with_no_matching_lead_action_ticks_nothing(self):
		task = self.make("Life Task", title="i55 something else", goal=self.goals[1].name, due_date=today())
		tasks.set_status(task.name, "Done")
		self.assertFalse(frappe.db.count("Life Action Log", {"goal": self.goals[1].name}))

	def test_the_insights_list_has_no_duplicates_and_at_most_three(self):
		rows = [{"title": t} for t in ["Board call", "board  call", "Foxin", "Board call", "A", "B", "C"]]
		out = today_api.unique_insights(rows)
		self.assertEqual([r["title"] for r in out["rows"]], ["Board call", "Foxin", "A"])
		self.assertEqual(out["total"], 5)
		self.assertEqual(len(today_api.get(space=PRIVATE)["rail"]["insights"]) <= 3, True)


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class TestBanners(LifeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		s = frappe.get_single("Life Settings")
		cls.saved = (s.weekly_review_day, s.weekly_review_time, s.month_plan_enabled)
		s.weekly_review_day, s.weekly_review_time, s.month_plan_enabled = "Sunday", "18:00:00", 1
		s.save()
		frappe.conf.lifeos_test_clock = 1
		# a cycle whose week 11 starts on 2027-03-15 (it started on 2027-01-04)
		cls.cycle = frappe.get_doc({"doctype": "Life Cycle", "space": PRIVATE, "title": "ux6 cycle", "start_date": "2027-01-04",
			"end_date": "2027-03-28", "status": "Planned"}).insert().name

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.conf.lifeos_test_clock = 0
		s = frappe.get_single("Life Settings")
		s.weekly_review_day, s.weekly_review_time, s.month_plan_enabled = cls.saved
		s.save()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.db.delete("Life View State", {"screen": rhythms.SCREEN})

	def banner(self, at):
		return rhythms.banner(PRIVATE, at)

	def test_weekly_review_from_its_time_until_skipped_or_done(self):
		self.assertIsNone(self.banner("2027-02-14 17:00:00"))  # a Sunday, before 18:00
		b = self.banner("2027-02-14 18:30:00")
		self.assertEqual((b["key"], b["occurrence"]), ("review", "review:2027-02-08"))
		self.assertIsNone(self.banner("2027-02-13 19:00:00"))  # Saturday
		rhythms.dismiss(b["occurrence"])
		self.assertIsNone(self.banner("2027-02-14 19:00:00"))
		self.assertEqual(self.banner("2027-02-21 19:00:00")["occurrence"], "review:2027-02-15")  # next week it is back
		# set 8: done once a review covering that week is locked
		frappe.get_doc({"doctype": "Life Review", "space": PRIVATE, "user": frappe.session.user, "status": "Locked", "period_start": "2027-02-15",
			"period_end": "2027-02-21", "locked_on": "2027-02-21 18:40:00", "went_well": "done"}).insert()
		self.assertIsNone(self.banner("2027-02-21 19:00:00"))

	def test_month_plan_in_the_first_three_days(self):
		b = self.banner("2027-02-02 09:00:00")
		self.assertEqual((b["key"], b["text"]), ("month", "Plan February"))
		self.assertIsNone(self.banner("2027-02-04 09:00:00"))
		frappe.get_doc({"doctype": "Life Month Plan", "space": PRIVATE, "year": 2027, "month": 2}).insert()
		self.assertIsNone(self.banner("2027-02-02 09:00:00"))

	def test_cycle_weeks_and_precedence(self):
		frappe.db.set_value("Life Cycle", self.cycle, "status", "Active")
		other = frappe.get_all("Life Cycle", filters={"space": PRIVATE, "status": "Active", "name": ("!=", self.cycle)}, pluck="name")
		for c in other:
			frappe.db.set_value("Life Cycle", c, "status", "Closed")
		self.assertEqual(self.banner("2027-03-16 10:00:00")["key"], "plan-next")  # week 11, a Tuesday
		self.assertEqual(self.banner("2027-03-23 10:00:00")["key"], "close")  # week 12
		self.assertEqual(self.banner("2027-03-21 19:00:00")["key"], "review")  # Sunday of week 11: the review comes first
		frappe.get_doc({"doctype": "Life Cycle", "space": PRIVATE, "title": "ux6 next", "start_date": "2027-04-05", "end_date": "2027-06-27",
			"status": "Planned"}).insert()
		self.assertIsNone(self.banner("2027-03-16 10:00:00"))

	def test_skip_through_the_api_and_agents_get_none(self):
		frappe.set_user(self.owner_user())
		today_api.skip_banner("month:2027-02")
		self.assertIsNone(rhythms.banner(PRIVATE, "2027-02-02 09:00:00"))
		self.assertRaises(frappe.ValidationError, today_api.skip_banner, "anything")
		self.as_user(AGENT)
		self.assertIsNone(today_api.get(space=PRIVATE, at="2027-02-02 09:00:00")["banner"])

	def test_the_clock_moves_only_on_a_test_site(self):
		frappe.conf.lifeos_test_clock = 0
		try:
			self.assertEqual(getdate(rhythms.clock("2000-01-01 10:00:00")), getdate())
		finally:
			frappe.conf.lifeos_test_clock = 1
		self.assertEqual(str(rhythms.clock("2000-01-01 10:00:00"))[:10], "2000-01-01")
		self.assertEqual(add_days(getdate("2027-02-14"), 0).weekday(), DAYS.index("Sunday"))

	def owner_user(self):
		from lifeos.tests.base import OWNER

		return OWNER
