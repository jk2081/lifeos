"""UX fixes, set 4, step 0 and 1: the data rules of sources, notes, wiki changes and connections, and the link search."""
import io

import frappe

from lifeos import index, permissions, queries, sources
from lifeos.api import inbox
from lifeos.devtools import attach, pdf_bytes
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


def png(w=1600, h=1200):
	from PIL import Image

	buf = io.BytesIO()
	Image.new("RGB", (w, h), "white").save(buf, format="PNG")
	return buf.getvalue()


class TestSourceFields(LifeTestCase):
	def test_intent_defaults_to_process(self):
		item = self.make("Life Inbox Item", title="ux4 intent", source_type="Message")
		self.assertEqual(item.intent, "Process")

	def test_media_kind_from_source_type_and_files(self):
		self.assertEqual(sources.media_kind("Voice Note"), "Voice")
		self.assertEqual(sources.media_kind("Email Digest"), "Email Digest")
		self.assertEqual(sources.media_kind("Web"), "Article")
		self.assertEqual(sources.media_kind("Upload", ["a.pdf"]), "Document")
		self.assertEqual(sources.media_kind("Upload", ["a.m4a"]), "Voice")
		self.assertEqual(sources.media_kind("Upload", ["a.JPG"]), "Photo")
		self.assertEqual(sources.media_kind("Message"), "Text")
		self.assertEqual(sources.media_kind("Upload", [], "https://example.com/a"), "Article")
		item = self.make("Life Inbox Item", title="ux4 kind", source_type="Upload")
		self.assertEqual(item.media_kind, "Text")
		attach("Life Inbox Item", item.name, "scan.pdf", pdf_bytes())
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item.name, "media_kind"), "Document")
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": item.name}, "media_kind"), "Document")

	def test_email_digest_is_a_source_type(self):
		item = inbox.create_item(title="ux4 digest", source_type="Email Digest", space=PRIVATE, raw_text="## Needs your attention")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item["name"], "media_kind"), "Email Digest")

	def test_photo_gets_a_480_px_thumbnail(self):
		from PIL import Image

		item = self.make("Life Inbox Item", title="ux4 photo", source_type="Upload")
		attach("Life Inbox Item", item.name, "photo.png", png())
		url = frappe.db.get_value("Life Inbox Item", item.name, "thumbnail")
		self.assertTrue(url)
		thumb = frappe.get_doc("File", {"file_url": url, "attached_to_name": item.name})
		self.assertTrue(thumb.is_private)
		self.assertEqual(Image.open(io.BytesIO(thumb.get_content())).size[0], 480)
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": item.name}, "thumbnail"), url)
		# the thumbnail is not an original
		self.assertEqual([f["file_name"] for f in inbox.get(item.name)["files"]], ["photo.png"])

	def test_external_id_is_unique_per_space_and_system(self):
		self.make("Life Inbox Item", title="ux4 mail 1", source_type="Email", source_system="gmail", external_id="m-1")
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make("Life Inbox Item", title="ux4 mail 2", source_type="Email", source_system="gmail", external_id="m-1")
		# another system or another space may use the same ID
		self.make("Life Inbox Item", title="ux4 mail 3", source_type="Email", source_system="outlook", external_id="m-1")
		self.make("Life Inbox Item", space=SHARED, title="ux4 mail 4", source_type="Email", source_system="gmail", external_id="m-1")
		# items with no ID are never in conflict
		self.make("Life Inbox Item", title="ux4 a", source_type="Message")
		self.make("Life Inbox Item", title="ux4 b", source_type="Message")
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Inbox Item", title="ux4 no system", source_type="Email", external_id="m-9")

	def test_chat_log_fields(self):
		log = self.make("Life Chat Log", title="ux4 chat", date=frappe.utils.today(), assistant="Claude Code", source_system="claude",
			external_id="c-1", transcript_md="**You** a question about the zebra crossing\n\n**Claude** an answer")
		self.assertEqual(log.assistant, "Claude Code")
		self.make("Life Chat Log", title="ux4 codex", date=frappe.utils.today(), assistant="Codex")
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make("Life Chat Log", title="ux4 chat again", date=frappe.utils.today(), source_system="claude", external_id="c-1")
		self.assertIn("zebra crossing", frappe.db.get_value("Life Index", {"ref_name": log.name}, "search_text"))
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": log.name}, ["media_kind", "assistant"]), ("Chat", "Claude Code"))

	def test_search_text_is_capped(self):
		long = ("word " * 20000) + "needlefar"
		item = self.make("Life Inbox Item", title="ux4 long", source_type="Message", transcript_md=long)
		text = frappe.db.get_value("Life Index", {"ref_name": item.name}, "search_text")
		self.assertEqual(len(text), index.SEARCH_CAP)
		short = self.make("Life Inbox Item", title="ux4 short", source_type="Message", transcript_md="word " * 9000 + "needlenear")
		self.assertIn("needlenear", frappe.db.get_value("Life Index", {"ref_name": short.name}, "search_text"))


class TestNoteFields(LifeTestCase):
	def test_collection_defaults_to_my_notes(self):
		note = self.make("Life Note", title="ux4 plain")
		self.assertEqual(note.collection, "My notes")
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": note.name}, "collection"), "My notes")

	def test_wiki_page_needs_a_summary_on_one_line(self):
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 wiki no summary", collection="Wiki")
		page = self.make("Life Note", title="ux4 wiki", collection="Wiki", summary="One line\nnot two")
		self.assertEqual(page.summary, "One line not two")

	def test_one_rules_page_per_space_and_only_in_the_wiki(self):
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 rules mine", is_rules=1)
		self.make("Life Note", title="ux4 rules", collection="Wiki", summary="Rules", is_rules=1)
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 rules 2", collection="Wiki", summary="Rules", is_rules=1)
		self.make("Life Note", space=SHARED, title="ux4 rules shared", collection="Wiki", summary="Rules", is_rules=1)

	def test_sources_are_inbox_items_or_chats_of_the_same_space(self):
		item = self.make("Life Inbox Item", title="ux4 src", source_type="Message")
		chat = self.make("Life Chat Log", title="ux4 src chat", date=frappe.utils.today())
		page = self.make("Life Note", title="ux4 cites", collection="Wiki", summary="Cites", sources=[
			{"source_doctype": "Life Inbox Item", "source_name": item.name}, {"source_doctype": "Life Chat Log", "source_name": chat.name},
			{"source_doctype": "Life Inbox Item", "source_name": item.name}])
		self.assertEqual(len(page.sources), 2)
		task = self.make("Life Task", title="ux4 not a source")
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 bad", sources=[{"source_doctype": "Life Task", "source_name": task.name}])
		other = self.make("Life Inbox Item", space=SHARED, title="ux4 other space", source_type="Message")
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 cross", sources=[{"source_doctype": "Life Inbox Item", "source_name": other.name}])

	def test_page_size_limit(self):
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 huge", content_md="x" * 200001)

	def test_wiki_change_has_no_links_and_is_read_only_to_people(self):
		target = self.make("Life Note", title="ux4 link target")
		page = self.make("Life Note", title="ux4 page", collection="Wiki", summary="A page")
		ch = frappe.get_doc({"doctype": "Life Wiki Change", "space": PRIVATE, "note": page.name, "change_type": "Edited",
			"changed_by": OWNER, "changed_on": frappe.utils.now_datetime(), "before_md": "", "after_md": "See [[ux4 link target]]"})
		ch.insert(ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Life Link", {"from_doctype": "Life Wiki Change"}))
		self.assertTrue(frappe.get_doc("Life Wiki Change", ch.name).has_permission("read"))
		self.assertFalse(frappe.get_doc("Life Wiki Change", ch.name).has_permission("write"))
		self.as_user(FAMILY)
		self.assertFalse(frappe.get_list("Life Wiki Change", filters={"name": ch.name}))
		self.assertTrue(target)


class TestConnections(LifeTestCase):
	def test_one_connection_per_space_and_system(self):
		c = self.make("Life Connection", system="Gmail", label="")
		self.assertEqual((c.system, c.label, c.default_intent), ("gmail", "Gmail", "Process"))
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make("Life Connection", system="gmail")
		self.make("Life Connection", space=SHARED, system="gmail")

	def test_agent_reads_but_cannot_change_a_connection(self):
		c = self.make("Life Connection", system="claude")
		self.as_user(AGENT)
		doc = frappe.get_doc("Life Connection", c.name)
		self.assertTrue(doc.has_permission("read"))
		self.assertFalse(doc.has_permission("write"))


class TestVaultSources(LifeTestCase):
	def test_a_source_of_a_vault_document_follows_vault_access(self):
		item = self.make("Life Inbox Item", title="ux4 passport scan", source_type="Upload")
		doc = self.make("Life Vault Document", title="ux4 passport", inbox_item=item.name)
		frappe.db.set_value("Life Inbox Item", item.name, "vault_document", doc.name)
		index.update(frappe.get_doc("Life Inbox Item", item.name))
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		self.as_user(AGENT)
		self.assertFalse(frappe.get_doc("Life Inbox Item", item.name).has_permission("read"))
		self.assertFalse(frappe.get_list("Life Inbox Item", filters={"name": item.name}))
		self.assertFalse(frappe.get_list("Life Index", filters={"ref_name": item.name}))
		self.as_user(OWNER)
		self.assertTrue(frappe.get_list("Life Index", filters={"ref_name": item.name}))
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 1)
		self.as_user(AGENT)
		self.assertTrue(frappe.get_list("Life Inbox Item", filters={"name": item.name}))
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)


class TestLinkQuery(LifeTestCase):
	def test_only_active_areas_of_the_space_unless_asked(self):
		active = self.make("Life Area", area_name="ux4 active area", parent_area=self.life["Career"])
		gone = self.make("Life Area", area_name="ux4 gone area", is_archived=1, parent_area=self.life["Career"])
		shared = self.make("Life Area", space=SHARED, area_name="ux4 shared area", parent_area=self.shared_life["Career"])
		rows = queries.link_query("Life Area", "ux4", "area_name", 0, 20, {"space": PRIVATE})
		names = [r[0] for r in rows]
		self.assertIn(active.name, names)
		self.assertNotIn(gone.name, names)
		self.assertNotIn(shared.name, names)
		rows = queries.link_query("Life Area", "ux4", "area_name", 0, 20, {"space": PRIVATE, "include_archived": 1})
		self.assertIn((gone.name, "ux4 gone area (archived)"), [tuple(r[:2]) for r in rows])
		# with no space, every space of the user, still no archived area
		names = [r[0] for r in queries.link_query("Life Area", "ux4", "area_name", 0, 20, {})]
		self.assertIn(shared.name, names)
		self.assertNotIn(gone.name, names)
		# a member of Shared only never sees Private areas
		self.as_user(FAMILY)
		names = [r[0] for r in queries.link_query("Life Area", "ux4", "area_name", 0, 20, {"space": PRIVATE})]
		self.assertEqual(names, [])

	def test_goals_leave_out_achieved_and_dropped(self):
		# set 6: the project picker became the goal picker; open-ended goals that are finished leave it
		area = self.areas["Tea"]
		live = self.make("Life Goal", title="ux4 live goal", goal_type="Open", area=area)
		done = self.make("Life Goal", title="ux4 done goal", goal_type="Open", area=area, outcome="Achieved")
		names = [r[0] for r in queries.link_query("Life Goal", "ux4", "title", 0, 20, {"space": PRIVATE})]
		self.assertIn(live.name, names)
		self.assertNotIn(done.name, names)
		names = [r[0] for r in queries.link_query("Life Goal", "ux4", "title", 0, 20, {"space": PRIVATE, "goal_outcome": ["Achieved"]})]
		self.assertEqual(names, [done.name])

	def test_search_link_uses_the_query(self):
		from frappe.desk.search import search_link

		gone = self.make("Life Area", area_name="ux4 hidden by search", is_archived=1, parent_area=self.life["Career"])
		got = [r["value"] for r in search_link("Life Area", "ux4 hidden", filters={"space": PRIVATE})]
		self.assertNotIn(gone.name, got)
		self.assertTrue(permissions)
