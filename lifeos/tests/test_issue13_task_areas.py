"""Issue 13: every task has an area; the Brain guesses one when it is missing."""
import json

import frappe

from lifeos import area_guess
from lifeos.ai import fake
from lifeos.api import tasks
from lifeos.patches.v12 import task_areas as patch
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase


def set_key(value):
	user = frappe.session.user
	frappe.set_user("Administrator")
	s = frappe.get_single("Life Settings")
	s.anthropic_api_key = value
	s.monthly_cap_usd = 30
	s.save()
	frappe.clear_cache(doctype="Life Settings")
	frappe.set_user(user)


def answer_with(area_name, confidence):
	"""A scripted model answer naming the id the prompt gave `area_name`."""
	def run(params):
		_slug, data = fake.asked(params)
		pick = next(a["id"] for a in data["areas"] if a["name"] == area_name)
		return {"content": [{"type": "text", "text": json.dumps({"area": pick, "confidence": confidence})}]}
	return run


class NoModel:
	"""A backend that fails the test if it is called."""

	calls = 0

	def run(self, params, on_text=None):
		NoModel.calls += 1
		raise AssertionError("the model was called")


class TestTaskAreas(LifeTestCase):
	def task(self, title, **values):
		return self.make("Life Task", title=title, status="Open", **values)

	def tearDown(self):
		frappe.flags.lifeos_ai_backend = None
		super().tearDown()

	# 1
	def test_a_task_with_a_goal_gets_the_goals_area(self):
		goal = self.make("Life Goal", title="i13 Grow the tea business", goal_type="Open", area=self.areas["Tea"])
		t = self.task("i13 Zqx call", goal=goal.name)
		self.assertEqual(t.area, self.areas["Tea"])
		self.assertTrue(t.area_guessed)
		self.assertGreaterEqual(t.area_confidence, 90)

	# 2
	def test_a_task_from_a_capture_gets_the_captures_area(self):
		item = self.make("Life Inbox Item", title="i13 Voice note", area=self.areas["Personal"])
		t = self.task("i13 Zqx follow", inbox_item=item.name)
		self.assertEqual(t.area, self.areas["Personal"])
		self.assertTrue(t.area_guessed)
		self.assertEqual(t.area_confidence, area_guess.CAPTURE_CONFIDENCE)

	# 3
	def test_a_task_titled_with_a_parts_name_gets_that_part(self):
		part = self.make("Life Area", area_name="i13 Mehi Motors", parent_area=self.life["Career"])
		t = self.task("Get Mehi Motors questionnaire scored")
		self.assertEqual(t.area, part.name)
		self.assertTrue(t.area_guessed)
		# words of a part's description count too: "Mithun" is only in the notes of the part
		blend = self.make("Life Area", area_name="i13 Blends", parent_area=self.life["Career"],
			description="Tea blends with Mithun and the tasters")
		t = self.task("Send Mithun the revised sheet")
		self.assertEqual(t.area, blend.name)

	# 4
	def test_the_model_guesses_when_nothing_else_does_and_no_key_falls_back(self):
		set_key("sk-test-not-real")
		backend = frappe.flags.lifeos_ai_backend = fake.ScriptedFake([answer_with("Money", 77)])
		t = self.task("Zqxv blorp")
		# the save itself never waits on the model: it files under Career and leaves the model to a job after the commit
		self.assertEqual((t.area, t.area_confidence, backend.received), (self.life["Career"], area_guess.FALLBACK_CONFIDENCE, []))
		area_guess.refine(t.name, t.area)  # the job
		t.reload()
		self.assertEqual(t.area, self.life["Money"])
		self.assertTrue(t.area_guessed)
		self.assertEqual(t.area_confidence, 77)
		self.assertFalse(frappe.db.exists("Life Action Log", {"task": t.name}))  # a better guess is not a correction
		sent = fake.asked(backend.received[0])[1]
		self.assertEqual(sent["title"], "Zqxv blorp")
		self.assertNotIn("Emotions", [a["name"] for a in sent["areas"]])  # only the areas that are on
		self.assertTrue(frappe.db.exists("Life AI Usage", {"purpose": "Skill: guess-area"}))
		# a guess the owner confirmed before the job ran is left alone
		t2 = self.task("Zqxv blorp confirmed")
		tasks.confirm_area(t2.name)
		self.assertIsNone(area_guess.refine(t2.name, self.life["Career"]))
		self.assertEqual(len(backend.received), 1)
		# without a key: no call, no error, Career with a low confidence
		set_key("")
		frappe.flags.lifeos_ai_backend = NoModel()
		calls = NoModel.calls
		t = self.task("Zqxv blorp again")
		self.assertIsNone(area_guess.refine(t.name, t.area))
		self.assertEqual(NoModel.calls, calls)
		self.assertEqual(t.area, self.life["Career"])
		self.assertTrue(t.area_guessed)
		self.assertLessEqual(t.area_confidence, 30)

	# 5
	def test_confirm_area_clears_the_mark_and_a_move_is_logged(self):
		t = self.task("Zqxv one")
		self.assertTrue(t.area_guessed)
		out = tasks.confirm_area(t.name)
		self.assertFalse(out["area_guessed"])
		self.assertEqual(out["area"], self.life["Career"])
		self.assertFalse(frappe.db.exists("Life Action Log", {"task": t.name}))

		t2 = self.task("Zqxv two")
		out = tasks.confirm_area(t2.name, self.life["Health"])
		self.assertEqual(out["area"], self.life["Health"])
		self.assertFalse(out["area_guessed"])
		log = frappe.get_all("Life Action Log", filters={"task": t2.name}, fields=["kind", "old_area", "new_area", "space"])
		self.assertEqual([(r.kind, r.old_area, r.new_area, r.space) for r in log],
			[("Area correction", self.life["Career"], self.life["Health"], PRIVATE)])
		frappe.delete_doc("Life Task", t2.name)  # a correction does not block deleting the task, and goes with it
		self.assertFalse(frappe.db.exists("Life Action Log", {"task": t2.name}))

		# changing a guessed area through the task's own edit clears the mark and is logged too
		t3 = self.task("Zqxv three")
		out = tasks.update(t3.name, {"area": self.areas["Tea"]})
		self.assertFalse(out["area_guessed"])
		self.assertTrue(frappe.db.exists("Life Action Log", {"task": t3.name, "new_area": self.areas["Tea"]}))
		# a task filed by a person is not marked
		self.assertFalse(self.task("Zqxv four", area=self.life["Health"]).area_guessed)

	# 6
	def test_the_patch_fills_every_task_without_an_area_and_calls_no_model(self):
		goal = self.make("Life Goal", title="i13 Patch goal", goal_type="Open", area=self.areas["Tea"])
		made = {}
		for title, values in (("Zqxv patch goal task", {"goal": goal.name}), ("Patch the personal things", {}),
				("Zqxv patch", {}), ("Zqxv patch done", {"status": "Done"})):
			t = self.make("Life Task", title=title, **{"status": "Open", **values})
			frappe.db.set_value("Life Task", t.name, {"area": None, "area_guessed": 0, "area_confidence": 0})
			made[title] = t.name
		set_key("sk-test-not-real")
		frappe.flags.lifeos_ai_backend = NoModel()
		calls = NoModel.calls
		frappe.set_user("Administrator")
		patch.execute()
		self.assertEqual(NoModel.calls, calls)
		self.assertFalse(frappe.db.count("Life Task", {"area": ("is", "not set"), "status": ("in", ["Open", "Doing", "Waiting"]),
			"space": PRIVATE}))
		got = {r.name: r for r in frappe.get_all("Life Task", filters={"name": ("in", list(made.values()))},
			fields=["name", "area", "area_guessed"])}
		self.assertEqual(got[made["Zqxv patch goal task"]].area, self.areas["Tea"])
		self.assertEqual(got[made["Patch the personal things"]].area, self.areas["Personal"])
		self.assertEqual(got[made["Zqxv patch"]].area, self.life["Career"])
		self.assertTrue(all(r.area_guessed for r in got.values()))
		# the index row follows
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_doctype": "Life Task", "ref_name": made["Zqxv patch"]}, "area"),
			self.life["Career"])
		set_key("")
		frappe.set_user(OWNER)
