"""Issue 48: the old Life Project table and the `project` aliases are gone."""
import re
import types
from pathlib import Path

import frappe

from lifeos import gone_names, proposals
from lifeos.api import connections, tasks
from lifeos.patches.v15 import remove_life_project
from lifeos.tests.base import PRIVATE, LifeTestCase

ROOT = Path(frappe.get_app_path("lifeos"))
OLD_COLUMN_TABLES = ("Life Task", "Life Note")


class TestRemoveLifeProject(LifeTestCase):
	"""The patch runs against a stand-in Life Project DocType (the real one is gone) and a `project` column on two tables;
	everything it makes is removed again, whatever the outcome."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self._clean()
		frappe.get_doc({"doctype": "DocType", "name": "Life Project", "module": "Life", "custom": 1, "autoname": "hash",
			"fields": [{"fieldname": "title", "fieldtype": "Data"}, {"fieldname": "migrated_to", "fieldtype": "Link", "options": "Life Goal"}],
			"permissions": [{"role": "System Manager", "read": 1}]}).insert()
		for dt in OLD_COLUMN_TABLES:
			frappe.db.sql_ddl(f"alter table `tab{dt}` add column project varchar(140)")
		self.goal = self.make("Life Goal", title="i48 goal", horizon="Long term", area=self.areas["Tea"])
		self.task = self.make("Life Task", title="i48 task", area=self.areas["Tea"], goal=self.goal.name)
		self.note = self.make("Life Note", title="i48 note", area=self.areas["Tea"], goal=self.goal.name)
		self.project = frappe.get_doc({"doctype": "Life Project", "title": "i48 project", "migrated_to": self.goal.name}).insert()
		for doc in (self.task, self.note):
			frappe.db.set_value(doc.doctype, doc.name, "project", self.project.name, update_modified=False)

	def tearDown(self):
		self._clean()
		super().tearDown()

	def _clean(self):
		if frappe.db.exists("DocType", "Life Project"):
			frappe.delete_doc("DocType", "Life Project", force=True, delete_permanently=True)
		frappe.db.sql_ddl("drop table if exists `tabLife Project`")
		for dt in OLD_COLUMN_TABLES:
			if remove_life_project.has_column(dt, "project"):
				frappe.db.sql_ddl(f"alter table `tab{dt}` drop column project")

	def test_1_a_migrated_site_loses_the_doctype_and_the_columns_and_keeps_its_links(self):
		remove_life_project.execute()
		self.assertFalse(frappe.db.exists("DocType", "Life Project"))
		self.assertFalse(remove_life_project.has_table("Life Project"))
		for dt in OLD_COLUMN_TABLES:
			self.assertFalse(remove_life_project.has_column(dt, "project"), dt)
		for doc in (self.goal, self.task, self.note):
			opened = frappe.get_doc(doc.doctype, doc.name)
			self.assertEqual(opened.title, doc.title)
		self.assertEqual(frappe.get_doc("Life Task", self.task.name).goal, self.goal.name)
		self.assertEqual(frappe.get_doc("Life Note", self.note.name).goal, self.goal.name)
		remove_life_project.execute()  # running it again on a clean site does nothing

	def test_2_a_project_without_migrated_to_stops_the_patch_and_changes_nothing(self):
		lost = frappe.get_doc({"doctype": "Life Project", "title": "i48 unmigrated"}).insert()
		self.assertEqual(len(remove_life_project.problems()), 1)
		with self.assertRaises(frappe.ValidationError) as caught:
			remove_life_project.execute()
		self.assertIn(lost.name, str(caught.exception))
		self.assertTrue(frappe.db.exists("DocType", "Life Project"))
		self.assertTrue(frappe.db.exists("Life Project", lost.name))
		for dt in OLD_COLUMN_TABLES:
			self.assertTrue(remove_life_project.has_column(dt, "project"), (dt, remove_life_project.has_table(dt)))

	def test_2b_a_record_with_a_project_and_no_goal_stops_the_patch_too(self):
		frappe.db.set_value("Life Task", self.task.name, "goal", None, update_modified=False)
		found = remove_life_project.problems()
		self.assertEqual(len(found), 1)
		self.assertIn(self.task.name, found[0])
		with self.assertRaises(frappe.ValidationError):
			remove_life_project.execute()
		self.assertTrue(remove_life_project.has_column("Life Task", "project"))


class TestProjectAliasesGone(LifeTestCase):
	def test_3_a_call_with_project_names_goal_and_the_same_call_with_goal_works(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			gone_names.refuse({"project": "x", "status": "open"})
		self.assertIn("`goal`", str(caught.exception))
		request = types.SimpleNamespace(path="/api/method/lifeos.api.tasks.list")
		frappe.local.request = request
		old_form = frappe.local.form_dict
		try:
			frappe.local.form_dict = frappe._dict(project="x")
			self.assertRaises(frappe.ValidationError, gone_names.before_request)
			frappe.local.form_dict = frappe._dict(goal="x")
			gone_names.before_request()
		finally:
			frappe.local.form_dict = old_form
			frappe.local.request = None
		goal = self.make("Life Goal", title="i48 alias goal", horizon="Long term", area=self.areas["Tea"])
		task = self.make("Life Task", title="i48 alias task", area=self.areas["Tea"], goal=goal.name)
		self.assertEqual([t["name"] for t in tasks.list(space=PRIVATE, goal=goal.name)["tasks"]], [task.name])
		self.assertRaises(frappe.ValidationError, tasks.update, task.name, {"project": goal.name})
		self.assertRaises(frappe.ValidationError, proposals.validate, "Task", {"title": "x", "project": goal.name}, PRIVATE)
		self.assertNotIn("project", tasks.list.__code__.co_varnames[:tasks.list.__code__.co_argcount])

	def test_4_a_someday_proposal_with_record_type_project_is_refused(self):
		goal = self.make("Life Goal", title="i48 someday goal", horizon="Long term", area=self.areas["Tea"])
		item = types.SimpleNamespace(space=PRIVATE, name="none")
		self.assertRaises(proposals.PayloadError, proposals._apply_someday, {"record_type": "Project", "record": goal.name}, item)
		self.assertEqual(frappe.db.get_value("Life Goal", goal.name, "is_someday"), 0)

	def test_5_connection_defaults_have_no_default_project(self):
		self.assertNotIn("default_project", connections.defaults(space=PRIVATE, system="gmail"))
		self.assertIn("default_goal", connections.defaults(space=PRIVATE, system="gmail"))
		self.make("Life Connection", system="gmail", active=1)
		out = connections.defaults(space=PRIVATE, system="gmail")
		self.assertEqual(out["known"], 1)
		self.assertNotIn("default_project", out)
		self.assertNotIn("default_project", connections.list(space=PRIVATE)["connections"][0])


class TestNoProjectInTheCode(LifeTestCase):
	# the one file that names the removed arguments, to refuse them, and the patches, which are history
	SKIP = {"gone_names.py"}
	GONE = re.compile(r"Life Project|goal_for_project|for_project|project_alias|default_project|ProjectPane|ProjectRedirect|\bproject: str|\bproject=|[\"']project[\"']\s*:|[\"']project[\"']\s*[,)\]]")

	def test_7_no_python_or_front_end_code_names_the_old_table_or_the_alias(self):
		files = [p for p in ROOT.rglob("*.py") if "tests" not in p.parts and "patches" not in p.parts and p.name not in self.SKIP]
		front = ROOT.parent / "frontend" / "src"
		files += [p for ext in ("*.js", "*.vue") for p in front.rglob(ext)] if front.exists() else []
		files += [p for p in (ROOT.parent / "agent").rglob("*.py")]
		self.assertGreater(len(files), 100)
		hits = [f"{p.relative_to(ROOT.parent)}:{n}: {line.strip()[:100]}" for p in files
			for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1) if self.GONE.search(line)]
		self.assertEqual(hits, [])
