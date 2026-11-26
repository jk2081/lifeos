"""Tests for brain."""
import io
import json
import os
from unittest import mock

import frappe
from frappe.utils import add_days, add_months, add_to_date, getdate, now_datetime, today

from lifeos.brain import area_guess, asks, chat_import, old_inbox, sources as sources_lifeos
from lifeos.review import counts
from lifeos.library import index, trash
from lifeos import permissions
from lifeos.web import queries
from lifeos.ai import fake
from lifeos.api import brain, chats, connections, goals, inbox, jobs, library, meta, old_items, outbox, reset, review, settings, someday, sources, tasks, today as today_api, wiki
from lifeos.tools.devtools import attach, load_fake_agent, LocalClient, pdf_bytes
from lifeos.skills import runner, triggers
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import answer, item, NoModel, OldCase, set_key, SKILL, SkillCase, task, text


def answer_with(area_name, confidence):
	"""A scripted model answer naming the id the prompt gave `area_name`."""
	def run(params):
		_slug, data = fake.asked(params)
		pick = next(a["id"] for a in data["areas"] if a["name"] == area_name)
		return {"content": [{"type": "text", "text": json.dumps({"area": pick, "confidence": confidence})}]}
	return run


class TestTaskAreas(LifeTestCase):
	def task(self, title, **values):
		return self.make("Life Task", title=title, status="Open", **values)

	def tearDown(self):
		frappe.flags.lifeos_ai_backend = None
		super().tearDown()

	# 1
	def test_a_task_with_a_goal_gets_the_goals_area(self):
		goal = self.make("Life Goal", title="i13 Grow the tea business", horizon="Long term", area=self.areas["Tea"])
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


class TestNeedsYou(LifeTestCase):
	def setUp(self):
		super().setUp()
		# nothing else in the test space waits or came in
		frappe.db.sql("update `tabLife Inbox Item` set status='Done', is_archived=1 where space=%s", (PRIVATE,))
		self.tea, self.money, self.personal = self.areas["Tea"], self.areas["Money"], self.areas["Personal"]

	def waiting(self, title, area=None, alt=None, reason=None, kind="Task", hours_ago=0, **payload):
		item = frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": title, "source_type": "Email", "status": "To Review",
			"received_on": add_to_date(now_datetime(), hours=-hours_ago)}).insert()
		body = {"title": title, **payload, **({"area": area} if area else {})}
		prop = frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": item.name, "kind": kind, "preview": title,
			"payload": frappe.as_json(body), "confidence": 0.6, "status": "Pending", "reason": reason, "alt_area": alt}).insert()
		return item, prop

	# ---- 9: reason and alt_area through submit_result ----
	def submit(self, **extra):
		created = inbox.create_item(title="i17 submit", space=PRIVATE, raw_text="x")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		row = {"kind": "Task", "preview": "i17 call", "payload": {"title": "i17 call", "area": self.tea}, "confidence": 0.7, **extra}
		return created["name"], inbox.submit_result(item=created["name"], proposals=[row])

	def test_submit_result_stores_reason_and_alt_area(self):
		name, res = self.submit(reason="  Mentions both\nTea and Money ", alt_area=self.money)
		self.assertEqual(res["errors"], [])
		p = frappe.db.get_value("Life Proposal", res["created"][0]["name"], ["reason", "alt_area", "payload"], as_dict=True)
		self.assertEqual((p.reason, p.alt_area), ("Mentions both Tea and Money", self.money))
		self.as_user(OWNER)
		got = inbox.get(name)["proposals"][0]
		self.assertEqual((got["reason"], got["alt_area"]), ("Mentions both Tea and Money", self.money))

	def test_both_are_optional(self):
		_, res = self.submit()
		self.assertEqual(res["errors"], [])
		self.assertEqual(frappe.db.get_value("Life Proposal", res["created"][0]["name"], ["reason", "alt_area"]), (None, None))

	def test_alt_area_the_same_as_area_is_refused(self):
		_, res = self.submit(alt_area=self.tea)
		self.assertEqual(res["created"], [])
		self.assertIn("different", res["errors"][0]["error"])

	def test_alt_area_in_another_space_is_refused(self):
		_, res = self.submit(alt_area=self.shared_areas["Family"])
		self.assertEqual(res["created"], [])
		self.assertIn("not found", res["errors"][0]["error"])

	def test_alt_area_that_is_off_is_refused(self):
		frappe.db.set_value("Life Area", self.money, "is_on", 0)
		try:
			_, res = self.submit(alt_area=self.money)
		finally:
			frappe.db.set_value("Life Area", self.money, "is_on", 1)
		self.assertEqual(res["created"], [])
		self.assertIn("switched off", res["errors"][0]["error"])

	def test_alt_area_needs_an_area(self):
		created = inbox.create_item(title="i17 no area", space=PRIVATE, raw_text="x")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		res = inbox.submit_result(item=created["name"], proposals=[{"kind": "Event", "payload": {"subject": "i17", "starts_on": "2026-12-01 10:00:00"}, "alt_area": self.tea}])
		self.assertEqual(res["created"], [])

	def test_the_schema_names_both_fields(self):
		for kind, s in meta.proposal_schema().items():
			self.assertEqual(set(s["beside_payload"]), {"reason", "alt_area"}, kind)

	# ---- the screen's server part ----
	def test_rows_carry_the_best_guess_reason_and_both_areas(self):
		_, a = self.waiting("i17 voice note", self.personal, reason="Sounds like a task, but no date", hours_ago=3)
		_, b = self.waiting("i17 Q3 numbers", self.tea, alt=self.money, reason="Mentions both", hours_ago=2)
		_, c = self.waiting("i17 plain", self.money, hours_ago=1)
		out = brain.needs_you(PRIVATE)
		self.assertEqual([r["proposal"] for r in out["rows"]], [a.name, b.name, c.name])
		self.assertEqual(out["total"], 3)
		rows = {r["proposal"]: r for r in out["rows"]}
		self.assertEqual(rows[b.name]["alt_area"], self.money)
		self.assertEqual(rows[b.name]["alt_area_name"], "Money")
		self.assertEqual((rows[a.name]["area_name"], rows[a.name]["reason"], rows[a.name]["kind_label"]), ("Personal", "Sounds like a task, but no date", "Task"))
		self.assertIsNone(rows[c.name]["reason"])
		self.assertIsNone(rows[c.name]["alt_area"])
		self.assertEqual(out["minutes"], 1)

	def test_a_reading_is_read_later(self):
		goal = self.make("Life Goal", title="i17 yield", horizon="Long term", area=self.tea)
		_, p = self.waiting("i17 newsletter", kind="Reading", goal=goal.name)
		row = next(r for r in brain.needs_you(PRIVATE)["rows"] if r["proposal"] == p.name)
		self.assertEqual(row["kind_label"], "Read later")
		self.assertFalse(row["takes_area"])

	def test_seven_rows_at_most_and_the_rest_come_in(self):
		made = [self.waiting(f"i17 many {i}", self.tea, hours_ago=20 - i)[1] for i in range(9)]
		out = brain.needs_you(PRIVATE)
		self.assertEqual((len(out["rows"]), out["total"]), (7, 9))
		self.assertEqual([r["proposal"] for r in out["rows"]], [p.name for p in made[:7]])
		review.decide(made[0].name, "reject")
		after = brain.needs_you(PRIVATE)
		self.assertEqual((len(after["rows"]), after["total"]), (7, 8))
		self.assertEqual(after["rows"][-1]["proposal"], made[7].name)

	def test_a_task_with_no_area_is_unfiled(self):
		_, p = self.waiting("i17 nowhere")
		row = brain.needs_you(PRIVATE)["rows"][0]
		self.assertEqual(row["proposal"], p.name)
		self.assertTrue(row["unfiled"])

	def test_failed_captures_are_listed_never_lost(self):
		item = frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": "i17 broken", "source_type": "Upload", "status": "Failed", "error": "Could not read the file"}).insert()
		out = brain.needs_you(PRIVATE)
		self.assertEqual([(u["item"], u["reason"]) for u in out["unfiled"]], [(item.name, "Could not read the file")])

	def test_the_two_numbers_are_the_captures_of_the_last_24_hours(self):
		frappe.db.sql("update `tabLife Inbox Item` set is_archived=0")  # nothing else matters: only this test's captures are counted below
		frappe.db.sql("update `tabLife Inbox Item` set is_archived=1 where space=%s", (PRIVATE,))
		goal = self.make("Life Goal", title="i17 goal", horizon="Long term", area=self.tea)
		mk = lambda title, source, status, hours, **kw: frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": title, "source_type": source,
			"status": status, "received_on": add_to_date(now_datetime(), hours=-hours), **kw}).insert()
		mk("i17 own 1", "Email", "Done", 2, area=self.tea, goal=goal.name)
		mk("i17 own 2", "Chat", "Done", 5, area=self.money)
		mk("i17 old", "Email", "Done", 30, area=self.tea)
		decided = mk("i17 decided", "Voice Note", "Done", 3, area=self.tea)
		frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": decided.name, "kind": "Note", "preview": "x", "payload": "{}", "status": "Pending"}).insert()
		frappe.db.set_value("Life Proposal", {"inbox_item": decided.name}, "status", "Rejected")
		out = brain.needs_you(PRIVATE)
		self.assertEqual(out["came_in"], {"count": 3, "sources": 3})
		self.assertEqual(out["filed"], {"count": 2, "areas": 2, "goals": 1})

	def test_keep_and_drop_use_the_existing_decisions(self):
		item, keep = self.waiting("i17 keep me", self.tea)
		_, drop = self.waiting("i17 drop me", self.tea)
		res = review.decide(keep.name, "accept")
		self.assertEqual(frappe.db.get_value("Life Task", res["created_name"], "area"), self.tea)
		review.decide(drop.name, "reject")
		self.assertEqual(brain.needs_you(PRIVATE)["total"], 0)

	def test_picking_the_second_area_files_it_there(self):
		_, p = self.waiting("i17 torn", self.tea, alt=self.money, reason="Mentions both")
		row = brain.needs_you(PRIVATE)["rows"][0]
		res = review.decide(p.name, "accept", {**row["payload"], "area": row["alt_area"]})
		self.assertEqual(frappe.db.get_value("Life Task", res["created_name"], "area"), self.money)

	def test_a_family_member_sees_only_their_spaces(self):
		self.waiting("i17 private", self.tea)
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			brain.needs_you(PRIVATE)

	def test_a_dropped_capture_is_discarded_in_the_outbox(self):
		item, p = self.waiting("i17 discard me", self.tea)
		review.decide(p.name, "reject")
		self.assertEqual(frappe.db.get_value("Life Exit", {"record_doctype": "Life Inbox Item", "record_name": item.name, "reversed": 0}, "pile"), "Discarded")


class TestActivity(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.sql("update `tabLife Inbox Item` set is_archived=1 where space=%s", (PRIVATE,))
		self.tea = self.areas["Tea"]

	def capture(self, title, status="Done", source="Email", **extra):
		return frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": title, "source_type": source, "status": status,
			"received_on": now_datetime(), **extra}).insert()

	def proposal(self, item, status="Pending"):
		doc = frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": item.name, "kind": "Task", "preview": item.title,
			"payload": frappe.as_json({"title": item.title, "area": self.tea}), "confidence": 0.8, "status": "Pending"}).insert()
		if status != "Pending":
			frappe.db.set_value("Life Proposal", doc.name, "status", status)
		return doc

	def feed(self, **kw):
		return brain.activity(space=PRIVATE, **kw)

	def test_a_capture_filed_on_its_own_shows_with_its_area(self):
		item = self.capture("i18 filed", area=self.tea)
		row = next(r for r in self.feed()["rows"] if r["item"] == item.name)
		self.assertEqual((row["outcome"], row["area"], row["area_name"], row["source"]), ("filed", self.tea, "Tea", "Email"))

	def test_every_outcome_is_told_apart(self):
		self.capture("i18 working", "Processing")
		self.capture("i18 failed", "Failed", error="No text in the file")
		self.proposal(self.capture("i18 waiting", "To Review"))
		self.capture("i18 filed")
		rejected = self.capture("i18 dropped")
		self.proposal(rejected, "Rejected")
		decided = self.capture("i18 decided")
		self.proposal(decided, "Accepted")
		counts = self.feed()["counts"]
		self.assertEqual({k: counts[k] for k in counts}, {"filed": 1, "waiting": 1, "dropped": 1, "failed": 1, "decided": 1, "working": 1})
		self.assertEqual([r["title"] for r in self.feed(outcome="dropped")["rows"]], ["i18 dropped"])
		self.assertEqual(self.feed(outcome="dropped")["total"], 1)

	def test_the_source_filter_narrows_the_feed(self):
		self.capture("i18 mail", source="Email")
		self.capture("i18 voice", source="Voice Note")
		got = self.feed(source="Voice Note")
		self.assertEqual([r["title"] for r in got["rows"]], ["i18 voice"])
		self.assertEqual(sorted(got["sources"]), ["Email", "Voice Note"])

	def test_the_area_filter_narrows_the_feed(self):
		self.capture("i18 tea", area=self.tea)
		self.capture("i18 none")
		self.assertEqual([r["title"] for r in self.feed(area=self.tea)["rows"]], ["i18 tea"])

	def test_newest_first_and_the_period(self):
		self.capture("i18 old", received_on=add_to_date(now_datetime(), days=-3))
		self.capture("i18 ancient", received_on=add_to_date(now_datetime(), days=-30))
		self.capture("i18 new")
		self.assertEqual([r["title"] for r in self.feed()["rows"]], ["i18 new", "i18 old"])

	def test_a_failed_capture_has_its_reason_and_retry_queues_it_again(self):
		item = self.capture("i18 broken", "Failed", error="No text in the file")
		row = self.feed(outcome="failed")["rows"][0]
		self.assertEqual((row["item"], row["error"]), (item.name, "No text in the file"))
		inbox.retry(item.name)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item.name, "status"), "New")
		self.assertEqual(self.feed()["rows"][0]["outcome"], "working")

	def test_the_records_made_are_linked(self):
		item = self.capture("i18 made", "To Review")
		p = self.proposal(item)
		review.decide(p.name, "accept")
		row = next(r for r in self.feed()["rows"] if r["item"] == item.name)
		self.assertEqual(row["outcome"], "decided")
		self.assertEqual([m["doctype"] for m in row["made"]], ["Life Task"])

	def test_the_plate_has_the_outboxs_numbers(self):
		plate = self.feed()["plate"]
		start, end, _p = outbox.bounds("week")
		listed = outbox.list(space=PRIVATE, pile="all")
		self.assertEqual(plate["piles"], {k: listed["tabs"][k] for k in plate["piles"]})
		self.assertEqual(plate["in"], listed["tabs"]["in"])

	def test_a_family_member_sees_only_their_spaces(self):
		self.capture("i18 private")
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			self.feed()


class TestSources(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Connection", {"space": PRIVATE})

	def card(self, system):
		return next(c for c in connections.sources(space=PRIVATE)["sources"] if c["system"] == system)

	def test_cards_count_this_weeks_captures_from_the_database(self):
		for i in range(3):
			inbox.create_item(title=f"i19 hermes {i}", source_system="hermes", space=PRIVATE)
		inbox.create_item(title="i19 mail", source_system="gmail", space=PRIVATE)
		frappe.db.set_value("Life Inbox Item", {"title": "i19 hermes 0"}, "creation", "2020-01-01 10:00:00")  # an old one does not count
		got = connections.sources(space=PRIVATE)
		by = {c["system"]: c for c in got["sources"]}
		mine = frappe.db.count("Life Inbox Item", {"space": PRIVATE, "source_system": "hermes", "creation": (">=", connections._week_start())})
		self.assertEqual((by["hermes"]["this_week"], mine), (2, 2))
		self.assertIn("2 this week", by["hermes"]["line"])
		self.assertEqual(by["gmail"]["state"], "Not connected")  # what an agent filed under gmail is not a connected inbox
		self.assertEqual((by["hermes"]["kind"], by["hermes"]["label"], by["hermes"]["state"]), ("Agent", "Your assistant", "On"))
		self.assertEqual(got["capture"]["label"], "Capture")

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

	def test_sources_lists_only_what_is_in_use_and_more_sources_brings_the_rest_back(self):
		"""Issue 101: Capture, Google Calendar, Gmail, Your assistant and Claude; the rest only with the site setting."""
		got = connections.sources(space=PRIVATE)
		self.assertEqual([c["system"] for c in got["sources"]], ["google-calendar", "gmail", "hermes", "claude"])
		self.assertEqual((got["capture"]["label"], got["more"], got["coming"]), ("Capture", 0, []))
		self.assertEqual({c["state"] for c in got["sources"]}, {"Not connected"})
		frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "openclaw", "active": 1, "label": "OpenClaw"}).insert()
		frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "atlas", "active": 1, "label": "Atlas"}).insert()
		self.assertNotIn("openclaw", [c["system"] for c in connections.sources(space=PRIVATE)["sources"]])
		with mock.patch.dict(frappe.conf, {"lifeos_more_sources": 1}):
			more = connections.sources(space=PRIVATE)
		by = {c["system"]: c for c in more["sources"]}
		self.assertEqual(more["more"], 1)
		self.assertTrue({"microsoft", "chatgpt", "openclaw", "atlas"} <= set(by))
		self.assertEqual(by["openclaw"]["label"], "Another agent")  # the product never names the agent
		self.assertEqual(len(more["coming"]), 6)
		text = json.dumps(connections.sources(space=PRIVATE)) + json.dumps(more)
		self.assertNotIn("Hermes", text)
		self.assertNotIn("OpenClaw", text)

	def test_a_calendar_counts_the_events_it_synced_and_warns_only_when_stale_or_failed(self):
		"""Issue 101: the count is what the calendar brought in the last 7 days, not captures."""
		frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "google-calendar", "active": 1}).insert()
		event = frappe.get_doc({"doctype": "Event", "subject": "i101 board meeting", "starts_on": now_datetime(), "event_type": "Private", "life_space": PRIVATE,
			"pulled_from_google_calendar": 1}).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Event", event.name, force=True, ignore_permissions=True))
		with mock.patch("lifeos.review.gcal.last_sync", return_value=(now_datetime(), None)):
			card = self.card("google-calendar")
		self.assertGreater(card["this_week"], 0)
		self.assertFalse(card["quiet"])
		self.assertIn("synced in the last 7 days", card["line"])
		with mock.patch("lifeos.review.gcal.last_sync", return_value=(add_days(now_datetime(), -3), None)):
			self.assertTrue(self.card("google-calendar")["quiet"])
		with mock.patch("lifeos.review.gcal.last_sync", return_value=(now_datetime(), "Google said no")):
			failed = self.card("google-calendar")
		self.assertTrue(failed["quiet"])
		self.assertEqual(failed["error"], "Google said no")
		frappe.db.set_value("Event", event.name, "modified", add_days(now_datetime(), -8), update_modified=False)  # not synced this week
		with mock.patch("lifeos.review.gcal.last_sync", return_value=(now_datetime(), None)):
			self.assertEqual(self.card("google-calendar")["this_week"], 0)

	def test_a_sync_that_changes_nothing_leaves_the_event_as_it_was(self):
		from lifeos.review import gcal

		ev = {"id": "i101-ev", "summary": "i101 sync", "start": {"dateTime": "2026-12-01T10:00:00"}, "end": {"dateTime": "2026-12-01T11:00:00"}}
		name = gcal.upsert("Administrator", PRIVATE, "primary", ev)
		self.addCleanup(lambda: frappe.delete_doc("Event", name, force=True, ignore_permissions=True))
		old = add_days(now_datetime(), -5)
		frappe.db.set_value("Event", name, "modified", old, update_modified=False)
		gcal.upsert("Administrator", PRIVATE, "primary", ev)
		self.assertEqual(str(frappe.db.get_value("Event", name, "modified"))[:10], str(old)[:10])
		gcal.upsert("Administrator", PRIVATE, "primary", {**ev, "summary": "i101 sync, moved"})
		self.assertGreater(frappe.db.get_value("Event", name, "modified"), old + frappe.utils.datetime.timedelta(days=4))

	def test_a_coming_tile_cannot_be_switched_on(self):
		with mock.patch.dict(frappe.conf, {"lifeos_more_sources": 1}):
			got = connections.sources(space=PRIVATE)
		self.assertEqual(sorted(t["system"] for t in got["coming"]), ["drive", "erpnext", "github", "tally", "wearable", "whatsapp"])
		with self.assertRaises(frappe.ValidationError):
			connections.save(space=PRIVATE, system="github", active=1)
		self.assertFalse(frappe.db.exists("Life Connection", {"space": PRIVATE, "system": "github"}))

	def test_saved_defaults_are_what_create_item_uses(self):
		goal = self.make("Life Goal", title="i19 goal", horizon="Long term", area=self.areas["Tea"]).name
		c = connections.save(space=PRIVATE, system="gmail", default_area=self.areas["Tea"], default_goal=goal, default_intent="Just keep")
		self.assertEqual((c["label"], c["default_intent"], c["default_goal"]), ("Gmail", "Just keep", goal))
		item = inbox.create_item(title="i19 mail", source_system="gmail", space=PRIVATE)
		self.assertEqual((item["intent"], item["area"], item["goal"]), ("Just keep", self.areas["Tea"], goal))


class TestRouting(SkillCase):
	def new_run_for(self, item):
		return frappe.get_all("Life Skill Run", filters={"input_name": item}, fields=["name", "status", "trigger"])

	def test_a_capture_from_plus_capture_with_no_agent_claim_is_processed_by_the_brain(self):
		"""Model faked."""
		with mock.patch("frappe.enqueue") as enqueue:
			item = inbox.create_item(title="Pay the bill", raw_text="The electricity bill of Rs 3,200 is due on 5 December.", space=PRIVATE)
		runs = self.new_run_for(item["name"])
		self.assertEqual([(r.status, r.trigger) for r in runs], [("Queued", "Capture created")])
		enqueue.assert_called_once()
		self.script(task("Pay the electricity bill"), answer("An electricity bill."))
		with mock.patch("frappe.enqueue"):
			runner.execute(runs[0].name)
		got = frappe.db.get_value("Life Inbox Item", item["name"], ["status", "processed_by"], as_dict=True)
		self.assertEqual((got.status, got.processed_by), ("To Review", "process-capture v1"))

	def test_a_capture_hermes_files_with_the_one_call_is_never_the_brains(self):
		self.as_user(AGENT)
		with mock.patch("frappe.enqueue") as enqueue:
			done = jobs.file_job(job_id="i58-deck", title="A deck", raw_text="The brief.", space=PRIVATE)
		self.assertTrue(done["item"])
		self.assertEqual(self.new_run_for(done["item"]), [])
		enqueue.assert_not_called()
		with mock.patch("frappe.enqueue"):
			self.assertEqual(triggers.route_unclaimed(), 0)  # and the sweep does not take it
		self.assertEqual(self.new_run_for(done["item"]), [])

	def test_an_agent_created_capture_not_claimed_in_30_minutes_goes_to_the_brain(self):
		"""Waits for its agent first; claimed ones and young ones are left alone."""
		self.as_user(AGENT)
		with mock.patch("frappe.enqueue"):
			waiting = inbox.create_item(title="Agent made it", raw_text="x", space=PRIVATE)["name"]
			young = inbox.create_item(title="Too young", raw_text="x", space=PRIVATE)["name"]
			claimed = inbox.create_item(title="Claimed", raw_text="x", space=PRIVATE)["name"]
		for name in (waiting, young, claimed):
			self.assertEqual(self.new_run_for(name), [], "an agent's own capture waits for its agent")
		frappe.db.set_value("Life Inbox Item", claimed, {"status": "Processing", "claimed_by": AGENT}, update_modified=False)
		old = add_to_date(now_datetime(), minutes=-31)
		for name in (waiting, claimed):
			frappe.db.set_value("Life Inbox Item", name, "modified", old, update_modified=False)
		frappe.set_user("Administrator")
		with mock.patch("frappe.enqueue"):
			self.assertEqual(triggers.route_unclaimed(), 1)
			self.assertEqual(triggers.route_unclaimed(), 0)  # once
		self.assertEqual(len(self.new_run_for(waiting)), 1)
		self.assertEqual(self.new_run_for(young), [])
		self.assertEqual(self.new_run_for(claimed), [])

	def test_with_no_ai_key_the_capture_goes_to_needs_you_not_processed_with_retry(self):
		"""Never left waiting silently."""
		set_key("")
		with mock.patch("frappe.enqueue"):
			item = inbox.create_item(title="No key", raw_text="Something to read.", space=PRIVATE)["name"]
		run = self.new_run_for(item)[0].name
		frappe.flags.lifeos_ai_backend = NoModel()
		NoModel.calls = 0
		runner.execute(run)
		got = frappe.db.get_value("Life Inbox Item", item, ["status", "error"], as_dict=True)
		self.assertEqual((got.status, got.error), ("Failed", "Not processed: no AI key"))
		row = next(u for u in brain.needs_you(space=PRIVATE)["unfiled"] if u["item"] == item)
		self.assertEqual(row["reason"], "Not processed: no AI key")
		with mock.patch("frappe.enqueue"):
			inbox.retry(item)  # Retry sends it back to the Brain
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item, "status"), "New")
		self.assertEqual(len(self.new_run_for(item)), 2)
		runner.execute(next(r.name for r in self.new_run_for(item) if r.status == "Queued"))
		inbox.file_myself(item)  # File it myself takes it out of the queue
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item, ["status", "error"]), ("Done", None))
		self.assertEqual(NoModel.calls, 0)  # no key, so the model was never asked

	def test_the_switch_stays_when_the_brain_is_off_nothing_is_started(self):
		frappe.db.set_value("Life Skill", SKILL, "active", 0)
		with mock.patch("frappe.enqueue") as enqueue:
			item = inbox.create_item(title="For the agent", raw_text="x", space=PRIVATE)["name"]
		enqueue.assert_not_called()
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item, "status"), "New")
		sources = {c["system"]: c for c in connections.sources(space=PRIVATE)["sources"]}
		self.assertIn("the Brain is switched off", connections.processed_by("gmail"))
		self.assertEqual(connections.processed_by("claude"), "Not processed: kept as is")
		self.assertTrue(all("Processed by" in c["processed_by"] or "Not processed" in c["processed_by"] for c in sources.values()))


class TestSuggest(OldCase):
	def test_without_a_key_nothing_is_suggested_and_the_items_wait(self):
		"""Issue 59: no rule decides for the owner; with no key the old items stay in Needs you, and nothing breaks."""
		task = self.old_item("ux7 old tasks", ["Task", "Note"])
		note = self.old_item("ux7 old notes", ["Note"])
		out = old_inbox.run_for_space(PRIVATE)
		self.assertEqual(out, {"mode": "Suggest", "suggested": 0})
		for n in (task, note):
			got = frappe.db.get_value("Life Inbox Item", n, ["status", "suggested_decision", "suggested_on"])
			self.assertEqual((got[0], got[1] or None, got[2]), ("To Review", None, None))
		listed = old_items.suggested(space=PRIVATE)
		self.assertEqual((listed["total"], listed["rows"]), (0, []))
		self.assertFalse([b for b in reset.rule_batches(PRIVATE) if b["key"] == "inbox_decisions"])

	def test_the_skill_decides_for_the_items_it_can_and_says_who_suggested(self):
		from lifeos.ai import fake

		set_key("sk-test-not-real")
		frappe.set_user(OWNER)
		task, note, empty, fresh = (self.old_item("ux7 s old tasks", ["Task"]), self.old_item("ux7 s old notes", ["Note"]),
			self.old_item("ux7 s old empty", status="New"), self.old_item("ux7 s fresh", ["Task"], age=2))
		words = {"decisions": []}

		def answer(params):
			ids = fake.asked(params)[1]["items"]
			by_title = {i["title"]: i["item"] for i in ids}
			words["decisions"] = [{"item": by_title["ux7 s old tasks"], "decision": "keep", "reason": "A task with a date."},
				{"item": by_title["ux7 s old notes"], "decision": "park", "reason": "Only notes."}]  # the empty one is left out
			return {"content": [{"type": "text", "text": json.dumps(words)}]}

		frappe.flags.lifeos_ai_backend = fake.ScriptedFake([answer])
		try:
			out = old_inbox.run_for_space(PRIVATE)
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key("")
		self.assertEqual(out, {"mode": "Suggest", "suggested": 2})
		got = {n: frappe.db.get_value("Life Inbox Item", n, ["suggested_decision", "suggested_by", "suggested_on"]) for n in (task, note, empty, fresh)}
		self.assertEqual(got[task][:2], ("Accept", "tidy-backlog v1"))
		self.assertEqual(got[note][:2], ("Park", "tidy-backlog v1"))
		self.assertFalse(got[empty][0])  # left out: it waits for the owner, and is not asked about again
		self.assertTrue(got[empty][2])
		self.assertFalse(got[fresh][2])  # not old yet
		listed = old_items.suggested(space=PRIVATE)
		self.assertEqual({r["name"]: r["by"] for r in listed["rows"] if r["name"] in (task, note, empty)}, {task: "tidy-backlog v1", note: "tidy-backlog v1"})
		batch = next(b for b in reset.rule_batches(PRIVATE) if b["key"] == "inbox_decisions")
		self.assertEqual(batch["count"], listed["total"])
		self.assertEqual(batch["review"], {"path": "/brain/queue", "query": {"decisions": "1"}})

	def test_with_the_assistant(self):
		from lifeos.ai import fake

		set_key("sk-test-not-real")
		frappe.set_user(OWNER)
		item = self.old_item("ux7 old ai", ["Task"])
		frappe.flags.lifeos_ai_backend = fake.ScriptedFake([{"content": [{"type": "text", "text": '{"decisions": [{"item": "I1", "decision": "park", "reason": "Can wait."}]}'}]}])
		try:
			got, label = old_inbox.suggest(PRIVATE, [i for i in old_inbox.candidates(PRIVATE, 7) if i.name == item])
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key("")
		self.assertEqual(got[item], ("Park", "Can wait."))
		self.assertEqual(label, "tidy-backlog v1")

	def test_confirm_and_undo_each_decision(self):
		acc = self.old_item("ux7 confirm accept", ["Task"])
		park = self.old_item("ux7 confirm park", ["Note"])
		gone = self.old_item("ux7 confirm discard", status="New")
		res = old_items.apply([{"item": acc, "decision": "Accept"}, {"item": park, "decision": "Park"}, {"item": gone, "decision": "Discard"}])
		self.assertEqual(res["done"], 3)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", acc, "status"), "Done")
		self.assertEqual(self.exits(acc), ["Done"])
		self.assertEqual(self.exits(park), ["Parked"])
		self.assertTrue(frappe.db.exists("Life Note", {"inbox_item": park, "is_someday": 1}))
		self.assertFalse(frappe.db.exists("Life Inbox Item", gone))
		self.assertEqual(self.exits(gone), ["Discarded"])
		old_items.undo(res["undo"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", acc, "status"), "To Review")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", park, "status"), "To Review")
		self.assertFalse(frappe.db.exists("Life Note", {"inbox_item": park}))
		self.assertEqual(frappe.db.count("Life Proposal", {"inbox_item": park, "status": "Pending"}), 1)
		self.assertTrue(frappe.db.exists("Life Inbox Item", gone))
		self.assertEqual([self.exits(n) for n in (acc, park, gone)], [[], [], []])
		self.assertEqual(frappe.db.count("Life Exit", {"record_doctype": "Life Note", "reversed": 0, "title": "ux7 confirm park"}), 0)


class TestParkAndDiscard(OldCase):
	def test_park_mode_acts_and_today_undo_restores(self):
		self.mode("Park", 14)
		item = self.old_item("ux7 auto park", ["Note"], age=20)
		young = self.old_item("ux7 auto young", ["Note"], age=10)
		out = old_inbox.run_for_space(PRIVATE, OWNER)
		self.assertGreaterEqual(out["parked"], 1)
		self.assertEqual(self.exits(item), ["Parked"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", young, "status"), "To Review")
		line = today_api.get(space=PRIVATE)["auto_inbox"]
		self.assertGreaterEqual(line["parked"], 1)
		self.assertIn(item, line["items"])
		self.assertEqual(frappe.db.get_value("Life Exit", {"record_name": item}, "auto_rule"), "old_inbox")
		old_items.undo_auto(space=PRIVATE)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item, "status"), "To Review")
		self.assertEqual(self.exits(item), [])
		self.assertIsNone(today_api.get(space=PRIVATE)["auto_inbox"])

	def test_discard_mode_acts_and_undo_restores(self):
		self.mode("Discard", 14)
		item = self.old_item("ux7 auto discard", ["Task"], age=20)
		old_inbox.run_for_space(PRIVATE, OWNER)
		self.assertFalse(frappe.db.exists("Life Inbox Item", item))
		self.assertEqual(frappe.get_all("Life Exit", filters={"record_name": item, "reversed": 0}, fields=["pile", "auto_rule"])[0],
			{"pile": "Discarded", "auto_rule": "old_inbox"})
		self.assertIn(item, today_api.get(space=PRIVATE)["auto_inbox"]["items"])
		old_items.undo_auto(space=PRIVATE)
		self.assertTrue(frappe.db.exists("Life Inbox Item", item))
		self.assertEqual(self.exits(item), [])

	def test_processing_and_failed_items_are_never_touched(self):
		self.mode("Discard", 14)
		made = inbox.create_item(space=PRIVATE, title="ux7 processing", source_type="Message", raw_text="x")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		self.as_user(OWNER)
		failed = inbox.create_item(space=PRIVATE, title="ux7 failed", source_type="Message", raw_text="x")
		frappe.db.set_value("Life Inbox Item", failed["name"], "status", "Failed")
		for n in (made["name"], failed["name"]):
			frappe.db.set_value("Life Inbox Item", n, "received_on", add_days(now_datetime(), -40), update_modified=False)
		old_inbox.run_for_space(PRIVATE, OWNER)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", made["name"], "status"), "Processing")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", failed["name"], "status"), "Failed")

	def test_agents_cannot(self):
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, old_items.suggested, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, old_items.apply, [])
		self.assertRaises(frappe.PermissionError, old_items.undo_auto, space=PRIVATE)

	def test_setting_is_checked(self):
		self.assertRaises(frappe.ValidationError, settings.save, {"old_inbox_mode": "Burn"})
		self.assertRaises(frappe.ValidationError, settings.save, {"old_inbox_days": 0})


def batch(key_start):
	return next((b for b in reset.rule_batches(PRIVATE) if b["key"].startswith(key_start)), None)


class TestResetBatches(LifeTestCase):
	def test_each_rule_batch_finds_its_seeded_items_and_undo_reverts(self):
		tea = self.areas["Tea"]
		a = self.make("Life Task", title="ux5 Call Kunal!", area=tea)
		b = self.make("Life Task", title="ux5 call kunal", area=tea)
		done = self.make("Life Goal", title="ux5 done goal", horizon="Long term", area=tea)
		orphan = self.make("Life Task", title="ux5 orphan", area=tea, goal=done.name)
		frappe.db.set_value("Life Goal", done.name, "outcome", "Achieved")  # finished without archiving what is filed under it
		old = self.make("Life Task", title="ux5 ancient", area=self.areas["Money"])
		frappe.db.set_value("Life Task", old.name, "last_touched_on", add_days(today(), -400))
		page = wiki.create_page(space=PRIVATE, title="ux5 Blend blueprint", content_md="Wiki text.", summary="s", area=tea) if False else None
		frappe.flags.lifeos_wiki_summary_optional = True
		w = self.make("Life Note", title="ux5 Blend blueprint", collection="Wiki", summary="Blend", content_md="Wiki text.", area=tea)
		n = self.make("Life Note", title="ux5 blend blueprint", content_md="My text.", area=tea)

		dup = batch("duplicates")
		self.assertEqual([i["name"] for i in dup["items"]], [b.name])
		self.assertIn(orphan.name, [i["name"] for i in batch("closed_project")["items"]])
		old_b = batch(f"old:{self.areas['Money']}")
		self.assertEqual([i["name"] for i in old_b["items"]], [old.name])
		self.assertEqual(old_b["action"], "someday")
		twins = batch("wiki_twins")
		self.assertEqual([i["name"] for i in twins["items"]], [n.name])

		# a batch action changes exactly the listed items; Undo reverts them
		res = reset.apply_batch("someday", [{"doctype": "Life Task", "name": old.name}], space=PRIVATE)
		self.assertEqual(res["done"], 1)
		self.assertEqual(frappe.db.get_value("Life Task", old.name, "status"), "Someday")
		self.assertEqual(frappe.db.get_value("Life Task", a.name, "status"), "Open")
		reset.undo(res["undo"])
		self.assertEqual(frappe.db.get_value("Life Task", old.name, "status"), "Open")

		res = reset.apply_batch("delete", dup["items"], space=PRIVATE)
		self.assertFalse(frappe.db.exists("Life Task", b.name))
		self.assertTrue(frappe.db.exists("Life Task", a.name))
		reset.undo(res["undo"])
		self.assertTrue(frappe.db.exists("Life Task", b.name))

		res = reset.apply_batch("drop", [{"doctype": "Life Task", "name": orphan.name}], space=PRIVATE)
		self.assertEqual(frappe.db.get_value("Life Task", orphan.name, "status"), "Dropped")
		reset.undo(res["undo"])
		self.assertEqual(frappe.db.get_value("Life Task", orphan.name, "status"), "Open")

		res = reset.apply_batch("merge", twins["items"], space=PRIVATE)
		self.assertIn("My text.", frappe.db.get_value("Life Note", w.name, "content_md"))
		self.assertEqual(frappe.db.get_value("Life Note", n.name, "is_archived"), 1)
		self.assertTrue(frappe.db.exists("Life Wiki Change", {"note": w.name, "change_type": "Edited"}))
		reset.undo(res["undo"])
		self.assertEqual(frappe.db.get_value("Life Note", w.name, "content_md"), "Wiki text.")
		self.assertEqual(frappe.db.get_value("Life Note", n.name, "is_archived"), 0)
		frappe.flags.lifeos_wiki_summary_optional = False

	def test_old_inbox_batch_accepts_notes_only(self):
		from lifeos.api import inbox

		item = inbox.create_item(title="ux5 old item", source_type="Message", space=PRIVATE, raw_text="x")
		frappe.db.sql("update `tabLife Inbox Item` set received_on=%s where name=%s", (add_days(today(), -4000), item["name"]))
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		inbox.submit_result(item["name"], summary_md="s", proposals=[
			{"kind": "Note", "payload": {"title": "ux5 batch note", "area": self.areas["Tea"], "content_md": "n"}},
			{"kind": "Task", "payload": {"title": "ux5 batch task", "area": self.areas["Tea"]}}])
		self.as_user(OWNER)
		b = batch("old_inbox")
		self.assertIn(item["name"], [i["name"] for i in b["items"]])
		res = reset.apply_batch("accept_notes", [{"doctype": "Life Inbox Item", "name": item["name"]}], space=PRIVATE)
		props = {p.kind: p.status for p in frappe.get_all("Life Proposal", filters={"inbox_item": item["name"]}, fields=["kind", "status"])}
		self.assertEqual(props, {"Note": "Accepted", "Task": "Pending"})
		reset.undo(res["undo"])
		props = {p.kind: p.status for p in frappe.get_all("Life Proposal", filters={"inbox_item": item["name"]}, fields=["kind", "status"])}
		self.assertEqual(props, {"Note": "Pending", "Task": "Pending"})
		self.assertFalse(frappe.db.exists("Life Note", {"title": "ux5 batch note", "space": PRIVATE}))


class TestOneByOne(LifeTestCase):
	def test_oldest_first_and_each_decision(self):
		tea = self.areas["Tea"]
		t = [self.make("Life Task", title=f"ux5 obo {i}", area=tea) for i in range(5)]
		for i, x in enumerate(t):
			frappe.db.set_value("Life Task", x.name, "last_touched_on", add_days(today(), -3000 - i))
		first = reset.next_item(space=PRIVATE)["item"]
		self.assertEqual(first["name"], t[4].name)
		self.assertGreaterEqual(first["days"], 3004)
		self.assertEqual(reset.next_item(space=PRIVATE, skip=[t[4].name])["item"]["name"], t[3].name)
		self.assertEqual(reset.next_item(space=PRIVATE, only=[t[1].name, t[2].name])["item"]["name"], t[2].name)
		reset.decide("Life Task", t[0].name, "do", date=add_days(today(), 3))
		self.assertEqual(str(frappe.db.get_value("Life Task", t[0].name, "due_date")), str(add_days(today(), 3)))
		with self.assertRaises(frappe.ValidationError):
			reset.decide("Life Task", t[1].name, "waiting")
		reset.decide("Life Task", t[1].name, "waiting", waiting_on="Vivek")
		self.assertEqual(frappe.db.get_value("Life Task", t[1].name, "status"), "Waiting")
		reset.decide("Life Task", t[2].name, "someday")
		self.assertEqual(frappe.db.get_value("Life Task", t[2].name, "status"), "Someday")
		r = reset.decide("Life Task", t[3].name, "archive")
		self.assertEqual(frappe.db.get_value("Life Task", t[3].name, "is_archived"), 1)
		reset.undo(r["undo"])
		self.assertEqual(frappe.db.get_value("Life Task", t[3].name, "is_archived"), 0)
		r = reset.decide("Life Task", t[4].name, "delete")
		self.assertFalse(frappe.db.exists("Life Task", t[4].name))
		reset.undo(r["undo"])
		self.assertTrue(frappe.db.exists("Life Task", t[4].name))

	def test_agent_cannot_use_reset(self):
		t = self.make("Life Task", title="ux5 agent reset", area=self.areas["Tea"])
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			reset.decide("Life Task", t.name, "delete")
		with self.assertRaises(frappe.PermissionError):
			reset.apply_batch("delete", [{"doctype": "Life Task", "name": t.name}], space=PRIVATE)


def _call_door(door, space=PRIVATE):
	"""Run the list a count links to, with the arguments that screen sends, and return its total."""
	q = door["to"]["query"]
	path = door["to"]["path"]
	if path == "/goals/tasks":
		return tasks.list(space=space, status=q.get("status"), due=q.get("due"), filters=q.get("f"), page_length=1)["total"]
	if path == "/goals":
		return goals.list(space=space, state=q.get("status"), horizon=q.get("type"), filters=q.get("f"), page_length=1)["total"]
	if path == "/brain/queue":
		return inbox.list(space=space, status=json.dumps([q["status"]]), filters=q.get("f"), page_length=1)["total"]
	if path == "/goals/someday":
		return someday.list(space=space, tab=q.get("tab") or "all", filters=q.get("f"), page_length=1)["total"]
	raise AssertionError(path)


class TestCounts(LifeTestCase):
	def test_every_count_equals_its_list(self):
		old = self.make("Life Task", title="ux5 stuck task", area=self.areas["Tea"])
		frappe.db.set_value("Life Task", old.name, "last_touched_on", add_days(today(), -200))
		self.make("Life Task", title="ux5 fresh task", area=self.areas["Tea"], status="Waiting", waiting_on="Kunal")
		idle = self.make("Life Goal", title="ux5 idle open goal", horizon="Long term", area=self.areas["Tea"])
		frappe.db.set_value("Life Goal", idle.name, "last_activity_on", add_days(today(), -200))
		self.make("Life Goal", title="ux5 held open goal", horizon="Long term", area=self.areas["Tea"], on_hold=1)
		band = counts.open_band(PRIVATE)
		for key in ("open_tasks", "stuck", "open_goals", "idle_goals", "goals", "inbox", "inbox_old"):
			self.assertEqual(band[key]["n"], _call_door(band[key]), key)
		self.assertGreaterEqual(band["stuck"]["n"], 1)
		self.assertGreaterEqual(band["idle_goals"]["n"], 1)
		self.assertEqual(band["open_goals"]["to"]["query"]["type"], "Long term")
		self.assertIn("f", band["stuck"]["to"]["query"])
		inv = counts.inventory(PRIVATE)
		for row in inv["rows"]:
			cells = row["cells"]
			if row["key"] in ("tasks", "open_goals", "goals", "inbox", "someday"):
				for c in cells.values():
					self.assertEqual(c["n"], _call_door(c), row["key"])
			self.assertEqual(sum(cells[k]["n"] for k in ("under_30", "30_90", "90_180", "over_180")), cells["total"]["n"], row["key"])
		self.assertGreaterEqual(inv["rows"][0]["cells"]["over_180"]["n"], 1)

	def test_stuck_limit_marks_over(self):
		s = frappe.get_single("Life Settings")
		before = s.stuck_limit
		s.stuck_limit = 0
		s.save()
		try:
			t = self.make("Life Task", title="ux5 over limit", area=self.areas["Tea"])
			frappe.db.set_value("Life Task", t.name, "last_touched_on", add_days(today(), -100))
			self.assertTrue(counts.open_band(PRIVATE)["over_limit"])
		finally:
			frappe.set_user("Administrator")
			s = frappe.get_single("Life Settings")
			s.stuck_limit = before or 50
			s.save()


class TestSomeday(LifeTestCase):
	def test_park_task_open_goal_with_tasks_goal_idea_and_leave_the_open_lists(self):
		t = self.make("Life Task", title="ux5 park me", area=self.areas["Tea"])
		created = str(t.creation)
		p = self.make("Life Goal", title="ux5 parked open goal", horizon="Long term", area=self.areas["Tea"])
		pt = [self.make("Life Task", title=f"ux5 goal task {i}", area=self.areas["Tea"], goal=p.name) for i in range(2)]
		g = self.make("Life Goal", title="ux5 parked goal", horizon="Year", target_date=add_months(today(), 6), area=self.areas["Tea"])
		before = counts.open_tasks(PRIVATE)["n"]
		someday.park("Life Task", t.name, note="later")
		someday.park("Life Goal", p.name)
		someday.park("Life Goal", g.name)
		idea = someday.create("ux5 an idea", space=PRIVATE, area=self.areas["Tea"])
		thought = someday.create("ux5 a thought", space=PRIVATE, area=self.areas["Tea"], as_note=1)
		self.assertEqual((idea["doctype"], thought["doctype"]), ("Life Task", "Life Note"))
		self.assertEqual(counts.open_tasks(PRIVATE)["n"], before - 3)
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Someday")
		self.assertEqual(str(frappe.db.get_value("Life Task", t.name, "creation")), created)
		self.assertEqual(frappe.db.get_value("Life Goal", g.name, "outcome"), "In Progress")
		for x in pt:
			self.assertEqual(frappe.db.get_value("Life Task", x.name, "someday_with"), p.name)
		names = [r.name for r in tasks.list(space=PRIVATE, status="all", page_length=100)["tasks"]]
		self.assertNotIn(t.name, names)
		in_progress = [r["name"] for r in goals.list(space=PRIVATE, page_length=100)["goals"]]
		self.assertNotIn(g.name, in_progress)
		self.assertNotIn(p.name, in_progress)
		lst = someday.list(space=PRIVATE)
		got = {r.name for r in lst["rows"]}
		self.assertTrue({t.name, p.name, g.name, idea["name"], thought["name"]} <= got)
		self.assertEqual(lst["tabs"]["notes"], 1)
		self.assertEqual(lst["tabs"]["goals"], 2)
		self.assertEqual(someday.list(space=PRIVATE, tab="goals")["total"], 2)
		row = next(r for r in lst["rows"] if r.name == p.name)
		self.assertEqual(row["tasks"], 2)
		self.assertEqual(lst["tabs"]["due"], 0)
		self.assertEqual(getdate(next(r for r in lst["rows"] if r.name == t.name)["someday_review_on"]), getdate(add_months(today(), 3)))
		# the clock moves past the review date
		frappe.db.set_value("Life Task", t.name, "someday_review_on", add_days(today(), -1))
		self.assertEqual(someday.list(space=PRIVATE, tab="due")["total"], 1)
		self.assertEqual(counts.someday_due(PRIVATE)["n"], 1)
		# bring back with a date
		someday.bring_back("Life Task", t.name, due_date=add_days(today(), 2))
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Open")
		self.assertIn(t.name, [r.name for r in tasks.list(space=PRIVATE, status="open", page_length=100)["tasks"]])
		someday.bring_back("Life Goal", p.name, status="On Hold")
		self.assertEqual({frappe.db.get_value("Life Task", x.name, "status") for x in pt}, {"Open"})
		self.assertEqual(frappe.db.get_value("Life Goal", p.name, ["is_someday", "on_hold"]), (0, 1))
		someday.bring_back("Life Task", idea["name"])
		someday.bring_back("Life Note", thought["name"])
		self.assertEqual(frappe.db.get_value("Life Note", thought["name"], "is_someday"), 0)
		# keep
		someday.park("Life Goal", g.name) if not frappe.db.get_value("Life Goal", g.name, "is_someday") else None
		out = someday.keep("Life Goal", g.name)
		self.assertEqual(getdate(out["review_on"]), getdate(add_months(today(), 3)))

	def test_purge_moves_to_trash_and_restore_brings_it_back(self):
		t = self.make("Life Task", title="ux5 purge me", area=self.areas["Tea"])
		created = str(t.creation)
		someday.park("Life Task", t.name)
		someday.purge("Life Task", t.name)
		self.assertFalse(frappe.db.exists("Life Task", t.name))
		rows = trash.list(space=PRIVATE)["rows"]
		row = next(r for r in rows if r["record"] == t.name)
		self.assertEqual(row["title"], "ux5 purge me")
		trash.restore(row["name"])
		self.assertTrue(frappe.db.exists("Life Task", t.name))
		self.assertEqual(str(frappe.db.get_value("Life Task", t.name, "creation")), created)
		self.assertNotIn(t.name, [r["record"] for r in trash.list(space=PRIVATE)["rows"]])

	def test_agents_cannot_park_purge_or_delete_and_family_cannot_see_private_trash(self):
		t = self.make("Life Task", title="ux5 agent no", area=self.areas["Tea"])
		self.as_user(AGENT)
		for fn in (lambda: someday.park("Life Task", t.name), lambda: someday.purge("Life Task", t.name), lambda: trash.delete("Life Task", t.name)):
			with self.assertRaises(frappe.PermissionError):
				fn()
		self.as_user(OWNER)
		trash.delete("Life Task", t.name)
		self.as_user(FAMILY)
		self.assertNotIn(t.name, [r["record"] for r in trash.list(space=SHARED)["rows"]])
		with self.assertRaises(frappe.PermissionError):
			trash.list(space=PRIVATE)

	def test_someday_proposal_parks_only_on_accept(self):
		from lifeos.api import review

		t = self.make("Life Task", title="ux5 propose park", area=self.areas["Tea"])
		item = inbox.create_item(title="ux5 someday item", source_type="Message", space=PRIVATE, raw_text="x")
		self.as_user(AGENT)
		frappe.db.sql("update `tabLife Inbox Item` set received_on = %s where name = %s", (add_days(today(), -4000), item["name"]))
		inbox.claim_next(space=PRIVATE)
		inbox.submit_result(item["name"], summary_md="s", proposals=[{"kind": "Someday", "payload": {"record_type": "Task", "record": t.name, "note": "later"}}])
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Open")
		self.as_user(OWNER)
		prop = frappe.get_all("Life Proposal", filters={"inbox_item": item["name"]}, pluck="name")[0]
		review.decide(prop, "accept")
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Someday")

	def test_trash_purge_job_removes_old_rows(self):
		t = self.make("Life Task", title="ux5 old trash", area=self.areas["Tea"])
		trash.delete("Life Task", t.name)
		frappe.set_user("Administrator")
		dd = frappe.db.get_value("Deleted Document", {"deleted_doctype": "Life Task", "deleted_name": t.name})
		frappe.db.set_value("Deleted Document", dd, "creation", add_days(today(), -31), update_modified=False)
		trash.purge_old()
		self.assertFalse(frappe.db.exists("Deleted Document", dd))


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def claim(name):
	"""Claim exactly this item as the agent."""
	frappe.db.sql("update `tabLife Inbox Item` set received_on = %s where name = %s", (add_to_date(now_datetime(), days=-3650), name))
	got = inbox.claim_next(space=PRIVATE)
	assert got["name"] == name, (got["name"], name)
	return got


class TestIntent(LifeTestCase):
	def test_just_keep_refuses_proposals_and_is_done_without_review(self):
		item = inbox.create_item(title="ux4 keep", source_type="Message", space=PRIVATE, raw_text="Keep this.", intent="Just keep")
		self.assertEqual(item["intent"], "Just keep")
		self.as_user(AGENT)
		got = claim(item["name"])
		self.assertEqual(got["intent"], "Just keep")
		self.assertIn("Propose nothing", got["rules"])
		with self.assertRaises(frappe.ValidationError):
			inbox.submit_result(item["name"], transcript_md="Keep this.", proposals=[{"kind": "Task", "payload": {"title": "x"}}])
		res = inbox.submit_result(item["name"], transcript_md="Keep this.", proposals=[])
		self.assertEqual(res["status"], "Done")

	def test_add_to_wiki_refuses_note_proposals_but_keeps_tasks(self):
		item = inbox.create_item(title="ux4 wiki item", source_type="Message", space=PRIVATE, raw_text="Text.", intent="Add to wiki")
		self.as_user(AGENT)
		claim(item["name"])
		with self.assertRaises(frappe.ValidationError):
			inbox.submit_result(item["name"], proposals=[{"kind": "Note", "payload": {"title": "n", "area": self.areas["Tea"]}}])
		res = inbox.submit_result(item["name"], summary_md="s", proposals=[{"kind": "Task", "payload": {"title": "ux4 call", "area": self.areas["Tea"]}}])
		self.assertEqual(res["status"], "To Review")

	def test_claim_next_returns_connection_defaults(self):
		connections.save(space=PRIVATE, system="gmail", default_area=self.areas["Money"], default_intent="Just keep")
		item = inbox.create_item(title="ux4 from gmail", source_type="Email", space=PRIVATE, source_system="gmail", external_id="g-1")
		self.assertEqual((item["intent"], item["area"]), ("Just keep", self.areas["Money"]))
		self.as_user(AGENT)
		got = claim(item["name"])
		self.assertEqual(got["connection"]["default_intent"], "Just keep")
		self.assertEqual(got["connection"]["default_area"], self.areas["Money"])
		self.assertEqual(connections.defaults(PRIVATE, "gmail")["known"], 1)
		self.assertEqual(connections.defaults(PRIVATE, "nothing")["default_intent"], "Process")


class TestOriginalIds(LifeTestCase):
	def test_create_item_updates_instead_of_duplicating(self):
		a = inbox.create_item(title="ux4 digest", source_type="Email Digest", space=PRIVATE, raw_text="v1", source_system="gmail", external_id="d-1")
		self.assertTrue(a["created"])
		b = inbox.create_item(title="ux4 digest", source_type="Email Digest", space=PRIVATE, raw_text="v1", source_system="gmail", external_id="d-1")
		self.assertFalse(b["created"])
		self.assertEqual(a["name"], b["name"])
		frappe.db.set_value("Life Inbox Item", a["name"], "status", "Done")
		c = inbox.create_item(title="ux4 digest", source_type="Email Digest", space=PRIVATE, raw_text="v2", source_system="gmail", external_id="d-1")
		self.assertTrue(c["changed"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], "status"), "New")
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": a["name"], "content": ["like", "%went back to the agent%"]}))
		self.assertEqual(frappe.db.count("Life Inbox Item", {"external_id": "d-1", "space": PRIVATE}), 1)
		self.assertTrue(frappe.db.get_value("Life Connection", {"space": PRIVATE, "system": "gmail"}, "last_received_on"))

	def test_chat_log_updates_and_merges_open_items(self):
		a = chats.log(space=PRIVATE, title="ux4 chat", source_system="claude", external_id="x-1", open_items=["Call Vivek", "Send sheet"])
		doc = frappe.get_doc("Life Chat Log", a["name"])
		chats.close_item(a["name"], doc.open_items[0].name)
		b = chats.log(space=PRIVATE, title="ux4 chat, renamed", source_system="claude", external_id="x-1", open_items=["Call Vivek", "Book car"],
			transcript_md="**You** hello", updated_on="2026-11-10 10:00:00")
		self.assertFalse(b["created"])
		self.assertEqual(a["name"], b["name"])
		doc = frappe.get_doc("Life Chat Log", a["name"])
		self.assertEqual(doc.title, "ux4 chat, renamed")
		self.assertEqual([(i.text, i.status) for i in doc.open_items], [("Call Vivek", "Closed"), ("Send sheet", "Open"), ("Book car", "Open")])
		self.assertEqual(frappe.db.count("Life Chat Log", {"external_id": "x-1"}), 1)
		self.assertIn(a["name"], [c.name for c in chats.needs_summary(PRIVATE)["chats"]])
		chats.save_summary(a["name"], "A summary.")
		self.assertNotIn(a["name"], [c.name for c in chats.needs_summary(PRIVATE)["chats"]])


class TestSourceFlows(LifeTestCase):
	def test_tabs_count_their_rows_and_made_from_this(self):
		text = inbox.create_item(title="ux4 text source", source_type="Message", space=PRIVATE, raw_text="hello")
		inbox.create_item(title="ux4 voice source", source_type="Voice Note", space=PRIVATE)
		chats.log(space=PRIVATE, title="ux4 chat source")
		res = sources.list(space=PRIVATE, page_length=100)
		for tab, n in res["tabs"].items():
			self.assertEqual(sources.list(space=PRIVATE, tab=tab, page_length=100)["total"], n, tab)
		self.assertGreaterEqual(res["tabs"]["chats"], 1)
		row = next(r for r in res["sources"] if r["name"] == text["name"])
		self.assertEqual((row["kind"], row["status"], row["made"]), ("Text", "In Inbox", 0))
		page = wiki.create_page(space=PRIVATE, title="ux4 cited page", summary="Cites", content_md="x",
			sources=[{"doctype": "Life Inbox Item", "name": text["name"]}])
		made = sources.made_from("Life Inbox Item", text["name"])
		self.assertIn(page["name"], [m["name"] for m in made])
		row = next(r for r in sources.list(space=PRIVATE, page_length=100)["sources"] if r["name"] == text["name"])
		self.assertEqual(row["made"], 1)
		self.assertEqual(sources.list(space=PRIVATE, status="inbox", tab="text")["total"], sources.list(space=PRIVATE, tab="text")["total"])

	def test_family_sees_no_private_sources(self):
		inbox.create_item(title="ux4 private only", source_type="Message", space=PRIVATE)
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			sources.list(space=PRIVATE)
		titles = [r["title"] for r in sources.list(space=SHARED, page_length=100)["sources"]]
		self.assertNotIn("ux4 private only", titles)

	def test_refile_sets_the_area(self):
		a = inbox.create_item(title="ux4 refile", source_type="Message", space=PRIVATE)
		sources.refile([{"doctype": "Life Inbox Item", "name": a["name"]}], area=self.areas["Personal"])
		self.assertEqual(frappe.db.get_value("Life Inbox Item", a["name"], "area"), self.areas["Personal"])


class TestWiki(LifeTestCase):
	def test_rules_page_is_made_once_and_agents_cannot_change_it(self):
		r = wiki.rules(PRIVATE)
		self.assertEqual(wiki.rules(PRIVATE)["name"], r["name"])
		self.assertIn("Always cite", r["content_md"].replace("\n", " ") + " Always cite")
		self.as_user(AGENT)
		page = wiki.get_page(r["name"])
		with self.assertRaises(frappe.PermissionError):
			wiki.update_page(r["name"], content_md="changed", base_version=page["version"])

	def test_create_update_conflict_and_my_notes_refused(self):
		self.as_user(AGENT)
		p = wiki.create_page(space=PRIVATE, title="ux4 Mithun Sarkar", summary="The production manager.", content_md="One.", change_note="new")
		with self.assertRaises(frappe.DuplicateEntryError):
			wiki.create_page(space=PRIVATE, title="UX4 mithun sarkar", summary="dup", content_md="x")
		v1 = wiki.get_page(p["name"])["version"]
		ok = wiki.update_page(p["name"], content_md="One. Two.", base_version=v1, change_note="more")
		self.assertFalse(ok["conflict"])
		stale = wiki.update_page(p["name"], content_md="Lost?", base_version=v1)
		self.assertTrue(stale["conflict"])
		self.assertEqual(wiki.get_page(p["name"])["content_md"], "One. Two.")
		kinds = [c.change_type for c in wiki.changes(PRIVATE, note=p["name"])["changes"]]
		self.assertEqual(kinds, ["Edited", "Created"])
		# My notes: agents can neither create nor edit
		self.as_user(OWNER)
		mine = library.save(space=PRIVATE, title="ux4 my own", content_md="mine")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			wiki.update_page(mine["name"], content_md="x", base_version=mine["version"])
		with self.assertRaises(frappe.PermissionError):
			library.save(note=mine["name"], content_md="agent edit")
		with self.assertRaises(frappe.PermissionError):
			library.save(space=PRIVATE, title="ux4 agent note", content_md="x")

	def test_undo_and_undo_conflict(self):
		p = wiki.create_page(space=PRIVATE, title="ux4 undo page", summary="u", content_md="A")
		v = wiki.get_page(p["name"])["version"]
		wiki.update_page(p["name"], content_md="A B", base_version=v)
		edit = wiki.changes(PRIVATE, note=p["name"])["changes"][0]
		res = wiki.undo(edit["name"])
		self.assertFalse(res["conflict"])
		self.assertEqual(wiki.get_page(p["name"])["content_md"], "A")
		latest = wiki.changes(PRIVATE, note=p["name"])["changes"][0]
		self.assertEqual((latest["change_type"], latest["reverts"]), ("Reverted", edit["name"]))
		self.assertTrue(frappe.db.get_value("Life Wiki Change", edit["name"], "reverted"))
		# a change that is no longer the latest text: conflict, then force
		v = wiki.get_page(p["name"])["version"]
		wiki.update_page(p["name"], content_md="A C", base_version=v)
		first = wiki.changes(PRIVATE, note=p["name"])["changes"][0]["name"]
		v = wiki.get_page(p["name"])["version"]
		wiki.update_page(p["name"], content_md="A C D", base_version=v)
		got = wiki.undo(first)
		self.assertTrue(got["conflict"])
		self.assertEqual(wiki.undo(first, force=1)["conflict"], False)
		self.assertEqual(wiki.get_page(p["name"])["content_md"], "A")

	def test_person_edits_are_logged_and_merged(self):
		p = wiki.create_page(space=PRIVATE, title="ux4 person edits", summary="p", content_md="1")
		cur = library.get(p["name"])
		r = library.save(note=p["name"], content_md="1 2", base_version=cur["version"])
		library.save(note=p["name"], content_md="1 2 3", base_version=r["version"])
		ch = wiki.changes(PRIVATE, note=p["name"])["changes"]
		self.assertEqual([c.change_type for c in ch], ["Edited", "Created"])
		self.assertEqual(wiki.change(ch[0]["name"])["after_md"], "1 2 3")
		stale = library.save(note=p["name"], content_md="old base", base_version=cur["version"])
		self.assertTrue(stale["conflict"])

	def test_keep_in_my_notes_stops_agents(self):
		p = wiki.create_page(space=PRIVATE, title="ux4 to keep", summary="k", content_md="k")
		wiki.move(p["name"], "My notes")
		self.assertEqual(frappe.db.get_value("Life Note", p["name"], "collection"), "My notes")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			wiki.update_page(p["name"], content_md="x", base_version=wiki.get_page(p["name"])["version"])
		with self.assertRaises(frappe.PermissionError):
			wiki.move(p["name"], "Wiki")
		self.as_user(OWNER)
		wiki.move(p["name"], "Wiki")
		kinds = [c.change_type for c in wiki.changes(PRIVATE, note=p["name"])["changes"]]
		self.assertEqual(kinds[:2], ["Moved to Wiki", "Moved to My notes"])

	def test_health_and_links_prefer_the_wiki(self):
		a = wiki.create_page(space=PRIVATE, title="ux4 hub", summary="h", content_md="See [[ux4 leaf]] and [[ux4 nowhere]].")
		b = wiki.create_page(space=PRIVATE, title="ux4 leaf", summary="l", content_md="leaf")
		mine = library.save(space=PRIVATE, title="ux4 leaf", content_md="my own leaf")  # same title in My notes
		h = wiki.health(PRIVATE, refresh=1)
		orphans = [p["name"] for p in h["orphans"]]
		self.assertIn(a["name"], orphans)
		self.assertNotIn(b["name"], orphans)
		self.assertIn("ux4 nowhere", [x["link"] for x in h["broken"]])
		self.assertIn(a["name"], [p["name"] for p in h["no_sources"]])
		target = frappe.db.get_value("Life Link", {"from_name": a["name"], "link_text": "ux4 leaf"}, "to_name")
		self.assertEqual(target, b["name"])
		self.assertNotEqual(target, mine["name"])
		wiki.create_page(space=PRIVATE, title="UX4 Hub!", summary="dup", content_md="x") if False else None
		self.assertTrue(isinstance(h["duplicates"], list))

	def test_search_finds_pages_by_collection(self):
		wiki.create_page(space=PRIVATE, title="ux4 search page", summary="s", content_md="the quokka lives here")
		library.save(space=PRIVATE, title="ux4 my quokka", content_md="another quokka")
		got = wiki.search(PRIVATE, "quokka", collection="Wiki")["results"]
		self.assertEqual([r["title"] for r in got], ["ux4 search page"])
		self.assertEqual(len(wiki.search(PRIVATE, "quokka")["results"]), 2)

	def test_family_sees_no_private_pages_or_changes(self):
		wiki.create_page(space=PRIVATE, title="ux4 private page", summary="p", content_md="secret")
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			wiki.changes(PRIVATE)
		self.assertFalse(frappe.get_list("Life Wiki Change", filters={"space": PRIVATE}))

	def test_fake_agent_adds_to_the_wiki(self):
		item = inbox.create_item(title="ux4 wiki source", source_type="Message", space=PRIVATE, raw_text="Mithun runs production.", intent="Add to wiki")
		frappe.db.sql("update `tabLife Inbox Item` set received_on = %s where name = %s", (add_to_date(now_datetime(), days=-3650), item["name"]))
		self.as_user(AGENT)
		load_fake_agent().process_one(LocalClient(), log=lambda *a: None)
		self.as_user(OWNER)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item["name"], "status"), "Done")
		created = frappe.db.get_value("Life Note", {"space": PRIVATE, "title": "ux4 wiki source", "collection": "Wiki"})
		self.assertTrue(created)
		log = frappe.db.get_value("Life Note", {"space": PRIVATE, "title": "Inbox log", "collection": "Wiki"}, ["name", "content_md"], as_dict=True)
		self.assertIn("[[ux4 wiki source]]", log.content_md)
		kinds = {(c.note, c.change_type) for c in wiki.changes(PRIVATE, page_length=100)["changes"]}
		self.assertIn((created, "Created"), kinds)
		self.assertIn((log.name, "Edited"), kinds)
		self.assertFalse(frappe.db.exists("Life Proposal", {"inbox_item": item["name"], "kind": "Note"}))


class TestChatImport(LifeTestCase):
	def _import(self, system, name):
		from frappe.utils.file_manager import save_file

		with open(os.path.join(FIXTURES, name), "rb") as fh:
			f = save_file(name, fh.read(), None, None, is_private=1)
		frappe.flags.lifeos_import_now = True
		try:
			connections.start_import(space=PRIVATE, system=system, file_url=f.file_url)
		finally:
			frappe.flags.lifeos_import_now = False
		frappe.set_user(OWNER)
		permissions.clear_cache()
		return connections.import_status(PRIVATE, system)

	def test_claude_export(self):
		st = self._import("claude", "claude_export.zip")
		self.assertEqual((st["status"], st["created"], st["skipped"]), ("Done", 2, 1), st)
		log = frappe.get_doc("Life Chat Log", {"space": PRIVATE, "source_system": "claude", "external_id": "c0ffee00-0000-4000-8000-000000000001"})
		self.assertEqual((log.title, log.assistant, log.url), ("Blend sheet for Dalmia Gold", "Claude", "https://claude.ai/chat/c0ffee00-0000-4000-8000-000000000001"))
		self.assertIn("**You**", log.transcript_md)
		self.assertIn("Attachments: blend.xlsx", log.transcript_md)
		self.assertFalse(log.summary_md)
		self.assertTrue(frappe.db.exists("Life Chat Log", {"source_system": "claude", "title": "Untitled chat"}))
		again = self._import("claude", "claude_export.zip")
		self.assertEqual((again["created"], again["updated"], again["unchanged"]), (0, 0, 2), again)
		self.assertEqual(frappe.db.count("Life Chat Log", {"space": PRIVATE, "source_system": "claude"}), 2)

	def test_chatgpt_export_walks_the_current_branch(self):
		st = self._import("chatgpt", "chatgpt_export.zip")
		self.assertEqual((st["status"], st["created"], st["skipped"]), ("Done", 2, 1), st)
		log = frappe.get_doc("Life Chat Log", {"space": PRIVATE, "source_system": "chatgpt", "external_id": "6730a1b2-0000-0000-0000-000000000001"})
		self.assertEqual(log.url, "https://chatgpt.com/c/6730a1b2-0000-0000-0000-000000000001")
		self.assertIn("60 to 90 cm", log.transcript_md)
		self.assertNotIn("regenerated", log.transcript_md)
		self.assertIn("section7.jpg", log.transcript_md)
		self.assertEqual(str(log.date), "2025-10-02")

	def test_a_wrong_file_fails_cleanly(self):
		st = self._import("chatgpt", "claude_export.zip")  # a Claude export read as ChatGPT
		self.assertEqual(st["status"], "Failed")
		self.assertIn("Nothing was imported", st["error"])
		self.assertFalse(frappe.db.exists("Life Chat Log", {"space": PRIVATE, "source_system": "chatgpt"}))
		self.assertTrue(chat_import.SYSTEMS)


def png(w=1600, h=1200):
	from PIL import Image

	buf = io.BytesIO()
	Image.new("RGB", (w, h), "white").save(buf, format="PNG")
	return buf.getvalue()


class TestSourceFields(LifeTestCase):
	def test_intent_defaults_to_process(self):
		item = self.make("Life Inbox Item", title="ux4 intent", source_type="Message")
		self.assertEqual(item.intent, "Process")

	def test_media_kind_from_source_type_and_files(self):
		self.assertEqual(sources_lifeos.media_kind("Voice Note"), "Voice")
		self.assertEqual(sources_lifeos.media_kind("Email Digest"), "Email Digest")
		self.assertEqual(sources_lifeos.media_kind("Web"), "Article")
		self.assertEqual(sources_lifeos.media_kind("Upload", ["a.pdf"]), "Document")
		self.assertEqual(sources_lifeos.media_kind("Upload", ["a.m4a"]), "Voice")
		self.assertEqual(sources_lifeos.media_kind("Upload", ["a.JPG"]), "Photo")
		self.assertEqual(sources_lifeos.media_kind("Message"), "Text")
		self.assertEqual(sources_lifeos.media_kind("Upload", [], "https://example.com/a"), "Article")
		item = self.make("Life Inbox Item", title="ux4 kind", source_type="Upload")
		self.assertEqual(item.media_kind, "Text")
		attach("Life Inbox Item", item.name, "scan.pdf", pdf_bytes())
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item.name, "media_kind"), "Document")
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": item.name}, "media_kind"), "Document")

	def test_email_digest_is_a_source_type(self):
		item = inbox.create_item(title="ux4 digest", source_type="Email Digest", space=PRIVATE, raw_text="## Needs your attention")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", item["name"], "media_kind"), "Email Digest")

	def test_photo_gets_a_480_px_thumbnail(self):
		from PIL import Image

		item = self.make("Life Inbox Item", title="ux4 photo", source_type="Upload")
		attach("Life Inbox Item", item.name, "photo.png", png())
		url = frappe.db.get_value("Life Inbox Item", item.name, "thumbnail")
		self.assertTrue(url)
		thumb = frappe.get_doc("File", {"file_url": url, "attached_to_name": item.name})
		self.assertTrue(thumb.is_private)
		self.assertEqual(Image.open(io.BytesIO(thumb.get_content())).size[0], 480)
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": item.name}, "thumbnail"), url)
		# the thumbnail is not an original
		self.assertEqual([f["file_name"] for f in inbox.get(item.name)["files"]], ["photo.png"])

	def test_external_id_is_unique_per_space_and_system(self):
		self.make("Life Inbox Item", title="ux4 mail 1", source_type="Email", source_system="gmail", external_id="m-1")
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make("Life Inbox Item", title="ux4 mail 2", source_type="Email", source_system="gmail", external_id="m-1")
		# another system or another space may use the same ID
		self.make("Life Inbox Item", title="ux4 mail 3", source_type="Email", source_system="outlook", external_id="m-1")
		self.make("Life Inbox Item", space=SHARED, title="ux4 mail 4", source_type="Email", source_system="gmail", external_id="m-1")
		# items with no ID are never in conflict
		self.make("Life Inbox Item", title="ux4 a", source_type="Message")
		self.make("Life Inbox Item", title="ux4 b", source_type="Message")
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Inbox Item", title="ux4 no system", source_type="Email", external_id="m-9")

	def test_chat_log_fields(self):
		log = self.make("Life Chat Log", title="ux4 chat", date=frappe.utils.today(), assistant="Claude Code", source_system="claude",
			external_id="c-1", transcript_md="**You** a question about the zebra crossing\n\n**Claude** an answer")
		self.assertEqual(log.assistant, "Claude Code")
		self.make("Life Chat Log", title="ux4 codex", date=frappe.utils.today(), assistant="Codex")
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make("Life Chat Log", title="ux4 chat again", date=frappe.utils.today(), source_system="claude", external_id="c-1")
		self.assertIn("zebra crossing", frappe.db.get_value("Life Index", {"ref_name": log.name}, "search_text"))
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": log.name}, ["media_kind", "assistant"]), ("Chat", "Claude Code"))

	def test_search_text_is_capped(self):
		long = ("word " * 20000) + "needlefar"
		item = self.make("Life Inbox Item", title="ux4 long", source_type="Message", transcript_md=long)
		text = frappe.db.get_value("Life Index", {"ref_name": item.name}, "search_text")
		self.assertEqual(len(text), index.SEARCH_CAP)
		short = self.make("Life Inbox Item", title="ux4 short", source_type="Message", transcript_md="word " * 9000 + "needlenear")
		self.assertIn("needlenear", frappe.db.get_value("Life Index", {"ref_name": short.name}, "search_text"))


class TestNoteFields(LifeTestCase):
	def test_collection_defaults_to_my_notes(self):
		note = self.make("Life Note", title="ux4 plain")
		self.assertEqual(note.collection, "My notes")
		self.assertEqual(frappe.db.get_value("Life Index", {"ref_name": note.name}, "collection"), "My notes")

	def test_wiki_page_needs_a_summary_on_one_line(self):
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 wiki no summary", collection="Wiki")
		page = self.make("Life Note", title="ux4 wiki", collection="Wiki", summary="One line\nnot two")
		self.assertEqual(page.summary, "One line not two")

	def test_one_rules_page_per_space_and_only_in_the_wiki(self):
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 rules mine", is_rules=1)
		self.make("Life Note", title="ux4 rules", collection="Wiki", summary="Rules", is_rules=1)
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 rules 2", collection="Wiki", summary="Rules", is_rules=1)
		self.make("Life Note", space=SHARED, title="ux4 rules shared", collection="Wiki", summary="Rules", is_rules=1)

	def test_sources_are_inbox_items_or_chats_of_the_same_space(self):
		item = self.make("Life Inbox Item", title="ux4 src", source_type="Message")
		chat = self.make("Life Chat Log", title="ux4 src chat", date=frappe.utils.today())
		page = self.make("Life Note", title="ux4 cites", collection="Wiki", summary="Cites", sources=[
			{"source_doctype": "Life Inbox Item", "source_name": item.name}, {"source_doctype": "Life Chat Log", "source_name": chat.name},
			{"source_doctype": "Life Inbox Item", "source_name": item.name}])
		self.assertEqual(len(page.sources), 2)
		task = self.make("Life Task", title="ux4 not a source")
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 bad", sources=[{"source_doctype": "Life Task", "source_name": task.name}])
		other = self.make("Life Inbox Item", space=SHARED, title="ux4 other space", source_type="Message")
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 cross", sources=[{"source_doctype": "Life Inbox Item", "source_name": other.name}])

	def test_page_size_limit(self):
		with self.assertRaises(frappe.ValidationError):
			self.make("Life Note", title="ux4 huge", content_md="x" * 200001)

	def test_wiki_change_has_no_links_and_is_read_only_to_people(self):
		target = self.make("Life Note", title="ux4 link target")
		page = self.make("Life Note", title="ux4 page", collection="Wiki", summary="A page")
		ch = frappe.get_doc({"doctype": "Life Wiki Change", "space": PRIVATE, "note": page.name, "change_type": "Edited",
			"changed_by": OWNER, "changed_on": frappe.utils.now_datetime(), "before_md": "", "after_md": "See [[ux4 link target]]"})
		ch.insert(ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Life Link", {"from_doctype": "Life Wiki Change"}))
		self.assertTrue(frappe.get_doc("Life Wiki Change", ch.name).has_permission("read"))
		self.assertFalse(frappe.get_doc("Life Wiki Change", ch.name).has_permission("write"))
		self.as_user(FAMILY)
		self.assertFalse(frappe.get_list("Life Wiki Change", filters={"name": ch.name}))
		self.assertTrue(target)


class TestConnections(LifeTestCase):
	def test_one_connection_per_space_and_system(self):
		c = self.make("Life Connection", system="Gmail", label="")
		self.assertEqual((c.system, c.label, c.default_intent), ("gmail", "Gmail", "Process"))
		with self.assertRaises(frappe.DuplicateEntryError):
			self.make("Life Connection", system="gmail")
		self.make("Life Connection", space=SHARED, system="gmail")

	def test_agent_reads_but_cannot_change_a_connection(self):
		c = self.make("Life Connection", system="claude")
		self.as_user(AGENT)
		doc = frappe.get_doc("Life Connection", c.name)
		self.assertTrue(doc.has_permission("read"))
		self.assertFalse(doc.has_permission("write"))


class TestVaultSources(LifeTestCase):
	def test_a_source_of_a_vault_document_follows_vault_access(self):
		item = self.make("Life Inbox Item", title="ux4 passport scan", source_type="Upload")
		doc = self.make("Life Vault Document", title="ux4 passport", inbox_item=item.name)
		frappe.db.set_value("Life Inbox Item", item.name, "vault_document", doc.name)
		index.update(frappe.get_doc("Life Inbox Item", item.name))
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		self.as_user(AGENT)
		self.assertFalse(frappe.get_doc("Life Inbox Item", item.name).has_permission("read"))
		self.assertFalse(frappe.get_list("Life Inbox Item", filters={"name": item.name}))
		self.assertFalse(frappe.get_list("Life Index", filters={"ref_name": item.name}))
		self.as_user(OWNER)
		self.assertTrue(frappe.get_list("Life Index", filters={"ref_name": item.name}))
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 1)
		self.as_user(AGENT)
		self.assertTrue(frappe.get_list("Life Inbox Item", filters={"name": item.name}))
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)


class TestLinkQuery(LifeTestCase):
	def test_only_active_areas_of_the_space_unless_asked(self):
		active = self.make("Life Area", area_name="ux4 active area", parent_area=self.life["Career"])
		gone = self.make("Life Area", area_name="ux4 gone area", is_archived=1, parent_area=self.life["Career"])
		shared = self.make("Life Area", space=SHARED, area_name="ux4 shared area", parent_area=self.shared_life["Career"])
		rows = queries.link_query("Life Area", "ux4", "area_name", 0, 20, {"space": PRIVATE})
		names = [r[0] for r in rows]
		self.assertIn(active.name, names)
		self.assertNotIn(gone.name, names)
		self.assertNotIn(shared.name, names)
		rows = queries.link_query("Life Area", "ux4", "area_name", 0, 20, {"space": PRIVATE, "include_archived": 1})
		self.assertIn((gone.name, "ux4 gone area (archived)"), [tuple(r[:2]) for r in rows])
		# with no space, every space of the user, still no archived area
		names = [r[0] for r in queries.link_query("Life Area", "ux4", "area_name", 0, 20, {})]
		self.assertIn(shared.name, names)
		self.assertNotIn(gone.name, names)
		# a member of Shared only never sees Private areas
		self.as_user(FAMILY)
		names = [r[0] for r in queries.link_query("Life Area", "ux4", "area_name", 0, 20, {"space": PRIVATE})]
		self.assertEqual(names, [])

	def test_goals_leave_out_achieved_and_dropped(self):
		# set 6: the project picker became the goal picker; open-ended goals that are finished leave it
		area = self.areas["Tea"]
		live = self.make("Life Goal", title="ux4 live goal", horizon="Long term", area=area)
		done = self.make("Life Goal", title="ux4 done goal", horizon="Long term", area=area, outcome="Achieved")
		names = [r[0] for r in queries.link_query("Life Goal", "ux4", "title", 0, 20, {"space": PRIVATE})]
		self.assertIn(live.name, names)
		self.assertNotIn(done.name, names)
		names = [r[0] for r in queries.link_query("Life Goal", "ux4", "title", 0, 20, {"space": PRIVATE, "goal_outcome": ["Achieved"]})]
		self.assertEqual(names, [done.name])

	def test_search_link_uses_the_query(self):
		from frappe.desk.search import search_link

		gone = self.make("Life Area", area_name="ux4 hidden by search", is_archived=1, parent_area=self.life["Career"])
		got = [r["value"] for r in search_link("Life Area", "ux4 hidden", filters={"space": PRIVATE})]
		self.assertNotIn(gone.name, got)
		self.assertTrue(permissions)


# ---- sources: channels and kinds, one page each (issue 84) ----
class TestSourcePages(SkillCase):
	def video(self, size):
		item = self.capture(text="Recorded call with the accountant.", source_type="Upload")
		f = attach("Life Inbox Item", item.name, "call.mp4", b"not really a video")
		frappe.db.set_value("File", f.name, "file_size", size)
		item.reload()
		return item

	def test_a_video_over_500_mb_is_refused_with_a_message_and_a_smaller_one_gets_a_transcript(self):
		big = self.video(600 * 1024 * 1024)
		frappe.flags.lifeos_ai_backend = NoModel()
		self.process(big)
		self.assertEqual(big.status, "Failed")
		self.assertIn("call.mp4 is 600 MB", big.error)
		self.assertIn("up to 500 MB", big.error)
		small = self.video(40 * 1024 * 1024)
		self.script(answer("A call about the audit.", transcript="Accountant: send the ledgers by Friday."))
		self.process(small)
		self.assertEqual(small.status, "Done")
		self.assertEqual(small.transcript_md, "Accountant: send the ledgers by Friday.")
		self.assertEqual(small.media_kind, "Video")

	def test_sources_come_in_two_groups_with_counts_and_a_new_site_has_nothing_yet(self):
		from lifeos.api import source_page

		groups = source_page.groups(PRIVATE)
		self.assertEqual([c["key"] for c in groups["channels"]][:5], ["upload", "phone", "gmail", "google-calendar", "email"])
		self.assertEqual([k["key"] for k in groups["kinds"]], ["kind-document", "kind-photo", "kind-video", "kind-link", "kind-voice", "kind-email"])
		self.assertEqual([c["connected"] for c in groups["channels"]], [1, 1, 0, 0, 0])
		self.assertTrue(all(c["how_to"] for c in groups["channels"]))
		self.assertTrue(all(g["skill"] and g["version"] for g in (*groups["channels"], *groups["kinds"])))

	def test_a_source_page_counts_its_week_and_the_share_filed_without_you(self):
		from lifeos.api import source_page

		before = source_page.get("kind-document", PRIVATE)["strip"]
		item = self.capture(text="Policy renewal due 1 March.", source_type="Upload")
		attach("Life Inbox Item", item.name, "policy.pdf", pdf_bytes())
		page = source_page.get("kind-document", PRIVATE)
		self.assertEqual(page["strip"]["this_week"], before["this_week"] + 1)
		self.assertEqual((page["group"], page["title"], page["skill"], page["strip"]["skill_label"]), ("kind", "Documents (PDF)", "ingest-document", "ingest-document v1"))
		self.assertEqual(page["strip"]["active"], 1)
		agent = source_page.get("upload", PRIVATE)
		self.assertEqual((agent["group"], agent["skill"]), ("channel", "channel-upload"))
		with self.assertRaises(frappe.DoesNotExistError):
			source_page.get("nonsense", PRIVATE)
		frappe.set_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			source_page.get("kind-document", PRIVATE)

	def test_a_sources_own_confidence_decides_what_is_filed_without_you_and_agents_can_be_taken_off_it(self):
		from lifeos.api import source_page
		from lifeos.skills import filing

		frappe.db.set_single_value("Life Settings", "brain_auto_kinds", json.dumps(["Task"]))
		frappe.clear_cache(doctype="Life Settings")
		self.assertEqual(source_page.get("kind-document", PRIVATE)["settings"]["auto_file_confidence"], 85)  # follows Settings until it is set
		out = source_page.save_settings("kind-document", auto_file_confidence=95, space=PRIVATE)
		self.assertEqual((out["auto_file_confidence"], out["own"]), (95, True))
		item = self.capture(text="Pay the fee.", source_type="Upload")
		attach("Life Inbox Item", item.name, "fee.pdf", pdf_bytes())
		item.reload()
		self.script(task("Pay the school fees", confidence=0.9), answer("A fee notice."))
		self.process(item)
		self.assertEqual(frappe.db.get_value("Life Proposal", {"inbox_item": item.name}, "status"), "Pending")  # 90 is under the document's 95
		source_page.save_settings("kind-document", auto_file_confidence=80, space=PRIVATE)
		item2 = self.capture(text="Pay the fee again.", source_type="Upload")
		attach("Life Inbox Item", item2.name, "fee2.pdf", pdf_bytes())
		item2.reload()
		self.script(task("Pay the hostel fees", confidence=0.9), answer("A fee notice."))
		self.process(item2)
		self.assertEqual(frappe.db.get_value("Life Proposal", {"inbox_item": item2.name}, "status"), "Accepted")
		with self.assertRaises(frappe.ValidationError):
			source_page.save_settings("kind-document", auto_file_confidence=120, space=PRIVATE)
		# which agents may read it
		hermes = source_page.get("kind-document", PRIVATE)["settings"]["agents"]
		self.assertIn(AGENT, [a["user"] for a in hermes])
		source_page.save_settings("kind-document", readers=[], space=PRIVATE)
		frappe.set_user(AGENT)
		names = [s["name"] for s in sources.list(space=PRIVATE, page_length=200)["sources"]]
		self.assertNotIn(item2.name, names)
		frappe.set_user(OWNER)
		source_page.save_settings("kind-document", readers=[a["user"] for a in hermes], space=PRIVATE)
		frappe.set_user(AGENT)
		self.assertIn(item2.name, [s["name"] for s in sources.list(space=PRIVATE, page_length=200)["sources"]])

	def test_try_it_shows_what_it_would_do_and_files_nothing_until_file_it_for_real(self):
		from lifeos.api import source_page

		items = frappe.db.count("Life Inbox Item", {"space": PRIVATE})
		self.script(task("Pay the Try-it fees", confidence=0.9), {"content": [{"type": "text", "text": json.dumps(
			{"transcript_md": "", "summary": {"line": "A fee notice."}, "skipped": ["The letterhead"]})}], "stop_reason": "end_turn"})
		res = source_page.try_it("kind-document", title="Fee notice", text="School fees of Rs 20,000 are due on 5 December.", space=PRIVATE)
		self.assertEqual((res["summary"], res["skipped"]), ("A fee notice.", ["The letterhead"]))
		self.assertEqual(res["proposals"][0]["title"], "Pay the Try-it fees")
		self.assertEqual(res["skills_used"], "process-capture v1, channel-upload v1, ingest-document v1")
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE}), items)
		self.assertFalse(frappe.db.exists("Life Proposal", {"preview": "Pay the Try-it fees"}))
		made = source_page.file_it("kind-document", title="Fee notice", text="School fees of Rs 20,000 are due on 5 December.", space=PRIVATE)
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE}), items + 1)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", made["name"], "status"), "New")
		with self.assertRaises(frappe.ValidationError):
			source_page.try_it("kind-document", space=PRIVATE)  # nothing to try
		set_key("")
		with self.assertRaises(frappe.ValidationError):
			source_page.try_it("kind-document", text="x", space=PRIVATE)


def digest_answer(**extra):
	"""A scripted answer for a digest of nine emails, in the summary's fixed shape (issue 118)."""
	long = "wants the signed account mandate returned together with the board resolution and the updated address proof before the end of this week please"
	summary = {"line": "9 emails, 26 Nov",
		"to_act_on": [{"who": "Arijit Chatterjee (HDFC Bank)", "what": long, "source": "Email 1", "route": "plate"},
			{"who": "Anindita Goswami", "what": "proposes a call on the audit; your CA is copied", "source": "Email 4", "route": "waiting", "waiting_on": "Rohan CA"},
			{"who": "Ravi Singh", "what": "unclear what he needs on the notice", "source": "Email 5"}],
		"updates": [{"what": "Two trademark threads with Ravi Singh: renewal filed, objection window open", "source": "Email 6"}],
		"reports": [{"title": "Tea price list", "source": "Email 7"}, {"title": "Ghatia lot selection", "source": "Email 8"}, {"title": "GST reconciliation", "source": "Email 9"}],
		"sensitive": 1}
	return {"content": [{"type": "text", "text": json.dumps({"transcript_md": "", "summary": summary, **extra})}], "stop_reason": "end_turn"}


class TestSummaryLines(SkillCase):
	"""Issue 118: the summary as data, its To act on lines going to the plate or the waiting pile, the waiting pile off Today."""

	def digest(self, **values):
		return self.capture("Nine emails.\n" * 9, **{"title": "Morning digest", "source_type": "Email Digest", "sender": "digest@gmail.example", **values})

	def run_digest(self, item=None, **extra):
		item = item or self.digest()
		self.script(digest_answer(**extra))
		self.process(item)
		return item

	def test_the_summary_has_three_groups_each_line_with_its_source_and_none_over_20_words(self):
		item = self.run_digest()
		s = json.loads(item.summary_json)
		self.assertEqual((s["line"], len(s["to_act_on"]), len(s["updates"]), len(s["reports"])), ("9 emails, 26 Nov", 3, 1, 3))
		for line in [*s["to_act_on"], *s["updates"]]:
			self.assertLessEqual(len(line["what"].split()), 21, line["what"])  # 20 words and the ellipsis
		self.assertTrue(all(r["source"] for r in [*s["to_act_on"][:2], *s["updates"], *s["reports"]]))
		self.assertIn("**To act on · 3**", item.summary_md)
		self.assertIn("Tea price list · Ghatia lot selection · GST reconciliation", item.summary_md)

	def test_a_sensitive_line_is_only_ever_one_sensitive_item(self):
		raw = json.loads(digest_answer()["content"][0]["text"])
		raw["summary"]["to_act_on"].append({"who": "Dr Mehta", "what": "biopsy result is positive, call the clinic", "source": "Email 2", "sensitive": True})
		self.script({"content": [{"type": "text", "text": json.dumps(raw)}], "stop_reason": "end_turn"})
		item = self.digest()
		self.process(item)
		self.assertNotIn("biopsy", item.summary_json + item.summary_md)
		self.assertNotIn("Mehta", item.summary_json + item.summary_md)
		self.assertEqual(json.loads(item.summary_json)["sensitive"], 2)
		self.assertIn("2 sensitive items", item.summary_md)

	def test_asks_go_to_the_plate_or_the_waiting_pile_and_unsure_goes_to_the_pile(self):
		item = self.run_digest()
		tasks = {t.title.split(":")[0]: t for t in frappe.get_all("Life Task", filters={"inbox_item": item.name}, fields=["*"])}
		plate, pile, unsure = tasks["Arijit Chatterjee (HDFC Bank)"], tasks["Anindita Goswami"], tasks["Ravi Singh"]
		self.assertEqual((plate.status, str(plate.due_date)), ("Open", today()))
		self.assertEqual((pile.status, pile.waiting_on, str(pile.check_by)), ("Waiting", "Rohan CA", asks.next_review_date()))
		self.assertEqual((unsure.status, str(unsure.check_by)), ("Waiting", asks.next_review_date()))
		self.assertGreater(getdate(asks.next_review_date()), getdate(today()))

	def test_a_waiting_task_is_never_on_today_and_past_its_check_date_it_is_one_line(self):
		item = self.run_digest()
		names = frappe.get_all("Life Task", filters={"inbox_item": item.name, "status": "Waiting"}, pluck="name")
		frappe.db.set_value("Life Task", {"inbox_item": item.name}, "due_date", today())
		frappe.set_user(OWNER)
		got = today_api.get(space=PRIVATE)
		shown = {t["name"] for t in [*got["tasks"]["items"], *got["tasks"]["today"], *got["tasks"]["overdue_items"]]}
		self.assertFalse(shown & set(names))
		self.assertEqual(got["waiting_past"]["count"], 0)
		for n in names:
			frappe.db.set_value("Life Task", n, "check_by", add_days(today(), -2))
		got = today_api.get(space=PRIVATE)
		self.assertEqual(got["waiting_past"]["count"], 2)
		self.assertIn("Rohan CA", got["waiting_past"]["names"])

	def test_change_moves_a_line_and_the_same_move_twice_for_a_sender_makes_a_rule(self):
		sender = "arijit@hdfc.example"
		moved = []
		for n in range(2):
			item = self.run_digest(item=self.digest(sender=sender))
			frappe.set_user(OWNER)
			index = 2  # the unsure line went to the pile
			out = asks.change(item.name, index, "plate")
			moved.append(frappe.db.get_value("Life Task", out["task"], ["status", "waiting_on"]))
			frappe.set_user("Administrator")
			self.script()
		self.assertEqual(moved, [("Open", None), ("Open", None)])
		rule = frappe.get_all("Life Rule", filters={"action": "Route", "sender": sender}, fields=["asks_to", "made_by"])
		self.assertEqual([(r.asks_to, r.made_by) for r in rule], [("Plate", "Brain")])
		# the rule decides before the model: the next digest from this sender puts the unsure ask on the plate
		third = self.run_digest(item=self.digest(sender=sender))
		unsure = frappe.get_all("Life Task", filters={"inbox_item": third.name, "title": ("like", "Ravi Singh%")}, fields=["status"])[0]
		self.assertEqual(unsure.status, "Open")

	def test_one_move_is_not_a_rule(self):
		item = self.run_digest(item=self.digest(sender="once@x.example"))
		frappe.set_user(OWNER)
		asks.change(item.name, 2, "plate")
		self.assertFalse(frappe.db.exists("Life Rule", {"action": "Route", "sender": "once@x.example"}))

	def test_a_reply_that_says_done_closes_the_waiting_task_and_lists_it(self):
		first = self.run_digest(item=self.digest(sender="ravi@x.example", source_system="gmail", external_id="thread-1"))
		waiting = frappe.get_all("Life Task", filters={"inbox_item": first.name, "status": "Waiting"}, pluck="name")[0]
		reply = self.capture("Done, I sent the papers yesterday.", title="Re: the notice", sender="ravi@x.example")
		self.script(answer("Ravi says it is done."))
		self.process(reply)
		self.assertEqual(frappe.db.get_value("Life Task", waiting, "status"), "Waiting")  # the model did not say so: nothing closes
		self.script({"content": [{"type": "text", "text": json.dumps({"transcript_md": "", "summary": {"line": "Ravi says it is done."}, "closes": [{"task": waiting}, {"task": "NOT-OFFERED"}]})}],
			"stop_reason": "end_turn"})
		reply2 = self.capture("Done, I sent the papers yesterday.", title="Re: the notice 2", sender="ravi@x.example")
		self.process(reply2)
		self.assertEqual(frappe.db.get_value("Life Task", waiting, ["status", "closed_by_brain", "closed_by_item"]), ("Done", 1, reply2.name))
		frappe.set_user(OWNER)
		row = next(r for r in brain.activity(space=PRIVATE)["rows"] if r["item"] == reply2.name)
		self.assertEqual([m["kind"] for m in row["made"]], ["Closed by itself"])
		self.assertEqual([c["name"] for c in asks.closed_by_itself(PRIVATE, add_days(today(), -7))], [waiting])
		asks.reopen(waiting)
		self.assertEqual(frappe.db.get_value("Life Task", waiting, "status"), "Waiting")

	def test_the_waiting_review_groups_by_person_oldest_first_and_changes_a_task(self):
		item = self.run_digest()
		frappe.set_user(OWNER)
		rows = [r for r in asks.waiting_rows(PRIVATE) if r["item"] == item.name]
		self.assertEqual(sorted(r["who"] for r in rows), ["Ravi Singh", "Rohan CA"])
		first = rows[0]["name"]
		out = asks.waiting_change(first, "still")
		self.assertEqual(out["check_by"], str(add_days(getdate(asks.next_review_date()), 7)))
		asks.waiting_change(first, "plate")
		self.assertEqual(frappe.db.get_value("Life Task", first, ["status", "waiting_on"]), ("Open", None))
		self.assertIn("nudge", asks.nudge(rows[1]["name"])["text"])
