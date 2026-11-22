"""Set 7, step 4: Inbox items left too long. The rule in all three modes, the rules without a key, Confirm selected and its
Undo, Today's line and its Undo, what is never touched, and Reset's batch."""
import json

import frappe
from frappe.utils import add_days, now_datetime, today

from lifeos import old_inbox
from lifeos.api import inbox, old_items, reset, settings
from lifeos.api import today as today_api
from lifeos.tests.base import AGENT, OWNER, PRIVATE, LifeTestCase
from lifeos.tests.test_ux5_ask import set_key


class OldCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		set_key("")
		frappe.set_user(OWNER)
		self.mode("Suggest", 7)
		# earlier items of this space are out of the way: only what each test makes is old
		frappe.db.sql("update `tabLife Inbox Item` set received_on = now() where space=%s", PRIVATE)

	def mode(self, mode, days):
		settings.save({"old_inbox_mode": mode, "old_inbox_days": days})
		frappe.clear_document_cache("Life Settings", "Life Settings")

	def old_item(self, title, kinds=(), age=10, status="To Review"):
		made = inbox.create_item(space=PRIVATE, title=title, source_type="Message", raw_text="x")
		if kinds or status == "To Review":
			frappe.db.set_value("Life Inbox Item", made["name"], {"status": "Processing", "claimed_by": AGENT, "claimed_on": now_datetime()})
			self.as_user(AGENT)
			inbox.submit_result(made["name"], summary_md="s", proposals=[
				{"kind": k, "preview": f"{title} {k} {i}", "payload": {"title": f"{title} {k} {i}", "area": "Tea"} if k != "Event" else
					{"subject": f"{title} {i}", "starts_on": f"{add_days(today(), 3)} 10:00:00"}} for i, k in enumerate(kinds)])
			self.as_user(OWNER)
		frappe.db.set_value("Life Inbox Item", made["name"], "received_on", add_days(now_datetime(), -age), update_modified=False)
		return made["name"]

	def exits(self, name):
		return frappe.get_all("Life Exit", filters={"record_name": name, "reversed": 0}, pluck="pile")


class TestSuggest(OldCase):
	def test_without_a_key_nothing_is_suggested_and_the_items_wait(self):
		"""Issue 59: no rule decides for the owner; with no key the old items stay in Needs you, and nothing breaks."""
		task = self.old_item("ux7 old tasks", ["Task", "Note"])
		note = self.old_item("ux7 old notes", ["Note"])
		out = old_inbox.run_for_space(PRIVATE)
		self.assertEqual(out, {"mode": "Suggest", "suggested": 0})
		for n in (task, note):
			got = frappe.db.get_value("Life Inbox Item", n, ["status", "suggested_decision", "suggested_on"])
			self.assertEqual((got[0], got[1] or None, got[2]), ("To Review", None, None))
		listed = old_items.suggested(space=PRIVATE)
		self.assertEqual((listed["total"], listed["rows"]), (0, []))
		self.assertFalse([b for b in reset.rule_batches(PRIVATE) if b["key"] == "inbox_decisions"])

	def test_the_skill_decides_for_the_items_it_can_and_says_who_suggested(self):
		from lifeos.ai import fake

		set_key("sk-test-not-real")
		frappe.set_user(OWNER)
		task, note, empty, fresh = (self.old_item("ux7 s old tasks", ["Task"]), self.old_item("ux7 s old notes", ["Note"]),
			self.old_item("ux7 s old empty", status="New"), self.old_item("ux7 s fresh", ["Task"], age=2))
		words = {"decisions": []}

		def answer(params):
			ids = fake.asked(params)[1]["items"]
			by_title = {i["title"]: i["item"] for i in ids}
			words["decisions"] = [{"item": by_title["ux7 s old tasks"], "decision": "keep", "reason": "A task with a date."},
				{"item": by_title["ux7 s old notes"], "decision": "park", "reason": "Only notes."}]  # the empty one is left out
			return {"content": [{"type": "text", "text": json.dumps(words)}]}

		frappe.flags.lifeos_ai_backend = fake.ScriptedFake([answer])
		try:
			out = old_inbox.run_for_space(PRIVATE)
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key("")
		self.assertEqual(out, {"mode": "Suggest", "suggested": 2})
		got = {n: frappe.db.get_value("Life Inbox Item", n, ["suggested_decision", "suggested_by", "suggested_on"]) for n in (task, note, empty, fresh)}
		self.assertEqual(got[task][:2], ("Accept", "tidy-backlog v1"))
		self.assertEqual(got[note][:2], ("Park", "tidy-backlog v1"))
		self.assertFalse(got[empty][0])  # left out: it waits for the owner, and is not asked about again
		self.assertTrue(got[empty][2])
		self.assertFalse(got[fresh][2])  # not old yet
		listed = old_items.suggested(space=PRIVATE)
		self.assertEqual({r["name"]: r["by"] for r in listed["rows"] if r["name"] in (task, note, empty)}, {task: "tidy-backlog v1", note: "tidy-backlog v1"})
		batch = next(b for b in reset.rule_batches(PRIVATE) if b["key"] == "inbox_decisions")
		self.assertEqual(batch["count"], listed["total"])
		self.assertEqual(batch["review"], {"path": "/inbox", "query": {"decisions": "1"}})

	def test_with_the_assistant(self):
		from lifeos.ai import fake

		set_key("sk-test-not-real")
		frappe.set_user(OWNER)
		item = self.old_item("ux7 old ai", ["Task"])
		frappe.flags.lifeos_ai_backend = fake.ScriptedFake([{"content": [{"type": "text", "text": '{"decisions": [{"item": "I1", "decision": "park", "reason": "Can wait."}]}'}]}])
		try:
			got, label = old_inbox.suggest(PRIVATE, [i for i in old_inbox.candidates(PRIVATE, 7) if i.name == item])
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key("")
		self.assertEqual(got[item], ("Park", "Can wait."))
		self.assertEqual(label, "tidy-backlog v1")

	def test_confirm_and_undo_each_decision(self):
		acc = self.old_item("ux7 confirm accept", ["Task"])
		park = self.old_item("ux7 confirm park", ["Note"])
		gone = self.old_item("ux7 confirm discard", status="New")
		res = old_items.apply([{"item": acc, "decision": "Accept"}, {"item": park, "decision": "Park"}, {"item": gone, "decision": "Discard"}])
		self.assertEqual(res["done"], 3)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", acc, "status"), "Done")
		self.assertEqual(self.exits(acc), ["Done"])
		self.assertEqual(self.exits(park), ["Parked"])
		self.assertTrue(frappe.db.exists("Life Note", {"inbox_item": park, "is_someday": 1}))
		self.assertFalse(frappe.db.exists("Life Inbox Item", gone))
		self.assertEqual(self.exits(gone), ["Discarded"])
		old_items.undo(res["undo"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", acc, "status"), "To Review")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", park, "status"), "To Review")
		self.assertFalse(frappe.db.exists("Life Note", {"inbox_item": park}))
		self.assertEqual(frappe.db.count("Life Proposal", {"inbox_item": park, "status": "Pending"}), 1)
		self.assertTrue(frappe.db.exists("Life Inbox Item", gone))
		self.assertEqual([self.exits(n) for n in (acc, park, gone)], [[], [], []])
		self.assertEqual(frappe.db.count("Life Exit", {"record_doctype": "Life Note", "reversed": 0, "title": "ux7 confirm park"}), 0)


class TestParkAndDiscard(OldCase):
	def test_park_mode_acts_and_today_undo_restores(self):
		self.mode("Park", 14)
		item = self.old_item("ux7 auto park", ["Note"], age=20)
		young = self.old_item("ux7 auto young", ["Note"], age=10)
		out = old_inbox.run_for_space(PRIVATE, OWNER)
		self.assertGreaterEqual(out["parked"], 1)
		self.assertEqual(self.exits(item), ["Parked"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", young, "status"), "To Review")
		line = today_api.get(space=PRIVATE)["auto_inbox"]
		self.assertGreaterEqual(line["parked"], 1)
		self.assertIn(item, line["items"])
		self.assertEqual(frappe.db.get_value("Life Exit", {"record_name": item}, "auto_rule"), "old_inbox")
		old_items.undo_auto(space=PRIVATE)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item, "status"), "To Review")
		self.assertEqual(self.exits(item), [])
		self.assertIsNone(today_api.get(space=PRIVATE)["auto_inbox"])

	def test_discard_mode_acts_and_undo_restores(self):
		self.mode("Discard", 14)
		item = self.old_item("ux7 auto discard", ["Task"], age=20)
		old_inbox.run_for_space(PRIVATE, OWNER)
		self.assertFalse(frappe.db.exists("Life Inbox Item", item))
		self.assertEqual(frappe.get_all("Life Exit", filters={"record_name": item, "reversed": 0}, fields=["pile", "auto_rule"])[0],
			{"pile": "Discarded", "auto_rule": "old_inbox"})
		self.assertIn(item, today_api.get(space=PRIVATE)["auto_inbox"]["items"])
		old_items.undo_auto(space=PRIVATE)
		self.assertTrue(frappe.db.exists("Life Inbox Item", item))
		self.assertEqual(self.exits(item), [])

	def test_processing_and_failed_items_are_never_touched(self):
		self.mode("Discard", 14)
		made = inbox.create_item(space=PRIVATE, title="ux7 processing", source_type="Message", raw_text="x")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		self.as_user(OWNER)
		failed = inbox.create_item(space=PRIVATE, title="ux7 failed", source_type="Message", raw_text="x")
		frappe.db.set_value("Life Inbox Item", failed["name"], "status", "Failed")
		for n in (made["name"], failed["name"]):
			frappe.db.set_value("Life Inbox Item", n, "received_on", add_days(now_datetime(), -40), update_modified=False)
		old_inbox.run_for_space(PRIVATE, OWNER)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", made["name"], "status"), "Processing")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", failed["name"], "status"), "Failed")

	def test_agents_cannot(self):
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, old_items.suggested, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, old_items.apply, [])
		self.assertRaises(frappe.PermissionError, old_items.undo_auto, space=PRIVATE)

	def test_setting_is_checked(self):
		self.assertRaises(frappe.ValidationError, settings.save, {"old_inbox_mode": "Burn"})
		self.assertRaises(frappe.ValidationError, settings.save, {"old_inbox_days": 0})
