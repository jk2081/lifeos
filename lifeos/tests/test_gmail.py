"""Tests for gmail."""
import base64
import json
import os
from unittest import mock

import frappe

from lifeos import mail, permissions
from lifeos.mail import digest, gmail
from lifeos.api import connections, inbox, settings
from lifeos.api import ask as ask_api
from lifeos.api import mail as mail_api
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import AskCase, item, set_key, SKILL, SkillCase, text, use


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
	"""Stands in for the Gmail client: the threads it holds, and a record of every call it gets."""

	def __init__(self, threads, files=None, address=MAILBOX):
		self.threads, self.files, self.calls, self.address = {t["id"]: t for t in threads}, files or {}, [], address
		self.query = None

	def profile(self):
		self.calls.append("profile")
		return {"emailAddress": self.address}

	def list_threads(self, query, page_token=None, max_results=100):
		self.calls.append("list_threads")
		self.query = query
		return {"threads": [{"id": i, "snippet": " ".join(gmail.text_of(t["messages"][-1]).split())[:80]} for i, t in list(self.threads.items())[:max_results]]}

	def get_thread(self, thread_id, fmt="full"):
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
		set_key("")  # no key unless a test sets one
		frappe.db.delete("Life Connection", {"space": PRIVATE})
		frappe.db.delete("Life Mail Account", {"space": PRIVATE})
		frappe.db.delete("Life Mail Search", {"space": PRIVATE})
		frappe.db.delete("Life Inbox Item", {"space": PRIVATE})
		frappe.db.delete("Life Skill Run")
		frappe.set_user("Administrator")
		self.conn = frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "label": MAILBOX, "mailbox": MAILBOX, "active": 1,
			"connected_by": OWNER}).insert()
		frappe.flags.lifeos_gmail, frappe.flags.lifeos_google = {}, {}
		self.addCleanup(lambda: setattr(frappe.flags, "lifeos_gmail", {}))
		self.addCleanup(lambda: setattr(frappe.flags, "lifeos_google", {}))

	def inbox(self, user, address, label, *threads, files=None, default=0, space=PRIVATE):
		"""An inbox of a person, with the threads a fake Gmail holds for it."""
		before = frappe.session.user
		frappe.set_user("Administrator")
		acc = frappe.get_doc({"doctype": "Life Mail Account", "space": space, "user": user, "provider": "gmail", "address": address, "label": label, "is_default": default,
			"active": 1}).insert()
		frappe.set_user(before)
		fake = FakeGmail(threads, files, address)
		frappe.flags.lifeos_gmail[address] = fake
		return acc, fake

	def items(self):
		return frappe.get_all("Life Inbox Item", filters={"space": PRIVATE, "source_system": "gmail"}, fields=["name", "external_id", "title", "status", "raw_text", "source_type", "source_url"])


class TestConnectGmail(GmailCase):
	def test_connect_asks_google_for_read_and_act_access_and_nothing_secret_is_returned(self):
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
			self.assertIn("gmail.send", out["url"])
			self.assertIn("calendar.events", out["url"])
			self.assertIn("access_type=offline", out["url"])
			self.assertNotIn("client-secret-xyz-789", json.dumps(out))
			conn = frappe.get_doc("Life Connection", out["connection"])
			self.assertEqual((conn.system, conn.active, conn.connected_by), ("gmail", 0, OWNER))
			app = frappe.get_doc("Connected App", conn.connected_app)
			self.assertEqual([r.scope for r in app.scopes], list(gmail.SCOPES))
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
		with mock.patch("lifeos.mail.gmail.configured", return_value=False):
			self.as_user(OWNER)
			with self.assertRaises(frappe.ValidationError) as e:
				connections.gmail_connect(space=PRIVATE)
		self.assertIn("Google Settings", str(e.exception))

	def test_a_mail_account_follows_its_connection_and_goes_with_it(self):
		acc = mail.account_for_connection(self.conn)
		self.assertEqual((acc.user, acc.address, acc.label, acc.active, acc.is_default, acc.connection), (OWNER, MAILBOX, MAILBOX, 1, 1, self.conn.name))
		self.assertEqual(mail.account_for_connection(self.conn).name, acc.name)  # the same account again
		self.as_user(OWNER)
		connections.save(name=self.conn.name, label="Rungamattee", active=0)
		acc.reload()
		self.assertEqual((acc.label, acc.active), ("Rungamattee", 0))
		self.assertEqual(mail.accounts_for(OWNER, PRIVATE), [])  # off: not searched
		connections.gmail_remove(self.conn.name)
		self.assertFalse(frappe.db.exists("Life Mail Account", acc.name))

	def test_two_mailboxes_are_two_cards(self):
		frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "mailbox": "second@example.com", "label": "second@example.com", "active": 1}).insert()
		cards = [c for c in connections.sources(space=PRIVATE)["connected"] if c["system"] == "gmail"]
		self.assertEqual(len(cards), 2)
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "mailbox": "second@example.com"}).insert()
		self.assertIn("gmail", [t["system"] for t in connections.sources(space=PRIVATE)["available"]])  # another can be connected


class TestSourceCards(GmailCase):
	def test_every_card_says_who_processes_it(self):
		"""The card data; the screen is checked in the acceptance walk."""
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


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def person(id, sender, subject, text, at=1_900_000_000_000, **kw):
	return thread(id, message(f"m-{id}", sender, subject, text, at=at, **kw))


class TestMailSearch(GmailCase):
	"""Live Gmail search (issue 86): one inbox or many, one query shape, the person's own inboxes only, every search logged."""

	def test_7_search_returns_subject_sender_date_snippet_and_thread_id_and_refuses_another_persons_inbox(self):
		acc, fake = self.inbox(OWNER, MAILBOX, "Personal", person("t1", "Anil <anil@ca.example>", "2014 tax return", "Your 2014 return is attached."))
		out = mail.search(OWNER, PRIVATE, {"text": "tax return"})
		hit = out["hits"][0]
		self.assertEqual((hit["thread_id"], hit["subject"], hit["inbox"]), ("t1", "2014 tax return", "Personal"))
		self.assertIn("anil@ca.example", hit["from"])
		self.assertIn("Your 2014 return", hit["snippet"])
		self.assertTrue(hit["date"])
		self.assertIn("tax return", fake.query)
		with self.assertRaises(frappe.PermissionError):  # the family member names the owner's inbox
			mail.search(FAMILY, PRIVATE, {"text": "tax"}, account=acc.name)
		with self.assertRaises(frappe.PermissionError):
			mail.search(FAMILY, PRIVATE, {"text": "tax"}, account=MAILBOX)
		with self.assertRaises(frappe.ValidationError):  # and with none of their own, there is nothing to search
			mail.search(FAMILY, PRIVATE, {"text": "tax"})
		self.assertEqual(fake.calls.count("list_threads"), 1)
		with self.assertRaises(frappe.ValidationError):
			mail.search(OWNER, PRIVATE, {})

	def test_the_tools_are_whitelisted_methods_with_the_persons_own_session(self):
		self.inbox(OWNER, MAILBOX, "Personal", person("t1", "A <a@a.example>", "Hello", "Hi"))
		self.as_user(OWNER)
		self.assertEqual(mail_api.search({"text": "hello"}, space=PRIVATE)["hits"][0]["thread_id"], "t1")
		self.assertEqual(mail_api.get_thread("t1", space=PRIVATE)["messages"][0]["text"], "Hi")
		self.assertEqual([a.label for a in mail.accounts_for(OWNER, PRIVATE)], ["Personal"])
		self.as_user(FAMILY)
		self.assertEqual(mail.accounts_for(FAMILY, SHARED), [])

	def test_8_an_attachment_is_stored_once_and_linked_to_the_asking_item(self):
		pdf = ("return.txt", b"The 2014 return: refund Rs 4,200.")
		self.inbox(OWNER, MAILBOX, "Personal", person("t1", "A <a@a.example>", "Return", "see attached", attachments=[pdf]), files={"att-return.txt": pdf[1]})
		self.as_user(OWNER)
		asking = item("Where is my 2014 return", space=PRIVATE)
		first = mail_api.get_attachment("m-t1", "att-return.txt", asking, filename="return.txt", space=PRIVATE)
		again = mail_api.get_attachment("m-t1", "att-return.txt", asking, filename="return.txt", space=PRIVATE)
		self.assertEqual(first["file"], again["file"])
		self.assertEqual(frappe.db.count("File", {"attached_to_doctype": "Life Inbox Item", "attached_to_name": asking, "file_name": "return.txt"}), 1)
		other = item("Another question", space=PRIVATE)
		linked = mail_api.get_attachment("m-t1", "att-return.txt", other, filename="return.txt", space=PRIVATE)
		self.assertEqual(frappe.db.get_value("File", linked["file"], "file_url"), frappe.db.get_value("File", first["file"], "file_url"))  # one copy on disk
		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			mail_api.get_attachment("m-t1", "att-return.txt", asking, space=SHARED)

	def test_9_every_search_writes_a_log_with_the_query_the_count_and_the_cost(self):
		self.inbox(OWNER, MAILBOX, "Personal", person("t1", "A <a@a.example>", "Tax", "x"), person("t2", "B <b@b.example>", "Tax again", "y"))
		mail.search(OWNER, PRIVATE, {"text": "tax", "from": "a@a.example"}, cost=0.0123)
		mail.search(OWNER, PRIVATE, {"text": "tax"}, max_results=1, agent="hermes")
		rows = frappe.get_all("Life Mail Search", filters={"space": PRIVATE}, fields=["user", "agent", "account_label", "query", "results", "cost"], order_by="creation asc")
		self.assertEqual(len(rows), 2)
		self.assertEqual((rows[0].user, rows[0].results, round(rows[0].cost, 4), rows[0].account_label), (OWNER, 2, 0.0123, "Personal"))
		self.assertIn("from:a@a.example", rows[0].query)
		self.assertEqual((rows[1].agent, rows[1].results), ("hermes", 1))

	def test_12_two_inboxes_are_one_merged_labelled_list_and_one_inbox_when_named(self):
		_, rung = self.inbox(OWNER, "rung@example.com", "Rungamattee", person("r1", "A <a@a.example>", "Tea order", "tea", at=1_900_000_000_000), default=1)
		_, home = self.inbox(OWNER, "home@example.com", "Personal", person("h1", "B <b@b.example>", "Tea party", "party", at=1_900_000_500_000))
		_, theirs = self.inbox(FAMILY, "family@example.com", "Family", person("f1", "C <c@c.example>", "Tea secrets", "x", at=1_900_000_900_000))
		both = mail.search(OWNER, PRIVATE, {"text": "tea"})
		self.assertEqual([(h["thread_id"], h["inbox"]) for h in both["hits"]], [("h1", "Personal"), ("r1", "Rungamattee")])  # newest first
		self.assertEqual(theirs.calls, [])  # another person's inbox is never touched
		one = mail.search(OWNER, PRIVATE, {"text": "tea"}, account="Rungamattee")
		self.assertEqual([h["thread_id"] for h in one["hits"]], ["r1"])
		self.assertEqual(home.calls.count("list_threads"), 1)  # only the first search reached it
		self.assertEqual(theirs.calls, [])
		self.assertEqual(mail.get_thread(OWNER, PRIVATE, "h1")["inbox"], "Personal")  # the thread is found in the inbox that has it
		self.assertEqual([r.label for r in mail.accounts_for(OWNER, PRIVATE)], ["Rungamattee", "Personal"])  # the default first

	def test_13_the_gmail_adapter_turns_each_plain_field_into_gmail_syntax(self):
		q = gmail.build_query
		self.assertEqual(q({"text": "tax return"}), "tax return")
		self.assertEqual(q({"from": "anil@ca.example"}), "from:anil@ca.example")
		self.assertEqual(q({"from": "Anil Shah"}), 'from:"Anil Shah"')
		self.assertEqual(q({"to": "me@example.com"}), "to:me@example.com")
		self.assertEqual(q({"subject": "tax return 2014"}), 'subject:"tax return 2014"')
		self.assertEqual(q({"has_attachment": True}), "has:attachment")
		self.assertEqual(q({"has_attachment": False}), "")
		self.assertEqual(q({"filename": "return.pdf"}), "filename:return.pdf")
		self.assertEqual(q({"after": "2014-04-05"}), "after:2014/04/05")
		self.assertEqual(q({"before": "2015-1-9"}), "before:2015/01/09")
		self.assertEqual(q({"raw": "is:starred larger:5M"}), "is:starred larger:5M")
		self.assertEqual(q({"text": "tax", "from": "anil", "has_attachment": 1, "after": "2014-04-01", "before": "2015-03-31", "raw": "in:anywhere"}),
			"tax from:anil has:attachment after:2014/04/01 before:2015/03/31 in:anywhere")
		with self.assertRaises(frappe.ValidationError):
			q({"after": "last spring"})

	def test_the_provider_interface_is_one_adapter_and_microsoft_is_not_built_yet(self):
		acc, _ = self.inbox(OWNER, MAILBOX, "Personal")
		ad = mail.adapter(acc)
		for name in ("search", "get_thread", "get_attachment", "send", "draft"):
			self.assertTrue(callable(getattr(ad, name)), name)
		frappe.db.set_value("Life Mail Account", acc.name, "provider", "microsoft")
		out = mail.search(OWNER, PRIVATE, {"text": "x"})  # the inbox that cannot be searched is named; it does not hide the others
		self.assertEqual((out["hits"], out["errors"][0]["inbox"]), ([], "Personal"))
		self.assertIn("not supported", out["errors"][0]["error"])

	def test_no_mail_is_copied_into_life_os_by_a_search(self):
		self.inbox(OWNER, MAILBOX, "Personal", person("t1", "A <a@a.example>", "Hello", "Hi"))
		before = (frappe.db.count("Life Inbox Item", {"space": PRIVATE}), frappe.db.count("Communication"))
		mail.search(OWNER, PRIVATE, {"text": "hello"})
		mail.get_thread(OWNER, PRIVATE, "t1")
		self.assertEqual((frappe.db.count("Life Inbox Item", {"space": PRIVATE}), frappe.db.count("Communication")), before)
		self.assertNotIn("lifeos.mail.gmail.fetch_all", json.dumps(frappe.get_hooks("scheduler_events")))

	def test_filing_a_thread_makes_a_brain_item_linked_to_gmail_and_filing_again_is_the_same_item(self):
		self.inbox(OWNER, MAILBOX, "Personal", person("t1", "Anil <anil@ca.example>", "2014 tax return", "Your 2014 return is attached."))
		self.as_user(OWNER)
		with mock.patch("frappe.enqueue"):
			one = mail_api.file("t1", area=self.areas["Tea"], space=PRIVATE)
			two = mail_api.file("t1", space=PRIVATE)
		self.assertEqual(one["item"], two["item"])
		doc = frappe.get_doc("Life Inbox Item", one["item"])
		self.assertEqual((doc.source_type, doc.source_system, doc.external_id, doc.area), ("Email", "gmail", "t1", self.areas["Tea"]))
		self.assertIn("mail.google.com", doc.source_url)
		self.assertIn("Your 2014 return", doc.raw_text)
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			mail_api.file("t1", space=PRIVATE)


class TestDigest(GmailCase):
	"""How email enters Life OS (issue 86): a daily digest of mail from real people, not a capture for each email."""

	def make(self, *threads, **kw):
		self.inbox(OWNER, MAILBOX, "Personal", *threads)
		return digest.make(OWNER, PRIVATE, **kw)

	def test_11_one_digest_item_lists_the_real_people_and_filing_a_line_makes_the_brain_item(self):
		name = self.make(person("t-meera", "Meera Shah <meera@shahandsons.example>", "Quote for the estate blend", "Could you send a quote by Friday?"),
			person("t-promo", "Shop <hello@shop.example>", "50% off", "Sale!", labels=("INBOX", "CATEGORY_PROMOTIONS")),
			person("t-list", "News <news@paper.example>", "Weekly", "Read on", headers={"List-Unsubscribe": "<mailto:u@paper.example>"}),
			person("t-noreply", "Service <no-reply@service.example>", "Your code", "123456"),
			person("t-mine", f"Me <{MAILBOX}>", "Note to self", "Remember", labels=("SENT",)))
		doc = frappe.get_doc("Life Inbox Item", name)
		self.assertEqual((doc.source_type, doc.source_system, doc.intent), ("Email Digest", "gmail", "Just keep"))
		self.assertIn("Quote for the estate blend", doc.raw_text)
		self.assertIn("Could you send a quote", doc.raw_text)
		self.assertIn("## Personal", doc.raw_text)
		for left_out in ("50% off", "Weekly", "Your code", "Note to self"):
			self.assertNotIn(left_out, doc.raw_text)
		self.assertIn("[File it](lifeos-file:", doc.raw_text)
		self.assertEqual([i.name for i in self.items()], [name])  # one item for the day, no capture for each email
		self.assertEqual(digest.make(OWNER, PRIVATE), name)  # the same day again is the same item
		self.assertEqual(len(self.items()), 1)
		self.as_user(OWNER)
		with mock.patch("frappe.enqueue"):
			filed = mail_api.file("t-meera", space=PRIVATE)
		self.assertEqual(len(self.items()), 2)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", filed["item"], "external_id"), "t-meera")

	def test_a_digest_groups_by_inbox_and_names_an_inbox_that_failed(self):
		self.inbox(OWNER, "rung@example.com", "Rungamattee", person("r1", "A <a@a.example>", "Estate order", "tea"))
		self.inbox(OWNER, MAILBOX, "Personal", person("h1", "B <b@b.example>", "Dinner", "tonight"))
		broken = self.inbox(OWNER, "broken@example.com", "Old", person("x", "C <c@c.example>", "x", "x"))[1]
		broken.list_threads = mock.Mock(side_effect=gmail.GmailError("Google refused access."))
		text = frappe.db.get_value("Life Inbox Item", digest.make(OWNER, PRIVATE), "raw_text")
		self.assertLess(text.index("## Rungamattee"), text.index("## Personal"))
		self.assertIn("Estate order", text)
		self.assertIn("Dinner", text)
		self.assertIn("## Old", text)
		self.assertIn("could not be read", text)

	def test_nothing_from_people_makes_no_item_and_the_weekly_one_is_its_own_item(self):
		self.assertIsNone(self.make(person("t1", "Service <no-reply@service.example>", "Code", "1")))
		self.assertEqual(self.items(), [])
		self.inbox(OWNER, "second@example.com", "Second", person("t2", "A <a@a.example>", "Hi", "hello"))
		day, week = digest.make(OWNER, PRIVATE, 1), digest.make(OWNER, PRIVATE, 7, weekly=True)
		self.assertNotEqual(day, week)
		self.assertIn("this week", frappe.db.get_value("Life Inbox Item", week, "title"))

	def test_a_person_with_no_inbox_has_no_digest_and_the_old_import_is_gone(self):
		self.assertIsNone(digest.make(FAMILY, PRIVATE))
		self.assertFalse(hasattr(gmail, "fetch_all"))
		self.assertIn("lifeos.mail.digest.run_daily", json.dumps(frappe.get_hooks("scheduler_events")))
		self.assertEqual(sorted(n for n in dir(gmail.GmailClient) if not n.startswith("_")), ["get_attachment", "get_thread", "list_threads", "profile"])



class TestAskSearchesMail(AskCase):
	"""Ask with an inbox connected (issue 86): it searches live, offers File it for what it read, and files only on the owner's click."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.delete("Life Mail Account", {"space": PRIVATE})
		frappe.db.delete("Life Mail Search", {"space": PRIVATE})
		frappe.get_doc({"doctype": "Life Mail Account", "space": PRIVATE, "user": OWNER, "provider": "gmail", "address": MAILBOX, "label": "Personal", "is_default": 1}).insert()
		self.gmail = FakeGmail([person("t-tax", "Anil <anil@ca.example>", "2014 tax return", "Your 2014 return is attached.")])
		frappe.flags.lifeos_gmail = {MAILBOX: self.gmail}
		self.addCleanup(lambda: setattr(frappe.flags, "lifeos_gmail", {}))
		frappe.set_user(OWNER)

	def test_10_ask_finds_the_thread_and_offers_file_it_and_filing_makes_a_brain_item_linked_to_gmail(self):
		backend = self.script(use("mail_search", {"text": "tax return", "after": "2014-04-01", "before": "2015-03-31"}),
			use("mail_thread", {"thread_id": "t-tax"}, id="t2"),
			{"content": [text("Anil Shah sent your 2014 tax return on 23 Nov.")], "stop_reason": "end_turn"})
		res = ask_api.ask("find the 2014 tax return", space=PRIVATE)
		offered = [t["name"] for t in backend.received[0]["tools"]]
		self.assertIn("mail_search", offered)
		self.assertIn("after:2014/04/01", self.gmail.query)
		msg = res["message"]
		self.assertEqual([(a["kind"], a["thread_id"]) for a in msg["actions"]], [("file_mail", "t-tax")])
		self.assertEqual(msg["actions"][0]["label"], "File it: 2014 tax return")
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE, "source_system": "gmail"}), 0)  # nothing is filed until the owner clicks
		log = frappe.get_all("Life Mail Search", filters={"space": PRIVATE}, fields=["user", "results", "query", "cost"])
		self.assertEqual((log[0].user, log[0].results), (OWNER, 1))
		self.assertGreater(log[0].cost, 0)  # the AI cost of the turn that searched
		with mock.patch("frappe.enqueue"):
			done = ask_api.run_action(msg["name"], 0)
		item = frappe.get_doc("Life Inbox Item", done["item"])
		self.assertEqual((item.source_system, item.external_id, item.title), ("gmail", "t-tax", "2014 tax return"))
		self.assertIn("mail.google.com", item.source_url)

	def test_without_an_inbox_ask_is_not_offered_the_mail_tools(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Life Mail Account", {"space": PRIVATE})
		frappe.set_user(OWNER)
		backend = self.script({"content": [text("Nothing here.")], "stop_reason": "end_turn"})
		ask_api.ask("find the 2014 tax return", space=PRIVATE)
		self.assertNotIn("mail_search", [t["name"] for t in backend.received[0]["tools"]])

	def test_a_family_member_asking_never_reaches_the_owners_inbox(self):
		self.as_user = lambda u: (permissions.clear_cache(), frappe.set_user(u))
		frappe.set_user("Administrator")
		frappe.db.set_value("Life Space", SHARED, "ask_enabled", 1)
		frappe.set_user(FAMILY)
		backend = self.script({"content": [text("Nothing here.")], "stop_reason": "end_turn"})
		ask_api.ask("find the 2014 tax return", space=SHARED)
		self.assertNotIn("mail_search", [t["name"] for t in backend.received[0]["tools"]])
		self.assertEqual(self.gmail.calls, [])
