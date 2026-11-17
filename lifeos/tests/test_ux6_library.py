"""UX fixes, set 6: Library > Captures and All, and the sensitive mark (the Vault rules on captures and notes)."""
import frappe
from frappe.utils import add_days, today

from lifeos import permissions
from lifeos.ai.tools import Context, t_get_record
from lifeos.api import inbox, library, search, sources, wiki
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


def set_switch(space, field, on):
	frappe.set_user("Administrator")
	frappe.db.set_value("Life Space", space, field, 1 if on else 0)
	frappe.local.lifeos_vault_open = None
	permissions.clear_cache()


class TestSensitive(LifeTestCase):
	def tearDown(self):
		set_switch(SHARED, "agents_can_read_vault", 0)
		set_switch(SHARED, "ask_can_read_vault", 0)
		super().tearDown()

	def test_agent_cannot_open_a_sensitive_note_while_the_switch_is_off(self):
		note = self.make("Life Note", space=SHARED, title="ux6 secret note", content_md="kumquatsecret", area=self.shared_areas["Family"])
		library.set_sensitive("Life Note", note.name, 1)
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, permissions.get_doc_checked, "Life Note", note.name)
		self.assertNotIn(note.name, [r.name for r in library.list(space=SHARED, collection="all", page_length=100)["notes"]])
		self.assertFalse([r for r in search.query(text="kumquatsecret", space=SHARED)["results"] if r.ref_name == note.name])
		set_switch(SHARED, "agents_can_read_vault", 1)
		self.as_user(AGENT)
		self.assertEqual(permissions.get_doc_checked("Life Note", note.name).name, note.name)

	def test_agent_does_not_claim_or_list_a_sensitive_inbox_item(self):
		item = self.make("Life Inbox Item", space=SHARED, title="ux6 sensitive capture", status="To Review", is_sensitive=1)
		self.as_user(AGENT)
		self.assertNotIn(item.name, [r.name for r in inbox.list(space=SHARED, page_length=100)["items"]])
		self.assertNotIn(item.name, [r["name"] for r in sources.list(space=SHARED, page_length=100)["sources"]])
		self.assertFalse(frappe.get_list("Life Inbox Item", filters={"name": item.name}))

	def test_only_the_owner_can_unmark(self):
		note = self.make("Life Note", space=SHARED, title="ux6 family note", content_md="x")
		self.as_user(FAMILY)
		library.set_sensitive("Life Note", note.name, 1)  # anyone who may edit can mark
		self.assertRaises(frappe.PermissionError, library.set_sensitive, "Life Note", note.name, 0)
		self.as_user(OWNER)
		self.assertEqual(library.set_sensitive("Life Note", note.name, 0)["is_sensitive"], 0)

	def test_agents_cannot_mark(self):
		note = self.make("Life Note", space=PRIVATE, title="ux6 agent mark", content_md="x")
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, library.set_sensitive, "Life Note", note.name, 1)

	def test_ask_reads_a_sensitive_item_only_with_its_switch(self):
		note = self.make("Life Note", space=SHARED, title="ux6 ask note", content_md="private words", is_sensitive=1)
		ctx = Context(SHARED, {"kind": "space"}, user=OWNER)
		self.assertIn("error", t_get_record(ctx, doctype="Life Note", name=note.name))
		set_switch(SHARED, "ask_can_read_vault", 1)
		self.as_user(OWNER)
		ctx = Context(SHARED, {"kind": "space"}, user=OWNER)
		self.assertNotIn("error", t_get_record(ctx, doctype="Life Note", name=note.name))

	def test_a_sensitive_wiki_page_is_hidden_from_the_agent(self):
		frappe.flags.lifeos_wiki_api = True
		try:
			page = self.make("Life Note", space=SHARED, title="ux6 wiki secret", collection="Wiki", summary="s", content_md="x")
		finally:
			frappe.flags.lifeos_wiki_api = False
		library.set_sensitive("Life Note", page.name, 1)
		self.as_user(AGENT)
		self.assertNotIn(page.name, [r.name for r in wiki.index(space=SHARED, page_length=500)["pages"]])


class TestCaptures(LifeTestCase):
	def test_vault_documents_are_sensitive_documents_with_their_expiry(self):
		person = self.make("Life Person", full_name="ux6 Holder")
		doc = self.make("Life Vault Document", title="ux6 passport", doc_type="Travel", holder=person.name, number_last4="1234",
			issue_date=add_days(today(), -300), expiry_date=add_days(today(), 20), remind_days_before=60)
		res = sources.list(space=PRIVATE, tab="documents", page_length=100)
		row = next(r for r in res["sources"] if r["name"] == doc.name)
		self.assertEqual((row["kind"], row["sensitive"], row["holder_name"], row["number_last4"]), ("Document", 1, "ux6 Holder", "1234"))
		self.assertEqual(row["expiry"]["state"], "expiring")
		self.assertEqual(row["ref"], "vault:" + doc.name)
		self.assertIn(doc.name, [r["name"] for r in sources.list(space=PRIVATE, sensitive=1, page_length=100)["sources"]])

	def test_all_holds_notes_and_written_by(self):
		mine = self.make("Life Note", title="ux6 my note", content_md="x")
		frappe.flags.lifeos_wiki_api = True
		try:
			kept = self.make("Life Note", title="ux6 kept note", collection="Wiki", summary="s", content_md="x")
		finally:
			frappe.flags.lifeos_wiki_api = False
		everything = [r["name"] for r in sources.list(space=PRIVATE, scope="all", tab="notes", page_length=100)["sources"]]
		self.assertIn(mine.name, everything)
		self.assertIn(kept.name, everything)
		by_assistant = sources.list(space=PRIVATE, scope="all", tab="notes", by="assistant", page_length=100)["sources"]
		self.assertEqual({r["name"] for r in by_assistant} & {mine.name, kept.name}, {kept.name})
		self.assertTrue(next(r for r in by_assistant if r["name"] == kept.name)["by_assistant"])
		self.assertNotIn("notes", sources.list(space=PRIVATE, page_length=1)["tabs"])
		self.assertEqual({r.name for r in library.list(space=PRIVATE, collection="all", page_length=200)["notes"]} & {mine.name, kept.name},
			{mine.name, kept.name})


class TestSensitiveEverywhere(LifeTestCase):
	"""The review of set 6: every agent read leaves sensitive items out while the space's switch is off."""

	def test_agent_reads_leave_sensitive_items_out(self):
		from frappe.utils import today as day

		from lifeos.api import chats, goals, links
		from lifeos.api import today as today_api

		goal = self.make("Life Goal", space=SHARED, title="ux6 review goal", goal_type="Open")
		parent = self.make("Life Note", space=SHARED, title="ux6 parent", content_md="x", goal=goal.name)
		child = self.make("Life Note", space=SHARED, title="ux6 secret child", content_md="x", parent_note=parent.name, goal=goal.name, is_sensitive=1)
		item = self.make("Life Inbox Item", space=SHARED, title="ux6 secret item", status="To Review", is_sensitive=1)
		chat = self.make("Life Chat Log", space=SHARED, title="ux6 secret chat", date=day(), is_sensitive=1)
		self.as_user(AGENT)
		self.assertNotIn(child.name, [c.name for c in library.get(parent.name)["children"]])
		self.assertNotIn(child.name, [r["name"] for r in links.backlinks("Life Goal", goal.name)])
		self.assertNotIn(item.name, [r.name for r in today_api.get(space=SHARED)["to_review"]["items"]])
		self.assertNotIn(chat.name, [c["name"] for g in chats.report(space=SHARED)["groups"] for c in g["chats"]])
		self.assertRaises(frappe.PermissionError, library.get, child.name)
		self.assertIsNotNone(goals)

	def test_agent_cannot_mark_through_a_plain_save(self):
		note = self.make("Life Note", space=SHARED, title="ux6 agent save", content_md="x")
		self.as_user(AGENT)
		doc = frappe.get_doc("Life Note", note.name)
		doc.is_sensitive = 1
		self.assertRaises(frappe.PermissionError, doc.save)
