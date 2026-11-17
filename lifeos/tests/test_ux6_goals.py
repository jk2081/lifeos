"""UX fixes, set 6: projects become open-ended goals. The migration patch on data shaped like the seeded data, what a goal
serves, the project-page states on an open-ended goal, and the `project=` aliases kept for one set."""
import frappe
from frappe.utils import add_days, add_months, getdate, today

from lifeos import counts
from lifeos.api import goals, inbox, tasks
from lifeos.patches.v7 import projects_into_goals
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase

# DocTypes whose old `project` column the patch reads (Frappe keeps a column when its field leaves the DocType)
OLD_COLUMNS = ("Life Task", "Life Note", "Life Chat Log", "Life Vault Document", "Life Goal")


def make_project(title, space=PRIVATE, **values):
	"""A Life Project row as old data had it. Only the migration may write one now."""
	doc = frappe.get_doc({"doctype": "Life Project", "space": space, "title": title, **values})
	doc.flags.allow_migration = True
	doc.insert(ignore_permissions=True)
	return doc


def set_old_project(doctype, name, project):
	# nosemgrep: frappe-sql-format-injection -- `doctype` comes from the constant OLD_COLUMNS
	frappe.db.sql(f"update `tab{doctype}` set project=%s where name=%s", (project, name))


class TestProjectsIntoGoals(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		missing = [dt for dt in OLD_COLUMNS if not frappe.db.has_column(dt, "project")]
		if missing:
			self.skipTest(f"no old project column on {', '.join(missing)}: this site never had projects")

	def snapshot(self):
		"""Everything the patch may write in the test space."""
		def rows(sql):
			return sorted(tuple(r) for r in frappe.db.sql(sql, PRIVATE))
		return {
			"goals": rows("""select name, title, goal_type, area, outcome, on_hold, is_someday, serves, done_when, notes_md, closed_on,
				completed_on, last_activity_on, is_archived, someday_on, creation, modified from `tabLife Goal` where space=%s"""),
			"tasks": rows("select name, goal, someday_with, status, is_archived, modified from `tabLife Task` where space=%s"),
			"notes": rows("select name, goal from `tabLife Note` where space=%s"),
			"chats": rows("select name, goal from `tabLife Chat Log` where space=%s"),
			"vault": rows("select name, goal from `tabLife Vault Document` where space=%s"),
			"links": rows("select from_doctype, from_name, to_doctype, to_name from `tabLife Link` where space=%s"),
			"projects": rows("select name, migrated_to from `tabLife Project` where space=%s"),
			"index": rows("select ref_doctype, ref_name, goal from `tabLife Index` where space=%s"),
		}

	def test_patch_maps_projects_and_their_links_once(self):
		tea, money = self.areas["Tea"], self.areas["Money"]
		done_day = add_days(today(), -40)
		active = make_project("ux6 mig active", area=tea, status="Active", outcome="Mandir built", notes_md="notes",
			target_date=add_days(today(), 90))
		hold = make_project("ux6 mig hold", area=tea, status="On Hold")
		done = make_project("ux6 mig done", area=money, status="Done", completed_on=done_day)
		dropped = make_project("ux6 mig dropped", area=money, status="Dropped", completed_on=done_day)
		parked = make_project("ux6 mig someday", area=tea, status="Someday", someday_on=add_days(today(), -10),
			someday_review_on=add_months(today(), 2), someday_note="later")
		# records filed under a project, as the old `project` column held them
		t_plain = self.make("Life Task", title="ux6 mig task", area=tea)
		set_old_project("Life Task", t_plain.name, active.name)
		t_done_proj = self.make("Life Task", title="ux6 mig task of a done project", area=money)
		set_old_project("Life Task", t_done_proj.name, done.name)
		own = self.make("Life Goal", title="ux6 mig own goal", goal_type="Open", area=tea)
		t_both = self.make("Life Task", title="ux6 mig task with goal and project", area=tea, goal=own.name)
		set_old_project("Life Task", t_both.name, hold.name)
		longer = self.make("Life Goal", title="ux6 mig longer", goal_type="Open", area=tea)
		served = self.make("Life Goal", title="ux6 mig served", goal_type="Open", area=tea, serves=longer.name)
		t_link = self.make("Life Task", title="ux6 mig task whose goal serves another", area=tea, goal=served.name)
		set_old_project("Life Task", t_link.name, active.name)
		t_parked = self.make("Life Task", title="ux6 mig parked task", area=tea, status="Someday")
		frappe.db.sql("update `tabLife Task` set someday_with=%s where name=%s", (parked.name, t_parked.name))
		note = self.make("Life Note", title="ux6 mig note", area=tea, content_md="x")
		set_old_project("Life Note", note.name, active.name)
		chat = self.make("Life Chat Log", title="ux6 mig chat", date=today(), area=tea)
		set_old_project("Life Chat Log", chat.name, hold.name)
		vault = self.make("Life Vault Document", title="ux6 mig doc", doc_type="Other", area=money)
		set_old_project("Life Vault Document", vault.name, done.name)
		child = self.make("Life Goal", title="ux6 mig goal under a project", goal_type="Annual", target_date=add_days(today(), 200), area=tea)
		set_old_project("Life Goal", child.name, active.name)
		band = counts.open_band(PRIVATE)

		projects_into_goals.execute()

		goal_of = {p.name: frappe.db.get_value("Life Project", p.name, "migrated_to") for p in (active, hold, done, dropped, parked)}
		self.assertTrue(all(goal_of.values()), goal_of)
		self.assertEqual(len(set(goal_of.values())), 5)

		def g(project):
			return frappe.get_doc("Life Goal", goal_of[project.name])

		for p in (active, hold, done, dropped, parked):
			self.assertEqual((g(p).goal_type, g(p).title, g(p).space, g(p).area), ("Open", p.title, PRIVATE, p.area))
		self.assertEqual((g(active).outcome, g(active).on_hold, g(active).is_someday), ("In Progress", 0, 0))
		self.assertEqual((g(active).done_when, g(active).notes_md, g(active).target_date), ("Mandir built", "notes", getdate(active.target_date)))
		self.assertEqual((g(hold).outcome, g(hold).on_hold), ("In Progress", 1))
		self.assertEqual((g(done).outcome, g(done).closed_on, g(done).completed_on), ("Achieved", getdate(done_day), getdate(done_day)))
		self.assertEqual((g(dropped).outcome, g(dropped).completed_on), ("Dropped", getdate(done_day)))
		self.assertEqual((g(parked).outcome, g(parked).is_someday, g(parked).someday_note), ("In Progress", 1, "later"))
		self.assertEqual(getdate(g(parked).someday_review_on), getdate(add_months(today(), 2)))
		self.assertEqual(str(g(active).creation), str(active.creation))
		# a finished project's goal is not archived by the migration: its archive state is the project's
		self.assertEqual(g(done).is_archived, 0)

		# every record that pointed at a project points at its goal
		self.assertEqual(frappe.db.get_value("Life Task", t_plain.name, "goal"), goal_of[active.name])
		self.assertEqual(frappe.db.get_value("Life Task", t_done_proj.name, "goal"), goal_of[done.name])
		self.assertEqual(frappe.db.get_value("Life Task", t_parked.name, "someday_with"), goal_of[parked.name])
		self.assertEqual(frappe.db.get_value("Life Note", note.name, "goal"), goal_of[active.name])
		self.assertEqual(frappe.db.get_value("Life Chat Log", chat.name, "goal"), goal_of[hold.name])
		self.assertEqual(frappe.db.get_value("Life Vault Document", vault.name, "goal"), goal_of[done.name])
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_doctype": "Life Task", "ref_name": t_plain.name}, "goal"), goal_of[active.name])
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_doctype": "Life Note", "ref_name": note.name}, "goal"), goal_of[active.name])
		# a goal that belonged to a project serves the project's goal
		self.assertEqual(frappe.db.get_value("Life Goal", child.name, "serves"), goal_of[active.name])
		# a task with both keeps its goal, and that goal serves the project's goal
		self.assertEqual(frappe.db.get_value("Life Task", t_both.name, "goal"), own.name)
		self.assertEqual(frappe.db.get_value("Life Goal", own.name, "serves"), goal_of[hold.name])
		# a task whose goal already serves another goal keeps both and is linked to the project's goal
		self.assertEqual(frappe.db.get_value("Life Task", t_link.name, "goal"), served.name)
		self.assertEqual(frappe.db.get_value("Life Goal", served.name, "serves"), longer.name)
		self.assertTrue(frappe.db.exists("Life Link", {"from_doctype": "Life Task", "from_name": t_link.name,
			"to_doctype": "Life Goal", "to_name": goal_of[active.name]}))

		# the open-task counts do not move
		after = counts.open_band(PRIVATE)
		for key in ("open_tasks", "stuck"):
			self.assertEqual(after[key]["n"], band[key]["n"], key)

		# a second run changes nothing
		before = self.snapshot()
		projects_into_goals.execute()
		self.assertEqual(self.snapshot(), before)


class TestServes(LifeTestCase):
	def test_served_by_and_no_loops(self):
		top = self.make("Life Goal", title="ux6 serves top", goal_type="Annual", target_date=add_days(today(), 300), area=self.areas["Tea"])
		mid = goals.create("ux6 serves mid", goal_type="Open", space=PRIVATE, area=self.areas["Tea"], serves=top.name, done_when="Done")
		low = goals.create("ux6 serves low", goal_type="Open", space=PRIVATE, area=self.areas["Tea"], serves=mid["name"])
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
		g = goals.create("ux6 state goal", goal_type="Open", space=PRIVATE, area=self.areas["Tea"])["name"]
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
		goal = self.make("Life Goal", title="ux6 alias goal", goal_type="Open", area=self.areas["Tea"])
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
