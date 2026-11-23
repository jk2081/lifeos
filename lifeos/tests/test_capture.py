"""Tests for capture."""
import io
import json
import os
import re

import frappe
from frappe.core.doctype.file.utils import find_file_by_url, get_content_hash
from frappe.utils import add_to_date, now_datetime, today

from lifeos.calendar import calendar_data
from lifeos.goals import cycles
from lifeos.library import files, links, trash
from lifeos import permissions
from lifeos.brain import proposals
from lifeos.api import chats, connections, inbox, meta, review, wiki
from lifeos.tools.devtools import attach, load_fake_agent, LocalClient, pdf_bytes
from lifeos.web.pwa import SW_PATH
from lifeos.review import meetings
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import item, task, upload
from lifeos.tools import tidy


class InboxCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.sql("update `tabLife Inbox Item` set status='Done' where space in %s and status in ('New', 'Processing')", ((PRIVATE, SHARED),))

	def claim(self, **item):
		created = inbox.create_item(space=PRIVATE, **item)
		self.as_user(AGENT)
		claimed = inbox.claim_next(space=PRIVATE)
		self.assertEqual(claimed["name"], created["name"])
		return claimed


class TestInboxPipeline(InboxCase):
	def test_create_and_claim(self):
		item = inbox.create_item(title="Journal photo", source_type="Journal Photo", space=PRIVATE, instruction="transcribe")
		self.assertEqual(item["status"], "New")
		attach("Life Inbox Item", item["name"], "page.txt", b"scan")
		self.as_user(AGENT)
		claimed = inbox.claim_next()
		self.assertEqual(claimed["name"], item["name"])
		self.assertEqual(claimed["status"], "Processing")
		self.assertEqual(claimed["claimed_by"], AGENT)
		self.assertEqual(claimed["files"][0]["file_name"], "page.txt")
		self.assertTrue(claimed["files"][0]["file_size"])
		self.assertIn("Tea", [a["area_name"] for a in claimed["context"]["areas"]])
		self.assertIsNone(inbox.claim_next(space=PRIVATE))

	def test_claim_takes_the_oldest_first(self):
		a = inbox.create_item(title="First", space=PRIVATE)
		b = inbox.create_item(title="Second", space=PRIVATE)
		frappe.db.set_value("Life Inbox Item", a["name"], "received_on", add_to_date(now_datetime(), minutes=-5))
		self.as_user(AGENT)
		self.assertEqual(inbox.claim_next(space=PRIVATE)["name"], a["name"])
		self.assertEqual(inbox.claim_next(space=PRIVATE)["name"], b["name"])

	def test_claim_timeout_releases_the_item(self):
		claimed = self.claim(title="Slow one")
		frappe.db.set_value("Life Inbox Item", claimed["name"], "claimed_on", add_to_date(now_datetime(), minutes=-31))
		self.assertEqual(inbox.release_stale_claims(), 1)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", claimed["name"], ["status", "claimed_by"]), ("New", None))
		again = inbox.claim_next(space=PRIVATE)
		self.assertEqual(again["name"], claimed["name"])

	def test_fresh_claim_is_not_released(self):
		claimed = self.claim(title="Quick one")
		frappe.db.set_value("Life Inbox Item", claimed["name"], "claimed_on", add_to_date(now_datetime(), minutes=-10))
		self.assertEqual(inbox.release_stale_claims(), 0)

	def test_submit_sets_to_review(self):
		claimed = self.claim(title="Voice note", source_type="Voice Note")
		out = inbox.submit_result(claimed["name"], transcript_md="call Vivek", summary_md="one to-do", proposals=[
			{"kind": "Task", "preview": "Call Vivek", "payload": {"title": "Call Vivek", "area": "Money"}, "confidence": 0.9}])
		self.assertEqual((out["status"], len(out["created"]), out["errors"]), ("To Review", 1, []))
		doc = frappe.get_doc("Life Inbox Item", claimed["name"])
		self.assertEqual((doc.transcript_md, doc.summary_md), ("call Vivek", "one to-do"))
		payload = frappe.parse_json(frappe.db.get_value("Life Proposal", out["created"][0]["name"], "payload"))
		self.assertEqual(payload["area"], self.areas["Money"])  # a title is resolved to the record

	def test_invalid_proposals_are_refused_and_valid_ones_kept(self):
		claimed = self.claim(title="Mixed bag")
		out = inbox.submit_result(claimed["name"], summary_md="s", proposals=[
			{"kind": "Task", "payload": {"title": "Good one"}, "confidence": 0.8},
			{"kind": "Task", "payload": {"title": "Sets owner", "owner": "Administrator"}},
			{"kind": "Task", "payload": {"title": "Other space", "space": SHARED}},
			{"kind": "Task", "payload": {"title": "Unknown field", "docstatus": 1}},
			{"kind": "Task", "payload": {"priority": "I"}},
			{"kind": "Task", "payload": {"title": "Bad date", "due_date": "next Friday"}},
			{"kind": "Task", "payload": {"title": "Foreign area", "area": self.shared_areas["Family"]}},
			{"kind": "Vault Document", "payload": {"title": "PAN", "number_last4": "ABCDE1234F"}},
			{"kind": "Spaceship", "payload": {}},
			{"kind": "Note", "payload": {"title": "Also good"}, "confidence": 2},
			{"kind": "Note", "payload": {"title": "Good note"}},
		])
		self.assertEqual([c["index"] for c in out["created"]], [0, 10])
		self.assertEqual([e["index"] for e in out["errors"]], [1, 2, 3, 4, 5, 6, 7, 8, 9])
		self.assertIn("owner", out["errors"][0]["error"])
		self.assertIn("space", out["errors"][1]["error"])
		self.assertIn("not allowed", out["errors"][2]["error"])
		self.assertIn("required", out["errors"][3]["error"])
		self.assertEqual(out["status"], "To Review")
		self.assertEqual(frappe.db.count("Life Proposal", {"inbox_item": claimed["name"]}), 2)

	def test_fail_and_retry(self):
		claimed = self.claim(title="Broken scan")
		out = inbox.fail_item(claimed["name"], error="Could not read the image")
		self.assertEqual(out["status"], "Failed")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", claimed["name"], "error"), "Could not read the image")
		self.assertRaises(frappe.PermissionError, inbox.retry, claimed["name"])  # the agent cannot retry
		self.as_user(OWNER)
		self.assertEqual(inbox.retry(claimed["name"])["status"], "New")
		self.assertIsNone(frappe.db.get_value("Life Inbox Item", claimed["name"], "error"))
		self.as_user(AGENT)
		self.assertEqual(inbox.claim_next(space=PRIVATE)["name"], claimed["name"])

	def test_submit_needs_a_claim(self):
		item = inbox.create_item(title="Unclaimed", space=PRIVATE)
		self.as_user(AGENT)
		self.assertRaises(frappe.ValidationError, inbox.submit_result, item["name"], summary_md="x")

	def test_outsider_cannot_use_the_inbox_of_a_space(self):
		item = inbox.create_item(title="Private thing", space=PRIVATE)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, inbox.create_item, title="x", space=PRIVATE)
		self.assertRaises(frappe.PermissionError, inbox.get, item["name"])
		self.assertRaises(frappe.PermissionError, inbox.list, space=PRIVATE)
		self.assertIsNone(inbox.claim_next())
		self.assertRaises(frappe.PermissionError, inbox.claim_next, space=PRIVATE)

	def test_files_stay_private_and_original(self):
		item = inbox.create_item(title="With file", space=PRIVATE)
		f = attach("Life Inbox Item", item["name"], "pan-card.txt", b"original bytes")
		self.assertTrue(f.is_private)
		public = frappe.get_doc({"doctype": "File", "file_name": "public.txt", "attached_to_doctype": "Life Inbox Item",
			"attached_to_name": item["name"], "is_private": 0, "content": b"x"})
		self.assertRaises(frappe.ValidationError, public.insert)
		self.as_user(FAMILY)
		self.assertFalse(frappe.get_doc("File", f.name).has_permission("read"))
		self.as_user(AGENT)
		self.assertTrue(frappe.get_doc("File", f.name).has_permission("read"))
		claimed = inbox.claim_next(space=PRIVATE)
		inbox.submit_result(claimed["name"], summary_md="done", proposals=[])
		self.assertIn(frappe.get_doc("File", f.name).get_content(), (b"original bytes", "original bytes"))

	def test_image_gets_a_preview_of_at_most_1600px(self):
		import io

		from PIL import Image

		buf = io.BytesIO()
		Image.new("RGB", (3000, 2000), "white").save(buf, format="JPEG")
		item = inbox.create_item(title="Big photo", source_type="Journal Photo", space=PRIVATE)
		attach("Life Inbox Item", item["name"], "big.jpg", buf.getvalue())
		url = frappe.db.get_value("Life Inbox Item", item["name"], "preview_image")
		self.assertTrue(url)
		preview = frappe.get_doc("File", {"file_url": url, "attached_to_name": item["name"]})
		self.assertLessEqual(max(Image.open(io.BytesIO(preview.get_content())).size), 1600)
		self.assertEqual(len(inbox.get(item["name"])["files"]), 1)  # the preview is not listed as an original

	def test_schema_lists_every_kind(self):
		schema = meta.proposal_schema()
		kinds = frappe.get_meta("Life Proposal").get_field("kind").options.split("\n")
		self.assertEqual(sorted(schema), sorted(kinds))
		for kind, s in schema.items():
			self.assertTrue(s["fields"] and s["example"], kind)
			proposals.validate(kind, s["example"], "Private") if kind in ("Event", "Important Date") else None


class TestReview(InboxCase):
	def submit(self, rows, **item):
		claimed = self.claim(title=item.pop("title", "Review me"), **item)
		out = inbox.submit_result(claimed["name"], transcript_md="t", summary_md="s", proposals=rows)
		self.assertEqual(out["errors"], [])
		self.as_user(OWNER)
		return claimed["name"], [c["name"] for c in out["created"]]

	def test_agent_cannot_decide(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "T", "area": "Tea"}}])
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, review.decide, props[0], "accept")
		self.assertRaises(frappe.PermissionError, review.decide_all, item, "accept")
		prop = frappe.get_doc("Life Proposal", props[0])
		prop.status = "Accepted"
		self.assertRaises(frappe.PermissionError, prop.save)
		self.assertEqual(frappe.db.get_value("Life Proposal", props[0], "status"), "Pending")

	def test_outsider_cannot_decide(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "T", "area": "Tea"}}])
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, review.decide, props[0], "accept")

	def test_accept_reject_and_done(self):
		item, props = self.submit([
			{"kind": "Task", "payload": {"title": "Accept me", "area": "Tea"}},
			{"kind": "Task", "payload": {"title": "Reject me", "area": "Tea"}},
		])
		out = review.decide(props[0], "accept")
		self.assertEqual((out["status"], out["created_doctype"], out["item_status"]), ("Accepted", "Life Task", "To Review"))
		task = frappe.get_doc("Life Task", out["created_name"])
		self.assertEqual((task.title, task.inbox_item, task.area, task.space), ("Accept me", item, self.areas["Tea"], PRIVATE))
		out = review.decide(props[1], "reject")
		self.assertEqual((out["status"], out["item_status"]), ("Rejected", "Done"))
		self.assertFalse(frappe.db.exists("Life Task", {"title": "Reject me", "space": PRIVATE}))
		self.assertRaises(frappe.ValidationError, review.decide, props[0], "reject")
		self.assertEqual(str(frappe.db.get_value("Life Inbox Item", item, "finished_on")), today())

	def test_edit_then_accept(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "Generic promotion [?]", "area": "Personal"}, "confidence": 0.41}])
		out = review.decide(props[0], "accept", payload={"title": "Genetic promotion plan", "area": "Tea", "also_in": ["Money"], "priority": "II"})
		task = frappe.get_doc("Life Task", out["created_name"])
		self.assertEqual((task.title, task.area, task.priority), ("Genetic promotion plan", self.areas["Tea"], "II"))
		self.assertEqual([r.area for r in task.also_in], [self.areas["Money"]])

	def test_edited_payload_is_validated(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "T", "area": "Tea"}}])
		self.assertRaises(frappe.ValidationError, review.decide, props[0], "accept", {"title": "T", "owner": "Administrator"})
		self.assertRaises(frappe.ValidationError, review.decide, props[0], "accept", {"title": "T", "area": self.shared_areas["Work"]})
		self.assertEqual(frappe.db.get_value("Life Proposal", props[0], "status"), "Pending")

	def test_area_is_required_to_file_a_task(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "No area yet"}}])
		self.assertRaises(frappe.ValidationError, review.decide, props[0], "accept")
		review.update_payload(props[0], {"title": "No area yet", "area": "Money"})
		self.assertEqual(review.decide(props[0], "accept")["status"], "Accepted")

	def test_accept_all_keeps_what_fails(self):
		item, props = self.submit([
			{"kind": "Task", "payload": {"title": "Fine", "area": "Tea"}},
			{"kind": "Task", "payload": {"title": "Needs an area"}},
		])
		out = review.decide_all(item, "accept")
		self.assertEqual((out["decided"], len(out["errors"]), out["item_status"]), ([props[0]], 1, "To Review"))

	def test_each_kind_creates_the_right_record(self):
		self.as_user(OWNER)
		habit = self.make("Life Habit", title="Japa")
		person = self.make("Life Person", full_name="Ruchi")
		cycle = self.make("Life Cycle", title="Kinds cycle", start_date=today(), status="Active")
		goal = self.make("Life Goal", cycle=cycle.name, title="Close open loops", actions=[{"title": "Anya passport"}, {"title": "Ruchi ITR"}])
		claimed = self.claim(title="Everything", source_type="Journal Photo")
		attach("Life Inbox Item", claimed["name"], "page-187.png", b"\x89PNG fake")
		out = inbox.submit_result(claimed["name"], transcript_md="Goal Oct to Dec", summary_md="s", proposals=[
			{"kind": "Task", "payload": {"title": "Visit leased gardens", "area": "Tea", "goal": "Close open loops", "priority": "I"}},
			{"kind": "Event", "payload": {"subject": "Golf round", "starts_on": "2026-11-14 07:00:00"}},
			{"kind": "Important Date", "payload": {"title": "Ruchi", "day": 14, "month": 1, "kind": "Birthday"}},
			{"kind": "Note", "payload": {"title": "New crops by estate", "content_md": "pepper", "area": "Tea", "also_in": ["Money"]}},
			{"kind": "Vault Document", "payload": {"title": "Driving licence", "doc_type": "ID", "expiry_date": "2026-12-12", "number_last4": "4821", "area": "Personal", "holder": "Ruchi"}},
			{"kind": "Month Goal", "payload": {"title": "GHL visit", "year": 2033, "month": 2, "area": "Tea"}},
			{"kind": "Habit Log", "payload": {"habit": "Japa", "date": "2026-11-13"}},
			{"kind": "Week Tick", "payload": {"goal": "Close open loops", "action": "Anya passport", "mark_done": True}},
			{"kind": "Journal Page", "payload": {"page_date": "2026-11-14", "page_number": "187-188"}},
		])
		self.assertEqual(out["errors"], [])
		self.as_user(OWNER)
		done = review.decide_all(claimed["name"], "accept")
		self.assertEqual((done["errors"], done["item_status"]), ([], "Done"))
		made = {p.kind: p for p in frappe.get_all("Life Proposal", filters={"inbox_item": claimed["name"]}, fields=["kind", "created_doctype", "created_name", "status", "decided_by"])}
		self.assertTrue(all(p.status == "Accepted" and p.decided_by == OWNER for p in made.values()))

		task = frappe.get_doc("Life Task", made["Task"].created_name)
		self.assertEqual((task.goal, task.priority, task.inbox_item), (goal.name, "I", claimed["name"]))
		event = frappe.get_doc("Event", made["Event"].created_name)
		self.assertEqual((event.subject, event.life_space, event.event_type), ("Golf round", PRIVATE, "Public"))
		date = frappe.get_doc("Event", made["Important Date"].created_name)
		self.assertEqual((date.subject, date.all_day, date.repeat_on, str(date.starts_on)[5:10]), ("Ruchi", 1, "Yearly", "01-14"))
		self.assertEqual([d["title"] for d in calendar_data.important_dates_between(PRIVATE, "2035-01-14", "2035-01-14")], ["Ruchi"])
		note = frappe.get_doc("Life Note", made["Note"].created_name)
		self.assertEqual([r.area for r in note.also_in], [self.areas["Money"]])
		vault = frappe.get_doc("Life Vault Document", made["Vault Document"].created_name)
		self.assertEqual((vault.number_last4, str(vault.expiry_date), vault.holder), ("4821", "2026-12-12", person.name))
		self.assertTrue(vault.file)
		self.assertEqual(made["Month Goal"].created_doctype, "Life Goal")
		self.assertEqual([(g["title"], g["status"]) for g in cycles.month_goals(PRIVATE, 2033, 2)], [("GHL visit", "Open")])
		self.assertTrue(frappe.db.exists("Life Habit Log", {"habit": habit.name, "date": "2026-11-13", "done": 1}))
		goal.reload()
		action = goal.actions[0]
		self.assertEqual(action.status, "Done")
		self.assertTrue(frappe.db.exists("Life Action Log", {"action_id": action.name, "week": 1}))
		page = frappe.get_doc("Life Note", made["Journal Page"].created_name)  # a journal page is a note in My notes
		self.assertEqual((page.collection, str(page.page_date), page.content_md, page.inbox_item), ("My notes", "2026-11-14", "Goal Oct to Dec", claimed["name"]))
		self.assertEqual(page.title, "Journal page 187-188, 2026-11-14")
		self.assertTrue(page.image)
		# the original stays on the inbox item
		self.assertEqual(len(inbox.get(claimed["name"])["files"]), 1)


class TestFakeAgent(InboxCase):
	def test_journal_photo_gives_a_transcript_and_five_proposals(self):
		fake = load_fake_agent()
		cycle = self.make("Life Cycle", title="Fake agent cycle", start_date=today(), status="Active")
		self.make("Life Goal", cycle=cycle.name, title="Close open loops", actions=[{"title": "Anya passport"}])
		self.make("Life Goal", cycle=cycle.name, title="Money", actions=[{"title": "Meet Arjun Singh for PMS"}])
		item = inbox.create_item(title="Journal photo, pages 187 to 188", source_type="Journal Photo", space=PRIVATE,
			instruction="transcribe and update my journal")
		attach("Life Inbox Item", item["name"], "journal.png", b"\x89PNG fake")
		self.as_user(AGENT)
		result = fake.process_one(LocalClient(), today=today(), log=lambda *_: None)
		self.assertEqual((result["status"], len(result["created"]), result["errors"]), ("To Review", 5, []))
		self.as_user(OWNER)
		data = inbox.get(item["name"])
		self.assertIn("Anya passport", data["transcript_md"])
		props = data["proposals"]
		self.assertEqual([p["kind"] for p in props], ["Task", "Task", "Week Tick", "Task", "Journal Page"])
		# accept three, edit one, reject one
		review.decide(props[0]["name"], "accept", {**props[0]["payload"], "area": "Money"})
		review.decide(props[2]["name"], "accept")
		review.decide(props[4]["name"], "accept")
		review.decide(props[3]["name"], "accept", {"title": "Genetic promotion", "area": "Personal"})
		out = review.decide(props[1]["name"], "reject")
		self.assertEqual(out["item_status"], "Done")
		tasks = frappe.get_all("Life Task", filters={"inbox_item": item["name"]}, pluck="title")
		self.assertEqual(sorted(tasks), ["Genetic promotion", "Meet Arjun Singh for PMS"])
		self.assertTrue(frappe.db.exists("Life Note", {"inbox_item": item["name"], "page_date": today()}))

	def test_pdf_gives_tasks_and_failure_is_reported(self):
		fake = load_fake_agent()
		item = inbox.create_item(title="Mithun production documents.pdf", space=PRIVATE, instruction="summarise and extract to-dos")
		attach("Life Inbox Item", item["name"], "Mithun production documents.pdf", pdf_bytes())
		other = inbox.create_item(title="Will fail", space=PRIVATE)
		frappe.db.set_value("Life Inbox Item", other["name"], "received_on", add_to_date(now_datetime(), minutes=5))
		self.as_user(AGENT)
		result = fake.process_one(LocalClient(), log=lambda *_: None)
		self.assertEqual([c["kind"] for c in result["created"]], ["Task", "Task", "Task"])
		failed = fake.process_one(LocalClient(), fail=True, log=lambda *_: None)
		self.assertEqual(failed["status"], "Failed")
		self.assertIsNone(fake.process_one(LocalClient(), log=lambda *_: None))


def file(external_id, **kw):
	return inbox.create_item(**{"source_type": "Upload", "space": PRIVATE, "source_system": "hermes", "external_id": external_id, **kw})


class TestRefile(LifeTestCase):
	def test_1_intent_changes_on_the_one_item(self):
		a = file("i6-deck", title="i6 Mehi Motors deck", intent="Just keep")
		b = file("i6-deck", title="i6 Mehi Motors deck", intent="Process")
		self.assertEqual(a["name"], b["name"])
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE, "external_id": "i6-deck"}), 1)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], "intent"), "Process")

	def test_2_instruction_and_title_change_and_left_out_arguments_keep_their_value(self):
		a = file("i6-notes", title="i6 old title", instruction="old instruction", raw_text="text", intent="Just keep", area=self.areas["Tea"])
		file("i6-notes", title="i6 new title", instruction="new instruction")
		item = frappe.get_doc("Life Inbox Item", a["name"])
		self.assertEqual((item.title, item.instruction), ("i6 new title", "new instruction"))
		self.assertEqual((item.raw_text, item.intent, item.area), ("text", "Just keep", self.areas["Tea"]))
		file("i6-notes")  # everything left out: nothing changes, not even the title
		item.reload()
		self.assertEqual((item.title, item.instruction, item.raw_text, item.intent, item.area),
			("i6 new title", "new instruction", "text", "Just keep", self.areas["Tea"]))
		file("i6-notes", area=self.areas["Money"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], "area"), self.areas["Money"])

	def test_3_a_failed_item_whose_intent_changes_goes_back_to_new_and_is_claimed(self):
		a = file("i6-failed", title="i6 failed deck", intent="Just keep")
		frappe.db.set_value("Life Inbox Item", a["name"], {"status": "Failed", "error": "proposals refused",
			"received_on": add_to_date(now_datetime(), days=-3650)})
		file("i6-failed", intent="Process")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], ["status", "error"]), ("New", None))
		self.as_user(AGENT)
		got = inbox.claim_next(space=PRIVATE)
		self.assertEqual((got["name"], got["intent"]), (a["name"], "Process"))

	def test_3b_a_done_item_whose_intent_changes_goes_back_but_one_whose_area_changes_does_not(self):
		a = file("i6-done", title="i6 done", intent="Just keep")
		frappe.db.set_value("Life Inbox Item", a["name"], "status", "Done")
		file("i6-done", area=self.areas["Money"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], "status"), "Done")
		file("i6-done", intent="Process")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], "status"), "New")

	def test_4_the_answer_says_updated_and_which_fields_changed(self):
		a = file("i6-answer", title="i6 answer", intent="Just keep", instruction="one")
		self.assertTrue(a["created"])
		self.assertFalse(a["updated"])
		b = file("i6-answer", title="i6 answer", intent="Process", instruction="two")
		self.assertFalse(b["created"])
		self.assertTrue(b["updated"])
		self.assertEqual(sorted(b["changed_fields"]), ["instruction", "intent"])
		c = file("i6-answer", intent="Process")
		self.assertEqual(c["changed_fields"], [])
		self.assertFalse(c["changed"])

	def test_5_an_agent_without_write_access_cannot_change_the_item(self):
		a = inbox.create_item(title="i6 shared", source_type="Upload", space=SHARED, source_system="hermes", external_id="i6-shared",
			intent="Just keep")
		frappe.set_user("Administrator")
		space = frappe.get_doc("Life Space", SHARED)
		for m in space.members:
			if m.user == AGENT:
				m.access = "Read"
		space.save(ignore_permissions=True)
		try:
			self.as_user(AGENT)
			with self.assertRaises(frappe.PermissionError):
				inbox.create_item(source_type="Upload", space=SHARED, source_system="hermes", external_id="i6-shared", intent="Process")
			self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], "intent"), "Just keep")
		finally:
			frappe.set_user("Administrator")
			space.reload()
			for m in space.members:
				if m.user == AGENT:
					m.access = "Write"
			space.save(ignore_permissions=True)
			permissions.clear_cache()
			frappe.set_user(OWNER)


DECK = b"issue 7 standard deck, version one"


def rows(doctype, name):
	return frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name, "attached_to_field": ["is", "not set"]},
		fields=["name", "file_url", "life_sha256", "life_version_of"])


def on_disk(file_url):
	return os.path.exists(frappe.get_site_path(file_url.lstrip("/")))


class TestFilesOnce(LifeTestCase):
	def test_1_same_bytes_twice_in_one_space_is_one_stored_file_linked_to_both(self):
		a, b = item("i7 deck for Mehi"), item("i7 deck for Arora")
		fa = upload("Life Inbox Item", a, "BTW standard deck.txt", DECK)
		fb = upload("Life Inbox Item", b, "BTW standard deck.txt", DECK)
		self.assertNotEqual(fa.name, fb.name)  # one link per record
		self.assertEqual(fa.file_url, fb.file_url)  # one stored copy
		self.assertTrue(on_disk(fa.file_url))
		self.assertEqual(fa.life_sha256, files.sha256(DECK))
		self.assertEqual(frappe.db.count("File", {"life_sha256": files.sha256(DECK)}), 2)
		self.assertEqual(len({r.file_url for r in frappe.get_all("File", filters={"life_sha256": files.sha256(DECK)}, fields=["file_url"])}), 1)
		# the same file sent again to the same item is not attached a second time
		again = upload("Life Inbox Item", a, "BTW standard deck.txt", DECK)
		self.assertEqual(again.name, fa.name)
		self.assertEqual(len(rows("Life Inbox Item", a)), 1)
		self.assertEqual(len(inbox._item_dict(frappe.get_doc("Life Inbox Item", a))["files"]), 1)

	def test_2_same_bytes_in_two_spaces_are_stored_separately(self):
		a, b = item("i7 private copy"), item("i7 shared copy", space=SHARED)
		fa = upload("Life Inbox Item", a, "i7 scan.txt", DECK + b" two spaces")
		fb = upload("Life Inbox Item", b, "i7 scan.txt", DECK + b" two spaces")
		self.assertEqual(fa.life_sha256, fb.life_sha256)
		self.assertNotEqual(fa.file_url, fb.file_url)
		self.assertTrue(on_disk(fa.file_url) and on_disk(fb.file_url))

	def test_3_refiling_with_a_changed_file_of_the_same_name_keeps_one_current_file_and_one_earlier_version(self):
		ext = {"source_system": "hermes", "external_id": "i7-btw-standard-deck"}
		name = item("i7 BTW standard deck", **ext)
		first = upload("Life Inbox Item", name, "BTW standard deck.txt", DECK)
		self.assertEqual(item("i7 BTW standard deck", **ext), name)  # filed again: the same item
		second = upload("Life Inbox Item", name, "BTW standard deck.txt", DECK + b", version two")
		listed = files.attachments("Life Inbox Item", name)
		self.assertEqual([f.name for f in listed], [second.name])
		self.assertEqual([v.name for v in listed[0].versions], [first.name])
		self.assertEqual(frappe.db.get_value("File", first.name, "life_version_of"), second.name)
		self.assertEqual(files.read(frappe.get_doc("File", second.name)), DECK + b", version two")
		self.assertEqual(files.read(frappe.get_doc("File", first.name)), DECK)
		self.assertEqual(second.file_name, "BTW standard deck.txt")  # the name it was sent with, though stored under another
		shown = inbox._item_dict(frappe.get_doc("Life Inbox Item", name))["files"]
		self.assertEqual((len(shown), len(shown[0]["versions"])), (1, 1))
		# an item without an external_id keeps both as attachments
		plain = item("i7 plain item")
		upload("Life Inbox Item", plain, "notes.txt", b"one")
		upload("Life Inbox Item", plain, "notes.txt", b"two")
		self.assertEqual(len(files.attachments("Life Inbox Item", plain)), 2)

	def test_4_deleting_one_of_two_records_that_share_a_file_leaves_the_file_for_the_other(self):
		a = self.make("Life Note", title="i7 note one", content_md="x")
		b = self.make("Life Note", title="i7 note two", content_md="y")
		fa = upload("Life Note", a.name, "i7 shared.txt", DECK + b" shared")
		fb = upload("Life Note", b.name, "i7 shared.txt", DECK + b" shared")
		self.assertEqual(fa.file_url, fb.file_url)
		trash.delete("Life Note", a.name)
		frappe.db.after_commit.run()  # the disk is cleaned after the commit
		self.assertFalse(frappe.db.exists("File", fa.name))
		self.assertTrue(frappe.db.exists("File", fb.name))
		self.assertTrue(on_disk(fb.file_url))
		self.assertEqual(files.read(frappe.get_doc("File", fb.name)), DECK + b" shared")
		# the last record using it goes: so does the stored copy, though another space holds the same bytes
		other = upload("Life Inbox Item", item("i7 shared bytes elsewhere", space=SHARED), "i7 shared.txt", DECK + b" shared")
		trash.delete("Life Note", b.name)
		frappe.db.after_commit.run()
		self.assertFalse(on_disk(fb.file_url))
		self.assertTrue(on_disk(other.file_url))

	def test_5_a_user_who_cannot_see_either_record_cannot_download_the_file(self):
		a, b = item("i7 private one"), item("i7 private two")
		fa = upload("Life Inbox Item", a, "i7 private.txt", DECK + b" private")
		upload("Life Inbox Item", b, "i7 private.txt", DECK + b" private")
		self.as_user(OWNER)
		self.assertTrue(find_file_by_url(fa.file_url))
		self.as_user(FAMILY)  # not a member of the private space
		self.assertIsNone(find_file_by_url(fa.file_url))
		self.assertFalse(frappe.get_doc("File", fa.name).has_permission("read"))
		# the same bytes uploaded in a space the family member can see get their own copy, not a door to the private one
		mine = upload("Life Inbox Item", item("i7 family copy", space=SHARED), "i7 private.txt", DECK + b" private")
		self.assertNotEqual(mine.file_url, fa.file_url)
		self.assertIsNone(find_file_by_url(fa.file_url))


DECK_tidy = b"issue 9 BTW standard deck"


PITCH = b"issue 9 Mehi Motors pitch"


NOTES = b"issue 9 Mehi brief notes"


REFUSAL = "submit_result refused: This item is to be kept only (intent Just keep). Send its text with no proposals."


def stored_twice(name, file_name, content, doctype="Life Inbox Item", hashed=True):
	"""A file stored the way it was before issue 7: its own copy on disk, whatever else holds the same bytes. Patch
	v10.file_hashes gave it its SHA-256 unless `hashed` is False."""
	stored = f"i9-{frappe.generate_hash(length=8)}-{file_name}"
	with open(frappe.get_site_path("private", "files", stored), "wb") as fh:
		fh.write(content)
	doc = frappe.get_doc({"doctype": "File", "file_name": file_name, "file_url": f"/private/files/{stored}", "is_private": 1,
		"attached_to_doctype": doctype, "attached_to_name": name})
	doc.flags.copy_from_existing_file = True
	doc.insert(ignore_permissions=True)
	frappe.db.set_value("File", doc.name, {"content_hash": get_content_hash(content), "file_size": len(content),
		"life_sha256": files.sha256(content) if hashed else None})
	return frappe.get_doc("File", doc.name)


def on_disk_tidy(url):
	return os.path.isfile(frappe.get_site_path(url.lstrip("/")))


def current(name):
	return frappe.get_all("File", filters={"attached_to_doctype": "Life Inbox Item", "attached_to_name": name,
		"attached_to_field": ["is", "not set"], "life_version_of": ["is", "not set"]}, fields=["name", "file_name", "file_url"])


class TestTidy(LifeTestCase):
	@classmethod
	def tearDownClass(cls):
		folder = frappe.get_site_path("private", "files")
		for name in os.listdir(folder):
			if name.startswith("i9-"):  # the copies seeded here; their rows are rolled back with the test
				os.remove(os.path.join(folder, name))
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.backups = []

	def tidy(self, apply=False, backup=None):
		return tidy.Tidy(apply=apply, spaces=[PRIVATE, SHARED], backup=backup or self.fake_backup).run()

	def fake_backup(self):
		self.backups.append(1)
		return ["fake-database.sql.gz", "fake-files.tar", "fake-private-files.tar"]

	def counts(self):
		disk = sorted(os.listdir(frappe.get_site_path("private", "files")))
		return {dt: frappe.db.count(dt) for dt in ("File", "Life Inbox Item", "Life Proposal", "Life Note", "Life Task", "Comment")} | {"disk": disk}

	def seed_duplicates(self, content=DECK_tidy):
		a, b = item("i9 Mehi deck"), item("i9 Arora deck")
		fa = stored_twice(a, "deck.txt", content)
		fb = stored_twice(b, "deck.txt", content)
		twin = stored_twice(b, "deck.txt", content, hashed=False)  # the same deck attached twice to one item
		other = stored_twice(item("i9 shared deck", space=SHARED), "deck.txt", content)  # another space keeps its own copy
		return a, b, fa, fb, twin, other

	def test_1_dry_run_reports_duplicates_and_changes_nothing(self):
		a, b, fa, fb, twin, _ = self.seed_duplicates()
		before = self.counts()
		report = self.tidy()
		self.assertFalse(report["applied"])
		groups = [g for g in report["duplicates"] if g["sha256"] == files.sha256(DECK_tidy)]
		self.assertEqual(len(groups), 1)  # one group per space with copies: the shared space has a single copy
		group = groups[0]
		self.assertEqual(group["keep"]["file_url"], fa.file_url)  # the oldest
		self.assertEqual({c["file_url"] for c in group["copies"]}, {fb.file_url, twin.file_url})
		self.assertIn(b, {r["name"] for c in group["copies"] for r in c["records"]})
		self.assertEqual([(t["name"], t["drop"]) for t in group["twins"]], [(b, twin.name)])
		self.assertEqual(self.counts(), before)
		self.assertEqual(self.backups, [])
		self.assertIn("Dry run", tidy.Tidy(spaces=[PRIVATE]).text(report))

	def test_2_apply_stores_each_file_once_and_every_record_still_opens_its_files(self):
		deck = DECK_tidy + b", merged"
		a, b, fa, fb, twin, other = self.seed_duplicates(deck)
		report = self.tidy(apply=True)
		self.assertTrue(report["applied"])
		self.assertEqual(self.backups, [1])
		rows = frappe.get_all("File", filters={"life_sha256": files.sha256(deck), "attached_to_name": ["in", [a, b]]},
			fields=["name", "file_url"])
		self.assertEqual({r.file_url for r in rows}, {fa.file_url})
		self.assertEqual(len(rows), 2)  # one row for each item: b's second row went
		self.assertFalse(frappe.db.exists("File", twin.name))
		for url in (fb.file_url, twin.file_url):
			self.assertFalse(on_disk_tidy(url))
		self.assertTrue(on_disk_tidy(fa.file_url) and on_disk_tidy(other.file_url))
		self.as_user(OWNER)
		for name in (a, b):
			shown = inbox._item_dict(frappe.get_doc("Life Inbox Item", name))["files"]
			self.assertEqual(len(shown), 1)
			opened = find_file_by_url(shown[0]["file_url"])  # what /private/files/... checks before it serves the file
			self.assertTrue(opened)
			self.assertEqual(files.read(opened), deck)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": b, "content": ["like", "Tidy:%"]}))

	def test_3_apply_moves_an_items_input_files_to_reusable_assets_and_keeps_its_outputs(self):
		asset = item("i9 BTW deck", intent="Just keep", source_system="hermes", external_id="i9-btw-standard-deck")
		stored_twice(asset, "BTW deck.txt", DECK_tidy)
		other_job = item("i9 Arora pitch", source_system="hermes", external_id="i9-arora")
		stored_twice(other_job, "brief notes.txt", NOTES)
		job = item("i9 Mehi Motors pitch", source_system="hermes", external_id="i9-mehi-motors")
		stored_twice(job, "BTW deck.txt", DECK_tidy)
		stored_twice(job, "brief notes.txt", NOTES)
		out = stored_twice(job, "Mehi pitch.txt", PITCH)
		report = self.tidy()
		found = next(j for j in report["jobs"] if j["item"] == job)
		self.assertEqual(sorted(f["file_name"] for f in found["inputs"]), ["BTW deck.txt", "brief notes.txt"])
		self.assertEqual([f["file_name"] for f in found["outputs"]], ["Mehi pitch.txt"])

		self.tidy(apply=True)
		doc = frappe.get_doc("Life Inbox Item", job)
		self.assertEqual([f.name for f in current(job)], [out.name])
		self.assertEqual(doc.job_id, "i9-mehi-motors")
		links = {r.label: r for r in doc.job_inputs}
		self.assertEqual(set(links), {"BTW deck.txt", "brief notes.txt"})
		self.assertEqual(links["BTW deck.txt"].asset, asset)  # the asset already kept
		made = links["brief notes.txt"].asset
		self.assertEqual(frappe.db.get_value("Life Inbox Item", made, ["intent", "external_id"]), ("Just keep", "brief-notes"))
		self.assertEqual(files.read(frappe.get_doc("File", current(made)[0].name)), NOTES)
		self.assertEqual(files.read(frappe.get_doc("File", current(asset)[0].name)), DECK_tidy)
		# the other job that had the notes is not a mixed job (no output), so it keeps its file
		self.assertEqual(len(current(other_job)), 1)

	def test_4_apply_puts_an_intent_refused_failed_item_back_to_new(self):
		refused = item("i9 refused deck", intent="Just keep", source_system="hermes", external_id="i9-refused")
		other = item("i9 other failure")
		frappe.db.set_value("Life Inbox Item", refused, {"status": "Failed", "error": REFUSAL})
		frappe.db.set_value("Life Inbox Item", other, {"status": "Failed", "error": "The PDF could not be read."})
		report = self.tidy()
		self.assertEqual([r["name"] for r in report["failed"]], [refused])
		self.tidy(apply=True)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", refused, ["status", "error"]), ("New", None))
		self.assertEqual(frappe.db.get_value("Life Inbox Item", other, "status"), "Failed")
		for name in frappe.get_all("Life Inbox Item", filters={"space": PRIVATE, "status": "New", "name": ["!=", refused]}, pluck="name"):
			frappe.db.set_value("Life Inbox Item", name, "status", "Done")  # so the claim below has only this one to take
		frappe.set_user(AGENT)
		self.assertEqual(inbox.claim_next(space=PRIVATE)["name"], refused)

	def test_5_apply_refuses_to_start_when_the_backup_fails(self):
		self.seed_duplicates()
		refused = item("i9 refused again")
		frappe.db.set_value("Life Inbox Item", refused, {"status": "Failed", "error": REFUSAL})
		before = self.counts()

		def broken():
			raise OSError("mysqldump: disk full")

		with self.assertRaises(tidy.TidyRefused):
			self.tidy(apply=True, backup=broken)
		self.assertEqual(self.counts(), before)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", refused, "status"), "Failed")

	def test_6_running_apply_twice_changes_nothing_the_second_time(self):
		self.seed_duplicates(DECK_tidy + b", twice")
		job = item("i9 twice pitch", source_system="hermes")
		stored_twice(job, "deck.txt", DECK_tidy)
		stored_twice(job, "pitch.txt", PITCH + b", filed twice")
		refused = item("i9 twice refused")
		frappe.db.set_value("Life Inbox Item", refused, {"status": "Failed", "error": REFUSAL})
		first = self.tidy(apply=True)
		self.assertTrue(first["duplicates"] and first["jobs"] and first["failed"])
		before = self.counts()
		second = self.tidy(apply=True)
		self.assertEqual(second["summary"]["to_do"], 0)
		self.assertFalse(second["applied"])
		self.assertEqual(second["actions"], [])
		self.assertEqual(self.counts(), before)
		self.assertEqual(self.backups, [1])  # nothing to do: no second backup


class TestItemPage(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.sql("update `tabLife Inbox Item` set status='Done' where space=%s and status in ('New', 'Processing')", PRIVATE)
		self.item = inbox.create_item(title="i10 production note", space=PRIVATE, instruction="summarise and extract to-dos")["name"]
		attach("Life Inbox Item", self.item, "i10-note.txt", b"i10 the note")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		out = inbox.submit_result(self.item, transcript_md="i10 the words", summary_md="i10 the summary", proposals=[
			{"kind": "Task", "preview": "i10 Call Vivek", "payload": {"title": "i10 Call Vivek", "area": "Tea"}, "confidence": 0.9},
			{"kind": "Task", "preview": "i10 Book the hall", "payload": {"title": "i10 Book the hall", "area": "Tea"}, "confidence": 0.8},
			{"kind": "Task", "preview": "i10 Send the letter", "payload": {"title": "i10 Send the letter", "area": "Tea"}, "confidence": 0.7}])
		self.proposals = [p["name"] for p in out["created"]]
		self.as_user(OWNER)
		review.decide(self.proposals[0], "accept")

	def test_1_every_section_has_its_content(self):
		got = inbox.item_page(self.item)
		self.assertEqual([f["file_name"] for f in got["files"]], ["i10-note.txt"])
		self.assertEqual((got["summary_md"], got["transcript_md"], got["instruction"]), ("i10 the summary", "i10 the words", "summarise and extract to-dos"))
		self.assertEqual(got["space_name"], PRIVATE)
		self.assertEqual(len([p for p in got["proposals"] if p["status"] == "Pending"]), 2)
		self.assertEqual([(m["kind"], m["title"], m["state"]) for m in got["came_of_it"]], [("Task", "i10 Call Vivek", "Open")])
		self.assertEqual(got["came_of_it"][0]["route"], links.route_of("Life Task", got["came_of_it"][0]["name"]))
		self.assertEqual(got["related"], {"pages": [], "chats": [], "meetings": []})

	def test_2_accepting_a_proposal_adds_it_to_what_came_of_it(self):
		review.decide(self.proposals[1], "accept")
		got = inbox.item_page(self.item)
		self.assertEqual([m["title"] for m in got["came_of_it"]], ["i10 Call Vivek", "i10 Book the hall"])
		self.assertEqual(len([p for p in got["proposals"] if p["status"] == "Pending"]), 1)
		task = got["came_of_it"][0]["name"]
		frappe.db.set_value("Life Task", task, "status", "Done")
		self.assertEqual(inbox.item_page(self.item)["came_of_it"][0]["state"], "Done")

	def test_3_related_wiki_pages_chat_logs_and_meetings(self):
		self.as_user(AGENT)
		wiki.create_page(space=PRIVATE, title="i10 Production", summary="From the note", content_md="From the note.", sources=[{"doctype": "Life Inbox Item", "name": self.item}])
		self.as_user(OWNER)
		chat = chats.log(space=PRIVATE, title="i10 chat about it", assistant="Claude", summary_md="About the note.")["name"]
		frappe.db.set_value("Life Chat Log", chat, "inbox_item", self.item)  # a chat log kept from this capture
		event = frappe.get_doc({"doctype": "Event", "subject": "i10 production meeting", "starts_on": now_datetime(), "event_type": "Private",
			"life_space": PRIVATE}).insert().name
		meetings.link(event, "Life Inbox Item", self.item)
		rel = inbox.item_page(self.item)["related"]
		self.assertEqual([(p["kind"], p["title"]) for p in rel["pages"]], [("Wiki page", "i10 Production")])
		self.assertEqual([c["name"] for c in rel["chats"]], [chat])
		self.assertEqual([(m["title"], m["ref"]) for m in rel["meetings"]], [("i10 production meeting", f"event:{event}")])

	def test_4_a_user_outside_the_space_gets_not_found(self):
		self.as_user(FAMILY)
		with self.assertRaises(frappe.DoesNotExistError):
			inbox.item_page(self.item)
		with self.assertRaises(frappe.DoesNotExistError):
			inbox.item_page("no-such-item")

	def test_5_links_and_search_lead_to_the_item_page(self):
		self.assertEqual(links.route_of("Life Inbox Item", self.item), f"/item/{self.item}")


def _app_file(*parts):
	with open(frappe.get_app_path("lifeos", *parts), encoding="utf-8") as f:
		return f.read()


class TestPhone(LifeTestCase):
	def test_manifest_is_installable_and_takes_shares(self):
		m = json.loads(_app_file("public", "manifest.webmanifest"))
		self.assertEqual((m["name"], m["display"], m["start_url"]), ("Life OS", "standalone", "/life/today"))
		self.assertTrue(any(i["sizes"] == "512x512" for i in m["icons"]))
		target = m["share_target"]
		self.assertEqual((target["action"], target["method"], target["enctype"]), ("/life/share", "POST", "multipart/form-data"))
		self.assertEqual(target["params"]["files"][0]["name"], "files")

	def test_service_worker_caches_only_the_apps_static_files(self):
		self.assertEqual(SW_PATH, "life/sw.js")
		sw = _app_file("public", "life-sw.js")
		self.assertEqual(len(re.findall(r"cache\.put\(", sw)), 1)  # the one place a response is cached ...
		self.assertIn("url.pathname.startsWith(STATIC_PREFIX)", sw)  # ... is only reached for /assets/lifeos/ files
		self.assertIn("const STATIC_PREFIX = '/assets/lifeos/'", sw)
		self.assertNotIn("/api/", sw)

	def test_a_phone_capture_is_one_capture_however_often_it_is_sent(self):
		args = {"title": "I50 shared link", "source_type": "Phone", "space": PRIVATE, "raw_text": "https://example.com",
			"source_system": "phone", "external_id": "i50-a-uuid"}
		first = inbox.create_item(**args)
		again = inbox.create_item(**args)  # a retry after the answer was lost
		self.assertTrue(first["created"])
		self.assertEqual((again["created"], again["name"]), (False, first["name"]))
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE, "external_id": "i50-a-uuid"}), 1)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", first["name"], "source_type"), "Phone")

	def test_the_phone_is_not_a_connection_and_cannot_be_switched_off(self):
		inbox.create_item(title="I50 from the phone", source_type="Phone", space=PRIVATE, source_system="phone")
		self.assertFalse(frappe.db.exists("Life Connection", {"space": PRIVATE, "system": "phone"}))
		connections.require_on(PRIVATE, "phone")  # does not raise
