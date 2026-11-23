"""Tests for review."""
import os
from datetime import datetime, timedelta

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

from lifeos.goals import cycles as rules, readings
from lifeos.tasks import weekplan
from lifeos.goals import habits as habit_rules
from lifeos.api import calendar, goals, library as library_api, outbox as outbox_api, periodic, settings, settings as settings_api, sources, today as today_api, week, weekly
from lifeos.review import findings, periodic as rv_rules
from lifeos.review.record import period_text, Review
from lifeos.tests.base import AGENT, AGENT as AGENT_USER, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import CalCase, gevent, GoalsCase, item, ME, ReviewCase, set_key, task, tidy


# October 2026 ended on Saturday 31 October; the review day is Sunday, so the monthly review is due from Sunday 1 November
NOV_1, OCT_31 = "2026-11-01", "2026-10-31"


class TestReviews(LifeTestCase):
	def setUp(self):
		super().setUp()
		for dt in ("Life Review", "Life Goal", "Life Cycle", "Life Habit"):
			frappe.db.delete(dt, {"space": PRIVATE})
		frappe.db.set_single_value("Life Settings", "weekly_review_day", "Sunday")
		frappe.db.set_single_value("Life Settings", "cycle_break_week", 1)
		frappe.clear_cache(doctype="Life Settings")
		frappe.conf.lifeos_test_clock = 1

	def tearDown(self):
		frappe.conf.pop("lifeos_test_clock", None)
		super().tearDown()

	def october(self):
		return [rules.add_month_goal(PRIVATE, 2026, 10, f"i47 goal {i}", self.area()) for i in range(3)]

	def area(self):
		return self.areas["Personal"]

	def test_monthly_review_is_due_from_the_first_review_day_until_locked(self):
		goals = self.october()
		me = (PRIVATE, OWNER)
		self.assertIsNone(rv_rules.month_due(*me, day=OCT_31))
		self.assertIsNone(rv_rules.month_due(*me, day="2026-10-20"))
		self.assertEqual(rv_rules.month_due(*me, day=NOV_1)["month"], 10)
		self.assertEqual(rv_rules.month_due(*me, day="2026-11-04")["month"], 10)  # until done
		self.assertEqual([d["kind"] for d in rv_rules.due(*me, day=NOV_1)], ["weekly", "monthly"])  # weekly first, then monthly
		for g in goals:
			periodic.decide(space=PRIVATE, kind="monthly", goal=g.name, pile="drop", reason="not now", at=f"{NOV_1} 10:00")
		periodic.visit(space=PRIVATE, kind="monthly", tab="look", at=f"{NOV_1} 10:00")
		periodic.plan_save(space=PRIVATE, kind="monthly", extra=[{"title": "i47 new", "area": self.area()}], confirm=1, at=f"{NOV_1} 10:00")
		periodic.lock(space=PRIVATE, kind="monthly", went_well="Shipped it", at=f"{NOV_1} 10:00")
		self.assertIsNone(rv_rules.month_due(*me, day="2026-11-04"))
		self.assertNotIn("monthly", [d["kind"] for d in rv_rules.due(*me, day="2026-11-04")])

	def test_a_month_with_nothing_in_it_is_not_due(self):
		self.assertIsNone(rv_rules.month_due(PRIVATE, OWNER, day=NOV_1))

	def test_cycle_review_is_due_on_the_last_day_and_replaces_the_weekly_one(self):
		cycle = self.make("Life Cycle", title="i47 cycle", start_date="2026-10-05", status="Active")
		self.assertEqual(str(cycle.end_date), "2026-12-27")
		me = (PRIVATE, OWNER)
		self.assertIsNone(rv_rules.cycle_due(PRIVATE, day="2026-12-26"))
		self.assertEqual([d["kind"] for d in rv_rules.due(*me, day="2026-12-27")], ["12-weeks"])
		self.assertFalse(rv_rules.weekly_due(*me, day="2026-12-27"))
		self.assertEqual([d["kind"] for d in rv_rules.due(*me, day="2026-12-30")], ["12-weeks"])  # the break week, until done
		self.assertEqual([d["kind"] for d in rv_rules.due(*me, day="2026-12-20")], ["weekly"])

	def test_locking_the_monthly_review_writes_next_months_plan(self):
		goals = self.october()
		habit = self.make("Life Habit", title="i47 walk").name
		habit_rules.set_month_habits(PRIVATE, 2026, 10, [{"habit": habit, "days_per_week": 5}])
		at = f"{NOV_1} 10:00"
		task = self.make("Life Task", title="i47 task", goal=goals[0].name, status="Open").name
		look = periodic.look(space=PRIVATE, kind="monthly", at=at)
		self.assertEqual([g["title"] for g in look["goals"]], ["i47 goal 0", "i47 goal 1", "i47 goal 2"])
		self.assertEqual(look["habits"][0]["title"], "i47 walk")
		periodic.decide(space=PRIVATE, kind="monthly", goal=goals[0].name, pile="carry", at=at)
		periodic.decide(space=PRIVATE, kind="monthly", goal=goals[1].name, pile="drop", reason="Not worth it", at=at)
		with self.assertRaises(frappe.ValidationError):
			periodic.lock(space=PRIVATE, kind="monthly", went_well="x", at=at)  # goal 2 is undecided
		periodic.decide(space=PRIVATE, kind="monthly", goal=goals[2].name, pile="finish", date="2026-11-10", at=at)
		area = self.area()
		out = periodic.plan_save(space=PRIVATE, kind="monthly", extra=[{"title": "i47 second", "area": area}, {"title": "i47 third", "area": area}], confirm=1, at=at)
		self.assertEqual([g["title"] for g in out["goals"]], ["i47 goal 0", "i47 second", "i47 third"])  # carried first
		res = periodic.lock(space=PRIVATE, kind="monthly", went_well="Good", not_well="Slow", change="Start earlier", at=at)
		self.assertEqual(res["header"]["status"], "Locked")
		nov = [g["title"] for g in rules.month_goals(PRIVATE, 2026, 11)]
		self.assertEqual([t for t in nov if t != "i47 goal 2"], ["i47 goal 0", "i47 second", "i47 third"])  # carried first, then in the order given
		self.assertIn("i47 goal 2", nov)  # the finished-later goal is dated in November
		self.assertEqual(frappe.db.get_value("Life Goal", goals[0].name, "outcome"), "Carried")
		self.assertEqual(frappe.db.get_value("Life Goal", goals[1].name, "outcome"), "Dropped")
		self.assertEqual(frappe.db.get_value("Life Goal", goals[1].name, "result_note"), "Not worth it")
		self.assertEqual(str(frappe.db.get_value("Life Goal", goals[2].name, "target_date")), "2026-11-10")
		self.assertNotEqual(frappe.db.get_value("Life Task", task, "goal"), goals[0].name)  # the task went with the carried goal
		self.assertEqual([h["habit"] for h in habit_rules.habits_month(PRIVATE, 2026, 11)["habits"]], [habit])
		doc = frappe.get_doc("Life Review", res["header"]["name"])
		self.assertEqual((doc.kind, doc.went_well, doc.do_differently), ("Monthly", "Good", "Start earlier"))

	def test_a_review_left_half_done_resumes_where_it_was(self):
		goals = self.october()
		at = f"{NOV_1} 10:00"
		periodic.decide(space=PRIVATE, kind="monthly", goal=goals[0].name, pile="carry", at=at)
		periodic.decide(space=PRIVATE, kind="monthly", goal=goals[1].name, pile="drop", reason="No", at=at)
		periodic.visit(space=PRIVATE, kind="monthly", tab="look", at=at)
		again = periodic.start(space=PRIVATE, kind="monthly", at=f"{add_days(getdate(NOV_1), 2)} 09:00")
		self.assertEqual(again["first"], "decide")  # goal 2 is still undecided
		rows = {r["name"]: r["decision"] for r in periodic.decisions(space=PRIVATE, kind="monthly", at=at)["goals"]}
		self.assertEqual(rows[goals[0].name]["pile"], "carry")
		self.assertEqual(rows[goals[1].name]["reason"], "No")
		self.assertIsNone(rows[goals[2].name])
		self.assertEqual(frappe.db.count("Life Review", {"space": PRIVATE, "kind": "Monthly"}), 1)

	def cycle_with_goals(self):
		cycle = self.make("Life Cycle", title="i47 cycle", start_date="2026-10-05", status="Active")
		area = self.area()
		made = []
		for i, per in enumerate((3, 2, 1)):
			g = frappe.get_doc({"doctype": "Life Goal", "space": PRIVATE, "cycle": cycle.name, "horizon": "12 weeks", "title": f"i47 cg {i}", "area": area, "sort_order": i,
				"done_when": f"finished {i}", "actions": [{"title": f"act {i}", "per_week": per, "status": "Open"}]}).insert()
			made.append(g)
		for w in (1, 2, 3):
			rules.set_tick(made[0].actions[0].name, w, 2)
		return cycle, made

	def test_cycle_review_score_matches_the_cycle_view(self):
		cycle, made = self.cycle_with_goals()
		at = "2026-12-27 10:00"
		score = periodic.look(space=PRIVATE, kind="12-weeks", at=at)
		grid = rules.grid(cycle.name)
		self.assertEqual(len(score["weeks"]), 12)
		self.assertEqual(score["average"], grid["average"])
		self.assertEqual([g["name"] for g in score["goals"]], [g.name for g in made])

	def test_locking_the_cycle_review_closes_it_with_the_same_score_and_makes_the_next(self):
		cycle, made = self.cycle_with_goals()
		at = "2026-12-27 10:00"
		expected = rules.cycle_average(cycle, rules._actions(cycle.name), rules._ticks(cycle.name), rules.WEEKS)
		periodic.decide(space=PRIVATE, kind="12-weeks", goal=made[0].name, pile="done", at=at)
		periodic.decide(space=PRIVATE, kind="12-weeks", goal=made[1].name, pile="carry", at=at)
		periodic.decide(space=PRIVATE, kind="12-weeks", goal=made[2].name, pile="drop", reason="Out of scope", at=at)
		plan = periodic.plan(space=PRIVATE, kind="12-weeks", at=at)
		self.assertEqual(plan["dates"]["start"], "2026-12-28")
		self.assertEqual([g["title"] for g in plan["goals"]], ["i47 cg 1"])
		periodic.plan_save(space=PRIVATE, kind="12-weeks", edits={made[1].name: {"done_when": "shipped by March", "actions": [{"title": "weekly push", "per_week": 4}]}},
			extra=[{"title": "i47 new goal", "area": self.area(), "done_when": "live", "actions": [{"title": "write", "per_week": 2}]}], confirm=1, at=at)
		res = periodic.lock(space=PRIVATE, kind="12-weeks", went_well="Learned a lot", at=at)
		old = frappe.get_doc("Life Cycle", cycle.name)
		self.assertEqual((old.status, old.final_score), ("Closed", expected))
		self.assertEqual(res["final_score"], expected)
		self.assertEqual([frappe.db.get_value("Life Goal", g.name, "outcome") for g in made], ["Achieved", "Carried", "Dropped"])
		new = frappe.get_doc("Life Cycle", res["next_cycle"])
		self.assertEqual((str(new.start_date), new.status), ("2026-12-28", "Planned"))
		goals = frappe.get_all("Life Goal", filters={"cycle": new.name}, fields=["name", "title", "done_when", "carried_from"], order_by="sort_order asc")
		self.assertEqual([g.title for g in goals], ["i47 cg 1", "i47 new goal"])
		self.assertEqual(goals[0].carried_from, made[1].name)
		self.assertEqual(goals[0].done_when, "shipped by March")
		acts = frappe.get_doc("Life Goal", goals[0].name).actions
		self.assertEqual([(a.title, a.per_week) for a in acts], [("weekly push", 4)])
		self.assertEqual(frappe.db.count("Life Review", {"space": PRIVATE, "kind": "12 Weeks", "status": "Locked"}), 1)
		later = rv_rules.due(PRIVATE, OWNER, day="2027-01-03")  # the cycle is closed: the weekly review is back
		self.assertEqual([d["kind"] for d in later], ["weekly"])

	def test_agents_cannot_start_a_review(self):
		self.october()
		self.as_user(AGENT_USER)
		with self.assertRaises(frappe.PermissionError):
			periodic.start(space=PRIVATE, kind="monthly", at=f"{NOV_1} 10:00")


def lock(space, user, start, end):
	return frappe.get_doc({"doctype": "Life Review", "space": space, "user": user, "status": "Locked", "period_start": start,
		"period_end": end, "locked_on": now_datetime(), "title": "x", "tab_state": "{}"}).insert(ignore_permissions=True)


class TestPeriod(ReviewCase):
	def test_first_review_is_the_last_seven_days(self):
		start, end = Review.period(PRIVATE, OWNER, "2026-11-22")
		self.assertEqual((str(start), str(end)), ("2026-11-16", "2026-11-22"))
		self.assertEqual(period_text(start, end), "Week of 16 to 22 November")

	def test_since_the_last_locked_review(self):
		lock(PRIVATE, OWNER, "2026-11-09", "2026-11-15")
		start, end = Review.period(PRIVATE, OWNER, "2026-11-22")
		self.assertEqual(str(start), "2026-11-16")

	def test_a_skipped_week_is_said(self):
		lock(PRIVATE, OWNER, "2026-11-02", "2026-11-08")
		start, end = Review.period(PRIVATE, OWNER, "2026-11-22")
		self.assertEqual(str(start), "2026-11-09")
		self.assertEqual(period_text(start, end), "Covers 9 to 22 November (you skipped last week)")
		self.assertEqual(period_text("2026-10-28", "2026-11-03"), "Week of 28 October to 3 November")

	def test_one_open_review_and_its_owner_only(self):
		weekly.start(space=PRIVATE)
		weekly.start(space=PRIVATE)
		self.assertEqual(frappe.db.count("Life Review", {"space": PRIVATE, "user": OWNER, "status": "Open"}), 1)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Life Review", "space": PRIVATE, "user": OWNER, "period_start": today(), "period_end": today()}).insert()
		# another member of a shared space neither sees nor opens the owner's review
		weekly.start(space=SHARED)
		self.as_user(FAMILY)
		self.assertFalse(frappe.get_list("Life Review", filters={"space": SHARED, "user": OWNER}))
		self.assertIsNone(weekly.get(space=SHARED)["name"])


class TestResumeAndGates(ReviewCase):
	def test_read_before_the_first_change_writes_nothing(self):
		head = weekly.get(space=PRIVATE)
		self.assertIsNone(head["name"])
		self.assertEqual(head["first"], "library")
		self.assertEqual(frappe.db.count("Life Review", {"space": PRIVATE}), 0)

	def test_resume_after_pause_and_tab_gates(self):
		stuck = self.task("s8 stuck", age=70)
		self.cycle_goal("s8 resume goal")  # a goal to plan, so the Goals tab is not done by having nothing in it
		head = weekly.start(space=PRIVATE)
		self.assertTrue(head["openable"]["tasks"])  # Library never blocks
		self.assertFalse(head["openable"]["goals"])
		self.assertFalse(head["done"]["library"])
		weekly.visit(space=PRIVATE, tab="library")
		weekly.settle_stale(task=stuck, decision="someday", space=PRIVATE)
		# pause: leave and come back; everything is where it was
		frappe.local.response = frappe._dict()
		head = weekly.start(space=PRIVATE)
		self.assertTrue(head["done"]["library"])
		self.assertTrue(head["done"]["tasks"])
		self.assertEqual(head["first"], "goals")
		self.assertEqual(weekly.stale_tasks(space=PRIVATE)["left"], 0)
		self.assertEqual(frappe.db.get_value("Life Task", stuck, "status"), "Someday")


class TestStaleTasks(ReviewCase):
	"""The Tasks tab lists the stale tasks once, each with Keep, Someday and Drop (issue 72; it replaced the piles board)."""

	def test_the_list_holds_the_stale_tasks_and_not_the_new_ones(self):
		frappe.set_user(OWNER)
		old, waiting, ancient = self.task("s8 old", age=70), self.task("s8 asked", age=40, status="Waiting", waiting_on="Ruchi"), self.task("s8 ancient", age=130)
		fresh, new = self.task("s8 recent", age=5), self.task("s8 came this week", age=40, created_days=1)
		weekly.start(space=PRIVATE)
		got = weekly.stale_tasks(space=PRIVATE)
		names = [r["name"] for r in got["tasks"]]
		self.assertEqual(names[:3], [ancient, old, waiting])  # the oldest first
		self.assertNotIn(fresh, names)
		self.assertNotIn(new, names)  # came in during the period
		self.assertEqual((got["left"], got["decided"]), (len(names), 0))
		self.assertEqual(got["tasks"][1]["age"], 70)

	def test_each_button_does_what_it_says(self):
		keep, someday, drop = self.task("s8 k", age=40), self.task("s8 p", age=70), self.task("s8 l", age=130)
		weekly.start(space=PRIVATE)
		weekly.settle_stale(task=keep, decision="keep", space=PRIVATE)
		self.assertEqual(frappe.db.get_value("Life Task", keep, "status"), "Open")
		self.assertEqual(str(frappe.db.get_value("Life Task", keep, "last_touched_on")), today())
		weekly.settle_stale(task=someday, decision="someday", space=PRIVATE)
		out = weekly.settle_stale(task=drop, decision="drop", space=PRIVATE)
		self.assertEqual([frappe.db.get_value("Life Task", n, "status") for n in (keep, someday, drop)], ["Open", "Someday", "Dropped"])
		self.assertEqual(self.exits(someday), ["Parked"])
		self.assertEqual(self.exits(drop), ["Discarded"])
		self.assertEqual((out["stale"]["decided"], out["stale"]["tasks"]), (3, []))
		self.assertTrue(out["header"]["done"]["tasks"])  # nothing left to decide
		self.assertRaises(frappe.ValidationError, weekly.settle_stale, task=keep, decision="later", space=PRIVATE)

	def test_agents_are_refused(self):
		from lifeos.tests.base import AGENT

		self.as_user(AGENT)
		for fn, kw in ((weekly.get, {}), (weekly.start, {}), (weekly.stale_tasks, {}), (weekly.settle_stale, {"task": "x", "decision": "keep"})):
			with self.assertRaises(frappe.PermissionError):
				fn(space=PRIVATE, **kw)


class LibCase(CalCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Review", {"space": PRIVATE})


class TestLibrary(LibCase):
	def test_came_in_counts_open_lists_with_exactly_that_many_rows(self):
		self.capture("s8 voice", get_datetime(f"{self.day} 09:00"))
		self.capture("s8 mail", get_datetime(f"{self.day} 09:00"), kind="Email")
		got = weekly.library(space=PRIVATE)
		rows = {r["key"]: r for r in got["came_in"]["rows"]}
		for key in ("captures", "chats", "emails"):
			q = rows[key]["to"]["query"]
			listed = sources.list(space=PRIVATE, tab=q.get("tab") or "all", from_date=q["from"], to_date=q["to"], filters=q.get("f"), page_length=500)
			self.assertEqual(rows[key]["n"], len(listed["sources"]), key)
		self.assertGreaterEqual(rows["captures"]["n"], 1)
		self.assertGreaterEqual(rows["emails"]["n"], 1)
		notes = library_api.list(space=PRIVATE, filters=rows["notes"]["to"]["query"]["f"], collection="all", page_length=500)
		self.assertEqual(rows["notes"]["n"], notes["total"])
		self.assertEqual(got["came_in"]["total"], sum(r["n"] for r in rows.values()))

	def test_strip_meeting_and_a_task_planned_from_it(self):
		fake = frappe.local.conf.get("lifeos_fake_calendar")
		frappe.local.conf.lifeos_fake_calendar = 0
		try:
			self.assertIsNone(weekly.library(space=PRIVATE)["strip"])  # no calendar: one line instead
		finally:
			frappe.local.conf.lifeos_fake_calendar = fake
		m = self.read(gevent("lib", f"{self.day} 15:00", 60, "Dalmia: blend sheet", [ME, "mithun@dalmia.example"]))["Dalmia: blend sheet"].name
		voice = self.capture("2 min, recorded 16:20", get_datetime(f"{self.day} 16:20"))
		weekly.start(space=PRIVATE)  # links what was captured
		strip = weekly.library(space=PRIVATE)["strip"]
		cell = next(e for d in strip["days"] for e in d["events"] if e["name"] == m)
		self.assertEqual((cell["matters"], cell["mark"]), (True, "linked"))
		detail = weekly.meeting(space=PRIVATE, event=m)
		self.assertEqual([l["name"] for l in detail["linked"]], [voice])
		goal = self.make("Life Goal", title="s8 Lotwise pilot", horizon="Long term")
		out = weekly.meeting_plan(space=PRIVATE, event=m, title="Send Mithun the lot sizes", goal=goal.name)
		self.assertEqual(frappe.db.get_value("Life Task", out["task"], "goal"), goal.name)
		self.assertIn(out["task"], [l["name"] for l in weekly.meeting(space=PRIVATE, event=m)["linked"]])
		self.assertEqual(weekly.meetings_list(space=PRIVATE)["rows"][0]["name"], m)

	def test_revelations_at_most_five_and_how_many_are_left(self):
		for i in range(7):
			findings.add(PRIVATE, "Promise", f"s8 promise {i}", [{"ref_doctype": "Life Goal", "ref_name": self.make("Life Goal", title=f"s8 g{i}", horizon="Long term").name}],
				[{"kind": "make_task", "label": "Make task", "title": f"s8 task {i}"}, {"kind": "dismiss", "label": "Not needed"}], source="AI")
		weekly.start(space=PRIVATE)
		got = weekly.library(space=PRIVATE)
		self.assertEqual((len(got["revelations"]), got["revelations_shown"]), (5, 5))
		first, second = got["revelations"][0], got["revelations"][1]
		out = weekly.finding_act(space=PRIVATE, insight=first["name"], index=0)
		self.assertTrue(frappe.db.exists("Life Task", out["task"]))
		weekly.finding_act(space=PRIVATE, insight=second["name"], index=1)
		self.assertEqual(frappe.db.get_value("Life Insight", second["name"], "status"), "Dismissed")
		got = weekly.library(space=PRIVATE)
		self.assertEqual((len(got["revelations"]), got["revelations_shown"]), (3, 5))  # "3 left", the next two do not move in


class TestReadingFromRevelations(LibCase):
	def test_confirm_a_reading_from_the_review(self):
		goal = self.make("Life Goal", title="s8 yield rev", horizon="Long term", measure_kind="Number", measure="yield", unit="kg/ha", start_value=1000, target_value=1800)
		r = frappe.get_doc({"doctype": "Life Goal Reading", "space": PRIVATE, "goal": goal.name, "date": today(), "value": 1460, "status": "Suggested",
			"suggested_by": "Agent", "excerpt": "1460 kg/ha"}).insert()
		weekly.start(space=PRIVATE)
		ins = frappe.db.get_value("Life Insight", {"reading": r.name})
		weekly.finding_act(space=PRIVATE, insight=ins, index=0)
		self.assertEqual(frappe.db.get_value("Life Goal", goal.name, "current_value"), 1460)
		self.assertEqual(frappe.db.get_value("Life Insight", ins, "status"), "Acted")


class TestTasksTab(ReviewCase):
	def test_left_your_plate_counts_open_lists_with_that_many_rows(self):
		done = self.make("Life Task", title="s8 plate done", status="Open")
		done.status = "Done"
		done.save()
		parked = self.task("s8 plate park", age=70)
		weekly.start(space=PRIVATE)
		weekly.settle_stale(task=parked, decision="someday", space=PRIVATE)
		got = weekly.plate(space=PRIVATE)
		by = {x["pile"]: x for x in got["piles"]}
		self.assertGreaterEqual(by["Done"]["n"], 1)
		self.assertGreaterEqual(by["Parked"]["n"], 1)
		for x in [*got["piles"], got["in"], got["out"]]:
			q = x["to"]["query"]
			listed = outbox_api.list(space=PRIVATE, pile=q["pile"], from_date=q["from"], to_date=q["to"], page_length=500)
			self.assertEqual(x["n"], listed["total"])
			self.assertEqual(x["n"], len(listed["rows"]))
		self.assertEqual(got["out"]["n"], sum(x["n"] for x in got["piles"]))

	def test_next_goals_opens_when_every_stale_task_is_decided(self):
		goal = self.cycle_goal("s8 tasks goal")
		needs = self.task("s8 tasks needs", age=40, goal=goal.name)
		old = self.task("s8 tasks old", age=70)
		head = weekly.start(space=PRIVATE)
		self.assertFalse(head["done"]["tasks"])
		weekly.settle_stale(task=needs, decision="keep", space=PRIVATE)
		self.assertFalse(weekly.get(space=PRIVATE)["done"]["tasks"])
		head = weekly.settle_stale(task=old, decision="someday", space=PRIVATE)["header"]
		self.assertTrue(head["done"]["tasks"])
		self.assertEqual(frappe.db.get_value("Life Task", old, "status"), "Someday")


class TestPrefill(GoalsCase):
	def test_the_prefill_order(self):
		g = self.goals[0]
		self.assertEqual((self.row(g)["plan"]["next_action"], self.row(g)["plan"]["source"]), ("", "empty"))  # nothing yet
		oldest = self.make("Life Task", title="s8 oldest task", goal=g, status="Open").name
		self.make("Life Task", title="s8 newer task", goal=g, status="Open")
		frappe.db.delete("Life Review", {"space": PRIVATE})
		self.assertEqual(self.row(g)["plan"]["task"], oldest)
		weekly.start(space=PRIVATE)
		# a task made for this goal in Library comes first
		ev = frappe.get_doc({"doctype": "Event", "subject": "s8 meeting", "starts_on": f"{today()} 09:00:00", "ends_on": f"{today()} 10:00:00",
			"life_space": PRIVATE, "event_type": "Public"}).insert(ignore_permissions=True)
		made = weekly.meeting_plan(space=PRIVATE, event=ev.name, title="s8 from the meeting", goal=g)["task"]
		p = self.row(g)["plan"]
		self.assertEqual((p["task"], p["next_action"], p["source"]), (made, "s8 from the meeting", "review"))
		# what the owner typed wins over everything
		weekly.goal_save(space=PRIVATE, goal=g, values={"next_action": "s8 my own action", "task": None})
		self.assertEqual(self.row(g)["plan"]["next_action"], "s8 my own action")

	def test_the_assistant_fills_what_has_no_task(self):
		set_key("fake-site-model")
		frappe.set_user("owner@lifeos.test")
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 1)
		try:
			weekly.start(space=PRIVATE)
			p = self.row(self.goals[1])["plan"]
			self.assertEqual((p["next_action"], p["source"]), ("Plan the next step for s8 cycle goal 1", "assistant"))
		finally:
			frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 0)

	def test_slots_do_not_overlap(self):
		weekly.start(space=PRIVATE)
		got = [(r["plan"]["slot"], r["plan"]["minutes"]) for r in self.tab()["rows"] if r["plan"]["slot"]]
		spans = sorted((frappe.utils.get_datetime(s), frappe.utils.get_datetime(s) + frappe.utils.datetime.timedelta(minutes=m)) for s, m in got)
		self.assertTrue(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])))


class TestStarsSkipsAndGate(GoalsCase):
	def test_exactly_three_stars_and_skip_needs_a_reason(self):
		for g in self.goals:
			weekly.goal_save(space=PRIVATE, goal=g, values={"next_action": f"act on {g}"})
		t = self.tab()
		self.assertEqual(len(t["stars"]), 3)  # prefilled: the three furthest behind
		self.assertTrue(t["ready"]["ok"])
		weekly.goal_star(space=PRIVATE, goal=t["stars"][0], on=0)
		t = self.tab()
		self.assertFalse(t["ready"]["ok"])
		self.assertIn("Star one more goal to go on", t["ready"]["left"])
		extra = next(g for g in self.goals if g not in t["stars"])
		weekly.goal_star(space=PRIVATE, goal=extra, on=1)
		weekly.goal_star(space=PRIVATE, goal=next(g for g in self.goals if g not in self.tab()["stars"]), on=1)
		self.assertFalse(self.tab()["ready"]["ok"])  # four is not three
		with self.assertRaises(frappe.ValidationError):
			weekly.goal_skip(space=PRIVATE, goal=self.goals[0], reason="  ")
		weekly.goal_skip(space=PRIVATE, goal=self.goals[0], reason="Travelling all week")
		t = self.tab()
		self.assertEqual(self.row(self.goals[0])["plan"]["skip"], "Travelling all week")
		self.assertNotIn(self.goals[0], t["stars"])
		self.assertTrue(t["ready"]["ok"])
		self.assertTrue(Review.find_open(PRIVATE, "owner@lifeos.test").done()["goals"])

	def test_a_goal_with_no_next_action_blocks(self):
		weekly.start(space=PRIVATE)
		t = self.tab()
		self.assertFalse(t["ready"]["ok"])
		self.assertEqual(sorted(t["ready"]["missing"]), sorted(self.goals))

	def test_over_capacity_is_said_and_does_not_block(self):
		settings_api.save({"work_days": "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday", "work_start": "09:00:00", "work_end": "10:00:00"})
		frappe.clear_document_cache("Life Settings", "Life Settings")
		try:
			for g in self.goals:
				weekly.goal_save(space=PRIVATE, goal=g, values={"next_action": f"act on {g}", "minutes": 600, "slot": f"{add_days(today(), 1)} 09:00"})
			cap = self.tab()["capacity"]
			self.assertTrue(cap["over"])
			self.assertGreater(cap["planned_minutes"], cap["free_minutes"])
			self.assertTrue(self.tab()["ready"]["ok"])
		finally:
			settings_api.save({"work_days": "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday", "work_start": "09:00:00", "work_end": "19:00:00"})
			frappe.clear_document_cache("Life Settings", "Life Settings")

	def test_other_goals_fold_and_can_be_planned(self):
		other = self.make("Life Goal", title="s8 Lotwise pilot", horizon="Long term").name
		t = self.tab()
		self.assertEqual(t["others"]["n"], 1)
		weekly.goal_add(space=PRIVATE, goal=other)
		t = self.tab()
		self.assertIn(other, [r["goal"] for r in t["rows"]])
		self.assertEqual(t["others"]["n"], 0)


class TestLock(GoalsCase):
	def plan_all(self):
		slot = f"{add_days(today(), 1)} 10:00"
		for i, g in enumerate(self.goals):
			who = "Kunal" if i == 1 else "Me"
			weekly.goal_save(space=PRIVATE, goal=g, values={"next_action": f"s8 next {i}", "slot": slot if i == 0 else "", "minutes": 45, "who": who,
				"note": "the figures"})
		weekly.goal_skip(space=PRIVATE, goal=self.goals[3], reason="Waiting for the season")
		return weekly.goals(space=PRIVATE)["stars"]

	def test_lock_needs_what_went_well_and_the_tabs_before(self):
		weekly.start(space=PRIVATE)
		with self.assertRaises(frappe.ValidationError):
			weekly.lock(space=PRIVATE, went_well="")
		with self.assertRaises(frappe.ValidationError):
			weekly.lock(space=PRIVATE, went_well="Closed the blend sheet")  # goals not planned yet

	def test_lock_makes_tasks_pins_the_top_three_and_locks(self):
		old = self.make("Life Task", title="s8 last week's star", status="Open", is_top_three=1, top_three_week=add_days(today(), -7)).name
		stars = self.plan_all()
		self.assertEqual(len(stars), 3)
		out = weekly.lock(space=PRIVATE, went_well="Closed the blend sheet in one sitting", do_differently="No calls on Tuesday")
		self.assertEqual(out["header"]["status"], "Locked")
		made = {m["goal"]: m for m in out["made"]}
		self.assertEqual(set(made), set(self.goals[:3]))  # the skipped one has no task
		first = frappe.db.get_value("Life Task", made[self.goals[0]]["task"], ["title", "scheduled_at", "duration_min", "notes_md", "status"], as_dict=True)
		self.assertEqual((first.title, str(first.scheduled_at)[:16], first.duration_min), ("s8 next 0", f"{add_days(today(), 1)} 10:00", 45))
		self.assertIn("the figures", first.notes_md)
		self.assertEqual(frappe.db.get_value("Life Task", made[self.goals[1]]["task"], ["status", "waiting_on"]), ("Waiting", "Kunal"))
		tops = frappe.get_all("Life Task", filters={"space": PRIVATE, "is_top_three": 1}, pluck="name")
		self.assertEqual(sorted(tops), sorted(made[g]["task"] for g in stars))
		self.assertEqual(frappe.db.get_value("Life Task", old, "is_top_three"), 0)  # last week's are cleared
		doc = frappe.get_doc("Life Review", out["header"]["name"])
		self.assertEqual((doc.went_well, doc.do_differently, doc.goals_planned, doc.goals_skipped), ("Closed the blend sheet in one sitting", "No calls on Tuesday", 3, 1))
		self.assertTrue(doc.locked_on and doc.minutes_spent >= 1)
		# Today: the top three first, starred
		got = today_api.get(space=PRIVATE)
		first_group = next(g for g in got["next"]["groups"] if g["rows"])
		self.assertEqual(first_group["key"], "top")
		self.assertEqual({r["name"] for r in first_group["rows"]}, set(tops))
		# the locked review is shown as done; the next starts after it
		self.assertEqual(weekly.get(space=PRIVATE)["status"], "Locked")
		self.assertEqual(str(Review.period(PRIVATE, OWNER, add_days(today(), 7))[0]), str(add_days(today(), 1)))
		with self.assertRaises(frappe.ValidationError):
			weekly.goal_save(space=PRIVATE, goal=self.goals[0], values={"next_action": "x"})

	def test_last_weeks_note_is_played_back(self):
		frappe.get_doc({"doctype": "Life Review", "space": PRIVATE, "user": OWNER, "status": "Locked", "period_start": add_days(today(), -14),
			"period_end": add_days(today(), -8), "locked_on": add_days(frappe.utils.now_datetime(), -8), "went_well": "x",
			"do_differently": "Too many calls on Tuesday"}).insert()
		self.assertEqual(weekly.reflect(space=PRIVATE)["last"], {"line": "Too many calls on Tuesday", "check": None})  # no key: the line only
		set_key("fake-site-model")
		frappe.set_user(OWNER)
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 1)
		try:
			tuesday = next(add_days(today(), -n) for n in range(1, 7) if frappe.utils.getdate(add_days(today(), -n)).weekday() == 1)
			frappe.get_doc({"doctype": "Event", "subject": "s8 call with Vivek", "starts_on": f"{tuesday} 11:00:00", "ends_on": f"{tuesday} 11:30:00",
				"life_space": PRIVATE, "event_type": "Public"}).insert(ignore_permissions=True)
			weekly.start(space=PRIVATE)
			self.assertEqual(weekly.reflect(space=PRIVATE)["last"]["check"], "This week Tuesday had 1 call.")
		finally:
			frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 0)


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
			goals.create(f"ux7 plan goal {i}", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")
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
		settings.save({"work_start": "00:00:00", "work_end": "23:59:00"})  # midnight is a start, not "not set"
		frappe.clear_document_cache("Life Settings", "Life Settings")
		self.assertEqual((weekplan.hours()["start"], weekplan.hours()["end"]), ((0, 0), (23, 59)))
		self.assertRaises(frappe.ValidationError, settings.save, {"work_days": ""})


class TestAddGoalWork(WeekCase):
	def test_add_creates_a_scheduled_task_under_the_goal(self):
		g = goals.create("ux7 add goal", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		at = monday_at(10)
		t = weekplan.add(g, title="ux7 draft the plan", scheduled_at=str(at), duration_min=90, note="the soil report")
		self.assertEqual((t.goal, t.area, get_datetime(t.scheduled_at), t.duration_min, t.status), (g, self.areas["Tea"], at, 90, "Open"))
		self.assertIn("the soil report", t.notes_md)
		# Add again updates the same task
		weekplan.add(g, task=t.name, title="ux7 draft the plan", scheduled_at="", duration_min=30)
		t.reload()
		self.assertIsNone(t.scheduled_at)
		self.assertEqual(t.notes_md.count("the soil report"), 1)

	def test_someone_else_makes_it_waiting_and_delegated(self):
		g = goals.create("ux7 delegate goal", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		out = weekplan.add(g, title="ux7 get the quotes", scheduled_at=str(monday_at(11)), duration_min=60, who="Mithun")
		self.assertEqual((out.status, out.waiting_on), ("Waiting", "Mithun"))
		self.assertEqual(frappe.get_all("Life Exit", filters={"record_name": out.name, "reversed": 0}, pluck="pile"), ["Delegated"])
		mine = weekplan.add(g, title="ux7 mine", who="Me")
		self.assertEqual(mine.status, "Open")

	def test_cards_prefill_the_oldest_open_task(self):
		g = goals.create("ux7 oldest goal", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		first = frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 first step", "goal": g, "status": "Open", "area": self.areas["Tea"]}).insert()
		frappe.db.set_value("Life Task", first.name, "creation", add_days(today(), -10))
		frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 second step", "goal": g, "status": "Open", "area": self.areas["Tea"]}).insert()
		card = next(c for c in weekplan.cards(PRIVATE, ai=False)["cards"] if c["goal"] == g)
		self.assertEqual((card["task"], card["next_action"], card["minutes"]), (first.name, "ux7 first step", 60))

	def test_people_only(self):
		g = goals.create("ux7 agent goal", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, week.key_results, space=PRIVATE)


class TestKeyResults(WeekCase):
	def test_readings_finish_lines_and_stale_goals(self):
		n = goals.create("ux7 kr number", "Long term", space=PRIVATE, area=self.areas["Tea"], measure_kind="Number", measure="Yield", unit="kg/ha",
			start_value=1200, target_value=1800)["name"]
		r = readings.suggest(n, 1500, today(), "Yield came to 1500", by="Agent")
		old = frappe.get_doc({"doctype": "Life Goal", "space": PRIVATE, "title": "ux7 kr no line", "horizon": "Long term", "area": self.areas["Tea"]}).insert()
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


class TestReviewFolder(LifeTestCase):
	"""The review screens live in one folder and reach the server through frontend/src/data/review.js."""

	COMPONENTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "src", "components")

	def test_no_review_file_calls_api_directly(self):
		import re

		folder = os.path.join(self.COMPONENTS, "review")
		bad = []
		for name in sorted(os.listdir(folder)):
			if not name.endswith((".vue", ".js")):
				continue
			source = open(os.path.join(folder, name), encoding="utf-8").read()
			if re.search(r"\bapi\(", source) or re.search(r"import\s*\{[^}]*\bapi\b[^}]*\}\s*from\s*'@/lib/api'", source):
				bad.append(name)
		self.assertEqual(bad, [], "these review components call api( directly; use data/review.js")

	def test_weekly_and_periodic_folders_are_gone(self):
		for folder in ("weekly", "periodic"):
			self.assertFalse(os.path.isdir(os.path.join(self.COMPONENTS, folder)), f"components/{folder} still exists")

