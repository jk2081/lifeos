"""Set 7, step 1: key results. The goal rule, progress in both directions, readings and the current value, Reading proposals
from agents, the nightly readings, Make it a habit, goals serving goals, and counted weekly actions."""
import json

import frappe
from frappe.utils import add_days, getdate, today

from lifeos import journal, readings
from lifeos.ai import fake
from lifeos.api import goals, inbox
from lifeos.api import journal as journal_api
from lifeos.tests.base import AGENT, OWNER, PRIVATE, LifeTestCase
from lifeos.tests.test_ux5_ask import set_key


def number_goal(title="ux7 weight", start=84, target=78, **kw):
	return goals.create(title, "Open", space=PRIVATE, measure_kind="Number", measure=kw.pop("measure", "Weight"), unit=kw.pop("unit", "kg"),
		start_value=start, target_value=target, **kw)["name"]


class TestGoalRule(LifeTestCase):
	def test_milestone_needs_a_finish_line(self):
		self.assertRaises(frappe.ValidationError, goals.create, "ux7 m", "Open", space=PRIVATE, measure_kind="Milestone")
		g = goals.create("ux7 m", "Open", space=PRIVATE, measure_kind="Milestone", done_when="The plan is signed")["name"]
		self.assertEqual(frappe.db.get_value("Life Goal", g, "measure_kind"), "Milestone")

	def test_number_needs_measure_start_and_target(self):
		for missing in ("measure", "start_value", "target_value"):
			args = {"measure": "Yield", "start_value": 1, "target_value": 2, missing: None}
			self.assertRaises(frappe.ValidationError, goals.create, "ux7 n", "Open", space=PRIVATE, measure_kind="Number", **args)
		self.assertRaises(frappe.ValidationError, goals.create, "ux7 n", "Open", space=PRIVATE, measure_kind="Number", measure="Yield",
			start_value=5, target_value=5)

	def test_finish_line_alone_is_a_milestone(self):
		g = goals.create("ux7 f", "Open", space=PRIVATE, done_when="Done")["name"]
		self.assertEqual(frappe.db.get_value("Life Goal", g, "measure_kind"), "Milestone")

	def test_old_goals_without_a_measure_still_save(self):
		g = frappe.get_doc({"doctype": "Life Goal", "space": PRIVATE, "title": "ux7 old", "goal_type": "Open"}).insert()
		g.title = "ux7 old, renamed"
		g.save()
		self.assertFalse(readings.has_finish_line(g))

	def test_editing_the_measure_applies_the_rule(self):
		g = goals.create("ux7 e", "Open", space=PRIVATE, done_when="Done")["name"]
		self.assertRaises(frappe.ValidationError, goals.update, g, {"measure_kind": "Number", "measure": "Yield"})
		goals.update(g, {"measure_kind": "Number", "measure": "Yield", "unit": "kg/ha", "start_value": 1200, "target_value": 1800})
		self.assertEqual(frappe.db.get_value("Life Goal", g, "target_value"), 1800)

	def test_agents_cannot_create_or_suggest(self):
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, goals.create, "ux7 a", "Open", space=PRIVATE, done_when="x")
		self.assertRaises(frappe.PermissionError, goals.suggest_measure, "Lose 6 kg", space=PRIVATE)


class TestProgress(LifeTestCase):
	def test_both_directions_and_clamping(self):
		self.assertEqual(readings.progress(84, 78, 81), 50.0)  # going down
		self.assertEqual(readings.progress(1200, 1800, 1500), 50.0)  # going up
		self.assertEqual(readings.progress(84, 78, 90), 0.0)
		self.assertEqual(readings.progress(84, 78, 70), 100.0)
		self.assertEqual(readings.progress(84, 78, None), 0.0)
		self.assertEqual(readings.direction(84, 78), "down")
		self.assertTrue(readings.reached({"measure_kind": "Number", "start_value": 84, "target_value": 78, "current_value": 77.5, "current_on": today()}))
		self.assertFalse(readings.reached({"measure_kind": "Number", "start_value": 84, "target_value": 78, "current_value": 79, "current_on": today()}))
		self.assertTrue(readings.reached({"measure_kind": "Number", "start_value": 1, "target_value": 10, "current_value": 10, "current_on": today()}))


class TestReadings(LifeTestCase):
	def test_current_value_is_the_latest_confirmed_reading(self):
		g = number_goal()
		goals.add_reading(g, 82, date=add_days(today(), -10))
		out = goals.add_reading(g, 81, date=add_days(today(), -3))
		self.assertEqual(out["current_value"], 81)
		self.assertEqual(out["progress"]["percent"], 50.0)
		# an older reading entered later does not replace the latest one
		goals.add_reading(g, 83, date=add_days(today(), -20))
		self.assertEqual(frappe.db.get_value("Life Goal", g, "current_value"), 81)
		# a suggested reading does not count until it is confirmed
		r = readings.suggest(g, 80, today(), "weighed 80 kg", by="Assistant")
		self.assertEqual(frappe.db.get_value("Life Goal", g, "current_value"), 81)
		out = goals.confirm_reading(r.name, value=79.5)
		self.assertEqual(out["current_value"], 79.5)
		self.assertEqual(str(frappe.db.get_value("Life Goal", g, "current_on")), today())
		# deleting the latest falls back to the one before
		frappe.delete_doc("Life Goal Reading", r.name)
		self.assertEqual(frappe.db.get_value("Life Goal", g, "current_value"), 81)

	def test_reject_keeps_it_out(self):
		g = number_goal()
		r = readings.suggest(g, 80, today(), "x", by="Agent")
		goals.reject_reading(r.name)
		self.assertIsNone(frappe.db.get_value("Life Goal", g, "current_on"))
		confirmed, suggested = readings.for_goal(g)
		self.assertEqual((confirmed, suggested), ([], []))
		# the same suggestion is not stored twice
		again = readings.suggest(g, 80, today(), "x", by="Agent")
		self.assertNotEqual(again.name, r.name)  # a rejected one does not block a new suggestion

	def test_readings_only_on_number_goals(self):
		g = goals.create("ux7 milestone", "Open", space=PRIVATE, done_when="Done")["name"]
		self.assertRaises(frappe.ValidationError, goals.add_reading, g, 3)

	def test_agents_cannot_confirm_or_reject(self):
		g = number_goal()
		r = readings.suggest(g, 80, today(), "x", by="Agent")
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, goals.confirm_reading, r.name)
		self.assertRaises(frappe.PermissionError, goals.reject_reading, r.name)
		self.assertRaises(frappe.PermissionError, goals.add_reading, g, 79)
		doc = frappe.get_doc("Life Goal Reading", r.name)
		doc.status = "Confirmed"
		self.assertRaises(frappe.PermissionError, doc.save, ignore_permissions=True)

	def test_reading_proposal_is_stored_as_suggested(self):
		g = number_goal("ux7 yield", 1200, 1800, measure="Ghillidary yield", unit="kg/ha")
		item = inbox.create_item(space=PRIVATE, title="Season update", source_type="Message", raw_text="Ghillidary yield this flush: 1640 kg/ha")
		self.as_user(AGENT)
		claimed = inbox.claim_next(space=PRIVATE)
		self.assertEqual(claimed["name"], item["name"])
		ctx_goal = next(x for x in claimed["context"]["goals"] if x["name"] == g)
		self.assertEqual(ctx_goal["measure"]["unit"], "kg/ha")
		out = inbox.submit_result(item["name"], summary_md="An update", proposals=[
			{"kind": "Reading", "preview": "Yield 1640", "confidence": 0.8,
				"payload": {"goal": g, "value": 1640, "excerpt": "Ghillidary yield this flush: 1640 kg/ha"}},
			{"kind": "Reading", "preview": "bad", "payload": {"goal": g, "value": "lots", "excerpt": "x"}}])
		self.assertEqual(len(out["readings"]), 1)
		self.assertEqual(len(out["errors"]), 1)
		self.assertEqual(out["created"], [])
		self.assertEqual(out["status"], "Done")  # nothing waits in the Inbox
		r = frappe.get_doc("Life Goal Reading", out["readings"][0]["name"])
		self.assertEqual((r.status, r.value, r.source_doctype, r.source_name, r.suggested_by), ("Suggested", 1640, "Life Inbox Item", item["name"], "Agent"))
		self.assertIsNone(frappe.db.get_value("Life Goal", g, "current_on"))

	def test_fake_agent_reports_a_reading(self):
		from lifeos.devtools import load_fake_agent

		fa = load_fake_agent()
		g = number_goal("ux7 weight goal")
		ctx = {"goals": [{"name": g, "measure_kind": "Number", "measure": {"measure": "Weight", "unit": "kg"}}]}
		got = fa.readings_in("Weight this morning was 80.4 kg", ctx, today())
		self.assertEqual(got[0]["payload"]["value"], 80.4)

	def test_nightly_readings_with_the_assistant(self):
		set_key("sk-test-not-real")
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 1)
		frappe.set_user(OWNER)
		g = number_goal("ux7 nightly", measure="Body weight")
		frappe.get_doc({"doctype": "Life Chat Log", "space": PRIVATE, "title": "ux7 health chat", "assistant": "Claude", "date": today(),
			"summary_md": "Body weight today 80.2 kg after the walk."}).insert()
		frappe.flags.lifeos_ai_backend = fake.SiteFake()
		try:
			made, note = readings.from_recent(PRIVATE, OWNER)
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key("")
		self.assertIsNone(note)
		self.assertGreaterEqual(made, 1)  # other number goals measured by "Weight" match the same words
		_, suggested = readings.for_goal(g)
		self.assertEqual(suggested[0]["value"], 80.2)
		self.assertEqual(suggested[0]["source_doctype"], "Life Chat Log")

	def test_nightly_readings_skip_without_a_key(self):
		set_key("")
		frappe.set_user(OWNER)
		number_goal("ux7 nokey")
		made, note = readings.from_recent(PRIVATE, OWNER)
		self.assertEqual(made, 0)
		self.assertIn("no API key", note)


class TestSuggestAndHabit(LifeTestCase):
	def test_rules_without_a_key(self):
		set_key("")
		frappe.set_user(OWNER)
		r = goals.suggest_measure("Ghillidary yield 1800 kg/ha", space=PRIVATE)
		self.assertEqual((r["kind"], r["unit"], r["target_value"], r["source"]), ("Number", "kg/ha", 1800, "rules"))
		r = goals.suggest_measure("Weight 84 to 78 kg", space=PRIVATE)
		self.assertEqual((r["start_value"], r["target_value"]), (84, 78))
		self.assertEqual(goals.suggest_measure("Ship MoneyOS", space=PRIVATE)["kind"], "Milestone")
		self.assertEqual(goals.suggest_measure("Walk 3 times a week", space=PRIVATE)["habit"]["days_per_week"], 3)

	def test_frequencies_are_habits(self):
		self.assertEqual(readings.habit_of("Meditate daily")["days_per_week"], 7)
		self.assertEqual(readings.habit_of("Swim twice a week")["days_per_week"], 2)
		self.assertEqual(readings.habit_of("Review every Sunday")["days_per_week"], 1)
		self.assertIsNone(readings.habit_of("Close the PMS account"))

	def test_make_it_a_habit_creates_no_goal(self):
		before = frappe.db.count("Life Goal", {"space": PRIVATE})
		out = goals.make_habit("ux7 Walk 3 times a week", space=PRIVATE)
		self.assertEqual(out["days_per_week"], 3)
		self.assertEqual(frappe.db.count("Life Goal", {"space": PRIVATE}), before)
		now = getdate(today())
		month = journal.habits_month(PRIVATE, now.year, now.month)
		self.assertIn(out["habit"], [h["habit"] for h in month["habits"]])


class TestServes(LifeTestCase):
	def test_serves_and_served_by_with_progress(self):
		top = number_goal("ux7 top", 1200, 1800, measure="Yield", unit="kg/ha")
		goals.add_reading(top, 1500)
		low = goals.create("ux7 low", "Annual", space=PRIVATE, target_date=add_days(today(), 90), serves=top, done_when="Plan done")["name"]
		frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 step", "goal": low, "status": "Done", "area": self.areas["Tea"]}).insert()
		frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "ux7 step 2", "goal": low, "status": "Open", "area": self.areas["Tea"]}).insert()
		d = goals.get(low)
		self.assertEqual(d["serves"]["name"], top)
		self.assertEqual(d["serves"]["progress"]["percent"], 50.0)
		t = goals.get(top)
		row = next(r for r in t["served_by"] if r.name == low)
		self.assertEqual((row.progress["kind"], row.progress["percent"]), ("tasks", 50.0))
		listed = goals.list(space=PRIVATE, sort="serves", page_length=500)["goals"]
		self.assertEqual(next(r for r in listed if r.name == top).progress["label"], "1500 kg/ha, target 1800 kg/ha")

	def test_cycle_goal_shows_the_goal_it_serves(self):
		top = number_goal("ux7 annual top", 10, 20, measure="Clients", unit="")
		c = journal_api.create_cycle(space=PRIVATE, start_date=add_days(today(), -today_weekday()))["cycle"]
		g = journal_api.save_goal(cycle=c, title="ux7 cycle goal", serves=top, measure_kind="Milestone", done_when="Ten pitches",
			actions=[{"title": "Pitch", "per_week": 4}])["goal"]
		row = next(x for x in journal.grid(c)["goals"] if x["name"] == g)
		self.assertEqual(row["serves_title"], "ux7 annual top")
		self.assertEqual(row["serves_progress"]["kind"], "number")


def today_weekday():
	return getdate(today()).weekday()


class TestCountedActions(LifeTestCase):
	def test_each_tick_counts_towards_the_week_score(self):
		c = journal_api.create_cycle(space=PRIVATE, start_date=add_days(today(), -today_weekday()))["cycle"]
		frappe.db.set_value("Life Cycle", c, "status", "Active")
		g = journal_api.save_goal(cycle=c, title="ux7 counted", measure_kind="Milestone", done_when="Done",
			actions=[{"title": "Call a client", "per_week": 4}])["goal"]
		action = frappe.get_doc("Life Goal", g).actions[0].name
		week = journal.current_week(frappe.get_doc("Life Cycle", c))
		s0 = journal.week_score(c, week)
		s1 = journal_api.tick(action, week, 1)
		self.assertEqual(s1["done"], s0["done"] + 1)
		self.assertGreater(s1["percent"], s0["percent"])
		s2 = journal_api.tick(action, week, 2)
		self.assertEqual(s2["done"], s0["done"] + 2)
		self.assertEqual(journal_api.tick(action, week, 9)["done"], s0["done"] + 4)  # never more than per_week
		row = next(x for x in journal.grid(c)["goals"] if x["name"] == g)
		self.assertEqual(row["actions"][0]["ticks"][str(week)], 4)
		self.assertEqual(json.loads(json.dumps(row["actions"][0]["per_week"])), 4)
