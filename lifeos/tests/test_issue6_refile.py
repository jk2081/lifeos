"""Issue 6: filing again with the same external_id updates the intent, instruction, title, area and goal."""
import frappe
from frappe.utils import add_to_date, now_datetime

from lifeos import permissions
from lifeos.api import inbox
from lifeos.tests.base import AGENT, OWNER, PRIVATE, SHARED, LifeTestCase


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
