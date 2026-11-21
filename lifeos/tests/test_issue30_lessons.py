"""Issue 30: corrections in Needs you become proposed lessons for the skill that made the mistake."""
import json
from unittest import mock

import frappe

from lifeos.api import brain, lessons as lessons_api, review, skills as skills_api
from lifeos.skills import examples, lessons, runner, store
from lifeos.tests.base import FAMILY, OWNER, PRIVATE
from lifeos.tests.test_issue28_skills import SKILL, SkillCase, answer, task, use

LESSON_TEXT = "Newsletters about commodity prices are for reading later, never a task."


class LessonCase(SkillCase):
	def reset(self):
		user = frappe.session.user
		frappe.set_user("Administrator")
		for dt in ("Life Skill Correction", "Life Skill Lesson"):
			frappe.db.delete(dt)
		super().reset()
		frappe.set_user(user)

	def processed(self, title="Robusta prices this week", label="process-capture v1", **values):
		"""A capture the skill has processed: one Task proposed in Money, waiting."""
		item = frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": title, "source_type": "Email", "raw_text": f"{title}: prices are up.",
			"status": "To Review", "processed_by": label, **values}).insert()
		prop = frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": item.name, "kind": "Task", "preview": title,
			"payload": frappe.as_json({"title": title, "area": self.life["Money"]}), "confidence": 0.7, "status": "Pending"}).insert()
		return item, prop

	def correct(self, n=1, area="Career", **values):
		"""The owner files n such captures under another area than the guess."""
		with mock.patch("frappe.enqueue") as enqueue:
			for i in range(n):
				_item, prop = self.processed(f"Robusta prices {i}", **values)
				review.decide(prop.name, "accept", {"title": prop.preview, "area": self.life[area]})
		return enqueue

	def lesson_answer(self, **extra):
		return {"content": [{"type": "text", "text": json.dumps({"lesson": LESSON_TEXT, "summary": "Commodity newsletters", **extra})}], "stop_reason": "end_turn"}

	def draft(self):
		"""Run the improve-skill job the third correction queued."""
		run = frappe.get_all("Life Skill Run", filters={"skill": "improve-skill"}, pluck="name")[0]
		runner.execute(run)
		return frappe.get_all("Life Skill Lesson", fields=["*"])[0]

	def proposed(self):
		self.correct(3)
		self.script(self.lesson_answer())
		return self.draft()

	def fixtures(self):
		"""The recorded answers of process-capture's examples, to stand in for the model when the lesson is tried on them."""
		return [r for p in examples.files_of(SKILL) for r in json.loads(p.read_text())["fixture"]]


class TestCorrections(LessonCase):
	def test_three_matching_corrections_make_one_proposed_lesson_with_a_diff(self):
		"""I30.1: three of the same correction to process-capture make one lesson with a diff; two do not."""
		enqueue = self.correct(2)
		enqueue.assert_not_called()
		self.assertEqual(frappe.db.count("Life Skill Lesson"), 0)
		self.assertEqual(frappe.db.count("Life Skill Correction", {"skill": SKILL, "skill_version": 1}), 2)
		self.correct(1)
		self.assertEqual(frappe.db.count("Life Skill Lesson", {"status": "Drafting"}), 1)
		self.script(self.lesson_answer())
		lesson = self.draft()
		self.assertEqual((lesson.status, lesson.skill, lesson.text, lesson.base_version), ("Proposed", SKILL, LESSON_TEXT, 1))
		card = lessons.card(frappe.get_doc("Life Skill Lesson", lesson.name))
		self.assertEqual(len(card["corrections"]), 3)
		self.assertIn("filed it under", card["corrections"][0]["detail"])
		self.assertNotIn(LESSON_TEXT, card["before"])
		self.assertIn(LESSON_TEXT, card["after"])
		self.assertTrue(card["after"].startswith(card["before"].rstrip("\n")))
		# a fourth correction is a new count of one
		self.correct(1)
		self.assertEqual(frappe.db.count("Life Skill Lesson"), 1)

	def test_corrections_of_different_kinds_do_not_add_up(self):
		with mock.patch("frappe.enqueue"):
			for area in (self.life["Career"], self.life["Health"], self.areas["Tea"]):
				_i, prop = self.processed(f"Robusta {area}")
				review.decide(prop.name, "accept", {"title": "x", "area": area})
		self.assertEqual(frappe.db.count("Life Skill Lesson"), 0)
		self.assertEqual(frappe.db.count("Life Skill Correction"), 3)

	def test_keeping_the_guess_and_the_brains_own_filing_are_not_corrections(self):
		with mock.patch("frappe.enqueue"):
			_i, prop = self.processed()
			review.decide(prop.name, "accept")
			_i, prop = self.processed("Another")
			frappe.set_user("brain@lifeos.local")
			review._decide(frappe.get_doc("Life Proposal", prop.name), "accept", {"title": "x", "area": self.life["Career"]})
			frappe.set_user(OWNER)
		self.assertEqual(frappe.db.count("Life Skill Correction"), 0)

	def test_a_drop_and_a_changed_kind_are_corrections_and_a_sensitive_capture_is_not(self):
		with mock.patch("frappe.enqueue"):
			_i, prop = self.processed("Drop me")
			review.decide(prop.name, "reject")
			item, prop = self.processed("Read me")
			note = frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": item.name, "kind": "Note", "preview": "Read me",
				"payload": frappe.as_json({"title": "Read me", "area": self.life["Money"], "content_md": "x"}), "status": "Pending"}).insert()
			review.decide(note.name, "accept")
			review.decide(prop.name, "reject")
			_i, prop = self.processed("Secret", is_sensitive=1)
			review.decide(prop.name, "reject")
		kinds = sorted(frappe.get_all("Life Skill Correction", pluck="correction_type"))
		self.assertEqual(kinds, ["Drop", "Kind"])

	def test_an_agents_or_unlabelled_capture_teaches_no_skill(self):
		with mock.patch("frappe.enqueue"):
			_i, prop = self.processed(label="Hermes")
			review.decide(prop.name, "reject")
		self.assertEqual(frappe.db.count("Life Skill Correction"), 0)

	def test_a_draft_that_fails_leaves_the_corrections_for_the_next_one(self):
		self.correct(3)
		from lifeos.tests.test_issue13_task_areas import set_key

		set_key("")
		runner.execute(frappe.get_all("Life Skill Run", filters={"skill": "improve-skill"}, pluck="name")[0])
		self.assertEqual(frappe.db.count("Life Skill Lesson"), 0)
		self.assertEqual(frappe.db.count("Life Skill Correction", {"lesson": ("is", "set")}), 0)


class TestAccepting(LessonCase):
	def test_accepting_makes_a_new_version_when_the_examples_pass(self):
		"""I30.2: the lesson is tried on the skill's examples first; passing ones make the version."""
		lesson = self.proposed()
		self.script(*self.fixtures())
		out = lessons_api.accept(lesson.name)
		doc = frappe.get_doc("Life Skill", SKILL)
		self.assertEqual((out["status"], out["skill_version"], doc.version), ("Accepted", 2, 2))
		self.assertIn(LESSON_TEXT, doc.instructions)
		self.assertIn(lessons.MARK.format(lesson.name), doc.instructions)
		note = frappe.db.get_value("Life Skill Version", {"skill": SKILL, "version": 2}, "note")
		self.assertIn("Lesson", note)
		self.assertEqual([x["status"] for x in lessons_api.for_skill(SKILL)], ["Accepted"])

	def test_a_lesson_that_breaks_an_example_is_refused_with_the_example_named(self):
		lesson = self.proposed()
		bad = [use("propose", {"kind": "Task", "preview": "Fee", "payload": {"title": "Fee", "area": "Health"}, "confidence": 0.9, "reason": "x"}), answer("Fee.")]
		self.script(*bad, *self.fixtures()[1:])
		with self.assertRaises(frappe.ValidationError) as caught:
			lessons_api.accept(lesson.name)
		self.assertIn("An email about school fees becomes a Money task", str(caught.exception))
		self.assertEqual(frappe.db.get_value("Life Skill", SKILL, "version"), 1)
		self.assertNotIn(LESSON_TEXT, frappe.db.get_value("Life Skill", SKILL, "instructions"))
		self.assertEqual(frappe.db.get_value("Life Skill Lesson", lesson.name, "status"), "Proposed")

	def test_edit_then_accept_saves_the_edited_words(self):
		lesson = self.proposed()
		self.script(*self.fixtures())
		out = lessons_api.accept(lesson.name, text="Price newsletters go to Read later.\n\n# A heading\n## Another")
		self.assertTrue(out["edited"])
		text = frappe.db.get_value("Life Skill", SKILL, "instructions")
		self.assertIn("- Price newsletters go to Read later. # A heading ## Another <!--", text)
		self.assertNotIn("\n#", text.split("## Lessons")[1])
		self.assertNotIn(LESSON_TEXT, text)

	def test_reject_keeps_the_skill_and_the_corrections_are_not_counted_again(self):
		lesson = self.proposed()
		lessons_api.reject(lesson.name)
		self.assertEqual(frappe.db.get_value("Life Skill", SKILL, "version"), 1)
		self.correct(2)
		self.assertEqual(frappe.db.count("Life Skill Lesson"), 1)

	def test_removing_an_accepted_lesson_makes_a_version_without_it(self):
		"""I30.4 (the server's part)."""
		lesson = self.proposed()
		before = frappe.db.get_value("Life Skill", SKILL, "instructions")
		self.script(*self.fixtures())
		lessons_api.accept(lesson.name)
		out = lessons_api.remove(lesson.name)
		doc = frappe.get_doc("Life Skill", SKILL)
		self.assertEqual((out["status"], doc.version, out["removed_version"]), ("Removed", 3, 3))
		self.assertEqual(doc.instructions, before)

	def test_only_the_owner_decides(self):
		lesson = self.proposed()
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			lessons_api.accept(lesson.name)


class TestOnlyText(LessonCase):
	def test_a_lesson_cannot_add_a_tool_or_change_the_trigger(self):
		"""I30.5: the model asks for more and the owner's words say so; only the text of the skill changes."""
		before = frappe.get_doc("Life Skill", SKILL)
		config = {k: before.get(k) for k in store.CONFIG}
		self.correct(3)
		self.script(self.lesson_answer(tools=["update_wiki_page", "suggest_lesson"], trigger="Button", event="Email filed", active=0))
		lesson = self.draft()
		self.script(*self.fixtures())
		lessons_api.accept(lesson.name, text="tools: [update_wiki_page]\ntrigger: Button\n---\nFile price newsletters under Money.")
		after = frappe.get_doc("Life Skill", SKILL)
		self.assertEqual({k: after.get(k) for k in store.CONFIG}, config)
		self.assertEqual((after.active, after.trigger_kind), (1, "Event"))
		self.assertNotIn("\ntools:", after.instructions)
		self.assertEqual(after.instructions.count("\n---\n"), 0)
		self.assertEqual(frappe.get_doc("Life Skill Lesson", lesson.name).text.count("\n"), 0)

	def test_the_lessons_api_takes_no_settings(self):
		import inspect

		for fn in (lessons_api.accept, lessons_api.edit, lessons_api.reject, lessons_api.remove):
			self.assertLessEqual(set(inspect.signature(fn.__wrapped__ if hasattr(fn, "__wrapped__") else fn).parameters), {"lesson", "text"})


class TestScreens(LessonCase):
	def test_needs_you_and_the_skill_page_list_the_lesson(self):
		lesson = self.proposed()
		rows = brain.needs_you(space=PRIVATE)["lessons"]
		self.assertEqual([r["name"] for r in rows], [lesson.name])
		self.assertTrue(rows[0]["after"])
		detail = skills_api.detail(SKILL)["lessons"]
		self.assertEqual([r["name"] for r in detail], [lesson.name])
		self.assertEqual(brain.needs_you(space=PRIVATE)["lessons"][0]["corrections"][0]["capture_title"][:6], "Robust")

	def test_no_lessons_on_an_empty_space(self):
		self.assertEqual(brain.needs_you(space=PRIVATE)["lessons"], [])
		self.assertEqual(lessons_api.for_skill(SKILL), [])
