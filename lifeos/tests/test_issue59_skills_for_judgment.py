"""Issue 59: the 12 hard-coded prompts are in skills (tidy-backlog, plan-week, notice, define-goal, reflect, guess-area, ask), and the
duplicate decisions and rule fallbacks are gone. The model is always faked."""
import ast
import json
from pathlib import Path

import frappe
from frappe.utils import today

from lifeos import insights, old_inbox, readings
from lifeos.ai import batches, fake
from lifeos.api import goals as goals_api
from lifeos.api import old_items, reset, weekly
from lifeos.review import goals as goals_mod
from lifeos.review import pile_sort, piles
from lifeos.review.record import Review
from lifeos.skills import examples, runner, store
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase
from lifeos.tests.test_set8_goals import GoalsCase
from lifeos.tests.test_set8_review import ReviewCase, tidy
from lifeos.tests.test_ux5_ask import set_key

APP = Path(frappe.get_app_path("lifeos"))
NEW_SKILLS = ("tidy-backlog", "plan-week", "notice", "define-goal", "reflect", "guess-area")
# the Python lines of the modules that held the prompts, before this issue (also in DECISIONS.md, "Issue 59")
LINES_BEFORE = {"old_inbox.py": 283, "ai/batches.py": 54, "review/pile_sort.py": 166, "weekplan.py": 260, "review/goals.py": 276, "ai/insights.py": 90,
	"review/followups.py": 140, "readings.py": 328, "goal_suggest.py": 58, "review/lock.py": 161, "area_guess.py": 257, "ai/ask.py": 128}


def text(**out):
	return {"content": [{"type": "text", "text": json.dumps(out)}], "stop_reason": "end_turn"}


def skill_answers(*by_skill):
	"""A faked model answering each request with the function of its skill: [(skill, fn(data) -> output)]."""
	table = dict(by_skill)

	def run(params):
		slug, data = fake.asked(params)
		return text(**table[slug](data))
	return fake.ScriptedFake([run] * 12)


class Keyed(LifeTestCase):
	"""A site with a key, and a model the test supplies."""

	def setUp(self):
		super().setUp()
		set_key("sk-test-not-real")
		frappe.set_user(OWNER)

	def tearDown(self):
		frappe.flags.lifeos_ai_backend = None
		frappe.set_user("Administrator")
		set_key("")
		super().tearDown()


class TestNoPromptsInCode(LifeTestCase):
	def test_no_python_file_outside_skills_and_the_client_has_a_model_prompt(self):
		"""I59.1: a walk over the code for `.call(purpose, system, …)` where the system prompt is written in the file."""
		found = []
		for path in sorted(APP.rglob("*.py")):
			rel = path.relative_to(APP).as_posix()
			if rel.startswith(("skills/", "tests/")) or rel == "ai/client.py" or "/node_modules/" in rel:
				continue
			tree = ast.parse(path.read_text())
			literal = {t.id for n in tree.body if isinstance(n, ast.Assign) and _is_text(n.value) for t in n.targets if isinstance(t, ast.Name)}
			for node in ast.walk(tree):
				if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "call" and len(node.args) >= 2:
					system = node.args[1]
					if _is_text(system) or (isinstance(system, ast.Name) and system.id in literal):
						found.append(f"{rel}:{node.lineno}")
		self.assertEqual(found, [])

	def test_the_asks_instructions_are_a_skill_the_owner_can_read(self):
		self.assertIn("Answer only from what the tools return", store.instructions_of("ask"))
		self.assertTrue(frappe.db.exists("Life Skill", "ask"))


def _is_text(node):
	return (isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 40) or isinstance(node, ast.JoinedStr) or (
		isinstance(node, ast.BinOp) and _is_text(node.left))


class TestTidyBacklog(ReviewCase):
	def test_one_skill_decides_for_old_inbox_items_reset_and_the_review_piles(self):
		"""I59.2: keep, park or drop comes from tidy-backlog for all three; the three old modules no longer decide."""
		for gone in (old_inbox.__dict__, pile_sort.__dict__, batches.__dict__):
			self.assertFalse({"rule_decision", "fake_decisions", "fake_sort", "SYSTEM", "SCHEMA"} & set(gone))
		self.assertNotIn("rule", pile_sort.__dict__)
		old = self.old_item("i59 old task", ["Task"], age=20)
		tasks = [self.task(f"i59 stuck {i}", age=90) for i in range(4)]
		table = {"i59 old task": "park", **{f"i59 stuck {i}": "drop" for i in range(4)}}

		def decide(data):
			return {"decisions": [{"item": i["item"], "decision": table[i["title"]], "reason": "because", "group": "i59 stuck tasks"} for i in data["items"] if i["title"] in table]}

		with tidy(lambda i: None):  # the helper switches the key and the space on; the model below replaces its answers
			backend = frappe.flags.lifeos_ai_backend = skill_answers(("tidy-backlog", decide), ("notice", lambda d: {"insights": [], "follow_ups": [], "readings": []}))
			got, label = old_inbox.suggest(PRIVATE, [i for i in old_inbox.candidates(PRIVATE, 7) if i.name == old])
			rows = batches.suggest(PRIVATE, [])
			weekly.start(space=PRIVATE)
			items = {i["name"]: i for i in piles.PileSet(Review.find_open(PRIVATE, OWNER), "tasks").items()}
			asked = [fake.asked(r)[0] for r in backend.received]
		self.assertEqual((got[old], label), (("Park", "because"), "tidy-backlog v1"))
		self.assertEqual([(b["title"], b["action"], b["count"]) for b in rows], [("i59 stuck tasks", "drop", 4)])
		self.assertEqual({items[t]["pile"] for t in tasks}, {"letgo"})
		self.assertEqual(asked.count("tidy-backlog"), 4)  # old Inbox, Reset, the review's two tabs


class TestPlanWeek(GoalsCase):
	def test_plan_week_fills_next_actions_and_stars_and_code_places_the_slots(self):
		"""I59.3: the skill writes the next actions and picks three stars; slots stay inside working hours with no overlaps."""
		from datetime import timedelta

		from frappe.utils import get_datetime

		from lifeos import weekplan

		def plan(data):
			if data["request"] == "stars":
				return {"plans": [], "stars": ["G4", "G3", "G2"]}
			return {"plans": [{"goal": g["goal"], "next_action": f"Do the first step of {g['title']}", "minutes": 90} for g in data["goals"]], "stars": []}

		with tidy(lambda i: None):
			frappe.flags.lifeos_ai_backend = skill_answers(("plan-week", plan), ("tidy-backlog", lambda d: {"decisions": []}),
				("notice", lambda d: {"insights": [], "follow_ups": [], "readings": []}), ("reflect", lambda d: {"sentence": ""}))
			weekly.start(space=PRIVATE)
			rows = {r["goal"]: r for r in weekly.goals(space=PRIVATE)["rows"]}
			stars = weekly.goals(space=PRIVATE)["stars"]
		self.assertEqual(rows[self.goals[0]]["plan"]["next_action"], "Do the first step of s8 cycle goal 0")
		self.assertEqual(rows[self.goals[0]]["plan"]["by"], "plan-week v1")
		self.assertEqual(rows[self.goals[0]]["plan"]["minutes"], 90)
		self.assertEqual(set(stars), set(self.goals[1:]))  # G2, G3 and G4 of the skill
		h, taken = weekplan.hours(), []
		for r in rows.values():
			s = get_datetime(r["plan"]["slot"])
			e = s + timedelta(minutes=90)
			self.assertIn(weekplan.DAYS[s.weekday()], h["days"])
			self.assertTrue((s.hour, s.minute) >= h["start"] and (e.hour, e.minute) <= h["end"])
			self.assertFalse([1 for a, b in taken if s < b and a < e])
			taken.append((s, e))


class TestNotice(Keyed):
	def test_notice_makes_a_promise_insight_and_a_goal_reading_and_a_dismissed_one_stays_hidden(self):
		"""I59.4: the insight and the reading come from notice; the fingerprint still hides a dismissed insight."""
		chat = self.make("Life Chat Log", title="i59 Mithun chat", date=today(), summary_md="I will send six questions to Mithun. Body weight 79.5 kg today.")
		goal = frappe.get_doc({"doctype": "Life Goal", "space": PRIVATE, "title": "i59 weight", "horizon": "Long term", "measure_kind": "Number",
			"measure": "Body weight", "unit": "kg", "start_value": 84, "target_value": 78}).insert()

		def notice(data):
			ref = next(r["ref"] for r in data["records"] if r["title"] == "i59 Mithun chat")
			if data["request"] == "insights":
				return {"insights": [{"kind": "Promise", "title": "You said you would send six questions to Mithun.", "evidence": [ref],
					"task_title": "Send six questions to Mithun"}], "follow_ups": [], "readings": []}
			g = next(g["goal"] for g in data["goals"] if g["title"] == "i59 weight")
			return {"insights": [], "follow_ups": [], "readings": [{"goal": g, "value": 79.5, "record": ref, "excerpt": "Body weight 79.5 kg today"}]}

		frappe.flags.lifeos_ai_backend = skill_answers(("notice", notice))
		frappe.db.delete("Life Insight", {"space": PRIVATE})
		insights.run(PRIVATE, ai=True)
		row = frappe.get_all("Life Insight", filters={"space": PRIVATE, "source": "AI"}, fields=["name", "kind", "source_line"])
		self.assertEqual([(r.kind, r.source_line) for r in row], [("Promise", "Suggested by notice v1")])
		made, note = readings.from_recent(PRIVATE, OWNER)
		self.assertIsNone(note)
		_, suggested = readings.for_goal(goal.name)
		self.assertEqual([(r["value"], r["suggested_by"]) for r in suggested], [(79.5, "notice v1")])
		self.assertGreaterEqual(made, 1)
		frappe.db.set_value("Life Insight", row[0].name, {"status": "Dismissed", "dismiss_reason": "Done already"})
		frappe.flags.lifeos_ai_backend = skill_answers(("notice", notice))
		stats = insights.run(PRIVATE, ai=True)
		self.assertEqual(stats["skipped_dismissed"], 1)
		self.assertEqual(frappe.db.count("Life Insight", {"space": PRIVATE, "source": "AI"}), 1)
		self.assertEqual(frappe.db.get_value("Life Insight", row[0].name, "status"), "Dismissed")


class TestDefineGoal(Keyed):
	def test_define_goal_fills_a_finish_line_for_a_goal_with_no_done_when(self):
		"""I59.5: the finish line and a number, and a goal title from tasks, from one skill."""
		frappe.flags.lifeos_ai_backend = fake.SiteFake()
		line = goals_api.suggest_measure("Ship MoneyOS", space=PRIVATE)
		number = goals_api.suggest_measure("Lose 6 kg", space=PRIVATE)
		self.assertEqual((line["kind"], line["done_when"], line["by"]), ("Milestone", "Ship MoneyOS is done", "define-goal v1"))
		self.assertEqual((number["kind"], number["unit"], number["target_value"]), ("Number", "kg", 6))


class TestNoKey(ReviewCase):
	def test_without_a_key_the_screens_show_their_empty_state_or_the_counts_and_no_errors(self):
		"""I59.6: no key: the old-items list is empty, the review opens with its items under Needs you, Reset has no AI batch, no insight
		errors, and every Suggest says there is nothing."""
		set_key("")
		frappe.set_user(OWNER)
		self.old_item("i59 nokey old", ["Task"], age=20)
		stuck = self.task("i59 nokey stuck", age=90)
		self.make("Life Goal", title="i59 nokey goal", horizon="Long term")
		self.assertEqual(old_inbox.run_for_space(PRIVATE), {"mode": "Suggest", "suggested": 0})
		self.assertEqual(old_items.suggested(space=PRIVATE)["rows"], [])
		got = reset.get(space=PRIVATE, ai=1)
		self.assertFalse([b for b in got["batches"] if b["source"] == "AI"])
		self.assertEqual(got["stuck"]["n"], 1)  # the stuck-task count is a count, not a judgment
		head = weekly.start(space=PRIVATE)
		self.assertTrue(head["name"])
		tab = piles.PileSet(Review.find_open(PRIVATE, OWNER), "tasks").summary()
		self.assertEqual(([r["ref"] for r in tab["needs"]], tab["by"]), ([f"Life Task:{stuck}"], None))
		self.assertEqual(weekly.goals(space=PRIVATE)["rows"][0]["plan"]["by"] if weekly.goals(space=PRIVATE)["rows"] else None, None)
		self.assertEqual(insights.run(PRIVATE, ai=True)["ai"], "AI insights skipped: no API key.")
		self.assertEqual(readings.from_recent(PRIVATE, OWNER), (0, None))
		self.assertEqual(goals_api.suggest_measure("Lose 6 kg", space=PRIVATE)["kind"], None)
		self.assertEqual(goals_mod.weekplan.suggest(PRIVATE, [], {}), ({}, None))


class TestExamples(LifeTestCase):
	def test_every_new_skills_examples_pass_against_their_recorded_answers(self):
		"""I59.7 (CI): the recorded answers replay against the shipped text; a changed skill must be re-recorded."""
		checked = 0
		for slug in NEW_SKILLS:
			skill, current = examples.shipped_skill(slug), store.digest(store.builtin(slug))
			files = examples.files_of(slug)
			self.assertGreaterEqual(len(files), 2, slug)
			for path in files:
				data = json.loads(path.read_text())
				self.assertEqual(data.get("skill_hash"), current, f"{slug} changed since {path.name} was recorded. Record the fixtures with: "
					f"bench --site SITE execute lifeos.skills.record --kwargs \"{{'skill': '{slug}'}}\"")
				state = runner.generate(skill, PRIVATE, examples.blocks_of(slug, data["input"]), replay=data["fixture"], lenient=True)
				results = examples.evaluate(data["checks"], state["output"], state["proposals"])
				self.assertTrue(all(r["passed"] for r in results), f"{slug}: {data['title']}: {results}")
				checked += 1
		self.assertGreaterEqual(checked, 14)


class TestLessCode(LifeTestCase):
	def test_the_modules_that_held_the_prompts_are_shorter_than_before(self):
		"""I59.8: the total number of lines of those modules is lower than before (the numbers are in DECISIONS.md)."""
		now = {name: len((APP / name).read_text().splitlines()) if (APP / name).exists() else 0 for name in LINES_BEFORE}
		self.assertLess(sum(now.values()), sum(LINES_BEFORE.values()), now)
