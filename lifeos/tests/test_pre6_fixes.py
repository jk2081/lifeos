"""Pre-step 6: the fixes made while bringing Life OS up to Frappe's conventions."""
import os
from unittest.mock import patch

import frappe

from lifeos import permissions
from lifeos.ai import fake
from lifeos.api import ask, chats, connections
from lifeos.tests.base import FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase
from lifeos.tests.test_ux5_ask import AskCase, text

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestAskCommitsOnce(AskCase):
	def test_progress_comes_from_the_cache_and_ends_done(self):
		self.script({"content": [text("Nothing open on drainage.")], "stop_reason": "end_turn"})
		res = ask.ask("What about drainage?", space=PRIVATE, client_id="pre6-progress")
		got = ask.progress("pre6-progress")
		self.assertEqual((got["status"], got["text"], got["message"]), ("Done", "Nothing open on drainage.", res["message"]["name"]))

	def test_an_unexpected_failure_is_an_error_answer_not_a_working_message(self):
		def boom(_payload):
			raise RuntimeError("the model client broke")

		self.script(boom)
		res = ask.ask("What about drainage?", space=PRIVATE, client_id="pre6-boom")
		self.assertEqual(res["error"], "ai")
		self.assertEqual(frappe.db.get_value("Life Ask Message", res["message"]["name"], "status"), "Error")
		self.assertEqual(ask.progress("pre6-boom")["status"], "Error")
		self.assertNotIn("the model client broke", res["error_text"])


class TestChatImportSavepoints(LifeTestCase):
	def test_a_failed_conversation_is_undone_alone(self):
		from frappe.utils.file_manager import save_file

		real, calls = chats.log, []

		def log_failing_second(**kw):
			calls.append(kw["external_id"])
			if len(calls) == 2:
				real(**kw)  # written, then the failure must take it back
				raise frappe.ValidationError("this conversation fails")
			return real(**kw)

		with open(os.path.join(FIXTURES, "claude_export.zip"), "rb") as fh:
			f = save_file("claude_export.zip", fh.read(), None, None, is_private=1)
		frappe.flags.lifeos_import_now = True
		try:
			with patch.object(chats, "log", side_effect=log_failing_second):
				connections.start_import(space=PRIVATE, system="claude", file_url=f.file_url)
		finally:
			frappe.flags.lifeos_import_now = False
		frappe.set_user(OWNER)
		permissions.clear_cache()
		st = connections.import_status(PRIVATE, "claude")
		self.assertEqual((st["status"], st["created"], st["skipped"]), ("Done", 1, 2), st)
		self.assertTrue(frappe.db.exists("Life Chat Log", {"space": PRIVATE, "external_id": calls[0]}))
		self.assertFalse(frappe.db.exists("Life Chat Log", {"space": PRIVATE, "external_id": calls[1]}))


class TestNoUserSwitching(AskCase):
	def _chat(self):
		from frappe.utils import today

		return self.make("Life Chat Log", title="pre6 Mithun blend sheets", date=today(), summary_md="I will send six questions to Mithun.",
			area=self.areas["Tea"])

	def _answer_citing_everything(self, seen):
		import json

		def answer(params):
			data = json.loads(params["messages"][-1]["content"])
			seen.extend(r["title"] for r in data["records"])
			refs = [r["ref"] for r in data["records"]] or ["R1"]
			return {"content": [text(json.dumps({"candidates": [{"kind": "Theme", "title": "pre6 theme", "evidence": refs}]}))],
				"stop_reason": "end_turn"}

		return answer

	def test_an_insight_for_a_user_never_holds_a_record_they_cannot_read(self):
		from lifeos import insights

		self._chat()
		frappe.db.delete("Life Insight", {"space": PRIVATE})
		seen = []
		self.script(self._answer_citing_everything(seen))
		frappe.set_user("Administrator")
		stats = insights.run(PRIVATE, ai=True, user=FAMILY)  # the family member is not in the Private space
		self.assertEqual(seen, [], "the model was sent records the user cannot read")
		self.assertEqual(stats["created"], 0)
		self.assertFalse(frappe.db.exists("Life Insight", {"space": PRIVATE}))
		self.assertEqual(frappe.session.user, "Administrator")

	def test_the_nightly_job_runs_for_the_owner_without_switching(self):
		from lifeos import insights

		self._chat()
		frappe.db.delete("Life Insight", {"space": PRIVATE})
		seen = []
		self.script(self._answer_citing_everything(seen))
		frappe.db.set_value("Life Space", SHARED, "ask_enabled", 0)
		frappe.set_user("Administrator")
		insights.run_nightly()
		self.assertEqual(frappe.session.user, "Administrator")
		self.assertIn("pre6 Mithun blend sheets", seen)
		self.assertTrue(frappe.db.exists("Life Insight", {"space": PRIVATE, "title": "pre6 theme"}))
		self.assertEqual(frappe.db.get_value("Life AI Usage", {"purpose": "Insights"}, "user"),
			frappe.db.get_value("Life Space", PRIVATE, "owner_user"))


class TestChatImportUser(LifeTestCase):
	def _file(self):
		from frappe.utils.file_manager import save_file

		with open(os.path.join(FIXTURES, "claude_export.zip"), "rb") as fh:
			return save_file("claude_export.zip", fh.read(), None, None, is_private=1).file_url

	def test_the_job_runs_only_as_the_person_who_started_it(self):
		from lifeos import chat_import

		url = self._file()
		frappe.set_user(OWNER)
		self.assertRaises(frappe.PermissionError, chat_import.run, PRIVATE, "claude", url, FAMILY)

	def test_an_import_never_writes_where_its_user_cannot(self):
		from lifeos import chat_import

		url = self._file()
		frappe.set_user(FAMILY)
		permissions.clear_cache()
		chat_import.run(PRIVATE, "claude", url, FAMILY)
		self.assertFalse(frappe.db.exists("Life Chat Log", {"space": PRIVATE, "source_system": "claude"}))
		self.assertEqual(chat_import.progress(PRIVATE, "claude")["created"], 0)
