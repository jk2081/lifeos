"""Plain tests for the connector's Hermes layout (no Frappe needed): python3 -m unittest agent/connector/test_connector.py"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("connector", Path(__file__).with_name("connector.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class HermesLayout(unittest.TestCase):
	def setUp(self):
		self.home = Path(tempfile.mkdtemp())
		for d in ("memories", "skills/productivity/lifeos", "skills/email/digest", "cron"):
			(self.home / d).mkdir(parents=True)
		(self.home / "memories/MEMORY.md").write_text("A note.\n")
		(self.home / "memories/USER.md").write_text("User is Jai.\n§\nPrefers mornings.\n§\n")
		(self.home / "skills/productivity/lifeos/SKILL.md").write_text("---\nname: lifeos\ndescription: Work the Life OS inbox\n---\n")
		(self.home / "skills/email/digest/SKILL.md").write_text("# Digest\nRead mail daily.\n")
		(self.home / "cron/jobs.json").write_text(json.dumps({"jobs": [{"id": "a1", "name": "Morning digest", "schedule": {"display": "0 7 * * *"}, "enabled": True}]}))

	def test_snapshot_reads_hermes_files(self):
		s = c.snapshot(self.home)
		self.assertEqual([f["text"] for f in s["facts"]], ["A note.", "User is Jai.", "Prefers mornings."])
		self.assertEqual({x["name"]: x["description"] for x in s["skills"]}, {"digest": "Read mail daily.", "lifeos": "Work the Life OS inbox"})
		self.assertEqual(s["jobs"][0]["schedule"], "0 7 * * *")
		self.assertFalse(s["jobs"][0]["paused"])

	def test_changes_are_written_back(self):
		facts = c.snapshot(self.home)["facts"]
		c.apply_change(self.home, {"kind": "Fact edit", "target": facts[2]["id"], "payload": {"text": "Calls before 11."}})
		self.assertEqual((self.home / "memories/USER.md").read_text(), "User is Jai.\n§\nCalls before 11.\n")
		c.apply_change(self.home, {"kind": "Fact delete", "target": facts[0]["id"]})
		self.assertEqual(c.hermes_entries(self.home / "memories/MEMORY.md"), [])
		c.apply_change(self.home, {"kind": "Job pause", "target": "a1"})
		self.assertIs(json.loads((self.home / "cron/jobs.json").read_text())["jobs"][0]["enabled"], False)
		with self.assertRaises(RuntimeError):
			c.apply_change(self.home, {"kind": "Fact delete", "target": "gone"})


if __name__ == "__main__":
	unittest.main()
