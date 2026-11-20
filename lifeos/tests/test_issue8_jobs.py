"""Issue 8: one call for an agent to file a piece of work (lifeos.api.jobs.file_job)."""
import base64
from unittest.mock import patch

import frappe

from lifeos import files, permissions
from lifeos.api import inbox, jobs, review
from lifeos.tests.base import AGENT, PRIVATE, SHARED, LifeTestCase

DECK = b"issue 8 standard deck"
BRAND = b"issue 8 brand guidelines"


def b64(data):
	return base64.b64encode(data).decode()


def call(job_id="i8-mehi-pitch", **kw):
	args = {
		"space": PRIVATE, "title": "i8 Mehi Motors: owner-first sales deck", "instruction": "Make a deck for Mehi Motors from my standard deck.",
		"inputs": [{"name": "BTW standard deck.txt", "file": b64(DECK), "reusable_as": "i8-btw-standard-deck"},
			{"name": "BTW brand guidelines.txt", "file": b64(BRAND), "reusable_as": "i8-btw-brand"}],
		"outputs": [{"name": "Mehi Motors deck.txt", "file": b64(b"i8 the deck")}, {"name": "Mehi Motors deck.html", "file": b64(b"<p>i8 the deck</p>")}],
		"transcript_md": "Slide 1: why Mehi Motors", "summary_md": "A deck for Mehi Motors, from [[BTW standard deck]].",
		"proposals": [{"kind": "Note", "preview": "i8 the record of the work", "payload": {"title": "i8 Mehi Motors deck", "content_md": "The deck."}, "confidence": 0.9},
			{"kind": "Task", "preview": "i8 score the questionnaire", "payload": {"title": "i8 Score the questionnaire"}, "confidence": 0.7}],
		"wiki": [{"title": "i8 Mehi Motors Pvt Ltd", "summary": "Honda dealership", "content_md": "A Honda two-wheeler dealership."}],
		"chat": {"title": "i8 Mehi Motors deck with Hermes", "summary_md": "Asked for a deck.", "open_items": ["Check Vahan"], "source_system": "hermes-telegram"},
		"source_system": "hermes",
	}
	args.update(kw)
	return jobs.file_job(job_id=job_id, **args)


def counts():
	return {dt: frappe.db.count(dt) for dt in ("Life Inbox Item", "Life Proposal", "Life Note", "Life Chat Log", "File", "Life Wiki Change")}


def stored(content):
	return {r.file_url for r in frappe.get_all("File", filters={"life_sha256": files.sha256(content)}, fields=["file_url"])}


class TestFileJob(LifeTestCase):
	def setUp(self):
		super().setUp()
		self.as_user(AGENT)

	def test_1_one_call_files_one_item_with_its_inputs_outputs_proposals_wiki_and_chat(self):
		before = counts()
		out = call()
		self.assertTrue(out["created"])
		self.assertEqual(frappe.db.count("Life Inbox Item", {"job_id": "i8-mehi-pitch"}), 1)
		got = inbox.get(out["item"])
		self.assertEqual(got["status"], "To Review")
		self.assertEqual(got["intent"], "Process")
		self.assertEqual(got["instruction"], "Make a deck for Mehi Motors from my standard deck.")
		self.assertEqual(sorted(f["file_name"] for f in got["files"]), ["Mehi Motors deck.html", "Mehi Motors deck.txt"])
		# two input assets, each its own kept item, linked to the job as inputs and not as its files
		self.assertEqual(len(got["inputs"]), 2)
		for row in got["inputs"]:
			asset = frappe.get_doc("Life Inbox Item", row["asset"])
			self.assertEqual((asset.intent, asset.status), ("Just keep", "Done"))
			self.assertEqual(len(files.attachments("Life Inbox Item", asset.name)), 1)
			self.assertEqual(row["file"]["file_name"], row["name"])
		self.assertEqual({r["reusable_as"] for r in got["inputs"]}, {"i8-btw-standard-deck", "i8-btw-brand"})
		self.assertEqual(sorted(p["status"] for p in got["proposals"]), ["Pending", "Pending"])
		self.assertEqual(len(out["proposals"]["waiting"]), 2)
		self.assertEqual(got["summary_md"], "A deck for Mehi Motors, from [[BTW standard deck]].")
		# the wiki page and the chat log, each linked to the item
		self.assertEqual(len(got["wiki_pages"]), 1)
		page = frappe.get_doc("Life Note", got["wiki_pages"][0]["name"])
		self.assertEqual(page.collection, "Wiki")
		self.assertIn(("Life Inbox Item", out["item"]), {(s.source_doctype, s.source_name) for s in page.sources})
		self.assertIn(("Life Chat Log", out["chat"]["name"]), {(s.source_doctype, s.source_name) for s in page.sources})
		self.assertEqual(got["job_chat"]["name"], out["chat"]["name"])
		chat = frappe.get_doc("Life Chat Log", out["chat"]["name"])
		self.assertEqual([i.text for i in chat.open_items], ["Check Vahan"])
		after = counts()
		self.assertEqual(after["Life Inbox Item"] - before["Life Inbox Item"], 3)  # the job and two assets
		self.assertEqual(after["Life Proposal"] - before["Life Proposal"], 2)
		self.assertEqual(after["Life Note"] - before["Life Note"], 1)
		self.assertEqual(after["Life Chat Log"] - before["Life Chat Log"], 1)
		self.assertEqual(after["File"] - before["File"], 4)
		self.assertTrue(out["url"].endswith(f"/life/item/{out['item']}"))

	def test_2_the_same_call_again_creates_nothing_and_updates_what_changed(self):
		first = call("i8-again")
		before = counts()
		same = call("i8-again")
		self.assertEqual(same["item"], first["item"])
		self.assertFalse(same["created"])
		self.assertEqual(same["changed_fields"], [])
		self.assertEqual(counts(), before)
		self.assertFalse(any(o["attached"] for o in same["outputs"]))
		self.assertFalse(any(i["asset_created"] or i["attached"] for i in same["inputs"]))
		self.assertEqual(same["proposals"]["created"], [])
		self.assertFalse(same["wiki"][0]["changed"])
		self.assertFalse(same["chat"]["created"])
		# changed fields are updated, still on the one item
		changed = call("i8-again", title="i8 Mehi Motors: deck, second cut", summary_md="A shorter deck.",
			instruction="Make it shorter.", wiki=[{"title": "i8 Mehi Motors Pvt Ltd", "content_md": "A Honda dealership in Kolkata."}])
		self.assertEqual(changed["item"], first["item"])
		self.assertEqual(set(changed["changed_fields"]), {"title", "summary_md", "instruction"})
		doc = frappe.get_doc("Life Inbox Item", first["item"])
		self.assertEqual((doc.title, doc.summary_md, doc.instruction), ("i8 Mehi Motors: deck, second cut", "A shorter deck.", "Make it shorter."))
		page = frappe.get_doc("Life Note", changed["wiki"][0]["name"])
		self.assertEqual(page.content_md, "A Honda dealership in Kolkata.")  # this job wrote it last, so its text is replaced
		self.assertEqual(frappe.db.count("Life Inbox Item", {"job_id": "i8-again"}), 1)
		self.assertEqual(frappe.db.count("Life Note", {"space": PRIVATE, "title": "i8 Mehi Motors Pvt Ltd"}), 1)
		# a proposal no longer sent goes while pending; a new one is added
		fewer = call("i8-again", proposals=[{"kind": "Task", "preview": "i8 call the owner", "payload": {"title": "i8 Call the owner"}}])
		self.assertEqual(len(fewer["proposals"]["removed"]), 2)
		self.assertEqual([p.preview for p in fewer["proposals"]["waiting"]], ["i8 call the owner"])

	def test_3_a_second_job_links_the_asset_already_kept_and_stores_no_new_file(self):
		first = call("i8-first")
		deck_files = frappe.db.count("File", {"life_sha256": files.sha256(DECK)})
		assets = frappe.db.count("Life Inbox Item", {"external_id": "i8-btw-standard-deck"})
		second = call("i8-second", title="i8 Arora Motors deck", wiki=[], chat=None, proposals=[],
			inputs=[{"name": "BTW standard deck.txt", "file": b64(DECK), "reusable_as": "i8-btw-standard-deck"},
				{"name": "BTW brand guidelines.txt", "reusable_as": "i8-btw-brand"}],  # no file: the kept one is linked
			outputs=[{"name": "Arora deck.txt", "file": b64(b"i8 arora deck")}])
		self.assertNotEqual(second["item"], first["item"])
		first_assets = {r["asset"] for r in inbox.get(first["item"])["inputs"]}
		self.assertEqual({r["asset"] for r in inbox.get(second["item"])["inputs"]}, first_assets)
		self.assertFalse(any(i["asset_created"] for i in second["inputs"]))
		self.assertEqual(frappe.db.count("Life Inbox Item", {"external_id": "i8-btw-standard-deck"}), assets)
		self.assertEqual(frappe.db.count("File", {"life_sha256": files.sha256(DECK)}), deck_files)
		self.assertEqual(len(stored(DECK)), 1)
		self.assertEqual(second["status"], "Done")  # nothing waits for the owner
		# an input used by this job only is attached to the job but listed as an input, not as an output
		own = call("i8-own", title="i8 own input", wiki=[], chat=None, proposals=[],
			inputs=[{"name": "Their brief.txt", "file": b64(b"i8 the client's own brief")}], outputs=[{"name": "Out.txt", "file": b64(b"i8 out")}])
		got = inbox.get(own["item"])
		self.assertEqual([f["file_name"] for f in got["files"]], ["Out.txt"])
		self.assertEqual(got["inputs"][0]["file"]["file_name"], "Their brief.txt")

	def test_4_an_invalid_proposal_refuses_the_whole_call_and_saves_nothing(self):
		before = counts()
		before_disk = len(stored(b"i8 never stored"))
		bad = [{"kind": "Task", "payload": {"title": "i8 fine"}}, {"kind": "Task", "payload": {"title": "i8 bad", "due_date": "not a date"}}]
		with self.assertRaises(frappe.ValidationError) as e:
			call("i8-invalid", proposals=bad, outputs=[{"name": "Out.txt", "file": b64(b"i8 never stored")}])
		self.assertIn("proposals[1]", str(e.exception))
		self.assertEqual(counts(), before)
		self.assertFalse(frappe.db.exists("Life Inbox Item", {"job_id": "i8-invalid"}))
		self.assertEqual(len(stored(b"i8 never stored")), before_disk)
		# a bad file and a bad wiki page are refused the same way, naming the field
		with self.assertRaises(frappe.ValidationError) as e:
			call("i8-invalid", outputs=[{"name": "Out.txt", "file": "not base64!"}])
		self.assertIn("outputs[0].file", str(e.exception))
		with self.assertRaises(frappe.ValidationError) as e:
			call("i8-invalid", wiki=[{"title": "i8 page"}])
		self.assertIn("wiki[0].content_md", str(e.exception))
		self.assertEqual(counts(), before)

	def test_4b_a_failure_while_writing_rolls_everything_back(self):
		before = counts()
		# the wiki pages are written last, after the item, its files, proposals and the chat log
		with patch("lifeos.api.jobs._wiki", side_effect=frappe.ValidationError("boom")):
			with self.assertRaises(frappe.ValidationError):
				call("i8-rollback", outputs=[{"name": "Out.txt", "file": b64(b"i8 rolled back")}])
		self.assertEqual(counts(), before)
		self.assertFalse(stored(b"i8 rolled back"))

	def test_5_an_agent_without_write_access_is_refused(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Life Space Member", {"parent": SHARED, "user": AGENT}, "access", "Read")
		permissions.clear_cache()
		try:
			self.as_user(AGENT)
			with self.assertRaises(frappe.PermissionError):
				call("i8-no-access", space=SHARED)
			self.assertFalse(frappe.db.exists("Life Inbox Item", {"job_id": "i8-no-access"}))
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Life Space Member", {"parent": SHARED, "user": AGENT}, "access", "Write")
			permissions.clear_cache()

	def test_6_agents_still_cannot_accept_proposals(self):
		out = call("i8-no-accept", proposals=[{"kind": "Task", "payload": {"title": "i8 agent may not accept"}, "status": "Accepted"}])
		name = out["proposals"]["waiting"][0].name
		self.assertEqual(frappe.db.get_value("Life Proposal", name, "status"), "Pending")
		with self.assertRaises(frappe.PermissionError):
			review.decide(proposal=name, decision="accept")
		with self.assertRaises(frappe.PermissionError):
			review.decide_all(item=out["item"], decision="accept")
		# filing again cannot decide them either
		again = call("i8-no-accept", proposals=[{"kind": "Task", "payload": {"title": "i8 agent may not accept"}, "status": "Accepted"}])
		self.assertEqual(frappe.db.get_value("Life Proposal", name, "status"), "Pending")
		self.assertEqual(again["status"], "To Review")

	def test_7_a_job_filed_the_old_way_is_taken_over_not_duplicated(self):
		old = inbox.create_item(title="i8 old box", space=PRIVATE, source_system="hermes", external_id="i8-old-way", intent="Just keep")["name"]
		out = call("i8-old-way", wiki=[], chat=None)
		self.assertEqual(out["item"], old)
		self.assertFalse(out["created"])
		doc = frappe.get_doc("Life Inbox Item", old)
		self.assertEqual((doc.job_id, doc.intent, doc.status), ("i8-old-way", "Process", "To Review"))
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE, "external_id": "i8-old-way"}), 1)
