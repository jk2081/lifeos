"""Issue 48: the old Life Project table and the `project` aliases are gone."""
import re
import types
from pathlib import Path

import frappe

from lifeos import gone_names, proposals
from lifeos.api import connections, tasks
from lifeos.tests.base import PRIVATE, LifeTestCase

ROOT = Path(frappe.get_app_path("lifeos"))


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
