import frappe
from frappe.utils import add_days, getdate, today

from lifeos import journal as rules
from lifeos.api import journal
from lifeos.api import today as today_api
from lifeos.tests.base import AGENT, FAMILY, PRIVATE, SHARED, LifeTestCase


class JournalCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		# each test starts with no active cycle in the test space
		frappe.db.sql("update `tabLife Cycle` set status='Planned' where space=%s and status='Active'", PRIVATE)

	def make_cycle(self, start=None, status="Planned", title="Test cycle", goals=None):
		cycle = self.make("Life Cycle", title=title, start_date=start or add_days(today(), -21), status=status)
		made = []
		for i, (gtitle, actions) in enumerate(goals or []):
			made.append(self.make("Life Goal", cycle=cycle.name, title=gtitle, sort_order=i + 1, area=self.areas["Tea"],
				actions=[{"title": t, "per_week": n} for t, n in actions]))
		return cycle, made


class TestWeekScore(JournalCase):
	def test_single_and_multi_count_actions(self):
		cycle, (goal,) = self.make_cycle(goals=[("Fit", [("Walk", 1), ("Workout", 3), ("Stretch", 1)])])
		walk, workout, stretch = [a.name for a in goal.actions]
		self.assertEqual(journal.week_score(cycle.name, 1)["percent"], 0)
		out = journal.tick(walk, 1, 1)
		self.assertEqual((out["done"], out["planned"], out["percent"]), (1, 5, 20.0))
		out = journal.tick(workout, 1, 2)
		self.assertEqual((out["done"], out["planned"]), (3, 5))
		out = journal.tick(workout, 1, 9)  # never more than per_week
		self.assertEqual((out["done"], out["percent"]), (4, 80.0))
		out = journal.tick(walk, 1, 0)  # untick
		self.assertEqual(out["done"], 3)
		self.assertEqual(journal.week_score(cycle.name, 2)["done"], 0)

	def test_ticks_are_dated_rows(self):
		cycle, (goal,) = self.make_cycle(goals=[("Fit", [("Workout", 3)])])
		action = goal.actions[0].name
		journal.tick(action, 4, 2)  # the current week: cycle started 21 days ago
		row = frappe.get_all("Life Action Log", filters={"action_id": action}, fields=["week", "date", "count", "cycle", "goal"])
		self.assertEqual(len(row), 1)
		self.assertEqual((row[0].week, row[0].count, str(row[0].date), row[0].goal), (4, 2, today(), goal.name))
		journal.tick(action, 2, 1)
		past = frappe.db.get_value("Life Action Log", {"action_id": action, "week": 2}, "date")
		start, end = rules.week_dates(cycle, 2)
		self.assertTrue(start <= getdate(past) <= end)
		goal.reload()
		self.assertEqual(goal.actions[0].ticks, "3")

	def test_dropped_action_is_not_planned(self):
		cycle, (goal,) = self.make_cycle(goals=[("Loops", [("A", 1), ("B", 1)])])
		a, b = [x.name for x in goal.actions]
		journal.tick(a, 1, 1)
		self.assertEqual(journal.week_score(cycle.name, 1)["percent"], 50.0)
		journal.set_action_status(b, "Dropped")
		score = journal.week_score(cycle.name, 1)
		self.assertEqual((score["done"], score["planned"], score["percent"]), (1, 1, 100.0))

	def test_action_done_early_stops_counting(self):
		cycle, (goal,) = self.make_cycle(goals=[("Loops", [("Anya passport", 1), ("Ruchi ITR", 1)])])
		passport, itr = [x.name for x in goal.actions]
		journal.set_action_status(passport, "Done")  # in week 4
		self.assertTrue(frappe.db.exists("Life Action Log", {"action_id": passport, "week": 4}))
		self.assertEqual(journal.week_score(cycle.name, 3)["planned"], 2)  # still planned before it was finished
		self.assertEqual(journal.week_score(cycle.name, 4)["planned"], 2)
		self.assertEqual(journal.week_score(cycle.name, 4)["done"], 1)
		self.assertEqual(journal.week_score(cycle.name, 5)["planned"], 1)  # no longer planned
		self.assertEqual(journal.week_score(cycle.name, 12)["planned"], 1)
		grid = journal.grid(cycle.name)
		action = grid["goals"][0]["actions"][0]
		self.assertEqual((action["status"], action["done_week"]), ("Done", 4))

	def test_grid_average_and_goal_percent(self):
		cycle, (g1, g2) = self.make_cycle(goals=[("One", [("A", 1)]), ("Two", [("B", 1)])])
		a, b = g1.actions[0].name, g2.actions[0].name
		for week in (1, 2, 3, 4):
			journal.tick(a, week, 1)
		journal.tick(b, 4, 1)
		grid = journal.grid(cycle.name)
		self.assertEqual(grid["current_week"], 4)
		self.assertEqual([w["percent"] for w in grid["weeks"][:4]], [50.0, 50.0, 50.0, 100.0])
		self.assertEqual(grid["average"], 62.5)
		self.assertEqual([g["percent"] for g in grid["goals"]], [100.0, 25.0])
		self.assertEqual(grid["weeks_left"], 8)

	def test_permissions(self):
		cycle, (goal,) = self.make_cycle(goals=[("Fit", [("Walk", 1)])])
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, journal.tick, goal.actions[0].name, 1, 1)
		self.assertRaises(frappe.PermissionError, journal.grid, cycle.name)
		self.assertRaises(frappe.PermissionError, journal.week_score, cycle.name, 1)
		self.as_user(AGENT)
		self.assertEqual(journal.tick(goal.actions[0].name, 1, 1)["done"], 1)


class TestCycles(JournalCase):
	def test_close_cycle_stores_outcomes_and_locks(self):
		cycle, (g1, g2) = self.make_cycle(start=add_days(today(), -90), status="Active", goals=[("One", [("A", 1)]), ("Two", [("B", 1)])])
		for week in range(1, 13):
			journal.tick(g1.actions[0].name, week, 1)
		out = journal.close_cycle(cycle.name, outcomes=[{"goal": g1.name, "outcome": "Achieved", "result_note": "Did it"},
			{"goal": g2.name, "outcome": "Not Achieved"}])
		self.assertEqual(out["final_score"], 50.0)
		cycle.reload()
		g1.reload()
		g2.reload()
		self.assertEqual((cycle.status, str(cycle.closed_on)), ("Closed", today()))
		self.assertEqual((g1.outcome, g1.result_note, g1.final_score), ("Achieved", "Did it", 100.0))
		self.assertEqual((g2.outcome, g2.final_score), ("Not Achieved", 0.0))
		# closed cycles are read-only
		self.assertRaises(frappe.ValidationError, journal.tick, g1.actions[0].name, 3, 0)
		g1.title = "Changed"
		self.assertRaises(frappe.ValidationError, g1.save)
		cycle.title = "Changed"
		self.assertRaises(frappe.ValidationError, cycle.save)
		self.assertRaises(frappe.ValidationError, journal.save_goal, cycle=cycle.name, title="Late goal")
		self.assertRaises(frappe.ValidationError, journal.close_cycle, cycle.name)

	def test_cannot_close_before_the_end_date(self):
		cycle, _ = self.make_cycle(status="Active", goals=[("One", [("A", 1)])])
		self.assertRaises(frappe.ValidationError, journal.close_cycle, cycle.name)

	def test_plan_next_cycle_copies_only_chosen_goals_with_open_actions(self):
		cycle, (keep, leave) = self.make_cycle(start="2026-10-05", status="Active", goals=[
			("GHL turnaround", [("Visit gardens", 1), ("Plan sections", 2), ("Old step", 1), ("Dropped step", 1)]), ("Golf", [("Putt", 1)])])
		journal.set_action_status(keep.actions[2].name, "Done")
		journal.set_action_status(keep.actions[3].name, "Dropped")
		out = journal.plan_next_cycle(cycle.name, goals=[keep.name])
		new = frappe.get_doc("Life Cycle", out["cycle"])
		self.assertEqual((str(new.start_date), new.status, new.title), ("2026-12-28", "Planned", "Dec to Mar 2027"))
		self.assertEqual(getdate(new.start_date).weekday(), 0)
		goals = frappe.get_all("Life Goal", filters={"cycle": new.name}, fields=["name", "title", "carried_from", "area"])
		self.assertEqual([(g.title, g.carried_from) for g in goals], [("GHL turnaround", keep.name)])
		copy = frappe.get_doc("Life Goal", goals[0].name)
		self.assertEqual([(a.title, a.per_week, a.status) for a in copy.actions], [("Visit gardens", 1, "Open"), ("Plan sections", 2, "Open")])
		self.assertEqual(frappe.db.get_value("Life Goal", keep.name, "outcome"), "Carried")
		self.assertEqual(frappe.db.get_value("Life Goal", leave.name, "outcome"), "In Progress")
		again = journal.plan_next_cycle(cycle.name, goals=[keep.name])  # no duplicates
		self.assertEqual((again["cycle"], again["carried"]), (new.name, []))

	def test_goal_history_follows_the_chain_across_three_cycles(self):
		frappe.flags.lifeos_allow_early_close = True
		c1, (g1,) = self.make_cycle(start="2026-01-05", status="Active", title="C1", goals=[("Long goal", [("Step", 1)])])
		for week in (1, 2, 3):
			journal.tick(g1.actions[0].name, week, 1)
		n2 = journal.plan_next_cycle(c1.name, goals=[g1.name])
		journal.close_cycle(c1.name, outcomes=[{"goal": g1.name, "outcome": "Carried"}])
		journal.start_cycle(n2["cycle"])
		g2 = frappe.get_doc("Life Goal", n2["carried"][0])
		for week in range(1, 7):
			journal.tick(g2.actions[0].name, week, 1)
		n3 = journal.plan_next_cycle(n2["cycle"], goals=[g2.name])
		journal.close_cycle(n2["cycle"], outcomes=[{"goal": g2.name, "outcome": "Carried"}])
		g3 = n3["carried"][0]
		for start_from in (g1.name, g2.name, g3):
			history = journal.goal(start_from)["history"]
			self.assertEqual([h["name"] for h in history], [g1.name, g2.name, g3])
			self.assertEqual([h["outcome"] for h in history], ["Carried", "Carried", "In Progress"])
			self.assertEqual([h["score"] for h in history[:2]], [25.0, 50.0])

	def test_goals_tab_groups_by_cycle(self):
		frappe.flags.lifeos_allow_early_close = True
		old, _ = self.make_cycle(start="2025-07-07", status="Active", title="Old", goals=[("Old goal", [("A", 1)])])
		journal.close_cycle(old.name)
		active, (ag,) = self.make_cycle(status="Active", title="Now", goals=[("Now goal", [("A", 1)])])
		journal.plan_next_cycle(active.name, goals=[ag.name])
		data = journal.goals(space=PRIVATE)
		mine = [c for c in data["cycles"] if c["title"] in ("Old", "Now") or c["goals"] and c["goals"][0].get("carried_from") == ag.name]
		self.assertEqual([c["status"] for c in mine], ["Planned", "Active", "Closed"])
		now = next(c for c in data["cycles"] if c["title"] == "Now")
		self.assertEqual((now["goals"][0]["actions"], now["goals"][0]["outcome"], now["goals"][0]["area_name"]), (1, "Carried", "Tea"))
		filtered = journal.goals(space=PRIVATE, area=self.areas["Money"])
		self.assertEqual([g for c in filtered["cycles"] for g in c["goals"]], [])


class TestMonthAndHabits(JournalCase):
	def setUp(self):
		super().setUp()
		for name in frappe.get_all("Life Month Plan", filters={"space": PRIVATE}, pluck="name"):
			frappe.delete_doc("Life Month Plan", name, force=True)
		frappe.db.delete("Life Habit Log", {"space": PRIVATE})

	def test_carry_month_goal(self):
		itr = rules.add_month_goal(PRIVATE, 2030, 12, "Ruchi ITR", self.areas["Money"])
		done = rules.add_month_goal(PRIVATE, 2030, 12, "Done thing")
		frappe.db.set_value("Life Goal", done.name, "outcome", "Achieved")
		out = rules.carry_month_goal(itr.name)
		self.assertEqual((out["year"], out["month"]), (2031, 1))
		self.assertEqual(frappe.db.get_value("Life Goal", itr.name, "outcome"), "Carried")
		row = frappe.get_doc("Life Goal", out["row"])
		self.assertEqual((row.title, row.horizon, row.outcome, row.area, row.carried_from), ("Ruchi ITR", "Month", "In Progress", self.areas["Money"], itr.name))
		self.assertEqual([g["row"] for g in rules.month_goals(PRIVATE, 2031, 1)], [row.name])
		self.assertRaises(frappe.ValidationError, rules.carry_month_goal, itr.name)
		self.assertRaises(frappe.ValidationError, rules.carry_month_goal, done.name)

	def test_make_task_from_goal(self):
		plan = self.make("Life Month Plan", year=2030, month=6)
		goal = rules.add_month_goal(PRIVATE, 2030, 6, "Accounts flow in ERP", self.areas["Tea"])
		out = journal.make_task_from_goal(plan.name, goal.name)
		task = frappe.get_doc("Life Task", out["task"])
		self.assertEqual((task.title, task.goal, task.month_plan, task.area), ("Accounts flow in ERP", goal.name, plan.name, self.areas["Tea"]))
		self.assertTrue(journal.make_task_from_goal(plan.name, goal.name)["existing"])

	def test_new_plan_copies_last_months_habits(self):
		japa, workout = self.make("Life Habit", title="Japa t"), self.make("Life Habit", title="Workout t")
		self.make("Life Month Plan", year=2031, month=5, habits=[{"habit": japa.name, "days_per_week": 7}, {"habit": workout.name, "days_per_week": 5}])
		june = rules.get_month_plan(PRIVATE, 2031, 6, create=True)
		self.assertEqual([(h.habit, h.days_per_week, str(h.tracked_from)) for h in june.habits],
			[(japa.name, 7, "2031-06-01"), (workout.name, 5, "2031-06-01")])

	def test_removing_a_habit_leaves_earlier_months_unchanged(self):
		japa, mala = self.make("Life Habit", title="Japa r"), self.make("Life Habit", title="Mala r")
		self.make("Life Month Plan", year=2031, month=10, habits=[{"habit": japa.name}, {"habit": mala.name}])
		self.make("Life Habit Log", habit=mala.name, date="2031-10-03")
		journal.set_month_habits(space=PRIVATE, year=2031, month=11, habits=[{"habit": japa.name}])
		november = journal.habits(space=PRIVATE, year=2031, month=11)
		october = journal.habits(space=PRIVATE, year=2031, month=10)
		self.assertEqual([h["habit"] for h in november["habits"]], [japa.name])
		self.assertEqual([h["habit"] for h in october["habits"]], [japa.name, mala.name])
		self.assertEqual(next(h for h in october["habits"] if h["habit"] == mala.name)["done_days"], [3])
		december = rules.get_month_plan(PRIVATE, 2031, 12, create=True)
		self.assertEqual([h.habit for h in december.habits], [japa.name])

	def test_days_outside_the_tracked_period_are_not_missed(self):
		now = getdate(today())
		if now.day < 4:
			self.skipTest("needs a few elapsed days in the month")
		old, added = self.make("Life Habit", title="Old habit"), self.make("Life Habit", title="Added today")
		self.make("Life Month Plan", year=now.year, month=now.month, habits=[{"habit": old.name, "tracked_from": now.replace(day=1)}])
		journal.set_month_habits(space=PRIVATE, year=now.year, month=now.month, habits=[{"habit": old.name}, {"habit": added.name}])
		journal.toggle_habit(added.name, str(now))
		data = {h["habit"]: h for h in journal.habits(space=PRIVATE, year=now.year, month=now.month)["habits"]}
		self.assertEqual((data[added.name]["tracked_days"], data[added.name]["done"], data[added.name]["percent"]), (1, 1, 100))
		self.assertEqual((data[old.name]["tracked_days"], data[old.name]["done"], data[old.name]["percent"]), (now.day, 0, 0))
		# removed mid-month: days after removal are not counted, earlier days stay
		journal.toggle_habit(old.name, str(now.replace(day=1)))
		journal.set_month_habits(space=PRIVATE, year=now.year, month=now.month, habits=[{"habit": added.name}])
		data = {h["habit"]: h for h in journal.habits(space=PRIVATE, year=now.year, month=now.month)["habits"]}
		self.assertTrue(data[old.name]["removed"])
		self.assertEqual((data[old.name]["tracked_days"], data[old.name]["done"]), (now.day - 1, 1))
		from lifeos.api import today as today_api
		self.assertEqual([h["habit"] for h in today_api.get(space=PRIVATE)["habits"]], [added.name])

	def test_days_per_week_changes_the_percentage(self):
		daily, five = self.make("Life Habit", title="Daily"), self.make("Life Habit", title="Five a week")
		self.make("Life Month Plan", year=2025, month=2, habits=[{"habit": daily.name, "days_per_week": 7}, {"habit": five.name, "days_per_week": 5}])
		for day in range(1, 21):
			for h in (daily, five):
				self.make("Life Habit Log", habit=h.name, date=f"2025-02-{day:02d}")
		data = {h["habit"]: h for h in journal.habits(space=PRIVATE, year=2025, month=2)["habits"]}
		self.assertEqual((data[daily.name]["done"], data[daily.name]["target"], data[daily.name]["percent"]), (20, 28, 71))
		self.assertEqual((data[five.name]["done"], data[five.name]["target"], data[five.name]["percent"]), (20, 20, 100))
		year = journal.habits_year(space=PRIVATE, year=2025)
		self.assertEqual({h["title"]: h["months"]["2"]["percent"] for h in year["habits"]}, {"Daily": 71, "Five a week": 100})
		self.assertEqual(list(year["habits"][0]["months"]), ["2"])

	def test_toggle_habit_and_permissions(self):
		habit = self.make("Life Habit", title="Toggle me")
		self.assertTrue(journal.toggle_habit(habit.name, "2026-11-10")["done"])
		self.assertTrue(frappe.db.exists("Life Habit Log", {"habit": habit.name, "date": "2026-11-10"}))
		self.assertFalse(journal.toggle_habit(habit.name, "2026-11-10")["done"])
		self.assertFalse(frappe.db.exists("Life Habit Log", {"habit": habit.name, "date": "2026-11-10"}))
		# a day that has not come cannot be ticked
		self.assertRaises(frappe.ValidationError, journal.toggle_habit, habit.name, frappe.utils.add_days(frappe.utils.today(), 1))
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, journal.toggle_habit, habit.name, "2026-11-10")
		self.assertRaises(frappe.PermissionError, journal.habits, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, journal.set_month_habits, space=PRIVATE, year=2026, month=11, habits=[])


class TestCheckinsPagesReview(JournalCase):
	def test_check_in_ranges_and_series(self):
		dims = frappe.get_all("Life Dimension", filters={"space": PRIVATE}, fields=["name", "dimension_name"], order_by="sort_order")
		self.assertEqual(len(dims), 8)
		out = journal.save_checkin(space=PRIVATE, date="2026-11-01", reflection_md="A steady week", scores=[
			{"dimension": dims[0].name, "habits": "2-3", "situation": "7", "note": "sleep"}, {"dimension": dims[1].name, "habits": 6, "situation": "4 to 5"},
			{"dimension": dims[2].name, "habits": "", "situation": ""}])
		self.assertEqual(len(out["scores"]), 2)
		s = out["scores"][0]
		self.assertEqual((s["habits_low"], s["habits_high"], s["situation_low"], s["situation_high"], s["note"]), (2, 3, 7, 7, "sleep"))
		self.assertEqual((out["scores"][1]["situation_low"], out["scores"][1]["situation_high"]), (4, 5))
		self.assertRaises(frappe.ValidationError, journal.save_checkin, space=PRIVATE, date="2026-11-02", scores=[{"dimension": dims[0].name, "habits": "12"}])
		self.assertRaises(frappe.ValidationError, journal.save_checkin, space=PRIVATE, date="2026-11-02", scores=[{"dimension": dims[0].name, "habits": "lots"}])
		journal.save_checkin(space=PRIVATE, date="2026-11-08", scores=[{"dimension": dims[0].name, "habits": "4-5", "situation": 8}])
		data = journal.checkins(space=PRIVATE)
		series = next(x for x in data["series"] if x["dimension"] == dims[0].name)
		mine = [p for p in series["points"] if p["date"] in ("2026-11-01", "2026-11-08")]
		self.assertEqual(mine, [{"date": "2026-11-01", "habits": 2.5, "situation": 7.0}, {"date": "2026-11-08", "habits": 4.5, "situation": 8.0}])
		edited = journal.save_checkin(name=out["name"], date="2026-11-01", scores=[{"dimension": dims[0].name, "habits": 9, "situation": 9}])
		self.assertEqual(edited["scores"][0]["habits_low"], 9)

	def test_pages_and_transcript(self):
		page = self.make("Life Journal Page", page_date="2026-11-14", page_number="187", transcript_md="Goal Oct to Dec [?]")
		self.assertIn(page.name, [p["name"] for p in journal.pages(space=PRIVATE)["pages"]])
		journal.save_page_transcript(page.name, "Goal Oct to Dec")
		self.assertEqual(journal.page_detail(page.name)["transcript_md"], "Goal Oct to Dec")
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, journal.page_detail, page.name)

	def test_weekly_review_gathers_the_week(self):
		now = getdate(today())
		monday = add_days(now, -now.weekday())
		cycle, (goal,) = self.make_cycle(start=add_days(monday, -7), status="Active", goals=[("Fit", [("Walk", 1), ("Run", 1)])])
		journal.tick(goal.actions[0].name, 2, 1)
		done = self.make("Life Task", title="Done this week")
		done.status = "Done"
		done.save()
		stale = self.make("Life Task", title="Stale open task")
		frappe.db.set_value("Life Task", stale.name, "last_touched_on", add_days(now, -200), update_modified=False)
		data = journal.weekly_review(space=PRIVATE)
		self.assertEqual((data["week_start"], data["week_end"]), (str(monday), str(add_days(monday, 6))))
		self.assertEqual((data["cycle"]["week"], data["cycle"]["percent"]), (2, 50.0))
		self.assertIn(done.name, [t["name"] for t in data["done"]])
		self.assertIn(stale.name, [t["name"] for t in data["decide"]])
		saved = journal.save_review_note(space=PRIVATE, week_start=str(monday), content_md="Good week.")
		note = frappe.get_doc("Life Note", saved["note"])
		self.assertEqual(frappe.db.get_value("Life Note", note.parent_note, "title"), "Reviews")
		journal.save_review_note(space=PRIVATE, week_start=str(monday), content_md="Good week. Updated.")
		self.assertEqual(frappe.db.count("Life Note", {"space": PRIVATE, "title": saved["title"]}), 1)
		self.assertEqual(journal.weekly_review(space=PRIVATE)["note"]["content_md"], "Good week. Updated.")
		from lifeos.api import tasks
		self.assertEqual(tasks.decide_stale(stale.name, "drop")["status"], "Dropped")


class TestTodayThisWeek(JournalCase):
	def test_today_lists_this_weeks_actions_and_a_tick_moves_the_score(self):
		cycle, (goal,) = self.make_cycle(status="Active", goals=[("Fit", [("Walk", 1), ("Workout", 3), ("Dropped one", 1)])])
		walk, workout, dropped = goal.actions
		journal.set_action_status(dropped.name, "Dropped")
		data = today_api.get(space=PRIVATE)["cycle"]
		self.assertEqual(data["week"], 4)
		acts = {a["name"]: a for a in data["actions"]}
		self.assertEqual(set(acts), {walk.name, workout.name})
		self.assertEqual((acts[workout.name]["per_week"], acts[workout.name]["count"], acts[workout.name]["goal_title"]), (3, 0, "Fit"))
		journal.tick(workout.name, 4, 2)
		data = today_api.get(space=PRIVATE)["cycle"]
		self.assertEqual({a["name"]: a["count"] for a in data["actions"]}[workout.name], 2)
		self.assertEqual((data["done"], data["planned"]), (2, 4))
