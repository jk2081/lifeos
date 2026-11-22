"""Issue 54: the core card, the index, the one call that returns them, sources recorded by Life OS, and the light weekly wiki check."""
import json

import frappe
from frappe.utils import add_days, today

from lifeos import context, wiki_check
from lifeos.ai import fake
from lifeos.api import context as context_api
from lifeos.api import jobs, wiki
from lifeos.skills import call
from lifeos.tests.base import AGENT, OWNER, PRIVATE, LifeTestCase
from lifeos.tests.test_issue59_skills_for_judgment import Keyed


def clean():
	for dt in ("Life Note", "Life Person", "Life Goal", "Life Cycle", "Life Inbox Item", "Life Wiki Finding", "Life Link"):
		frappe.db.delete(dt, {"space": PRIVATE})
	frappe.db.delete("Life Index", {"space": PRIVATE})
	context.changed()


class TestContext(LifeTestCase):
	def setUp(self):
		super().setUp()
		clean()

	def page(self, title, summary, text="x", **kw):
		return self.make("Life Note", title=title, collection="Wiki", summary=summary, content_md=text, **kw)

	# 1
	def test_1_the_card_holds_the_areas_the_goals_and_the_cycle_week_and_changes_with_a_goal(self):
		cycle = self.make("Life Cycle", title="i54 cycle", start_date=add_days(today(), -14), status="Active")
		self.make("Life Goal", title="i54 Open the Pune dealership", area=self.areas["Tea"], cycle=cycle.name, horizon="12 weeks", done_when="Keys in hand")
		text = context.card(PRIVATE)
		self.assertLess(context.words(text), 1500)
		self.assertIn("Areas that are on", text)
		self.assertIn("Tea", text)
		self.assertIn("i54 Open the Pune dealership", text)
		self.assertIn("Keys in hand", text)
		self.assertIn("week 3 of 12", text)
		self.make("Life Goal", title="i54 Run a half marathon", area=self.life["Health"], horizon="Year", target_date=add_days(today(), 200))
		self.assertIn("i54 Run a half marathon", context.card(PRIVATE))  # cached, and rebuilt when a goal is added

	def test_1b_a_card_with_a_huge_rules_page_stays_under_the_limit(self):
		self.make("Life Note", title="Wiki rules", collection="Wiki", is_rules=1, summary="Rules", content_md=("word " * 5000))
		self.assertLess(context.words(context.card(PRIVATE)), 1500)

	# 2
	def test_2_a_page_or_a_person_adds_one_index_line_a_rename_changes_it_and_a_person_is_listed_once(self):
		before = len(context.index_lines(PRIVATE))
		p = self.page("i54 Mehi Motors", "Honda dealership in Ranchi")
		self.assertEqual(len(context.index_lines(PRIVATE)), before + 1)
		line = next(x for x in context.index_lines(PRIVATE) if x["name"] == p.name)
		self.assertEqual((line["title"], line["kind"], line["summary"], line["updated"]), ("i54 Mehi Motors", "wiki", "Honda dealership in Ranchi", today()))
		p.reload()
		p.title = "i54 Mehi Motors Pvt Ltd"
		p.save()
		self.assertEqual([x["title"] for x in context.index_lines(PRIVATE) if x["name"] == p.name], ["i54 Mehi Motors Pvt Ltd"])
		page = wiki.create_page(space=PRIVATE, title="i54 Mr Rao", summary="Our manager at the dealership", content_md="x", about="Person")
		titles = [x["title"] for x in context.index_lines(PRIVATE)]
		self.assertEqual(titles.count("i54 Mr Rao"), 1)  # the person, once; never also the page about them
		self.assertEqual(next(x for x in context.index_lines(PRIVATE) if x["title"] == "i54 Mr Rao")["doctype"], "Life Person")
		self.assertEqual(len(titles), before + 2)
		self.assertTrue(frappe.db.exists("Life Note", page["name"]))
		long = self.page("i54 Long summary", " ".join(f"w{i}" for i in range(40)))
		self.assertEqual(len(next(x for x in context.index_lines(PRIVATE) if x["name"] == long.name)["summary"].split()), 15)

	# 3
	def test_3_get_with_no_task_returns_the_card_and_the_index_and_with_a_task_the_matches_in_budget(self):
		self.page("Mehi Motors", "Honda dealership in Ranchi", "Four showrooms. Owner is Mr Rao. They want a demo of the app.")
		self.page("Tea estate", "Ghatia estate tea", "Tea.")
		out = context_api.get(space=PRIVATE)
		self.assertTrue(out["card"])
		self.assertEqual({x["title"] for x in out["index"]}, {"Mehi Motors", "Tea estate"})
		out = context_api.get(space=PRIVATE, task="Mehi Motors demo", budget=600)
		self.assertEqual([x["title"] for x in out["index"]], ["Mehi Motors"])
		self.assertEqual(out["pages"][0]["title"], "Mehi Motors")
		self.assertIn("demo", out["pages"][0]["excerpt"])
		self.assertLessEqual(out["words"], 600)
		self.assertTrue(out["card"])
		tight = context_api.get(space=PRIVATE, task="Mehi Motors demo", budget=context.words(out["card"]) + 5)
		self.assertEqual((tight["index"], tight["pages"]), ([], []))  # the card always comes whole; the rest gives way to the budget

	# 4
	def test_4_sensitive_pages_never_reach_an_agent_whose_space_keeps_them_closed(self):
		self.page("i54 Open page", "Fine to share", "Mehi Motors fine.")
		self.page("i54 Secret Mehi page", "Mehi Motors bank details", "Mehi Motors secret.", is_sensitive=1)
		self.as_user(OWNER)
		self.assertIn("i54 Secret Mehi page", [x["title"] for x in context_api.get(space=PRIVATE)["index"]])
		self.as_user(AGENT)
		self.assertFalse(frappe.db.get_value("Life Space", PRIVATE, "agents_can_read_vault"))
		for task in (None, "Mehi Motors bank details"):
			out = context_api.get(space=PRIVATE, task=task)
			self.assertNotIn("i54 Secret Mehi page", json.dumps(out))
			self.assertIn("i54 Open page", json.dumps(out)) if not task else None
		self.as_user("Administrator")
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 1)
		permissions_clear()
		try:
			self.as_user(AGENT)
			self.assertIn("i54 Secret Mehi page", [x["title"] for x in context_api.get(space=PRIVATE)["index"]])
		finally:
			self.as_user("Administrator")
			frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
			permissions_clear()

	# 5
	def test_5_a_fact_filed_through_the_filing_call_records_its_job_and_day_without_the_agent_passing_one(self):
		self.as_user(AGENT)
		out = jobs.file_job(job_id="i54-mehi-job", space=PRIVATE, title="i54 Mehi Motors deck", summary_md="A deck.",
			wiki=[{"title": "i54 Mehi Motors", "summary": "Honda dealership", "content_md": "Four showrooms."}])
		got = wiki.get_page(out["wiki"][0]["name"])
		self.assertEqual([(s["doctype"], s["name"], s["added_on"]) for s in got["sources"]], [("Life Inbox Item", out["item"], today())])
		later = jobs.file_job(job_id="i54-mehi-job-2", space=PRIVATE, title="i54 Second job", summary_md="More.",
			wiki=[{"title": "i54 Mehi Motors", "summary": "Honda dealership", "content_md": "Five showrooms from March."}])
		got = wiki.get_page(later["wiki"][0]["name"])
		self.assertEqual({s["name"] for s in got["sources"]}, {out["item"], later["item"]})
		self.assertTrue(all(s["added_on"] for s in got["sources"]))


def permissions_clear():
	from lifeos import permissions

	permissions.clear_cache()


def answers(**out):
	def run(params):
		slug, _data = fake.asked(params)
		return {"content": [{"type": "text", "text": json.dumps(out)}], "stop_reason": "end_turn"}
	return fake.ScriptedFake([run] * 4)


class TestWeeklyCheck(Keyed):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		clean()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def page(self, title, summary, text):
		return self.make("Life Note", title=title, collection="Wiki", summary=summary, content_md=text)

	def capture(self, title, text):
		return self.make("Life Inbox Item", title=title, source_type="Upload", status="Done", raw_text=text, received_on=today())

	def ask_with(self, **out):
		frappe.flags.lifeos_ai_backend = answers(**out)
		return wiki_check.run(PRIVATE)

	# 6
	def test_6_the_check_links_an_orphan_proposes_a_page_for_a_name_in_three_captures_and_raises_one_contradiction(self):
		mehi = self.page("i54 Mehi Motors", "Honda dealership", "Mehi Motors has 4 dealerships in Jharkhand.")
		ranchi = self.page("i54 Ranchi accounts", "Accounts in Ranchi", "Mehi Motors has 6 dealerships in Jharkhand.")
		lone = self.page("i54 Lone deck", "A deck", "Pricing.")
		for i in range(3):
			self.capture(f"i54 call {i}", f"Visit i54 Ghatia Estate on day {i}")
		self.capture("i54 other", "Nothing about estates, only i54 Two Names once")
		call_ids = {}

		def run(params):
			_slug, data = fake.asked(params)
			call_ids.update({p["title"]: p["id"] for p in data["pages"]})
			by = call_ids
			return {"content": [{"type": "text", "text": json.dumps({
				"orphans": [{"page": by["i54 Lone deck"], "action": "link", "link_to": by["i54 Mehi Motors"], "reason": "pitch"}],
				"missing": [{"name": "i54 Ghatia Estate", "summary": "Tea estate"}, {"name": "i54 Two Names", "summary": "Seen once"}],
				"stale": [{"page": by["i54 Ranchi accounts"], "summary": "Dealership counts for Mehi Motors"}],
				"contradictions": [{"topic": "Mehi dealership count", "question": "Two pages disagree on Mehi Motors' dealership count: keep which?",
					"options": [{"page": by["i54 Mehi Motors"], "fact": "Mehi Motors has 4 dealerships in Jharkhand."},
						{"page": by["i54 Ranchi accounts"], "fact": "Mehi Motors has 6 dealerships in Jharkhand."},
						{"page": by["i54 Mehi Motors"], "fact": "A fact that is not on the page."}]}]})}], "stop_reason": "end_turn"}
		frappe.flags.lifeos_ai_backend = fake.ScriptedFake([run])
		out = wiki_check.run(PRIVATE)
		self.assertEqual(out["linked"], [lone.name])
		self.assertIn("[[i54 Lone deck]]", frappe.db.get_value("Life Note", mehi.name, "content_md"))
		self.assertTrue(frappe.db.exists("Life Link", {"from_name": mehi.name, "to_name": lone.name}))
		self.assertEqual(len(out["created"]), 1)  # three captures name Ghatia Estate; one names Two Names
		self.assertEqual(frappe.db.get_value("Life Note", out["created"][0], "title"), "i54 Ghatia Estate")
		self.assertEqual(len(frappe.get_doc("Life Note", out["created"][0]).sources), 3)
		self.assertEqual(frappe.db.get_value("Life Note", ranchi.name, "summary"), "Dealership counts for Mehi Motors")
		self.assertEqual(len(out["findings"]), 1)
		finding = frappe.get_doc("Life Wiki Finding", out["findings"][0])
		self.assertEqual(len(json.loads(finding.options)), 2)  # the fact that is not on the page is dropped
		self.frappe_clear = None
		frappe.flags.lifeos_ai_backend = fake.ScriptedFake([run])
		again = wiki_check.run(PRIVATE)
		self.assertEqual(again["findings"], [])  # the same contradiction is raised once
		self.assertEqual(frappe.db.count("Life Wiki Finding", {"space": PRIVATE, "status": "Open"}), 1)
		self.as_user(OWNER)
		shown = frappe.get_attr("lifeos.api.brain.needs_you")(space=PRIVATE)["contradictions"]
		self.assertEqual([c["question"] for c in shown], ["Two pages disagree on Mehi Motors' dealership count: keep which?"])

	def test_7_deciding_leaves_every_page_with_the_chosen_fact_and_its_source(self):
		src = self.capture("i54 invoice", "Six dealerships")
		a = self.page("i54 Mehi Motors", "Dealer", "Mehi Motors has 4 dealerships in Jharkhand.")
		b = self.make("Life Note", title="i54 Ranchi accounts", collection="Wiki", summary="Accounts", content_md="Mehi Motors has 6 dealerships in Jharkhand.",
			sources=[{"source_doctype": "Life Inbox Item", "source_name": src.name}])
		f = frappe.get_doc({"doctype": "Life Wiki Finding", "space": PRIVATE, "topic": "count", "question": "keep which?", "status": "Open", "options": json.dumps([
			{"page": a.name, "title": a.title, "fact": "Mehi Motors has 4 dealerships in Jharkhand.", "source_doctype": None, "source_name": None},
			{"page": b.name, "title": b.title, "fact": "Mehi Motors has 6 dealerships in Jharkhand.", "source_doctype": "Life Inbox Item", "source_name": src.name}])}).insert()
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, context_api.decide, f.name, 1)
		self.as_user(OWNER)
		context_api.decide(f.name, 1)
		a.reload()
		self.assertIn("6 dealerships", a.content_md)
		self.assertNotIn("4 dealerships", a.content_md)
		self.assertEqual([r.source_name for r in a.sources], [src.name])
		self.assertEqual(frappe.db.get_value("Life Wiki Finding", f.name, "status"), "Decided")
		self.assertRaises(frappe.ValidationError, context_api.decide, f.name, 1)

	def test_8_with_no_answer_from_the_skill_nothing_changes(self):
		self.page("i54 Mehi Motors", "Dealer", "x")
		frappe.flags.lifeos_ai_backend = None
		from lifeos.tests.test_ux5_ask import set_key
		set_key("")
		out = wiki_check.run(PRIVATE)
		self.assertIn("skipped", out)
		self.assertEqual(call.ask("check-wiki", {}, PRIVATE).reason, "no AI key")
