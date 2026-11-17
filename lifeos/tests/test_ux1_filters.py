"""UX fixes, set 1: the filters behind the list screens, and the counts that link to them."""
import frappe
from frappe.utils import add_days, getdate, today

from lifeos import archive as archive_rules
from lifeos.api import archive, chats, goals, inbox, library, tasks, vault
from lifeos.api import area as area_api
from lifeos.api import calendar as calendar_api
from lifeos.api import today as today_api
from lifeos.tests.base import FAMILY, PRIVATE, LifeTestCase


class TestListFilters(LifeTestCase):
	def names(self, rows, key="name"):
		return {r[key] for r in rows}

	def test_task_due_filter(self):
		now = getdate(today())
		late = self.make("Life Task", title="ux1 late", due_date=add_days(now, -3))
		due = self.make("Life Task", title="ux1 today", due_date=now)
		far = self.make("Life Task", title="ux1 far", due_date=add_days(now, 40))
		none = self.make("Life Task", title="ux1 no date")
		get = lambda **f: self.names(tasks.list(space=PRIVATE, page_length=100, **f)["tasks"])  # noqa: E731
		self.assertIn(late.name, get(due="overdue"))
		self.assertNotIn(due.name, get(due="overdue"))
		self.assertEqual({late.name, due.name} & get(due="today"), {due.name})
		both = get(due="today,overdue")
		self.assertTrue({late.name, due.name} <= both)
		self.assertFalse({far.name, none.name} & both)
		self.assertIn(none.name, get(due="none"))
		self.assertNotIn(due.name, get(due="none"))
		self.assertIn(due.name, get(due="week"))
		self.assertNotIn(far.name, get(due="week"))
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, due="sometime")
		# the Today numbers are counted with the same filters as the lists they link to
		t = today_api.get(space=PRIVATE)
		self.assertEqual(t["tasks"]["due"], tasks.list(space=PRIVATE, due="today,overdue")["total"])
		self.assertEqual(t["tasks"]["overdue"], tasks.list(space=PRIVATE, due="overdue")["total"])
		self.assertEqual(t["open_loops"], tasks.list(space=PRIVATE, loops=1)["total"])

	def test_task_done_loops_sort_and_completed(self):
		goal = self.make("Life Goal", title="ux1 goal", goal_type="Open", area=self.areas["Tea"])
		a = self.make("Life Task", title="ux1 b open", goal=goal.name, area=self.areas["Tea"])
		b = self.make("Life Task", title="ux1 a done", goal=goal.name, area=self.areas["Tea"], status="Done")
		c = self.make("Life Task", title="ux1 c carried", goal=goal.name, area=self.areas["Tea"], status="Carried")
		get = lambda **f: tasks.list(space=PRIVATE, goal=goal.name, page_length=100, **f)  # noqa: E731
		self.assertEqual(self.names(get()["tasks"]), {a.name})
		self.assertEqual(self.names(get(done=1)["tasks"]), {a.name, b.name})
		self.assertEqual(self.names(get(status="Carried")["tasks"]), {c.name})
		# "4 of 10 tasks done" on a goal card: the total equals the list with Show done and archived records
		card = next(g for g in goals.list(space=PRIVATE, goal_type="Open")["goals"] if g["name"] == goal.name)
		self.assertEqual(card["tasks_counted"], get(done=1, include_archived=1)["total"])
		self.assertEqual([t["title"] for t in get(done=1, sort="title")["tasks"]], ["ux1 a done", "ux1 b open"])
		self.assertEqual([t["title"] for t in get(done=1, sort="title", dir="desc")["tasks"]], ["ux1 b open", "ux1 a done"])
		self.assertEqual([t["title"] for t in get(done=1, sort="title; drop table x")["tasks"]][:0], [])  # an unknown sort is ignored
		self.assertEqual(self.names(get(status="Done", completed_from=today(), completed_to=today())["tasks"]), {b.name})
		self.assertEqual(get(status="Done", completed_from=add_days(today(), 1))["total"], 0)
		old = self.make("Life Task", title="ux1 loop", goal=goal.name, area=self.areas["Tea"])
		frappe.db.set_value("Life Task", old.name, "creation", add_days(today(), -30), update_modified=False)
		self.assertEqual(self.names(get(loops=1)["tasks"]), {old.name})
		self.assertEqual(tasks.list(space=PRIVATE, loops=1)["total"], tasks.open_loops(space=PRIVATE)["total"])

	def test_area_filter_takes_sub_areas(self):
		sub = self.make("Life Area", area_name="ux1 Estate", parent_area=self.areas["Tea"])
		t = self.make("Life Task", title="ux1 in sub", area=sub.name)
		unfiled = self.make("Life Task", title="ux1 unfiled")
		self.assertIn(t.name, self.names(tasks.list(space=PRIVATE, area=self.areas["Tea"], page_length=100)["tasks"]))
		self.assertNotIn(t.name, self.names(tasks.list(space=PRIVATE, area=self.areas["Money"], page_length=100)["tasks"]))
		none = self.names(tasks.list(space=PRIVATE, area="none", page_length=100)["tasks"])
		self.assertIn(unfiled.name, none)
		self.assertNotIn(t.name, none)
		tree = {a["name"]: a for a in area_api.tree(space=PRIVATE)["areas"]}
		self.assertEqual(tree[self.areas["Tea"]]["open_tasks"], tasks.list(space=PRIVATE, area=self.areas["Tea"])["total"])

	def test_inbox_filters(self):
		a = self.make("Life Inbox Item", title="ux1 voice", source_type="Voice Note", status="New", area=self.areas["Tea"])
		b = self.make("Life Inbox Item", title="ux1 mail", source_type="Email", status="New")
		frappe.db.set_value("Life Inbox Item", b.name, "received_on", add_days(today(), -10))
		get = lambda **f: inbox.list(space=PRIVATE, page_length=100, **f)  # noqa: E731
		self.assertEqual({a.name, b.name} & self.names(get(source_type="Voice Note")["items"]), {a.name})
		self.assertEqual({a.name, b.name} & self.names(get(area=self.areas["Tea"])["items"]), {a.name})
		self.assertEqual({a.name, b.name} & self.names(get(area="none")["items"]), {b.name})
		self.assertEqual({a.name, b.name} & self.names(get(from_date=add_days(today(), -1))["items"]), {a.name})
		self.assertEqual({a.name, b.name} & self.names(get(to_date=add_days(today(), -5))["items"]), {b.name})
		res = get(status="New", source_type="Email")
		self.assertEqual(res["total"], len(res["items"]))
		self.assertEqual(get(status='["New", "Processing"]')["total"], get(status="New")["total"] + get(status="Processing")["total"])
		frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": a.name, "kind": "Task", "preview": "x",
			"payload": "{}", "confidence": 0.9, "status": "Pending"}).insert(ignore_permissions=True)
		res = get(source_type="Voice Note")
		row = next(r for r in res["items"] if r["name"] == a.name)
		self.assertEqual((row["pending"], row["proposals"], row["area_name"]), (1, 1, "Tea"))
		self.assertEqual(res["pending_total"], sum(r["pending"] for r in res["items"]))

	def test_open_goal_filters(self):
		sub = self.make("Life Area", area_name="ux1 Garden", parent_area=self.areas["Money"])
		a = self.make("Life Goal", title="ux1 active", goal_type="Open", area=sub.name)
		h = self.make("Life Goal", title="ux1 hold", goal_type="Open", area=self.areas["Money"], on_hold=1)
		get = lambda **f: goals.list(space=PRIVATE, goal_type="Open", **f)  # noqa: E731
		self.assertEqual(self.names(get(area=self.areas["Money"])["goals"]), {a.name, h.name})
		self.assertEqual(self.names(get(area=self.areas["Money"], filters=[["on_hold", "=", 0]])["goals"]), {a.name})
		self.assertEqual(get(area=self.areas["Money"], filters=[["on_hold", "=", 1]])["total"], 1)
		self.assertEqual(get(area=self.areas["Money"], state="achieved")["total"], 0)
		tree = {r["name"]: r for r in area_api.tree(space=PRIVATE)["areas"]}
		self.assertEqual(tree[self.areas["Money"]]["goals"], goals.list(space=PRIVATE, area=self.areas["Money"])["total"])
		self.assertRaises(frappe.ValidationError, goals.list, space=PRIVATE, state="Nope")

	def test_vault_filters(self):
		person = self.make("Life Person", full_name="ux1 Holder")
		now = getdate(today())
		gone = self.make("Life Vault Document", title="ux1 expired", doc_type="ID", holder=person.name, expiry_date=add_days(now, -5))
		soon = self.make("Life Vault Document", title="ux1 soon", doc_type="Travel", expiry_date=add_days(now, 30), area=self.areas["Personal"])
		later = self.make("Life Vault Document", title="ux1 later", doc_type="Travel", expiry_date=add_days(now, 300))
		never = self.make("Life Vault Document", title="ux1 never", doc_type="Tax")
		mine = {gone.name, soon.name, later.name, never.name}
		get = lambda **f: mine & self.names(vault.list(space=PRIVATE, **f)["documents"])  # noqa: E731
		self.assertEqual(get(expiry="expired"), {gone.name})
		self.assertEqual(get(expiry="soon"), {soon.name})
		self.assertEqual(get(expiry="later"), {later.name})
		self.assertEqual(get(expiry="none"), {never.name})
		self.assertEqual(get(holder=person.name), {gone.name})
		self.assertEqual(get(holder="none"), {soon.name, later.name, never.name})
		self.assertEqual(get(doc_type="Travel"), {soon.name, later.name})
		self.assertEqual(get(area=self.areas["Personal"]), {soon.name})
		self.assertRaises(frappe.ValidationError, vault.list, space=PRIVATE, expiry="whenever")
		res = vault.list(space=PRIVATE, expiry="soon")
		self.assertEqual(res["total"], len(res["documents"]))
		self.assertEqual(res["soon"], res["total"])
		self.assertEqual(today_api.get(space=PRIVATE)["vault_soon"], res["total"])
		self.assertEqual(vault.list(space=PRIVATE)["expired"], vault.list(space=PRIVATE, expiry="expired")["total"])

	def test_chat_filters(self):
		goal = self.make("Life Goal", title="ux1 chat goal", goal_type="Open", area=self.areas["Tea"])
		a = chats.log(space=PRIVATE, title="ux1 chat open", area=self.areas["Tea"], goal=goal.name, open_items=["Follow up"])["name"]
		b = chats.log(space=PRIVATE, title="ux1 chat old", date=add_days(today(), -20))["name"]
		mine = {a, b}
		get = lambda **f: chats.list(space=PRIVATE, **f)  # noqa: E731
		self.assertEqual(mine & self.names(get(open_items=1)["chats"]), {a})
		self.assertEqual(mine & self.names(get(area=self.areas["Tea"])["chats"]), {a})
		self.assertEqual(mine & self.names(get(area="none")["chats"]), {b})
		self.assertEqual(mine & self.names(get(goal=goal.name)["chats"]), {a})
		self.assertEqual(mine & self.names(get(from_date=add_days(today(), -2))["chats"]), {a})
		self.assertEqual(mine & self.names(get(to_date=add_days(today(), -10))["chats"]), {b})
		res = get()
		self.assertEqual(res["with_open_items"], get(open_items=1)["total"])
		tea = next(x for x in res["by_area"] if x["area"] == self.areas["Tea"])
		self.assertEqual(tea["count"], get(area=self.areas["Tea"])["total"])
		self.assertEqual(sum(x["count"] for x in res["by_area"]), res["total"])
		for g in ("day", "area", "goal"):
			self.assertEqual(get(group_by=g)["total"], res["total"])
		one = chats.get(a)
		self.assertEqual((one["title"], one["open_count"], one["area_name"]), ("ux1 chat open", 1, "Tea"))
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, chats.get, a)

	def test_library_list(self):
		tag = self.make("Life Tag", tag_name="ux1tag")
		goal = self.make("Life Goal", title="ux1 note goal", goal_type="Open", area=self.areas["Tea"])
		a = self.make("Life Note", title="ux1 reference", area=self.areas["Tea"], content_md="a", tags=[{"tag": tag.name}])
		b = self.make("Life Note", title="ux1 goal note", area=self.areas["Tea"], goal=goal.name, content_md="b")
		c = self.make("Life Note", title="ux1 loose", content_md="c")
		mine = {a.name, b.name, c.name}
		get = lambda **f: library.list(space=PRIVATE, page_length=100, **f)  # noqa: E731
		self.assertEqual(mine & self.names(get(area=self.areas["Tea"])["notes"]), {a.name, b.name})
		self.assertEqual(mine & self.names(get(area=self.areas["Tea"], goal="none")["notes"]), {a.name})
		self.assertEqual(mine & self.names(get(goal=goal.name)["notes"]), {b.name})
		self.assertEqual(mine & self.names(get(tag=tag.name)["notes"]), {a.name})
		self.assertEqual(mine & self.names(get(area="none")["notes"]), {c.name})
		self.assertEqual(goals.get(goal.name)["tabs"]["notes"], get(goal=goal.name, collection="all")["total"])

	def test_archive_filters(self):
		t = self.make("Life Task", title="ux1 archived task", area=self.areas["Tea"], status="Done")
		n = self.make("Life Note", title="ux1 archived note", area=self.areas["Money"], content_md="x")
		archive_rules.set_archived("Life Task", t.name, True, "Auto")
		archive_rules.set_archived("Life Note", n.name, True, "Manual")
		mine = {t.name, n.name}
		get = lambda **f: archive.list(space=PRIVATE, page_length=100, **f)  # noqa: E731
		names = lambda res: mine & {r["ref_name"] for r in res["records"]}  # noqa: E731
		self.assertEqual(names(get()), mine)
		self.assertEqual(names(get(doctype="Life Task")), {t.name})
		self.assertEqual(names(get(area=self.areas["Money"])), {n.name})
		self.assertEqual(names(get(reason="Auto")), {t.name})
		self.assertEqual(names(get(reason="Auto", archived_from=today(), archived_to=today())), {t.name})
		self.assertEqual(names(get(reason="Auto", archived_from=add_days(today(), 1))), set())
		res = get(doctype="Life Note", area=self.areas["Money"])
		self.assertEqual(res["total"], len(res["records"]))

	def test_calendar_entry(self):
		d = calendar_api.add_important_date(space=PRIVATE, title="ux1 birthday", day=3, month=4)["name"]
		e = calendar_api.add_event(space=PRIVATE, subject="ux1 event", starts_on=f"{today()} 10:00:00")["name"]
		self.assertEqual(calendar_api.entry("date", d)["title"], "ux1 birthday")
		self.assertEqual(calendar_api.entry("event", e)["title"], "ux1 event")
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, calendar_api.entry, "date", d)
		self.assertRaises(frappe.PermissionError, calendar_api.entry, "event", e)
