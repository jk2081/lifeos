"""Issue 55: Today lists tasks only. A goal or a lead action is never a row; a task planned this week under a cycle goal is, with
its goal; finishing it ticks the lead action; goals with nothing planned are one count; the Insights list has no duplicates."""
import frappe
from frappe.utils import add_days, today

from lifeos import journal as rules
from lifeos.api import journal, tasks
from lifeos.api import today as today_api
from lifeos.tests.base import PRIVATE, LifeTestCase


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

	def test_goals_and_lead_actions_are_not_rows(self):  # I55.1
		data = today_api.get(space=PRIVATE)
		titles = {r["title"] for r in self.rows()}
		self.assertFalse(titles & {g.title for g in self.goals} | titles & {g.actions[0].title for g in self.goals})
		self.assertFalse([r for r in self.rows() if r.get("type") not in ("task", "event")])
		self.assertEqual(data["no_plan"], 3)

	def test_a_planned_task_shows_with_its_goal_and_ticks_the_lead_action(self):  # I55.2, I55.3
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

	def test_the_insights_list_has_no_duplicates_and_at_most_three(self):  # I55.7
		rows = [{"title": t} for t in ["Board call", "board  call", "Foxin", "Board call", "A", "B", "C"]]
		out = today_api.unique_insights(rows)
		self.assertEqual([r["title"] for r in out["rows"]], ["Board call", "Foxin", "A"])
		self.assertEqual(out["total"], 5)
		self.assertEqual(len(today_api.get(space=PRIVATE)["rail"]["insights"]) <= 3, True)
