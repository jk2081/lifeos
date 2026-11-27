"""Tests for today."""
from unittest import mock

import frappe
from frappe.utils import add_days, add_to_date, getdate, now_datetime, today

from lifeos.calendar import calendar_data
from lifeos.goals import cycles as rules, rhythms, year_plan as plan
from lifeos.api import calendar as cal, dashboard as dash, goals, tasks, today as today_api
from lifeos import permissions
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
		frappe.db.delete("Event", {"life_space": PRIVATE, "subject": ("like", "i16 %")})
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
		out = cal.year_plan(PRIVATE)
		tea = self.lane(out, self.areas["Tea"])
		self.assertTrue(tea, "a part has its own row")
		self.assertEqual(tea["part_of"], "Career")
		bar = next(b for b in tea["goals"] if b["name"] == g.name)
		# the bar covers its cycle
		self.assertEqual((bar["start"], bar["end"]), (str(cycle.start_date), str(cycle.end_date)))
		career = self.lane(out, self.life["Career"])
		self.assertIn(annual.name, [b["name"] for b in career["goals"]])
		self.assertNotIn(g.name, [b["name"] for b in career["goals"]], "a part's goal is not in the parent's row")

	# acceptance 3: finished and carried goals are grey and say so
	def test_finished_and_carried_goals_are_grey(self):
		cycle = self.cycle()
		done = self.goal("i16 done", self.life["Career"], cycle, outcome="Achieved")
		carried = self.goal("i16 carried", self.life["Career"], cycle, outcome="Carried")
		open_ = self.goal("i16 open", self.life["Career"], cycle)
		bars = {b["name"]: b for b in self.lane(cal.year_plan(PRIVATE), self.life["Career"])["goals"]}
		self.assertTrue(bars[done.name]["grey"] and bars[carried.name]["grey"])
		self.assertFalse(bars[open_.name]["grey"])
		self.assertTrue(bars[carried.name]["label"].endswith("carried"))

	# acceptance 4: an area that is off has no lane
	def test_an_area_that_is_off_has_no_lane(self):
		cycle = self.cycle()
		mind = self.life["Mind"]
		frappe.db.set_value("Life Area", mind, "is_on", 0)
		g = self.goal("i16 mind goal", mind, cycle)
		out = cal.year_plan(PRIVATE)
		self.assertIsNone(self.lane(out, mind))
		self.assertNotIn(g.name, [b["name"] for lane in out["lanes"] for b in lane["goals"]])
		frappe.db.set_value("Life Area", mind, "is_on", 1)
		self.assertTrue(self.lane(cal.year_plan(PRIVATE), mind))

	def test_reviews_count_from_the_week_of_setup(self):
		monday = getdate(today()) - frappe.utils.datetime.timedelta(days=getdate(today()).weekday())
		for weeks_ago in (1, 2, 4):
			start = add_days(monday, -7 * weeks_ago)
			frappe.get_doc({"doctype": "Life Review", "space": PRIVATE, "user": OWNER, "kind": "Weekly", "status": "Locked", "period_start": start,
				"period_end": add_days(start, 6), "locked_on": now_datetime(), "title": "i16 review", "tab_state": "{}"}).insert(ignore_permissions=True)
		with mock.patch.object(plan, "setup_date", return_value=add_days(monday, -21)):  # set up three weeks ago: the review of 4 weeks ago is before it
			reviews = cal.year_plan(PRIVATE)["reviews"]
		self.assertEqual((reviews["done"], reviews["total"]), (2, 4))
		ticks = {w["start"]: w for w in reviews["weeks"]}
		self.assertNotIn(str(add_days(monday, -28)), ticks, "no tick for a week before setup")
		self.assertTrue(ticks[str(add_days(monday, -7))]["done"])
		self.assertFalse(ticks[str(add_days(monday, -21))]["done"] or ticks[str(add_days(monday, -21))]["future"], "a week with no review is a miss")
		self.assertTrue(ticks[str(monday)]["future"], "the week that is running is not a miss")

	# acceptance 3 of issue 100
	def test_a_site_set_up_on_23_november_says_of_1_on_the_24th(self):
		with mock.patch.object(plan, "today", return_value="2026-11-24"), mock.patch.object(plan, "setup_date", return_value=getdate("2026-11-23")):
			reviews = cal.year_plan(PRIVATE)["reviews"]
		self.assertEqual((reviews["done"], reviews["total"], reviews["since"]), (0, 1, "2026-11-23"))
		self.assertEqual(reviews["weeks"][0]["start"], "2026-11-23")

	def test_setup_is_the_day_the_guide_was_finished_else_the_first_space(self):
		frappe.defaults.clear_user_default("lifeos_onboarding", OWNER)
		first = min(getdate(c) for c in frappe.get_all("Life Space", filters={"name": ("in", list(permissions.user_spaces()))}, pluck="creation"))
		self.assertEqual(plan.setup_date(PRIVATE), first)
		frappe.defaults.set_user_default("lifeos_onboarding", "done", OWNER)
		self.assertEqual(plan.setup_date(PRIVATE), getdate(today()))
		frappe.defaults.clear_user_default("lifeos_onboarding", OWNER)

	# acceptance 1 of issue 100
	def test_four_cycles_around_today(self):
		self.cycle(start="2026-11-17")
		with mock.patch.object(plan, "today", return_value="2026-11-24"):
			out = cal.year_plan(PRIVATE)
			back = cal.year_plan(PRIVATE, shift=-1)
		self.assertEqual(out["kind"], "cycle")
		cols = out["columns"]
		self.assertEqual([c["when"] for c in cols], ["past", "current", "future", "future"])
		self.assertEqual([c["label"].split(" · ")[0] for c in cols], ["Last cycle", "This cycle", "Next cycle", "The cycle after"])
		self.assertEqual(cols[1]["label"], "This cycle · week 2")
		self.assertEqual((cols[1]["start"], cols[1]["end"]), ("2026-11-17", "2027-02-08"))
		self.assertEqual(cols[0]["end"], "2026-11-16")
		self.assertEqual(cols[2]["start"], "2027-02-15")
		self.assertEqual(cols[3]["start"], str(rules.next_monday(cols[2]["end"])))
		self.assertEqual([c["when"] for c in back["columns"]], ["past", "past", "current", "future"])
		self.assertEqual(back["columns"][2]["start"], "2026-11-17")

	# acceptance 2 of issue 100
	def test_with_no_cycle_the_columns_are_quarters(self):
		with mock.patch.object(plan, "today", return_value="2026-11-24"):
			out = cal.year_plan(PRIVATE)
			later = cal.year_plan(PRIVATE, shift=1)
		self.assertEqual(out["kind"], "quarter")
		self.assertEqual([(c["start"], c["end"]) for c in out["columns"]], [("2026-10-01", "2026-12-31"), ("2027-01-01", "2027-03-31"), ("2027-04-01", "2027-06-30"), ("2027-07-01", "2027-09-30")])
		self.assertEqual([c["label"] for c in out["columns"]][:2], ["This quarter", "Next quarter"])
		self.assertEqual(later["columns"][0]["start"], "2027-01-01")

	def test_a_goals_deadline_is_marked_and_the_score_of_a_finished_cycle_shown(self):
		cycle = self.cycle()
		goal = self.goal("i16 dated", self.life["Career"], target_date=add_days(today(), 20))
		out = cal.year_plan(PRIVATE)
		bar = next(b for b in self.lane(out, self.life["Career"])["goals"] if b["name"] == goal.name)
		self.assertEqual(bar["deadline"], str(add_days(today(), 20)))
		self.assertEqual(out["columns"][1]["cycle"], cycle.name)

	def test_key_dates_are_one_dot_a_week(self):
		soon = add_days(today(), 10)
		calendar_data.add_yearly_date(PRIVATE, "i16 Anya", getdate(soon).day, getdate(soon).month, kind="Birthday")
		for title in ("i16 trip", "i16 exam"):
			frappe.get_doc({"doctype": "Event", "subject": title, "starts_on": f"{soon} 00:00:00", "all_day": 1, "event_type": "Public", "life_space": PRIVATE}).insert()
		frappe.get_doc({"doctype": "Event", "subject": "i16 stand-up", "starts_on": f"{soon} 10:00:00", "ends_on": f"{soon} 10:30:00", "event_type": "Public", "life_space": PRIVATE}).insert()
		week = next(w for w in cal.year_plan(PRIVATE)["key_weeks"] if w["start"] == str(plan.monday_of(soon)))
		self.assertEqual(week["count"], 3)
		self.assertEqual(sorted(i["title"] for i in week["items"]), ["i16 Anya", "i16 exam", "i16 trip"])
		self.assertTrue(all(i["ref"].split(":")[0] in ("event", "date") for i in week["items"]))

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
		self.assertEqual(goals.grid(cycle=self.cycle.name, space=PRIVATE)["goals"][0]["actions"][0]["name"], goal.actions[0].name)

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
		cls.saved = (s.weekly_review_day, s.weekly_review_time)
		s.weekly_review_day, s.weekly_review_time = "Sunday", "18:00:00"
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
		s.weekly_review_day, s.weekly_review_time = cls.saved
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
		self.assertIsNotNone(rhythms.banner(PRIVATE, "2027-02-14 18:30:00"))
		today_api.skip_banner("review:2027-02-08")
		self.assertIsNone(rhythms.banner(PRIVATE, "2027-02-14 18:30:00"))
		self.assertRaises(frappe.ValidationError, today_api.skip_banner, "anything")
		self.as_user(AGENT)
		self.assertIsNone(today_api.get(space=PRIVATE, at="2027-02-14 18:30:00")["banner"])

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


class TestDashboard(LifeTestCase):
	"""Issue 123: the Today dashboard, one request for each view."""

	def setUp(self):
		super().setUp()
		self.clear()
		self.now = getdate(today())
		self.monday = add_days(self.now, -self.now.weekday())
		frappe.db.set_single_value("Life Settings", "week_starts_on", "Monday")
		frappe.db.set_single_value("Life Settings", "simple_mode", 0)
		frappe.db.sql("update `tabLife Cycle` set status='Planned' where space=%s and status='Active'", PRIVATE)  # the seeded cycle is out of the way
		self.cycle = self.make("Life Cycle", title="i123 cycle", start_date=add_days(self.monday, -21), status="Active")
		self.goal = self.make("Life Goal", title="i123 fit", cycle=self.cycle.name, area=self.areas["Tea"], horizon="12 weeks", sort_order=1,
			actions=[{"title": "Walk", "per_week": 2}], target_date=add_days(self.now, 10))
		goals.tick(self.goal.actions[0].name, 4, 1)  # this is week 4: half done
		goals.tick(self.goal.actions[0].name, 3, 2)

	def tearDown(self):
		self.clear()
		frappe.db.set_single_value("Life Settings", "simple_mode", 0)
		super().tearDown()

	def clear(self):
		frappe.set_user("Administrator")
		for dt in ("Life Proposal", "Life Inbox Item", "Life Rule", "Life Link", "Life Task", "Life Goal", "Life Cycle", "Life Habit", "Life Person"):
			frappe.db.delete(dt, {"space": PRIVATE})
		frappe.set_user(OWNER)

	def capture(self, title, status="Done", hours=1, **kw):
		return frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": title, "source_type": "Email", "status": status,
			"received_on": add_to_date(now_datetime(), hours=-hours), **kw}).insert()

	def proposal(self, item, status="Pending", **kw):
		made = frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": item.name, "kind": "Note", "preview": "x", "payload": "{}", "status": "Pending", **kw}).insert()
		if status != "Pending":
			frappe.db.set_value("Life Proposal", made.name, "status", status)  # a decision goes through review.decide; this sets what it leaves
		return made

	def seed_brain(self):
		for i in range(3):
			self.capture(f"i123 own {i}")
		changed = self.capture("i123 changed")
		self.proposal(changed, "Accepted")  # the owner accepted it: it is not filed alone
		self.capture("i123 secret", is_sensitive=1)
		asks_you = self.capture("i123 asks", status="To Review")
		self.proposal(asks_you)
		self.proposal(asks_you)
		for check in (add_days(self.now, -2), add_days(self.now, 3), self.now):
			self.make("Life Task", title=f"i123 wait {check}", status="Waiting", waiting_on="Ekta", check_by=check)
		self.make("Life Rule", made_by="Brain", enabled=1, sender="a@b.com", action="Ask", learned_from="seed")
		for i in range(2):
			self.make("Life Task", title=f"i123 done {i}", status="Done", completed_on=self.now)

	def test_week_has_the_four_cards_and_the_panels(self):  # acceptance 1
		self.seed_brain()
		top = self.make("Life Task", title="i123 top", is_top_three=1, top_three_week=self.monday, status="Open", due_date=add_days(self.now, 2))
		self.make("Life Habit", title="i123 walk", days_per_week=7, tracked_from=add_days(self.now, -30))
		out = dash.get("week", space=PRIVATE)
		cards = {c["key"]: c for c in out["cards"]}
		self.assertEqual(list(cards), ["score", "needs", "waiting", "filed"])
		self.assertEqual(len(out["panels"]), 2)
		self.assertEqual(cards["score"]["value"], "50%")
		self.assertIn("target 85%", cards["score"]["sub"])
		self.assertIn("last week 100%", cards["score"]["sub"])
		self.assertEqual((cards["needs"]["value"], cards["needs"]["open"]), (2, "list:needs-you"))
		self.assertEqual((cards["waiting"]["value"], cards["waiting"]["parts"][0]["text"], cards["waiting"]["parts"][0]["open"]), (3, "1 late", "list:waiting-overdue"))
		self.assertEqual(cards["filed"]["value"], "67%")  # 4 of the 6 the Brain finished with: the changed one and the one asking are not alone
		line = {p["open"]: p["text"] for p in out["brain_line"]["parts"]}
		self.assertEqual(line["list:came-in"], "6 came in")
		self.assertEqual(line["list:filed-alone"], "4 filed alone")  # the sensitive one is counted, as the Activity list counts it
		self.assertEqual(line["list:needs-you"], "1 to you")
		self.assertEqual(line["list:rules"], "1 rules learned")
		goals_panel, coming = out["panels"]
		self.assertEqual(goals_panel["groups"][0]["rows"][0]["ref"], f"goal:{self.goal.name}")
		self.assertEqual(coming["habits"][0]["title"], "i123 walk")
		self.assertIn(f"task:{top.name}", [r["ref"] for r in coming["rows"]])
		self.assertEqual(coming["more"], 0)

	def test_coming_up_is_six_lines_and_the_rest_counted(self):
		for i in range(9):
			self.make("Life Task", title=f"i123 due {i}", status="Open", due_date=add_days(self.now, 1 + i % 5))
		coming = dash.get("week", space=PRIVATE)["panels"][1]
		self.assertEqual((len(coming["rows"]), coming["more"]["n"]), (6, 3))

	def test_the_lists_hold_what_the_numbers_count(self):
		self.seed_brain()
		needs = dash.list("needs-you", "week", space=PRIVATE)["rows"]
		self.assertEqual(len(needs), 2)
		past = dash.list("waiting-overdue", "week", space=PRIVATE)["rows"]
		self.assertEqual(len(past), 1)
		self.assertEqual(len(dash.list("waiting", "week", space=PRIVATE)["rows"]), 3)
		self.assertEqual(len(dash.list("waiting-due", "day", space=PRIVATE)["rows"]), 2)  # check-by today or past
		self.assertEqual(len(dash.list("rules", "week", space=PRIVATE)["rules"]), 1)
		filed = dash.list("filed-alone", "week", space=PRIVATE)["rows"]
		self.assertEqual(len(filed), 4)
		self.assertTrue(all(r["ref"].startswith("inbox:") for r in filed))
		self.assertEqual(len(dash.list("done", "week", space=PRIVATE)["rows"]), 2)
		self.assertRaises(frappe.ValidationError, dash.list, "nonsense", "week", space=PRIVATE)

	def test_a_sensitive_item_is_counted_and_never_named(self):
		self.capture("i123 payslip", is_sensitive=1)
		rows = dash.list("filed-alone", "week", space=PRIVATE)["rows"]
		self.assertEqual([r["title"] for r in rows], ["A sensitive item"])
		self.assertNotIn("payslip", frappe.as_json(dash.get("week", space=PRIVATE)))

	def test_filed_alone_compares_with_the_month_before(self):
		last_month = getdate(add_days(self.now.replace(day=1), -3))
		for i in range(2):
			self.capture(f"i123 old {i}", received_on=f"{last_month} 10:00:00")
		self.proposal(self.capture("i123 old changed", received_on=f"{last_month} 10:00:00"), "Accepted")
		self.capture("i123 now")
		sub = {c["key"]: c for c in dash.get("week", space=PRIVATE)["cards"]}["filed"]["sub"]
		self.assertEqual(sub, "up from 67% in " + dash.SHORT[last_month.month - 1])

	def test_day_month_and_year_have_their_cards_and_panels(self):  # acceptance 2
		self.seed_brain()
		self.make("Life Task", title="i123 top", is_top_three=1, top_three_week=self.monday, status="Done", completed_on=self.now)
		day = dash.get("day", space=PRIVATE)
		self.assertEqual([c["key"] for c in day["cards"]], ["top", "needs", "check", "habits"])
		self.assertEqual([p["key"] for p in day["panels"]], ["schedule", "top"])
		self.assertEqual(day["cards"][0]["value"], "1 of 3")
		self.assertEqual(day["cards"][2]["value"], 2)
		month = dash.get("month", space=PRIVATE)
		self.assertEqual([c["key"] for c in month["cards"]], ["score", "plan", "due", "filed"])
		self.assertEqual([p["key"] for p in month["panels"]], ["weeks", "key-dates"])
		self.assertTrue(any(r["accent"] for r in month["panels"][0]["rows"]))  # the current week
		year = dash.get("year", space=PRIVATE)
		self.assertEqual([c["key"] for c in year["cards"]], ["year-goals", "cycle", "reviews", "filed"])
		self.assertEqual([p["key"] for p in year["panels"]], ["goals", "cycles"])
		self.assertEqual(year["cards"][1]["sub"], "week 4 of 12")
		self.assertEqual(year["panels"][1]["rows"][0]["ref"], f"list:cycle:{self.cycle.name}")
		self.assertEqual(len(dash.list(f"cycle:{self.cycle.name}", "year", space=PRIVATE)["rows"]), 1)
		self.assertEqual(dash.list(f"week-work:{self.monday}", "month", space=PRIVATE)["title"], f"Week of {dash._short(self.monday)}")

	def test_a_task_planned_at_a_time_is_on_the_days_schedule(self):
		self.make("Life Task", title="i123 planned", status="Open", scheduled_at=f"{self.now} 09:30:00", duration_min=30)
		rows = dash.get("day", space=PRIVATE)["panels"][0]["rows"]
		hit = [r for r in rows if r["title"] == "i123 planned"]
		self.assertEqual(len(hit), 1, "a task scheduled today is part of the day's schedule, as on the old timeline")
		self.assertEqual(hit[0]["at"], "09:30")
		self.assertTrue(hit[0]["ref"].startswith("task:"))

	def test_with_goals_off_other_cards_take_their_place(self):  # acceptance 3
		self.seed_brain()
		frappe.db.set_single_value("Life Settings", "simple_mode", 1)
		person = frappe.get_doc({"doctype": "Life Person", "space": PRIVATE, "full_name": "Ekta Jalan", "kind": "Person"}).insert()
		mail = self.capture("i123 mail")
		for dt, name in (("Life Inbox Item", mail.name), ("Life Task", self.make("Life Task", title="i123 t", status="Open").name)):
			self.make("Life Link", from_doctype=dt, from_name=name, to_doctype="Life Person", to_name=person.name, link_text="x", origin="Brain")
		week = dash.get("week", space=PRIVATE)
		self.assertTrue(week["simple"])
		self.assertEqual([c["key"] for c in week["cards"]], ["done", "needs", "waiting", "filed"])
		self.assertEqual(week["cards"][0]["value"], 2)
		self.assertEqual(week["panels"][0]["key"], "active")
		self.assertEqual((week["panels"][0]["rows"][0]["title"], week["panels"][0]["rows"][0]["sub"]), ("Ekta Jalan", "1 email · 1 task"))
		for view in dash.VIEWS:
			out = dash.get(view, space=PRIVATE)
			self.assertNotRegex(frappe.as_json(out).lower(), r"goal|score|top three|cycle", view)
		self.assertEqual([c["key"] for c in dash.get("day", space=PRIVATE)["cards"]], ["plate", "needs", "check"])  # no habits: no Habits card
		self.make("Life Habit", title="i123 walk", days_per_week=7, tracked_from=add_days(self.now, -30))
		self.assertEqual([c["key"] for c in dash.get("day", space=PRIVATE)["cards"]][-1], "habits")
		self.assertEqual([c["key"] for c in dash.get("month", space=PRIVATE)["cards"]], ["done", "active", "keys", "filed"])
		self.assertEqual([c["key"] for c in dash.get("year", space=PRIVATE)["cards"]], ["done", "reviews", "needs", "filed"])
		self.assertEqual([p["key"] for p in dash.get("year", space=PRIVATE)["panels"]], ["active", "filed-months"])

	def test_an_empty_space_says_what_will_appear_and_offers_one_action(self):  # acceptance 9
		self.clear()
		for view in dash.VIEWS:
			out = dash.get(view, space=PRIVATE)
			self.assertTrue(out["new"])
			for c in out["cards"]:
				if c["key"] == "habits" or c["value"] is None or c["value"] == 0:
					self.assertTrue(c["empty"] and c["empty"]["line"] and c["empty"]["action"] and c["empty"]["to"], f"{view} {c['key']}")
		simple = frappe.db.set_single_value("Life Settings", "simple_mode", 1)
		self.assertTrue(dash.get("week", space=PRIVATE)["cards"][0]["empty"]["action"])

	def test_the_dashboard_is_for_people_and_reads_a_bounded_number_of_queries(self):
		self.seed_brain()
		for view in dash.VIEWS:
			with self.assertQueryCount(90):
				dash.get(view, space=PRIVATE)
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, dash.get, "week", space=PRIVATE)
