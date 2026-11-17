"""Pre-step 6: the fixes made while bringing Life OS up to Frappe's conventions."""
import os
from unittest.mock import patch

import frappe

from lifeos import permissions
from lifeos.ai import fake
from lifeos.api import ask, chats, connections
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase
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


class TestFilePaths(LifeTestCase):
	def _file(self, url, name="x.png"):
		return frappe.get_doc({"doctype": "File", "file_url": url, "file_name": name, "is_private": 1})

	def test_a_dot_dot_path_reads_nothing(self):
		from lifeos import files

		for url in ("/private/files/../../site_config.json", "/files/../../../common_site_config.json"):
			self.assertRaises((frappe.PermissionError, frappe.ValidationError), files.read, self._file(url, "site_config.json"))

	def test_a_link_out_of_the_files_folder_reads_nothing(self):
		from lifeos import files, sources

		link = frappe.get_site_path("private", "files", "pre6-link.png")
		if os.path.lexists(link):
			os.remove(link)
		os.symlink(os.path.realpath(frappe.get_site_path("site_config.json")), link)
		try:
			doc = self._file("/private/files/pre6-link.png", "pre6-link.png")
			self.assertRaises(frappe.PermissionError, files.read, doc)
			self.assertRaises(frappe.PermissionError, sources.make_thumbnail, doc)
		finally:
			os.remove(link)

	def test_a_real_file_is_read(self):
		from frappe.utils.file_manager import save_file

		from lifeos import files

		f = save_file("pre6.txt", b"hello", None, None, is_private=1)
		self.assertEqual(files.read(f), b"hello")


class TestPermissionHooksAnswerTrueOrFalse(LifeTestCase):
	"""Frappe reads None from a has_permission hook as a refusal, so every hook answers True or False on every path."""

	USERS = ("Administrator", OWNER, FAMILY, AGENT)
	PTYPES = ("read", "write", "create", "delete", "select")

	def _doc(self, values):
		return frappe.get_doc(values)

	def _all(self, hook, doc):
		out = {}
		for user in self.USERS:
			for ptype in self.PTYPES:
				permissions.clear_cache()
				got = hook(doc, ptype=ptype, user=user)
				self.assertIn(got, (True, False), f"{hook.__name__} answered {got!r} for {user} {ptype}")
				self.assertIsInstance(got, bool, f"{hook.__name__} for {user} {ptype}")
				out[(user, ptype)] = got
		return out

	def test_space_records(self):
		h = permissions.has_permission
		private = self._all(h, self._doc({"doctype": "Life Task", "space": PRIVATE, "title": "pre6"}))
		self.assertTrue(private[(OWNER, "write")])
		self.assertFalse(private[(FAMILY, "read")])
		self.assertFalse(private[(AGENT, "delete")])
		self.assertTrue(private[(AGENT, "read")])
		no_space = self._all(h, self._doc({"doctype": "Life Task", "title": "pre6"}))
		self.assertTrue(no_space[(FAMILY, "create")])
		vault = self._all(h, self._doc({"doctype": "Life Vault Document", "space": PRIVATE, "title": "pre6"}))
		self.assertEqual(vault[(AGENT, "read")], PRIVATE in permissions.vault_open_spaces())
		insight = self._all(h, self._doc({"doctype": "Life Insight", "space": PRIVATE, "title": "pre6"}))
		self.assertFalse(insight[(AGENT, "read")])

	def test_spaces(self):
		got = self._all(permissions.space_has_permission, self._doc({"doctype": "Life Space", "name": PRIVATE, "space_name": PRIVATE}))
		self.assertTrue(got[(OWNER, "write")])  # a Life Admin
		self.assertTrue(got[(AGENT, "read")])
		self.assertFalse(got[(AGENT, "write")])
		self.assertFalse(got[(FAMILY, "read")])

	def test_events(self):
		got = self._all(permissions.event_has_permission, self._doc({"doctype": "Event", "subject": "pre6", "life_space": PRIVATE}))
		self.assertTrue(got[(OWNER, "delete")])
		self.assertFalse(got[(AGENT, "delete")])
		self.assertFalse(got[(FAMILY, "read")])
		free = self._all(permissions.event_has_permission, self._doc({"doctype": "Event", "subject": "pre6"}))
		self.assertTrue(free[(FAMILY, "read")])

	def test_view_states(self):
		got = self._all(permissions.view_state_has_permission, self._doc({"doctype": "Life View State", "user": OWNER}))
		self.assertTrue(got[(OWNER, "write")])
		self.assertFalse(got[(FAMILY, "read")])
		self.assertFalse(got[(AGENT, "read")])

	def test_ask(self):
		thread = self._doc({"doctype": "Life Ask Thread", "user": OWNER, "space": PRIVATE})
		got = self._all(permissions.ask_has_permission, thread)
		self.assertTrue(got[(OWNER, "read")])
		self.assertFalse(got[(FAMILY, "read")])
		self.assertFalse(got[(AGENT, "read")])
		message = self._all(permissions.ask_has_permission, self._doc({"doctype": "Life Ask Message", "thread": "no-such-thread"}))
		self.assertTrue(message[(FAMILY, "read")])  # no thread, no owner to protect

	def test_files(self):
		vault = self.make("Life Vault Document", title="pre6 permit")
		got = self._all(permissions.file_has_permission, self._doc({"doctype": "File", "file_name": "p.pdf",
			"attached_to_doctype": "Life Vault Document", "attached_to_name": vault.name}))
		self.assertTrue(got[(FAMILY, "read")])  # the space rules apply elsewhere; this hook only closes the Vault to agents
		self.assertEqual(got[(AGENT, "read")], PRIVATE in permissions.vault_open_spaces())
		other = self._all(permissions.file_has_permission, self._doc({"doctype": "File", "file_name": "n.txt"}))
		self.assertTrue(other[(AGENT, "read")])

	def test_app(self):
		for user in self.USERS:
			frappe.set_user(user)
			self.assertIs(permissions.has_app_permission(), True)
		frappe.set_user("Guest")
		self.assertIs(permissions.has_app_permission(), False)


class TestAuditFixes(LifeTestCase):
	"""The findings of the pre-step 6 audit that were High (and the trash, of the same kind as the inbox list)."""

	def setUp(self):
		super().setUp()
		frappe.db.sql("update `tabLife Inbox Item` set status='Done' where space in %s and status in ('New', 'Processing')", ((PRIVATE, SHARED),))

	def _accepted_task(self, title="pre6 accepted"):
		from lifeos.api import inbox, review

		item = inbox.create_item(space=PRIVATE, title=f"{title} item", source_type="Message")
		self.as_user(AGENT)
		claimed = inbox.claim_next(space=PRIVATE)
		self.assertEqual(claimed["name"], item["name"])
		out = inbox.submit_result(claimed["name"], transcript_md="t", summary_md="s",
			proposals=[{"kind": "Task", "payload": {"title": title, "area": "Tea"}}])
		self.as_user(OWNER)
		prop = out["created"][0]["name"]
		res = review.decide(prop, "accept")
		return item["name"], prop, res["created_name"]

	def test_undo_takes_only_a_proposal_this_user_may_change(self):
		from lifeos.api import reset

		item, prop, task = self._accepted_task()
		self.as_user(FAMILY)  # only in the Shared space
		self.assertRaises(frappe.PermissionError, reset.undo, [{"op": "unaccept", "proposal": prop, "item": item}])
		self.assertRaises(frappe.ValidationError, reset.undo, [{"op": "unaccept", "proposal": {"name": ["like", "%"]}}])
		self.assertEqual(frappe.db.get_value("Life Proposal", prop, "status"), "Accepted")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item, "status"), "Done")
		self.as_user(OWNER)  # the owner's undo still works, and the index follows the item
		reset.undo([{"op": "unaccept", "proposal": prop, "item": "ignored", "doctype": "Life Task", "name": "ignored"}])
		self.assertEqual(frappe.db.get_value("Life Proposal", prop, "status"), "Pending")
		self.assertFalse(frappe.db.exists("Life Task", task))
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_doctype": "Life Inbox Item", "ref_name": item}, "status"), "To Review")

	def test_a_task_made_from_a_proposal_can_be_deleted(self):
		from lifeos.api import trash

		_item, prop, task = self._accepted_task("pre6 delete me")
		trash.delete("Life Task", task)
		self.assertFalse(frappe.db.exists("Life Task", task))
		self.assertTrue(frappe.db.exists("Life Proposal", prop))
		self.assertIsNone(frappe.db.get_value("Life Proposal", prop, "created_name"))

	def test_a_goal_an_idea_is_filed_under_still_cannot_be_deleted(self):
		from lifeos.api import trash

		goal = self.make("Life Goal", title="pre6 goal with an idea", goal_type="Open", area=self.areas["Tea"])
		self.make("Life Idea", title="pre6 idea", goal=goal.name)
		self.assertRaises(frappe.ValidationError, trash.delete, "Life Goal", goal.name)
		self.assertTrue(frappe.db.exists("Life Goal", goal.name))

	def _vault_source(self):
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		permissions.clear_cache()
		doc = self.make("Life Vault Document", title="pre6 passport", doc_type="ID")
		item = self.make("Life Inbox Item", title="pre6 passport scan", source_type="Upload", transcript_md="pre6 SECRET")
		frappe.db.set_value("Life Inbox Item", item.name, "vault_document", doc.name)
		return doc, item

	def test_an_agent_never_lists_the_source_of_a_closed_vault(self):
		from lifeos.api import inbox

		_doc, item = self._vault_source()
		self.as_user(OWNER)
		self.assertIn(item.name, [r.name for r in inbox.list(space=PRIVATE, include_archived=1, page_length=100)["items"]])
		self.as_user(AGENT)
		got = inbox.list(space=PRIVATE, include_archived=1, page_length=100)
		self.assertNotIn(item.name, [r.name for r in got["items"]])
		summary = inbox.list(space=PRIVATE, include_archived=1, summary={"fields": ["transcript_md"]})["summary"]
		self.assertNotIn("pre6 SECRET", [r["transcript_md"] for r in summary["rows"]])

	def test_an_agent_never_sees_a_deleted_vault_document_in_the_trash(self):
		from lifeos.api import trash

		doc, item = self._vault_source()
		self.as_user(OWNER)
		trash.delete("Life Inbox Item", item.name)  # the source refers to the document, so it goes first
		trash.delete("Life Vault Document", doc.name)
		self.assertTrue({doc.name, item.name} <= {r["record"] for r in trash.list(space=PRIVATE)["rows"]})
		self.as_user(AGENT)
		self.assertFalse({doc.name, item.name} & {r["record"] for r in trash.list(space=PRIVATE)["rows"]})


class TestReviewFixes(LifeTestCase):
	def test_task_counts_match_the_task_list(self):
		from lifeos.api import tasks

		self.make("Life Task", title="pre6 count due", area=self.areas["Tea"], due_date=frappe.utils.today())
		self.make("Life Task", title="pre6 count waiting", area=self.areas["Tea"], status="Waiting", waiting_on="Mr Rao")
		for args in ({"status": "all"}, {"status": "all", "due": "today,overdue"}, {"status": "open"},
				{"status": "all", "filters": '[["title", "like", "pre6 count%"]]'}):
			self.assertEqual(tasks.total(PRIVATE, **args), tasks.list(space=PRIVATE, page_length=1, **args)["total"], args)

	def test_the_graph_keeps_a_closed_vault_off_an_agents_graph(self):
		from lifeos.api import graph

		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		permissions.clear_cache()
		doc = self.make("Life Vault Document", title="pre6 graph passport", doc_type="ID")
		task = self.make("Life Task", title="pre6 graph task", area=self.areas["Tea"])
		frappe.get_doc({"doctype": "Life Link", "space": PRIVATE, "from_doctype": "Life Task", "from_name": task.name,
			"to_doctype": "Life Vault Document", "to_name": doc.name, "link_text": "pre6"}).insert(ignore_permissions=True)
		ids = {n["id"] for n in graph.get(space=PRIVATE)["nodes"]}
		self.assertIn(f"Life Vault Document/{doc.name}", ids)
		self.as_user(AGENT)
		got = graph.get(space=PRIVATE)
		self.assertNotIn(f"Life Vault Document/{doc.name}", {n["id"] for n in got["nodes"]})
		self.assertNotIn("pre6 graph passport", [n["label"] for n in got["nodes"]])
		centred = graph.get(space=PRIVATE, center=f"Life Vault Document/{doc.name}")
		self.assertNotIn("pre6 graph passport", [n["label"] for n in centred["nodes"]])
