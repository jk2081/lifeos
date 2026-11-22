"""Issue 58: one rule for who processes a capture, and Life OS reads Gmail itself (read only)."""
import base64
import json
from unittest import mock

import frappe
from frappe.utils import add_to_date, now_datetime

from lifeos import gmail
from lifeos.api import brain, connections, inbox, jobs
from lifeos.skills import runner, triggers
from lifeos.tests.base import AGENT, OWNER, PRIVATE
from lifeos.tests.test_issue13_task_areas import NoModel, set_key
from lifeos.tests.test_issue28_skills import SKILL, SkillCase, answer, task

MAILBOX = "owner@example.com"


def b64(text):
	return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def message(id, sender, subject, text, labels=("INBOX",), headers=None, at=1_900_000_000_000, attachments=()):
	head = [{"name": "From", "value": sender}, {"name": "To", "value": MAILBOX}, {"name": "Subject", "value": subject},
		{"name": "Date", "value": "Mon, 23 Nov 2026 09:00:00 +0530"}, *[{"name": k, "value": v} for k, v in (headers or {}).items()]]
	parts = [{"mimeType": "text/plain", "body": {"data": b64(text)}}]
	parts += [{"mimeType": "application/pdf", "filename": n, "body": {"attachmentId": f"att-{n}", "size": len(c)}} for n, c in attachments]
	return {"id": id, "internalDate": str(at), "labelIds": list(labels), "payload": {"headers": head, "mimeType": "multipart/mixed", "parts": parts}}


class FakeGmail:
	"""Stands in for the Gmail client and records every call it gets."""

	def __init__(self, threads, files=None):
		self.threads, self.files, self.calls = {t["id"]: t for t in threads}, files or {}, []

	def profile(self):
		self.calls.append("profile")
		return {"emailAddress": MAILBOX}

	def list_threads(self, query, page_token=None):
		self.calls.append("list_threads")
		self.query = query
		return {"threads": [{"id": i} for i in self.threads]}

	def get_thread(self, thread_id):
		self.calls.append("get_thread")
		return self.threads[thread_id]

	def get_attachment(self, message_id, attachment_id):
		self.calls.append("get_attachment")
		return self.files[attachment_id]


def thread(id, *messages):
	return {"id": id, "messages": list(messages)}


class GmailCase(SkillCase):
	def setUp(self):
		super().setUp()
		set_key("")  # no key unless a test sets one: the triage skill then has no answer, and mail from a person is kept
		frappe.db.delete("Life Connection", {"space": PRIVATE})
		frappe.db.delete("Life Inbox Item", {"space": PRIVATE})
		frappe.db.delete("Life Skill Run")
		frappe.set_user("Administrator")
		self.conn = frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "label": MAILBOX, "mailbox": MAILBOX, "active": 1}).insert()

	def fetch(self, *threads, files=None, **settings):
		for k, v in settings.items():
			self.conn.set(k, v)
		self.conn.save()
		client = FakeGmail(threads, files)
		with mock.patch("frappe.enqueue"):
			stats = gmail.fetch(self.conn.name, client)
		self.conn.reload()
		return stats, client

	def items(self):
		return frappe.get_all("Life Inbox Item", filters={"space": PRIVATE, "source_system": "gmail"}, fields=["name", "external_id", "title", "status", "raw_text", "source_type"])


class TestRouting(SkillCase):
	def new_run_for(self, item):
		return frappe.get_all("Life Skill Run", filters={"input_name": item}, fields=["name", "status", "trigger"])

	def test_a_capture_from_plus_capture_with_no_agent_claim_is_processed_by_the_brain(self):
		"""I58.1 (model faked)."""
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
		"""I58.2."""
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
		"""I58.3: waits for its agent first; claimed ones and young ones are left alone."""
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
		"""I58.4: never left waiting silently."""
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
		sources = {c["system"]: c for c in connections.sources(space=PRIVATE)["connected"]}
		self.assertIn("the Brain is switched off", connections.processed_by("gmail"))
		self.assertEqual(connections.processed_by("claude"), "Not processed: kept as is")
		self.assertTrue(all("Processed by" in c["processed_by"] or "Not processed" in c["processed_by"] for c in sources.values()))


class TestGmail(GmailCase):
	def test_a_run_files_one_capture_per_kept_thread_and_skips_what_is_not_a_person(self):
		"""I58.5 (Gmail client faked)."""
		person = thread("t-person", message("m1", "Meera Shah <meera@shahandsons.example>", "Quote for the estate blend", "Could you send a quote by Friday?"))
		promo = thread("t-promo", message("m2", "Shop <hello@shop.example>", "50% off", "Sale!", labels=("INBOX", "CATEGORY_PROMOTIONS")))
		updates = thread("t-upd", message("m3", "Bank <alerts@bank.example>", "Statement", "Your statement", labels=("INBOX", "CATEGORY_UPDATES")))
		listed = thread("t-list", message("m4", "News <news@paper.example>", "Weekly", "Read on", headers={"List-Unsubscribe": "<mailto:u@paper.example>"}))
		bulk = thread("t-bulk", message("m5", "Club <club@club.example>", "Notice", "Dear member", headers={"Precedence": "bulk"}))
		noreply = thread("t-noreply", message("m6", "Service <no-reply@service.example>", "Your code", "123456"))
		noreply2 = thread("t-noreply2", message("m7", "Service <donotreply@service.example>", "Receipt", "Thanks"))
		vip = thread("t-vip", message("m8", "Anil <anil@vendor.example>", "Offer", "Special", labels=("INBOX", "CATEGORY_PROMOTIONS")))
		skipped = thread("t-skip", message("m9", "Pest <sales@pest.example>", "Hello", "Hi there"))
		mine = thread("t-mine", message("m10", f"Me <{MAILBOX}>", "Note to self", "Remember", labels=("SENT",)))
		stats, client = self.fetch(person, promo, updates, listed, bulk, noreply, noreply2, vip, skipped, mine,
			always_include="vendor.example", always_skip="pest.example")
		got = {i.external_id: i for i in self.items()}
		self.assertEqual(sorted(got), ["t-person", "t-vip"])
		self.assertEqual((got["t-person"].title, got["t-person"].source_type), ("Quote for the estate blend", "Email"))
		self.assertIn("Could you send a quote", got["t-person"].raw_text)
		self.assertEqual(stats["kept"], 2)
		self.assertEqual((self.conn.seen_week, self.conn.kept_week), (10, 2))
		self.assertIn("10 this week · 2 kept", connections.sources(space=PRIVATE)["connected"][0]["line"])
		self.assertEqual(frappe.db.count("Life Skill Run", {"skill": SKILL}), 2)  # the Brain is started for each kept capture
		self.assertIn("in:inbox", client.query)

	def test_a_label_can_be_read_instead_of_the_inbox(self):
		_, client = self.fetch(thread("t1", message("m1", "A <a@a.example>", "S", "x")), label_name="Life OS")
		self.assertIn("label:Life-OS", client.query)
		self.assertNotIn("in:inbox", client.query)

	def test_the_triage_skill_decides_what_is_kept_and_a_missing_answer_keeps_it(self):
		set_key("sk-test-not-real")
		self.script({"content": [{"type": "text", "text": json.dumps({"keep": False, "reason": "Cold sales outreach"})}], "stop_reason": "end_turn"},
			{"content": [{"type": "text", "text": json.dumps({"keep": True, "reason": "A client"})}], "stop_reason": "end_turn"})
		stats, _ = self.fetch(thread("t-cold", message("m1", "Rohan <rohan@leads.example>", "10x your leads", "Hop on a call?")),
			thread("t-client", message("m2", "Meera <meera@client.example>", "Quote", "Please quote")))
		self.assertEqual(sorted(i.external_id for i in self.items()), ["t-client"])
		self.assertEqual(stats["skipped"], {"Cold sales outreach": 1})
		set_key("")  # no key: the answer is missing, so the mail is kept
		stats, _ = self.fetch(thread("t-nokey", message("m3", "Pat <pat@friend.example>", "Lunch?", "Are you free?")))
		self.assertIn("t-nokey", [i.external_id for i in self.items()])

	def test_a_reply_updates_the_same_capture_and_a_done_capture_goes_back_to_the_brain(self):
		"""I58.6."""
		first = message("m1", "Meera <meera@client.example>", "Quote", "Please send a quote.", at=1_900_000_000_000)
		self.fetch(thread("t1", first))
		item = self.items()[0]
		frappe.db.set_value("Life Inbox Item", item.name, "status", "Done")
		frappe.db.delete("Life Skill Run")
		reply = message("m2", "Meera <meera@client.example>", "Re: Quote", "Also, by Friday please.", at=1_900_000_100_000)
		self.fetch(thread("t1", first, reply))
		items = self.items()
		self.assertEqual(len(items), 1)  # the same capture, the same external_id
		self.assertEqual((items[0].name, items[0].external_id, items[0].status), (item.name, "t1", "New"))
		self.assertIn("Also, by Friday please.", items[0].raw_text)
		self.assertIn("Earlier in this thread", items[0].raw_text)
		self.assertIn("Please send a quote.", items[0].raw_text)
		self.assertEqual(len(frappe.get_all("Life Skill Run", filters={"input_name": item.name, "skill": SKILL, "status": "Queued"})), 1)
		# the same mail read again changes nothing and starts nothing
		frappe.db.delete("Life Skill Run")
		stats, _ = self.fetch(thread("t1", first, reply))
		self.assertEqual(stats["updated"], 0)
		self.assertEqual(frappe.db.count("Life Skill Run"), 0)

	def test_attachments_are_kept_up_to_10_mb_and_once(self):
		pdf = ("offer.txt", b"The offer: 200 kg at Rs 900.")
		t = thread("t1", message("m1", "A <a@a.example>", "With a file", "see attached", attachments=[pdf]))
		_, client = self.fetch(t, files={"att-offer.txt": pdf[1]})
		names = [f.file_name for f in frappe.get_all("File", filters={"attached_to_doctype": "Life Inbox Item", "attached_to_name": self.items()[0].name}, fields=["file_name"])]
		self.assertIn("offer.txt", names)
		self.assertEqual(client.calls.count("get_attachment"), 1)
		_, client = self.fetch(t, files={"att-offer.txt": pdf[1]})
		self.assertEqual(client.calls.count("get_attachment"), 0)
		big = ("big.pdf", b"x")
		t2 = thread("t2", message("m3", "B <b@b.example>", "Too big", "x", attachments=[big]))
		t2["messages"][0]["payload"]["parts"][1]["body"]["size"] = gmail.ATTACHMENT_CAP + 1
		_, client = self.fetch(t2, files={"att-big.pdf": b"x"})
		self.assertEqual(client.calls.count("get_attachment"), 0)

	def test_sensitive_senders_mark_the_capture_sensitive(self):
		self.fetch(thread("t1", message("m1", "Dr Rao <rao@clinic.example>", "Your report", "Attached")), always_sensitive="clinic.example")
		self.assertEqual(frappe.db.get_value("Life Inbox Item", self.items()[0].name, "is_sensitive"), 1)

	def test_the_fetch_never_calls_a_gmail_method_that_changes_mail(self):
		"""I58.7: only list and get are used, and the client has nothing else."""
		_, client = self.fetch(thread("t1", message("m1", "A <a@a.example>", "S", "x")))
		self.assertTrue(set(client.calls) <= {"profile", "list_threads", "get_thread", "get_attachment"}, client.calls)
		self.assertEqual(sorted(n for n in dir(gmail.GmailClient) if not n.startswith("_")),
			["get_attachment", "get_thread", "list_threads", "profile"])
		sent = []

		def reply(url, **kwargs):
			sent.append(url)
			return mock.Mock(status_code=200, json=lambda: {"threads": []} if url.endswith("/threads") else {"emailAddress": MAILBOX})

		real = gmail.GmailClient(lambda: {"Authorization": "Bearer x"})
		with mock.patch("requests.get", side_effect=reply), mock.patch("requests.post") as post, mock.patch("requests.put") as put, \
				mock.patch("requests.delete") as delete, mock.patch("requests.patch") as patch, mock.patch("requests.request") as request:
			gmail.fetch(self.conn.name, real)
		for call in (post, put, delete, patch, request):
			call.assert_not_called()
		self.assertTrue(sent and all(u.startswith(gmail.API) for u in sent), sent)
		self.assertFalse([u for u in sent if any(w in u for w in ("modify", "trash", "delete", "send", "labels", "batch", "import", "insert"))], sent)

	def test_hermes_filing_an_email_with_the_thread_id_updates_the_capture(self):
		"""I58.8: no second capture."""
		self.fetch(thread("t-9", message("m1", "Meera <meera@client.example>", "Quote", "Please send a quote.")))
		made = self.items()[0]
		self.as_user(AGENT)
		with mock.patch("frappe.enqueue"):
			done = inbox.create_item(title="Quote", source_type="Email", source_system="gmail", external_id="t-9", space=PRIVATE,
				instruction="Reply today", raw_text=made.raw_text)
		self.assertEqual((done["created"], done["updated"], done["name"]), (False, True, made.name))
		frappe.set_user("Administrator")
		self.assertEqual(len(self.items()), 1)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", made.name, "instruction"), "Reply today")

	def test_no_token_or_secret_is_written_to_logs_captures_or_errors(self):
		"""I58.10."""
		token = "ya29.A0SECRETTOKENVALUE123456"
		refresh = "1//0gREFRESHSECRETVALUE9876"
		self.assertNotIn("SECRET", gmail.scrub(f"Authorization: Bearer {token} and {refresh}"))
		import requests

		real = gmail.GmailClient(lambda: {"Authorization": f"Bearer {token}"})
		with mock.patch("requests.get", side_effect=requests.ConnectionError(f"failed with Bearer {token} {refresh}")):
			stats = gmail.fetch(self.conn.name, real)
		self.conn.reload()
		self.assertTrue(stats["error"])
		self.assertNotIn("SECRET", self.conn.last_error)

		class Breaks(FakeGmail):
			def get_thread(self, thread_id):
				raise ValueError(f"boom Bearer {token} {refresh} secret=abcdefgh12345")

		with mock.patch("frappe.enqueue"):
			gmail.fetch(self.conn.name, Breaks([thread("t-x", message("m1", "A <a@a.example>", "S", "x"))]))
		marks = ("A0SECRETTOKENVALUE123456", "0gREFRESHSECRETVALUE9876", "abcdefgh12345")
		logs = frappe.get_all("Error Log", filters={"method": ("like", "Life OS Gmail%")}, fields=["method", "error"])
		self.assertTrue(logs)  # the failure was logged, without the token
		for dt, fields in (("Error Log", ["error", "method"]), ("Life Inbox Item", ["raw_text", "title", "error"]), ("Life Connection", ["last_error"]),
				("Life Skill Run", ["error", "output"])):
			for row in frappe.get_all(dt, fields=fields, order_by="creation desc", limit=100):
				for v in row.values():
					for mark in marks:
						self.assertNotIn(mark, str(v or ""), dt)


class TestConnectGmail(GmailCase):
	def test_connect_asks_google_for_read_only_access_and_nothing_secret_is_returned(self):
		settings = frappe.get_doc("Google Settings")
		before = (settings.enable, settings.client_id, settings.get_password("client_secret", raise_exception=False))
		settings.enable, settings.client_id, settings.client_secret = 1, "client-id-123.apps.example", "client-secret-xyz-789"
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Google Settings")
		self.as_user(OWNER)
		try:
			with mock.patch("frappe.db.commit"):
				out = connections.gmail_connect(space=PRIVATE)
			self.assertTrue(out["url"].startswith(gmail.AUTHORIZATION_URI))
			self.assertIn("gmail.readonly", out["url"])
			self.assertIn("access_type=offline", out["url"])
			self.assertNotIn("client-secret-xyz-789", json.dumps(out))
			conn = frappe.get_doc("Life Connection", out["connection"])
			self.assertEqual((conn.system, conn.active, conn.connected_by), ("gmail", 0, OWNER))
			app = frappe.get_doc("Connected App", conn.connected_app)
			self.assertEqual([r.scope for r in app.scopes], [gmail.SCOPE])
			self.assertTrue(app.name.startswith(gmail.APP_PREFIX))
			card = next(c for c in connections.sources(space=PRIVATE)["connected"] if c["name"] == conn.name)
			self.assertEqual((card["pending"], card["processed_by"]), (1, "Processed by: the Brain"))
			self.assertEqual(connections.gmail_setup()["ready"], 1)
			with self.assertRaises(frappe.PermissionError):
				self.as_user(AGENT)
				connections.gmail_connect(space=PRIVATE)
		finally:
			frappe.set_user("Administrator")
			settings.enable, settings.client_id = before[0], before[1]
			settings.client_secret = before[2] or ""
			settings.save(ignore_permissions=True)
			frappe.db.delete("Token Cache", {"connected_app": ("like", f"{gmail.APP_PREFIX}%")})
			for name in frappe.get_all("Life Connection", filters={"space": PRIVATE, "system": "gmail"}, pluck="connected_app"):
				if name and frappe.db.exists("Connected App", name):
					frappe.delete_doc("Connected App", name, ignore_permissions=True, force=True)

	def test_without_google_settings_connect_says_what_to_set_up(self):
		with mock.patch("lifeos.gmail.configured", return_value=False):
			self.as_user(OWNER)
			with self.assertRaises(frappe.ValidationError) as e:
				connections.gmail_connect(space=PRIVATE)
		self.assertIn("Google Settings", str(e.exception))

	def test_two_mailboxes_are_two_cards(self):
		frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "mailbox": "second@example.com", "label": "second@example.com", "active": 1}).insert()
		cards = [c for c in connections.sources(space=PRIVATE)["connected"] if c["system"] == "gmail"]
		self.assertEqual(len(cards), 2)
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "mailbox": "second@example.com"}).insert()
		self.assertIn("gmail", [t["system"] for t in connections.sources(space=PRIVATE)["available"]])  # another can be connected


class TestSourceCards(GmailCase):
	def test_every_card_says_who_processes_it(self):
		"""I58.9 (the card data; the screen is checked in the acceptance walk)."""
		for system in ("hermes", "claude", "google-calendar"):
			frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": system, "active": 1}).insert()
		got = connections.sources(space=PRIVATE)
		by = {c["system"]: c["processed_by"] for c in got["connected"]}
		self.assertEqual(by["gmail"], "Processed by: the Brain")
		self.assertEqual(by["hermes"], "Processed by: Hermes")
		self.assertEqual(by["claude"], "Not processed: kept as is")
		self.assertEqual(by["google-calendar"], "Not processed: kept as is")
		self.assertEqual(got["available"][0]["processed_by"], "Processed by: the Brain")  # Upload
		for c in got["connected"]:
			self.assertTrue(c["lands"])
