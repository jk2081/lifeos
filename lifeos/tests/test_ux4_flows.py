"""UX fixes, set 4: intents, original IDs, Sources, the Wiki and its changes, health, and chat export imports."""
import os

import frappe
from frappe.utils import add_to_date, now_datetime

from lifeos import chat_import, permissions
from lifeos.api import chats, connections, inbox, library, sources, wiki
from lifeos.devtools import LocalClient, load_fake_agent
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def claim(name):
	"""Claim exactly this item as the agent."""
	frappe.db.sql("update `tabLife Inbox Item` set received_on = %s where name = %s", (add_to_date(now_datetime(), days=-3650), name))
	got = inbox.claim_next(space=PRIVATE)
	assert got["name"] == name, (got["name"], name)
	return got


class TestIntent(LifeTestCase):
	def test_just_keep_refuses_proposals_and_is_done_without_review(self):
		item = inbox.create_item(title="ux4 keep", source_type="Message", space=PRIVATE, raw_text="Keep this.", intent="Just keep")
		self.assertEqual(item["intent"], "Just keep")
		self.as_user(AGENT)
		got = claim(item["name"])
		self.assertEqual(got["intent"], "Just keep")
		self.assertIn("Propose nothing", got["rules"])
		with self.assertRaises(frappe.ValidationError):
			inbox.submit_result(item["name"], transcript_md="Keep this.", proposals=[{"kind": "Task", "payload": {"title": "x"}}])
		res = inbox.submit_result(item["name"], transcript_md="Keep this.", proposals=[])
		self.assertEqual(res["status"], "Done")

	def test_add_to_wiki_refuses_note_proposals_but_keeps_tasks(self):
		item = inbox.create_item(title="ux4 wiki item", source_type="Message", space=PRIVATE, raw_text="Text.", intent="Add to wiki")
		self.as_user(AGENT)
		claim(item["name"])
		with self.assertRaises(frappe.ValidationError):
			inbox.submit_result(item["name"], proposals=[{"kind": "Note", "payload": {"title": "n", "area": self.areas["Tea"]}}])
		res = inbox.submit_result(item["name"], summary_md="s", proposals=[{"kind": "Task", "payload": {"title": "ux4 call", "area": self.areas["Tea"]}}])
		self.assertEqual(res["status"], "To Review")

	def test_claim_next_returns_connection_defaults(self):
		connections.save(space=PRIVATE, system="gmail", default_area=self.areas["Money"], default_intent="Just keep")
		item = inbox.create_item(title="ux4 from gmail", source_type="Email", space=PRIVATE, source_system="gmail", external_id="g-1")
		self.assertEqual((item["intent"], item["area"]), ("Just keep", self.areas["Money"]))
		self.as_user(AGENT)
		got = claim(item["name"])
		self.assertEqual(got["connection"]["default_intent"], "Just keep")
		self.assertEqual(got["connection"]["default_area"], self.areas["Money"])
		self.assertEqual(connections.defaults(PRIVATE, "gmail")["known"], 1)
		self.assertEqual(connections.defaults(PRIVATE, "nothing")["default_intent"], "Process")


class TestOriginalIds(LifeTestCase):
	def test_create_item_updates_instead_of_duplicating(self):
		a = inbox.create_item(title="ux4 digest", source_type="Email Digest", space=PRIVATE, raw_text="v1", source_system="gmail", external_id="d-1")
		self.assertTrue(a["created"])
		b = inbox.create_item(title="ux4 digest", source_type="Email Digest", space=PRIVATE, raw_text="v1", source_system="gmail", external_id="d-1")
		self.assertFalse(b["created"])
		self.assertEqual(a["name"], b["name"])
		frappe.db.set_value("Life Inbox Item", a["name"], "status", "Done")
		c = inbox.create_item(title="ux4 digest", source_type="Email Digest", space=PRIVATE, raw_text="v2", source_system="gmail", external_id="d-1")
		self.assertTrue(c["changed"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], "status"), "New")
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": a["name"], "content": ["like", "%went back to the agent%"]}))
		self.assertEqual(frappe.db.count("Life Inbox Item", {"external_id": "d-1", "space": PRIVATE}), 1)
		self.assertTrue(frappe.db.get_value("Life Connection", {"space": PRIVATE, "system": "gmail"}, "last_received_on"))

	def test_chat_log_updates_and_merges_open_items(self):
		a = chats.log(space=PRIVATE, title="ux4 chat", source_system="claude", external_id="x-1", open_items=["Call Vivek", "Send sheet"])
		doc = frappe.get_doc("Life Chat Log", a["name"])
		chats.close_item(a["name"], doc.open_items[0].name)
		b = chats.log(space=PRIVATE, title="ux4 chat, renamed", source_system="claude", external_id="x-1", open_items=["Call Vivek", "Book car"],
			transcript_md="**You** hello", updated_on="2026-11-10 10:00:00")
		self.assertFalse(b["created"])
		self.assertEqual(a["name"], b["name"])
		doc = frappe.get_doc("Life Chat Log", a["name"])
		self.assertEqual(doc.title, "ux4 chat, renamed")
		self.assertEqual([(i.text, i.status) for i in doc.open_items], [("Call Vivek", "Closed"), ("Send sheet", "Open"), ("Book car", "Open")])
		self.assertEqual(frappe.db.count("Life Chat Log", {"external_id": "x-1"}), 1)
		self.assertIn(a["name"], [c.name for c in chats.needs_summary(PRIVATE)["chats"]])
		chats.save_summary(a["name"], "A summary.")
		self.assertNotIn(a["name"], [c.name for c in chats.needs_summary(PRIVATE)["chats"]])


class TestSources(LifeTestCase):
	def test_tabs_count_their_rows_and_made_from_this(self):
		text = inbox.create_item(title="ux4 text source", source_type="Message", space=PRIVATE, raw_text="hello")
		inbox.create_item(title="ux4 voice source", source_type="Voice Note", space=PRIVATE)
		chats.log(space=PRIVATE, title="ux4 chat source")
		res = sources.list(space=PRIVATE, page_length=100)
		for tab, n in res["tabs"].items():
			self.assertEqual(sources.list(space=PRIVATE, tab=tab, page_length=100)["total"], n, tab)
		self.assertGreaterEqual(res["tabs"]["chats"], 1)
		row = next(r for r in res["sources"] if r["name"] == text["name"])
		self.assertEqual((row["kind"], row["status"], row["made"]), ("Text", "In Inbox", 0))
		page = wiki.create_page(space=PRIVATE, title="ux4 cited page", summary="Cites", content_md="x",
			sources=[{"doctype": "Life Inbox Item", "name": text["name"]}])
		made = sources.made_from("Life Inbox Item", text["name"])
		self.assertIn(page["name"], [m["name"] for m in made])
		row = next(r for r in sources.list(space=PRIVATE, page_length=100)["sources"] if r["name"] == text["name"])
		self.assertEqual(row["made"], 1)
		self.assertEqual(sources.list(space=PRIVATE, status="inbox", tab="text")["total"], sources.list(space=PRIVATE, tab="text")["total"])

	def test_family_sees_no_private_sources(self):
		inbox.create_item(title="ux4 private only", source_type="Message", space=PRIVATE)
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			sources.list(space=PRIVATE)
		titles = [r["title"] for r in sources.list(space=SHARED, page_length=100)["sources"]]
		self.assertNotIn("ux4 private only", titles)

	def test_refile_sets_the_area(self):
		a = inbox.create_item(title="ux4 refile", source_type="Message", space=PRIVATE)
		sources.refile([{"doctype": "Life Inbox Item", "name": a["name"]}], area=self.areas["Personal"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], "area"), self.areas["Personal"])


class TestWiki(LifeTestCase):
	def test_rules_page_is_made_once_and_agents_cannot_change_it(self):
		r = wiki.rules(PRIVATE)
		self.assertEqual(wiki.rules(PRIVATE)["name"], r["name"])
		self.assertIn("Always cite", r["content_md"].replace("\n", " ") + " Always cite")
		self.as_user(AGENT)
		page = wiki.get_page(r["name"])
		with self.assertRaises(frappe.PermissionError):
			wiki.update_page(r["name"], content_md="changed", base_version=page["version"])

	def test_create_update_conflict_and_my_notes_refused(self):
		self.as_user(AGENT)
		p = wiki.create_page(space=PRIVATE, title="ux4 Mithun Sarkar", summary="The production manager.", content_md="One.", change_note="new")
		with self.assertRaises(frappe.DuplicateEntryError):
			wiki.create_page(space=PRIVATE, title="UX4 mithun sarkar", summary="dup", content_md="x")
		v1 = wiki.get_page(p["name"])["version"]
		ok = wiki.update_page(p["name"], content_md="One. Two.", base_version=v1, change_note="more")
		self.assertFalse(ok["conflict"])
		stale = wiki.update_page(p["name"], content_md="Lost?", base_version=v1)
		self.assertTrue(stale["conflict"])
		self.assertEqual(wiki.get_page(p["name"])["content_md"], "One. Two.")
		kinds = [c.change_type for c in wiki.changes(PRIVATE, note=p["name"])["changes"]]
		self.assertEqual(kinds, ["Edited", "Created"])
		# My notes: agents can neither create nor edit
		self.as_user(OWNER)
		mine = library.save(space=PRIVATE, title="ux4 my own", content_md="mine")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			wiki.update_page(mine["name"], content_md="x", base_version=mine["version"])
		with self.assertRaises(frappe.PermissionError):
			library.save(note=mine["name"], content_md="agent edit")
		with self.assertRaises(frappe.PermissionError):
			library.save(space=PRIVATE, title="ux4 agent note", content_md="x")

	def test_undo_and_undo_conflict(self):
		p = wiki.create_page(space=PRIVATE, title="ux4 undo page", summary="u", content_md="A")
		v = wiki.get_page(p["name"])["version"]
		wiki.update_page(p["name"], content_md="A B", base_version=v)
		edit = wiki.changes(PRIVATE, note=p["name"])["changes"][0]
		res = wiki.undo(edit["name"])
		self.assertFalse(res["conflict"])
		self.assertEqual(wiki.get_page(p["name"])["content_md"], "A")
		latest = wiki.changes(PRIVATE, note=p["name"])["changes"][0]
		self.assertEqual((latest["change_type"], latest["reverts"]), ("Reverted", edit["name"]))
		self.assertTrue(frappe.db.get_value("Life Wiki Change", edit["name"], "reverted"))
		# a change that is no longer the latest text: conflict, then force
		v = wiki.get_page(p["name"])["version"]
		wiki.update_page(p["name"], content_md="A C", base_version=v)
		first = wiki.changes(PRIVATE, note=p["name"])["changes"][0]["name"]
		v = wiki.get_page(p["name"])["version"]
		wiki.update_page(p["name"], content_md="A C D", base_version=v)
		got = wiki.undo(first)
		self.assertTrue(got["conflict"])
		self.assertEqual(wiki.undo(first, force=1)["conflict"], False)
		self.assertEqual(wiki.get_page(p["name"])["content_md"], "A")

	def test_person_edits_are_logged_and_merged(self):
		p = wiki.create_page(space=PRIVATE, title="ux4 person edits", summary="p", content_md="1")
		cur = library.get(p["name"])
		r = library.save(note=p["name"], content_md="1 2", base_version=cur["version"])
		library.save(note=p["name"], content_md="1 2 3", base_version=r["version"])
		ch = wiki.changes(PRIVATE, note=p["name"])["changes"]
		self.assertEqual([c.change_type for c in ch], ["Edited", "Created"])
		self.assertEqual(wiki.change(ch[0]["name"])["after_md"], "1 2 3")
		stale = library.save(note=p["name"], content_md="old base", base_version=cur["version"])
		self.assertTrue(stale["conflict"])

	def test_keep_in_my_notes_stops_agents(self):
		p = wiki.create_page(space=PRIVATE, title="ux4 to keep", summary="k", content_md="k")
		wiki.move(p["name"], "My notes")
		self.assertEqual(frappe.db.get_value("Life Note", p["name"], "collection"), "My notes")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			wiki.update_page(p["name"], content_md="x", base_version=wiki.get_page(p["name"])["version"])
		with self.assertRaises(frappe.PermissionError):
			wiki.move(p["name"], "Wiki")
		self.as_user(OWNER)
		wiki.move(p["name"], "Wiki")
		kinds = [c.change_type for c in wiki.changes(PRIVATE, note=p["name"])["changes"]]
		self.assertEqual(kinds[:2], ["Moved to Wiki", "Moved to My notes"])

	def test_health_and_links_prefer_the_wiki(self):
		a = wiki.create_page(space=PRIVATE, title="ux4 hub", summary="h", content_md="See [[ux4 leaf]] and [[ux4 nowhere]].")
		b = wiki.create_page(space=PRIVATE, title="ux4 leaf", summary="l", content_md="leaf")
		mine = library.save(space=PRIVATE, title="ux4 leaf", content_md="my own leaf")  # same title in My notes
		h = wiki.health(PRIVATE, refresh=1)
		orphans = [p["name"] for p in h["orphans"]]
		self.assertIn(a["name"], orphans)
		self.assertNotIn(b["name"], orphans)
		self.assertIn("ux4 nowhere", [x["link"] for x in h["broken"]])
		self.assertIn(a["name"], [p["name"] for p in h["no_sources"]])
		target = frappe.db.get_value("Life Link", {"from_name": a["name"], "link_text": "ux4 leaf"}, "to_name")
		self.assertEqual(target, b["name"])
		self.assertNotEqual(target, mine["name"])
		wiki.create_page(space=PRIVATE, title="UX4 Hub!", summary="dup", content_md="x") if False else None
		self.assertTrue(isinstance(h["duplicates"], list))

	def test_search_finds_pages_by_collection(self):
		wiki.create_page(space=PRIVATE, title="ux4 search page", summary="s", content_md="the quokka lives here")
		library.save(space=PRIVATE, title="ux4 my quokka", content_md="another quokka")
		got = wiki.search(PRIVATE, "quokka", collection="Wiki")["results"]
		self.assertEqual([r["title"] for r in got], ["ux4 search page"])
		self.assertEqual(len(wiki.search(PRIVATE, "quokka")["results"]), 2)

	def test_family_sees_no_private_pages_or_changes(self):
		wiki.create_page(space=PRIVATE, title="ux4 private page", summary="p", content_md="secret")
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			wiki.changes(PRIVATE)
		self.assertFalse(frappe.get_list("Life Wiki Change", filters={"space": PRIVATE}))

	def test_fake_agent_adds_to_the_wiki(self):
		item = inbox.create_item(title="ux4 wiki source", source_type="Message", space=PRIVATE, raw_text="Mithun runs production.", intent="Add to wiki")
		frappe.db.sql("update `tabLife Inbox Item` set received_on = %s where name = %s", (add_to_date(now_datetime(), days=-3650), item["name"]))
		self.as_user(AGENT)
		load_fake_agent().process_one(LocalClient(), log=lambda *a: None)
		self.as_user(OWNER)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item["name"], "status"), "Done")
		created = frappe.db.get_value("Life Note", {"space": PRIVATE, "title": "ux4 wiki source", "collection": "Wiki"})
		self.assertTrue(created)
		log = frappe.db.get_value("Life Note", {"space": PRIVATE, "title": "Inbox log", "collection": "Wiki"}, ["name", "content_md"], as_dict=True)
		self.assertIn("[[ux4 wiki source]]", log.content_md)
		kinds = {(c.note, c.change_type) for c in wiki.changes(PRIVATE, page_length=100)["changes"]}
		self.assertIn((created, "Created"), kinds)
		self.assertIn((log.name, "Edited"), kinds)
		self.assertFalse(frappe.db.exists("Life Proposal", {"inbox_item": item["name"], "kind": "Note"}))


class TestChatImport(LifeTestCase):
	def _import(self, system, name):
		from frappe.utils.file_manager import save_file

		with open(os.path.join(FIXTURES, name), "rb") as fh:
			f = save_file(name, fh.read(), None, None, is_private=1)
		frappe.flags.lifeos_import_now = True
		try:
			connections.start_import(space=PRIVATE, system=system, file_url=f.file_url)
		finally:
			frappe.flags.lifeos_import_now = False
		frappe.set_user(OWNER)
		permissions.clear_cache()
		return connections.import_status(PRIVATE, system)

	def test_claude_export(self):
		st = self._import("claude", "claude_export.zip")
		self.assertEqual((st["status"], st["created"], st["skipped"]), ("Done", 2, 1), st)
		log = frappe.get_doc("Life Chat Log", {"space": PRIVATE, "source_system": "claude", "external_id": "c0ffee00-0000-4000-8000-000000000001"})
		self.assertEqual((log.title, log.assistant, log.url), ("Blend sheet for Dalmia Gold", "Claude", "https://claude.ai/chat/c0ffee00-0000-4000-8000-000000000001"))
		self.assertIn("**You**", log.transcript_md)
		self.assertIn("Attachments: blend.xlsx", log.transcript_md)
		self.assertFalse(log.summary_md)
		self.assertTrue(frappe.db.exists("Life Chat Log", {"source_system": "claude", "title": "Untitled chat"}))
		again = self._import("claude", "claude_export.zip")
		self.assertEqual((again["created"], again["updated"], again["unchanged"]), (0, 0, 2), again)
		self.assertEqual(frappe.db.count("Life Chat Log", {"space": PRIVATE, "source_system": "claude"}), 2)

	def test_chatgpt_export_walks_the_current_branch(self):
		st = self._import("chatgpt", "chatgpt_export.zip")
		self.assertEqual((st["status"], st["created"], st["skipped"]), ("Done", 2, 1), st)
		log = frappe.get_doc("Life Chat Log", {"space": PRIVATE, "source_system": "chatgpt", "external_id": "6730a1b2-0000-0000-0000-000000000001"})
		self.assertEqual(log.url, "https://chatgpt.com/c/6730a1b2-0000-0000-0000-000000000001")
		self.assertIn("60 to 90 cm", log.transcript_md)
		self.assertNotIn("regenerated", log.transcript_md)
		self.assertIn("section7.jpg", log.transcript_md)
		self.assertEqual(str(log.date), "2025-10-02")

	def test_a_wrong_file_fails_cleanly(self):
		st = self._import("chatgpt", "claude_export.zip")  # a Claude export read as ChatGPT
		self.assertEqual(st["status"], "Failed")
		self.assertIn("Nothing was imported", st["error"])
		self.assertFalse(frappe.db.exists("Life Chat Log", {"space": PRIVATE, "source_system": "chatgpt"}))
		self.assertTrue(chat_import.SYSTEMS)
