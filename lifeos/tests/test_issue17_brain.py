"""Issue 17: Brain > Needs you. A proposal carries a reason and a second-choice area; the screen's server part lists what needs a decision."""
import frappe
from frappe.utils import add_to_date, now_datetime

from lifeos.api import brain, inbox, meta, review
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


class TestNeedsYou(LifeTestCase):
	def setUp(self):
		super().setUp()
		# nothing else in the test space waits or came in
		frappe.db.sql("update `tabLife Inbox Item` set status='Done', is_archived=1 where space=%s", (PRIVATE,))
		self.tea, self.money, self.personal = self.areas["Tea"], self.areas["Money"], self.areas["Personal"]

	def waiting(self, title, area=None, alt=None, reason=None, kind="Task", hours_ago=0, **payload):
		item = frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": title, "source_type": "Email", "status": "To Review",
			"received_on": add_to_date(now_datetime(), hours=-hours_ago)}).insert()
		body = {"title": title, **payload, **({"area": area} if area else {})}
		prop = frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": item.name, "kind": kind, "preview": title,
			"payload": frappe.as_json(body), "confidence": 0.6, "status": "Pending", "reason": reason, "alt_area": alt}).insert()
		return item, prop

	# ---- 9: reason and alt_area through submit_result ----
	def submit(self, **extra):
		created = inbox.create_item(title="i17 submit", space=PRIVATE, raw_text="x")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		row = {"kind": "Task", "preview": "i17 call", "payload": {"title": "i17 call", "area": self.tea}, "confidence": 0.7, **extra}
		return created["name"], inbox.submit_result(item=created["name"], proposals=[row])

	def test_submit_result_stores_reason_and_alt_area(self):
		name, res = self.submit(reason="  Mentions both\nTea and Money ", alt_area=self.money)
		self.assertEqual(res["errors"], [])
		p = frappe.db.get_value("Life Proposal", res["created"][0]["name"], ["reason", "alt_area", "payload"], as_dict=True)
		self.assertEqual((p.reason, p.alt_area), ("Mentions both Tea and Money", self.money))
		self.as_user(OWNER)
		got = inbox.get(name)["proposals"][0]
		self.assertEqual((got["reason"], got["alt_area"]), ("Mentions both Tea and Money", self.money))

	def test_both_are_optional(self):
		_, res = self.submit()
		self.assertEqual(res["errors"], [])
		self.assertEqual(frappe.db.get_value("Life Proposal", res["created"][0]["name"], ["reason", "alt_area"]), (None, None))

	def test_alt_area_the_same_as_area_is_refused(self):
		_, res = self.submit(alt_area=self.tea)
		self.assertEqual(res["created"], [])
		self.assertIn("different", res["errors"][0]["error"])

	def test_alt_area_in_another_space_is_refused(self):
		_, res = self.submit(alt_area=self.shared_areas["Family"])
		self.assertEqual(res["created"], [])
		self.assertIn("not found", res["errors"][0]["error"])

	def test_alt_area_that_is_off_is_refused(self):
		frappe.db.set_value("Life Area", self.money, "is_on", 0)
		try:
			_, res = self.submit(alt_area=self.money)
		finally:
			frappe.db.set_value("Life Area", self.money, "is_on", 1)
		self.assertEqual(res["created"], [])
		self.assertIn("switched off", res["errors"][0]["error"])

	def test_alt_area_needs_an_area(self):
		created = inbox.create_item(title="i17 no area", space=PRIVATE, raw_text="x")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		res = inbox.submit_result(item=created["name"], proposals=[{"kind": "Event", "payload": {"subject": "i17", "starts_on": "2026-12-01 10:00:00"}, "alt_area": self.tea}])
		self.assertEqual(res["created"], [])

	def test_the_schema_names_both_fields(self):
		for kind, s in meta.proposal_schema().items():
			self.assertEqual(set(s["beside_payload"]), {"reason", "alt_area"}, kind)

	# ---- the screen's server part ----
	def test_rows_carry_the_best_guess_reason_and_both_areas(self):
		_, a = self.waiting("i17 voice note", self.personal, reason="Sounds like a task, but no date", hours_ago=3)
		_, b = self.waiting("i17 Q3 numbers", self.tea, alt=self.money, reason="Mentions both", hours_ago=2)
		_, c = self.waiting("i17 plain", self.money, hours_ago=1)
		out = brain.needs_you(PRIVATE)
		self.assertEqual([r["proposal"] for r in out["rows"]], [a.name, b.name, c.name])
		self.assertEqual(out["total"], 3)
		rows = {r["proposal"]: r for r in out["rows"]}
		self.assertEqual(rows[b.name]["alt_area"], self.money)
		self.assertEqual(rows[b.name]["alt_area_name"], "Money")
		self.assertEqual((rows[a.name]["area_name"], rows[a.name]["reason"], rows[a.name]["kind_label"]), ("Personal", "Sounds like a task, but no date", "Task"))
		self.assertIsNone(rows[c.name]["reason"])
		self.assertIsNone(rows[c.name]["alt_area"])
		self.assertEqual(out["minutes"], 1)

	def test_a_reading_is_read_later(self):
		goal = self.make("Life Goal", title="i17 yield", goal_type="Open", area=self.tea)
		_, p = self.waiting("i17 newsletter", kind="Reading", goal=goal.name)
		row = next(r for r in brain.needs_you(PRIVATE)["rows"] if r["proposal"] == p.name)
		self.assertEqual(row["kind_label"], "Read later")
		self.assertFalse(row["takes_area"])

	def test_seven_rows_at_most_and_the_rest_come_in(self):
		made = [self.waiting(f"i17 many {i}", self.tea, hours_ago=20 - i)[1] for i in range(9)]
		out = brain.needs_you(PRIVATE)
		self.assertEqual((len(out["rows"]), out["total"]), (7, 9))
		self.assertEqual([r["proposal"] for r in out["rows"]], [p.name for p in made[:7]])
		review.decide(made[0].name, "reject")
		after = brain.needs_you(PRIVATE)
		self.assertEqual((len(after["rows"]), after["total"]), (7, 8))
		self.assertEqual(after["rows"][-1]["proposal"], made[7].name)

	def test_a_task_with_no_area_is_unfiled(self):
		_, p = self.waiting("i17 nowhere")
		row = brain.needs_you(PRIVATE)["rows"][0]
		self.assertEqual(row["proposal"], p.name)
		self.assertTrue(row["unfiled"])

	def test_failed_captures_are_listed_never_lost(self):
		item = frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": "i17 broken", "source_type": "Upload", "status": "Failed", "error": "Could not read the file"}).insert()
		out = brain.needs_you(PRIVATE)
		self.assertEqual([(u["item"], u["reason"]) for u in out["unfiled"]], [(item.name, "Could not read the file")])

	def test_the_two_numbers_are_the_captures_of_the_last_24_hours(self):
		frappe.db.sql("update `tabLife Inbox Item` set is_archived=0")  # nothing else matters: only this test's captures are counted below
		frappe.db.sql("update `tabLife Inbox Item` set is_archived=1 where space=%s", (PRIVATE,))
		goal = self.make("Life Goal", title="i17 goal", goal_type="Open", area=self.tea)
		mk = lambda title, source, status, hours, **kw: frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": title, "source_type": source,
			"status": status, "received_on": add_to_date(now_datetime(), hours=-hours), **kw}).insert()
		mk("i17 own 1", "Email", "Done", 2, area=self.tea, goal=goal.name)
		mk("i17 own 2", "Chat", "Done", 5, area=self.money)
		mk("i17 old", "Email", "Done", 30, area=self.tea)
		decided = mk("i17 decided", "Voice Note", "Done", 3, area=self.tea)
		frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": decided.name, "kind": "Note", "preview": "x", "payload": "{}", "status": "Pending"}).insert()
		frappe.db.set_value("Life Proposal", {"inbox_item": decided.name}, "status", "Rejected")
		out = brain.needs_you(PRIVATE)
		self.assertEqual(out["came_in"], {"count": 3, "sources": 3})
		self.assertEqual(out["filed"], {"count": 2, "areas": 2, "goals": 1})

	def test_keep_and_drop_use_the_existing_decisions(self):
		item, keep = self.waiting("i17 keep me", self.tea)
		_, drop = self.waiting("i17 drop me", self.tea)
		res = review.decide(keep.name, "accept")
		self.assertEqual(frappe.db.get_value("Life Task", res["created_name"], "area"), self.tea)
		review.decide(drop.name, "reject")
		self.assertEqual(brain.needs_you(PRIVATE)["total"], 0)

	def test_picking_the_second_area_files_it_there(self):
		_, p = self.waiting("i17 torn", self.tea, alt=self.money, reason="Mentions both")
		row = brain.needs_you(PRIVATE)["rows"][0]
		res = review.decide(p.name, "accept", {**row["payload"], "area": row["alt_area"]})
		self.assertEqual(frappe.db.get_value("Life Task", res["created_name"], "area"), self.money)

	def test_a_family_member_sees_only_their_spaces(self):
		self.waiting("i17 private", self.tea)
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			brain.needs_you(PRIVATE)

	def test_a_dropped_capture_is_discarded_in_the_outbox(self):
		item, p = self.waiting("i17 discard me", self.tea)
		review.decide(p.name, "reject")
		self.assertEqual(frappe.db.get_value("Life Exit", {"record_doctype": "Life Inbox Item", "record_name": item.name, "reversed": 0}, "pile"), "Discarded")
