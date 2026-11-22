"""UX fixes, set 6: projects became long-term goals. What a goal
serves and the project-page states on an open-ended goal."""
import frappe
from frappe.utils import add_days, today

from lifeos.api import goals, tasks
from lifeos.tests.base import PRIVATE, LifeTestCase


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
