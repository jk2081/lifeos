"""Issue 21: Goals > All tasks. Every open task once under its area, regrouped by goal and by due date, the filters, and the
Someday filter against the old Someday page."""
import frappe
from frappe.utils import add_days, today

from lifeos.api import someday, tasks
from lifeos.tests.base import PRIVATE, LifeTestCase


class TestAllTasks(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Task", {"space": PRIVATE})
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		self.career, self.health, self.tea = self.life["Career"], self.life["Health"], self.areas["Tea"]
		for a in (self.career, self.health):
			frappe.db.set_value("Life Area", a, "is_on", 1)

	def names(self, res):
		return [t["name"] for g in res["groups"] for p in g["parts"] for t in p["tasks"]]

	def test_every_open_task_appears_once_under_its_area(self):
		a = self.make("Life Task", title="i21 a", area=self.career, status="Open").name
		b = self.make("Life Task", title="i21 b", area=self.tea, status="Doing").name
		c = self.make("Life Task", title="i21 c", area=self.health, status="Waiting", waiting_on="Vivek").name
		d = self.make("Life Task", title="i21 none", status="Open").name
		self.make("Life Task", title="i21 done", area=self.health, status="Done")
		res = tasks.all_tasks(space=PRIVATE)
		self.assertEqual(sorted(self.names(res)), sorted([a, b, c, d]))
		self.assertEqual(res["total"], 4)
		career = next(g for g in res["groups"] if g["area"] == self.career)
		# a task saved with no area gets a guessed one (issue 13), so it is under an area too
		guessed = next(t for g in res["groups"] for p in g["parts"] for t in p["tasks"] if t["name"] == d)
		self.assertTrue(guessed["area_guessed"] and guessed["area"])
		self.assertEqual([t["name"] for t in career["parts"][-1]["tasks"]], [b])
		self.assertIn(a, [t["name"] for t in career["parts"][0]["tasks"]])
		self.assertEqual(tasks.count(PRIVATE, status="open"), 4)

	def test_goal_and_due_date_regroup_the_same_tasks(self):
		g = self.make("Life Goal", title="i21 goal", area=self.career, goal_type="Open").name
		self.make("Life Task", title="i21 g", area=self.career, goal=g, due_date=today())
		self.make("Life Task", title="i21 late", area=self.health, due_date=add_days(today(), -2))
		self.make("Life Task", title="i21 undated", area=self.health)
		same = sorted(self.names(tasks.all_tasks(space=PRIVATE)))
		by_goal = tasks.all_tasks(space=PRIVATE, group="goal")
		by_due = tasks.all_tasks(space=PRIVATE, group="due")
		self.assertEqual(sorted(self.names(by_goal)), same)
		self.assertEqual(sorted(self.names(by_due)), same)
		self.assertEqual([x["label"] for x in by_goal["groups"]], ["i21 goal", "No goal"])
		self.assertEqual([x["key"] for x in by_due["groups"]], ["overdue", "today", "none"])

	def test_filters_and_counts(self):
		self.make("Life Task", title="i21 soon", area=self.career, due_date=today())
		self.make("Life Task", title="i21 far", area=self.career, due_date=add_days(today(), 60))
		self.make("Life Task", title="i21 wait", area=self.career, status="Waiting", waiting_on="Mr. Rao")
		self.make("Life Task", title="i21 done", area=self.career, status="Done")
		counts = tasks.all_tasks(space=PRIVATE)["counts"]
		self.assertEqual(counts, {"open": 3, "due": 1, "waiting": 1, "someday": 0, "done": 1})
		for show, n in (("due", 1), ("waiting", 1), ("done", 1)):
			self.assertEqual(tasks.all_tasks(space=PRIVATE, show=show)["total"], n)
		self.assertEqual(tasks.all_tasks(space=PRIVATE, q="soon")["total"], 1)
		self.assertEqual(tasks.all_tasks(space=PRIVATE, area=self.health)["total"], 0)
		with self.assertRaises(frappe.ValidationError):
			tasks.all_tasks(space=PRIVATE, show="x")

	def test_the_someday_filter_is_the_someday_pages_tasks(self):
		t = self.make("Life Task", title="i21 parked", area=self.career).name
		someday.park("Life Task", t)
		self.make("Life Task", title="i21 open", area=self.career)
		old = [r["name"] for r in someday.list(space=PRIVATE, tab="tasks", page_length=100)["rows"]]
		new = self.names(tasks.all_tasks(space=PRIVATE, show="someday"))
		self.assertEqual(sorted(new), sorted(old))
		self.assertIn(t, new)

	def test_a_guessed_area_and_the_top_three_come_through(self):
		t = self.make("Life Task", title="i21 guess", area=self.career, area_guessed=1, area_confidence=70, is_top_three=1).name
		row = next(x for g in tasks.all_tasks(space=PRIVATE)["groups"] for p in g["parts"] for x in p["tasks"] if x["name"] == t)
		self.assertTrue(row["area_guessed"])
		self.assertTrue(row["is_top_three"])
		self.assertEqual(row["area_name"], "Career")

	def test_an_area_that_is_off_hides_its_tasks_and_the_counts_agree(self):
		self.make("Life Task", title="i21 h", area=self.health)
		self.make("Life Task", title="i21 c", area=self.career)
		frappe.db.set_value("Life Area", self.health, "is_on", 0)
		res = tasks.all_tasks(space=PRIVATE)
		self.assertEqual((res["total"], res["counts"]["open"]), (1, 1))
