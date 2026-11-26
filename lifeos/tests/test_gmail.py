"""Tests for gmail."""
import base64
import json
import os
from unittest import mock

import frappe

from frappe.utils import add_to_date, now_datetime

from lifeos import mail, permissions
from lifeos.agents import acts, limits
from lifeos.brain import agent_page as pages_agent
from lifeos.ai import fake
from lifeos.mail import digest, gmail, microsoft
from lifeos.api import connections, inbox, settings
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
			card = next(c for c in connections.sources(space=PRIVATE)["sources"] if c["name"] == conn.name)
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
		cards = [c for c in connections.sources(space=PRIVATE)["sources"] if c["system"] == "gmail"]
		self.assertEqual(len(cards), 2)
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "mailbox": "second@example.com"}).insert()
		self.assertEqual([c.get("add_another") for c in cards], [None, 1])  # another can be connected, from the last row


class TestConnectingAddresses(GmailCase):
	"""Issue 101: the return address of each mailbox, what comes back when Google refuses, what an abandoned sign-in leaves, and why a search finds no inbox."""

	def setUp(self):
		super().setUp()
		frappe.defaults.clear_default(connections.CONFIRMED_KEY, parent="__default")
		self.addCleanup(lambda: frappe.defaults.clear_default(connections.CONFIRMED_KEY, parent="__default"))

	def google_settings(self):
		settings = frappe.get_doc("Google Settings")
		before = (settings.enable, settings.client_id, settings.get_password("client_secret", raise_exception=False))
		settings.enable, settings.client_id, settings.client_secret = 1, "client-id-123.apps.example", "client-secret-xyz-789"
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Google Settings")

		def restore():
			settings.enable, settings.client_id, settings.client_secret = before[0], before[1], before[2] or ""
			settings.save(ignore_permissions=True)
			frappe.clear_cache(doctype="Google Settings")
		self.addCleanup(restore)

	def pending(self, age_minutes=0, name=None):
		"""A mailbox card still waiting for sign-in, made `age_minutes` ago, with its Connected App."""
		app = gmail.make_app(name or gmail.free_app_name())
		conn = frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "label": "Gmail", "active": 0, "connected_app": app.name,
			"connected_by": OWNER}).insert()
		frappe.db.set_value("Life Connection", conn.name, "creation", add_to_date(now_datetime(), minutes=-age_minutes), update_modified=False)
		return conn

	def test_setup_names_the_address_for_the_next_mailbox_and_a_successful_sign_in_confirms_it(self):
		self.google_settings()
		self.as_user(OWNER)
		first = connections.gmail_setup()
		self.assertEqual((first["ready"], first["confirmed"]), (1, 0))
		self.assertTrue(first["redirect_uri"].endswith(f"connected_app.callback/{gmail.free_app_name()}"))
		self.assertTrue(first["console_url"].startswith("https://console.cloud.google.com/"))
		conn = self.pending()
		with mock.patch("lifeos.mail.gmail.finish"):
			connections.gmail_finish(conn.name)
		frappe.db.set_value("Life Connection", conn.name, "mailbox", "third@example.com")  # finish is faked: the mailbox is read by the real one
		self.assertTrue(connections.redirect_confirmed(gmail.redirect_uri(conn.connected_app)))
		again = connections.gmail_setup()  # the next mailbox has the next address, which nobody has confirmed
		self.assertNotEqual(again["redirect_uri"], gmail.redirect_uri(conn.connected_app))
		self.assertEqual(again["confirmed"], 0)

	def test_google_sending_the_person_back_with_an_error_leaves_the_error_and_the_address_on_the_card(self):
		self.google_settings()
		conn = self.pending()
		path = f"/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/{conn.connected_app}"
		self.as_user(OWNER)
		with mock.patch.object(frappe, "request", frappe._dict(path=path)), mock.patch("frappe.db.commit"):
			connections.oauth_callback(error="redirect_uri_mismatch", state="x")
		self.assertEqual(frappe.local.response["location"], "/life/brain/sources")
		card = next(c for c in connections.sources(space=PRIVATE)["sources"] if c["name"] == conn.name)
		self.assertEqual((card["state"], card["pending"]), ("Waiting", 1))
		self.assertIn("does not know this return address", card["error"])
		self.assertEqual(card["redirect_uri"], gmail.redirect_uri(conn.connected_app))
		with mock.patch.object(frappe, "request", frappe._dict(path=path)), mock.patch("frappe.db.commit"):
			connections.oauth_callback(error="access_denied", error_description="The person said no", state="x")
		self.assertIn("The person said no", frappe.db.get_value("Life Connection", conn.name, "last_error"))

	def test_an_error_for_another_persons_connection_is_ignored(self):
		self.google_settings()
		conn = self.pending()
		path = f"/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/{conn.connected_app}"
		self.as_user(FAMILY)
		with mock.patch.object(frappe, "request", frappe._dict(path=path)), mock.patch("frappe.db.commit"):
			connections.oauth_callback(error="access_denied", state="x")
		self.assertFalse(frappe.db.get_value("Life Connection", conn.name, "last_error"))

	def test_a_sign_in_left_for_an_hour_is_removed_with_its_connected_app(self):
		self.google_settings()
		old, fresh = self.pending(61, "life-os-gmail-91"), self.pending(10, "life-os-gmail-92")
		bare = frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "active": 1}).insert()  # an agent's defaults, never a sign-in
		frappe.db.set_value("Life Connection", bare.name, "creation", add_to_date(now_datetime(), days=-3), update_modified=False)
		connections.clean_abandoned()
		self.assertTrue(frappe.db.exists("Life Connection", bare.name))
		self.assertFalse(frappe.db.exists("Life Connection", old.name))
		self.assertFalse(frappe.db.exists("Connected App", "life-os-gmail-91"))
		self.assertTrue(frappe.db.exists("Life Connection", fresh.name))
		self.assertTrue(frappe.db.exists("Connected App", "life-os-gmail-92"))
		self.assertTrue(frappe.db.exists("Life Connection", self.conn.name))  # a connected mailbox is never cleaned

	def test_a_pending_card_is_waiting_and_its_switch_note_is_there(self):
		self.google_settings()
		conn = self.pending()
		card = next(c for c in connections.sources(space=PRIVATE)["sources"] if c["name"] == conn.name)
		self.assertEqual((card["state"], card["pending"], card["active"]), ("Waiting", 1, 0))
		self.assertEqual([c["state"] for c in connections.sources(space=PRIVATE)["sources"] if c["system"] == "gmail"], ["On", "Waiting"])
		self.assertEqual(len([c for c in connections.sources(space=PRIVATE)["sources"] if c["system"] == "gmail" and c.get("add_another")]), 0)  # not until all are connected

	def test_a_search_says_which_case_it_is_when_there_is_no_inbox(self):
		self.as_user(OWNER)
		frappe.db.delete("Life Connection", {"space": PRIVATE})
		with self.assertRaises(frappe.ValidationError) as e:
			mail_api.search(fields={"text": "invoice"}, space=PRIVATE)
		self.assertIn("No inbox is connected. Connect Gmail in Brain › Sources.", str(e.exception))
		frappe.set_user("Administrator")
		off = frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "mailbox": MAILBOX, "active": 0, "connected_by": OWNER}).insert()
		self.as_user(OWNER)
		with self.assertRaises(frappe.ValidationError) as e:
			mail_api.search(fields={"text": "invoice"}, space=PRIVATE)
		self.assertIn("Gmail is connected but switched off. Switch it on in Brain › Sources.", str(e.exception))
		frappe.set_user("Administrator")
		frappe.delete_doc("Life Connection", off.name, force=True)
		frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "gmail", "active": 0, "connected_by": OWNER}).insert()
		self.as_user(OWNER)
		with self.assertRaises(frappe.ValidationError) as e:
			mail_api.search(fields={"text": "invoice"}, space=PRIVATE)
		self.assertIn("Gmail sign-in wasn't finished. Connect again in Brain › Sources.", str(e.exception))


class TestSourceCards(GmailCase):
	def test_every_card_says_who_processes_it(self):
		"""The card data; the screen is checked in the acceptance walk."""
		for system in ("hermes", "claude", "google-calendar"):
			frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": system, "active": 1}).insert()
		got = connections.sources(space=PRIVATE)
		by = {c["system"]: c["processed_by"] for c in got["sources"]}
		self.assertEqual(by["gmail"], "Processed by: the Brain")
		self.assertEqual(by["hermes"], "Processed by: Your assistant")
		self.assertEqual(by["claude"], "Not processed: kept as is")
		self.assertEqual(by["google-calendar"], "Not processed: kept as is")
		self.assertEqual(got["capture"]["processed_by"], "Processed by: the Brain")
		for c in got["sources"]:
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

	def test_the_provider_interface_is_one_adapter_and_a_provider_without_one_is_named_not_hidden(self):
		acc, _ = self.inbox(OWNER, MAILBOX, "Personal")
		ad = mail.adapter(acc)
		for name in ("search", "get_thread", "get_attachment", "send", "draft"):
			self.assertTrue(callable(getattr(ad, name)), name)
		frappe.db.set_value("Life Mail Account", acc.name, "provider", "yahoo")
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



# ---------------------------------------------------------------- Ask's tools (issue 107)

DAY_MS = 86_400_000
NOV1 = 1_793_491_200_000  # 2026-11-01 00:00 UTC


class PagedGmail(FakeGmail):
	"""A fake inbox that answers like Gmail: only the threads inside `after:` and `before:`, newest first, a page at a time with a token."""

	def list_threads(self, query, page_token=None, max_results=100):
		import re
		from datetime import datetime, timezone

		self.calls.append("list_threads")
		self.query = query
		day = lambda t: int(datetime(*[int(x) for x in t.split("/")], tzinfo=timezone.utc).timestamp() * 1000)  # noqa: E731
		lo, hi = (day(re.search(f"{k}:(\\S+)", query).group(1)) for k in ("after", "before"))
		found = sorted((t for t in self.threads.values() if lo <= int(t["messages"][-1]["internalDate"]) < hi), key=lambda t: -int(t["messages"][-1]["internalDate"]))
		start = int(page_token or 0)
		return {"threads": [{"id": t["id"], "snippet": "x"} for t in found[start:start + max_results]], "resultSizeEstimate": len(found),
			**({"nextPageToken": str(start + max_results)} if start + max_results < len(found) else {})}


class TestAskTools(GmailCase):
	"""Ask's tools (issue 107): read a period, read the digests, save an attachment, make pages and people, save notes; each write is logged with an Undo."""
	KEY = "i107agent"
	PDF = ("blueprint.txt", b"The SAP B1 blueprint.")

	def setUp(self):
		super().setUp()
		set_key("sk-test-not-real")
		frappe.db.set_value("Life Space", PRIVATE, {"ask_enabled": 1, "ask_can_read_vault": 0})
		self.addCleanup(lambda: setattr(frappe.flags, "lifeos_ai_backend", None))
		for dt in ("Life Agent Action", "Life Agent Config"):
			frappe.db.delete(dt, {"space": PRIVATE})
		frappe.db.delete("Life Note", {"space": PRIVATE})
		frappe.db.delete("Life Person", {"space": PRIVATE})
		frappe.db.delete("File", {"file_name": "blueprint.txt"})
		self.career = frappe.db.get_value("Life Area", {"space": PRIVATE, "area_name": "Career"})
		self.tea = self.areas["Tea"]
		self.as_user(OWNER)

	def script(self, *responses):
		frappe.flags.lifeos_ai_backend = fake.ScriptedFake(responses)
		return frappe.flags.lifeos_ai_backend

	def steps(self, *steps):
		"""A model that answers each turn from the result of the tool it called the turn before."""
		def turn(step):
			def respond(params):
				last = params["messages"][-1]["content"]
				prev = json.loads(last[0]["content"]) if isinstance(last, list) and last and last[0].get("type") == "tool_result" else {}
				return step(prev)
			return respond
		return self.script(*[turn(s) for s in steps])

	def busy_inbox(self, per_day=4):
		"""60 threads over 1 to 15 November 2026 (four a day), and two outside that range."""
		threads = [person(f"d{d:02d}-{k}", f"P{k} <p{k}@x.example>", f"Day {d} mail {k}", "text", at=NOV1 + (d - 1) * DAY_MS + (3 + k) * 3_600_000) for d in range(1, 16) for k in range(per_day)]
		threads += [person("before", "A <a@x.example>", "Before", "x", at=NOV1 - 3_600_000), person("after", "A <a@x.example>", "After", "x", at=NOV1 + 15 * DAY_MS + 3_600_000)]
		fake = PagedGmail(threads, {"att-blueprint.txt": self.PDF[1]})
		frappe.flags.lifeos_gmail[MAILBOX] = fake
		frappe.set_user("Administrator")
		frappe.get_doc({"doctype": "Life Mail Account", "space": PRIVATE, "user": OWNER, "provider": "gmail", "address": MAILBOX, "label": "Personal", "is_default": 1, "active": 1}).insert()
		self.as_user(OWNER)
		return fake

	def blueprint(self):
		t = person("t-bp", "Anirudh Poddar <anirudh@sap.example>", "SAP B1 Blueprint", "The blueprint is attached.", attachments=[self.PDF])
		fake = FakeGmail([t], {"att-blueprint.txt": self.PDF[1]})
		frappe.flags.lifeos_gmail[MAILBOX] = fake
		frappe.set_user("Administrator")
		frappe.get_doc({"doctype": "Life Mail Account", "space": PRIVATE, "user": OWNER, "provider": "gmail", "address": MAILBOX, "label": "Personal", "is_default": 1, "active": 1}).insert()
		self.as_user(OWNER)

	def test_1_list_threads_returns_every_thread_of_a_period_over_three_pages_and_none_outside_it(self):
		from lifeos.tools import mail as mail_tools

		self.busy_inbox()
		got, token, pages_read = [], None, 0
		while True:
			page = mail_tools.list_threads("2026-11-01", "2026-11-15", page_token=token, space=PRIVATE)
			pages_read += 1
			got += page["threads"]
			token = page["next_page_token"]
			if pages_read == 1:
				self.assertEqual((page["pages"], len(page["threads"])), (3, 25))
			if not token:
				break
		self.assertEqual((pages_read, len(got)), (3, 60))
		self.assertEqual(len({t["thread_id"] for t in got}), 60)
		self.assertFalse({"before", "after"} & {t["thread_id"] for t in got})

	def test_2_digests_read_returns_the_stored_digests_of_a_range_and_the_days_with_none(self):
		from lifeos.tools import digests

		frappe.set_user("Administrator")
		for day in ("2026-11-10", "2026-11-12"):
			frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": f"Email, {day}", "source_type": "Email Digest", "source_system": "gmail",
				"external_id": f"digest:{OWNER}:day:{day}", "raw_text": f"Digest of {day}", "status": "New"}).insert()
		self.as_user(OWNER)
		got = digests.read("2026-11-10", "2026-11-13", space=PRIVATE)
		self.assertEqual([d["date"] for d in got["digests"]], ["2026-11-10", "2026-11-12"])
		self.assertEqual(got["missing_days"], ["2026-11-11", "2026-11-13"])
		self.assertIn("Digest of 2026-11-12", got["digests"][1]["text"])

	def test_3_save_attachment_saves_a_file_under_an_area_linked_to_its_email_and_undo_removes_it(self):
		from lifeos.tools import actions, mail as mail_tools

		self.blueprint()
		out = mail_tools.save_attachment("t-bp", "att-blueprint.txt", area="Career", part="Tea", space=PRIVATE)
		self.assertIn("Saved blueprint.txt", out["done"])
		f = frappe.get_doc("File", out["file"])
		self.assertEqual((f.attached_to_doctype, f.attached_to_name, f.is_private), ("Life Inbox Item", out["item"], 1))
		item = frappe.get_doc("Life Inbox Item", out["item"])
		self.assertEqual((item.area, item.external_id, item.source_system), (self.tea, "t-bp", "gmail"))  # the email it came from
		log = frappe.get_doc("Life Agent Action", out["action"])
		self.assertEqual((log.status, log.asked_by, log.agent), ("Done", "owner", "ask"))
		again = mail_tools.save_attachment("t-bp", "att-blueprint.txt", area="Career", part="Tea", space=PRIVATE)
		self.assertEqual(again["file"], out["file"])  # the same attachment is one file
		self.assertIsNone(again["undo"])  # the second call made nothing, so there is nothing to undo
		with self.assertRaises(frappe.ValidationError):
			actions.undo(again["action"])
		actions.undo(out["action"])
		self.assertFalse(frappe.db.exists("File", out["file"]))
		self.assertFalse(frappe.db.exists("Life Inbox Item", out["item"]))
		self.assertTrue(frappe.db.get_value("Life Agent Action", out["action"], "undone"))
		with self.assertRaises(frappe.ValidationError):
			actions.undo(out["action"])

	def test_3b_a_page_gets_the_file_and_cites_the_email_and_a_vault_type_goes_to_the_vault(self):
		from lifeos.tools import mail as mail_tools, pages

		self.blueprint()
		page = pages.create("Ambaji Food Products", "Career", part="Tea", kind="Prospect", body="Prospective client.", space=PRIVATE)
		out = mail_tools.save_attachment("t-bp", "att-blueprint.txt", page=page["page"], space=PRIVATE)
		self.assertEqual(frappe.db.get_value("File", out["file"], "attached_to_name"), page["page"])
		self.assertIn(("Life Inbox Item", out["item"]), [(s.source_doctype, s.source_name) for s in frappe.get_doc("Life Note", page["page"]).sources])
		vault = mail_tools.save_attachment("t-bp", "att-blueprint.txt", area="Career", vault_type="ID", space=PRIVATE)
		doc = frappe.get_doc("Life Vault Document", vault["vault_document"])
		self.assertEqual((doc.doc_type, doc.area), ("ID", self.career))
		self.assertEqual(frappe.db.get_value("File", vault["file"], "attached_to_doctype"), "Life Vault Document")

	def test_4_a_prospect_page_and_a_person_linked_to_it_exist_are_linked_and_are_the_owners_alone(self):
		from lifeos.tools import actions, pages, people

		page = pages.create("Ambaji Food Products", "Career", part="Tea", kind="Prospect", body="Prospective client of BTW.", space=PRIVATE)
		doc = frappe.get_doc("Life Note", page["page"])
		self.assertEqual((doc.kind, doc.collection, doc.area), ("Prospect", "Wiki", self.tea))
		self.assertIn("Prospect, Career › Tea", page["done"])
		org = frappe.get_doc("Life Person", doc.person)
		self.assertEqual((org.kind, org.wiki_page), ("Organisation", doc.name))
		made = people.add("Anirudh Poddar", email="anirudh@sap.example", company="SAP Partner Pvt Ltd", link_to=doc.name, space=PRIVATE)
		person = frappe.get_doc("Life Person", made["person"])
		self.assertEqual((person.email, frappe.db.get_value("Life Person", person.organisation, "full_name")), ("anirudh@sap.example", "SAP Partner Pvt Ltd"))
		self.assertIn("[[Anirudh Poddar]]", frappe.db.get_value("Life Note", doc.name, "content_md"))
		self.assertTrue(frappe.db.exists("Life Link", {"from_name": doc.name, "to_doctype": "Life Person", "to_name": person.name}))
		again = people.add("anirudh poddar", space=PRIVATE)  # the same person is not added twice
		self.assertEqual(again["person"], person.name)
		self.as_user(FAMILY)  # a family member who is not in the owner's space sees none of it
		self.assertFalse(frappe.has_permission("Life Note", "read", doc=doc))
		self.assertFalse(frappe.has_permission("Life Person", "read", doc=person))
		self.as_user(OWNER)
		actions.undo(made["action"])
		self.assertFalse(frappe.db.exists("Life Person", person.name))
		actions.undo(page["action"])
		self.assertFalse(frappe.db.exists("Life Note", doc.name))
		self.assertFalse(frappe.db.exists("Life Person", org.name))

	def test_pages_update_adds_links_and_undo_puts_the_text_back_and_notes_save_a_note(self):
		from lifeos.tools import actions, notes, pages

		page = pages.create("Ambaji Food Products", "Career", kind="Client", body="# Ambaji\n", space=PRIVATE)
		upd = pages.update(page["page"], add_links=["SAP B1 Blueprint"], space=PRIVATE)
		self.assertIn("[[SAP B1 Blueprint]]", frappe.db.get_value("Life Note", page["page"], "content_md"))
		actions.undo(upd["action"])
		self.assertEqual(frappe.db.get_value("Life Note", page["page"], "content_md"), "# Ambaji\n")
		note = notes.save("Email, 1 to 15 Nov", "A summary.", "Career", part="Tea", space=PRIVATE)
		self.assertEqual(frappe.db.get_value("Life Note", note["note"], ["collection", "area"]), ("My notes", self.tea))
		actions.undo(note["action"])
		self.assertFalse(frappe.db.exists("Life Note", note["note"]))
		with self.assertRaises(frappe.DoesNotExistError):
			pages.create("X", "No such area", space=PRIVATE)

	def test_5_an_agent_that_asks_first_makes_a_needs_you_item_not_a_file_and_the_owners_ok_makes_it(self):
		from lifeos.tools import actions, mail as mail_tools

		self.blueprint()
		frappe.set_user("Administrator")
		cfg = limits.config(PRIVATE, self.KEY, create=True)
		self.as_user(AGENT)
		out = mail_tools.save_attachment("t-bp", "att-blueprint.txt", area="Career", space=PRIVATE, source_system=self.KEY)
		self.assertIn("waiting", out)
		self.assertFalse(frappe.db.exists("File", {"file_name": "blueprint.txt"}))
		self.assertEqual(frappe.db.get_value("Life Agent Action", out["waiting"], ["status", "asked_by"]), ("Waiting", "agent"))
		self.as_user(OWNER)
		self.assertIn(out["waiting"], [r["name"] for r in pages_agent.requests(PRIVATE)])  # in Needs you
		done = pages_agent.decide(PRIVATE, out["waiting"], "approve", OWNER)
		self.assertEqual(done["status"], "Done")
		self.assertTrue(frappe.db.exists("File", {"file_name": "blueprint.txt"}))
		frappe.set_user("Administrator")
		limits.set_ability(cfg, "save_files", "off")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			mail_tools.save_attachment("t-bp", "att-blueprint.txt", area="Career", space=PRIVATE, source_system=self.KEY)

	def test_the_tools_are_whitelisted_methods_that_do_what_the_functions_do(self):
		from lifeos.api import tools

		self.busy_inbox()
		self.assertEqual(len(tools.mail_list_threads("2026-11-01", "2026-11-02", space=PRIVATE)["threads"]), 8)
		self.assertEqual(tools.digests_read("2026-11-01", "2026-11-02", space=PRIVATE)["missing_days"], ["2026-11-01", "2026-11-02"])
		page = tools.pages_create("Ambaji Food Products", "Career", kind="Client", body="# Ambaji", space=PRIVATE)
		tools.pages_update(page["page"], add_links='["Anirudh Poddar"]', space=PRIVATE)
		frappe.flags.lifeos_gmail[MAILBOX] = FakeGmail([person("t-bp", "Anirudh Poddar <a@sap.example>", "Blueprint", "Attached.", attachments=[self.PDF])], {"att-blueprint.txt": self.PDF[1]})
		saved = tools.mail_save_attachment("t-bp", "att-blueprint.txt", page=page["page"], space=PRIVATE)
		self.assertEqual(frappe.db.get_value("File", saved["file"], "attached_to_name"), page["page"])
		who = tools.people_add("Anirudh Poddar", email="a@sap.example", link_to=page["page"], space=PRIVATE)
		note = tools.notes_save("Summary", "Text.", "Career", space=PRIVATE)
		self.assertTrue(all(frappe.db.exists(dt, n) for dt, n in (("Life Note", page["page"]), ("Life Person", who["person"]), ("Life Note", note["note"]))))
		tools.undo(note["action"])
		self.assertFalse(frappe.db.exists("Life Note", note["note"]))

	def test_6_every_write_tool_refuses_a_person_without_the_space(self):
		from lifeos.tools import mail as mail_tools, notes, pages, people

		self.blueprint()
		self.as_user(FAMILY)
		for call in (lambda: mail_tools.save_attachment("t-bp", "att-blueprint.txt", area="Career", space=PRIVATE), lambda: pages.create("X", "Career", space=PRIVATE),
				lambda: pages.update("nothing", body="x", space=PRIVATE), lambda: people.add("X", space=PRIVATE), lambda: notes.save("X", "y", "Career", space=PRIVATE),
				lambda: mail_tools.list_threads("2026-11-01", "2026-11-02", space=PRIVATE)):
			with self.assertRaises(frappe.PermissionError):
				call()


# ---------------------------------------------------------------- Microsoft (issue 88)

MS_ADDRESS = "owner@outlook.example"


def ms_message(id, conversation, sender, subject, text, at="2026-11-23T04:00:00Z", attachments=(), headers=None, categories=()):
	name, _, address = sender.partition("|")
	return {"id": id, "conversationId": conversation, "subject": subject, "from": {"emailAddress": {"name": name, "address": address}},
		"toRecipients": [{"emailAddress": {"address": MS_ADDRESS}}], "receivedDateTime": at, "bodyPreview": text, "body": {"contentType": "text", "content": text},
		"webLink": f"https://outlook.office.com/mail/{id}", "categories": list(categories),
		"attachments": [{"id": f"att-{n}", "name": n, "size": len(c), "isInline": False} for n, c in attachments],
		"internetMessageHeaders": [{"name": k, "value": v} for k, v in (headers or {}).items()]}


class FakeGraph:
	"""Stands in for the Graph client: the messages it holds, and a record of every call it gets."""

	def __init__(self, messages, files=None, address=MS_ADDRESS):
		self.messages, self.files, self.calls, self.address, self.search = messages, files or {}, [], address, None

	def profile(self):
		self.calls.append("profile")
		return {"mail": self.address}

	def search_messages(self, search, top=10):
		self.calls.append("search_messages")
		self.search = search
		return {"value": self.messages[:top]}

	def conversation(self, conversation_id):
		self.calls.append("conversation")
		return {"value": [m for m in self.messages if m["conversationId"] == conversation_id]}

	def inbox_since(self, since, category="", top=100):
		self.calls.append("inbox_since")
		return {"value": self.messages}

	def get_attachment(self, message_id, attachment_id):
		self.calls.append("get_attachment")
		return self.files[attachment_id]


class SentMail:
	"""Stands in for what changes an inbox: records what would have been sent."""

	def __init__(self):
		self.calls = []

	def send(self, to, subject, body, thread_id=None, cc=None):
		self.calls.append(("send", to, subject, body, thread_id))
		return {"id": None, "thread_id": thread_id}

	def draft(self, to, subject, body, thread_id=None, cc=None):
		self.calls.append(("draft", to, subject, body, thread_id))
		return {"id": "d1", "thread_id": thread_id}


class MicrosoftCase(GmailCase):
	def microsoft_inbox(self, user, address, label, *messages, files=None, default=0):
		before = frappe.session.user
		frappe.set_user("Administrator")
		acc = frappe.get_doc({"doctype": "Life Mail Account", "space": PRIVATE, "user": user, "provider": "microsoft", "address": address, "label": label, "is_default": default,
			"active": 1}).insert()
		frappe.set_user(before)
		fake = FakeGraph(list(messages), files, address)
		frappe.flags.lifeos_microsoft = {**(getattr(frappe.flags, "lifeos_microsoft", None) or {}), address: fake}
		self.addCleanup(lambda: setattr(frappe.flags, "lifeos_microsoft", {}))
		return acc, fake


class TestMicrosoftInbox(MicrosoftCase):
	"""Microsoft as the second provider (issue 88): the same interface, merged with Gmail, filed and sent through the shared code."""

	def test_1_the_microsoft_adapter_turns_each_plain_field_into_graph_syntax(self):
		q = microsoft.build_query
		self.assertEqual(q({"text": "tax return"}), "tax return")
		self.assertEqual(q({"from": "anil@ca.example"}), "from:anil@ca.example")
		self.assertEqual(q({"from": "Anil Shah"}), "from:(Anil Shah)")
		self.assertEqual(q({"to": "me@example.com"}), "to:me@example.com")
		self.assertEqual(q({"subject": "tax return 2014"}), "subject:(tax return 2014)")
		self.assertEqual(q({"has_attachment": True}), "hasattachments:true")
		self.assertEqual(q({"has_attachment": False}), "")
		self.assertEqual(q({"filename": "return.pdf"}), "attachment:return.pdf")
		self.assertEqual(q({"after": "2014-04-05"}), "received>=2014-04-05")
		self.assertEqual(q({"before": "2015-1-9"}), "received<2015-01-09")
		self.assertEqual(q({"raw": "participants:anil"}), "participants:anil")
		self.assertEqual(q({"text": 'say "hi"', "from": "anil", "has_attachment": 1, "after": "2014-04-01", "before": "2015-03-31", "raw": "kind:email"}),
			"say  hi  from:anil hasattachments:true received>=2014-04-01 received<2015-03-31 kind:email")
		self.assertNotIn('"', q({"subject": 'a "quoted" word', "raw": 'x"y'}))  # nothing can end the quoted search string early
		with self.assertRaises(frappe.ValidationError):
			q({"after": "last spring"})
		acc, fake = self.microsoft_inbox(OWNER, MS_ADDRESS, "Work", ms_message("m1", "c1", "Anil|anil@ca.example", "2014 tax return", "Your 2014 return."))
		out = mail.search(OWNER, PRIVATE, {"text": "tax", "from": "anil", "has_attachment": True})
		self.assertEqual(fake.search, "tax from:anil hasattachments:true")
		self.assertEqual((out["hits"][0]["thread_id"], out["hits"][0]["inbox"], out["hits"][0]["subject"]), ("c1", "Work", "2014 tax return"))
		self.assertIn("anil@ca.example", out["hits"][0]["from"])
		self.assertEqual(out["hits"][0]["link"], "https://outlook.office.com/mail/m1")

	def test_2_one_gmail_and_one_microsoft_inbox_are_one_labelled_list_and_each_result_opens_through_its_own_adapter(self):
		_, gm = self.inbox(OWNER, MAILBOX, "Personal", person("g1", "A <a@a.example>", "Tea tasting", "tea", at=1_900_000_000_000), default=1)
		_, ms = self.microsoft_inbox(OWNER, MS_ADDRESS, "Work", ms_message("m1", "c1", "B|b@b.example", "Tea order", "order", at="2031-01-01T00:00:00Z"))
		both = mail.search(OWNER, PRIVATE, {"text": "tea"})
		self.assertEqual([(h["thread_id"], h["inbox"]) for h in both["hits"]], [("c1", "Work"), ("g1", "Personal")])  # newest first, each marked
		self.assertEqual(both["errors"], [])
		self.assertEqual(mail.get_thread(OWNER, PRIVATE, "c1")["inbox"], "Work")
		self.assertEqual(mail.get_thread(OWNER, PRIVATE, "g1")["inbox"], "Personal")
		self.assertIn("conversation", ms.calls)
		self.assertIsInstance(mail.adapter(frappe._dict(mail.accounts_for(OWNER, PRIVATE)[0])), gmail.GmailAdapter)
		self.assertIsInstance(mail.adapter(frappe._dict(mail.accounts_for(OWNER, PRIVATE)[1])), microsoft.MicrosoftAdapter)
		self.assertIn("received", frappe.get_all("Life Mail Search", filters={"space": PRIVATE}, pluck="query")[0] + "received")  # one log, in each provider's syntax
		self.assertEqual(frappe.db.count("Life Mail Search", {"space": PRIVATE}), 1)
		thread = mail.get_thread(OWNER, PRIVATE, "c1")
		self.assertEqual((thread["messages"][0]["text"], thread["subject"]), ("order", "Tea order"))

	def test_a_thread_in_one_microsoft_conversation_is_all_its_messages_oldest_first(self):
		self.microsoft_inbox(OWNER, MS_ADDRESS, "Work", ms_message("m2", "c1", "B|b@b.example", "Re: Quote", "Thanks", at="2026-11-23T05:00:00Z"),
			ms_message("m1", "c1", "A|a@a.example", "Quote", "Please quote", at="2026-11-23T04:00:00Z"), ms_message("m3", "c2", "C|c@c.example", "Other", "x"))
		thread = mail.get_thread(OWNER, PRIVATE, "c1")
		self.assertEqual([m["text"] for m in thread["messages"]], ["Please quote", "Thanks"])
		self.assertEqual(thread["subject"], "Quote")
		with self.assertRaises(microsoft.MicrosoftError):
			mail.get_thread(OWNER, PRIVATE, "nothing-here")

	def test_3_an_attachment_from_a_microsoft_inbox_is_stored_once_and_linked_to_the_asking_item(self):
		pdf = ("return.txt", b"The 2014 return: refund Rs 4,200.")
		self.microsoft_inbox(OWNER, MS_ADDRESS, "Work", ms_message("m1", "c1", "A|a@a.example", "Return", "see attached", attachments=[pdf]), files={"att-return.txt": pdf[1]})
		self.as_user(OWNER)
		thread = mail_api.get_thread("c1", space=PRIVATE)
		self.assertEqual(thread["messages"][0]["attachments"], [{"attachment_id": "att-return.txt", "filename": "return.txt", "size": len(pdf[1])}])
		asking = item("Where is my 2014 return", space=PRIVATE)
		first = mail_api.get_attachment("m1", "att-return.txt", asking, filename="return.txt", space=PRIVATE)
		again = mail_api.get_attachment("m1", "att-return.txt", asking, filename="return.txt", space=PRIVATE)
		self.assertEqual(first["file"], again["file"])
		self.assertEqual(frappe.db.count("File", {"attached_to_doctype": "Life Inbox Item", "attached_to_name": asking, "file_name": "return.txt"}), 1)
		self.assertEqual(frappe.get_doc("File", first["file"]).get_content(), pdf[1].decode())

	def test_4_a_reply_to_a_microsoft_thread_is_sent_from_that_inbox_and_waits_for_approval_when_the_agent_suggested_it(self):
		_, gm = self.inbox(OWNER, MAILBOX, "Personal", person("g1", "A <a@a.example>", "Unrelated", "x"), default=1)
		acc, _ms = self.microsoft_inbox(OWNER, MS_ADDRESS, "Work", ms_message("m1", "c1", "Meera|meera@example.com", "Quote", "Could you send a quote?"))
		out_gmail, out_ms = SentMail(), SentMail()
		frappe.flags.lifeos_google = {MAILBOX: out_gmail, MS_ADDRESS: out_ms}
		frappe.db.set_value("Life Space", PRIVATE, "owner_user", OWNER)
		reply = {"to": "meera@example.com", "subject": "Re: Quote", "body": "Quote attached.", "thread_id": "c1"}
		asked = acts.request(PRIVATE, "hermes", "email.send", reply, "owner", "Reply to Meera's quote email")
		self.assertEqual(asked["status"], "done")
		self.assertEqual((out_ms.calls[0][0], out_ms.calls[0][4], out_gmail.calls), ("send", "c1", []))  # from the Microsoft inbox, in its conversation
		self.assertEqual(asked["result"]["from"], MS_ADDRESS)
		own = acts.request(PRIVATE, "hermes", "email.send", {**reply, "body": "Second."}, "agent")
		self.assertEqual(own["status"], "waiting")  # its own idea: the owner says yes first
		self.assertEqual(len(out_ms.calls), 1)
		done = acts.decide(own["action"], True, OWNER)
		self.assertEqual(done["status"], "Done")
		self.assertEqual([c[0] for c in out_ms.calls], ["send", "send"])
		self.assertEqual(out_gmail.calls, [])

	def test_the_graph_client_replies_inside_the_conversation_and_sends_new_mail_otherwise(self):
		calls = []
		client = microsoft.GraphActs(lambda: {})
		client._call = lambda method, path, params=None, body=None, extra=None, raw=False: calls.append((method, path, body)) or (
			{"value": [{"id": "last", "receivedDateTime": "2026-11-23T05:00:00Z"}, {"id": "first", "receivedDateTime": "2026-11-23T04:00:00Z"}]} if "/me/messages" == path else {"id": "x"})
		client.send("meera@example.com, tom@example.com", "Re: Quote", "Thanks", "c1")
		self.assertEqual(calls[-1][0:2], ("POST", "/me/messages/last/reply"))
		self.assertEqual(calls[-1][2]["comment"], "Thanks")
		self.assertEqual([r["emailAddress"]["address"] for r in calls[-1][2]["message"]["toRecipients"]], ["meera@example.com", "tom@example.com"])
		client.send("meera@example.com", "Hello", "Hi")
		self.assertEqual(calls[-1][0:2], ("POST", "/me/sendMail"))
		self.assertEqual(calls[-1][2]["message"]["subject"], "Hello")
		with self.assertRaises(microsoft.MicrosoftError):
			client.create_event("x", "2026-11-25", "2026-11-25")  # Microsoft's calendar is not built

	def test_the_calendar_tools_use_a_google_inbox_and_say_so_when_there_is_none(self):
		self.microsoft_inbox(OWNER, MS_ADDRESS, "Work", ms_message("m1", "c1", "A|a@a.example", "Hi", "x"), )
		frappe.db.set_value("Life Space", PRIVATE, "owner_user", OWNER)
		frappe.flags.lifeos_google = {MS_ADDRESS: SentMail()}
		out = acts.request(PRIVATE, "hermes", "calendar.create", {"title": "Lunch", "start": "2026-11-25T13:00:00", "end": "2026-11-25T14:00:00"}, "owner", "Add lunch")
		self.assertEqual(out["status"], "failed")
		self.assertIn("Google", out["error"])

	def test_5_the_daily_digest_groups_gmail_and_microsoft_inboxes_in_one_item(self):
		self.inbox(OWNER, MAILBOX, "Personal", person("g1", "B <b@b.example>", "Dinner", "tonight"), default=1)
		self.microsoft_inbox(OWNER, MS_ADDRESS, "Work", ms_message("m1", "c1", "Meera Shah|meera@shah.example", "Quote for the estate blend", "Could you send a quote?"),
			ms_message("m2", "c2", "Shop|hello@shop.example", "News", "Sale", headers={"List-Unsubscribe": "<mailto:u@shop.example>"}),
			ms_message("m3", "c3", "Service|no-reply@service.example", "Your code", "123456"), ms_message("m4", "c4", "Me|" + MS_ADDRESS, "Note", "to self"))
		name = digest.make(OWNER, PRIVATE)
		doc = frappe.get_doc("Life Inbox Item", name)
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE, "source_type": "Email Digest"}), 1)
		self.assertLess(doc.raw_text.index("## Personal"), doc.raw_text.index("## Work"))
		self.assertIn("Dinner", doc.raw_text)
		self.assertIn("Quote for the estate blend", doc.raw_text)
		self.assertIn("Open in Outlook](https://outlook.office.com/mail/m1)", doc.raw_text)
		self.assertIn("Open in Gmail]", doc.raw_text)
		self.assertIn("lifeos-file:", doc.raw_text)
		for left_out in ("News", "Your code", "Note"):
			self.assertNotIn(left_out, doc.raw_text)
		self.assertEqual(digest.make(OWNER, PRIVATE), name)

	def test_filing_a_microsoft_thread_makes_a_brain_item_linked_to_outlook(self):
		self.microsoft_inbox(OWNER, MS_ADDRESS, "Work", ms_message("m1", "c1", "Anil|anil@ca.example", "2014 tax return", "Your 2014 return is attached."))
		self.as_user(OWNER)
		with mock.patch("frappe.enqueue"):
			one, two = mail_api.file("c1", space=PRIVATE), mail_api.file("c1", space=PRIVATE)
		self.assertEqual(one["item"], two["item"])
		doc = frappe.get_doc("Life Inbox Item", one["item"])
		self.assertEqual((doc.source_system, doc.external_id), ("microsoft", "c1"))
		self.assertIn("outlook.office.com", doc.source_url)

	def test_another_persons_microsoft_inbox_is_never_searched(self):
		_, theirs = self.microsoft_inbox(FAMILY, "family@outlook.example", "Family", ms_message("m9", "c9", "X|x@x.example", "Tea secrets", "x"))
		self.inbox(OWNER, MAILBOX, "Personal", person("g1", "A <a@a.example>", "Tea", "tea"))
		self.assertEqual([h["thread_id"] for h in mail.search(OWNER, PRIVATE, {"text": "tea"})["hits"]], ["g1"])
		self.assertEqual(theirs.calls, [])
		with self.assertRaises(frappe.PermissionError):
			mail.search(OWNER, PRIVATE, {"text": "tea"}, account="family@outlook.example")


class TestConnectMicrosoft(MicrosoftCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Token Cache", {"connected_app": ("like", f"{microsoft.APP_PREFIX}%")})
		for name in frappe.get_all("Life Connection", filters={"space": PRIVATE, "system": "microsoft"}, pluck="connected_app"):
			if name and frappe.db.exists("Connected App", name):
				frappe.delete_doc("Connected App", name, ignore_permissions=True, force=True)
		super().tearDown()

	def test_connect_asks_microsoft_for_read_and_send_access_with_a_refresh_token_and_nothing_secret_is_returned(self):
		self.as_user(OWNER)
		with mock.patch.dict(frappe.conf, {"lifeos_microsoft_client_id": "client-id-123", "lifeos_microsoft_client_secret": "client-secret-xyz-789"}), mock.patch("frappe.db.commit"):
			self.assertEqual(connections.microsoft_setup()["ready"], 1)
			out = connections.microsoft_connect(space=PRIVATE)
		self.assertTrue(out["url"].startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize"))
		for scope in ("offline_access", "Mail.Read", "Mail.Send"):
			self.assertIn(scope, out["url"])
		self.assertNotIn("client-secret-xyz-789", json.dumps(out))
		conn = frappe.get_doc("Life Connection", out["connection"])
		self.assertEqual((conn.system, conn.active, conn.connected_by), ("microsoft", 0, OWNER))
		self.assertEqual([r.scope for r in frappe.get_doc("Connected App", conn.connected_app).scopes], list(microsoft.SCOPES))
		with mock.patch.dict(frappe.conf, {"lifeos_more_sources": 1}):
			card = next(c for c in connections.sources(space=PRIVATE)["sources"] if c["name"] == conn.name)
		self.assertEqual((card["pending"], card["system"]), (1, "microsoft"))
		with self.assertRaises(frappe.PermissionError):
			self.as_user(AGENT)
			connections.microsoft_connect(space=PRIVATE)

	def test_without_the_azure_app_in_the_site_config_connect_says_what_to_set_up(self):
		self.as_user(OWNER)
		with mock.patch.dict(frappe.conf, {"lifeos_microsoft_client_id": "", "lifeos_microsoft_client_secret": ""}):
			self.assertEqual(connections.microsoft_setup()["ready"], 0)
			with self.assertRaises(frappe.ValidationError) as e:
				connections.microsoft_connect(space=PRIVATE)
		self.assertIn("MICROSOFT.md", str(e.exception))

	def test_finishing_reads_the_address_makes_the_mail_account_and_removing_takes_it_away(self):
		conn = frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "microsoft", "label": "Microsoft", "active": 0, "connected_by": OWNER}).insert()
		microsoft.finish(conn, FakeGraph([], address="Me@Outlook.example"))
		acc = frappe.get_doc("Life Mail Account", {"connection": conn.name})
		self.assertEqual((acc.provider, acc.address, acc.user, acc.active), ("microsoft", "me@outlook.example", OWNER, 1))
		second = frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "microsoft", "label": "Microsoft", "active": 0, "connected_by": OWNER}).insert()
		with self.assertRaises(microsoft.MicrosoftError):  # the same inbox twice
			microsoft.finish(second, FakeGraph([], address="me@outlook.example"))
		self.as_user(OWNER)
		connections.gmail_remove(conn.name)
		self.assertFalse(frappe.db.exists("Life Mail Account", acc.name))

	def test_sources_offers_both_providers_and_a_microsoft_card_says_who_processes_it(self):
		self.as_user(OWNER)
		self.assertNotIn("microsoft", [c["system"] for c in connections.sources(space=PRIVATE)["sources"]])  # hidden unless the site shows more sources
		with mock.patch.dict(frappe.conf, {"lifeos_more_sources": 1}):
			out = connections.sources(space=PRIVATE)
		self.assertEqual({"gmail", "microsoft"} - {t["system"] for t in out["sources"]}, set())
		self.assertEqual(next(c for c in out["sources"] if c["system"] == "microsoft")["connected"], 0)
		frappe.set_user("Administrator")
		frappe.get_doc({"doctype": "Life Connection", "space": PRIVATE, "system": "microsoft", "mailbox": MS_ADDRESS, "label": "Work", "active": 1}).insert()
		self.as_user(OWNER)
		with mock.patch.dict(frappe.conf, {"lifeos_more_sources": 1}):
			card = next(c for c in connections.sources(space=PRIVATE)["sources"] if c["system"] == "microsoft" and c.get("name"))
		self.assertEqual((card["label"], card["active"], card["mailbox"], card["processed_by"]), ("Work", 1, MS_ADDRESS, "Processed by: the Brain"))
