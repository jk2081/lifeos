"""Issue 18: Brain > Activity. The feed of captures and what the Brain did with each, its filters, failed items, and the Outbox piles."""
import frappe
from frappe.utils import add_to_date, now_datetime

from lifeos.api import brain, inbox, outbox, review
from lifeos.tests.base import FAMILY, PRIVATE, LifeTestCase


class TestActivity(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.sql("update `tabLife Inbox Item` set is_archived=1 where space=%s", (PRIVATE,))
		self.tea = self.areas["Tea"]

	def capture(self, title, status="Done", source="Email", **extra):
		return frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": title, "source_type": source, "status": status,
			"received_on": now_datetime(), **extra}).insert()

	def proposal(self, item, status="Pending"):
		doc = frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": item.name, "kind": "Task", "preview": item.title,
			"payload": frappe.as_json({"title": item.title, "area": self.tea}), "confidence": 0.8, "status": "Pending"}).insert()
		if status != "Pending":
			frappe.db.set_value("Life Proposal", doc.name, "status", status)
		return doc

	def feed(self, **kw):
		return brain.activity(space=PRIVATE, **kw)

	def test_a_capture_filed_on_its_own_shows_with_its_area(self):
		item = self.capture("i18 filed", area=self.tea)
		row = next(r for r in self.feed()["rows"] if r["item"] == item.name)
		self.assertEqual((row["outcome"], row["area"], row["area_name"], row["source"]), ("filed", self.tea, "Tea", "Email"))

	def test_every_outcome_is_told_apart(self):
		self.capture("i18 working", "Processing")
		self.capture("i18 failed", "Failed", error="No text in the file")
		self.proposal(self.capture("i18 waiting", "To Review"))
		self.capture("i18 filed")
		rejected = self.capture("i18 dropped")
		self.proposal(rejected, "Rejected")
		decided = self.capture("i18 decided")
		self.proposal(decided, "Accepted")
		counts = self.feed()["counts"]
		self.assertEqual({k: counts[k] for k in counts}, {"filed": 1, "waiting": 1, "dropped": 1, "failed": 1, "decided": 1, "working": 1})
		self.assertEqual([r["title"] for r in self.feed(outcome="dropped")["rows"]], ["i18 dropped"])
		self.assertEqual(self.feed(outcome="dropped")["total"], 1)

	def test_the_source_filter_narrows_the_feed(self):
		self.capture("i18 mail", source="Email")
		self.capture("i18 voice", source="Voice Note")
		got = self.feed(source="Voice Note")
		self.assertEqual([r["title"] for r in got["rows"]], ["i18 voice"])
		self.assertEqual(sorted(got["sources"]), ["Email", "Voice Note"])

	def test_the_area_filter_narrows_the_feed(self):
		self.capture("i18 tea", area=self.tea)
		self.capture("i18 none")
		self.assertEqual([r["title"] for r in self.feed(area=self.tea)["rows"]], ["i18 tea"])

	def test_newest_first_and_the_period(self):
		self.capture("i18 old", received_on=add_to_date(now_datetime(), days=-3))
		self.capture("i18 ancient", received_on=add_to_date(now_datetime(), days=-30))
		self.capture("i18 new")
		self.assertEqual([r["title"] for r in self.feed()["rows"]], ["i18 new", "i18 old"])

	def test_a_failed_capture_has_its_reason_and_retry_queues_it_again(self):
		item = self.capture("i18 broken", "Failed", error="No text in the file")
		row = self.feed(outcome="failed")["rows"][0]
		self.assertEqual((row["item"], row["error"]), (item.name, "No text in the file"))
		inbox.retry(item.name)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item.name, "status"), "New")
		self.assertEqual(self.feed()["rows"][0]["outcome"], "working")

	def test_the_records_made_are_linked(self):
		item = self.capture("i18 made", "To Review")
		p = self.proposal(item)
		review.decide(p.name, "accept")
		row = next(r for r in self.feed()["rows"] if r["item"] == item.name)
		self.assertEqual(row["outcome"], "decided")
		self.assertEqual([m["doctype"] for m in row["made"]], ["Life Task"])

	def test_the_plate_has_the_outboxs_numbers(self):
		plate = self.feed()["plate"]
		start, end, _p = outbox.bounds("week")
		listed = outbox.list(space=PRIVATE, pile="all")
		self.assertEqual(plate["piles"], {k: listed["tabs"][k] for k in plate["piles"]})
		self.assertEqual(plate["in"], listed["tabs"]["in"])

	def test_a_family_member_sees_only_their_spaces(self):
		self.capture("i18 private")
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			self.feed()
