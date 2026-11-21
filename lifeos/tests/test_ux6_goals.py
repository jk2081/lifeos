"""UX fixes, set 6: projects became long-term goals. What a goal
serves, the project-page states on an open-ended goal, and the `project=` aliases kept for one set."""
import frappe
from frappe.utils import add_days, today

from lifeos.api import goals, inbox, tasks
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase

def make_project(title, space=PRIVATE, **values):
	"""A Life Project row as old data had it. Only the migration may write one now."""
	doc = frappe.get_doc({"doctype": "Life Project", "space": space, "title": title, **values})
	doc.flags.allow_migration = True
	doc.insert(ignore_permissions=True)
	return doc


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


class TestProjectAliases(LifeTestCase):
	def test_project_names_the_goal_it_became(self):
		goal = self.make("Life Goal", title="ux6 alias goal", horizon="Long term", area=self.areas["Tea"])
		frappe.set_user("Administrator")
		project = make_project("ux6 alias project", area=self.areas["Tea"], status="Active")
		frappe.db.set_value("Life Project", project.name, "migrated_to", goal.name)
		self.as_user(OWNER)
		task = self.make("Life Task", title="ux6 alias task", area=self.areas["Tea"], goal=goal.name)
		self.make("Life Task", title="ux6 alias other task", area=self.areas["Tea"])
		for value in (project.name, "ux6 alias project"):
			self.assertEqual([t["name"] for t in tasks.list(space=PRIVATE, project=value)["tasks"]], [task.name], value)
		item = inbox.create_item(title="ux6 alias item", source_type="Message", space=PRIVATE, raw_text="x", project=project.name)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item["name"], "goal"), goal.name)
		item = inbox.create_item(title="ux6 alias item by title", source_type="Message", space=PRIVATE, raw_text="x", project="ux6 alias project")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item["name"], "goal"), goal.name)
