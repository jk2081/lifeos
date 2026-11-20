"""Issue 10: the item page (lifeos.api.inbox.item_page): one capture with its files, summary, proposals, what came of it and
what is related to it."""
import frappe
from frappe.utils import now_datetime

from lifeos import links
from lifeos.api import chats, inbox, review, wiki
from lifeos.devtools import attach
from lifeos.review import meetings
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, LifeTestCase


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
