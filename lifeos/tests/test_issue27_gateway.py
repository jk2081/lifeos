"""Issue 27: one gateway for every model call: the cost of each call, a cap per month and per feature."""
import os

import frappe

from lifeos import area_guess
from lifeos.ai import client, fake
from lifeos.tests.base import OWNER, PRIVATE
from lifeos.tests.test_ux5_ask import AskCase, text


def put(feature, cost):
	frappe.get_doc({"doctype": "Life AI Usage", "user": OWNER, "month": client.month(), "model": "claude-sonnet-5-5", "cost": cost,
		"purpose": feature}).insert(ignore_permissions=True)


def set_feature_caps(value):
	import json

	frappe.db.set_single_value("Life Settings", "feature_caps", json.dumps(value))
	frappe.clear_cache(doctype="Life Settings")


def reply(t):
	return {"content": [text(t)], "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 5}}


class TestGateway(AskCase):
	def tearDown(self):
		set_feature_caps({})
		frappe.set_user("Administrator")
		frappe.db.delete("Life AI Usage")
		super().tearDown()

	def test_only_the_ai_client_imports_anthropic(self):
		"""I27.1: nothing outside lifeos/ai/client.py imports the SDK."""
		root = os.path.dirname(os.path.dirname(__file__))
		found = []
		for folder, dirs, files in os.walk(root):
			dirs[:] = [d for d in dirs if d not in ("node_modules", "public", "tests", "__pycache__")]
			for f in files:
				path = os.path.join(folder, f)
				if f.endswith(".py") and path != os.path.join(root, "ai", "client.py"):
					with open(path) as fh:
						for line in fh:
							if line.lstrip().startswith(("import anthropic", "from anthropic")):
								found.append(path)
		self.assertEqual(found, [])

	def test_a_call_records_feature_model_tokens_and_cost(self):
		"""I27.2: feature, model, tokens, the record it was for and the user; cached tokens are priced as cached."""
		self.script({"content": [text("ok")], "stop_reason": "end_turn",
			"usage": {"input_tokens": 1_000_000, "output_tokens": 100_000, "cached_tokens": 2_000_000, "cache_write_tokens": 400_000}})
		client.call("Area guess", "s", [{"role": "user", "content": "x"}], kind="short", reference=("Life Task", "T-1"))
		u = frappe.get_all("Life AI Usage", fields=["*"])[0]
		self.assertEqual((u.purpose, u.model, u.input_tokens, u.output_tokens, u.cached_tokens), ("Area guess", "claude-haiku-5-5", 1_000_000, 100_000, 2_000_000))
		self.assertEqual((u.reference_doctype, u.reference_name, u.user), ("Life Task", "T-1", OWNER))
		# haiku: input 0.10, output 0.50, cached 0.01, cache write 0.125 per million tokens
		self.assertAlmostEqual(u.cost, 0.10 + 0.05 + 0.02 + 0.05, places=6)

	def test_over_the_monthly_cap_the_caller_gets_its_fallback(self):
		"""I27.3: the call is refused and the area guess falls back to its rules (no answer from the model)."""
		put("Ask", 31)
		backend = self.script(reply("never sent"))
		with self.assertRaises(client.CapReached):
			client.call("Ask", "s", [{"role": "user", "content": "x"}])
		task = frappe.get_doc({"doctype": "Life Task", "title": "Pay the water bill", "space": PRIVATE})
		self.assertIsNone(area_guess.ask_model(task, [frappe._dict(name="A-1", area_name="Home", parent_area=None, description="")]))
		self.assertEqual(backend.received, [])

	def test_a_feature_cap_refuses_only_that_feature(self):
		"""I27.4"""
		put("Insights", 2)
		set_feature_caps({"Insights": 1.5})
		backend = self.script(reply("a"))
		with self.assertRaises(client.CapReached) as e:
			client.call("Insights", "s", [{"role": "user", "content": "x"}])
		self.assertIn("Insights has reached its own cap", str(e.exception))
		self.assertEqual(client.text_of(client.call("Ask", "s", [{"role": "user", "content": "x"}])["content"]), "a")
		self.assertEqual(len(backend.received), 1)
