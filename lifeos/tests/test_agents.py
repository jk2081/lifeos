"""Tests for agents."""
import base64
import json
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from lifeos.agents import acts, connector, context, limits
from lifeos.library import files, wiki_check
from lifeos import permissions
from lifeos.ai import fake
from lifeos.api import agent_connector, agent_page, brain, context as context_api, google, inbox, jobs, review, search, wiki
from lifeos.api import mail as mail_api
from lifeos.skills import call as call_skills
from lifeos.brain import agent_page as pages
from lifeos.mail import gmail
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.test_gmail import FakeGmail, message
from lifeos.tests.helpers import AskCase, Keyed, find, set_key, task, text


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


class TestConnector(LifeTestCase):
	"""Your agent in the open (issue 85): the connector's report, pull and confirm, the owner's changes, and the areas an agent may read."""
	KEY = "i85agent"

	def setUp(self):
		super().setUp()
		for dt in ("Life Agent Fact", "Life Agent Job", "Life Agent Change", "Life Agent Action", "Life Agent Config"):
			frappe.db.delete(dt, {"space": PRIVATE})
		permissions.clear_cache()

	def report(self, **kw):
		self.as_user(AGENT)
		args = {"source_system": self.KEY, "space": PRIVATE, "facts": [{"id": "f1", "text": "Prefers mornings for calls", "origin": "WhatsApp chat", "learned_on": "2026-11-01"},
			{"id": "f2", "text": "Daughter's school is Mehi Public"}], "jobs": [{"id": "j1", "name": "Morning digest", "schedule": "Every day 7:00"}],
			"skills": [{"name": "chase-invoices", "description": "Chases overdue invoices"}], **kw}
		out = agent_connector.report(**args)
		self.as_user(OWNER)
		return out

	def state(self):
		return {dt: frappe.get_all(dt, filters={"space": PRIVATE, "agent": self.KEY}, fields=["name", "modified"], order_by="name") for dt in ("Life Agent Fact", "Life Agent Job")}

	# 1
	def test_1_a_report_creates_facts_jobs_and_settings_and_a_repeat_changes_nothing(self):
		first = self.report()
		self.assertEqual(first["changed"]["facts"], 2)
		page = agent_page.get(self.KEY, space=PRIVATE)
		self.assertEqual([f["text"] for f in page["facts"]].count("Prefers mornings for calls"), 1)
		self.assertEqual([j["title"] for j in page["jobs"]], ["Morning digest"])
		self.assertEqual(page["name"], "Your assistant")
		self.assertEqual(page["skills"][0]["name"], "chase-invoices")
		before = self.state()
		again = self.report()
		self.assertEqual(again["changed"], {"facts": 0, "jobs": 0, "actions": 0})
		self.assertEqual(self.state(), before)
		self.report(facts=[{"id": "f1", "text": "Prefers afternoons for calls"}])  # a new report is the whole memory: f2 is gone, f1 changed
		self.assertEqual([f["text"] for f in agent_page.get(self.KEY, space=PRIVATE)["facts"]], ["Prefers afternoons for calls"])

	# 2
	def test_2_deleting_a_fact_or_pausing_a_job_queues_a_change_the_connector_confirms_or_fails(self):
		self.report()
		page = agent_page.get(self.KEY, space=PRIVATE)
		fact = next(f for f in page["facts"] if f["id"] == "f1")
		other = next(f for f in page["facts"] if f["id"] == "f2")
		job = page["jobs"][0]
		agent_page.delete_fact(self.KEY, fact["name"], space=PRIVATE)
		agent_page.edit_fact(self.KEY, other["name"], "Daughter is at Mehi Public, class 5", space=PRIVATE)
		page = agent_page.pause_job(self.KEY, job["name"], 1, space=PRIVATE)
		self.assertEqual(sorted(c["change"]["status"] for c in (page["facts"] + page["jobs"]) if c["change"]), ["waiting"] * 3)
		self.assertEqual(next(j for j in page["jobs"])["paused"], 1)  # shows the state asked for, as waiting
		self.report()  # a report while the changes wait does not undo them
		self.assertEqual(len(frappe.get_all("Life Agent Fact", filters={"space": PRIVATE, "agent": self.KEY})), 2)
		self.assertEqual(frappe.db.get_value("Life Agent Fact", other["name"], "fact"), "Daughter's school is Mehi Public")
		self.as_user(AGENT)
		got = agent_connector.pull(self.KEY, space=PRIVATE)
		self.assertEqual(sorted(c["kind"] for c in got["changes"]), ["Fact delete", "Fact edit", "Job pause"])
		by_kind = {c["kind"]: c["id"] for c in got["changes"]}
		agent_connector.confirm(self.KEY, changes=[{"id": by_kind["Fact delete"], "status": "applied"}, {"id": by_kind["Fact edit"], "status": "applied"},
			{"id": by_kind["Job pause"], "status": "failed", "reason": "No such job on the server"}], space=PRIVATE)
		self.as_user(OWNER)
		page = agent_page.get(self.KEY, space=PRIVATE)
		self.assertEqual([f["text"] for f in page["facts"]], ["Daughter is at Mehi Public, class 5"])
		self.assertEqual(page["jobs"][0]["change"]["status"], "failed")
		self.assertEqual(page["jobs"][0]["change"]["reason"], "No such job on the server")
		self.assertEqual(page["jobs"][0]["paused"], 0)
		self.as_user(AGENT)
		self.assertEqual(agent_connector.confirm(self.KEY, changes=[{"id": by_kind["Fact delete"], "status": "failed", "reason": "x"}], space=PRIVATE), {"applied": 0, "failed": 0})  # settled once

	# 3
	def test_3_an_area_switched_off_is_left_out_of_context_search_and_records(self):
		note = self.make("Life Note", title="i85 Tea sourcing", collection="Wiki", summary="Where the tea comes from", content_md="Assam estates", area=self.areas["Tea"])
		task = self.make("Life Task", title="i85 Call the Assam estate", area=self.areas["Tea"])
		self.make("Life Note", title="i85 Family trip", collection="Wiki", summary="Goa in December", content_md="Booked", area=self.life["Health"])
		self.report()
		frappe.db.commit()  # the full-text index drops deleted rows only at commit
		self.as_user(AGENT)
		self.assertIn("i85 Tea sourcing", [x["title"] for x in context_api.get(space=PRIVATE)["index"]])
		self.assertTrue(find("i85", space=PRIVATE)["results"])
		self.as_user(OWNER)
		agent_page.set_area(self.KEY, self.areas["Tea"], 0, space=PRIVATE)
		self.as_user(AGENT)
		got = context_api.get(space=PRIVATE)
		titles = [x["title"] for x in got["index"]]
		self.assertNotIn("i85 Tea sourcing", titles)
		self.assertIn("i85 Family trip", titles)
		self.assertNotIn("i85 Call the Assam estate", [r["title"] for r in find("i85", space=PRIVATE)["results"]])
		self.assertIn("i85 Family trip", [r["title"] for r in find("i85", space=PRIVATE)["results"]])
		self.assertEqual(frappe.get_list("Life Task", filters={"name": task.name}), [])
		self.assertFalse(frappe.has_permission("Life Note", "read", note.name))
		self.assertTrue(frappe.has_permission("Life Note", "read", frappe.get_all("Life Note", filters={"title": "i85 Family trip", "space": PRIVATE}, pluck="name")[0]))
		self.as_user(OWNER)
		self.assertIn("i85 Tea sourcing", [r["title"] for r in find("i85", space=PRIVATE)["results"]])  # the owner still sees it
		agent_page.set_area(self.KEY, self.areas["Tea"], 1, space=PRIVATE)
		self.as_user(AGENT)
		self.assertIn("i85 Tea sourcing", [x["title"] for x in context_api.get(space=PRIVATE)["index"]])

	# 4
	def test_4_pay_cannot_be_set_to_anything_but_off(self):
		self.report()
		self.assertEqual(next(c for c in agent_page.get(self.KEY, space=PRIVATE)["can"] if c["key"] == "pay")["mode"], "off")
		for mode in ("ask", "auto"):
			with self.assertRaises(frappe.ValidationError):
				agent_page.set_ability(self.KEY, "pay", mode, space=PRIVATE)
		page = agent_page.set_ability(self.KEY, "send_email", "auto", space=PRIVATE)
		self.assertEqual(next(c for c in page["can"] if c["key"] == "send_email")["mode"], "auto")
		self.assertEqual(next(c for c in page["can"] if c["key"] == "send_email")["change"]["status"], "waiting")
		with self.assertRaises(frappe.ValidationError):
			agent_page.set_ability(self.KEY, "send_email", "maybe", space=PRIVATE)

	def test_5_a_request_waits_in_needs_you_and_approving_moves_it_to_what_it_did(self):
		self.report(actions=[{"id": "a1", "action": "send_email", "title": "Chase Mehi Motors for the invoice", "draft": "Hello, a gentle reminder.", "status": "Waiting"},
			{"id": "a2", "action": "read_email", "title": "Read the morning mail", "cost": 0.0123, "status": "Done"}])
		self.assertEqual([r["title"] for r in brain.needs_you(space=PRIVATE)["agent_requests"]], ["Chase Mehi Motors for the invoice"])
		page = agent_page.get(self.KEY, space=PRIVATE)
		self.assertEqual([d["title"] for d in page["did"]], ["Read the morning mail"])
		agent_page.decide(page["waiting"][0]["name"], "approve", space=PRIVATE)
		page = agent_page.get(self.KEY, space=PRIVATE)
		self.assertEqual((page["waiting"], sorted(d["title"] for d in page["did"])), ([], ["Chase Mehi Motors for the invoice", "Read the morning mail"]))
		self.as_user(AGENT)
		self.assertEqual(agent_connector.pull(self.KEY, space=PRIVATE)["decisions"], [{"id": "a1", "decision": "approved"}])
		agent_connector.confirm(self.KEY, delivered=["a1"], space=PRIVATE)
		self.assertEqual(agent_connector.pull(self.KEY, space=PRIVATE)["decisions"], [])
		with self.assertRaises(frappe.PermissionError):
			agent_page.decide(page["did"][0]["name"], "approve", space=PRIVATE)  # an agent never approves
		self.report()  # a repeated report does not bring it back to waiting
		self.assertEqual(brain.needs_you(space=PRIVATE)["agent_requests"], [])

	def test_6_the_agent_is_shown_under_the_name_the_owner_gives_it_and_only_the_owner_changes_it(self):
		self.report()
		self.assertEqual(agent_page.rename(self.KEY, "Ravi", space=PRIVATE)["name"], "Ravi")
		self.assertEqual(agent_page.rename(self.KEY, "", space=PRIVATE)["name"], "Your assistant")
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			agent_page.edit_fact(self.KEY, "x", "y", space=SHARED)
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			agent_page.get(self.KEY, space=PRIVATE)


class RecordingGoogle:
	"""Stands in for Google: records what would have been sent."""

	def __init__(self):
		self.calls = []

	def _note(self, what, **kw):
		self.calls.append((what, kw))
		return {"id": f"{what}-{len(self.calls)}", "thread_id": kw.get("thread_id") or "th-new", "event_id": f"ev-{len(self.calls)}", "title": kw.get("title", ""), "start": kw.get("start"), "end": None}

	def send(self, to, subject, body, thread_id=None, cc=None):
		return self._note("send", to=to, subject=subject, body=body, thread_id=thread_id)

	def draft(self, to, subject, body, thread_id=None, cc=None):
		return self._note("draft", to=to, subject=subject, thread_id=thread_id)

	def delete_draft(self, draft_id):
		self._note("delete_draft", id=draft_id)

	def archive(self, thread_id):
		self._note("archive", thread_id=thread_id)

	def unarchive(self, thread_id):
		self._note("unarchive", thread_id=thread_id)

	def label(self, thread_id, name):
		self._note("label", thread_id=thread_id, name=name)
		return "Label_9"

	def unlabel(self, thread_id, label_id):
		self._note("unlabel", thread_id=thread_id)

	def list_events(self, time_min, time_max, limit=50):
		return [{"event_id": "e1", "title": "Call with Meera", "start": time_min}]

	def create_event(self, title, start, end, attendees=None, description=None, location=None):
		return self._note("create_event", title=title, start=start)

	def move_event(self, event_id, start, end):
		return self._note("move_event", event_id=event_id, start=start)

	def respond(self, event_id, response, address):
		return self._note("respond", event_id=event_id, response=response)

	def delete_event(self, event_id):
		self._note("delete_event", event_id=event_id)


class TestGoogleActs(LifeTestCase):
	"""Google through Life OS (issue 86): the owner's request runs, the agent's own idea waits for the owner's OK, a switch off refuses, nothing is deleted."""
	KEY = "i86agent"
	ADDRESS = "owner86@example.com"

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		for dt in ("Life Agent Action", "Life Agent Config", "Life Mail Account", "Life Mail Search"):
			frappe.db.delete(dt, {"space": PRIVATE})
		frappe.db.delete("Life Inbox Item", {"space": PRIVATE, "source_system": "gmail"})
		frappe.get_doc({"doctype": "Life Mail Account", "space": PRIVATE, "user": OWNER, "provider": "gmail", "address": self.ADDRESS, "label": "Personal", "is_default": 1}).insert()
		self.google = RecordingGoogle()
		frappe.flags.lifeos_google = {self.ADDRESS: self.google}
		frappe.flags.lifeos_gmail = {}
		self.addCleanup(lambda: (setattr(frappe.flags, "lifeos_google", {}), setattr(frappe.flags, "lifeos_gmail", {})))
		permissions.clear_cache()
		self.as_user(OWNER)

	def mode(self, action, mode):
		frappe.set_user("Administrator")
		cfg = limits.config(PRIVATE, self.KEY, create=True)
		limits.set_ability(cfg, action, mode)
		self.as_user(OWNER)

	def act(self, tool, params, asked_by, message=None):
		return acts.request(PRIVATE, self.KEY, tool, params, asked_by, message)

	EMAIL = {"to": "meera@example.com", "subject": "Quote", "body": "Hello Meera, the quote is attached."}
	EVENT = {"title": "Lunch with Meera", "start": "2026-11-25T13:00:00", "end": "2026-11-25T14:00:00"}

	# 1
	def test_1_the_owners_request_runs_at_once_and_is_logged_with_no_approval(self):
		self.mode("change_calendar", "off")  # even a switch that is off: the owner asked
		out = self.act("calendar.create", self.EVENT, "owner", "Put lunch with Meera on Wednesday at 1")
		self.assertEqual(out["status"], "done")
		self.assertEqual([c[0] for c in self.google.calls], ["create_event"])
		row = frappe.get_doc("Life Agent Action", out["action"])
		self.assertEqual((row.status, row.asked_by, row.request), ("Done", "owner", "Put lunch with Meera on Wednesday at 1"))
		self.assertEqual(pages.requests(PRIVATE), [])  # nothing waits
		with self.assertRaises(frappe.ValidationError):  # an owner's request carries the owner's words
			self.act("calendar.create", self.EVENT, "owner")
		with self.assertRaises(frappe.ValidationError):
			self.act("calendar.create", self.EVENT, "someone")

	# 2
	def test_2_an_agents_own_idea_waits_for_the_owners_ok_and_no_discards_it(self):
		out = self.act("email.send", self.EMAIL, "agent")  # the default is "asks you"
		self.assertEqual(out["status"], "waiting")
		self.assertEqual(self.google.calls, [])
		wait = pages.requests(PRIVATE, self.KEY)
		self.assertEqual([(w["action_label"], w["title"]) for w in wait], [("Send email", "Send “Quote” to meera@example.com")])
		self.assertIn("the quote is attached", wait[0]["draft"])
		self.assertEqual(brain.needs_you(space=PRIVATE)["agent_requests"][0]["name"], out["action"])
		pages.decide(PRIVATE, out["action"], "approve", OWNER)
		self.assertEqual([c[0] for c in self.google.calls], ["send"])
		row = frappe.get_doc("Life Agent Action", out["action"])
		self.assertEqual((row.status, row.decided_by, row.asked_by), ("Done", OWNER, "agent"))
		self.assertEqual(pages.requests(PRIVATE), [])
		self.assertEqual([d["name"] for d in pages.sections(PRIVATE, self.KEY)["did"]], [out["action"]])
		with self.assertRaises(frappe.ValidationError):  # decided once
			pages.decide(PRIVATE, out["action"], "approve", OWNER)
		no = self.act("email.send", self.EMAIL, "agent")
		pages.decide(PRIVATE, no["action"], "no", OWNER)
		self.assertEqual(len(self.google.calls), 1)  # nothing more was sent
		gone = frappe.get_doc("Life Agent Action", no["action"])
		self.assertEqual((gone.status, gone.params, gone.draft), ("Declined", None, None))
		self.assertEqual(pages.requests(PRIVATE), [])

	def test_a_switch_on_its_own_runs_the_agents_idea_at_once(self):
		self.mode("send_email", "auto")
		self.assertEqual(self.act("email.send", self.EMAIL, "agent")["status"], "done")
		self.assertEqual(frappe.db.get_value("Life Agent Action", {"agent": self.KEY}, "asked_by"), "agent")

	# 3
	def test_3_with_the_switch_off_the_agents_idea_is_refused_with_the_reason(self):
		self.mode("send_email", "off")
		with self.assertRaises(frappe.PermissionError) as e:
			self.act("email.send", self.EMAIL, "agent")
		self.assertIn("Send email", str(e.exception))
		self.assertIn("off", str(e.exception))
		self.assertEqual((self.google.calls, frappe.db.count("Life Agent Action", {"space": PRIVATE})), ([], 0))
		self.assertEqual(self.act("email.send", self.EMAIL, "owner", "Send Meera the quote")["status"], "done")  # the owner may still ask

	# 4
	def test_4_read_tools_return_only_what_the_agent_may_read(self):
		tea = self.areas["Tea"]
		threads = [{"id": "t-open", "messages": [message("m1", "A <a@a.example>", "Open thread", "hello")]}, {"id": "t-tea", "messages": [message("m2", "B <b@b.example>", "Tea thread", "tea")]}]
		frappe.flags.lifeos_gmail = {self.ADDRESS: FakeGmail(threads, address=self.ADDRESS)}
		frappe.set_user("Administrator")
		inbox.create_item(title="Tea thread", source_type="Email", source_system="gmail", external_id="t-tea", space=PRIVATE, area=tea)
		cfg = limits.config(PRIVATE, self.KEY, create=True)
		self.as_user(OWNER)
		got = acts.read(PRIVATE, self.KEY, "mail.search", {"fields": {"text": "thread"}})
		self.assertEqual(sorted(h["thread_id"] for h in got["hits"]), ["t-open", "t-tea"])
		limits.set_area(cfg, tea, False)
		got = acts.read(PRIVATE, self.KEY, "mail.search", {"fields": {"text": "thread"}})
		self.assertEqual([h["thread_id"] for h in got["hits"]], ["t-open"])
		self.assertEqual(acts.read(PRIVATE, self.KEY, "mail.get_thread", {"thread_id": "t-open"})["subject"], "Open thread")
		with self.assertRaises(frappe.PermissionError):
			acts.read(PRIVATE, self.KEY, "mail.get_thread", {"thread_id": "t-tea"})
		self.assertEqual(acts.read(PRIVATE, self.KEY, "calendar.list", {})["events"][0]["title"], "Call with Meera")
		self.mode("read_email", "off")
		with self.assertRaises(frappe.PermissionError):
			acts.read(PRIVATE, self.KEY, "mail.search", {"fields": {"text": "thread"}})
		self.assertEqual(frappe.db.count("Life Mail Search", {"agent": self.KEY}), 2)  # the two searches that ran are logged with the agent's name

	def test_an_agent_reaches_the_inbox_of_the_person_it_acts_for_only(self):
		frappe.set_user("Administrator")
		frappe.get_doc({"doctype": "Life Mail Account", "space": SHARED, "user": FAMILY, "provider": "gmail", "address": "fam86@example.com", "label": "Family"}).insert()
		frappe.flags.lifeos_gmail = {self.ADDRESS: FakeGmail([{"id": "t1", "messages": [message("m1", "A <a@a.example>", "Mine", "x")]}], address=self.ADDRESS),
			"fam86@example.com": FakeGmail([{"id": "tf", "messages": [message("m2", "B <b@b.example>", "Not yours", "x")]}], address="fam86@example.com")}
		self.as_user(AGENT)
		got = mail_api.search({"text": "x"}, space=PRIVATE, source_system=self.KEY)
		self.assertEqual([h["thread_id"] for h in got["hits"]], ["t1"])
		with self.assertRaises(frappe.PermissionError):
			mail_api.search({"text": "x"}, account="fam86@example.com", space=PRIVATE, source_system=self.KEY)
		frappe.db.delete("Life Mail Account", {"address": "fam86@example.com"})

	# 5
	def test_5_there_is_no_delete_tool(self):
		names = [t["name"] for t in google.tools()]
		self.assertEqual(sorted(names), sorted(acts.TOOLS))
		for word in ("delete", "trash", "remove", "purge", "spam"):
			self.assertEqual([n for n in names if word in n], [])
		self.assertEqual(sorted(n for n in names if n.startswith("email.")), ["email.archive", "email.draft", "email.label", "email.send"])
		self.assertEqual(sorted(n for n in names if n.startswith("calendar.")), ["calendar.cancel", "calendar.create", "calendar.list", "calendar.move", "calendar.respond"])
		with self.assertRaises(frappe.ValidationError):
			self.act("email.delete", {"thread_id": "t"}, "owner", "delete it")
		whitelisted = {f.__name__ for f in frappe.whitelisted if f.__module__ in ("lifeos.api.google", "lifeos.api.mail")}
		self.assertEqual([n for n in whitelisted if "delete" in n or "trash" in n], [])

	def test_the_api_takes_the_agents_name_checks_the_owners_words_and_lists_the_tools(self):
		self.as_user(AGENT)
		out = google.act(self.KEY, "email.draft", {**self.EMAIL}, "agent", space=PRIVATE)
		self.assertEqual(out["status"], "waiting")
		with self.assertRaises(frappe.ValidationError):
			google.act(self.KEY, "email.draft", {"to": "x@example.com"}, "owner", "Draft it", space=PRIVATE)  # a subject and a body are missing
		self.assertEqual(google.act(self.KEY, "calendar.respond", {"event_id": "e1", "response": "accepted"}, "owner", "Say yes to the 3 pm", space=PRIVATE)["status"], "done")
		with self.assertRaises(frappe.ValidationError):
			google.act(self.KEY, "calendar.respond", {"event_id": "e1", "response": "maybe"}, "owner", "Say maybe", space=PRIVATE)
		self.assertEqual(google.calendar_list(source_system=self.KEY, space=PRIVATE)["events"][0]["title"], "Call with Meera")

	def test_a_did_row_names_the_record_it_changed_unless_it_failed_was_undone_or_the_record_is_gone(self):
		frappe.set_user("Administrator")
		t = frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "I129 did row"}).insert()
		made = {"task": t.name, "action": frappe.get_doc({"doctype": "Life Agent Action", "space": PRIVATE, "agent": self.KEY, "action": "add_task", "title": "Made task", "status": "Done",
			"happened_on": frappe.utils.now_datetime(), "result": json.dumps({"line": "Made task", "task": t.name})}).insert().name}
		self.as_user(OWNER)
		did = {d["name"]: d for d in pages.sections(PRIVATE, self.KEY)["did"]}
		self.assertEqual(did[made["action"]]["ref"], "task:" + made["task"])
		self.assertEqual(pages.made_ref(json.dumps({"task": made["task"]}), 1, "Done", PRIVATE), "")  # undone
		self.assertEqual(pages.made_ref(json.dumps({"task": made["task"]}), 0, "Failed", PRIVATE), "")
		self.assertEqual(pages.made_ref(json.dumps({"task": made["task"]}), 0, "Done", SHARED), "")  # another space
		self.assertEqual(pages.made_ref(json.dumps({"task": "no-such-task"}), 0, "Done", PRIVATE), "")
		self.assertEqual(pages.made_ref(None, 0, "Done", PRIVATE), "")

	def test_a_draft_a_label_and_an_archive_can_be_undone_and_a_sent_email_cannot(self):
		self.mode("send_email", "auto")
		draft = self.act("email.draft", self.EMAIL, "agent")
		archived = self.act("email.archive", {"thread_id": "t9", "subject": "Old"}, "owner", "Archive the old thread")
		labelled = self.act("email.label", {"thread_id": "t9", "label": "Done"}, "owner", "Label it Done")
		sent = self.act("email.send", self.EMAIL, "owner", "Send the quote")
		did = {d["name"]: d for d in pages.sections(PRIVATE, self.KEY)["did"]}
		self.assertEqual([did[n]["can_undo"] for n in (draft["action"], archived["action"], labelled["action"], sent["action"])], [1, 1, 1, 0])
		for n in (draft["action"], archived["action"], labelled["action"]):
			pages.undo(PRIVATE, n)
		self.assertEqual([c[0] for c in self.google.calls if c[0] in ("delete_draft", "unarchive", "unlabel")], ["delete_draft", "unarchive", "unlabel"])
		with self.assertRaises(frappe.ValidationError):
			pages.undo(PRIVATE, sent["action"])
		with self.assertRaises(frappe.ValidationError):
			pages.undo(PRIVATE, draft["action"])  # once

	def test_a_google_failure_is_logged_as_failed_without_a_token(self):
		self.google.send = lambda *a, **k: (_ for _ in ()).throw(gmail.GmailError("Google refused. Bearer ya29.SECRETSECRETSECRET"))
		out = self.act("email.send", self.EMAIL, "owner", "Send it")
		self.assertEqual(out["status"], "failed")
		row = frappe.get_doc("Life Agent Action", out["action"])
		self.assertEqual(row.status, "Failed")
		self.assertNotIn("SECRETSECRET", row.error)
		self.assertEqual(pages.sections(PRIVATE, self.KEY)["did"][0]["status"], "Failed")


class TestOneAssistant(LifeTestCase):
	"""Issue 125: what the owner asks an agent runs at once, whichever tool it uses; the agent's own idea follows its switch; one gate for both."""
	KEY = "i125agent"
	ADDRESS = "owner125@example.com"

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		for dt in ("Life Agent Action", "Life Agent Config", "Life Mail Account"):
			frappe.db.delete(dt, {"space": PRIVATE})
		frappe.db.delete("Life Person", {"space": PRIVATE})
		frappe.get_doc({"doctype": "Life Mail Account", "space": PRIVATE, "user": OWNER, "provider": "gmail", "address": self.ADDRESS, "label": "Personal", "is_default": 1}).insert()
		self.google = RecordingGoogle()
		frappe.flags.lifeos_google = {self.ADDRESS: self.google}
		self.addCleanup(lambda: setattr(frappe.flags, "lifeos_google", {}))
		self.config(display_name="Hermes")
		permissions.clear_cache()

	def config(self, **values):
		frappe.set_user("Administrator")
		cfg = limits.config(PRIVATE, self.KEY, create=True)
		cfg.update(values)
		cfg.save(ignore_permissions=True)

	def mode(self, action, mode):
		frappe.set_user("Administrator")
		limits.set_ability(limits.config(PRIVATE, self.KEY, create=True), action, mode)

	def person(self, **kw):
		from lifeos.api import tools

		self.as_user(AGENT)
		return tools.people_add("Ekta Jalan", space=PRIVATE, source_system=self.KEY, **kw)

	# 1
	def test_1_the_owners_request_through_people_add_runs_at_once_even_when_the_ability_asks(self):
		from lifeos.api import tools

		self.mode("write_pages", "ask")
		out = self.person(asked_by="owner", owner_message="Make Ekta Jalan a person")
		self.assertIn("person", out)
		row = frappe.get_doc("Life Agent Action", out["action"])
		self.assertEqual((row.status, row.asked_by, row.request, row.agent), ("Done", "owner", "Make Ekta Jalan a person", self.KEY))
		self.assertTrue(row.undo)
		self.as_user(OWNER)
		tools.undo(out["action"])
		self.assertFalse(frappe.db.exists("Life Person", out["person"]))

	# 2
	def test_2_the_owners_words_are_needed_the_agents_idea_waits_and_the_safety_switch_holds_the_owners_request(self):
		self.mode("write_pages", "ask")
		with self.assertRaises(frappe.ValidationError):
			self.person(asked_by="owner")
		with self.assertRaises(frappe.ValidationError):
			self.person(asked_by="someone")
		idea = self.person(asked_by="agent")
		self.assertIn("waiting", idea)
		self.assertFalse(frappe.db.exists("Life Person", {"space": PRIVATE, "full_name": "Ekta Jalan"}))
		self.config(owner_runs_now=0)
		held = self.person(asked_by="owner", owner_message="Make Ekta Jalan a person")
		self.assertIn("waiting", held)
		self.as_user(OWNER)
		cards = {c["name"]: c for c in pages.requests(PRIVATE)}
		self.assertEqual((cards[held["waiting"]]["asked_by"], cards[held["waiting"]]["request"], cards[held["waiting"]]["agent_name"]), ("owner", "Make Ekta Jalan a person", "Hermes"))
		self.assertEqual(cards[idea["waiting"]]["asked_by"], "agent")
		pages.decide(PRIVATE, held["waiting"], "approve", OWNER)  # approved, it runs
		self.assertTrue(frappe.db.exists("Life Person", {"space": PRIVATE, "full_name": "Ekta Jalan"}))
		self.assertEqual(frappe.db.get_value("Life Agent Action", held["waiting"], ["asked_by", "status"]), ("owner", "Done"))

	# 3
	def test_3_tasks_add_and_events_add_follow_the_owners_request_and_the_add_tasks_and_events_switch(self):
		from lifeos.api import tools

		frappe.set_user("Administrator")
		ekta = frappe.get_doc({"doctype": "Life Person", "space": PRIVATE, "full_name": "Ekta Jalan", "kind": "Person"}).insert()
		self.as_user(AGENT)
		out = tools.tasks_add("Agree a time with Ekta for 1 Dec", area="Tea", due_date="2026-11-27", person="Ekta Jalan", space=PRIVATE, source_system=self.KEY, asked_by="owner",
			owner_message="add a task 'Agree a time with Ekta for 1 Dec', due 27 Nov")
		task = frappe.get_doc("Life Task", out["task"])
		self.assertEqual((str(task.due_date), task.area), ("2026-11-27", self.areas["Tea"]))
		self.assertTrue(frappe.db.exists("Life Link", {"from_doctype": "Life Task", "from_name": task.name, "to_doctype": "Life Person", "to_name": ekta.name}))
		event = tools.events_add("Lunch with Ekta", "2026-12-01 13:00", "2026-12-01 14:00", space=PRIVATE, source_system=self.KEY, asked_by="owner", owner_message="Lunch with Ekta on 1 Dec at 1")
		self.assertTrue(frappe.db.exists("Event", event["event"]))
		self.assertEqual(limits.abilities(limits.config(PRIVATE, self.KEY))["add_planning"], "ask")  # the default
		idea = tools.tasks_add("Chase Ekta", space=PRIVATE, source_system=self.KEY)
		self.assertIn("waiting", idea)
		self.mode("add_planning", "auto")
		self.as_user(AGENT)
		self.assertIn("task", tools.tasks_add("Chase Ekta", space=PRIVATE, source_system=self.KEY))
		self.mode("add_planning", "off")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			tools.events_add("Lunch", "2026-12-02", space=PRIVATE, source_system=self.KEY)
		self.assertIn("event", tools.events_add("Lunch", "2026-12-02", space=PRIVATE, source_system=self.KEY, asked_by="owner", owner_message="Lunch on 2 Dec"))  # the owner may still ask

	# 4
	def test_4_google_act_and_the_tools_give_the_same_answer_for_the_same_asked_by_and_switch(self):
		from lifeos.api import tools

		def verdict(call):
			try:
				out = call()
			except frappe.PermissionError:
				return "refused"
			except frappe.ValidationError:
				return "invalid"
			return "waiting" if out.get("status") == "waiting" or "waiting" in out else "done"

		cases = [(who, msg, mode, runs) for who in ("owner", "agent") for msg in (None, "Do it") for mode in ("auto", "ask", "off") for runs in (1, 0)]
		for who, msg, mode, runs in cases:
			frappe.db.delete("Life Person", {"space": PRIVATE})
			self.mode("send_email", mode)
			self.mode("write_pages", mode)
			self.config(owner_runs_now=runs)
			self.as_user(AGENT)
			google_says = verdict(lambda: google.act(self.KEY, "email.archive", {"thread_id": "t1"}, who, msg, space=PRIVATE))
			tool_says = verdict(lambda: tools.people_add("Ekta Jalan", space=PRIVATE, source_system=self.KEY, asked_by=who, owner_message=msg))
			self.assertEqual(google_says, tool_says, (who, msg, mode, runs))
			expected = ("invalid" if not msg else "done" if runs else "waiting") if who == "owner" else {"auto": "done", "ask": "waiting", "off": "refused"}[mode]
			self.assertEqual(tool_says, expected, (who, msg, mode, runs))

	def test_a_waiting_google_request_reads_you_asked_when_the_owner_asked(self):
		self.config(owner_runs_now=0)
		self.as_user(AGENT)
		out = google.act(self.KEY, "email.archive", {"thread_id": "t1"}, "owner", "Archive that thread", space=PRIVATE)
		self.assertEqual(out["status"], "waiting")
		self.as_user(OWNER)
		card = [c for c in pages.requests(PRIVATE) if c["name"] == out["action"]][0]
		self.assertEqual((card["asked_by"], card["request"]), ("owner", "Archive that thread"))

	def test_the_activity_feed_lists_what_changed_with_who_asked_and_undo_for_a_tool_act(self):
		out = self.person(asked_by="owner", owner_message="Make Ekta Jalan a person")
		self.as_user(OWNER)
		got = brain.activity(space=PRIVATE)
		self.assertEqual([(r["agent_name"], r["asked_by"], r["request"], r["can_undo"]) for r in got["assistant"]], [("Hermes", "owner", "Make Ekta Jalan a person", 1)])
		self.assertEqual(got["counts"]["assistant"], 1)
		only = brain.activity(space=PRIVATE, outcome="assistant")
		self.assertEqual((only["rows"], len(only["assistant"])), ([], 1))
		self.assertEqual(brain.activity(space=PRIVATE, outcome="failed")["assistant"], [])
		agent_page.undo(out["action"], PRIVATE)
		self.assertFalse(frappe.db.exists("Life Person", out["person"]))
		self.assertEqual(brain.activity(space=PRIVATE)["assistant"][0]["undone"], 1)

	def test_the_name_goes_to_the_connector_and_a_failed_job_is_reported(self):
		self.config(display_name="Jai's assistant")
		self.assertEqual(connector.pull(PRIVATE, self.KEY)["assistant_name"], "Jai's assistant")
		connector.report(PRIVATE, self.KEY, AGENT, jobs=[{"id": "j1", "name": "Folio refresh", "schedule": "daily", "last_status": "error", "last_run": "2026-11-26 07:00", "last_error": "401 Unauthorized"},
			{"id": "j2", "name": "Digest", "schedule": "daily", "last_status": "ok"}])
		self.as_user(OWNER)
		sec = pages.sections(PRIVATE, self.KEY)
		self.assertEqual((sec["failed_job"]["title"], sec["failed_job"]["error"]), ("Folio refresh", "401 Unauthorized"))
		self.assertEqual([j["failed"] for j in sec["jobs"]], [0, 1])
		self.assertEqual(sec["name"], "Jai's assistant")


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


class TestFlow(AskCase):
	"""Issue 108: Life OS's tools and agent for Frappe Flow (try them at /flow)."""

	def ctx(self, user):
		from frappe.flow import ToolContext

		return ToolContext(session_id="t", agent="lifeos/Life OS", user=user)

	def test_1_every_flow_tool_imports_with_a_docstring_and_type_hints(self):
		from frappe.flow import Tool

		from lifeos.ai import flow
		self.assertEqual(frappe.get_hooks("flow_tools"), [f"lifeos.ai.flow.{n}" for n in flow.TOOL_NAMES])
		for path in frappe.get_hooks("flow_tools"):
			t = frappe.get_attr(path)
			self.assertIsInstance(t, Tool, path)
			self.assertTrue(t.description.strip(), path)
			hints = {k for k in t.func.__annotations__ if k != "return"}
			params = set(__import__("inspect").signature(t.func).parameters)
			self.assertEqual(hints, params, path)
			self.assertEqual(set(t.parameters["properties"]), params - {"ctx"}, path)
			self.assertFalse(t.requires_confirmation, path)  # writes show with Undo; nothing here sends or deletes

	def test_2_the_life_os_agent_is_registered_after_sync_and_lists_the_tools(self):
		from frappe.flow.lib.agent import sync_agents, sync_tools

		from lifeos.ai import flow
		frappe.set_user("Administrator")
		if not frappe.db.exists("Flow Provider", "openai"):
			frappe.get_doc({"doctype": "Flow Provider", "provider": "openai", "api_key": "sk-test-not-real"}).insert()
		model = frappe.db.get_value("Flow Model", {"enabled": 1, "embedding": 0}, "name") or frappe.get_doc(
			{"doctype": "Flow Model", "title": "t108 model", "provider": "openai", "model_id": "gpt-test"}).insert().name
		self.assertTrue(flow.agents())
		from frappe.flow.doctype.flow_skill.flow_skill import sync_skills
		sync_skills()
		sync_tools()
		sync_agents()
		agent = frappe.get_doc("Flow Agent", "lifeos/Life OS")
		self.assertTrue(frappe.db.exists("Flow Model", model))
		self.assertEqual({r.tool for r in agent.tools if r.tool.startswith("lifeos/")}, {f"lifeos/{n}" for n in flow.TOOL_NAMES})
		self.assertIn("cite every claim", agent.instructions.lower())
		self.assertEqual([r.skill for r in agent.skills], ["lifeos/ask"])

	def test_3_the_flow_skill_is_the_ask_skill(self):
		from pathlib import Path

		from lifeos.skills import store
		body = (Path(frappe.get_app_source_path("lifeos", "skills")) / "ask" / "SKILL.md").read_text().split("\n---\n", 1)[1].strip()
		self.assertEqual(body, (Path(store.DIR) / "ask.md").read_text().split("\n---\n", 1)[1].strip())

	def test_4_a_second_user_cannot_read_or_change_the_owners_space_through_a_tool(self):
		from unittest.mock import patch

		from lifeos.ai import flow

		self.make("Life Task", title="t108 owner-only secret")
		with patch("lifeos.permissions.default_space", return_value=PRIVATE):
			mine = flow.list_records(kind="tasks", ctx=self.ctx(OWNER))
			self.assertIn("t108 owner-only secret", str(mine))
			# even when the tool is handed the owner's space, a user who is not in it is refused
			for out in (flow.list_records(kind="tasks", ctx=self.ctx(FAMILY)), flow.search(query="t108 owner-only secret", ctx=self.ctx(FAMILY)),
					flow.make_task(title="t108 family writes", ctx=self.ctx(FAMILY))):
				self.assertIn("error", out)
				self.assertNotIn("t108 owner-only secret", str(out))
		self.assertFalse(frappe.db.exists("Life Task", {"title": "t108 family writes"}))
