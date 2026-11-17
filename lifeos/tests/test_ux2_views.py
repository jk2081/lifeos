"""UX fixes, set 2: saved list views, and standard Frappe filters, order_by and summaries on the list methods."""
import frappe
from frappe.utils import add_days, getdate, today

from lifeos.api import archive, chats, inbox, library, projects, tasks, timeline, vault, views
from lifeos.api.utils import std_filters, std_order
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


NO_SPACE_SCREEN = "ux2-test-screen"


class TestViewState(LifeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		# only the rows these tests made: the test site also holds views saved through the browser by the same users
		frappe.db.delete("Life View State", {"space": ("in", [PRIVATE, SHARED])})
		frappe.db.delete("Life View State", {"screen": NO_SPACE_SCREEN})
		super().tearDown()

	def mine(self):
		"""The session user's saved views in the test spaces."""
		return {k: v for k, v in views.get_all().items() if k.split("|", 1)[1] in (PRIVATE, SHARED)}

	def test_a_user_reads_and_writes_only_their_own_states(self):
		views.save("tasks", PRIVATE, {"query": {"status": "Done"}, "view": "table"})
		views.save("tasks", SHARED, {"query": {"priority": "I"}})
		views.save("vault", PRIVATE, {"query": {}})
		mine = self.mine()
		self.assertEqual(mine[f"tasks|{PRIVATE}"], {"query": {"status": "Done"}, "view": "table"})
		self.assertEqual(mine[f"tasks|{SHARED}"]["query"], {"priority": "I"})
		self.assertEqual(len(mine), 3)
		# saving again replaces: one row per user, screen and space
		views.save("tasks", PRIVATE, {"query": {}})
		self.assertEqual(views.get_all()[f"tasks|{PRIVATE}"], {"query": {}})
		self.assertEqual(frappe.db.count("Life View State", {"user": OWNER, "screen": "tasks", "space": PRIVATE}), 1)
		row = frappe.db.get_value("Life View State", {"user": OWNER, "screen": "tasks", "space": PRIVATE}, "name")

		self.as_user(FAMILY)
		self.assertEqual(self.mine(), {})  # nothing of the owner's, although both are members of the shared space
		views.save("tasks", SHARED, {"query": {"status": "Waiting"}})
		self.assertEqual(self.mine(), {f"tasks|{SHARED}": {"query": {"status": "Waiting"}}})
		self.assertFalse(any(k.endswith(f"|{PRIVATE}") for k in views.get_all()))
		self.assertRaises(frappe.PermissionError, views.save, "tasks", PRIVATE, {"query": {}})  # not a member of that space
		# the DocType itself is closed too: no listing, reading or changing another person's row
		self.assertEqual(frappe.get_list("Life View State", filters={"user": OWNER}), [])
		self.assertEqual(len(frappe.get_list("Life View State", filters={"space": ("in", [PRIVATE, SHARED])})), 1)
		self.assertEqual({r.user for r in frappe.get_list("Life View State", fields=["user"])}, {FAMILY})
		self.assertFalse(frappe.has_permission("Life View State", "read", frappe.get_doc("Life View State", row)))
		self.assertFalse(frappe.has_permission("Life View State", "write", frappe.get_doc("Life View State", row)))
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Life View State", row).check_permission, "write")

		self.as_user(OWNER)
		self.assertEqual(views.get_all()[f"tasks|{SHARED}"]["query"], {"priority": "I"})  # the family member's save did not touch it

	def test_agents_have_no_saved_views(self):
		views.save("tasks", PRIVATE, {"query": {"status": "Done"}})
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, views.get_all)
		self.assertRaises(frappe.PermissionError, views.save, "tasks", PRIVATE, {"query": {}})
		self.assertRaises(frappe.PermissionError, frappe.get_list, "Life View State")
		self.assertFalse(frappe.has_permission("Life View State", "read"))
		self.assertFalse(frappe.has_permission("Life View State", "create"))

	def test_what_is_saved(self):
		views.save("tasks", PRIVATE, {"query": {"status": "Done"}, "open": "task:abc"})
		self.assertNotIn("open", views.get_all()[f"tasks|{PRIVATE}"])  # the open record is never saved
		self.assertRaises(frappe.ValidationError, views.save, "", PRIVATE, {})
		self.assertRaises((frappe.ValidationError, frappe.FrappeTypeError), views.save, "tasks", PRIVATE, [1, 2])  # refused by the type hint since pre-step 6
		self.assertRaises(frappe.ValidationError, views.save, "tasks", PRIVATE, {"query": {"x": "y" * 30000}})
		self.assertRaises(frappe.PermissionError, views.save, "tasks", "No such space", {})
		views.save(NO_SPACE_SCREEN, None, {"view": "a"})  # a screen that is not tied to a space
		self.assertEqual(views.get_all()[f"{NO_SPACE_SCREEN}|"], {"view": "a"})
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, views.get_all)


class TestStandardFilters(LifeTestCase):
	def names(self, rows, key="name"):
		return {r[key] for r in rows}

	def test_field_names_are_checked_against_the_doctype(self):
		for bad in ("no_such_field", "title; drop table tabUser", "t.title", "`title`", "space or 1=1", "", "also_in", "organisation_section"):
			self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[[bad, "=", "x"]])
			self.assertRaises(frappe.ValidationError, std_filters, "Life Task", [[bad, "=", "x"]])
		for bad in ("no_such_field desc", "title desc; drop table tabUser", "title sideways", "title desc nulls"):
			self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, order_by=bad)
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["title", "regexp", "x"]])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["title", "=", ["a", "b"]]])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["title"]])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["Life Note", "title", "=", "x"]])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["title", "like", "x"]] * 30)
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, fields=["password"])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, summary={"fields": ["nope"], "aggregates": []})
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, summary={"fields": ["status"], "aggregates": [{"function": "sleep"}]})
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE,
			summary={"fields": ["status"], "aggregates": [{"function": "max", "fieldname": "1); drop table x; --"}]})
		# a value is always a parameter, never part of the SQL
		conds, values = std_filters("Life Task", [["title", "=", "x' or '1'='1"]], "t")
		self.assertEqual(conds, ["ifnull(t.`title`, '') = %(sf0)s"])
		self.assertEqual(values, {"sf0": "x' or '1'='1"})
		self.assertEqual(std_order("Life Task", "due_date desc, title asc", "t"), "t.`due_date` desc, t.`title` asc")
		self.assertEqual(std_order("Life Task", "priority desc", "t", {"priority": "case t.priority when 'I' then 1 else 5 end"}),
			"case t.priority when 'I' then 1 else 5 end desc")
		self.assertIsNone(std_order("Life Task", "", "t"))

	def test_task_filters_operators_and_sort(self):
		now = getdate(today())
		a = self.make("Life Task", title="ux2 alpha", priority="I", due_date=add_days(now, 2), area=self.areas["Tea"])
		b = self.make("Life Task", title="ux2 beta", priority="II", due_date=add_days(now, 9), waiting_on="the bank", status="Waiting")
		c = self.make("Life Task", title="ux2 gamma")
		get = lambda **kw: tasks.list(space=PRIVATE, page_length=100, filters=[["title", "like", "ux2"], *kw.pop("f", [])], **kw)  # noqa: E731
		self.assertEqual(self.names(get()["tasks"]), {a.name, b.name, c.name})
		self.assertEqual(get()["total"], 3)
		self.assertEqual(self.names(get(f=[["priority", "=", "I"]])["tasks"]), {a.name})
		self.assertEqual(self.names(get(f=[["priority", "!=", "I"]])["tasks"]), {b.name, c.name})
		self.assertEqual(self.names(get(f=[["priority", "in", ["I", "II"]]])["tasks"]), {a.name, b.name})
		self.assertEqual(self.names(get(f=[["priority", "not in", "I, II"]])["tasks"]), {c.name})
		self.assertEqual(self.names(get(f=[["due_date", "is", "not set"]])["tasks"]), {c.name})
		self.assertEqual(self.names(get(f=[["due_date", "is", "set"]])["tasks"]), {a.name, b.name})
		self.assertEqual(self.names(get(f=[["waiting_on", "is", "set"]])["tasks"]), {b.name})
		self.assertEqual(self.names(get(f=[["due_date", ">", str(add_days(now, 5))]])["tasks"]), {b.name})
		self.assertEqual(self.names(get(f=[["due_date", "between", [str(now), str(add_days(now, 3))]]])["tasks"]), {a.name})
		self.assertEqual(self.names(get(f=[["title", "not like", "beta"]])["tasks"]), {a.name, c.name})
		self.assertEqual(self.names(get(f=[["Life Task", "priority", "=", "II"]])["tasks"]), {b.name})
		self.assertEqual(self.names(get(f=[["creation", "timespan", "today"]])["tasks"]), {a.name, b.name, c.name})
		# standard filters narrow the list's own filters: they never widen them, and the space is always applied
		self.assertEqual(self.names(get(area=self.areas["Tea"])["tasks"]), {a.name})
		self.assertEqual(self.names(get(status="Waiting", f=[["priority", "=", "II"]])["tasks"]), {b.name})
		self.assertEqual(get(f=[["space", "=", SHARED]])["total"], 0)
		self.assertEqual([t["title"] for t in get(order_by="title desc")["tasks"]], ["ux2 gamma", "ux2 beta", "ux2 alpha"])
		self.assertEqual([t["title"] for t in get(order_by="priority desc, title asc")["tasks"]], ["ux2 gamma", "ux2 beta", "ux2 alpha"])
		self.assertEqual(get(fields=["waiting_on", "modified"])["tasks"][0].keys() >= {"waiting_on", "modified", "title"}, True)
		s = get(summary={"fields": ["status"], "aggregates": [{"function": "count"}], "order_by": "_aggregate_0 desc", "totals": 1})["summary"]
		self.assertEqual({r["status"]: r["_aggregate_0"] for r in s["rows"]}, {"Open": 2, "Waiting": 1})
		self.assertEqual(s["total"], 2)
		self.assertEqual(s["totals"]["_aggregate_0"], 3)
		s = get(summary={"fields": ["area"], "aggregates": [{"function": "count"}, {"function": "max", "fieldname": "due_date"}]})["summary"]
		tea = next(r for r in s["rows"] if r["area"] == self.areas["Tea"])
		self.assertEqual((tea["area__label"], tea["_aggregate_0"], tea["_aggregate_1"]), ("Tea", 1, str(add_days(now, 2))))

	def test_every_list_takes_standard_filters(self):
		tea = self.areas["Tea"]
		project = self.make("Life Project", title="ux2 project", area=tea)
		self.make("Life Project", title="ux2 other", area=tea)
		note = self.make("Life Note", title="ux2 note", area=tea, content_md="x")
		self.make("Life Note", title="ux2 second", area=tea, content_md="x")
		doc = self.make("Life Vault Document", title="ux2 passport", doc_type="Travel", area=tea, number_last4="1234")
		self.make("Life Vault Document", title="ux2 lease", doc_type="Property", area=tea)
		chat = self.make("Life Chat Log", title="ux2 chat", date=today(), area=tea, assistant="ChatGPT")
		self.make("Life Chat Log", title="ux2 chat two", date=today(), area=tea)
		item = self.make("Life Inbox Item", title="ux2 item", source_type="Email")
		self.make("Life Inbox Item", title="ux2 item two")
		like = [["title", "like", "ux2"]]
		self.assertEqual(self.names(projects.list(space=PRIVATE, filters=[*like, ["title", "=", "ux2 project"]])["projects"]), {project.name})
		self.assertEqual(projects.list(space=PRIVATE, filters=like)["total"], 2)
		self.assertEqual([p["title"] for p in projects.list(space=PRIVATE, filters=like, order_by="title desc")["projects"]], ["ux2 project", "ux2 other"])
		self.assertEqual(self.names(vault.list(space=PRIVATE, filters=[*like, ["number_last4", "=", "1234"]])["documents"]), {doc.name})
		self.assertEqual(vault.list(space=PRIVATE, filters=like)["total"], 2)
		self.assertEqual(vault.list(space=PRIVATE, filters=like, fields=["issue_date"])["documents"][0].keys() >= {"issue_date"}, True)
		self.assertEqual(self.names(chats.list(space=PRIVATE, filters=[*like, ["assistant", "=", "ChatGPT"]])["chats"]), {chat.name})
		self.assertEqual(self.names(inbox.list(space=PRIVATE, filters=[*like, ["source_type", "=", "Email"]])["items"]), {item.name})
		self.assertEqual(inbox.list(space=PRIVATE, filters=like)["total"], 2)
		# the cross-type lists filter on the columns of Life Index
		self.assertEqual(self.names(library.list(space=PRIVATE, filters=[["title", "=", "ux2 note"]])["notes"]), {note.name})
		got = timeline.get(space=PRIVATE, filters=[*like, ["ref_doctype", "=", "Life Vault Document"]])
		self.assertEqual(got["total"], 2)
		self.assertEqual({e["ref_name"] for d in got["days"] for e in d["entries"]} >= {doc.name}, True)
		self.assertEqual(timeline.get(space=PRIVATE, filters=like, summary={"fields": ["kind"], "aggregates": [{"function": "count"}]})["summary"]["total"] >= 4, True)
		frappe.db.set_value("Life Note", note.name, {"is_archived": 1, "archived_on": today(), "archive_reason": "Manual"})
		frappe.get_doc("Life Note", note.name).save()
		self.assertEqual({r["ref_name"] for r in archive.list(space=PRIVATE, filters=[["kind", "=", "Note"], *like])["records"]}, {note.name})
		for method in (projects.list, vault.list, chats.list, inbox.list, library.list, archive.list):
			self.assertRaises(frappe.ValidationError, method, space=PRIVATE, filters=[["no_such_field", "=", 1]])
			self.assertRaises(frappe.ValidationError, method, space=PRIVATE, order_by="no_such_field desc")
		self.assertRaises(frappe.ValidationError, timeline.get, space=PRIVATE, filters=[["no_such_field", "=", 1]])
		# a second user still sees nothing from a private space, whatever the filters say
		self.as_user(FAMILY)
		for method in (tasks.list, projects.list, vault.list, chats.list, inbox.list, library.list, archive.list, timeline.get):
			self.assertRaises(frappe.PermissionError, method, space=PRIVATE, filters=[["space", "=", PRIVATE]])
