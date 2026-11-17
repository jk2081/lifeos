"""Pre-step 6: the fixes made while bringing Life OS up to Frappe's conventions."""
import os
from unittest.mock import patch

import frappe

from lifeos import permissions
from lifeos.ai import fake
from lifeos.api import ask, chats, connections
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase
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
