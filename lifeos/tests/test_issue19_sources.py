"""Issue 19: Brain > Sources. Cards with this week's counts, a source switched off refuses captures, Coming tiles stay off, defaults apply."""
import frappe

from lifeos.api import connections, inbox, jobs
from lifeos.tests.base import PRIVATE, LifeTestCase


class TestSources(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Connection", {"space": PRIVATE})

	def card(self, system):
		return next(c for c in connections.sources(space=PRIVATE)["connected"] if c["system"] == system)

	def test_cards_count_this_weeks_captures_from_the_database(self):
		for i in range(3):
			inbox.create_item(title=f"i19 hermes {i}", source_system="hermes", space=PRIVATE)
		inbox.create_item(title="i19 mail", source_system="gmail", space=PRIVATE)
		frappe.db.set_value("Life Inbox Item", {"title": "i19 hermes 0"}, "creation", "2020-01-01 10:00:00")  # an old one does not count
		got = connections.sources(space=PRIVATE)
		by = {c["system"]: c for c in got["connected"]}
		mine = frappe.db.count("Life Inbox Item", {"space": PRIVATE, "source_system": "hermes", "creation": (">=", connections._week_start())})
		self.assertEqual((by["hermes"]["this_week"], mine), (2, 2))
		self.assertIn("2 this week", by["hermes"]["line"])
		self.assertIn("only people, not newsletters", by["gmail"]["line"])
		self.assertEqual(by["hermes"]["kind"], "Agent · Telegram")
		self.assertNotIn("hermes", [t["system"] for t in got["available"]])
		self.assertEqual(got["available"][0]["system"], "upload")

	def test_switching_hermes_off_refuses_its_captures_and_on_again_works(self):
		inbox.create_item(title="i19 first", source_system="hermes", space=PRIVATE)
		name = frappe.db.get_value("Life Connection", {"space": PRIVATE, "system": "hermes"})
		connections.save(name=name, active=0)
		with self.assertRaises(frappe.PermissionError) as e:
			inbox.create_item(title="i19 off", source_system="hermes", space=PRIVATE)
		self.assertIn("switched off", str(e.exception))
		with self.assertRaises(frappe.PermissionError):
			jobs.file_job(job_id="i19-job", source_system="Hermes", space=PRIVATE)
		self.assertFalse(frappe.db.exists("Life Inbox Item", {"title": "i19 off"}))
		inbox.create_item(title="i19 upload", source_type="Upload", source_system="upload", space=PRIVATE)  # Upload is always on
		connections.save(name=name, active=1)
		self.assertEqual(inbox.create_item(title="i19 on", source_system="hermes", space=PRIVATE)["title"], "i19 on")
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE, "title": "i19 first"}), 1)  # nothing was deleted

	def test_a_coming_tile_cannot_be_switched_on(self):
		got = connections.sources(space=PRIVATE)
		self.assertEqual(sorted(t["system"] for t in got["coming"]), ["drive", "erpnext", "github", "tally", "wearable", "whatsapp"])
		with self.assertRaises(frappe.ValidationError):
			connections.save(space=PRIVATE, system="github", active=1)
		self.assertFalse(frappe.db.exists("Life Connection", {"space": PRIVATE, "system": "github"}))

	def test_saved_defaults_are_what_create_item_uses(self):
		goal = self.make("Life Goal", title="i19 goal", goal_type="Open", area=self.areas["Tea"]).name
		c = connections.save(space=PRIVATE, system="gmail", default_area=self.areas["Tea"], default_goal=goal, default_intent="Just keep")
		self.assertEqual((c["label"], c["default_intent"], c["default_goal"]), ("Gmail", "Just keep", goal))
		item = inbox.create_item(title="i19 mail", source_system="gmail", space=PRIVATE)
		self.assertEqual((item["intent"], item["area"], item["goal"]), ("Just keep", self.areas["Tea"], goal))
