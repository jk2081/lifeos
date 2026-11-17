import frappe
from frappe.utils import add_to_date, now_datetime, today

from lifeos import proposals
from lifeos.api import inbox, meta, review
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


from lifeos.devtools import LocalClient, attach, load_fake_agent, pdf_bytes


class InboxCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.sql("update `tabLife Inbox Item` set status='Done' where space in %s and status in ('New', 'Processing')", ((PRIVATE, SHARED),))

	def claim(self, **item):
		created = inbox.create_item(space=PRIVATE, **item)
		self.as_user(AGENT)
		claimed = inbox.claim_next(space=PRIVATE)
		self.assertEqual(claimed["name"], created["name"])
		return claimed


class TestInboxPipeline(InboxCase):
	def test_create_and_claim(self):
		item = inbox.create_item(title="Journal photo", source_type="Journal Photo", space=PRIVATE, instruction="transcribe")
		self.assertEqual(item["status"], "New")
		attach("Life Inbox Item", item["name"], "page.txt", b"scan")
		self.as_user(AGENT)
		claimed = inbox.claim_next()
		self.assertEqual(claimed["name"], item["name"])
		self.assertEqual(claimed["status"], "Processing")
		self.assertEqual(claimed["claimed_by"], AGENT)
		self.assertEqual(claimed["files"][0]["file_name"], "page.txt")
		self.assertTrue(claimed["files"][0]["file_size"])
		self.assertIn("Tea", [a["area_name"] for a in claimed["context"]["areas"]])
		self.assertIsNone(inbox.claim_next(space=PRIVATE))

	def test_claim_takes_the_oldest_first(self):
		a = inbox.create_item(title="First", space=PRIVATE)
		b = inbox.create_item(title="Second", space=PRIVATE)
		frappe.db.set_value("Life Inbox Item", a["name"], "received_on", add_to_date(now_datetime(), minutes=-5))
		self.as_user(AGENT)
		self.assertEqual(inbox.claim_next(space=PRIVATE)["name"], a["name"])
		self.assertEqual(inbox.claim_next(space=PRIVATE)["name"], b["name"])

	def test_claim_timeout_releases_the_item(self):
		claimed = self.claim(title="Slow one")
		frappe.db.set_value("Life Inbox Item", claimed["name"], "claimed_on", add_to_date(now_datetime(), minutes=-31))
		self.assertEqual(inbox.release_stale_claims(), 1)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", claimed["name"], ["status", "claimed_by"]), ("New", None))
		again = inbox.claim_next(space=PRIVATE)
		self.assertEqual(again["name"], claimed["name"])

	def test_fresh_claim_is_not_released(self):
		claimed = self.claim(title="Quick one")
		frappe.db.set_value("Life Inbox Item", claimed["name"], "claimed_on", add_to_date(now_datetime(), minutes=-10))
		self.assertEqual(inbox.release_stale_claims(), 0)

	def test_submit_sets_to_review(self):
		claimed = self.claim(title="Voice note", source_type="Voice Note")
		out = inbox.submit_result(claimed["name"], transcript_md="call Vivek", summary_md="one to-do", proposals=[
			{"kind": "Task", "preview": "Call Vivek", "payload": {"title": "Call Vivek", "area": "Money"}, "confidence": 0.9}])
		self.assertEqual((out["status"], len(out["created"]), out["errors"]), ("To Review", 1, []))
		doc = frappe.get_doc("Life Inbox Item", claimed["name"])
		self.assertEqual((doc.transcript_md, doc.summary_md), ("call Vivek", "one to-do"))
		payload = frappe.parse_json(frappe.db.get_value("Life Proposal", out["created"][0]["name"], "payload"))
		self.assertEqual(payload["area"], self.areas["Money"])  # a title is resolved to the record

	def test_invalid_proposals_are_refused_and_valid_ones_kept(self):
		claimed = self.claim(title="Mixed bag")
		out = inbox.submit_result(claimed["name"], summary_md="s", proposals=[
			{"kind": "Task", "payload": {"title": "Good one"}, "confidence": 0.8},
			{"kind": "Task", "payload": {"title": "Sets owner", "owner": "Administrator"}},
			{"kind": "Task", "payload": {"title": "Other space", "space": SHARED}},
			{"kind": "Task", "payload": {"title": "Unknown field", "docstatus": 1}},
			{"kind": "Task", "payload": {"priority": "I"}},
			{"kind": "Task", "payload": {"title": "Bad date", "due_date": "next Friday"}},
			{"kind": "Task", "payload": {"title": "Foreign area", "area": self.shared_areas["Family"]}},
			{"kind": "Vault Document", "payload": {"title": "PAN", "number_last4": "ABCDE1234F"}},
			{"kind": "Spaceship", "payload": {}},
			{"kind": "Note", "payload": {"title": "Also good"}, "confidence": 2},
			{"kind": "Note", "payload": {"title": "Good note"}},
		])
		self.assertEqual([c["index"] for c in out["created"]], [0, 10])
		self.assertEqual([e["index"] for e in out["errors"]], [1, 2, 3, 4, 5, 6, 7, 8, 9])
		self.assertIn("owner", out["errors"][0]["error"])
		self.assertIn("space", out["errors"][1]["error"])
		self.assertIn("not allowed", out["errors"][2]["error"])
		self.assertIn("required", out["errors"][3]["error"])
		self.assertEqual(out["status"], "To Review")
		self.assertEqual(frappe.db.count("Life Proposal", {"inbox_item": claimed["name"]}), 2)

	def test_only_one_new_tag_per_item(self):
		self.as_user(OWNER)
		self.make("Life Tag", tag_name="audit")
		claimed = self.claim(title="Tags")
		out = inbox.submit_result(claimed["name"], summary_md="s", proposals=[
			{"kind": "Note", "payload": {"title": "A", "tags": ["audit", "brand new"]}},
			{"kind": "Note", "payload": {"title": "B", "tags": ["brand new"]}},
			{"kind": "Note", "payload": {"title": "C", "tags": ["second new"]}},
		])
		self.assertEqual(len(out["created"]), 2)
		self.assertIn("one new tag", out["errors"][0]["error"])

	def test_fail_and_retry(self):
		claimed = self.claim(title="Broken scan")
		out = inbox.fail_item(claimed["name"], error="Could not read the image")
		self.assertEqual(out["status"], "Failed")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", claimed["name"], "error"), "Could not read the image")
		self.assertRaises(frappe.PermissionError, inbox.retry, claimed["name"])  # the agent cannot retry
		self.as_user(OWNER)
		self.assertEqual(inbox.retry(claimed["name"])["status"], "New")
		self.assertIsNone(frappe.db.get_value("Life Inbox Item", claimed["name"], "error"))
		self.as_user(AGENT)
		self.assertEqual(inbox.claim_next(space=PRIVATE)["name"], claimed["name"])

	def test_submit_needs_a_claim(self):
		item = inbox.create_item(title="Unclaimed", space=PRIVATE)
		self.as_user(AGENT)
		self.assertRaises(frappe.ValidationError, inbox.submit_result, item["name"], summary_md="x")

	def test_outsider_cannot_use_the_inbox_of_a_space(self):
		item = inbox.create_item(title="Private thing", space=PRIVATE)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, inbox.create_item, title="x", space=PRIVATE)
		self.assertRaises(frappe.PermissionError, inbox.get, item["name"])
		self.assertRaises(frappe.PermissionError, inbox.list, space=PRIVATE)
		self.assertIsNone(inbox.claim_next())
		self.assertRaises(frappe.PermissionError, inbox.claim_next, space=PRIVATE)

	def test_files_stay_private_and_original(self):
		item = inbox.create_item(title="With file", space=PRIVATE)
		f = attach("Life Inbox Item", item["name"], "pan-card.txt", b"original bytes")
		self.assertTrue(f.is_private)
		public = frappe.get_doc({"doctype": "File", "file_name": "public.txt", "attached_to_doctype": "Life Inbox Item",
			"attached_to_name": item["name"], "is_private": 0, "content": b"x"})
		self.assertRaises(frappe.ValidationError, public.insert)
		self.as_user(FAMILY)
		self.assertFalse(frappe.get_doc("File", f.name).has_permission("read"))
		self.as_user(AGENT)
		self.assertTrue(frappe.get_doc("File", f.name).has_permission("read"))
		claimed = inbox.claim_next(space=PRIVATE)
		inbox.submit_result(claimed["name"], summary_md="done", proposals=[])
		self.assertIn(frappe.get_doc("File", f.name).get_content(), (b"original bytes", "original bytes"))

	def test_image_gets_a_preview_of_at_most_1600px(self):
		import io

		from PIL import Image

		buf = io.BytesIO()
		Image.new("RGB", (3000, 2000), "white").save(buf, format="JPEG")
		item = inbox.create_item(title="Big photo", source_type="Journal Photo", space=PRIVATE)
		attach("Life Inbox Item", item["name"], "big.jpg", buf.getvalue())
		url = frappe.db.get_value("Life Inbox Item", item["name"], "preview_image")
		self.assertTrue(url)
		preview = frappe.get_doc("File", {"file_url": url, "attached_to_name": item["name"]})
		self.assertLessEqual(max(Image.open(io.BytesIO(preview.get_content())).size), 1600)
		self.assertEqual(len(inbox.get(item["name"])["files"]), 1)  # the preview is not listed as an original

	def test_schema_lists_every_kind(self):
		schema = meta.proposal_schema()
		kinds = frappe.get_meta("Life Proposal").get_field("kind").options.split("\n")
		self.assertEqual(sorted(schema), sorted(kinds))
		for kind, s in schema.items():
			self.assertTrue(s["fields"] and s["example"], kind)
			proposals.validate(kind, s["example"], "Private") if kind in ("Event", "Important Date") else None


class TestReview(InboxCase):
	def submit(self, rows, **item):
		claimed = self.claim(title=item.pop("title", "Review me"), **item)
		out = inbox.submit_result(claimed["name"], transcript_md="t", summary_md="s", proposals=rows)
		self.assertEqual(out["errors"], [])
		self.as_user(OWNER)
		return claimed["name"], [c["name"] for c in out["created"]]

	def test_agent_cannot_decide(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "T", "area": "Tea"}}])
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, review.decide, props[0], "accept")
		self.assertRaises(frappe.PermissionError, review.decide_all, item, "accept")
		prop = frappe.get_doc("Life Proposal", props[0])
		prop.status = "Accepted"
		self.assertRaises(frappe.PermissionError, prop.save)
		self.assertEqual(frappe.db.get_value("Life Proposal", props[0], "status"), "Pending")

	def test_outsider_cannot_decide(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "T", "area": "Tea"}}])
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, review.decide, props[0], "accept")

	def test_accept_reject_and_done(self):
		item, props = self.submit([
			{"kind": "Task", "payload": {"title": "Accept me", "area": "Tea"}},
			{"kind": "Task", "payload": {"title": "Reject me", "area": "Tea"}},
		])
		out = review.decide(props[0], "accept")
		self.assertEqual((out["status"], out["created_doctype"], out["item_status"]), ("Accepted", "Life Task", "To Review"))
		task = frappe.get_doc("Life Task", out["created_name"])
		self.assertEqual((task.title, task.inbox_item, task.area, task.space), ("Accept me", item, self.areas["Tea"], PRIVATE))
		out = review.decide(props[1], "reject")
		self.assertEqual((out["status"], out["item_status"]), ("Rejected", "Done"))
		self.assertFalse(frappe.db.exists("Life Task", {"title": "Reject me", "space": PRIVATE}))
		self.assertRaises(frappe.ValidationError, review.decide, props[0], "reject")
		self.assertEqual(str(frappe.db.get_value("Life Inbox Item", item, "finished_on")), today())

	def test_edit_then_accept(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "Generic promotion [?]", "area": "Personal"}, "confidence": 0.41}])
		out = review.decide(props[0], "accept", payload={"title": "Genetic promotion plan", "area": "Tea", "also_in": ["Money"], "priority": "II"})
		task = frappe.get_doc("Life Task", out["created_name"])
		self.assertEqual((task.title, task.area, task.priority), ("Genetic promotion plan", self.areas["Tea"], "II"))
		self.assertEqual([r.area for r in task.also_in], [self.areas["Money"]])

	def test_edited_payload_is_validated(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "T", "area": "Tea"}}])
		self.assertRaises(frappe.ValidationError, review.decide, props[0], "accept", {"title": "T", "owner": "Administrator"})
		self.assertRaises(frappe.ValidationError, review.decide, props[0], "accept", {"title": "T", "area": self.shared_areas["Work"]})
		self.assertEqual(frappe.db.get_value("Life Proposal", props[0], "status"), "Pending")

	def test_area_is_required_to_file_a_task(self):
		item, props = self.submit([{"kind": "Task", "payload": {"title": "No area yet"}}])
		self.assertRaises(frappe.ValidationError, review.decide, props[0], "accept")
		review.update_payload(props[0], {"title": "No area yet", "area": "Money"})
		self.assertEqual(review.decide(props[0], "accept")["status"], "Accepted")

	def test_accept_all_keeps_what_fails(self):
		item, props = self.submit([
			{"kind": "Task", "payload": {"title": "Fine", "area": "Tea"}},
			{"kind": "Task", "payload": {"title": "Needs an area"}},
		])
		out = review.decide_all(item, "accept")
		self.assertEqual((out["decided"], len(out["errors"]), out["item_status"]), ([props[0]], 1, "To Review"))

	def test_each_kind_creates_the_right_record(self):
		self.as_user(OWNER)
		habit = self.make("Life Habit", title="Japa")
		person = self.make("Life Person", full_name="Ruchi")
		cycle = self.make("Life Cycle", title="Kinds cycle", start_date=today(), status="Active")
		goal = self.make("Life Goal", cycle=cycle.name, title="Close open loops", actions=[{"title": "Anya passport"}, {"title": "Ruchi ITR"}])
		claimed = self.claim(title="Everything", source_type="Journal Photo")
		attach("Life Inbox Item", claimed["name"], "page-187.png", b"\x89PNG fake")
		out = inbox.submit_result(claimed["name"], transcript_md="Goal Oct to Dec", summary_md="s", proposals=[
			{"kind": "Task", "payload": {"title": "Visit leased gardens", "area": "Tea", "goal": "Close open loops", "priority": "I", "tags": ["estate"]}},
			{"kind": "Event", "payload": {"subject": "Golf round", "starts_on": "2026-11-14 07:00:00"}},
			{"kind": "Important Date", "payload": {"title": "Ruchi", "day": 14, "month": 1, "kind": "Birthday", "person": "Ruchi"}},
			{"kind": "Note", "payload": {"title": "New crops by estate", "content_md": "pepper", "area": "Tea", "also_in": ["Money"]}},
			{"kind": "Vault Document", "payload": {"title": "Driving licence", "doc_type": "ID", "expiry_date": "2026-12-12", "number_last4": "4821", "area": "Personal", "holder": "Ruchi"}},
			{"kind": "Month Goal", "payload": {"title": "GHL visit", "year": 2033, "month": 2, "priority": "I", "area": "Tea"}},
			{"kind": "Habit Log", "payload": {"habit": "Japa", "date": "2026-11-13"}},
			{"kind": "Check-in", "payload": {"date": "2026-11-14", "scores": [{"dimension": "Money", "habits": "2-3", "situation": 7, "note": "PMS"}], "reflection_md": "ok"}},
			{"kind": "Week Tick", "payload": {"goal": "Close open loops", "action": "Anya passport", "mark_done": True}},
			{"kind": "Journal Page", "payload": {"page_date": "2026-11-14", "page_number": "187-188"}},
		])
		self.assertEqual(out["errors"], [])
		self.as_user(OWNER)
		done = review.decide_all(claimed["name"], "accept")
		self.assertEqual((done["errors"], done["item_status"]), ([], "Done"))
		made = {p.kind: p for p in frappe.get_all("Life Proposal", filters={"inbox_item": claimed["name"]}, fields=["kind", "created_doctype", "created_name", "status", "decided_by"])}
		self.assertTrue(all(p.status == "Accepted" and p.decided_by == OWNER for p in made.values()))

		task = frappe.get_doc("Life Task", made["Task"].created_name)
		self.assertEqual((task.goal, task.priority, task.inbox_item), (goal.name, "I", claimed["name"]))
		self.assertEqual(frappe.db.get_value("Life Tag", task.tags[0].tag, "tag_name"), "estate")
		event = frappe.get_doc("Event", made["Event"].created_name)
		self.assertEqual((event.subject, event.life_space, event.event_type), ("Golf round", PRIVATE, "Public"))
		date = frappe.get_doc("Life Important Date", made["Important Date"].created_name)
		self.assertEqual((date.day, date.month, date.person), (14, 1, person.name))
		note = frappe.get_doc("Life Note", made["Note"].created_name)
		self.assertEqual([r.area for r in note.also_in], [self.areas["Money"]])
		vault = frappe.get_doc("Life Vault Document", made["Vault Document"].created_name)
		self.assertEqual((vault.number_last4, str(vault.expiry_date), vault.holder), ("4821", "2026-12-12", person.name))
		self.assertTrue(vault.file)
		self.assertEqual(made["Month Goal"].created_doctype, "Life Month Plan")
		plan = frappe.get_doc("Life Month Plan", f"{PRIVATE}-2033-02")
		self.assertEqual([(g.title, g.priority) for g in plan.goals], [("GHL visit", "I")])
		self.assertTrue(frappe.db.exists("Life Habit Log", {"habit": habit.name, "date": "2026-11-13", "done": 1}))
		checkin = frappe.get_doc("Life Check-in", made["Check-in"].created_name)
		self.assertEqual((checkin.scores[0].habits_low, checkin.scores[0].habits_high, checkin.scores[0].situation_low), (2, 3, 7))
		goal.reload()
		action = goal.actions[0]
		self.assertEqual(action.status, "Done")
		self.assertTrue(frappe.db.exists("Life Action Log", {"action_id": action.name, "week": 1}))
		page = frappe.get_doc("Life Journal Page", made["Journal Page"].created_name)
		self.assertEqual((page.page_number, page.transcript_md, page.inbox_item), ("187-188", "Goal Oct to Dec", claimed["name"]))
		self.assertTrue(page.image)
		# the original stays on the inbox item
		self.assertEqual(len(inbox.get(claimed["name"])["files"]), 1)


class TestFakeAgent(InboxCase):
	def test_journal_photo_gives_a_transcript_and_five_proposals(self):
		fake = load_fake_agent()
		cycle = self.make("Life Cycle", title="Fake agent cycle", start_date=today(), status="Active")
		self.make("Life Goal", cycle=cycle.name, title="Close open loops", actions=[{"title": "Anya passport"}])
		self.make("Life Goal", cycle=cycle.name, title="Money", actions=[{"title": "Meet Arjun Singh for PMS"}])
		item = inbox.create_item(title="Journal photo, pages 187 to 188", source_type="Journal Photo", space=PRIVATE,
			instruction="transcribe and update my journal")
		attach("Life Inbox Item", item["name"], "journal.png", b"\x89PNG fake")
		self.as_user(AGENT)
		result = fake.process_one(LocalClient(), today=today(), log=lambda *_: None)
		self.assertEqual((result["status"], len(result["created"]), result["errors"]), ("To Review", 5, []))
		self.as_user(OWNER)
		data = inbox.get(item["name"])
		self.assertIn("Anya passport", data["transcript_md"])
		props = data["proposals"]
		self.assertEqual([p["kind"] for p in props], ["Task", "Task", "Week Tick", "Task", "Journal Page"])
		# accept three, edit one, reject one
		review.decide(props[0]["name"], "accept", {**props[0]["payload"], "area": "Money"})
		review.decide(props[2]["name"], "accept")
		review.decide(props[4]["name"], "accept")
		review.decide(props[3]["name"], "accept", {"title": "Genetic promotion", "area": "Personal"})
		out = review.decide(props[1]["name"], "reject")
		self.assertEqual(out["item_status"], "Done")
		tasks = frappe.get_all("Life Task", filters={"inbox_item": item["name"]}, pluck="title")
		self.assertEqual(sorted(tasks), ["Genetic promotion", "Meet Arjun Singh for PMS"])
		self.assertTrue(frappe.db.exists("Life Journal Page", {"inbox_item": item["name"]}))

	def test_pdf_gives_tasks_and_failure_is_reported(self):
		fake = load_fake_agent()
		item = inbox.create_item(title="Mithun production documents.pdf", space=PRIVATE, instruction="summarise and extract to-dos")
		attach("Life Inbox Item", item["name"], "Mithun production documents.pdf", pdf_bytes())
		other = inbox.create_item(title="Will fail", space=PRIVATE)
		frappe.db.set_value("Life Inbox Item", other["name"], "received_on", add_to_date(now_datetime(), minutes=5))
		self.as_user(AGENT)
		result = fake.process_one(LocalClient(), log=lambda *_: None)
		self.assertEqual([c["kind"] for c in result["created"]], ["Task", "Task", "Task"])
		failed = fake.process_one(LocalClient(), fail=True, log=lambda *_: None)
		self.assertEqual(failed["status"], "Failed")
		self.assertIsNone(fake.process_one(LocalClient(), log=lambda *_: None))
