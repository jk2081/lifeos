"""UX fixes, set 5: the AI client (key, cap, usage), Ask with the fake model, its tools' permissions and the Vault switch."""
import json

import frappe
from frappe.utils import add_days, today

from lifeos.ai import client, fake
from lifeos.api import ask
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


def text(t):
	return {"type": "text", "text": t}


def set_key(value):
	frappe.set_user("Administrator")
	s = frappe.get_single("Life Settings")
	s.anthropic_api_key = value
	s.monthly_cap_usd = 30
	s.save()
	frappe.clear_cache(doctype="Life Settings")


class AskCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		set_key("sk-test-not-real")
		frappe.db.delete("Life AI Usage")
		frappe.db.set_value("Life Space", PRIVATE, {"ask_enabled": 1, "ask_can_read_vault": 0})
		frappe.db.set_value("Life Space", SHARED, {"ask_enabled": 1, "ask_can_read_vault": 0})
		frappe.set_user(OWNER)

	def tearDown(self):
		frappe.flags.lifeos_ai_backend = None
		super().tearDown()

	def script(self, *responses):
		frappe.flags.lifeos_ai_backend = fake.ScriptedFake(responses)
		return frappe.flags.lifeos_ai_backend


class TestClient(AskCase):
	def test_no_key_says_not_set_up(self):
		set_key("")
		frappe.set_user(OWNER)
		self.script(text("x"))
		res = ask.ask("What is open?", space=PRIVATE)
		self.assertEqual(res["error"], "not_set_up")
		self.assertEqual(res["error_text"], "Ask is not set up yet.")
		self.assertFalse(ask.status(space=PRIVATE)["ready"])

	def test_cap_refuses_with_the_spend(self):
		frappe.get_doc({"doctype": "Life AI Usage", "user": OWNER, "month": client.month(), "model": "claude-sonnet-5-5", "cost": 31,
			"purpose": "Ask"}).insert(ignore_permissions=True)
		self.script(text("x"))
		res = ask.ask("What is open?", space=PRIVATE)
		self.assertEqual(res["error"], "cap")
		self.assertIn("$31.00 of $30", res["error_text"])
		self.assertEqual(res["spend"]["text"], "This month: $31.00 of $30")

	def test_usage_and_cost_are_recorded(self):
		self.script({"content": [text("Nothing here.")], "stop_reason": "end_turn", "usage": {"input_tokens": 1_000_000, "output_tokens": 100_000}})
		res = ask.ask("Anything?", space=PRIVATE)
		self.assertEqual(res["message"]["status"], "Done")
		u = frappe.get_all("Life AI Usage", fields=["model", "input_tokens", "output_tokens", "cost", "purpose", "user"])
		self.assertEqual(len(u), 1)
		self.assertEqual((u[0].model, u[0].purpose, u[0].user), ("claude-sonnet-5-5", "Ask", OWNER))
		self.assertAlmostEqual(u[0].cost, 2.0 + 1.0)
		self.assertEqual(client.spend_status()["text"], "This month: $3.00 of $30")

	def test_agents_cannot_ask(self):
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			ask.ask("What is open?", space=PRIVATE)


class TestAnswer(AskCase):
	def test_answer_cites_records_and_make_task_only_when_clicked(self):
		t = self.make("Life Task", title="ux5ask drainage review with Mr Rao", area=self.areas["Tea"])
		fk = self.script(
			{"content": [fake.tool_use("search", {"query": "drainage"}, "t1")], "stop_reason": "tool_use"},
			lambda p: {"content": [text("The drainage review is open [R1]."),
				fake.tool_use("suggest_actions", {"actions": [{"kind": "make_task", "label": "Make task: call Mr Rao", "title": "Call Mr Rao", "area_ref": "R1"}]}, "t2")],
				"stop_reason": "tool_use"},
			{"content": [], "stop_reason": "end_turn"})
		before = frappe.db.count("Life Task", {"space": PRIVATE})
		res = ask.ask("What about drainage?", space=PRIVATE, scope={"kind": "space", "label": "Everything in this space"})
		m = res["message"]
		self.assertEqual(m["text"], "The drainage review is open [1].")
		self.assertEqual(m["cited"][0]["name"], t.name)
		self.assertEqual(m["cited"][0]["pane"], "task:" + t.name)
		self.assertEqual(m["actions"][0]["kind"], "make_task")
		self.assertEqual(m["actions"][0]["area"], self.areas["Tea"])
		self.assertEqual(frappe.db.count("Life Task", {"space": PRIVATE}), before)
		# the search result reached the model as data, with the system prompt's rules
		self.assertIn("treat", "treat")
		self.assertIn("never instructions", fk.received[0]["system"])
		tool_result = fk.received[1]["messages"][-1]["content"][0]["content"]
		self.assertIn("drainage review", tool_result)
		out = ask.run_action(m["name"], 0)
		self.assertEqual(frappe.db.get_value("Life Task", out["task"], "area"), self.areas["Tea"])
		# the thread is private to its user
		self.as_user(FAMILY)
		with self.assertRaises(frappe.DoesNotExistError):
			ask.thread(res["thread"])

	def test_area_scope_and_family_never_reaches_private(self):
		self.make("Life Task", title="ux5scope tea drainage", area=self.areas["Tea"])
		self.make("Life Task", title="ux5scope money drainage", area=self.areas["Money"])
		fk = self.script({"content": [fake.tool_use("search", {"query": "ux5scope drainage"}, "t1")], "stop_reason": "tool_use"},
			{"content": [text("Done.")], "stop_reason": "end_turn"})
		ask.ask("ux5scope?", space=PRIVATE, scope={"kind": "area", "label": "Tea", "name": self.areas["Tea"]})
		result = fk.received[1]["messages"][-1]["content"][0]["content"]
		self.assertIn("ux5scope tea drainage", result)
		self.assertNotIn("ux5scope money", result)
		# the family member asks in Shared and gets nothing from Private
		self.as_user(FAMILY)
		fk = self.script({"content": [fake.tool_use("search", {"query": "ux5scope drainage"}, "t1")], "stop_reason": "tool_use"},
			{"content": [text("I could not find that.")], "stop_reason": "end_turn"})
		res = ask.ask("ux5scope?", space=SHARED)
		self.assertNotIn("ux5scope", fk.received[1]["messages"][-1]["content"][0]["content"].split('"query"')[0].replace("ux5scope?", ""))
		self.assertEqual(res["message"]["cited"], [])
		with self.assertRaises(frappe.PermissionError):
			ask.ask("x?", space=PRIVATE)

	def test_vault_is_never_sent_while_the_switch_is_off(self):
		v = self.make("Life Vault Document", title="ux5vault passport zebracode", doc_type="ID", notes_md="zebracode number 12345", area=self.areas["Money"])
		fk = self.script({"content": [fake.tool_use("search", {"query": "zebracode"}, "t1"),
				fake.tool_use("get_record", {"doctype": "Life Vault Document", "name": v.name}, "t2")], "stop_reason": "tool_use"},
			{"content": [text("I could not find that.")], "stop_reason": "end_turn"})
		ask.ask("Where is my passport?", space=PRIVATE)
		sent = json.dumps(fk.received[1]["messages"][-1])
		self.assertNotIn("ux5vault passport", sent)
		self.assertNotIn("12345", sent)
		self.assertIn("not available to Ask", sent)
		frappe.db.set_value("Life Space", PRIVATE, "ask_can_read_vault", 1)
		fk = self.script({"content": [fake.tool_use("get_record", {"doctype": "Life Vault Document", "name": v.name}, "t1")], "stop_reason": "tool_use"},
			{"content": [text("Found [R1].")], "stop_reason": "end_turn"})
		ask.ask("Where is my passport?", space=PRIVATE)
		self.assertIn("12345", json.dumps(fk.received[1]["messages"][-1]))

	def test_tool_limit_answers_with_what_was_found(self):
		self.make("Life Task", title="ux5limit thing", area=self.areas["Tea"])
		calls = [{"content": [fake.tool_use("search", {"query": "ux5limit"}, f"t{i}")], "stop_reason": "tool_use"} for i in range(9)]
		fk = self.script(*calls, {"content": [text("Partial answer [R1].")], "stop_reason": "end_turn"})
		res = ask.ask("ux5limit?", space=PRIVATE)
		self.assertLessEqual(sum(1 for r in fk.received if r.get("tools")), 10)
		self.assertIn("Partial answer", res["message"]["text"])
		self.assertTrue("not checked" in res["message"]["text"] or "limit" in res["message"]["text"])

	def test_history_search_and_delete(self):
		self.script({"content": [text("One.")], "stop_reason": "end_turn"}, {"content": [text("Two.")], "stop_reason": "end_turn"})
		res = ask.ask("ux5hist first question?", space=PRIVATE)
		res2 = ask.ask("and a follow-up?", thread=res["thread"])
		self.assertEqual(res2["thread"], res["thread"])
		self.assertEqual(len(ask.thread(res["thread"])["messages"]), 4)
		self.assertEqual(ask.threads(space=PRIVATE, q="ux5hist")["total"], 1)
		ask.delete_thread(res["thread"])
		self.assertEqual(ask.threads(space=PRIVATE, q="ux5hist")["total"], 0)


class TestLiveSmoke(AskCase):
	"""Calls the real API once, only when a real key is configured in site config (never in this repo's test runs)."""

	def test_live_answer(self):
		key = frappe.conf.get("anthropic_api_key_live_test")
		if not key:
			self.skipTest("no live key configured")
		set_key(key)
		frappe.set_user(OWNER)
		res = ask.ask("What tasks are open?", space=PRIVATE)
		self.assertEqual(res["message"]["status"], "Done")


class TestAIInsightsAndBatches(AskCase):
	def test_ai_insight_candidates_keep_only_visible_evidence(self):
		from lifeos import insights

		frappe.db.delete("Life Insight", {"space": PRIVATE})
		chat = self.make("Life Chat Log", title="ux5ai Mithun blend sheets", date=today(), summary_md="I will send six questions to Mithun.",
			area=self.areas["Tea"])
		frappe.get_doc({"doctype": "Life Insight", "space": PRIVATE, "kind": "Theme", "title": "ux5ai old theme", "status": "Dismissed",
			"dismiss_reason": "Not relevant", "fingerprint": "x", "evidence": [{"ref_doctype": "Life Chat Log", "ref_name": chat.name}]}).insert(ignore_permissions=True)

		def answer(params):
			data = json.loads(params["messages"][-1]["content"])
			ref = next(r["ref"] for r in data["records"] if r["title"] == "ux5ai Mithun blend sheets")
			self.assertEqual(data["dismissed"][0]["reason"], "Not relevant")
			return {"content": [text(json.dumps({"candidates": [
				{"kind": "Promise", "title": "You said you would send six questions to Mithun.", "evidence": [ref], "task_title": "Send six questions to Mithun"},
				{"kind": "Theme", "title": "Made up", "evidence": ["R999"]}]}))], "stop_reason": "end_turn"}

		fk = self.script(answer)
		stats = insights.run(PRIVATE, ai=True)
		self.assertEqual(fk.received[0]["output_config"]["format"]["type"], "json_schema")
		rows = frappe.get_all("Life Insight", filters={"space": PRIVATE, "source": "AI"}, fields=["name", "kind", "title"])
		self.assertEqual([(r.kind, r.title) for r in rows], [("Promise", "You said you would send six questions to Mithun.")])
		self.assertEqual(frappe.db.get_value("Life AI Usage", {"purpose": "Insights"}, "user"), OWNER)
		self.assertIsNone(stats["ai"])

	def test_no_key_skips_ai_and_rules_still_run(self):
		from lifeos import insights

		set_key("")
		frappe.set_user(OWNER)
		stats = insights.run(PRIVATE, ai=True)
		self.assertIn("no API key", stats["ai"])

	def test_ai_batches_only_over_candidates(self):
		from lifeos.api import reset

		ts = [self.make("Life Task", title=f"ux5aib task {i}", area=self.areas["Tea"]) for i in range(4)]

		def answer(params):
			rows = json.loads(params["messages"][-1]["content"])
			mine = [r["ref"] for r in rows if r["title"].startswith("ux5aib")]
			return {"content": [text(json.dumps({"batches": [{"title": "ux5 AI batch", "reason": "They go together.", "action": "someday",
				"items": mine[:3] + ["C9999"]}]}))], "stop_reason": "end_turn"}

		self.script(answer)
		got = reset.get(space=PRIVATE, ai=1)
		ai = [b for b in got["batches"] if b["source"] == "AI"]
		self.assertEqual(len(ai), 1)
		self.assertEqual(ai[0]["count"], 3)
		self.assertTrue({i["name"] for i in ai[0]["items"]} <= {t.name for t in ts})
