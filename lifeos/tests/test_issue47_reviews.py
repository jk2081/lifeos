"""Issue 47: the monthly and the 12-week review, in the weekly review's shell. When each is due, what Lock writes, and that a
review left half done resumes."""
import frappe
from frappe.utils import add_days, getdate

from lifeos import journal as rules
from lifeos.api import periodic
from lifeos.review import periodic as rv_rules
from lifeos.tests.base import AGENT as AGENT_USER, OWNER, PRIVATE, LifeTestCase

# October 2026 ended on Saturday 31 October; the review day is Sunday, so the monthly review is due from Sunday 1 November
NOV_1, OCT_31 = "2026-11-01", "2026-10-31"


class TestReviews(LifeTestCase):
	def setUp(self):
		super().setUp()
		for dt in ("Life Review", "Life Goal", "Life Cycle", "Life Month Plan", "Life Habit"):
			frappe.db.delete(dt, {"space": PRIVATE})
		frappe.db.sql("delete from `tabLife Month Plan Habit` where parenttype = 'Life Month Plan' and parent not in (select name from `tabLife Month Plan`)")
		frappe.db.set_single_value("Life Settings", "weekly_review_day", "Sunday")
		frappe.db.set_single_value("Life Settings", "cycle_break_week", 1)
		frappe.clear_cache(doctype="Life Settings")
		frappe.conf.lifeos_test_clock = 1

	def tearDown(self):
		frappe.conf.pop("lifeos_test_clock", None)
		super().tearDown()

	def october(self):
		rules.get_month_plan(PRIVATE, 2026, 10, create=True)
		return [rules.add_month_goal(PRIVATE, 2026, 10, f"i47 goal {i}", self.area()) for i in range(3)]

	def area(self):
		return self.areas["Personal"]

	def test_monthly_review_is_due_from_the_first_review_day_until_locked(self):  # I47.1
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

	def test_cycle_review_is_due_on_the_last_day_and_replaces_the_weekly_one(self):  # I47.5
		cycle = self.make("Life Cycle", title="i47 cycle", start_date="2026-10-05", status="Active")
		self.assertEqual(str(cycle.end_date), "2026-12-27")
		me = (PRIVATE, OWNER)
		self.assertIsNone(rv_rules.cycle_due(PRIVATE, day="2026-12-26"))
		self.assertEqual([d["kind"] for d in rv_rules.due(*me, day="2026-12-27")], ["12-weeks"])
		self.assertFalse(rv_rules.weekly_due(*me, day="2026-12-27"))
		self.assertEqual([d["kind"] for d in rv_rules.due(*me, day="2026-12-30")], ["12-weeks"])  # the break week, until done
		self.assertEqual([d["kind"] for d in rv_rules.due(*me, day="2026-12-20")], ["weekly"])

	def test_locking_the_monthly_review_writes_next_months_plan(self):  # I47.3, I47.4
		goals = self.october()
		habit = self.make("Life Habit", title="i47 walk").name
		plan = rules.get_month_plan(PRIVATE, 2026, 10)
		plan.append("habits", {"habit": habit, "days_per_week": 5, "sort_order": 1})
		plan.save()
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
		self.assertEqual([h["habit"] for h in rules.habits_month(PRIVATE, 2026, 11)["habits"]], [habit])
		doc = frappe.get_doc("Life Review", res["header"]["name"])
		self.assertEqual((doc.kind, doc.went_well, doc.do_differently), ("Monthly", "Good", "Start earlier"))

	def test_a_review_left_half_done_resumes_where_it_was(self):  # I47.9
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

	def test_cycle_review_score_matches_the_cycle_view(self):  # I47.6
		cycle, made = self.cycle_with_goals()
		at = "2026-12-27 10:00"
		score = periodic.look(space=PRIVATE, kind="12-weeks", at=at)
		grid = rules.grid(cycle.name)
		self.assertEqual(len(score["weeks"]), 12)
		self.assertEqual(score["average"], grid["average"])
		self.assertEqual([g["name"] for g in score["goals"]], [g.name for g in made])

	def test_locking_the_cycle_review_closes_it_with_the_same_score_and_makes_the_next(self):  # I47.7
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
