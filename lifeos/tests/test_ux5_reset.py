"""UX fixes, set 5: Reset batches, one by one, undo and the trash."""
import frappe
from frappe.utils import add_days, today

from lifeos import trash
from lifeos.api import reset, wiki
from lifeos.tests.base import AGENT, OWNER, PRIVATE, LifeTestCase


def batch(key_start):
	return next((b for b in reset.rule_batches(PRIVATE) if b["key"].startswith(key_start)), None)


class TestResetBatches(LifeTestCase):
	def test_each_rule_batch_finds_its_seeded_items_and_undo_reverts(self):
		tea = self.areas["Tea"]
		a = self.make("Life Task", title="ux5 Call Kunal!", area=tea)
		b = self.make("Life Task", title="ux5 call kunal", area=tea)
		done = self.make("Life Project", title="ux5 done project", area=tea, status="Active")
		orphan = self.make("Life Task", title="ux5 orphan", area=tea, project=done.name)
		frappe.db.set_value("Life Project", done.name, "status", "Done")
		old = self.make("Life Task", title="ux5 ancient", area=self.areas["Money"])
		frappe.db.set_value("Life Task", old.name, "last_touched_on", add_days(today(), -400))
		page = wiki.create_page(space=PRIVATE, title="ux5 Blend blueprint", content_md="Wiki text.", summary="s", area=tea) if False else None
		frappe.flags.lifeos_wiki_summary_optional = True
		w = self.make("Life Note", title="ux5 Blend blueprint", collection="Wiki", summary="Blend", content_md="Wiki text.", area=tea)
		n = self.make("Life Note", title="ux5 blend blueprint", content_md="My text.", area=tea)

		dup = batch("duplicates")
		self.assertEqual([i["name"] for i in dup["items"]], [b.name])
		self.assertIn(orphan.name, [i["name"] for i in batch("closed_project")["items"]])
		old_b = batch(f"old:{self.areas['Money']}")
		self.assertEqual([i["name"] for i in old_b["items"]], [old.name])
		self.assertEqual(old_b["action"], "someday")
		twins = batch("wiki_twins")
		self.assertEqual([i["name"] for i in twins["items"]], [n.name])

		# a batch action changes exactly the listed items; Undo reverts them
		res = reset.apply_batch("someday", [{"doctype": "Life Task", "name": old.name}], space=PRIVATE)
		self.assertEqual(res["done"], 1)
		self.assertEqual(frappe.db.get_value("Life Task", old.name, "status"), "Someday")
		self.assertEqual(frappe.db.get_value("Life Task", a.name, "status"), "Open")
		reset.undo(res["undo"])
		self.assertEqual(frappe.db.get_value("Life Task", old.name, "status"), "Open")

		res = reset.apply_batch("delete", dup["items"], space=PRIVATE)
		self.assertFalse(frappe.db.exists("Life Task", b.name))
		self.assertTrue(frappe.db.exists("Life Task", a.name))
		reset.undo(res["undo"])
		self.assertTrue(frappe.db.exists("Life Task", b.name))

		res = reset.apply_batch("drop", [{"doctype": "Life Task", "name": orphan.name}], space=PRIVATE)
		self.assertEqual(frappe.db.get_value("Life Task", orphan.name, "status"), "Dropped")
		reset.undo(res["undo"])
		self.assertEqual(frappe.db.get_value("Life Task", orphan.name, "status"), "Open")

		res = reset.apply_batch("merge", twins["items"], space=PRIVATE)
		self.assertIn("My text.", frappe.db.get_value("Life Note", w.name, "content_md"))
		self.assertEqual(frappe.db.get_value("Life Note", n.name, "is_archived"), 1)
		self.assertTrue(frappe.db.exists("Life Wiki Change", {"note": w.name, "change_type": "Edited"}))
		reset.undo(res["undo"])
		self.assertEqual(frappe.db.get_value("Life Note", w.name, "content_md"), "Wiki text.")
		self.assertEqual(frappe.db.get_value("Life Note", n.name, "is_archived"), 0)
		frappe.flags.lifeos_wiki_summary_optional = False

	def test_old_inbox_batch_accepts_notes_only(self):
		from lifeos.api import inbox

		item = inbox.create_item(title="ux5 old item", source_type="Message", space=PRIVATE, raw_text="x")
		frappe.db.sql("update `tabLife Inbox Item` set received_on=%s where name=%s", (add_days(today(), -4000), item["name"]))
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		inbox.submit_result(item["name"], summary_md="s", proposals=[
			{"kind": "Note", "payload": {"title": "ux5 batch note", "area": self.areas["Tea"], "content_md": "n"}},
			{"kind": "Task", "payload": {"title": "ux5 batch task", "area": self.areas["Tea"]}}])
		self.as_user(OWNER)
		b = batch("old_inbox")
		self.assertIn(item["name"], [i["name"] for i in b["items"]])
		res = reset.apply_batch("accept_notes", [{"doctype": "Life Inbox Item", "name": item["name"]}], space=PRIVATE)
		props = {p.kind: p.status for p in frappe.get_all("Life Proposal", filters={"inbox_item": item["name"]}, fields=["kind", "status"])}
		self.assertEqual(props, {"Note": "Accepted", "Task": "Pending"})
		reset.undo(res["undo"])
		props = {p.kind: p.status for p in frappe.get_all("Life Proposal", filters={"inbox_item": item["name"]}, fields=["kind", "status"])}
		self.assertEqual(props, {"Note": "Pending", "Task": "Pending"})
		self.assertFalse(frappe.db.exists("Life Note", {"title": "ux5 batch note", "space": PRIVATE}))


class TestOneByOne(LifeTestCase):
	def test_oldest_first_and_each_decision(self):
		tea = self.areas["Tea"]
		t = [self.make("Life Task", title=f"ux5 obo {i}", area=tea) for i in range(5)]
		for i, x in enumerate(t):
			frappe.db.set_value("Life Task", x.name, "last_touched_on", add_days(today(), -3000 - i))
		first = reset.next_item(space=PRIVATE)["item"]
		self.assertEqual(first["name"], t[4].name)
		self.assertGreaterEqual(first["days"], 3004)
		self.assertEqual(reset.next_item(space=PRIVATE, skip=[t[4].name])["item"]["name"], t[3].name)
		self.assertEqual(reset.next_item(space=PRIVATE, only=[t[1].name, t[2].name])["item"]["name"], t[2].name)
		reset.decide("Life Task", t[0].name, "do", date=add_days(today(), 3))
		self.assertEqual(str(frappe.db.get_value("Life Task", t[0].name, "due_date")), str(add_days(today(), 3)))
		with self.assertRaises(frappe.ValidationError):
			reset.decide("Life Task", t[1].name, "waiting")
		reset.decide("Life Task", t[1].name, "waiting", waiting_on="Vivek")
		self.assertEqual(frappe.db.get_value("Life Task", t[1].name, "status"), "Waiting")
		reset.decide("Life Task", t[2].name, "someday")
		self.assertEqual(frappe.db.get_value("Life Task", t[2].name, "status"), "Someday")
		r = reset.decide("Life Task", t[3].name, "archive")
		self.assertEqual(frappe.db.get_value("Life Task", t[3].name, "is_archived"), 1)
		reset.undo(r["undo"])
		self.assertEqual(frappe.db.get_value("Life Task", t[3].name, "is_archived"), 0)
		r = reset.decide("Life Task", t[4].name, "delete")
		self.assertFalse(frappe.db.exists("Life Task", t[4].name))
		reset.undo(r["undo"])
		self.assertTrue(frappe.db.exists("Life Task", t[4].name))

	def test_agent_cannot_use_reset(self):
		t = self.make("Life Task", title="ux5 agent reset", area=self.areas["Tea"])
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			reset.decide("Life Task", t.name, "delete")
		with self.assertRaises(frappe.PermissionError):
			reset.apply_batch("delete", [{"doctype": "Life Task", "name": t.name}], space=PRIVATE)
