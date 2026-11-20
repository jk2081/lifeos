"""Issue 12: Settings > Areas. Switch the seven on and off, add and edit parts, archive a part and move its open work, and
only Life Admin changes areas. The screen itself is checked by acceptance checks I12.<width>.1 to .5."""
import frappe

from lifeos import areas
from lifeos.api import goals, meta, settings, tasks
from lifeos.tests.base import AGENT, FAMILY, PRIVATE, SHARED, LifeTestCase


class TestSettingsAreas(LifeTestCase):
	def context_areas(self, space=PRIVATE):
		return {a["name"] for a in meta.space_context(space)["areas"]}

	def row(self, name, space=PRIVATE):
		return next(a for a in settings.get(space)["areas"] if a.name == name)

	# 1
	def test_switching_money_on_and_off_shows_and_hides_it_and_its_goals(self):
		money = self.life["Money"]
		settings.save_item("area", name=money, is_on=0)
		goal = goals.create("i12 goal in Money", "Open", space=PRIVATE, area=money)["name"]
		self.assertNotIn(money, self.context_areas())
		settings.save_item("area", name=money, is_on=1)
		self.assertIn(money, self.context_areas())
		self.assertIn(goal, {g["name"] for g in goals.list(space=PRIVATE, page_length=100)["goals"]})
		self.assertGreaterEqual(self.row(money)["goals"], 1)
		settings.save_item("area", name=money, is_on=0)
		self.assertNotIn(money, self.context_areas())
		self.assertNotIn(goal, {g["name"] for g in goals.list(space=PRIVATE, page_length=100)["goals"]})
		self.assertTrue(frappe.db.exists("Life Goal", goal))  # nothing is deleted
		settings.save_item("area", name=money, is_on=1)
		self.assertIn(goal, {g["name"] for g in goals.list(space=PRIVATE, page_length=100)["goals"]})

	# 2
	def test_adding_a_part_under_career_lists_it_with_its_description_and_colour(self):
		career = self.life["Career"]
		part = settings.save_item("area", space=PRIVATE, title="i12 CIS Board", parent_area=career, description="Vice Chair",
			colour="violet")["name"]
		row = self.row(part)
		self.assertEqual((row.parent_area, row.description, row.colour, row["goals"]), (career, "Vice Chair", "violet", 0))
		self.assertIn(part, self.context_areas())
		goals.create("i12 board goal", "Open", space=PRIVATE, area=part)
		self.assertEqual(self.row(part)["goals"], 1)
		self.assertGreaterEqual(self.row(career)["goals"], 1)  # an area of life counts the goals of its parts

	# 3
	def test_archiving_a_part_with_open_work_asks_where_and_moves_it(self):
		career = self.life["Career"]
		part = settings.save_item("area", space=PRIVATE, title="i12 part to archive", parent_area=career)["name"]
		other = settings.save_item("area", space=PRIVATE, title="i12 other part", parent_area=career)["name"]
		open_task = self.make("Life Task", title="i12 open task", area=part).name
		done_task = self.make("Life Task", title="i12 done task", area=part, status="Done").name
		goal = goals.create("i12 goal in the part", "Open", space=PRIVATE, area=part)["name"]
		work = settings.area_open_work(part)
		self.assertEqual((work["goals"], work["tasks"]), (1, 1))
		self.assertEqual([t.name for t in work["targets"]][0], career)
		self.assertIn(other, [t.name for t in work["targets"]])
		self.assertNotIn(part, [t.name for t in work["targets"]])
		with self.assertRaisesRegex(frappe.ValidationError, "Choose where to move them"):
			settings.save_item("area", name=part, is_archived=1)
		self.assertEqual(frappe.db.get_value("Life Area", part, "is_archived"), 0)
		for wrong in (part, self.life["Health"], self.areas["Personal"]):  # not to itself, nor outside Career
			with self.assertRaises(frappe.ValidationError):
				settings.save_item("area", name=part, is_archived=1, move_to=wrong)
		settings.save_item("area", name=part, is_archived=1, move_to=other)
		self.assertEqual(frappe.db.get_value("Life Area", part, "is_archived"), 1)
		self.assertEqual(frappe.db.get_value("Life Task", open_task, "area"), other)
		self.assertEqual(frappe.db.get_value("Life Goal", goal, "area"), other)
		self.assertEqual(frappe.db.get_value("Life Task", done_task, "area"), part)  # closed work stays where it was
		self.assertIn(open_task, {t["name"] for t in tasks.list(space=PRIVATE, area=other, page_length=100)["tasks"]})
		# to the area of life itself
		settings.save_item("area", name=other, is_archived=1, move_to=career)
		self.assertEqual(frappe.db.get_value("Life Task", open_task, "area"), career)

	# 4
	def test_only_life_admin_changes_areas(self):
		work = self.shared_life["Career"]
		self.as_user(FAMILY)
		got = settings.get(SHARED)
		self.assertFalse(got["is_admin"])
		self.assertTrue(any(a.is_life_area for a in got["areas"]))  # the screen still reads
		for call in (lambda: settings.save_item("area", name=work, is_on=0), lambda: settings.save_item("area", name=work, description="x"),
				lambda: settings.save_item("area", space=SHARED, title="i12 family part", parent_area=work),
				lambda: settings.reorder("area", frappe.as_json([work])), lambda: settings.area_open_work(work)):
			self.assertRaises(frappe.PermissionError, call)
		self.assertEqual(frappe.db.get_value("Life Area", work, "is_on"), 1)
		self.as_user(AGENT)
		with self.assertRaisesRegex(frappe.PermissionError, "Only a person"):
			settings.save_item("area", name=work, is_on=0)

	def test_goal_counts_leave_out_closed_and_someday_goals(self):
		mind = self.life["Mind"]
		settings.save_item("area", name=mind, is_on=1)
		before = areas.goal_counts(PRIVATE).get(mind, 0)
		goals.create("i12 counted", "Open", space=PRIVATE, area=mind)
		closed = goals.create("i12 achieved", "Open", space=PRIVATE, area=mind)["name"]
		frappe.db.set_value("Life Goal", closed, "outcome", "Achieved")
		self.assertEqual(areas.goal_counts(PRIVATE).get(mind, 0), before + 1)
		settings.save_item("area", name=mind, is_on=0)
