"""Issue 56: Edit a goal, "Done when" required on new goals (a setting, on by default), the cycle goal's actions."""
import frappe

from lifeos.api import goals, inbox, journal, review
from lifeos.tests.base import AGENT, OWNER, PRIVATE, LifeTestCase


def set_required(on):
	frappe.db.set_single_value("Life Settings", "require_done_when", 1 if on else 0)


class TestGoalEdit(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		set_required(True)

	def tearDown(self):
		set_required(True)
		super().tearDown()

	def test_6_a_goal_without_a_finish_line_is_refused_with_the_setting_on(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			goals.create(title="i56 bare", horizon="Long term", space=PRIVATE)
		self.assertIn("Write what will be true when this goal is done. Stuck? Use Suggest.", str(ctx.exception))
		self.assertFalse(frappe.db.exists("Life Goal", {"title": "i56 bare"}))
		self.assertTrue(goals.create(title="i56 with", horizon="Long term", space=PRIVATE, done_when="It is shipped")["name"])
		self.assertTrue(goals.create(title="i56 number", horizon="Long term", space=PRIVATE, measure_kind="Number", measure="Weight", unit="kg",
			start_value=84, target_value=78)["name"])

	def test_7_with_the_setting_off_a_goal_needs_no_finish_line(self):
		set_required(False)
		self.assertTrue(goals.create(title="i56 free", horizon="Long term", space=PRIVATE)["name"])

	def test_the_setting_is_on_by_default(self):
		meta = frappe.get_meta("Life Settings").get_field("require_done_when")
		self.assertEqual(str(meta.default), "1")

	def test_a_site_that_never_saved_the_setting_has_it_on(self):
		from lifeos.api import session, settings

		frappe.db.delete("Singles", {"doctype": "Life Settings", "field": "require_done_when"})
		frappe.clear_document_cache("Life Settings", "Life Settings")
		self.assertEqual(session.boot()["settings"]["require_done_when"], 1)
		self.assertEqual(settings.get(space=PRIVATE)["settings"]["require_done_when"], 1)
		with self.assertRaises(frappe.ValidationError):
			goals.create(title="i56 never saved", horizon="Long term", space=PRIVATE)

	def test_existing_goals_without_done_when_are_not_blocked(self):
		g = self.make("Life Goal", title="i56 old", horizon="Long term").name
		out = goals.update(g, {"title": "i56 old renamed"})
		self.assertEqual(out["goal"]["title"], "i56 old renamed")
		self.assertFalse(out["goal"]["has_finish_line"])

	def test_10_an_agent_goal_proposal_without_done_when_cannot_be_accepted_until_it_has_one(self):
		item = inbox.create_item(space=PRIVATE, title="Idea", source_type="Message", raw_text="Start the nursery")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		out = inbox.submit_result(item["name"], summary_md="x", proposals=[{"kind": "Goal", "preview": "Nursery", "payload": {"title": "i56 nursery", "horizon": "Long term"}}])
		self.assertEqual(len(out["proposals"]) if "proposals" in out else 1, 1)  # accepted into Needs you
		prop = frappe.get_all("Life Proposal", filters={"inbox_item": item["name"]}, pluck="name")[0]
		self.as_user(OWNER)
		from lifeos.api import brain

		row = next(r for r in brain.needs_you(space=PRIVATE)["rows"] if r["proposal"] == prop)
		self.assertTrue(row["blocked"])
		with self.assertRaises(frappe.ValidationError):
			review.decide(prop, "accept")
		self.assertEqual(frappe.db.get_value("Life Proposal", prop, "status"), "Pending")
		done = review.decide(prop, "accept", {"title": "i56 nursery", "horizon": "Long term", "done_when": "The nursery is planted"})
		self.assertEqual(done["status"], "Accepted")
		self.assertEqual(frappe.db.get_value("Life Goal", done["created_name"], "done_when"), "The nursery is planted")

	def test_make_it_a_goal_needs_a_finish_line(self):
		career = self.life["Career"]
		ts = [self.make("Life Task", title=f"i56 zorbax {n}", area=career).name for n in range(3)]
		from lifeos.api import tasks

		with self.assertRaises(frappe.ValidationError):
			tasks.make_goal(ts, space=PRIVATE, area=career, title="Zorbax")
		out = tasks.make_goal(ts, space=PRIVATE, area=career, title="Zorbax", done_when="Zorbax is delivered")
		self.assertEqual(frappe.db.get_value("Life Goal", out["goal"], "done_when"), "Zorbax is delivered")

	def test_a_month_goal_needs_a_finish_line_too(self):
		plan = journal.month(space=PRIVATE, year=2026, month=11, create=1)["plan"]["name"]
		with self.assertRaises(frappe.ValidationError):
			journal.save_month_goal(plan, title="i56 month")
		journal.save_month_goal(plan, title="i56 month", done_when="Sent")
		self.assertTrue(frappe.db.exists("Life Goal", {"title": "i56 month", "done_when": "Sent"}))

	def test_suggest_without_a_key_gives_two_examples(self):
		out = goals.suggest_measure(title="i56 suggest", space=PRIVATE, horizon="12 weeks")
		self.assertIsNone(out["kind"])
		self.assertEqual(len(out["examples"]), 2)


	def test_11_suggest_sends_the_goals_title_area_actions_and_tasks_to_the_skill(self):
		from lifeos.ai import fake
		from lifeos.tests.test_issue13_task_areas import set_key

		cycle = self.make("Life Cycle", title="i56 s cycle", start_date="2026-11-02", end_date="2027-01-24", status="Active").name
		g = self.make("Life Goal", title="i56 systems", horizon="12 weeks", cycle=cycle, area=self.life["Career"],
			actions=[{"title": "Start the internal audit", "per_week": 2, "status": "Open"}]).name
		self.make("Life Task", title="i56 draft the audit plan", goal=g)
		set_key("sk-test-not-real")
		backend = frappe.flags.lifeos_ai_backend = fake.ScriptedFake([{"content": [{"type": "text", "text": '{"kind": "Milestone", "done_when": "The audit has run twice."}'}],
			"stop_reason": "end_turn", "usage": {"input_tokens": 100, "output_tokens": 10}}])
		try:
			out = goals.suggest_measure(title="i56 systems", goal=g)
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key(None)
		self.assertEqual(out["done_when"], "The audit has run twice.")
		sent = str(backend.received)
		for text in ("Start the internal audit", "i56 draft the audit plan", "Career"):
			self.assertIn(text, sent)


class TestEditGoal(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		frappe.db.delete("Life Cycle", {"space": PRIVATE})
		self.cycle = self.make("Life Cycle", title="i56 cycle", start_date="2026-11-02", end_date="2027-01-24", status="Active").name
		self.goal = self.make("Life Goal", title="i56 RMT", horizon="12 weeks", cycle=self.cycle, done_when="Done",
			actions=[{"title": "Audit", "per_week": 2, "status": "Open"}, {"title": "Newsletter", "per_week": 1, "status": "Open"}]).name

	def test_1_a_rename_keeps_the_goal_and_what_points_to_it(self):
		note = self.make("Life Note", title="i56 note", goal=self.goal, content_md="x").name
		task = self.make("Life Task", title="i56 task", goal=self.goal).name
		out = goals.edit(self.goal, {"title": "i56 RMT systems"})
		self.assertEqual(out["goal"]["name"], self.goal)
		self.assertEqual(out["goal"]["title"], "i56 RMT systems")
		self.assertEqual(frappe.db.get_value("Life Note", note, "goal"), self.goal)
		self.assertEqual(frappe.db.get_value("Life Task", task, "goal"), self.goal)
		self.assertEqual(frappe.db.get_value("Life Goal", self.goal, "cycle"), self.cycle)
		self.assertTrue(frappe.get_all("Comment", filters={"reference_doctype": "Life Goal", "reference_name": self.goal, "content": ("like", "%renamed%")}))

	def test_2_the_area_can_be_changed_to_a_part(self):
		tea = self.areas["Tea"]  # a part of Career
		out = goals.edit(self.goal, {"area": tea})
		self.assertEqual(out["goal"]["area"], tea)
		res = goals.by_area(space=PRIVATE, show="open")
		self.assertIn(self.goal, [g["name"] for s in res["sections"] for grp in s["groups"] for g in grp["goals"]])

	def test_3_actions_can_be_added_retired_renamed_and_reordered(self):
		acts = journal.goal(self.goal)["goal"]["actions"]
		audit, news = acts[0], acts[1]
		out = goals.edit(self.goal, {}, actions=[
			{"name": news["name"], "title": "RMT newsletter", "per_week": 1},
			{"name": audit["name"], "title": audit["title"], "per_week": 2, "retired": True},
			{"title": "Training programme", "per_week": 3}])
		self.assertEqual(out["goal"]["title"], "i56 RMT")
		page = journal.goal(self.goal)
		self.assertEqual([(a["title"], a["status"]) for a in page["goal"]["actions"]],
			[("RMT newsletter", "Open"), ("Audit", "Dropped"), ("Training programme", "Open")])
		grid = next(g for g in journal.rules.grid(self.cycle)["goals"] if g["name"] == self.goal)
		self.assertEqual([a["title"] for a in grid["actions"]], ["RMT newsletter", "Audit", "Training programme"])
		cycles = next(g for c in journal.goals(space=PRIVATE)["cycles"] if c["name"] == self.cycle for g in c["goals"] if g["name"] == self.goal)
		self.assertEqual(cycles["actions"], 2)  # the retired one is not counted
		again = goals.edit(self.goal, {}, actions=[{"name": audit["name"], "title": "Audit", "per_week": 2}])
		self.assertTrue(again)
		self.assertEqual(frappe.db.get_value("Life Goal Action", audit["name"], "status"), "Open")

	def test_4_5_the_goal_page_finds_its_cycle_and_counts_this_weeks_ticks(self):
		got = goals.get(self.goal)
		self.assertEqual(got["cycle"]["title"], "i56 cycle")
		page = journal.goal(self.goal)
		self.assertEqual(page["cycle"]["name"], self.cycle)
		week = page["this_week"]
		self.assertEqual(week["planned"], 3)
		self.assertEqual(week["done"], 0)

	def test_only_a_writer_can_edit(self):
		self.as_user("family@lifeos.test")
		with self.assertRaises(frappe.PermissionError):
			goals.edit(self.goal, {"title": "no"})
