"""Tests for agents."""
import base64
import json
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from lifeos.agents import context
from lifeos.library import files, wiki_check
from lifeos import permissions
from lifeos.ai import fake
from lifeos.api import context as context_api, inbox, jobs, review, wiki
from lifeos.skills import call as call_skills
from lifeos.tests.base import AGENT, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import Keyed, set_key, task, text


DECK = b"issue 8 standard deck"


BRAND = b"issue 8 brand guidelines"


def b64(data):
	return base64.b64encode(data).decode()


def call(job_id="i8-mehi-pitch", **kw):
	args = {
		"space": PRIVATE, "title": "i8 Mehi Motors: owner-first sales deck", "instruction": "Make a deck for Mehi Motors from my standard deck.",
		"inputs": [{"name": "BTW standard deck.txt", "file": b64(DECK), "reusable_as": "i8-btw-standard-deck"},
			{"name": "BTW brand guidelines.txt", "file": b64(BRAND), "reusable_as": "i8-btw-brand"}],
		"outputs": [{"name": "Mehi Motors deck.txt", "file": b64(b"i8 the deck")}, {"name": "Mehi Motors deck.html", "file": b64(b"<p>i8 the deck</p>")}],
		"transcript_md": "Slide 1: why Mehi Motors", "summary_md": "A deck for Mehi Motors, from [[BTW standard deck]].",
		"proposals": [{"kind": "Note", "preview": "i8 the record of the work", "payload": {"title": "i8 Mehi Motors deck", "content_md": "The deck."}, "confidence": 0.9},
			{"kind": "Task", "preview": "i8 score the questionnaire", "payload": {"title": "i8 Score the questionnaire"}, "confidence": 0.7}],
		"wiki": [{"title": "i8 Mehi Motors Pvt Ltd", "summary": "Honda dealership", "content_md": "A Honda two-wheeler dealership."}],
		"chat": {"title": "i8 Mehi Motors deck with Hermes", "summary_md": "Asked for a deck.", "open_items": ["Check Vahan"], "source_system": "hermes-telegram"},
		"source_system": "hermes",
	}
	args.update(kw)
	return jobs.file_job(job_id=job_id, **args)


def counts():
	return {dt: frappe.db.count(dt) for dt in ("Life Inbox Item", "Life Proposal", "Life Note", "Life Chat Log", "File", "Life Wiki Change")}


def stored(content):
	return {r.file_url for r in frappe.get_all("File", filters={"life_sha256": files.sha256(content)}, fields=["file_url"])}


class TestFileJob(LifeTestCase):
	def setUp(self):
		super().setUp()
		self.as_user(AGENT)

	def test_1_one_call_files_one_item_with_its_inputs_outputs_proposals_wiki_and_chat(self):
		before = counts()
		out = call()
		self.assertTrue(out["created"])
		self.assertEqual(frappe.db.count("Life Inbox Item", {"job_id": "i8-mehi-pitch"}), 1)
		got = inbox.get(out["item"])
		self.assertEqual(got["status"], "To Review")
		self.assertEqual(got["intent"], "Process")
		self.assertEqual(got["instruction"], "Make a deck for Mehi Motors from my standard deck.")
		self.assertEqual(sorted(f["file_name"] for f in got["files"]), ["Mehi Motors deck.html", "Mehi Motors deck.txt"])
		# two input assets, each its own kept item, linked to the job as inputs and not as its files
		self.assertEqual(len(got["inputs"]), 2)
		for row in got["inputs"]:
			asset = frappe.get_doc("Life Inbox Item", row["asset"])
			self.assertEqual((asset.intent, asset.status), ("Just keep", "Done"))
			self.assertEqual(len(files.attachments("Life Inbox Item", asset.name)), 1)
			self.assertEqual(row["file"]["file_name"], row["name"])
		self.assertEqual({r["reusable_as"] for r in got["inputs"]}, {"i8-btw-standard-deck", "i8-btw-brand"})
		self.assertEqual(sorted(p["status"] for p in got["proposals"]), ["Pending", "Pending"])
		self.assertEqual(len(out["proposals"]["waiting"]), 2)
		self.assertEqual(got["summary_md"], "A deck for Mehi Motors, from [[BTW standard deck]].")
		# the wiki page and the chat log, each linked to the item
		self.assertEqual(len(got["wiki_pages"]), 1)
		page = frappe.get_doc("Life Note", got["wiki_pages"][0]["name"])
		self.assertEqual(page.collection, "Wiki")
		self.assertIn(("Life Inbox Item", out["item"]), {(s.source_doctype, s.source_name) for s in page.sources})
		self.assertIn(("Life Chat Log", out["chat"]["name"]), {(s.source_doctype, s.source_name) for s in page.sources})
		self.assertEqual(got["job_chat"]["name"], out["chat"]["name"])
		chat = frappe.get_doc("Life Chat Log", out["chat"]["name"])
		self.assertEqual([i.text for i in chat.open_items], ["Check Vahan"])
		after = counts()
		self.assertEqual(after["Life Inbox Item"] - before["Life Inbox Item"], 3)  # the job and two assets
		self.assertEqual(after["Life Proposal"] - before["Life Proposal"], 2)
		self.assertEqual(after["Life Note"] - before["Life Note"], 1)
		self.assertEqual(after["Life Chat Log"] - before["Life Chat Log"], 1)
		self.assertEqual(after["File"] - before["File"], 4)
		self.assertTrue(out["url"].endswith(f"/life/item/{out['item']}"))

	def test_2_the_same_call_again_creates_nothing_and_updates_what_changed(self):
		first = call("i8-again")
		before = counts()
		same = call("i8-again")
		self.assertEqual(same["item"], first["item"])
		self.assertFalse(same["created"])
		self.assertEqual(same["changed_fields"], [])
		self.assertEqual(counts(), before)
		self.assertFalse(any(o["attached"] for o in same["outputs"]))
		self.assertFalse(any(i["asset_created"] or i["attached"] for i in same["inputs"]))
		self.assertEqual(same["proposals"]["created"], [])
		self.assertFalse(same["wiki"][0]["changed"])
		self.assertFalse(same["chat"]["created"])
		# changed fields are updated, still on the one item
		changed = call("i8-again", title="i8 Mehi Motors: deck, second cut", summary_md="A shorter deck.",
			instruction="Make it shorter.", wiki=[{"title": "i8 Mehi Motors Pvt Ltd", "content_md": "A Honda dealership in Kolkata."}])
		self.assertEqual(changed["item"], first["item"])
		self.assertEqual(set(changed["changed_fields"]), {"title", "summary_md", "instruction"})
		doc = frappe.get_doc("Life Inbox Item", first["item"])
		self.assertEqual((doc.title, doc.summary_md, doc.instruction), ("i8 Mehi Motors: deck, second cut", "A shorter deck.", "Make it shorter."))
		page = frappe.get_doc("Life Note", changed["wiki"][0]["name"])
		self.assertEqual(page.content_md, "A Honda dealership in Kolkata.")  # this job wrote it last, so its text is replaced
		self.assertEqual(frappe.db.count("Life Inbox Item", {"job_id": "i8-again"}), 1)
		self.assertEqual(frappe.db.count("Life Note", {"space": PRIVATE, "title": "i8 Mehi Motors Pvt Ltd"}), 1)
		# a proposal no longer sent goes while pending; a new one is added
		fewer = call("i8-again", proposals=[{"kind": "Task", "preview": "i8 call the owner", "payload": {"title": "i8 Call the owner"}}])
		self.assertEqual(len(fewer["proposals"]["removed"]), 2)
		self.assertEqual([p.preview for p in fewer["proposals"]["waiting"]], ["i8 call the owner"])

	def test_3_a_second_job_links_the_asset_already_kept_and_stores_no_new_file(self):
		first = call("i8-first")
		deck_files = frappe.db.count("File", {"life_sha256": files.sha256(DECK)})
		assets = frappe.db.count("Life Inbox Item", {"external_id": "i8-btw-standard-deck"})
		second = call("i8-second", title="i8 Arora Motors deck", wiki=[], chat=None, proposals=[],
			inputs=[{"name": "BTW standard deck.txt", "file": b64(DECK), "reusable_as": "i8-btw-standard-deck"},
				{"name": "BTW brand guidelines.txt", "reusable_as": "i8-btw-brand"}],  # no file: the kept one is linked
			outputs=[{"name": "Arora deck.txt", "file": b64(b"i8 arora deck")}])
		self.assertNotEqual(second["item"], first["item"])
		first_assets = {r["asset"] for r in inbox.get(first["item"])["inputs"]}
		self.assertEqual({r["asset"] for r in inbox.get(second["item"])["inputs"]}, first_assets)
		self.assertFalse(any(i["asset_created"] for i in second["inputs"]))
		self.assertEqual(frappe.db.count("Life Inbox Item", {"external_id": "i8-btw-standard-deck"}), assets)
		self.assertEqual(frappe.db.count("File", {"life_sha256": files.sha256(DECK)}), deck_files)
		self.assertEqual(len(stored(DECK)), 1)
		self.assertEqual(second["status"], "Done")  # nothing waits for the owner
		# an input used by this job only is attached to the job but listed as an input, not as an output
		own = call("i8-own", title="i8 own input", wiki=[], chat=None, proposals=[],
			inputs=[{"name": "Their brief.txt", "file": b64(b"i8 the client's own brief")}], outputs=[{"name": "Out.txt", "file": b64(b"i8 out")}])
		got = inbox.get(own["item"])
		self.assertEqual([f["file_name"] for f in got["files"]], ["Out.txt"])
		self.assertEqual(got["inputs"][0]["file"]["file_name"], "Their brief.txt")

	def test_4_an_invalid_proposal_refuses_the_whole_call_and_saves_nothing(self):
		before = counts()
		before_disk = len(stored(b"i8 never stored"))
		bad = [{"kind": "Task", "payload": {"title": "i8 fine"}}, {"kind": "Task", "payload": {"title": "i8 bad", "due_date": "not a date"}}]
		with self.assertRaises(frappe.ValidationError) as e:
			call("i8-invalid", proposals=bad, outputs=[{"name": "Out.txt", "file": b64(b"i8 never stored")}])
		self.assertIn("proposals[1]", str(e.exception))
		self.assertEqual(counts(), before)
		self.assertFalse(frappe.db.exists("Life Inbox Item", {"job_id": "i8-invalid"}))
		self.assertEqual(len(stored(b"i8 never stored")), before_disk)
		# a bad file and a bad wiki page are refused the same way, naming the field
		with self.assertRaises(frappe.ValidationError) as e:
			call("i8-invalid", outputs=[{"name": "Out.txt", "file": "not base64!"}])
		self.assertIn("outputs[0].file", str(e.exception))
		with self.assertRaises(frappe.ValidationError) as e:
			call("i8-invalid", wiki=[{"title": "i8 page"}])
		self.assertIn("wiki[0].content_md", str(e.exception))
		self.assertEqual(counts(), before)

	def test_4b_a_failure_while_writing_rolls_everything_back(self):
		before = counts()
		# the wiki pages are written last, after the item, its files, proposals and the chat log
		with patch("lifeos.api.jobs._wiki", side_effect=frappe.ValidationError("boom")):
			with self.assertRaises(frappe.ValidationError):
				call("i8-rollback", outputs=[{"name": "Out.txt", "file": b64(b"i8 rolled back")}])
		self.assertEqual(counts(), before)
		self.assertFalse(stored(b"i8 rolled back"))

	def test_5_an_agent_without_write_access_is_refused(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Life Space Member", {"parent": SHARED, "user": AGENT}, "access", "Read")
		permissions.clear_cache()
		try:
			self.as_user(AGENT)
			with self.assertRaises(frappe.PermissionError):
				call("i8-no-access", space=SHARED)
			self.assertFalse(frappe.db.exists("Life Inbox Item", {"job_id": "i8-no-access"}))
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Life Space Member", {"parent": SHARED, "user": AGENT}, "access", "Write")
			permissions.clear_cache()

	def test_6_agents_still_cannot_accept_proposals(self):
		out = call("i8-no-accept", proposals=[{"kind": "Task", "payload": {"title": "i8 agent may not accept"}, "status": "Accepted"}])
		name = out["proposals"]["waiting"][0].name
		self.assertEqual(frappe.db.get_value("Life Proposal", name, "status"), "Pending")
		with self.assertRaises(frappe.PermissionError):
			review.decide(proposal=name, decision="accept")
		with self.assertRaises(frappe.PermissionError):
			review.decide_all(item=out["item"], decision="accept")
		# filing again cannot decide them either
		again = call("i8-no-accept", proposals=[{"kind": "Task", "payload": {"title": "i8 agent may not accept"}, "status": "Accepted"}])
		self.assertEqual(frappe.db.get_value("Life Proposal", name, "status"), "Pending")
		self.assertEqual(again["status"], "To Review")

	def test_7_a_job_filed_the_old_way_is_taken_over_not_duplicated(self):
		old = inbox.create_item(title="i8 old box", space=PRIVATE, source_system="hermes", external_id="i8-old-way", intent="Just keep")["name"]
		out = call("i8-old-way", wiki=[], chat=None)
		self.assertEqual(out["item"], old)
		self.assertFalse(out["created"])
		doc = frappe.get_doc("Life Inbox Item", old)
		self.assertEqual((doc.job_id, doc.intent, doc.status), ("i8-old-way", "Process", "To Review"))
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE, "external_id": "i8-old-way"}), 1)


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
		from lifeos.tests.helpers import set_key
		set_key("")
		out = wiki_check.run(PRIVATE)
		self.assertIn("skipped", out)
		self.assertEqual(call_skills.ask("check-wiki", {}, PRIVATE).reason, "no AI key")


class TestAgentMethodsExist(LifeTestCase):
	"""Every `lifeos.api.<module>.<method>` that an agent's instructions name is a real whitelisted method."""

	def test_methods_named_in_skills_exist(self):
		import importlib
		import re
		from pathlib import Path

		root = Path(frappe.get_app_path("lifeos"))
		files = [*(root / "skills").glob("*.md"), *(root.parent.parent / "agent").glob("*.md")]
		named = set()
		for f in files:
			named |= set(re.findall(r"lifeos\.api\.([a-z_]+)\.([a-z_]+)", f.read_text()))
		self.assertTrue(named)
		missing = []
		for module, method in sorted(named):
			try:
				fn = getattr(importlib.import_module(f"lifeos.api.{module}"), method, None)
			except ImportError:
				fn = None
			if fn is None or fn not in frappe.whitelisted:
				missing.append(f"lifeos.api.{module}.{method}")
		self.assertEqual(missing, [])
