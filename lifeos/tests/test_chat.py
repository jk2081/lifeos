"""Chat on Flow (issue 119): the send method, the run's usage and the cap, the tools' Vault and space rules, the Done list with Undo, the patch that
moves old Ask threads, and the deleted modules. The Flow Server and the model are not called here (the acceptance checks run a real turn against
tools/fake_openai.py): `new_session` and `FlowSession.chat` are replaced by what they write."""
import json
from unittest import mock

import frappe
from frappe.flow import ToolContext

from lifeos.ai import chat as engine
from lifeos.ai import client, flow
from lifeos.api import chat
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import AskCase


def ctx(thread, user=OWNER):
	return ToolContext(session_id=thread.flow_session, agent="lifeos/Life OS", user=user)


class ChatCase(AskCase):
	"""A Flow model exists (so Chat is set up); sessions and runs are written without the Flow Server."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		if not frappe.db.exists("Flow Provider", "openai"):
			frappe.get_doc({"doctype": "Flow Provider", "provider": "openai", "api_key": "sk-test-not-real"}).insert()
		if not frappe.db.get_value("Flow Model", {"enabled": 1, "embedding": 0}, "name"):
			frappe.get_doc({"doctype": "Flow Model", "title": "t119 model", "provider": "openai", "model_id": "gpt-test"}).insert()
		frappe.set_user(OWNER)
		self.runs = []
		self.patches = [mock.patch("frappe.flow.lib.session.new_session", side_effect=self.new_session), mock.patch("lifeos.ai.chat.ensure_agent", return_value=engine.AGENT),
			mock.patch("lifeos.ai.chat.give_flow_role"), mock.patch("frappe.flow.doctype.flow_session.flow_session.FlowSession.chat", autospec=True, side_effect=self.chat_run)]
		for p in self.patches:
			p.start()
			self.addCleanup(p.stop)

	def new_session(self, agent, title=None, **kw):
		return frappe.get_doc({"doctype": "Flow Session", "agent": engine.AGENT, "model": frappe.db.get_value("Flow Model", {"enabled": 1, "embedding": 0}, "name"), "title": title}).insert(ignore_permissions=True)  # system: the test stands in for Flow's own session

	def chat_run(self, session, body, **kw):
		run = frappe.get_doc({"doctype": "Flow Run", "session": session.name, "source": "Manual", "input": body, "status": "Running", "on_complete": kw.get("on_complete")}).insert(ignore_permissions=True)  # system: the run Flow would have written
		self.runs.append(run.name)
		return run

	def finish(self, run, output="The answer.", usage=None, status="Completed"):
		frappe.db.set_value("Flow Run", run, {"status": status, "output": output, "usage": json.dumps(usage or {"input_tokens": 1000, "output_tokens": 200, "cost": 0.0})})


class TestChat(ChatCase):
	def test_1_send_makes_a_flow_session_runs_the_agent_writes_one_usage_row_and_refuses_at_the_cap(self):
		res = chat.send("What is open on drainage?", space=PRIVATE, scope={"kind": "area", "label": "Tea", "name": self.areas["Tea"]})
		self.assertEqual(res["message"]["status"], "Working")
		t = frappe.get_doc("Life Ask Thread", res["thread"])
		self.assertTrue(frappe.db.exists("Flow Session", t.flow_session))
		run = frappe.get_doc("Flow Run", res["message"]["name"])
		self.assertIn("Scope: Tea", run.input)  # the scope and the question reach the agent
		self.assertTrue(run.input.endswith("Question: What is open on drainage?"))
		self.assertEqual(run.on_complete, "lifeos.ai.chat.run_done")
		self.assertEqual(frappe.db.count("Life AI Usage", {"reference_name": run.name}), 0)  # nothing is spent until the run ends
		self.finish(run.name, "Nothing is open on drainage.", {"input_tokens": 1_000_000, "output_tokens": 100_000})
		got = chat.progress(res["thread"], run.name)
		self.assertEqual((got["status"], got["text"]), ("Done", "Nothing is open on drainage."))
		chat.progress(res["thread"], run.name)  # asking again writes nothing more
		usage = frappe.get_all("Life AI Usage", filters={"reference_name": run.name}, fields=["purpose", "user", "space", "cost"])
		self.assertEqual(len(usage), 1)
		self.assertEqual((usage[0].purpose, usage[0].user, usage[0].space), ("Chat", OWNER, PRIVATE))
		self.assertGreater(usage[0].cost, 0)
		# a follow-up continues the same session
		again = chat.send("And the week after?", thread=res["thread"])
		self.assertEqual(frappe.get_doc("Life Ask Thread", res["thread"]).flow_session, t.flow_session)
		self.assertEqual(frappe.db.count("Flow Run", {"session": t.flow_session}), 2)
		self.assertEqual(len(chat.thread(res["thread"])["messages"]), 4)
		# the month's cap reached: refused, no run
		self.finish(again["message"]["name"], "x")
		frappe.get_doc({"doctype": "Life AI Usage", "user": OWNER, "month": client.month(), "model": "m", "cost": 31, "purpose": "Chat"}).insert(ignore_permissions=True)  # system: the test spends the cap
		before = frappe.db.count("Flow Run")
		refused = chat.send("One more?", space=PRIVATE)
		self.assertEqual(refused["error"], "cap")
		self.assertEqual(frappe.db.count("Flow Run"), before)

	def test_2_the_record_in_view_travels_with_the_question_and_must_be_readable(self):
		task = self.make("Life Task", title="t119 open record", area=self.areas["Tea"])
		res = chat.send("Summarise this", space=PRIVATE, record={"doctype": "Life Task", "name": task.name})
		self.assertIn(f"Life Task {task.name}", frappe.db.get_value("Flow Run", res["message"]["name"], "input"))
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			chat.send("Summarise this", space=SHARED, record={"doctype": "Life Task", "name": task.name})

	def test_3_no_model_in_flow_says_chat_needs_a_key_and_an_off_space_or_an_agent_is_refused(self):
		with mock.patch("lifeos.ai.chat.ready", return_value=False):
			res = chat.send("What is open?", space=PRIVATE)
			self.assertEqual((res["error"], res["error_text"]), ("not_set_up", "Chat needs an AI key. Add one in Settings › AI."))
			self.assertFalse(chat.status(space=PRIVATE)["ready"])
		self.assertTrue(chat.status(space=PRIVATE)["ready"])
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 0)
		self.assertEqual(chat.send("What is open?", space=PRIVATE)["error"], "off")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			chat.send("What is open?", space=PRIVATE)

	def test_4_a_failed_start_is_an_error_answer_not_a_crash(self):
		with mock.patch("lifeos.ai.chat.start", side_effect=RuntimeError("the Flow Server is down")):
			res = chat.send("What is open?", space=PRIVATE)
		self.assertEqual((res["error"], res["message"]["status"]), ("ai", "Error"))
		self.assertNotIn("Flow Server is down", res["error_text"])

	def test_5_threads_are_private_listed_searched_and_deleted_with_their_session(self):
		res = chat.send("t119hist first?", space=PRIVATE)
		session = frappe.db.get_value("Life Ask Thread", res["thread"], "flow_session")
		self.assertEqual(chat.threads(space=PRIVATE, q="t119hist")["rows"][0]["questions"], 1)
		other = chat.send("t119 another chat", space=PRIVATE)
		with self.assertRaises(frappe.DoesNotExistError):  # an answer is read through its own thread only
			chat.progress(res["thread"], other["message"]["name"])
		self.as_user(FAMILY)
		with self.assertRaises(frappe.DoesNotExistError):
			chat.thread(res["thread"])
		self.as_user(OWNER)
		chat.delete_thread(res["thread"])
		self.assertEqual(chat.threads(space=PRIVATE, q="t119hist")["total"], 0)
		self.assertFalse(frappe.db.exists("Flow Session", session))


class TestChatTools(ChatCase):
	"""The tools Flow runs for Chat: the thread's space and scope, the Vault, and the Done list."""

	def thread(self, scope=None, space=PRIVATE):
		res = chat.send("t119 start", space=space, scope=scope)
		return frappe.get_doc("Life Ask Thread", res["thread"]), res["message"]["name"]

	def test_1_a_tool_given_a_vault_document_gives_the_model_only_one_sensitive_document(self):
		v = self.make("Life Vault Document", title="t119 passport zebracode", doc_type="ID", notes_md="zebracode number 12345", area=self.areas["Money"])
		t, _run = self.thread()
		for out in (flow.get_record(doctype="Life Vault Document", name=v.name, ctx=ctx(t)), flow.search(query="zebracode", ctx=ctx(t))):
			self.assertNotIn("12345", json.dumps(out))
			self.assertNotIn("passport", json.dumps(out))
		self.assertEqual(flow.get_record(doctype="Life Vault Document", name=v.name, ctx=ctx(t)), {"error": "1 sensitive document"})
		frappe.db.set_value("Life Space", PRIVATE, "ask_can_read_vault", 1)
		self.assertIn("12345", json.dumps(flow.get_record(doctype="Life Vault Document", name=v.name, ctx=ctx(t))))

	def test_2_another_users_space_is_refused_and_the_threads_scope_narrows_a_search(self):
		self.make("Life Task", title="t119scope tea drainage", area=self.areas["Tea"])
		self.make("Life Task", title="t119scope money drainage", area=self.areas["Money"])
		t, _run = self.thread({"kind": "area", "label": "Tea", "name": self.areas["Tea"]})
		found = json.dumps(flow.search(query="t119scope drainage", ctx=ctx(t)))
		self.assertIn("t119scope tea drainage", found)
		self.assertNotIn("t119scope money", found)
		# the family member is not in the owner's thread's space
		out = flow.list_records(kind="tasks", ctx=ctx(t, FAMILY))
		self.assertIn("error", out)
		self.assertNotIn("t119scope", json.dumps(out))

	def test_3_a_write_the_owner_asked_for_is_listed_in_the_answers_done_with_undo_and_undo_takes_it_back(self):
		t, run = self.thread()
		out = flow.make_task(title="t119 call the auditor", area="Tea", ctx=ctx(t))
		self.assertEqual(len(out["done_list"]), 1)
		task = frappe.db.get_value("Life Task", {"title": "t119 call the auditor", "space": PRIVATE}, "name")
		self.assertTrue(task)
		# Flow keeps the tool's result in the run's transcript; the answer reads its Done list from there
		session = frappe.get_doc("Flow Session", t.flow_session)
		session.append("messages", {"role": "tool", "run": run, "tool_call_id": "c1", "content": json.dumps(out)})
		session.flags.ignore_validate = True
		session.save(ignore_permissions=True)
		self.finish(run, "I made the task.")
		answer = chat.progress(t.name, run)
		self.assertEqual(len(answer["done"]), 1)
		self.assertTrue(answer["done"][0]["undo"])
		self.assertEqual(answer["done"][0]["undone"], 0)
		chat.undo_done(run, 0)
		self.assertFalse(frappe.db.exists("Life Task", task))
		self.assertEqual(chat.progress(t.name, run)["done"][0]["undone"], 1)
		with self.assertRaises(frappe.ValidationError):
			chat.undo_done(run, 0)

	def test_4_the_references_an_answer_cites_keep_their_numbers_across_tool_calls(self):
		a = self.make("Life Task", title="t119cite alpha review", area=self.areas["Tea"])
		b = self.make("Life Task", title="t119cite beta review", area=self.areas["Tea"])
		t, run = self.thread()
		first = flow.search(query="t119cite alpha", ctx=ctx(t))
		second = flow.search(query="t119cite beta", ctx=ctx(t))
		refs = {r["title"]: r["ref"] for r in [*first["results"], *second["results"]]}
		self.assertNotEqual(refs["t119cite alpha review"], refs["t119cite beta review"])
		self.finish(run, f"Alpha [{refs['t119cite alpha review']}], beta [{refs['t119cite beta review']}].")
		got = chat.progress(t.name, run)
		self.assertEqual(got["text"], "Alpha [1], beta [2].")
		self.assertEqual([c["name"] for c in got["cited"]], [a.name, b.name])


class TestChatPatchAndDeletions(ChatCase):
	def test_1_the_patch_moves_an_ask_thread_with_three_messages_to_a_thin_thread_with_a_read_only_note(self):
		from lifeos.patches import ask_threads_to_chat

		thread = self.make("Life Ask Thread", user=OWNER, space=PRIVATE, title="t119 old question")
		frappe.db.sql_ddl("create table if not exists `tabLife Ask Message` (name varchar(140) primary key, thread varchar(140), role varchar(20), text longtext, status varchar(20), creation datetime(6))")
		try:
			for i, (role, text) in enumerate((("user", "Where is my passport?"), ("assistant", "In the Vault."), ("user", "Thanks"))):
				frappe.db.sql("insert into `tabLife Ask Message` (name, thread, role, text, status, creation) values (%s, %s, %s, %s, 'Done', %s)", (f"t119-{i}", thread.name, role, text, f"2026-11-0{i + 1} 10:00:00"))  # nosemgrep: frappe-semgrep-rules.rules.frappe-using-db-sql -- seeds the table the patch reads, which no DocType makes any more
			ask_threads_to_chat.move_messages()
		finally:
			frappe.db.sql_ddl("drop table if exists `tabLife Ask Message`")
		got = frappe.get_doc("Life Ask Thread", thread.name)
		self.assertFalse(got.flow_session)
		self.assertEqual([(m["role"], m["text"]) for m in json.loads(got.transcript)], [("user", "Where is my passport?"), ("assistant", "In the Vault."), ("user", "Thanks")])
		shown = chat.thread(thread.name)
		self.assertEqual([m["text"] for m in shown["messages"]], ["Where is my passport?", "In the Vault.", "Thanks"])
		self.assertEqual(chat.threads(space=PRIVATE, q="passport")["rows"][0]["questions"], 2)

	def test_2_the_modules_ask_replaced_are_gone_and_the_message_doctype_does_not_exist(self):
		import importlib

		for module in ("lifeos.ai.ask", "lifeos.ai.ask_job", "lifeos.api.ask"):
			with self.assertRaises(ImportError, msg=module):
				importlib.import_module(module)
		self.assertFalse(frappe.db.exists("DocType", "Life Ask Message"))
		self.assertFalse(frappe.db.table_exists("Life Ask Message"))
		self.assertTrue(frappe.db.exists("DocType", "Life Ask Thread"))
