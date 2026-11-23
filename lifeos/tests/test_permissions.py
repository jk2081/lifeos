"""Tests for permissions."""
import ast
import importlib.util
import inspect
import json
import os
import pathlib
from pathlib import Path
import re
import types
from unittest.mock import patch

import frappe
from frappe.modules.patch_handler import get_patches_from_app
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime, today

from lifeos import counts, devtools, gone_names, install, permissions, proposals
from lifeos.ai import fake
from lifeos.api import archive, ask, chats, client_errors, connections, goals, graph, inbox, library, search, session, settings, someday, sources, tasks, timeline, today as today_api, vault
from lifeos.api.utils import in_area
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import answer, AskCase, item, task, text


class TestSpacePermissions(LifeTestCase):
	def setUp(self):
		super().setUp()
		self.private_note = self.make("Life Note", title="Private note about tea", content_md="secret garden")
		self.shared_note = self.make("Life Note", space=SHARED, title="Shared shopping note")

	def test_member_can_list_and_read(self):
		names = frappe.get_list("Life Note", pluck="name", limit=0)
		self.assertIn(self.private_note.name, names)
		self.assertIn(self.shared_note.name, names)

	def test_outsider_cannot_list(self):
		self.as_user(FAMILY)
		names = frappe.get_list("Life Note", pluck="name", limit=0)
		self.assertNotIn(self.private_note.name, names)
		self.assertIn(self.shared_note.name, names)
		self.assertNotIn(PRIVATE, frappe.get_list("Life Space", pluck="name", limit=0))
		self.assertEqual(frappe.get_list("Life Area", filters={"space": PRIVATE}, pluck="name"), [])
		self.assertEqual(frappe.get_list("Life Index", filters={"space": PRIVATE}, pluck="name"), [])

	def test_outsider_cannot_read(self):
		self.as_user(FAMILY)
		doc = frappe.get_doc("Life Note", self.private_note.name)
		self.assertFalse(doc.has_permission("read"))
		self.assertRaises(frappe.PermissionError, doc.check_permission, "read")
		self.assertRaises(frappe.PermissionError, permissions.get_doc_checked, "Life Note", self.private_note.name)
		self.assertRaises(frappe.PermissionError, frappe.client.get, "Life Note", self.private_note.name)

	def test_outsider_cannot_write_or_create(self):
		self.as_user(FAMILY)
		doc = frappe.get_doc("Life Note", self.private_note.name)
		doc.title = "Taken over"
		self.assertRaises(frappe.PermissionError, doc.save)
		new = frappe.get_doc({"doctype": "Life Note", "space": PRIVATE, "title": "Sneaked in"})
		self.assertRaises(frappe.PermissionError, new.insert)
		self.assertRaises(frappe.PermissionError, permissions.require_space, PRIVATE)

	def test_outsider_cannot_delete(self):
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Life Note", self.private_note.name)

	def test_read_only_member_cannot_write(self):
		frappe.set_user("Administrator")
		space = frappe.get_doc("Life Space", SHARED)
		for m in space.members:
			if m.user == FAMILY:
				m.access = "Read"
		space.save()
		try:
			self.as_user(FAMILY)
			doc = frappe.get_doc("Life Note", self.shared_note.name)
			self.assertTrue(doc.has_permission("read"))
			doc.title = "Changed"
			self.assertRaises(frappe.PermissionError, doc.save)
			self.assertRaises(frappe.PermissionError, permissions.require_space, SHARED, True)
		finally:
			frappe.set_user("Administrator")
			space.reload()
			for m in space.members:
				if m.user == FAMILY:
					m.access = "Write"
			space.save()

	def test_record_cannot_move_space(self):
		self.private_note.space = SHARED
		self.assertRaises(frappe.ValidationError, self.private_note.save)

	def test_user_without_spaces_sees_nothing(self):
		from lifeos import devtools

		devtools.make_user("stranger@lifeos.test", "Stranger", ["Life User"])
		self.as_user("stranger@lifeos.test")
		self.assertEqual(frappe.get_list("Life Note", pluck="name"), [])
		self.assertEqual(frappe.get_list("Life Space", pluck="name"), [])


class TestAgentLimits(LifeTestCase):
	def test_agent_can_create_and_edit(self):
		self.as_user(AGENT)
		task = self.make("Life Task", title="Filed by Hermes")
		self.assertEqual(task.owner, AGENT)
		task.notes_md = "more"
		task.save()
		# UX fixes, set 4: notes are the exception. Agents write wiki pages through lifeos.api.wiki and only propose notes
		self.assertRaises(frappe.PermissionError, self.make, "Life Note", title="Filed by Hermes")

	def test_agent_cannot_delete(self):
		note = self.make("Life Note", title="Keep me")
		task = self.make("Life Task", title="Keep me too")
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Life Note", note.name)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Life Task", task.name)
		self.assertTrue(frappe.db.exists("Life Note", note.name))

	def test_agent_cannot_change_spaces_or_members(self):
		self.as_user(AGENT)
		space = frappe.get_doc("Life Space", PRIVATE)
		space.append("members", {"user": FAMILY, "access": "Write"})
		self.assertRaises(frappe.PermissionError, space.save)
		new = frappe.get_doc({"doctype": "Life Space", "space_name": "Agent Space"})
		self.assertRaises(frappe.PermissionError, new.insert)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Life Space", SHARED)

	def test_agent_cannot_write_settings(self):
		self.as_user(AGENT)
		settings = frappe.get_doc("Life Settings")
		settings.score_target = 10
		self.assertRaises(frappe.PermissionError, settings.save)

	def test_family_user_cannot_change_spaces(self):
		self.as_user(FAMILY)
		space = frappe.get_doc("Life Space", SHARED)
		space.append("members", {"user": "stranger@lifeos.test", "access": "Write"})
		self.assertRaises(frappe.PermissionError, space.save)

	def test_owner_admin_can_manage_spaces(self):
		space = frappe.get_doc({"doctype": "Life Space", "space_name": "Anya's space", "owner_user": FAMILY}).insert()
		self.assertIn(FAMILY, [m.user for m in space.members])
		self.as_user(FAMILY)
		self.assertIn("Anya's space", permissions.user_spaces())


APP = pathlib.Path(__file__).resolve().parents[2]


def lifeos_whitelisted():
	return [f for f in frappe.whitelisted if (getattr(f, "__module__", "") or "").startswith("lifeos.")]


class TestWhitelistConventions(IntegrationTestCase):
	def setUp(self):
		import lifeos.api  # noqa: F401
		for path in sorted((APP / "lifeos/api").glob("*.py")):
			importlib.import_module(f"lifeos.api.{path.stem}")
		importlib.import_module("lifeos.queries")

	def test_every_method_declares_http_methods_and_hints(self):
		methods = lifeos_whitelisted()
		self.assertGreater(len(methods), 150)
		for fn in methods:
			name = f"{fn.__module__}.{fn.__name__}"
			allowed = frappe.allowed_http_methods_for_whitelisted_func[fn]
			self.assertIn(allowed, (["GET"], ["POST"]), f"{name} declares {allowed}")
			for param in inspect.signature(fn).parameters.values():
				if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
					continue
				self.assertIn(param.name, fn.__annotations__, f"{name}: {param.name} has no type hint")

	def test_front_end_list_of_get_methods_is_current(self):
		spec = importlib.util.spec_from_file_location("http_methods", APP / "scripts/http-methods.py")
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		on_disk = json.loads((APP / "frontend/src/lib/getMethods.json").read_text())
		self.assertEqual(on_disk, module.get_methods(APP), "run scripts/http-methods.py")
		get_only = sorted(f"{f.__module__}.{f.__name__}" for f in lifeos_whitelisted()
			if frappe.allowed_http_methods_for_whitelisted_func[f] == ["GET"])
		self.assertEqual(sorted(on_disk), get_only)


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
			from lifeos.ai import fake

			data = fake.asked(params)[1]
			seen.extend(r["title"] for r in data.get("records", []))
			refs = [r["ref"] for r in data.get("records", [])] or ["R1"]
			return {"content": [text(json.dumps({"follow_ups": [], "readings": [], "insights": [{"kind": "Theme", "title": "pre6 theme", "evidence": refs}]}))],
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
		self.assertEqual(frappe.db.get_value("Life AI Usage", {"purpose": "Skill: notice"}, "user"),
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


class TestNavigation(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Review", {"user": ("in", [OWNER, FAMILY])})

	def lock(self, user, space=PRIVATE):
		return frappe.get_doc({"doctype": "Life Review", "space": space, "user": user, "kind": "Weekly", "status": "Locked",
			"period_start": add_days(today(), -6), "period_end": today(), "locked_on": now_datetime(), "title": "i14 review",
			"tab_state": "{}"}).insert(ignore_permissions=True)

	# acceptance test 2: Review is hidden until one is locked, then shown
	def test_review_is_shown_only_after_the_person_locks_a_weekly_review(self):
		self.assertFalse(session.counts(PRIVATE)["reviewed"])
		frappe.get_doc({"doctype": "Life Review", "space": PRIVATE, "user": OWNER, "kind": "Weekly", "status": "Open",
			"period_start": add_days(today(), -6), "period_end": today(), "title": "i14 open", "tab_state": "{}"}).insert(ignore_permissions=True)
		self.assertFalse(session.counts(PRIVATE)["reviewed"], "an open review does not count")
		self.lock(OWNER)
		self.assertTrue(session.counts(PRIVATE)["reviewed"])
		self.assertTrue(session.counts(SHARED)["reviewed"], "the review is the person's, whichever space is open")
		frappe.set_user(FAMILY)
		self.assertFalse(session.counts(SHARED)["reviewed"], "another person's review does not show Review")

	# acceptance test 3: Brain's count is the Inbox count
	def test_the_brain_count_is_the_number_of_inbox_items_to_review(self):
		item = inbox.create_item("i14 capture to review", "Message", space=PRIVATE, raw_text="i14")
		frappe.db.set_value("Life Inbox Item", item["name"], "status", "To Review")
		c = session.counts(PRIVATE)
		listed = inbox.list(space=PRIVATE, status='["To Review"]', page_length=1)["total"]
		self.assertGreaterEqual(listed, 1)
		self.assertEqual(c["to_review"], listed)
		self.assertEqual(c["doors"]["inbox"]["n"], listed)


APP_cleanup = Path(frappe.get_app_path("lifeos"))


SRC = APP_cleanup.parent / "frontend" / "src"


# the owner's known goal titles and names: none may be in seed.py
PERSONAL = ["RMT", "GHL", "Tea & Coffee", "Business That Works", "Unstoppable", "Ruchi", "Anya", "Japa", "Mala", "Golf", "Arjun",
	"Nowrojee", "Sarjapur", "MoneyOS", "Get super-fit", "Close open loops", "Mind and learning", "Oct to Dec 2026", "Driver's licence",
	"Merrill", "Dalmia", "Mithun"]


# whitelisted methods that no screen, skill, agent or test calls by name, with the reason each stays (none now)
KEPT = {}


def imports_of(path, text):
	for m in re.finditer(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""", text):
		spec = m.group(1)
		base = SRC / spec[2:] if spec.startswith("@/") else (path.parent / spec if spec.startswith(".") else None)
		if base is None:
			continue
		for cand in (base, Path(f"{base}.js"), Path(f"{base}.vue"), base / "index.js"):
			if cand.is_file():
				yield cand.resolve()
				break
	for m in re.finditer(r"page\('([^']+)'\)", text):
		yield (SRC / "pages" / f"{m.group(1)}.vue").resolve()


class TestCleanup(IntegrationTestCase):
	def test_every_front_end_file_is_imported_or_routed(self):

		seen, todo = set(), [(SRC / "main.js").resolve()]
		while todo:
			path = todo.pop()
			if path in seen:
				continue
			seen.add(path)
			todo.extend(imports_of(path, path.read_text()))
		files = {p.resolve() for p in SRC.rglob("*") if p.suffix in (".vue", ".js")}
		self.assertEqual(sorted(str(p.relative_to(SRC.resolve())) for p in files - seen), [])

	def test_patches_txt_is_empty_and_a_site_installs_and_migrates_without_patches(self):

		lines = [x.strip() for x in (APP_cleanup / "patches.txt").read_text().splitlines()]
		self.assertEqual([x for x in lines if x and not x.startswith(("#", "["))], [])
		self.assertFalse((APP_cleanup / "patches").exists())
		self.assertEqual(get_patches_from_app("lifeos"), [])
		install.after_migrate()
		install.after_migrate()  # again: the schema comes from the DocTypes and setup is repeatable

	def test_seed_has_no_personal_names_goals_or_amounts(self):

		text = (APP_cleanup / "seed.py").read_text()
		for word in PERSONAL:
			self.assertNotIn(word.lower(), text.lower(), word)
		self.assertNotRegex(text, r"\d[\d,]{3,}\s*(?:rs|inr|usd|\$)|(?:rs|inr|usd|\$)\s*\d{3,}")

	def test_every_whitelisted_method_has_a_caller(self):
		# A report of the methods nothing calls; any that stays is in KEPT with its reason (and in DECISIONS.md
		corpus = "\n".join(p.read_text(errors="ignore") for p in [*SRC.rglob("*.vue"), *SRC.rglob("*.js")])
		corpus += "\n".join(p.read_text(errors="ignore") for p in (APP_cleanup / "skills").rglob("*.md"))
		corpus += (APP_cleanup.parent / "agent" / "fake_agent.py").read_text() + "".join(p.read_text() for p in (APP_cleanup.parent / "tools").glob("acceptance*.mjs")) + "".join(p.read_text() for p in (APP_cleanup.parent / "tools" / "acceptance").glob("*.mjs"))
		tests = "\n".join(p.read_text() for p in (APP_cleanup / "tests").glob("test_*.py") if p.name != Path(__file__).name)
		python = {p: p.read_text() for p in APP_cleanup.rglob("*.py") if "tests" not in p.parts}
		orphans = []
		for path, text in python.items():
			module = ".".join(path.relative_to(APP_cleanup.parent).with_suffix("").parts)
			for node in ast.walk(ast.parse(text)):
				if not isinstance(node, ast.FunctionDef) or not any("whitelist" in ast.unparse(d) for d in node.decorator_list):
					continue
				short = module.split(".")[-1]
				name = node.name
				called = (
					re.search(rf"\b{short}\.{name}\b", corpus + tests + "\n".join(python.values()))
					or re.search(rf"['\"`][\w.]*{name}['\"`]", corpus)  # a name passed to the review's r.act and r.read
					or len(re.findall(rf"(?<!def )\b{name}\(", text)) > 0  # called inside its own module
					or re.search(rf"import[^\n]*\b{name}\b", "\n".join(python.values()) + tests)
				)
				if not called and f"{module}.{name}" not in KEPT:
					orphans.append(f"{module}.{name}")
		self.assertEqual(sorted(orphans), [])


ROOT = Path(frappe.get_app_path("lifeos"))


class TestProjectAliasesGone(LifeTestCase):
	def test_3_a_call_with_project_names_goal_and_the_same_call_with_goal_works(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			gone_names.refuse({"project": "x", "status": "open"})
		self.assertIn("`goal`", str(caught.exception))
		request = types.SimpleNamespace(path="/api/method/lifeos.api.tasks.list")
		frappe.local.request = request
		old_form = frappe.local.form_dict
		try:
			frappe.local.form_dict = frappe._dict(project="x")
			self.assertRaises(frappe.ValidationError, gone_names.before_request)
			frappe.local.form_dict = frappe._dict(goal="x")
			gone_names.before_request()
		finally:
			frappe.local.form_dict = old_form
			frappe.local.request = None
		goal = self.make("Life Goal", title="i48 alias goal", horizon="Long term", area=self.areas["Tea"])
		task = self.make("Life Task", title="i48 alias task", area=self.areas["Tea"], goal=goal.name)
		self.assertEqual([t["name"] for t in tasks.list(space=PRIVATE, goal=goal.name)["tasks"]], [task.name])
		self.assertRaises(frappe.ValidationError, tasks.update, task.name, {"project": goal.name})
		self.assertRaises(frappe.ValidationError, proposals.validate, "Task", {"title": "x", "project": goal.name}, PRIVATE)
		self.assertNotIn("project", tasks.list.__code__.co_varnames[:tasks.list.__code__.co_argcount])

	def test_4_a_someday_proposal_with_record_type_project_is_refused(self):
		goal = self.make("Life Goal", title="i48 someday goal", horizon="Long term", area=self.areas["Tea"])
		item = types.SimpleNamespace(space=PRIVATE, name="none")
		self.assertRaises(proposals.PayloadError, proposals._apply_someday, {"record_type": "Project", "record": goal.name}, item)
		self.assertEqual(frappe.db.get_value("Life Goal", goal.name, "is_someday"), 0)

	def test_5_connection_defaults_have_no_default_project(self):
		self.assertNotIn("default_project", connections.defaults(space=PRIVATE, system="gmail"))
		self.assertIn("default_goal", connections.defaults(space=PRIVATE, system="gmail"))
		self.make("Life Connection", system="gmail", active=1)
		out = connections.defaults(space=PRIVATE, system="gmail")
		self.assertEqual(out["known"], 1)
		self.assertNotIn("default_project", out)
		self.assertNotIn("default_project", connections.list(space=PRIVATE)["connections"][0])


class TestNoProjectInTheCode(LifeTestCase):
	# the one file that names the removed arguments, to refuse them, and the patches, which are history
	SKIP = {"gone_names.py"}
	GONE = re.compile(r"Life Project|goal_for_project|for_project|project_alias|default_project|ProjectPane|ProjectRedirect|\bproject: str|\bproject=|[\"']project[\"']\s*:|[\"']project[\"']\s*[,)\]]")

	def test_7_no_python_or_front_end_code_names_the_old_table_or_the_alias(self):
		files = [p for p in ROOT.rglob("*.py") if "tests" not in p.parts and "patches" not in p.parts and p.name not in self.SKIP]
		front = ROOT.parent / "frontend" / "src"
		files += [p for ext in ("*.js", "*.vue") for p in front.rglob(ext)] if front.exists() else []
		files += [p for p in (ROOT.parent / "agent").rglob("*.py")]
		self.assertGreater(len(files), 100)
		hits = [f"{p.relative_to(ROOT.parent)}:{n}: {line.strip()[:100]}" for p in files
			for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1) if self.GONE.search(line)]
		self.assertEqual(hits, [])


class ClientErrorCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user(OWNER)
		frappe.db.delete("Error Log", {"method": ["like", f"{client_errors.TITLE} %"]})

	def logged(self, reference):
		return frappe.get_all("Error Log", filters={"method": f"{client_errors.TITLE} {reference}"}, pluck="error")

	def test_logs_one_entry_with_the_reference_and_no_query(self):
		out = client_errors.log(reference="ABC123", message="Cannot read properties of null", stack="TypeError\n at x",
			path="/life/plan/week?view=review&q=secret#frag", component="WeeklyReview", info="14", kind="render")
		self.assertEqual(out, {"reference": "ABC123"})
		[body] = self.logged("ABC123")
		self.assertIn("path: /life/plan/week\n", body)
		self.assertNotIn("secret", body)
		self.assertIn("user: " + OWNER, body)
		self.assertIn("Cannot read properties of null", body)

	def test_fields_are_clipped(self):
		client_errors.log(reference="CLIP01", message="m" * 5000, stack="s" * 50000, path="/" + "p" * 1000)
		[body] = self.logged("CLIP01")
		self.assertLess(len(body), 5200)

	def test_a_reference_is_required(self):
		self.assertRaises(frappe.ValidationError, client_errors.log, reference=" ", message="x")

	def test_guests_are_refused(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, client_errors.log, reference="GUEST1", message="x")
		frappe.set_user(OWNER)
		self.assertFalse(self.logged("GUEST1"))

	def test_post_only_and_rate_limited(self):
		fn = client_errors.log
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(fn), ["POST"])
		self.assertNotIn(fn, frappe.guest_methods)
		self.assertTrue(hasattr(fn, "__wrapped__"), "the rate limit wraps the method")


class TestLens(LifeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.parent = cls.life["Career"]  # issue 11: an area of life with its parts
		cls.sub = frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Lens Estate", "parent_area": cls.parent}).insert().name
		cls.other = cls.areas["Money"]

	def filed(self, doctype, title_field="title", **values):
		"""Three records: one in the sub-area, one in another area that lists the parent in "also in", one only elsewhere."""
		sub = self.make(doctype, **{title_field: f"lens {doctype} sub", "area": self.sub, **values})
		also = self.make(doctype, **{title_field: f"lens {doctype} also", "area": self.other, "also_in": [{"area": self.parent}], **values})
		out = self.make(doctype, **{title_field: f"lens {doctype} elsewhere", "area": self.other, **values})
		return sub.name, also.name, out.name

	def check(self, names, listed, label):
		sub, also, out = names
		self.assertIn(sub, listed, f"{label}: a record in a sub-area is in its parent area")
		self.assertIn(also, listed, f"{label}: a record listing the area in also-in is in it")
		self.assertNotIn(out, listed, f"{label}: a record of another area is not")

	def test_tasks(self):
		names = self.filed("Life Task", status="Open")
		res = tasks.list(space=PRIVATE, area=self.parent, page_length=100)
		self.check(names, [r.name for r in res["tasks"]], "tasks.list")
		self.assertEqual(res["total"], tasks.total(PRIVATE, status="open", area=self.parent))

	def test_inbox(self):
		names = self.filed("Life Inbox Item", status="To Review")
		res = inbox.list(space=PRIVATE, area=self.parent, page_length=100)
		self.check(names, [r.name for r in res["items"]], "inbox.list")

	def test_notes_and_sources(self):
		names = self.filed("Life Note", content_md="x")
		self.check(names, [r.name for r in library.list(space=PRIVATE, area=self.parent, page_length=100)["notes"]], "library.list")
		self.check(names, [n.name for n in library.tree(space=PRIVATE, area=self.parent)["notes"]], "library.tree")
		chat_names = self.filed("Life Chat Log", date=today())
		res = sources.list(space=PRIVATE, area=self.parent, tab="chats", page_length=100)
		self.check(chat_names, [r["name"] for r in res["sources"]], "sources.list")
		self.check(chat_names, [r.name for r in chats.list(space=PRIVATE, area=self.parent, page_length=100)["chats"]], "chats.list")
		res = timeline.get(space=PRIVATE, area=self.parent, page_length=200)
		self.check(names, [r.ref_name for d in res["days"] for r in d["entries"]], "timeline.get")

	def test_vault(self):
		names = self.filed("Life Vault Document", doc_type="Other")
		self.check(names, [r.name for r in vault.list(space=PRIVATE, area=self.parent, page_length=100)["documents"]], "vault.list")

	def test_goals_and_someday(self):
		sub = self.make("Life Goal", title="lens goal sub", horizon="Long term", area=self.sub)
		out = self.make("Life Goal", title="lens goal elsewhere", horizon="Long term", area=self.other)
		listed = [r.name for r in goals.list(space=PRIVATE, area=self.parent, page_length=100)["goals"]]
		self.assertIn(sub.name, listed)
		self.assertNotIn(out.name, listed)
		names = self.filed("Life Task", status="Open")
		for n in names:
			someday.park(doctype="Life Task", name=n)
		listed = [r.name for r in someday.list(space=PRIVATE, area=self.parent, page_length=100)["rows"]]
		self.check(names, listed, "someday.list")

	def test_archive(self):
		names = self.filed("Life Note", content_md="x")
		for n in names:
			frappe.db.set_value("Life Note", n, {"is_archived": 1, "archived_on": today()})
			frappe.get_doc("Life Note", n).save()
		res = archive.list(space=PRIVATE, area=self.parent, page_length=100)
		self.check(names, [r.ref_name for r in res["records"]], "archive.list")

	def test_search(self):
		names = self.filed("Life Note", content_md="zanzibarlens")
		res = search.query(text="zanzibarlens", space=PRIVATE, area=self.parent)
		self.check(names, [r.ref_name for r in res["results"]], "search.query")
		self.assertEqual(len(search.query(text="zanzibarlens", space=PRIVATE)["results"]), 3)

	def test_counts_and_today(self):
		names = self.filed("Life Task", status="Open", due_date=today())
		band = counts.open_band(PRIVATE, self.parent)
		self.assertEqual(band["open_tasks"]["to"]["query"]["area"], self.parent)
		self.assertEqual(band["open_tasks"]["n"], tasks.list(space=PRIVATE, area=self.parent, status="all",
			filters=band["open_tasks"]["to"]["query"]["f"], page_length=1)["total"])
		self.assertLess(band["open_tasks"]["n"], counts.open_band(PRIVATE)["open_tasks"]["n"])
		day = today_api.get(space=PRIVATE, area=self.parent)
		listed = [r.name for g in day["next"]["groups"] if g["key"] == "today" for r in g["rows"] if r.get("type") == "task"]
		self.check(names, listed, "today.get")
		self.assertEqual(next(g for g in day["next"]["groups"] if g["key"] == "today")["tasks"]["n"], len(listed))  # set 8: the top three come first
		side = counts.sidebar(PRIVATE, self.parent)
		self.assertEqual(side["tasks"]["to"]["query"]["area"], self.parent)

	def test_in_area_and_grid(self):
		names = self.filed("Life Task", status="Open")
		self.assertEqual(in_area(PRIVATE, self.parent, "Life Task", list(names)), set(names[:2]))
		self.assertEqual(in_area(PRIVATE, None, "Life Task", list(names)), set(names))
		g = graph.get(space=PRIVATE, area=self.parent)
		self.assertIsInstance(g["nodes"], list)
		self.assertIsNone(goals.grid(space=PRIVATE, area=self.parent)) if not frappe.db.exists("Life Cycle", {"space": PRIVATE}) else None

	def test_new_area_gets_a_colour(self):
		a = frappe.get_doc("Life Area", self.life["Mind"])  # issue 11: the seven come with their colours
		self.assertEqual(a.colour, "violet")
		b = frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Lens Colour Sub", "parent_area": a.name}).insert()
		self.assertEqual(b.colour, a.colour)
		json.dumps(a.as_dict(), default=str)


NEWCOMER = "issue1-newcomer@lifeos.test"


NEW_AGENT = "issue1-agent@lifeos.test"


class TestMembers(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		for u in (NEWCOMER, NEW_AGENT):
			devtools.make_user(u, u.split("@")[0], [])
			doc = frappe.get_doc("User", u)
			doc.flags.ignore_permissions = True
			doc.remove_roles(*settings.LIFE_ROLES)
		for space in (PRIVATE, SHARED):
			doc = frappe.get_doc("Life Space", space)
			for m in [m for m in doc.members if m.user in (NEWCOMER, NEW_AGENT)]:
				doc.remove(m)
			doc.save(ignore_permissions=True)
		self.as_user(OWNER)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for u in (NEWCOMER, NEW_AGENT):
			for space in frappe.get_all("Life Space Member", filters={"user": u, "parenttype": "Life Space"}, pluck="parent"):
				doc = frappe.get_doc("Life Space", space)
				for m in [m for m in doc.members if m.user == u]:
					doc.remove(m)
				doc.save(ignore_permissions=True)
			frappe.delete_doc("User", u, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def space(self, name=PRIVATE):
		return next(s for s in settings.get(space=PRIVATE)["spaces"] if s["name"] == name)

	def test_get_lists_agents_in_members_with_is_agent(self):
		sp = self.space()
		rows = {m["user"]: m for m in sp["members"]}
		self.assertIn(AGENT, rows)
		self.assertTrue(rows[AGENT]["is_agent"])
		self.assertEqual(rows[AGENT]["kind"], "Agent")
		self.assertFalse(rows[OWNER]["is_agent"])
		self.assertEqual(rows[OWNER]["kind"], "Owner")
		self.assertEqual(sp["members"][0]["user"], OWNER)
		self.assertEqual((sp["people_count"], sp["agent_count"]), (1, 1))
		shared = {m["user"]: m["kind"] for m in self.space(SHARED)["members"]}
		self.assertEqual(shared[FAMILY], "Person")

	def test_agents_view_comes_from_the_same_rows(self):
		got = settings.get(space=PRIVATE)
		card = next(a for a in got["agents"] if a["user"] == AGENT)
		reach = {r["space"]: r["access"] for r in card["spaces"]}
		for sp in got["spaces"]:
			row = next((m for m in sp["members"] if m["user"] == AGENT), None)
			self.assertEqual(reach[sp["name"]], row["access"] if row else None)
		# a change made for the Agents view shows in Members, and back
		settings.set_member(PRIVATE, AGENT, "Read")
		self.assertEqual(next(m for m in self.space()["members"] if m["user"] == AGENT)["access"], "Read")
		card = next(a for a in settings.get(space=PRIVATE)["agents"] if a["user"] == AGENT)
		self.assertEqual(next(r for r in card["spaces"] if r["space"] == PRIVATE)["access"], "Read")
		settings.set_member(PRIVATE, AGENT, "Write")

	def test_only_life_admin_changes_members(self):
		for user in (FAMILY, AGENT):
			self.as_user(user)
			self.assertRaises(frappe.PermissionError, settings.set_member, SHARED, FAMILY, "Read")
			self.assertRaises(frappe.PermissionError, settings.set_member, SHARED, OWNER, remove=1)
			self.assertRaises(frappe.PermissionError, settings.find_users, "lifeos")
		self.as_user(OWNER)
		self.assertEqual(next(m for m in self.space(SHARED)["members"] if m["user"] == FAMILY)["access"], "Write")

	def test_the_owner_cannot_be_removed_or_lose_edit(self):
		self.assertRaises(frappe.ValidationError, settings.set_member, PRIVATE, OWNER, remove=1)
		self.assertRaises(frappe.ValidationError, settings.set_member, PRIVATE, OWNER, "Read")
		self.assertIn(OWNER, [m["user"] for m in self.space()["members"]])

	def test_an_agent_is_added_with_view_access_and_appears_at_once(self):
		out = settings.set_member(PRIVATE, NEW_AGENT, grant_role="Life Agent")
		row = next(m for m in out["members"] if m["user"] == NEW_AGENT)
		self.assertEqual((row["access"], row["is_agent"], row["kind"]), ("Read", True, "Agent"))
		self.assertTrue(permissions.is_agent(NEW_AGENT))
		self.assertIn(NEW_AGENT, [a["user"] for a in settings.get(space=PRIVATE)["agents"]])
		# an existing agent keeps its role and gets Read by default
		settings.set_member(SHARED, NEW_AGENT)
		self.assertEqual(next(m for m in self.space(SHARED)["members"] if m["user"] == NEW_AGENT)["access"], "Read")

	def test_a_person_gets_edit_access_by_default(self):
		settings.set_member(PRIVATE, NEWCOMER, grant_role="Life User")
		row = next(m for m in self.space()["members"] if m["user"] == NEWCOMER)
		self.assertEqual((row["access"], row["kind"]), ("Write", "Person"))

	def test_no_role_is_refused_until_the_owner_chooses_one(self):
		self.assertRaises(frappe.ValidationError, settings.set_member, PRIVATE, NEWCOMER)
		self.assertNotIn(NEWCOMER, [m["user"] for m in self.space()["members"]])
		self.assertFalse(set(frappe.get_roles(NEWCOMER)) & set(settings.LIFE_ROLES))

	def test_this_screen_never_gives_an_agent_life_user_or_life_admin(self):
		self.assertRaises(frappe.PermissionError, settings.set_member, PRIVATE, NEWCOMER, grant_role="Life Admin")
		self.assertRaises(frappe.PermissionError, settings.set_member, SHARED, AGENT, grant_role="Life User")
		self.assertRaises(frappe.PermissionError, settings.set_member, SHARED, AGENT, grant_role="Life Admin")
		self.assertEqual(set(frappe.get_roles(AGENT)) & set(settings.LIFE_ROLES), {"Life Agent"})
		self.assertFalse(set(frappe.get_roles(NEWCOMER)) & set(settings.LIFE_ROLES))

	def test_an_agent_cannot_own_a_space(self):
		self.assertRaises(frappe.ValidationError, settings.create_space, "Issue 1 agent space", owner_user=AGENT)
		self.assertFalse(frappe.db.exists("Life Space", "Issue 1 agent space"))

	def test_find_users_lists_people_and_agents_with_their_kind(self):
		found = {r["name"]: r for u in (AGENT, FAMILY, NEWCOMER, "Administrator") for r in settings.find_users(u, space=PRIVATE)}
		self.assertEqual(found[AGENT]["kind"], "Agent")
		self.assertTrue(found[AGENT]["is_member"])
		self.assertEqual(found[FAMILY]["kind"], "Person")
		self.assertFalse(found[FAMILY]["is_member"])
		self.assertIsNone(found[NEWCOMER]["kind"])
		self.assertNotIn("Administrator", found)


MARKER = "zqprivatemarker"
# the errors a read may answer with; anything else is a traceback
ALLOWED = (frappe.PermissionError, frappe.DoesNotExistError, frappe.ValidationError, frappe.NotFound if hasattr(frappe, "NotFound") else frappe.DoesNotExistError)


class TestReadsThroughFrappePermissions(LifeTestCase):
	"""Every read in lifeos/api/ answers a person from another space with nothing of this space's (issue 73)."""

	def setUp(self):
		super().setUp()
		self.note = self.make("Life Note", title=f"{MARKER} note", content_md=f"{MARKER} body")
		self.task = self.make("Life Task", title=f"{MARKER} task")
		self.person = self.make("Life Person", full_name=f"{MARKER} person")
		self.item = item(f"{MARKER} capture")
		self.area = self.areas["Tea"]
		self.goal = self.make("Life Goal", title=f"{MARKER} goal", horizon="Long term", done_when="Done").name
		self.args = {"space": PRIVATE, "area": self.area, "goal": self.goal, "task": self.task.name, "note": self.note.name, "item": self.item,
			"name": self.person.name, "document": "-", "chat": "-", "run": "-", "skill": "-", "client_id": "-", "kind": "Task", "text": MARKER}

	def reads(self):
		"""Every whitelisted GET method of lifeos/api/, as (dotted name, function, the keyword arguments to call it with)."""
		import importlib
		import pkgutil

		import lifeos.api as api_package

		for mod in pkgutil.iter_modules(api_package.__path__):
			module = importlib.import_module(f"lifeos.api.{mod.name}")
			for name, fn in vars(module).items():
				if not callable(fn) or getattr(fn, "__module__", None) != module.__name__ or fn not in frappe.whitelisted:
					continue
				if "GET" not in (frappe.allowed_http_methods_for_whitelisted_func.get(fn) or []):
					continue
				params = inspect.signature(fn).parameters
				required = [p for p in params.values() if p.default is inspect.Parameter.empty]
				kwargs = {}
				for p in required:
					if p.name == "name" and "doctype" in params:
						continue
					if p.name not in self.args:
						break
					kwargs[p.name] = self.args[p.name]
				else:
					if "space" in params:
						kwargs["space"] = PRIVATE
					if "doctype" in params and "name" in params:
						kwargs.update(doctype="Life Note", name=self.note.name)
					if "kind" in params and "name" in params:
						kwargs.update(kind="Task", name=self.task.name)
					yield f"{mod.name}.{name}", fn, kwargs

	def test_1_a_person_in_another_space_gets_nothing_from_this_one_from_any_read(self):
		self.as_user(FAMILY)
		called = 0
		for dotted, fn, kwargs in self.reads():
			try:
				result = fn(**kwargs)
			except ALLOWED:
				called += 1
				continue
			called += 1
			self.assertNotIn(MARKER, json.dumps(result, default=str), dotted)
		self.assertGreater(called, 50)

	def test_2_the_brain_and_an_agent_read_only_what_they_are_allowed_to(self):
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		self.make("Life Vault Document", title=f"{MARKER} passport", doc_type="ID")
		for user in (AGENT, permissions.BRAIN_USER):
			self.as_user(user)
			names = frappe.get_list("Life Task", filters={"space": PRIVATE}, pluck="name", limit=0)
			self.assertIn(self.task.name, names, user)
			self.assertEqual(frappe.get_list("Life Vault Document", filters={"space": PRIVATE}, pluck="name", limit=0), [], user)
		self.as_user(AGENT)
		self.assertEqual(frappe.get_list("Life Space", filters={"name": SHARED}, pluck="name"), [SHARED])
		self.assertEqual(frappe.get_list("Life Person", filters={"space": "Nowhere"}, pluck="name"), [])
		for dotted, fn, kwargs in self.reads():
			try:
				fn(**kwargs)
			except ALLOWED:
				pass

	def test_3_the_scan_refuses_a_get_all_in_the_api_unless_it_says_why(self):
		import subprocess
		import tempfile

		guard = Path(__file__).resolve().parents[2] / "tools" / "scan_guard.py"
		with tempfile.TemporaryDirectory() as tmp:
			api = Path(tmp) / "lifeos" / "api"
			api.mkdir(parents=True)
			bad, good = api / "bad.py", api / "good.py"
			bad.write_text('rows = frappe.get_all("Life Task")\ndoc.save(ignore_permissions=True)\n')
			good.write_text('rows = frappe.get_all("Life Task")  # system: a background job\ndoc.save(ignore_permissions=True)  # system: seeded\n')
			refused = subprocess.run(["python3", str(guard), str(bad)], capture_output=True, text=True)
			passed = subprocess.run(["python3", str(guard), str(good)], capture_output=True, text=True)
		self.assertEqual(refused.returncode, 1, refused.stdout)
		self.assertEqual(refused.stdout.count("bad.py"), 2)
		self.assertEqual(passed.returncode, 0, passed.stdout)

	def test_3b_the_api_has_no_unexplained_get_all(self):
		import sys

		sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
		try:
			import scan_guard
		finally:
			sys.path.pop(0)
		self.assertEqual(scan_guard.findings([Path(__file__).resolve().parents[1] / "api"]), [])

	def test_4_no_cache_lives_in_frappe_local_outside_the_permissions_request_cache(self):
		app = Path(__file__).resolve().parents[1]
		found = [f"{p.relative_to(app)}:{n}" for p in app.rglob("*.py") if "tests" not in p.parts and p.name != "permissions.py"
			for n, line in enumerate(p.read_text().splitlines(), 1) if re.search(r"frappe\.local\.(?!request\b|form_dict\b|response\b|flags\b)\w+\s*=[^=]", line)]
		self.assertEqual(found, [])
		self.assertIn("@request_cache", (app / "permissions.py").read_text())
		self.assertNotRegex((app / "permissions.py").read_text(), r"frappe\.local\.\w+\s*=[^=]")

	def test_5_a_filter_list_where_a_string_is_expected_is_refused(self):
		for method, arg in ((goals.get, "goal"), (tasks.get, "task"), (inbox.get, "item")):
			with self.assertRaises(frappe.FrappeTypeError, msg=method.__module__) as raised:
				method(**{arg: [["name", "like", "%"]]})
			self.assertIn(arg, str(raised.exception))
