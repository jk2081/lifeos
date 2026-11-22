"""Issue 22: Goals > No goal. Open tasks with no goal by area, the count on the tab, Fine as is, and Make it a goal."""
import frappe

from lifeos.api import goals, tasks
from lifeos.tests.base import PRIVATE, LifeTestCase


class TestNoGoal(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Task", {"space": PRIVATE})
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		self.career, self.health = self.life["Career"], self.life["Health"]
		for a in (self.career, self.health):
			frappe.db.set_value("Life Area", a, "is_on", 1)

	def names(self, res):
		return [t["name"] for g in res["groups"] for t in g["tasks"]]

	def test_tasks_with_no_goal_by_area_and_the_count(self):
		g = self.make("Life Goal", title="i22 goal", area=self.career, horizon="Long term").name
		a = self.make("Life Task", title="i22 a", area=self.career).name
		b = self.make("Life Task", title="i22 b", area=self.health, status="Waiting", waiting_on="Rao").name
		self.make("Life Task", title="i22 has goal", area=self.career, goal=g)
		self.make("Life Task", title="i22 done", area=self.career, status="Done")
		res = tasks.no_goal(space=PRIVATE)
		self.assertEqual(sorted(self.names(res)), sorted([a, b]))
		self.assertEqual({g["area"] for g in res["groups"]}, {self.career, self.health})
		self.assertEqual(tasks.no_goal_total(space=PRIVATE)["count"], 2)

	def test_an_area_that_is_off_still_lists_its_tasks(self):
		t = self.make("Life Task", title="i22 off", area=self.health).name
		frappe.db.set_value("Life Area", self.health, "is_on", 0)
		res = tasks.no_goal(space=PRIVATE)
		group = next(g for g in res["groups"] if g["area"] == self.health)
		self.assertFalse(group["is_on"])
		self.assertEqual([x["name"] for x in group["tasks"]], [t])
		self.assertEqual(tasks.no_goal_total(space=PRIVATE)["count"], 1)

	def test_fine_as_is_confirms_the_area_and_leaves_the_list(self):
		t = self.make("Life Task", title="i22 fine", area=self.career, area_guessed=1, area_confidence=60).name
		tasks.keep_standalone(t)
		self.assertEqual(frappe.db.get_value("Life Task", t, ["standalone", "area_guessed"]), (1, 0))
		self.assertEqual(self.names(tasks.no_goal(space=PRIVATE)), [])
		self.assertEqual(tasks.no_goal_total(space=PRIVATE)["count"], 0)

	def test_a_suggestion_needs_three_tasks_sharing_a_word(self):
		for t in ("Call Mehi Motors about the quote", "Send Mehi Motors the drawings", "Visit Mehi Motors plant"):
			self.make("Life Task", title=t, area=self.career)
		self.make("Life Task", title="Pay the electricity bill", area=self.career)
		self.make("Life Task", title="Stretch", area=self.health)
		res = tasks.no_goal(space=PRIVATE)
		career = next(g for g in res["groups"] if g["area"] == self.career)
		self.assertEqual(len(career["suggestion"]["tasks"]), 3)
		self.assertIsNone(next(g for g in res["groups"] if g["area"] == self.health)["suggestion"])

	def test_make_goal_creates_one_goal_and_attaches_the_tasks(self):
		ts = [self.make("Life Task", title=f"i22 mehi {n}", area=self.career).name for n in range(3)]
		other = self.make("Life Task", title="i22 other", area=self.career).name
		out = tasks.make_goal(ts, space=PRIVATE, area=self.career)
		goal = frappe.get_doc("Life Goal", out["goal"])
		self.assertEqual((goal.area, goal.horizon, goal.outcome), (self.career, "Year", "In Progress"))
		self.assertEqual(frappe.db.count("Life Goal", {"space": PRIVATE}), 1)
		for t in ts:
			self.assertEqual(frappe.db.get_value("Life Task", t, "goal"), goal.name)
		self.assertFalse(frappe.db.get_value("Life Task", other, "goal"))
		self.assertEqual(self.names(tasks.no_goal(space=PRIVATE)), [other])
		with self.assertRaises(frappe.ValidationError):  # a task that has a goal now cannot be made a goal again
			tasks.make_goal(ts[:1], space=PRIVATE)

	def test_make_goal_takes_its_title_from_the_assistant_when_a_key_is_set(self):
		from lifeos.ai import fake
		from lifeos.tests.test_issue13_task_areas import set_key

		ts = [self.make("Life Task", title=f"Call Vivek about plan {n}", area=self.career).name for n in range(3)]
		set_key("sk-test-not-real")
		backend = frappe.flags.lifeos_ai_backend = fake.ScriptedFake([{"content": [{"type": "text", "text": '{"kind": "Title", "title": "Agree the plan with Vivek"}'}],
			"stop_reason": "end_turn", "usage": {"input_tokens": 100, "output_tokens": 10}}])
		used = frappe.db.count("Life AI Usage", {"purpose": "Skill: define-goal"})
		try:
			out = tasks.make_goal(ts, space=PRIVATE, area=self.career)
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key(None)
		self.assertEqual(out["title"], "Agree the plan with Vivek")
		self.assertEqual(len(backend.received), 1)
		self.assertEqual(frappe.db.count("Life AI Usage", {"purpose": "Skill: define-goal"}), used + 1)

	def test_make_goal_names_the_goal_from_the_titles_without_a_key(self):
		ts = [self.make("Life Task", title=f"Quote for Zorbax {n}", area=self.career).name for n in range(3)]
		self.assertEqual(tasks.make_goal(ts, space=PRIVATE, area=self.career)["title"], "Get Zorbax done")
