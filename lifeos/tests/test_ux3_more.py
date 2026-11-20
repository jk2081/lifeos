"""UX fixes, set 3: Settings (archive, restore, order, counts), the three permission tightenings, and goals of every type."""
import frappe
from frappe.utils import add_days, today

from lifeos import permissions
from lifeos.api import area, goals, journal, links, search, settings, tasks, timeline, vault
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


class TestSettings(LifeTestCase):
	# issue 11: areas are the seven areas of life with their parts; the seven are switched off, not archived, so only a part is
	# archived, and a part holds no parts of its own
	def test_archive_a_part_and_restore(self):
		career = self.life["Career"]
		part = settings.save_item("area", space=PRIVATE, title="ux3 part", parent_area=career)["name"]
		task = self.make("Life Task", title="ux3 filed under the part", area=part, status="Done")  # issue 12: open work must move first
		out = settings.save_item("area", name=part, is_archived=1)
		self.assertEqual(out["archived_children"], [])
		self.assertEqual(frappe.db.get_value("Life Area", part, "is_archived"), 1)
		self.assertEqual(str(frappe.db.get_value("Life Area", part, "archived_on")), today())
		# the records under it are not changed, and the pickers no longer offer it
		self.assertEqual(frappe.db.get_value("Life Task", task.name, ["area", "is_archived"]), (part, 0))
		self.assertNotIn(part, [a.name for a in area.tree(PRIVATE)["areas"]])
		got = settings.get(PRIVATE)
		row = next(a for a in got["areas"] if a.name == part)
		self.assertTrue(row.is_archived and row["count"] >= 1)
		# restored: back in place under its area of life
		settings.save_item("area", name=part, is_archived=0)
		self.assertEqual(frappe.db.get_value("Life Area", part, ["is_archived", "parent_area"]), (0, career))
		self.assertIsNone(frappe.db.get_value("Life Area", part, "archived_on"))
		self.assertRaises(frappe.ValidationError, settings.save_item, "area", name=career, is_archived=1)

	def test_reorder_and_nest(self):
		career, mind = self.life["Career"], self.life["Mind"]
		a = settings.save_item("area", space=PRIVATE, title="ux3 order a", parent_area=career)["name"]
		b = settings.save_item("area", space=PRIVATE, title="ux3 order b", parent_area=career)["name"]
		settings.reorder("area", frappe.as_json([b, a]), parent_area=career)
		self.assertLess(frappe.db.get_value("Life Area", b, "sort_order"), frappe.db.get_value("Life Area", a, "sort_order"))
		settings.reorder("area", frappe.as_json([a]), parent_area=mind)
		self.assertEqual(frappe.db.get_value("Life Area", a, "parent_area"), mind)
		# one level deep: a part under a part, or a part at the top, is refused
		c = settings.save_item("area", space=PRIVATE, title="ux3 order c", parent_area=career)["name"]
		self.assertRaises(frappe.ValidationError, settings.save_item, "area", name=c, parent_area=a)
		self.assertRaises(frappe.ValidationError, settings.save_item, "area", name=c, parent_area="")

	def test_tags_habits_dimensions_archive_and_leave_the_pickers(self):
		tag = settings.save_item("tag", space=PRIVATE, title="ux3tag")["name"]
		habit = settings.save_item("habit", space=PRIVATE, title="ux3 habit")["name"]
		dim = settings.save_item("dimension", space=PRIVATE, title="ux3 dim")["name"]
		for kind, name in (("tag", tag), ("habit", habit), ("dimension", dim)):
			settings.save_item(kind, name=name, is_archived=1)
		from lifeos.api.inbox import space_context
		ctx = space_context(PRIVATE)
		self.assertNotIn(tag, [t.name for t in ctx["tags"]])
		self.assertNotIn(habit, [t.name for t in ctx["habits"]])
		self.assertNotIn(dim, [t.name for t in ctx["dimensions"]])

	def test_no_role_names_and_no_administrator(self):
		got = settings.get(PRIVATE)
		text = frappe.as_json(got)
		self.assertNotIn("Life Agent", text)
		self.assertNotIn("Life User", text)
		for s in got["spaces"]:
			self.assertNotIn("Administrator", [m["user"] for m in s["members"]])
		# issue 1: agents are listed with people in Members, marked by kind, and again in Agents
		self.assertTrue(any(m["user"] == AGENT and m["is_agent"] for s in got["spaces"] for m in s["members"]))
		self.assertIn(AGENT, [a["user"] for a in got["agents"]])


class TestAgentsAndTheVault(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		self.as_user(OWNER)
		self.doc = self.make("Life Vault Document", title="ux3 secret passport", doc_type="ID", area=self.areas["Tea"],
			expiry_date=add_days(today(), 20), notes_md="ux3vaultword")
		self.file = frappe.get_doc({"doctype": "File", "file_name": "ux3-secret.txt", "content": b"secret", "is_private": 1,
			"attached_to_doctype": "Life Vault Document", "attached_to_name": self.doc.name}).insert()
		self.make("Life Note", title="ux3 note that links", content_md="see [[ux3 secret passport]]", area=self.areas["Tea"])

	def can_see(self):
		"""What the session user can reach of the document, by every path that returns records."""
		seen = {}
		try:
			vault.get(self.doc.name)
			seen["get"] = True
		except (frappe.DoesNotExistError, frappe.PermissionError):
			seen["get"] = False
		seen["list"] = any(d.name == self.doc.name for d in vault.list(space=PRIVATE)["documents"])
		seen["count"] = vault.list(space=PRIVATE, filters=frappe.as_json([["title", "like", "ux3 secret%"]]))["total"] > 0
		seen["rest"] = bool(frappe.get_list("Life Vault Document", filters={"name": self.doc.name}))
		seen["index"] = bool(frappe.get_list("Life Index", filters={"ref_name": self.doc.name}))
		seen["search"] = any(r.ref_name == self.doc.name for r in search.query("ux3vaultword")["results"])
		entries = [e for d in timeline.get(space=PRIVATE, page_length=200)["days"] for e in d["entries"]]
		seen["timeline"] = any(e.ref_name == self.doc.name for e in entries)
		# area pages went in set 6: the lens narrows the timeline to the area instead
		lens = [e for d in timeline.get(space=PRIVATE, area=self.areas["Tea"], page_length=200)["days"] for e in d["entries"]]
		seen["area"] = any(e.ref_name == self.doc.name for e in lens)
		seen["file"] = bool(frappe.has_permission("File", "read", self.file))
		seen["suggest"] = any(r["name"] == self.doc.name for r in links.suggest(space=PRIVATE, text="ux3 secret"))
		return seen

	def test_switch_off_hides_everything_from_the_agent(self):
		self.as_user(AGENT)
		seen = self.can_see()
		self.assertFalse(any(seen.values()), seen)
		# the same answer as a record that does not exist
		self.assertRaises(frappe.DoesNotExistError, vault.get, self.doc.name)

	def test_switch_on_lets_the_agent_read(self):
		self.as_user(OWNER)
		settings.set_agent_vault(PRIVATE, 1)
		self.as_user(AGENT)
		seen = self.can_see()
		self.assertTrue(all(seen.values()), seen)

	def test_people_are_not_affected(self):
		self.as_user(OWNER)
		self.assertTrue(all(self.can_see().values()))
		settings.set_agent_vault(PRIVATE, 1)
		self.as_user(OWNER)
		self.assertTrue(all(self.can_see().values()))

	def test_only_an_admin_changes_the_switch(self):
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, settings.set_agent_vault, SHARED, 1)
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, settings.set_agent_vault, PRIVATE, 1)


class TestDeskAndRoles(LifeTestCase):
	def test_life_user_and_agent_roles_have_no_desk_access(self):
		self.assertEqual(frappe.db.get_value("Role", "Life User", "desk_access"), 0)
		self.assertEqual(frappe.db.get_value("Role", "Life Agent", "desk_access"), 0)
		self.assertEqual(frappe.db.get_value("User", FAMILY, "user_type"), "Website User")
		self.assertEqual(frappe.db.get_value("User", AGENT, "user_type"), "Website User")

	def test_agent_with_a_person_role_is_refused(self):
		frappe.set_user("Administrator")
		user = frappe.get_doc("User", AGENT)
		user.append("roles", {"role": "Life User"})
		self.assertRaises(frappe.ValidationError, user.save)


class TestGoals(LifeTestCase):
	def test_types_and_validation(self):
		self.assertRaises(frappe.ValidationError, goals.create, "ux3 annual no date", "Annual", space=PRIVATE)
		g = goals.create("ux3 annual", "Annual", space=PRIVATE, target_date="2026-12-31", area=self.areas["Tea"])
		self.assertIsNone(frappe.db.get_value("Life Goal", g["name"], "cycle"))
		self.assertRaises(frappe.ValidationError, goals.create, "ux3 12wy no cycle", "12 Week Year", space=PRIVATE)
		doc = frappe.get_doc("Life Goal", g["name"])
		doc.cycle = "nonexistent"
		self.assertRaises(Exception, doc.save)

	def test_task_completion(self):
		g = goals.create("ux3 open goal", "Open", space=PRIVATE, area=self.areas["Tea"])["name"]
		self.assertEqual(goals.task_counts([g]), {})
		t1 = self.make("Life Task", title="ux3 g1", goal=g)
		self.make("Life Task", title="ux3 g2", goal=g)
		t3 = self.make("Life Task", title="ux3 g3", goal=g)
		tasks.set_status(t1.name, "Done")
		tasks.set_status(t3.name, "Dropped")
		self.assertEqual(goals.task_counts([g])[g], (1, 2))
		from lifeos.api import archive as archive_api
		archive_api.set("Life Task", t1.name)
		self.assertEqual(goals.task_counts([g])[g], (1, 2))  # archiving a done task does not lower the figure
		rows = goals.list(space=PRIVATE, filters=frappe.as_json([["title", "like", "ux3 open goal"]]))["goals"]
		self.assertEqual((rows[0].tasks_done, rows[0].tasks_counted, rows[0].score), (1, 2, None))

	def test_list_tabs_and_close(self):
		g = goals.create("ux3 closable", "Open", space=PRIVATE)["name"]
		mine = frappe.as_json([["title", "like", "ux3 closable"]])
		self.assertEqual(goals.list(space=PRIVATE, filters=mine)["tabs"], {"in_progress": 1, "achieved": 0, "closed": 0, "someday": 0, "all": 1})
		goals.close(g, "Dropped", "not now")
		self.assertEqual(str(frappe.db.get_value("Life Goal", g, "closed_on")), today())
		tabs = goals.list(space=PRIVATE, filters=mine)["tabs"]
		self.assertEqual(tabs, {"in_progress": 0, "achieved": 0, "closed": 1, "someday": 0, "all": 1})
		self.assertEqual(goals.list(space=PRIVATE, state="closed", filters=mine)["total"], 1)

	def test_add_to_cycle_keeps_tasks(self):
		cycle = frappe.get_doc({"doctype": "Life Cycle", "space": PRIVATE, "title": "ux3 cycle", "start_date": add_days(today(), -7), "status": "Active"}).insert()
		g = goals.create("ux3 moving", "Open", space=PRIVATE)["name"]
		t = self.make("Life Task", title="ux3 moving task", goal=g)
		self.assertNotIn(g, [x["name"] for x in journal.goals(space=PRIVATE)["cycles"][0]["goals"]] if journal.goals(space=PRIVATE)["cycles"] else [])
		goals.add_to_cycle(g, cycle.name)
		self.assertEqual(frappe.db.get_value("Life Goal", g, ["goal_type", "cycle", "carried_from"]), ("12 Week Year", cycle.name, None))
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "goal"), g)
		from lifeos import journal as rules
		self.assertIn(g, [x["name"] for x in rules.grid(cycle.name)["goals"]])

	def test_agents_cannot_create_or_close(self):
		g = goals.create("ux3 agent goal", "Open", space=PRIVATE)["name"]
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, goals.create, "ux3 by agent", "Open", space=PRIVATE)
		self.assertRaises(frappe.PermissionError, goals.close, g, "Achieved")

	def test_other_space_member_sees_no_goals_or_counts(self):
		g = goals.create("ux3 private goal", "Open", space=PRIVATE)["name"]
		self.make("Life Task", title="ux3 private goal task", goal=g)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, goals.list, space=PRIVATE)
		self.assertEqual(goals.task_counts([g]), {})
		self.assertNotIn(g, [x.name for x in goals.list(space=SHARED, state="all")["goals"]])
