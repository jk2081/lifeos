"""Issue 20: Goals > By area. Sections for the areas that are on with their parts, cards with Done when, next action and open
task count, the filters, the owner's order, and an area that is off."""
import frappe

from lifeos.api import goals
from lifeos.tests.base import AGENT, FAMILY, PRIVATE, SHARED, LifeTestCase


class TestGoalsByArea(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		self.career, self.health, self.tea = self.life["Career"], self.life["Health"], self.areas["Tea"]
		frappe.db.set_value("Life Area", self.career, "is_on", 1)
		frappe.db.set_value("Life Area", self.health, "is_on", 1)

	def goal(self, title, area, **kw):
		return self.make("Life Goal", title=title, area=area, goal_type="Open", **kw).name

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
		inside = self.make("Life Goal", title="i20 inside", area=self.health, goal_type="12 Week Year", cycle=cycle).name
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
