"""Tests for goals."""
import json
import os
import types

import frappe
from frappe.utils import add_days, add_months, getdate, today

from lifeos import areas, cycles as rules, focus_defaults, old_inbox, readings
from lifeos import habits as habit_rules
from lifeos.ai import fake
from lifeos.api import area, focus, goals, inbox, library, links, reset, review, search, settings, someday, tasks, timeline, today as today_api, vault, weekly
from lifeos.life.doctype.life_goal.life_goal import derive_horizon
from lifeos.review import stale
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import item, set_key, task, text


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
		self.assertEqual(goals.week_score(cycle.name, 1)["percent"], 0)
		out = goals.tick(walk, 1, 1)
		self.assertEqual((out["done"], out["planned"], out["percent"]), (1, 5, 20.0))
		out = goals.tick(workout, 1, 2)
		self.assertEqual((out["done"], out["planned"]), (3, 5))
		out = goals.tick(workout, 1, 9)  # never more than per_week
		self.assertEqual((out["done"], out["percent"]), (4, 80.0))
		out = goals.tick(walk, 1, 0)  # untick
		self.assertEqual(out["done"], 3)
		self.assertEqual(goals.week_score(cycle.name, 2)["done"], 0)

	def test_ticks_are_dated_rows(self):
		cycle, (goal,) = self.make_cycle(goals=[("Fit", [("Workout", 3)])])
		action = goal.actions[0].name
		goals.tick(action, 4, 2)  # the current week: cycle started 21 days ago
		row = frappe.get_all("Life Action Log", filters={"action_id": action}, fields=["week", "date", "count", "cycle", "goal"])
		self.assertEqual(len(row), 1)
		self.assertEqual((row[0].week, row[0].count, str(row[0].date), row[0].goal), (4, 2, today(), goal.name))
		goals.tick(action, 2, 1)
		past = frappe.db.get_value("Life Action Log", {"action_id": action, "week": 2}, "date")
		start, end = rules.week_dates(cycle, 2)
		self.assertTrue(start <= getdate(past) <= end)
		goal.reload()
		self.assertEqual(goal.actions[0].ticks, "3")

	def test_dropped_action_is_not_planned(self):
		cycle, (goal,) = self.make_cycle(goals=[("Loops", [("A", 1), ("B", 1)])])
		a, b = [x.name for x in goal.actions]
		goals.tick(a, 1, 1)
		self.assertEqual(goals.week_score(cycle.name, 1)["percent"], 50.0)
		goals.set_action_status(b, "Dropped")
		score = goals.week_score(cycle.name, 1)
		self.assertEqual((score["done"], score["planned"], score["percent"]), (1, 1, 100.0))

	def test_action_done_early_stops_counting(self):
		cycle, (goal,) = self.make_cycle(goals=[("Loops", [("Anya passport", 1), ("Ruchi ITR", 1)])])
		passport, itr = [x.name for x in goal.actions]
		goals.set_action_status(passport, "Done")  # in week 4
		self.assertTrue(frappe.db.exists("Life Action Log", {"action_id": passport, "week": 4}))
		self.assertEqual(goals.week_score(cycle.name, 3)["planned"], 2)  # still planned before it was finished
		self.assertEqual(goals.week_score(cycle.name, 4)["planned"], 2)
		self.assertEqual(goals.week_score(cycle.name, 4)["done"], 1)
		self.assertEqual(goals.week_score(cycle.name, 5)["planned"], 1)  # no longer planned
		self.assertEqual(goals.week_score(cycle.name, 12)["planned"], 1)
		grid = goals.grid(cycle.name)
		action = grid["goals"][0]["actions"][0]
		self.assertEqual((action["status"], action["done_week"]), ("Done", 4))

	def test_grid_average_and_goal_percent(self):
		cycle, (g1, g2) = self.make_cycle(goals=[("One", [("A", 1)]), ("Two", [("B", 1)])])
		a, b = g1.actions[0].name, g2.actions[0].name
		for week in (1, 2, 3, 4):
			goals.tick(a, week, 1)
		goals.tick(b, 4, 1)
		grid = goals.grid(cycle.name)
		self.assertEqual(grid["current_week"], 4)
		self.assertEqual([w["percent"] for w in grid["weeks"][:4]], [50.0, 50.0, 50.0, 100.0])
		self.assertEqual(grid["average"], 62.5)
		self.assertEqual([g["percent"] for g in grid["goals"]], [100.0, 25.0])
		self.assertEqual(grid["weeks_left"], 8)

	def test_permissions(self):
		cycle, (goal,) = self.make_cycle(goals=[("Fit", [("Walk", 1)])])
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, goals.tick, goal.actions[0].name, 1, 1)
		self.assertRaises(frappe.PermissionError, goals.grid, cycle.name)
		self.assertRaises(frappe.PermissionError, goals.week_score, cycle.name, 1)
		self.as_user(AGENT)
		self.assertEqual(goals.tick(goal.actions[0].name, 1, 1)["done"], 1)


class TestCycles(JournalCase):
	def test_close_cycle_stores_outcomes_and_locks(self):
		cycle, (g1, g2) = self.make_cycle(start=add_days(today(), -90), status="Active", goals=[("One", [("A", 1)]), ("Two", [("B", 1)])])
		for week in range(1, 13):
			goals.tick(g1.actions[0].name, week, 1)
		out = goals.close_cycle(cycle.name, outcomes=[{"goal": g1.name, "outcome": "Achieved", "result_note": "Did it"},
			{"goal": g2.name, "outcome": "Not Achieved"}])
		self.assertEqual(out["final_score"], 50.0)
		cycle.reload()
		g1.reload()
		g2.reload()
		self.assertEqual((cycle.status, str(cycle.closed_on)), ("Closed", today()))
		self.assertEqual((g1.outcome, g1.result_note, g1.final_score), ("Achieved", "Did it", 100.0))
		self.assertEqual((g2.outcome, g2.final_score), ("Not Achieved", 0.0))
		# closed cycles are read-only
		self.assertRaises(frappe.ValidationError, goals.tick, g1.actions[0].name, 3, 0)
		g1.title = "Changed"
		self.assertRaises(frappe.ValidationError, g1.save)
		cycle.title = "Changed"
		self.assertRaises(frappe.ValidationError, cycle.save)
		self.assertRaises(frappe.ValidationError, goals.save_goal, cycle=cycle.name, title="Late goal")
		self.assertRaises(frappe.ValidationError, goals.close_cycle, cycle.name)

	def test_cannot_close_before_the_end_date(self):
		cycle, _ = self.make_cycle(status="Active", goals=[("One", [("A", 1)])])
		self.assertRaises(frappe.ValidationError, goals.close_cycle, cycle.name)

	def test_plan_next_cycle_copies_only_chosen_goals_with_open_actions(self):
		cycle, (keep, leave) = self.make_cycle(start="2026-10-05", status="Active", goals=[
			("GHL turnaround", [("Visit gardens", 1), ("Plan sections", 2), ("Old step", 1), ("Dropped step", 1)]), ("Golf", [("Putt", 1)])])
		goals.set_action_status(keep.actions[2].name, "Done")
		goals.set_action_status(keep.actions[3].name, "Dropped")
		out = goals.plan_next_cycle(cycle.name, goals=[keep.name])
		new = frappe.get_doc("Life Cycle", out["cycle"])
		self.assertEqual((str(new.start_date), new.status, new.title), ("2026-12-28", "Planned", "Dec to Mar 2027"))
		self.assertEqual(getdate(new.start_date).weekday(), 0)
		carried = frappe.get_all("Life Goal", filters={"cycle": new.name}, fields=["name", "title", "carried_from", "area"])
		self.assertEqual([(g.title, g.carried_from) for g in carried], [("GHL turnaround", keep.name)])
		copy = frappe.get_doc("Life Goal", carried[0].name)
		self.assertEqual([(a.title, a.per_week, a.status) for a in copy.actions], [("Visit gardens", 1, "Open"), ("Plan sections", 2, "Open")])
		self.assertEqual(frappe.db.get_value("Life Goal", keep.name, "outcome"), "Carried")
		self.assertEqual(frappe.db.get_value("Life Goal", leave.name, "outcome"), "In Progress")
		again = goals.plan_next_cycle(cycle.name, goals=[keep.name])  # no duplicates
		self.assertEqual((again["cycle"], again["carried"]), (new.name, []))

	def test_goal_history_follows_the_chain_across_three_cycles(self):
		frappe.flags.lifeos_allow_early_close = True
		c1, (g1,) = self.make_cycle(start="2026-01-05", status="Active", title="C1", goals=[("Long goal", [("Step", 1)])])
		for week in (1, 2, 3):
			goals.tick(g1.actions[0].name, week, 1)
		n2 = goals.plan_next_cycle(c1.name, goals=[g1.name])
		goals.close_cycle(c1.name, outcomes=[{"goal": g1.name, "outcome": "Carried"}])
		goals.start_cycle(n2["cycle"])
		g2 = frappe.get_doc("Life Goal", n2["carried"][0])
		for week in range(1, 7):
			goals.tick(g2.actions[0].name, week, 1)
		n3 = goals.plan_next_cycle(n2["cycle"], goals=[g2.name])
		goals.close_cycle(n2["cycle"], outcomes=[{"goal": g2.name, "outcome": "Carried"}])
		g3 = n3["carried"][0]
		for start_from in (g1.name, g2.name, g3):
			history = goals.detail(start_from)["history"]
			self.assertEqual([h["name"] for h in history], [g1.name, g2.name, g3])
			self.assertEqual([h["outcome"] for h in history], ["Carried", "Carried", "In Progress"])
			self.assertEqual([h["score"] for h in history[:2]], [25.0, 50.0])

	def test_goals_tab_groups_by_cycle(self):
		frappe.flags.lifeos_allow_early_close = True
		old, _ = self.make_cycle(start="2025-07-07", status="Active", title="Old", goals=[("Old goal", [("A", 1)])])
		goals.close_cycle(old.name)
		active, (ag,) = self.make_cycle(status="Active", title="Now", goals=[("Now goal", [("A", 1)])])
		goals.plan_next_cycle(active.name, goals=[ag.name])
		data = goals.across_cycles(space=PRIVATE)
		mine = [c for c in data["cycles"] if c["title"] in ("Old", "Now") or c["goals"] and c["goals"][0].get("carried_from") == ag.name]
		self.assertEqual([c["status"] for c in mine], ["Planned", "Active", "Closed"])
		now = next(c for c in data["cycles"] if c["title"] == "Now")
		self.assertEqual((now["goals"][0]["actions"], now["goals"][0]["outcome"], now["goals"][0]["area_name"]), (1, "Carried", "Tea"))
		filtered = goals.across_cycles(space=PRIVATE, area=self.areas["Money"])
		self.assertEqual([g for c in filtered["cycles"] for g in c["goals"]], [])


class TestMonthAndHabits(JournalCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Habit Log", {"space": PRIVATE})
		frappe.db.sql("update `tabLife Habit` set tracked_from = null, tracked_until = null where space = %s", PRIVATE)

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

	def test_removing_a_habit_leaves_earlier_months_unchanged(self):
		japa, mala = self.make("Life Habit", title="Japa r"), self.make("Life Habit", title="Mala r")
		goals.set_month_habits(space=PRIVATE, year=2031, month=10, habits=[{"habit": japa.name}, {"habit": mala.name}])
		self.make("Life Habit Log", habit=mala.name, date="2031-10-03")
		goals.set_month_habits(space=PRIVATE, year=2031, month=11, habits=[{"habit": japa.name}])
		november = goals.month_habits(space=PRIVATE, year=2031, month=11)
		october = goals.month_habits(space=PRIVATE, year=2031, month=10)
		self.assertEqual([h["habit"] for h in november["habits"]], [japa.name])
		self.assertEqual([h["habit"] for h in october["habits"]], [japa.name, mala.name])
		self.assertEqual(next(h for h in october["habits"] if h["habit"] == mala.name)["done_days"], [3])
		december = goals.month_habits(space=PRIVATE, year=2031, month=12)
		self.assertEqual([h["habit"] for h in december["habits"]], [japa.name])

	def test_days_outside_the_tracked_period_are_not_missed(self):
		now = getdate(today())
		if now.day < 4:
			self.skipTest("needs a few elapsed days in the month")
		old, added = self.make("Life Habit", title="Old habit", tracked_from=now.replace(day=1)), self.make("Life Habit", title="Added today")
		goals.set_month_habits(space=PRIVATE, year=now.year, month=now.month, habits=[{"habit": old.name}, {"habit": added.name}])
		goals.toggle_habit(added.name, str(now))
		data = {h["habit"]: h for h in goals.month_habits(space=PRIVATE, year=now.year, month=now.month)["habits"]}
		self.assertEqual((data[added.name]["tracked_days"], data[added.name]["done"], data[added.name]["percent"]), (1, 1, 100))
		self.assertEqual((data[old.name]["tracked_days"], data[old.name]["done"], data[old.name]["percent"]), (now.day, 0, 0))
		# removed mid-month: days after removal are not counted, earlier days stay
		goals.toggle_habit(old.name, str(now.replace(day=1)))
		goals.set_month_habits(space=PRIVATE, year=now.year, month=now.month, habits=[{"habit": added.name}])
		data = {h["habit"]: h for h in goals.month_habits(space=PRIVATE, year=now.year, month=now.month)["habits"]}
		self.assertTrue(data[old.name]["removed"])
		self.assertEqual((data[old.name]["tracked_days"], data[old.name]["done"]), (now.day - 1, 1))
		from lifeos.api import today as today_api
		self.assertEqual([h["habit"] for h in today_api.get(space=PRIVATE)["habits"]], [added.name])

	def test_days_per_week_changes_the_percentage(self):
		daily = self.make("Life Habit", title="Daily", days_per_week=7, sort_order=1, tracked_from="2025-02-01", tracked_until="2025-02-28")
		five = self.make("Life Habit", title="Five a week", days_per_week=5, sort_order=2, tracked_from="2025-02-01", tracked_until="2025-02-28")
		for day in range(1, 21):
			for h in (daily, five):
				self.make("Life Habit Log", habit=h.name, date=f"2025-02-{day:02d}")
		data = {h["habit"]: h for h in goals.month_habits(space=PRIVATE, year=2025, month=2)["habits"]}
		self.assertEqual((data[daily.name]["done"], data[daily.name]["target"], data[daily.name]["percent"]), (20, 28, 71))
		self.assertEqual((data[five.name]["done"], data[five.name]["target"], data[five.name]["percent"]), (20, 20, 100))
		year = goals.habits_year(space=PRIVATE, year=2025)
		self.assertEqual({h["title"]: h["months"]["2"]["percent"] for h in year["habits"]}, {"Daily": 71, "Five a week": 100})
		self.assertEqual(list(year["habits"][0]["months"]), ["2"])

	def test_toggle_habit_and_permissions(self):
		habit = self.make("Life Habit", title="Toggle me")
		self.assertTrue(goals.toggle_habit(habit.name, "2026-11-10")["done"])
		self.assertTrue(frappe.db.exists("Life Habit Log", {"habit": habit.name, "date": "2026-11-10"}))
		self.assertFalse(goals.toggle_habit(habit.name, "2026-11-10")["done"])
		self.assertFalse(frappe.db.exists("Life Habit Log", {"habit": habit.name, "date": "2026-11-10"}))
		# a day that has not come cannot be ticked
		self.assertRaises(frappe.ValidationError, goals.toggle_habit, habit.name, frappe.utils.add_days(frappe.utils.today(), 1))
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, goals.toggle_habit, habit.name, "2026-11-10")
		self.assertRaises(frappe.PermissionError, goals.month_habits, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, goals.set_month_habits, space=PRIVATE, year=2026, month=11, habits=[])


class TestWeeklyReview(JournalCase):
	def test_weekly_review_gathers_the_week(self):
		now = getdate(today())
		monday = add_days(now, -now.weekday())
		cycle, (goal,) = self.make_cycle(start=add_days(monday, -7), status="Active", goals=[("Fit", [("Walk", 1), ("Run", 1)])])
		goals.tick(goal.actions[0].name, 2, 1)
		done = self.make("Life Task", title="Done this week")
		done.status = "Done"
		done.save()
		stale = self.make("Life Task", title="Stale open task")
		frappe.db.set_value("Life Task", stale.name, "last_touched_on", add_days(now, -200), update_modified=False)
		data = weekly.week_summary(space=PRIVATE)
		self.assertEqual((data["week_start"], data["week_end"]), (str(monday), str(add_days(monday, 6))))
		self.assertEqual((data["cycle"]["week"], data["cycle"]["percent"]), (2, 50.0))
		self.assertIn(done.name, [t["name"] for t in data["done"]])
		self.assertIn(stale.name, [t["name"] for t in data["decide"]])


class TestTodayThisWeek(JournalCase):
	def test_a_tick_moves_the_score_and_lead_actions_are_not_rows(self):  # issue 55: Today lists tasks, not a goal's weekly actions
		cycle, (goal,) = self.make_cycle(status="Active", goals=[("Fit", [("Walk", 1), ("Workout", 3), ("Dropped one", 1)])])
		walk, workout, dropped = goal.actions
		goals.set_action_status(dropped.name, "Dropped")
		data = today_api.get(space=PRIVATE)
		self.assertEqual(data["cycle"]["week"], 4)
		self.assertNotIn("actions", data["cycle"])
		self.assertFalse([g for g in data["next"]["groups"] if g["key"] == "twy"])
		goals.tick(workout.name, 4, 2)
		data = today_api.get(space=PRIVATE)["cycle"]
		self.assertEqual((data["done"], data["planned"]), (2, 4))


class TestServes(LifeTestCase):
	def test_served_by_and_no_loops(self):
		top = self.make("Life Goal", title="ux6 serves top", horizon="Year", target_date=add_days(today(), 300), area=self.areas["Tea"])
		mid = goals.create("ux6 serves mid", horizon="Long term", space=PRIVATE, area=self.areas["Tea"], serves=top.name, done_when="Done")
		low = goals.create("ux6 serves low", horizon="Long term", space=PRIVATE, area=self.areas["Tea"], serves=mid["name"])
		page = goals.get(top.name)
		self.assertEqual([r["name"] for r in page["served_by"]], [mid["name"]])
		self.assertEqual(goals.get(mid["name"])["goal"]["serves_title"], "ux6 serves top")
		listed = [r["name"] for r in goals.list(space=PRIVATE, serves=mid["name"])["goals"]]
		self.assertEqual(listed, [low["name"]])
		self.assertRaises(frappe.ValidationError, goals.update, mid["name"], {"serves": mid["name"]})
		self.assertRaises(frappe.ValidationError, goals.update, top.name, {"serves": mid["name"]})  # mid serves top
		self.assertRaises(frappe.ValidationError, goals.update, top.name, {"serves": low["name"]})  # through mid
		self.assertEqual(frappe.db.get_value("Life Goal", top.name, "serves"), None)


class TestOpenGoalStates(LifeTestCase):
	def test_done_archives_and_active_restores(self):
		g = goals.create("ux6 state goal", horizon="Long term", space=PRIVATE, area=self.areas["Tea"])["name"]
		task = self.make("Life Task", title="ux6 state task", area=self.areas["Tea"], goal=g)
		note = self.make("Life Note", title="ux6 state note", area=self.areas["Tea"], goal=g, content_md="x")
		self.assertEqual(goals.set_status(g, "On Hold")["status"], "On Hold")
		self.assertIn(g, [r["name"] for r in goals.list(space=PRIVATE)["goals"]])
		out = goals.set_status(g, "Done")
		self.assertEqual((out["status"], out["is_archived"], out["archived_records"]), ("Done", 1, 2))
		for doc in (task, note):
			self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, ["is_archived", "archive_reason"]), (1, "Project"))
		self.assertNotIn(g, [r["name"] for r in goals.list(space=PRIVATE)["goals"]])
		self.assertIn(g, [r["name"] for r in goals.list(space=PRIVATE, state="achieved")["goals"]])
		out = goals.set_status(g, "Active")
		self.assertEqual((out["status"], out["is_archived"]), ("Active", 0))
		for doc in (task, note):
			self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "is_archived"), 0)
		self.assertEqual(frappe.db.get_value("Life Goal", g, ["outcome", "on_hold", "closed_on"]), ("In Progress", 0, None))
		self.assertRaises(frappe.ValidationError, goals.set_status, g, "Finished")


def number_goal(title="ux7 weight", start=84, target=78, **kw):
	return goals.create(title, "Long term", space=PRIVATE, measure_kind="Number", measure=kw.pop("measure", "Weight"), unit=kw.pop("unit", "kg"),
		start_value=start, target_value=target, **kw)["name"]


class TestGoalRule(LifeTestCase):
	def test_milestone_needs_a_finish_line(self):
		self.assertRaises(frappe.ValidationError, goals.create, "ux7 m", "Long term", space=PRIVATE, measure_kind="Milestone")
		g = goals.create("ux7 m", "Long term", space=PRIVATE, measure_kind="Milestone", done_when="The plan is signed")["name"]
		self.assertEqual(frappe.db.get_value("Life Goal", g, "measure_kind"), "Milestone")

	def test_number_needs_measure_start_and_target(self):
		for missing in ("measure", "start_value", "target_value"):
			args = {"measure": "Yield", "start_value": 1, "target_value": 2, missing: None}
			self.assertRaises(frappe.ValidationError, goals.create, "ux7 n", "Long term", space=PRIVATE, measure_kind="Number", **args)
		self.assertRaises(frappe.ValidationError, goals.create, "ux7 n", "Long term", space=PRIVATE, measure_kind="Number", measure="Yield",
			start_value=5, target_value=5)

	def test_finish_line_alone_is_a_milestone(self):
		g = goals.create("ux7 f", "Long term", space=PRIVATE, done_when="Done")["name"]
		self.assertEqual(frappe.db.get_value("Life Goal", g, "measure_kind"), "Milestone")

	def test_old_goals_without_a_measure_still_save(self):
		g = frappe.get_doc({"doctype": "Life Goal", "space": PRIVATE, "title": "ux7 old", "horizon": "Long term"}).insert()
		g.title = "ux7 old, renamed"
		g.save()
		self.assertFalse(readings.has_finish_line(g))

	def test_editing_the_measure_applies_the_rule(self):
		g = goals.create("ux7 e", "Long term", space=PRIVATE, done_when="Done")["name"]
		self.assertRaises(frappe.ValidationError, goals.update, g, {"measure_kind": "Number", "measure": "Yield"})
		goals.update(g, {"measure_kind": "Number", "measure": "Yield", "unit": "kg/ha", "start_value": 1200, "target_value": 1800})
		self.assertEqual(frappe.db.get_value("Life Goal", g, "target_value"), 1800)

	def test_agents_cannot_create_or_suggest(self):
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, goals.create, "ux7 a", "Long term", space=PRIVATE, done_when="x")
		self.assertRaises(frappe.PermissionError, goals.suggest_measure, "Lose 6 kg", space=PRIVATE)


class TestProgress(LifeTestCase):
	def test_both_directions_and_clamping(self):
		self.assertEqual(readings.progress(84, 78, 81), 50.0)  # going down
		self.assertEqual(readings.progress(1200, 1800, 1500), 50.0)  # going up
		self.assertEqual(readings.progress(84, 78, 90), 0.0)
		self.assertEqual(readings.progress(84, 78, 70), 100.0)
		self.assertEqual(readings.progress(84, 78, None), 0.0)
		self.assertEqual(readings.direction(84, 78), "down")
		self.assertTrue(readings.reached({"measure_kind": "Number", "start_value": 84, "target_value": 78, "current_value": 77.5, "current_on": today()}))
		self.assertFalse(readings.reached({"measure_kind": "Number", "start_value": 84, "target_value": 78, "current_value": 79, "current_on": today()}))
		self.assertTrue(readings.reached({"measure_kind": "Number", "start_value": 1, "target_value": 10, "current_value": 10, "current_on": today()}))


class TestReadings(LifeTestCase):
	def test_current_value_is_the_latest_confirmed_reading(self):
		g = number_goal()
		goals.add_reading(g, 82, date=add_days(today(), -10))
		out = goals.add_reading(g, 81, date=add_days(today(), -3))
		self.assertEqual(out["current_value"], 81)
		self.assertEqual(out["progress"]["percent"], 50.0)
		# an older reading entered later does not replace the latest one
		goals.add_reading(g, 83, date=add_days(today(), -20))
		self.assertEqual(frappe.db.get_value("Life Goal", g, "current_value"), 81)
		# a suggested reading does not count until it is confirmed
		r = readings.suggest(g, 80, today(), "weighed 80 kg", by="Assistant")
		self.assertEqual(frappe.db.get_value("Life Goal", g, "current_value"), 81)
		out = goals.confirm_reading(r.name, value=79.5)
		self.assertEqual(out["current_value"], 79.5)
		self.assertEqual(str(frappe.db.get_value("Life Goal", g, "current_on")), today())
		# deleting the latest falls back to the one before
		frappe.delete_doc("Life Goal Reading", r.name)
		self.assertEqual(frappe.db.get_value("Life Goal", g, "current_value"), 81)

	def test_reject_keeps_it_out(self):
		g = number_goal()
		r = readings.suggest(g, 80, today(), "x", by="Agent")
		goals.reject_reading(r.name)
		self.assertIsNone(frappe.db.get_value("Life Goal", g, "current_on"))
		confirmed, suggested = readings.for_goal(g)
		self.assertEqual((confirmed, suggested), ([], []))
		# the same suggestion is not stored twice
		again = readings.suggest(g, 80, today(), "x", by="Agent")
		self.assertNotEqual(again.name, r.name)  # a rejected one does not block a new suggestion

	def test_readings_only_on_number_goals(self):
		g = goals.create("ux7 milestone", "Long term", space=PRIVATE, done_when="Done")["name"]
		self.assertRaises(frappe.ValidationError, goals.add_reading, g, 3)

	def test_agents_cannot_confirm_or_reject(self):
		g = number_goal()
		r = readings.suggest(g, 80, today(), "x", by="Agent")
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, goals.confirm_reading, r.name)
		self.assertRaises(frappe.PermissionError, goals.reject_reading, r.name)
		self.assertRaises(frappe.PermissionError, goals.add_reading, g, 79)
		doc = frappe.get_doc("Life Goal Reading", r.name)
		doc.status = "Confirmed"
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)

	def test_reading_proposal_is_stored_as_suggested(self):
		g = number_goal("ux7 yield", 1200, 1800, measure="Ghillidary yield", unit="kg/ha")
		item = inbox.create_item(space=PRIVATE, title="Season update", source_type="Message", raw_text="Ghillidary yield this flush: 1640 kg/ha")
		self.as_user(AGENT)
		claimed = inbox.claim_next(space=PRIVATE)
		self.assertEqual(claimed["name"], item["name"])
		ctx_goal = next(x for x in claimed["context"]["goals"] if x["name"] == g)
		self.assertEqual(ctx_goal["measure"]["unit"], "kg/ha")
		out = inbox.submit_result(item["name"], summary_md="An update", proposals=[
			{"kind": "Reading", "preview": "Yield 1640", "confidence": 0.8,
				"payload": {"goal": g, "value": 1640, "excerpt": "Ghillidary yield this flush: 1640 kg/ha"}},
			{"kind": "Reading", "preview": "bad", "payload": {"goal": g, "value": "lots", "excerpt": "x"}}])
		self.assertEqual(len(out["readings"]), 1)
		self.assertEqual(len(out["errors"]), 1)
		self.assertEqual(out["created"], [])
		self.assertEqual(out["status"], "Done")  # nothing waits in the Inbox
		r = frappe.get_doc("Life Goal Reading", out["readings"][0]["name"])
		self.assertEqual((r.status, r.value, r.source_doctype, r.source_name, r.suggested_by), ("Suggested", 1640, "Life Inbox Item", item["name"], "Agent"))
		self.assertIsNone(frappe.db.get_value("Life Goal", g, "current_on"))

	def test_fake_agent_reports_a_reading(self):
		from lifeos.devtools import load_fake_agent

		fa = load_fake_agent()
		g = number_goal("ux7 weight goal")
		ctx = {"goals": [{"name": g, "measure_kind": "Number", "measure": {"measure": "Weight", "unit": "kg"}}]}
		got = fa.readings_in("Weight this morning was 80.4 kg", ctx, today())
		self.assertEqual(got[0]["payload"]["value"], 80.4)

	def test_nightly_readings_with_the_assistant(self):
		set_key("sk-test-not-real")
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 1)
		frappe.set_user(OWNER)
		g = number_goal("ux7 nightly", measure="Body weight")
		frappe.get_doc({"doctype": "Life Chat Log", "space": PRIVATE, "title": "ux7 health chat", "assistant": "Claude", "date": today(),
			"summary_md": "Body weight today 80.2 kg after the walk."}).insert()
		frappe.flags.lifeos_ai_backend = fake.SiteFake()
		try:
			made, note = readings.from_recent(PRIVATE, OWNER)
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key("")
		self.assertIsNone(note)
		self.assertGreaterEqual(made, 1)  # other number goals measured by "Weight" match the same words
		_, suggested = readings.for_goal(g)
		self.assertEqual(suggested[0]["value"], 80.2)
		self.assertEqual(suggested[0]["source_doctype"], "Life Chat Log")

	def test_nightly_readings_skip_without_a_key(self):
		set_key("")
		frappe.set_user(OWNER)
		number_goal("ux7 nokey")
		made, note = readings.from_recent(PRIVATE, OWNER)
		self.assertEqual(made, 0)
		self.assertIn("no API key", note)


class TestSuggestAndHabit(LifeTestCase):
	def test_without_a_key_there_is_no_suggestion_but_a_habit_is_still_seen(self):
		"""Issue 59: the rules that guessed a measure are gone; no key means no suggestion and no error."""
		set_key("")
		frappe.set_user(OWNER)
		r = goals.suggest_measure("Ghillidary yield 1800 kg/ha", space=PRIVATE)
		self.assertEqual((r["kind"], r["by"], r["target_value"]), (None, None, None))
		self.assertEqual(goals.suggest_measure("Walk 3 times a week", space=PRIVATE)["habit"]["days_per_week"], 3)

	def test_frequencies_are_habits(self):
		self.assertEqual(readings.habit_of("Meditate daily")["days_per_week"], 7)
		self.assertEqual(readings.habit_of("Swim twice a week")["days_per_week"], 2)
		self.assertEqual(readings.habit_of("Review every Sunday")["days_per_week"], 1)
		self.assertIsNone(readings.habit_of("Close the PMS account"))

	def test_make_it_a_habit_creates_no_goal(self):
		before = frappe.db.count("Life Goal", {"space": PRIVATE})
		out = goals.make_habit("ux7 Walk 3 times a week", space=PRIVATE)
		self.assertEqual(out["days_per_week"], 3)
		self.assertEqual(frappe.db.count("Life Goal", {"space": PRIVATE}), before)
		now = getdate(today())
		month = habit_rules.habits_month(PRIVATE, now.year, now.month)
		self.assertIn(out["habit"], [h["habit"] for h in month["habits"]])


class TestServesInGoalPages(LifeTestCase):
	def test_serves_and_served_by_with_progress(self):
		top = number_goal("ux7 top", 1200, 1800, measure="Yield", unit="kg/ha")
		goals.add_reading(top, 1500)
		low = goals.create("ux7 low", "Year", space=PRIVATE, target_date=add_days(today(), 90), serves=top, done_when="Plan done")["name"]
		frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 step", "goal": low, "status": "Done", "area": self.areas["Tea"]}).insert()
		frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 step 2", "goal": low, "status": "Open", "area": self.areas["Tea"]}).insert()
		d = goals.get(low)
		self.assertEqual(d["serves"]["name"], top)
		self.assertEqual(d["serves"]["progress"]["percent"], 50.0)
		t = goals.get(top)
		row = next(r for r in t["served_by"] if r.name == low)
		self.assertEqual((row.progress["kind"], row.progress["percent"]), ("tasks", 50.0))
		listed = goals.list(space=PRIVATE, sort="serves", page_length=500)["goals"]
		self.assertEqual(next(r for r in listed if r.name == top).progress["label"], "1500 kg/ha, target 1800 kg/ha")

	def test_cycle_goal_shows_the_goal_it_serves(self):
		top = number_goal("ux7 annual top", 10, 20, measure="Clients", unit="")
		c = goals.create_cycle(space=PRIVATE, start_date=add_days(today(), -today_weekday()))["cycle"]
		g = goals.save_goal(cycle=c, title="ux7 cycle goal", serves=top, measure_kind="Milestone", done_when="Ten pitches",
			actions=[{"title": "Pitch", "per_week": 4}])["goal"]
		row = next(x for x in rules.grid(c)["goals"] if x["name"] == g)
		self.assertEqual(row["serves_title"], "ux7 annual top")
		self.assertEqual(row["serves_progress"]["kind"], "number")


def today_weekday():
	return getdate(today()).weekday()


class TestCountedActions(LifeTestCase):
	def test_each_tick_counts_towards_the_week_score(self):
		c = goals.create_cycle(space=PRIVATE, start_date=add_days(today(), -today_weekday()))["cycle"]
		frappe.db.set_value("Life Cycle", c, "status", "Active")
		g = goals.save_goal(cycle=c, title="ux7 counted", measure_kind="Milestone", done_when="Done",
			actions=[{"title": "Call a client", "per_week": 4}])["goal"]
		action = frappe.get_doc("Life Goal", g).actions[0].name
		week = rules.current_week(frappe.get_doc("Life Cycle", c))
		s0 = rules.week_score(c, week)
		s1 = goals.tick(action, week, 1)
		self.assertEqual(s1["done"], s0["done"] + 1)
		self.assertGreater(s1["percent"], s0["percent"])
		s2 = goals.tick(action, week, 2)
		self.assertEqual(s2["done"], s0["done"] + 2)
		self.assertEqual(goals.tick(action, week, 9)["done"], s0["done"] + 4)  # never more than per_week
		row = next(x for x in rules.grid(c)["goals"] if x["name"] == g)
		self.assertEqual(row["actions"][0]["ticks"][str(week)], 4)
		self.assertEqual(json.loads(json.dumps(row["actions"][0]["per_week"])), 4)


class TestGoalsByArea(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		self.career, self.health, self.tea = self.life["Career"], self.life["Health"], self.areas["Tea"]
		frappe.db.set_value("Life Area", self.career, "is_on", 1)
		frappe.db.set_value("Life Area", self.health, "is_on", 1)

	def goal(self, title, area, **kw):
		return self.make("Life Goal", title=title, area=area, horizon="Long term", **kw).name

	def section(self, res, area):
		return next((s for s in res["sections"] if s["area"] == area), None)

	def test_goals_sit_under_their_area_and_part(self):
		a = self.goal("i20 career", self.career)
		b = self.goal("i20 tea", self.tea)
		c = self.goal("i20 health", self.health)
		res = goals.by_area(space=PRIVATE, show="open")
		self.assertEqual(res["total"], 3)
		career = self.section(res, self.career)
		direct = next(g for g in career["groups"] if g["area"] is None)
		part = next(g for g in career["groups"] if g["area"] and g["area"]["name"] == self.tea)
		self.assertEqual([g["name"] for g in direct["goals"]], [a])
		self.assertEqual([g["name"] for g in part["goals"]], [b])
		self.assertEqual([g["name"] for g in self.section(res, self.health)["groups"][0]["goals"]], [c])

	def test_the_card_has_done_when_next_action_and_the_open_task_count_of_the_goal_page(self):
		g = self.goal("i20 card", self.career, done_when="Signed")
		self.make("Life Task", title="i20 later", status="Open", goal=g, area=self.career, due_date="2026-12-20")
		self.make("Life Task", title="i20 sooner", status="Doing", goal=g, area=self.career, due_date="2026-12-01")
		self.make("Life Task", title="i20 done", status="Done", goal=g, area=self.career)
		card = next(x for s in goals.by_area(space=PRIVATE, show="open")["sections"] for grp in s["groups"] for x in grp["goals"] if x["name"] == g)
		self.assertEqual(card["done_when_line"], "Signed")
		self.assertEqual(card["next_action"]["title"], "i20 sooner")
		self.assertEqual(card["open_tasks"], goals.get(goal=g)["tabs"]["tasks"])
		self.assertEqual(card["open_tasks"], 2)
		self.assertEqual(card["progress"]["label"], goals.get(goal=g)["goal"]["progress"]["label"])

	def test_a_number_goal_shows_its_start_and_target(self):
		g = self.goal("i20 number", self.career, measure_kind="Number", measure="Weight", unit="kg", start_value=84, target_value=78)
		card = next(x for grp in self.section(goals.by_area(space=PRIVATE, show="open"), self.career)["groups"] for x in grp["goals"] if x["name"] == g)
		self.assertEqual(card["done_when_line"], "84 → 78 kg")

	def test_an_area_that_is_off_has_no_section_and_turning_it_on_brings_its_goals_back(self):
		self.goal("i20 health", self.health)
		frappe.db.set_value("Life Area", self.health, "is_on", 0)
		res = goals.by_area(space=PRIVATE, show="open")
		self.assertIsNone(self.section(res, self.health))
		self.assertIn(self.health, [a["name"] for a in res["off"]])
		self.assertEqual(res["total"], 0)
		frappe.db.set_value("Life Area", self.health, "is_on", 1)
		self.assertEqual(self.section(goals.by_area(space=PRIVATE, show="open"), self.health)["count"], 1)

	def test_an_area_without_goals_still_has_a_section(self):
		self.goal("i20 career", self.career)
		health = self.section(goals.by_area(space=PRIVATE, show="open"), self.health)
		self.assertEqual((health["count"], health["groups"]), (0, []))

	def test_filters_this_cycle_all_open_finished(self):
		cycle = self.make("Life Cycle", title="i20 cycle", start_date="2026-10-05", status="Active").name
		inside = self.make("Life Goal", title="i20 inside", area=self.health, horizon="12 weeks", cycle=cycle).name
		outside = self.goal("i20 outside", self.health)
		done = self.goal("i20 done", self.health)
		frappe.db.set_value("Life Goal", done, "outcome", "Achieved")
		names = lambda show: {x["name"] for s in goals.by_area(space=PRIVATE, show=show)["sections"] for grp in s["groups"] for x in grp["goals"]}
		self.assertEqual(names("cycle"), {inside})
		self.assertEqual(names("open"), {inside, outside})
		self.assertEqual(names("finished"), {done})
		with self.assertRaises(frappe.ValidationError):
			goals.by_area(space=PRIVATE, show="nonsense")

	def test_reorder_saves_the_owners_order_and_score_sort_is_the_other_order(self):
		a, b, c = (self.goal(f"i20 {n}", self.health) for n in "abc")
		names = lambda **kw: [x["name"] for x in self.section(goals.by_area(space=PRIVATE, show="open", **kw), self.health)["groups"][0]["goals"]]
		self.assertEqual(names(), [a, b, c])
		goals.reorder(goals=[c, a, b])
		self.assertEqual(names(), [c, a, b])
		goals.reorder(goals=[b, c])
		self.assertEqual(names().index(b) < names().index(c), True)
		self.assertEqual(len(names(sort="score")), 3)

	def test_an_agent_cannot_reorder_and_a_reader_cannot_see_the_space(self):
		a = self.goal("i20 a", self.health)
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			goals.reorder(goals=[a])
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			goals.by_area(space=PRIVATE)
		self.assertEqual(goals.by_area(space=SHARED)["total"], 0)


class TestCyclesScreen(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		frappe.db.delete("Life Cycle", {"space": PRIVATE})
		frappe.db.set_single_value("Life Settings", "cycle_break_week", 1)
		frappe.clear_cache(doctype="Life Settings")

	def test_the_grid_says_when_the_next_cycle_opens(self):
		start = rules.next_monday(add_days(today(), -30))
		cycle = self.make("Life Cycle", title="i45 cycle", start_date=start, status="Active")
		out = goals.grid(cycle=cycle.name, space=PRIVATE)
		nxt = out["next"]
		self.assertEqual(nxt["plan_opens"], str(add_days(getdate(start), 70)))
		self.assertEqual(nxt["starts"], str(rules.next_monday(cycle.end_date)))
		self.assertEqual(nxt["break_week"], [str(add_days(getdate(cycle.end_date), 1)), str(add_days(getdate(nxt["starts"]), -1))])
		frappe.db.set_single_value("Life Settings", "cycle_break_week", 0)
		frappe.clear_cache(doctype="Life Settings")
		self.assertIsNone(goals.grid(cycle=cycle.name, space=PRIVATE)["next"]["break_week"])

	def test_this_month_lists_the_month_goals_with_status_and_carried_month(self):
		now = getdate(today())
		last = now.replace(day=1) - frappe.utils.datetime.timedelta(days=1)
		old = rules.add_month_goal(PRIVATE, last.year, last.month, "i45 carried goal")
		carried = rules.carry_month_goal(old.name)
		rules.add_month_goal(PRIVATE, now.year, now.month, "i45 second goal")
		self.make("Life Task", title="i45 task one", goal=carried["row"], status="Done")
		self.make("Life Task", title="i45 task two", goal=carried["row"], status="Open")
		out = goals.this_month(space=PRIVATE, year=now.year, month=now.month)
		by_title = {g["title"]: g for g in out["goals"]}
		first = by_title["i45 carried goal"]
		self.assertEqual(first["carried_from"], old.name)
		self.assertEqual(first["carried_from_month"], last.month)
		self.assertEqual((first["tasks_done"], first["tasks_counted"]), (1, 2))
		self.assertEqual(by_title["i45 second goal"]["carried_from_month"], None)
		# a goal's status changes through the goal, and the next read shows it
		frappe.db.set_value("Life Goal", by_title["i45 second goal"]["row"], "outcome", "Achieved")
		again = {g["title"]: g for g in goals.this_month(space=PRIVATE, year=now.year, month=now.month)["goals"]}
		self.assertEqual(again["i45 second goal"]["status"], "Done")

	def test_a_journal_page_is_a_note_in_the_notes_list(self):
		note = self.make("Life Note", title="i45 a note", content_md="text")
		page = self.make("Life Note", title="Journal page 7", content_md="i45 paper words", page_date=today())
		rows = {r["name"]: r for r in library.list(space=PRIVATE, page_length=100)["notes"]}
		self.assertEqual((rows[page.name]["kind"], rows[note.name]["kind"]), ("Note", "Note"))


def set_required(on):
	frappe.db.set_single_value("Life Settings", "require_done_when", 1 if on else 0)


class TestGoalEdit(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		set_required(True)

	def tearDown(self):
		set_required(True)
		super().tearDown()

	def test_6_a_goal_without_a_finish_line_is_refused_with_the_setting_on(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			goals.create(title="i56 bare", horizon="Long term", space=PRIVATE)
		self.assertIn("Write what will be true when this goal is done. Stuck? Use Suggest.", str(ctx.exception))
		self.assertFalse(frappe.db.exists("Life Goal", {"title": "i56 bare"}))
		self.assertTrue(goals.create(title="i56 with", horizon="Long term", space=PRIVATE, done_when="It is shipped")["name"])
		self.assertTrue(goals.create(title="i56 number", horizon="Long term", space=PRIVATE, measure_kind="Number", measure="Weight", unit="kg",
			start_value=84, target_value=78)["name"])

	def test_7_with_the_setting_off_a_goal_needs_no_finish_line(self):
		set_required(False)
		self.assertTrue(goals.create(title="i56 free", horizon="Long term", space=PRIVATE)["name"])

	def test_the_setting_is_on_by_default(self):
		meta = frappe.get_meta("Life Settings").get_field("require_done_when")
		self.assertEqual(str(meta.default), "1")

	def test_a_site_that_never_saved_the_setting_has_it_on(self):
		from lifeos.api import session, settings

		frappe.db.delete("Singles", {"doctype": "Life Settings", "field": "require_done_when"})
		frappe.clear_document_cache("Life Settings", "Life Settings")
		self.assertEqual(session.boot()["settings"]["require_done_when"], 1)
		self.assertEqual(settings.get(space=PRIVATE)["settings"]["require_done_when"], 1)
		with self.assertRaises(frappe.ValidationError):
			goals.create(title="i56 never saved", horizon="Long term", space=PRIVATE)

	def test_existing_goals_without_done_when_are_not_blocked(self):
		g = self.make("Life Goal", title="i56 old", horizon="Long term").name
		out = goals.update(g, {"title": "i56 old renamed"})
		self.assertEqual(out["goal"]["title"], "i56 old renamed")
		self.assertFalse(out["goal"]["has_finish_line"])

	def test_10_an_agent_goal_proposal_without_done_when_cannot_be_accepted_until_it_has_one(self):
		item = inbox.create_item(space=PRIVATE, title="Idea", source_type="Message", raw_text="Start the nursery")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		out = inbox.submit_result(item["name"], summary_md="x", proposals=[{"kind": "Goal", "preview": "Nursery", "payload": {"title": "i56 nursery", "horizon": "Year", "target_date": "2027-03-01"}}])
		self.assertEqual(len(out["proposals"]) if "proposals" in out else 1, 1)  # accepted into Needs you
		prop = frappe.get_all("Life Proposal", filters={"inbox_item": item["name"]}, pluck="name")[0]
		self.as_user(OWNER)
		from lifeos.api import brain

		row = next(r for r in brain.needs_you(space=PRIVATE)["rows"] if r["proposal"] == prop)
		self.assertTrue(row["blocked"])
		with self.assertRaises(frappe.ValidationError):
			review.decide(prop, "accept")
		self.assertEqual(frappe.db.get_value("Life Proposal", prop, "status"), "Pending")
		done = review.decide(prop, "accept", {"title": "i56 nursery", "horizon": "Year", "target_date": "2027-03-01", "done_when": "The nursery is planted"})
		self.assertEqual(done["status"], "Accepted")
		self.assertEqual(frappe.db.get_value("Life Goal", done["created_name"], "done_when"), "The nursery is planted")

	def test_make_it_a_goal_needs_a_finish_line(self):
		career = self.life["Career"]
		ts = [self.make("Life Task", title=f"i56 zorbax {n}", area=career).name for n in range(3)]
		from lifeos.api import tasks

		with self.assertRaises(frappe.ValidationError):
			tasks.make_goal(ts, space=PRIVATE, area=career, title="Zorbax")
		out = tasks.make_goal(ts, space=PRIVATE, area=career, title="Zorbax", done_when="Zorbax is delivered")
		self.assertEqual(frappe.db.get_value("Life Goal", out["goal"], "done_when"), "Zorbax is delivered")

	def test_a_month_goal_needs_a_finish_line_too(self):
		last = str(rules.month_bounds(2026, 11)[1])
		with self.assertRaises(frappe.ValidationError):
			goals.create(title="i56 month", horizon="Month", target_date=last, space=PRIVATE)
		goals.create(title="i56 month", horizon="Month", target_date=last, done_when="Sent", space=PRIVATE)
		self.assertTrue(frappe.db.exists("Life Goal", {"title": "i56 month", "done_when": "Sent"}))

	def test_suggest_without_a_key_gives_two_examples(self):
		out = goals.suggest_measure(title="i56 suggest", space=PRIVATE, horizon="12 weeks")
		self.assertIsNone(out["kind"])
		self.assertEqual(len(out["examples"]), 2)


	def test_11_suggest_sends_the_goals_title_area_actions_and_tasks_to_the_skill(self):
		from lifeos.ai import fake
		from lifeos.tests.helpers import set_key

		cycle = self.make("Life Cycle", title="i56 s cycle", start_date="2026-11-02", end_date="2027-01-24", status="Active").name
		g = self.make("Life Goal", title="i56 systems", horizon="12 weeks", cycle=cycle, area=self.life["Career"],
			actions=[{"title": "Start the internal audit", "per_week": 2, "status": "Open"}]).name
		self.make("Life Task", title="i56 draft the audit plan", goal=g)
		set_key("sk-test-not-real")
		backend = frappe.flags.lifeos_ai_backend = fake.ScriptedFake([{"content": [{"type": "text", "text": '{"kind": "Milestone", "done_when": "The audit has run twice."}'}],
			"stop_reason": "end_turn", "usage": {"input_tokens": 100, "output_tokens": 10}}])
		try:
			out = goals.suggest_measure(title="i56 systems", goal=g)
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key(None)
		self.assertEqual(out["done_when"], "The audit has run twice.")
		sent = str(backend.received)
		for text in ("Start the internal audit", "i56 draft the audit plan", "Career"):
			self.assertIn(text, sent)


class TestEditGoal(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		frappe.db.delete("Life Cycle", {"space": PRIVATE})
		self.cycle = self.make("Life Cycle", title="i56 cycle", start_date="2026-11-02", end_date="2027-01-24", status="Active").name
		self.goal = self.make("Life Goal", title="i56 RMT", horizon="12 weeks", cycle=self.cycle, done_when="Done",
			actions=[{"title": "Audit", "per_week": 2, "status": "Open"}, {"title": "Newsletter", "per_week": 1, "status": "Open"}]).name

	def test_1_a_rename_keeps_the_goal_and_what_points_to_it(self):
		note = self.make("Life Note", title="i56 note", goal=self.goal, content_md="x").name
		task = self.make("Life Task", title="i56 task", goal=self.goal).name
		out = goals.edit(self.goal, {"title": "i56 RMT systems"})
		self.assertEqual(out["goal"]["name"], self.goal)
		self.assertEqual(out["goal"]["title"], "i56 RMT systems")
		self.assertEqual(frappe.db.get_value("Life Note", note, "goal"), self.goal)
		self.assertEqual(frappe.db.get_value("Life Task", task, "goal"), self.goal)
		self.assertEqual(frappe.db.get_value("Life Goal", self.goal, "cycle"), self.cycle)
		self.assertTrue(frappe.get_all("Comment", filters={"reference_doctype": "Life Goal", "reference_name": self.goal, "content": ("like", "%renamed%")}))

	def test_2_the_area_can_be_changed_to_a_part(self):
		tea = self.areas["Tea"]  # a part of Career
		out = goals.edit(self.goal, {"area": tea})
		self.assertEqual(out["goal"]["area"], tea)
		res = goals.by_area(space=PRIVATE, show="open")
		self.assertIn(self.goal, [g["name"] for s in res["sections"] for grp in s["groups"] for g in grp["goals"]])

	def test_3_actions_can_be_added_retired_renamed_and_reordered(self):
		acts = goals.detail(self.goal)["goal"]["actions"]
		audit, news = acts[0], acts[1]
		out = goals.edit(self.goal, {}, actions=[
			{"name": news["name"], "title": "RMT newsletter", "per_week": 1},
			{"name": audit["name"], "title": audit["title"], "per_week": 2, "retired": True},
			{"title": "Training programme", "per_week": 3}])
		self.assertEqual(out["goal"]["title"], "i56 RMT")
		page = goals.detail(self.goal)
		self.assertEqual([(a["title"], a["status"]) for a in page["goal"]["actions"]],
			[("RMT newsletter", "Open"), ("Audit", "Dropped"), ("Training programme", "Open")])
		grid = next(g for g in rules.grid(self.cycle)["goals"] if g["name"] == self.goal)
		self.assertEqual([a["title"] for a in grid["actions"]], ["RMT newsletter", "Audit", "Training programme"])
		cycles = next(g for c in goals.across_cycles(space=PRIVATE)["cycles"] if c["name"] == self.cycle for g in c["goals"] if g["name"] == self.goal)
		self.assertEqual(cycles["actions"], 2)  # the retired one is not counted
		again = goals.edit(self.goal, {}, actions=[{"name": audit["name"], "title": "Audit", "per_week": 2}])
		self.assertTrue(again)
		self.assertEqual(frappe.db.get_value("Life Goal Action", audit["name"], "status"), "Open")

	def test_4_5_the_goal_page_finds_its_cycle_and_counts_this_weeks_ticks(self):
		got = goals.get(self.goal)
		self.assertEqual(got["cycle"]["title"], "i56 cycle")
		page = goals.detail(self.goal)
		self.assertEqual(page["cycle"]["name"], self.cycle)
		week = page["this_week"]
		self.assertEqual(week["planned"], 3)
		self.assertEqual(week["done"], 0)

	def test_only_a_writer_can_edit(self):
		self.as_user("family@lifeos.test")
		with self.assertRaises(frappe.PermissionError):
			goals.edit(self.goal, {"title": "no"})


def use_focuses(on):
	frappe.db.set_single_value("Life Settings", "use_focuses", 1 if on else 0)


class TestFocuses(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		for name in frappe.get_all("Life Area", filters={"space": PRIVATE, "is_focus": 1}, pluck="name"):
			frappe.delete_doc("Life Area", name, force=True)
		use_focuses(True)
		self.tea = self.areas["Tea"]

	def tearDown(self):
		use_focuses(False)
		super().tearDown()

	def focus(self, name="Yield", parent=None, **kw):
		return frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": name, "parent_area": parent or self.tea, "is_focus": 1, **kw}).insert()

	def test_1_a_focus_sits_under_a_part_or_a_life_area_and_nothing_goes_below_it(self):
		under_part = self.focus("Yield")
		under_area = self.focus("Fitness", parent=self.life["Health"])
		self.assertTrue(under_part.is_focus and under_area.is_focus)
		with self.assertRaises(frappe.ValidationError):
			self.focus("Deeper", parent=under_part.name)
		with self.assertRaises(frappe.ValidationError):  # a part cannot go below a focus either
			frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Sub", "parent_area": under_part.name}).insert()
		part = frappe.get_doc("Life Area", self.tea)  # a part with focuses is still a valid part
		part.description = "still valid"
		part.save()

	def test_2_a_part_of_a_kind_offers_its_focuses(self):
		names = lambda kind: [f["name"] for f in settings.focus_offers(kind)]  # noqa: E731
		self.assertEqual(names("Company"), ["Review cadence", "Systems", "Marketing", "People", "Finance"])
		self.assertEqual(names("Estate"), ["Yield", "Quality", "People", "Systems"])
		self.assertEqual(names("Household"), ["Home", "Money admin", "Health admin"])
		self.assertEqual(names("Other"), [])
		self.assertTrue(all(st for _n, st in focus_defaults.offered("Company")))
		out = settings.save_item("area", space=PRIVATE, title="Acme", parent_area=self.life["Career"], part_kind="Company")
		self.assertEqual(len(out["focuses"]), 5)
		kids = frappe.get_all("Life Area", filters={"parent_area": out["name"]}, fields=["area_name", "is_focus", "standard"])
		self.assertEqual({k.area_name for k in kids}, set(names("Company")))
		self.assertTrue(all(k.is_focus and k.standard for k in kids))
		chosen = settings.save_item("area", space=PRIVATE, title="Estate Two", parent_area=self.life["Career"], part_kind="Estate", focuses=["Yield", "Quality"])
		self.assertEqual(len(chosen["focuses"]), 2)

	def test_3_with_use_focuses_off_no_focus_is_shown_or_required(self):
		f = self.focus("Yield")
		self.make("Life Goal", title="i57 under focus", horizon="Year", target_date="2027-03-01", area=f.name)
		self.assertIn(f.name, [a.name for a in areas.ordered(PRIVATE)])
		use_focuses(False)
		self.assertNotIn(f.name, [a.name for a in areas.ordered(PRIVATE)])
		self.assertNotIn(f.name, [a["name"] for a in inbox.space_context(PRIVATE)["areas"]])
		self.assertNotIn(f.name, [a["name"] for a in settings.get(space=PRIVATE)["areas"]])
		data = goals.by_area(space=PRIVATE, show="open")
		self.assertEqual(data["focus_count"], 0)
		part_group = next(g for s in data["sections"] for g in s["groups"] if g["area"] and g["area"]["name"] == self.tea)
		self.assertEqual([x["title"] for x in part_group["goals"]], ["i57 under focus"])  # the goal sits under its part
		self.assertEqual(part_group["focuses"], [])
		self.assertEqual(areas.add_offered_focuses(self.tea), [])
		use_focuses(True)
		self.assertEqual(goals.by_area(space=PRIVATE, show="open")["focus_count"], 1)

	def test_a_new_site_has_it_off(self):
		self.assertEqual(str(frappe.get_meta("Life Settings").get_field("use_focuses").default), "0")

	def test_by_area_puts_the_annual_goal_first_and_marks_a_focus_without_one(self):
		f = self.focus("Yield")
		self.make("Life Goal", title="i57 quarterly", horizon="Month", target_date="2026-11-30", area=f.name)
		data = goals.by_area(space=PRIVATE, show="open")
		entry = next(e for s in data["sections"] for g in s["groups"] for e in g["focuses"] if e["name"] == f.name)
		self.assertFalse(entry["has_annual"])
		self.make("Life Goal", title="i57 annual", horizon="Year", target_date="2027-03-01", area=f.name)
		data = goals.by_area(space=PRIVATE, show="open")
		entry = next(e for s in data["sections"] for g in s["groups"] for e in g["focuses"] if e["name"] == f.name)
		self.assertTrue(entry["has_annual"])
		self.assertEqual([g["title"] for g in entry["goals"]], ["i57 annual", "i57 quarterly"])

	def test_the_focus_page_has_the_standard_principles_and_goals_by_horizon(self):
		f = self.focus("Yield", standard="Above 1,700 kg/ha")
		settings.save_item("area", name=f.name, principles=["One system", "Fix the process first"])
		self.make("Life Goal", title="i57 annual", horizon="Year", target_date="2027-03-01", area=f.name)
		self.make("Life Goal", title="i57 old", horizon="Year", target_date="2026-03-01", area=f.name, outcome="Achieved")
		page = focus.get(f.name)
		self.assertEqual((page["standard"], page["principles"]), ("Above 1,700 kg/ha", ["One system", "Fix the process first"]))
		self.assertEqual([g["title"] for g in page["annual"]], ["i57 annual"])
		self.assertEqual([g["title"] for g in page["finished"]], ["i57 old"])
		self.assertTrue(page["has_annual"])
		settings.save_item("area", name=f.name, principles=["Fix the process first", "One system"])  # reordered
		self.assertEqual(focus.get(f.name)["principles"], ["Fix the process first", "One system"])
		self.assertEqual(focus.annual_for(f.name)["title"], "i57 annual")
		with self.assertRaises(frappe.ValidationError):
			focus.get(self.tea)

	def test_7_a_new_goal_cannot_be_open(self):
		frappe.flags.lifeos_allow_open_goals = False
		with self.assertRaises(frappe.ValidationError):
			goals.create(title="i57 open", horizon="Long term", space=PRIVATE)
		with self.assertRaises(frappe.ValidationError):  # no horizon and no date would be Open too
			goals.create(title="i57 open", space=PRIVATE)
		self.assertTrue(goals.create(title="i57 annual", horizon="Year", target_date="2027-03-01", space=PRIVATE)["name"])
		cycle = self.make("Life Cycle", title="i57 cycle", start_date="2026-11-02", end_date="2027-01-24", status="Active").name
		self.assertTrue(goals.create(title="i57 twelve", horizon="12 weeks", cycle=cycle, space=PRIVATE)["name"])
		year = goals.create(title="i57 to open", horizon="Year", target_date="2027-03-01", space=PRIVATE)["name"]
		with self.assertRaises(frappe.ValidationError):
			goals.update(year, {"horizon": "Long term"})

	def test_8_an_open_goal_is_marked_and_made_a_focus_with_an_annual_goal_holding_its_tasks(self):
		g = self.make("Life Goal", title="i57 RMT: improve systems", horizon="Long term", area=self.tea, done_when="Numbers by 9 am", notes_md="Ongoing work").name
		t = self.make("Life Task", title="i57 audit walk", goal=g, area=self.tea).name
		data = goals.by_area(space=PRIVATE, show="open")
		card = next(r for s in data["sections"] for grp in s["groups"] for r in grp["goals"] if r["name"] == g)
		self.assertEqual(card["to_sort"], 1)
		out = focus.sort_open(g, "focus", title="Systems on ERPNext", target_date="2027-03-31", done_when="All stores on ERPNext")
		self.assertEqual(frappe.db.get_value("Life Area", out["focus"], ["is_focus", "parent_area", "standard"]), (1, self.tea, "Numbers by 9 am"))
		annual = frappe.get_doc("Life Goal", out["annual"])
		self.assertEqual((annual.title, annual.horizon, annual.area), ("Systems on ERPNext", "Year", out["focus"]))
		self.assertEqual(frappe.db.get_value("Life Task", t, "goal"), annual.name)
		self.assertEqual(frappe.db.get_value("Life Goal", g, "outcome"), "Dropped")
		self.assertFalse(frappe.db.get_value("Life Task", t, "is_archived"))

	def test_an_open_goal_becomes_an_annual_goal_or_is_dropped(self):
		a = self.make("Life Goal", title="i57 a", horizon="Long term", area=self.tea).name
		b = self.make("Life Goal", title="i57 b", horizon="Long term", area=self.tea).name
		with self.assertRaises(frappe.ValidationError):
			focus.sort_open(a, "annual")
		focus.sort_open(a, "annual", target_date="2027-06-30")
		self.assertEqual(frappe.db.get_value("Life Goal", a, ["horizon", "target_date"], as_dict=True).horizon, "Year")
		focus.sort_open(b, "drop")
		self.assertEqual(frappe.db.get_value("Life Goal", b, "outcome"), "Dropped")

	def test_9_an_agent_cannot_create_or_switch_a_focus_but_can_file_under_one(self):
		f = self.focus("Yield")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Quality", "parent_area": self.tea, "is_focus": 1}).insert()
		doc = frappe.get_doc("Life Area", f.name)
		doc.standard = "changed"
		with self.assertRaises(frappe.PermissionError):
			doc.save()
		with self.assertRaises(frappe.PermissionError):
			settings.save_item("area", name=f.name, is_on=0)
		item = self.make("Life Task", title="i57 filed by the agent", area=f.name)
		self.assertEqual(item.area, f.name)

	def test_the_core_card_carries_each_focus_with_its_standard_and_principles(self):
		from lifeos import context

		self.focus("Yield", standard="Above 1,700 kg/ha")
		settings.save_item("area", name=frappe.db.get_value("Life Area", {"space": PRIVATE, "area_name": "Yield"}), principles=["One system"])
		card = context.card(PRIVATE, hidden=False)
		self.assertIn("Yield", card)
		self.assertIn("Above 1,700 kg/ha", card)
		self.assertIn("1. One system", card)
		use_focuses(False)
		context.changed()
		self.assertNotIn("Above 1,700 kg/ha", context.card(PRIVATE, hidden=False))


APP = os.path.dirname(os.path.dirname(__file__))


REPO = os.path.dirname(APP)


def set_planning(value):
	frappe.db.set_single_value("Life Settings", "planning_period", value)
	frappe.clear_cache(doctype="Life Settings")


class TestHorizon(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		frappe.db.delete("Life Cycle", {"space": PRIVATE})

	def tearDown(self):
		set_planning("12 Week Years")
		super().tearDown()

	def test_horizon_follows_the_target_date_and_the_cycle(self):
		now = getdate(today())
		self.assertEqual(derive_horizon(add_days(now.replace(day=1), 0), None, PRIVATE), "Month")
		next_march = now.replace(year=now.year + 1, month=3, day=15) if now.month >= 3 else now.replace(month=3, day=15)
		self.assertEqual(derive_horizon(next_march, None, PRIVATE), "Year")
		self.assertEqual(derive_horizon(add_months(now, 36), None, PRIVATE), "Long term")
		self.assertEqual(derive_horizon(None, None, PRIVATE), "Long term")
		cycle = self.make("Life Cycle", title="i60 cycle", start_date=today(), status="Active")
		self.assertEqual(derive_horizon(None, cycle.name, PRIVATE), "12 weeks")
		goal = self.make("Life Goal", title="i60 in the cycle", cycle=cycle.name)
		self.assertEqual(goal.horizon, "12 weeks")
		dated = self.make("Life Goal", title="i60 dated", target_date=add_months(now, 36))
		self.assertEqual(dated.horizon, "Long term")
		month = self.make("Life Goal", title="i60 this month", target_date=now)
		self.assertEqual(month.horizon, "Month")

	def test_a_date_inside_the_active_cycle_is_a_12_week_goal(self):
		cycle = self.make("Life Cycle", title="i60 cycle two", start_date=add_days(today(), -30), status="Active")
		d = add_days(cycle.start_date, 75) if getdate(add_days(cycle.start_date, 75)).month != getdate(today()).month else add_days(cycle.start_date, 80)
		self.assertEqual(derive_horizon(d, None, PRIVATE), "12 weeks")

	def test_quarters_follow_the_calendar_quarter(self):
		now = getdate(today())
		qm = ((now.month - 1) // 3) * 3 + 1
		other_month = qm + 2 if now.month != qm + 2 else qm
		in_quarter = now.replace(month=other_month, day=15)
		if (in_quarter.year, in_quarter.month) == (now.year, now.month):
			in_quarter = now.replace(month=qm + 1, day=15)
		self.make("Life Cycle", title="i60 away", start_date=add_days(today(), -300), status="Active")
		self.assertNotEqual(derive_horizon(in_quarter, None, PRIVATE), "12 weeks")  # 12 Week Years: no cycle covers it
		set_planning("Quarters")
		self.assertEqual(derive_horizon(in_quarter, None, PRIVATE), "12 weeks")
		goal = self.make("Life Goal", title="i60 quarter goal", target_date=in_quarter)  # needs no cycle
		self.assertEqual((goal.horizon, goal.cycle), ("12 weeks", None))

	def test_year_and_month_goals_need_a_date_and_only_12_weeks_has_a_cycle(self):
		self.assertRaises(frappe.ValidationError, self.make, "Life Goal", title="i60 year", horizon="Year")
		self.assertRaises(frappe.ValidationError, self.make, "Life Goal", title="i60 month", horizon="Month")
		cycle = self.make("Life Cycle", title="i60 cycle three", start_date=today(), status="Active")
		self.assertRaises(frappe.ValidationError, self.make, "Life Goal", title="i60 odd", horizon="Year", target_date=add_months(today(), 5), cycle=cycle.name)


# issue 72: the journal, the month-plan record, dimensions, important dates (now yearly Events) and what only they used
SIMPLIFIED_AWAY = ("Life Journal Page", "Life Check-in", "Life Check-in Score", "Life Month Plan", "Life Month Plan Habit", "Life Dimension",
	"Life Important Date")
SIMPLIFIED_CODE = ("lifeos.api.journal", "lifeos import journal", "api/journal", "review.piles", "review import piles", "pile_sort", "pile_actions",
	"components/journal", "pages/Reset", "components/weekly/piles", "lifeos.journal")


class TestRemoved(LifeTestCase):
	def test_the_old_records_are_gone(self):
		for dt in ("Life Month Plan Goal", "Life Idea", "Life Tag", "Life Tag Link", *SIMPLIFIED_AWAY):
			self.assertFalse(frappe.db.exists("DocType", dt), dt)
			self.assertFalse(frappe.db.table_exists(dt), dt)
		for dt in ("Life Task", "Life Note", "Life Inbox Item", "Life Vault Document", "Life Chat Log"):
			self.assertFalse(frappe.get_meta(dt).has_field("tags"), dt)
		self.assertFalse(frappe.get_meta("Life Goal").has_field("goal_type"))

	def test_no_code_names_them(self):
		banned = ("Life Idea", "Life Tag", *SIMPLIFIED_AWAY, *SIMPLIFIED_CODE)
		pattern_tags = ("tags", "tag_ids", "tags_csv")
		bad = []
		roots = [APP, os.path.join(REPO, "frontend", "src"), os.path.join(REPO, "agent")]
		skip = ("node_modules", "public", "patches", "__pycache__", "test_goals.py")
		for root in roots:
			for base, dirs, files in os.walk(root):
				dirs[:] = [d for d in dirs if d not in skip]
				for f in files:
					if f in skip or not f.endswith((".py", ".js", ".vue", ".md")):
						continue
					text = open(os.path.join(base, f), encoding="utf-8", errors="ignore").read()
					for word in banned:
						if word in text:
							bad.append((os.path.join(base, f), word))
					for line_no, line in enumerate(text.splitlines(), 1):
						if any(f'"{p}"' in line or f"'{p}'" in line or f".{p}" in line or f"{p}:" in line for p in pattern_tags):
							bad.append((os.path.join(base, f), f"line {line_no}: {line.strip()[:80]}"))
		self.assertEqual(bad, [])


class TestSomeday(LifeTestCase):
	def test_park_makes_a_someday_task_or_note_from_reset_old_inbox_and_the_weekly_review(self):
		t = self.make("Life Task", title="i60 reset", area=self.areas["Tea"])
		reset.decide("Life Task", t.name, "someday")
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Someday")
		t2 = self.make("Life Task", title="i60 pile", area=self.areas["Tea"])
		stale.settle(types.SimpleNamespace(state={}), t2.name, "someday")
		self.assertEqual(frappe.db.get_value("Life Task", t2.name, "status"), "Someday")
		made = inbox.create_item(space=PRIVATE, title="i60 old capture", source_type="Message", raw_text="a thought")
		before = {dt: frappe.db.count(dt) for dt in ("Life Task", "Life Note")}
		old_inbox.park(frappe.get_doc("Life Inbox Item", made["name"]))
		note = frappe.get_doc("Life Note", {"inbox_item": made["name"]})
		self.assertEqual((note.is_someday, bool(note.someday_review_on)), (1, True))
		self.assertEqual(frappe.db.count("Life Task"), before["Life Task"])
		self.assertEqual(frappe.db.count("Life Note"), before["Life Note"] + 1)

	def test_create_makes_a_someday_task_or_note(self):
		task = someday.create("i60 maybe", space=PRIVATE)
		self.assertEqual((task["doctype"], frappe.db.get_value("Life Task", task["name"], "status")), ("Life Task", "Someday"))
		note = someday.create("i60 thought", space=PRIVATE, as_note=1)
		self.assertEqual(frappe.db.get_value("Life Note", note["name"], "is_someday"), 1)
		rows = {r.name: r.type for r in someday.list(space=PRIVATE, page_length=100)["rows"]}
		self.assertEqual((rows[task["name"]], rows[note["name"]]), ("Task", "Note"))


class TestAgentProposals(LifeTestCase):
	def test_a_month_goal_proposal_is_accepted_as_a_goal_with_horizon_month(self):
		self.as_user(AGENT)
		made = inbox.create_item(space=PRIVATE, title="i60 agent", source_type="Message", raw_text="x")
		frappe.db.set_value("Life Inbox Item", made["name"], {"status": "Processing", "claimed_by": AGENT})
		now = getdate(today())
		out = inbox.submit_result(made["name"], summary_md="s", proposals=[
			{"kind": "Month Goal", "payload": {"title": "i60 old kind", "year": now.year, "month": now.month, "area": "Tea"}},
			{"kind": "Goal", "payload": {"title": "i60 new kind", "horizon": "Year", "target_date": "2027-03-01"}}])
		self.assertEqual(out["errors"], [])
		self.as_user(OWNER)
		from lifeos.api import review

		self.assertEqual(review.decide_all(made["name"], "accept")["errors"], [])
		goal = frappe.get_doc("Life Goal", {"title": "i60 old kind", "space": PRIVATE})
		self.assertEqual((goal.horizon, getdate(goal.target_date).month), ("Month", now.month))
		self.assertIn(goal.name, [g["row"] for g in rules.month_goals(PRIVATE, now.year, now.month)])
		self.assertEqual(frappe.db.get_value("Life Goal", {"title": "i60 new kind"}, "horizon"), "Year")


class TestSettings(LifeTestCase):
	# issue 11: areas are the seven areas of life with their parts; the seven are switched off, not archived, so only a part is
	# archived, and a part holds no parts of its own
	def test_archive_a_part_and_restore(self):
		career = self.life["Career"]
		part = settings.save_item("area", space=PRIVATE, title="ux3 part", parent_area=career)["name"]
		task = self.make("Life Task", title="ux3 filed under the part", area=part, status="Done")  # issue 12: open work must move first
		out = settings.save_item("area", name=part, is_archived=1)
		self.assertEqual(out["archived_children"], [])
		self.assertEqual(frappe.db.get_value("Life Area", part, "is_archived"), 1)
		self.assertEqual(str(frappe.db.get_value("Life Area", part, "archived_on")), today())
		# the records under it are not changed, and the pickers no longer offer it
		self.assertEqual(frappe.db.get_value("Life Task", task.name, ["area", "is_archived"]), (part, 0))
		self.assertNotIn(part, [a.name for a in area.tree(PRIVATE)["areas"]])
		got = settings.get(PRIVATE)
		row = next(a for a in got["areas"] if a.name == part)
		self.assertTrue(row.is_archived and row["count"] >= 1)
		# restored: back in place under its area of life
		settings.save_item("area", name=part, is_archived=0)
		self.assertEqual(frappe.db.get_value("Life Area", part, ["is_archived", "parent_area"]), (0, career))
		self.assertIsNone(frappe.db.get_value("Life Area", part, "archived_on"))
		self.assertRaises(frappe.ValidationError, settings.save_item, "area", name=career, is_archived=1)

	def test_reorder_and_nest(self):
		career, mind = self.life["Career"], self.life["Mind"]
		a = settings.save_item("area", space=PRIVATE, title="ux3 order a", parent_area=career)["name"]
		b = settings.save_item("area", space=PRIVATE, title="ux3 order b", parent_area=career)["name"]
		settings.reorder("area", frappe.as_json([b, a]), parent_area=career)
		self.assertLess(frappe.db.get_value("Life Area", b, "sort_order"), frappe.db.get_value("Life Area", a, "sort_order"))
		settings.reorder("area", frappe.as_json([a]), parent_area=mind)
		self.assertEqual(frappe.db.get_value("Life Area", a, "parent_area"), mind)
		# one level deep: a part under a part, or a part at the top, is refused
		c = settings.save_item("area", space=PRIVATE, title="ux3 order c", parent_area=career)["name"]
		self.assertRaises(frappe.ValidationError, settings.save_item, "area", name=c, parent_area=a)
		self.assertRaises(frappe.ValidationError, settings.save_item, "area", name=c, parent_area="")

	def test_habits_archive_and_leave_the_pickers(self):
		habit = settings.save_item("habit", space=PRIVATE, title="ux3 habit")["name"]
		settings.save_item("habit", name=habit, is_archived=1)
		from lifeos.api.inbox import space_context
		ctx = space_context(PRIVATE)
		self.assertNotIn(habit, [t.name for t in ctx["habits"]])

	def test_no_role_names_and_no_administrator(self):
		got = settings.get(PRIVATE)
		text = frappe.as_json(got)
		self.assertNotIn("Life Agent", text)
		self.assertNotIn("Life User", text)
		for s in got["spaces"]:
			self.assertNotIn("Administrator", [m["user"] for m in s["members"]])
		# issue 1: agents are listed with people in Members, marked by kind, and again in Agents
		self.assertTrue(any(m["user"] == AGENT and m["is_agent"] for s in got["spaces"] for m in s["members"]))
		self.assertIn(AGENT, [a["user"] for a in got["agents"]])


class TestAgentsAndTheVault(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		self.as_user(OWNER)
		self.doc = self.make("Life Vault Document", title="ux3 secret passport", doc_type="ID", area=self.areas["Tea"],
			expiry_date=add_days(today(), 20), notes_md="ux3vaultword")
		self.file = frappe.get_doc({"doctype": "File", "file_name": "ux3-secret.txt", "content": b"secret", "is_private": 1,
			"attached_to_doctype": "Life Vault Document", "attached_to_name": self.doc.name}).insert()
		self.make("Life Note", title="ux3 note that links", content_md="see [[ux3 secret passport]]", area=self.areas["Tea"])

	def can_see(self):
		"""What the session user can reach of the document, by every path that returns records."""
		seen = {}
		try:
			vault.get(self.doc.name)
			seen["get"] = True
		except (frappe.DoesNotExistError, frappe.PermissionError):
			seen["get"] = False
		seen["list"] = any(d.name == self.doc.name for d in vault.list(space=PRIVATE)["documents"])
		seen["count"] = vault.list(space=PRIVATE, filters=frappe.as_json([["title", "like", "ux3 secret%"]]))["total"] > 0
		seen["rest"] = bool(frappe.get_list("Life Vault Document", filters={"name": self.doc.name}))
		seen["index"] = bool(frappe.get_list("Life Index", filters={"ref_name": self.doc.name}))
		seen["search"] = any(r.ref_name == self.doc.name for r in search.query("ux3vaultword")["results"])
		entries = [e for d in timeline.get(space=PRIVATE, page_length=200)["days"] for e in d["entries"]]
		seen["timeline"] = any(e.ref_name == self.doc.name for e in entries)
		# area pages went in set 6: the lens narrows the timeline to the area instead
		lens = [e for d in timeline.get(space=PRIVATE, area=self.areas["Tea"], page_length=200)["days"] for e in d["entries"]]
		seen["area"] = any(e.ref_name == self.doc.name for e in lens)
		seen["file"] = bool(frappe.has_permission("File", "read", self.file))
		seen["suggest"] = any(r["name"] == self.doc.name for r in links.suggest(space=PRIVATE, text="ux3 secret"))
		return seen

	def test_switch_off_hides_everything_from_the_agent(self):
		self.as_user(AGENT)
		seen = self.can_see()
		self.assertFalse(any(seen.values()), seen)
		# the same answer as a record that does not exist
		self.assertRaises(frappe.DoesNotExistError, vault.get, self.doc.name)

	def test_switch_on_lets_the_agent_read(self):
		self.as_user(OWNER)
		settings.set_agent_vault(PRIVATE, 1)
		self.as_user(AGENT)
		seen = self.can_see()
		self.assertTrue(all(seen.values()), seen)

	def test_people_are_not_affected(self):
		self.as_user(OWNER)
		self.assertTrue(all(self.can_see().values()))
		settings.set_agent_vault(PRIVATE, 1)
		self.as_user(OWNER)
		self.assertTrue(all(self.can_see().values()))

	def test_only_an_admin_changes_the_switch(self):
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, settings.set_agent_vault, SHARED, 1)
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, settings.set_agent_vault, PRIVATE, 1)


class TestDeskAndRoles(LifeTestCase):
	def test_life_user_and_agent_roles_have_no_desk_access(self):
		self.assertEqual(frappe.db.get_value("Role", "Life User", "desk_access"), 0)
		self.assertEqual(frappe.db.get_value("Role", "Life Agent", "desk_access"), 0)
		self.assertEqual(frappe.db.get_value("User", FAMILY, "user_type"), "Website User")
		self.assertEqual(frappe.db.get_value("User", AGENT, "user_type"), "Website User")

	def test_agent_with_a_person_role_is_refused(self):
		frappe.set_user("Administrator")
		user = frappe.get_doc("User", AGENT)
		user.append("roles", {"role": "Life User"})
		self.assertRaises(frappe.ValidationError, user.save)


class TestGoals(LifeTestCase):
	def test_types_and_validation(self):
		self.assertRaises(frappe.ValidationError, goals.create, "ux3 annual no date", "Year", space=PRIVATE)
		g = goals.create("ux3 annual", "Year", space=PRIVATE, target_date="2026-12-31", area=self.areas["Tea"])
		self.assertIsNone(frappe.db.get_value("Life Goal", g["name"], "cycle"))
		self.assertRaises(frappe.ValidationError, goals.create, "ux3 12wy no cycle", "12 weeks", space=PRIVATE)
		doc = frappe.get_doc("Life Goal", g["name"])
		doc.cycle = "nonexistent"
		self.assertRaises(Exception, doc.save)

	def test_task_completion(self):
		g = goals.create("ux3 open goal", "Long term", space=PRIVATE, area=self.areas["Tea"])["name"]
		self.assertEqual(goals.task_counts([g]), {})
		t1 = self.make("Life Task", title="ux3 g1", goal=g)
		self.make("Life Task", title="ux3 g2", goal=g)
		t3 = self.make("Life Task", title="ux3 g3", goal=g)
		tasks.set_status(t1.name, "Done")
		tasks.set_status(t3.name, "Dropped")
		self.assertEqual(goals.task_counts([g])[g], (1, 2))
		from lifeos.api import archive as archive_api
		archive_api.set("Life Task", t1.name)
		self.assertEqual(goals.task_counts([g])[g], (1, 2))  # archiving a done task does not lower the figure
		rows = goals.list(space=PRIVATE, filters=frappe.as_json([["title", "like", "ux3 open goal"]]))["goals"]
		self.assertEqual((rows[0].tasks_done, rows[0].tasks_counted, rows[0].score), (1, 2, None))

	def test_list_tabs_and_close(self):
		g = goals.create("ux3 closable", "Long term", space=PRIVATE)["name"]
		mine = frappe.as_json([["title", "like", "ux3 closable"]])
		self.assertEqual(goals.list(space=PRIVATE, filters=mine)["tabs"], {"in_progress": 1, "achieved": 0, "closed": 0, "someday": 0, "all": 1})
		goals.close(g, "Dropped", "not now")
		self.assertEqual(str(frappe.db.get_value("Life Goal", g, "closed_on")), today())
		tabs = goals.list(space=PRIVATE, filters=mine)["tabs"]
		self.assertEqual(tabs, {"in_progress": 0, "achieved": 0, "closed": 1, "someday": 0, "all": 1})
		self.assertEqual(goals.list(space=PRIVATE, state="closed", filters=mine)["total"], 1)

	def test_add_to_cycle_keeps_tasks(self):
		cycle = frappe.get_doc({"doctype": "Life Cycle", "space": PRIVATE, "title": "ux3 cycle", "start_date": add_days(today(), -7), "status": "Active"}).insert()
		g = goals.create("ux3 moving", "Long term", space=PRIVATE)["name"]
		t = self.make("Life Task", title="ux3 moving task", goal=g)
		self.assertNotIn(g, [x["name"] for x in goals.across_cycles(space=PRIVATE)["cycles"][0]["goals"]] if goals.across_cycles(space=PRIVATE)["cycles"] else [])
		goals.add_to_cycle(g, cycle.name)
		self.assertEqual(frappe.db.get_value("Life Goal", g, ["horizon", "cycle", "carried_from"]), ("12 weeks", cycle.name, None))
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "goal"), g)
		self.assertIn(g, [x["name"] for x in rules.grid(cycle.name)["goals"]])

	def test_agents_cannot_create_or_close(self):
		g = goals.create("ux3 agent goal", "Long term", space=PRIVATE)["name"]
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, goals.create, "ux3 by agent", "Long term", space=PRIVATE)
		self.assertRaises(frappe.PermissionError, goals.close, g, "Achieved")

	def test_other_space_member_sees_no_goals_or_counts(self):
		g = goals.create("ux3 private goal", "Long term", space=PRIVATE)["name"]
		self.make("Life Task", title="ux3 private goal task", goal=g)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, goals.list, space=PRIVATE)
		self.assertEqual(goals.task_counts([g]), {})
		self.assertNotIn(g, [x.name for x in goals.list(space=SHARED, state="all")["goals"]])
