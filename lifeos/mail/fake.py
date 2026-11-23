"""A stand-in for Gmail and Google on the acceptance site (site config lifeos_fake_gmail = 1). No test calls Google.

`gmail()` answers searches from two canned threads; `google()` records what would have been sent in the cache (last 50), so a check can assert it.
"""
import base64
import json
import re

import frappe

SENT_KEY = "lifeos_fake_google_calls"
ADDRESS = "owner@example.com"


def _b64(text):
	return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _message(id, sender, subject, text, at):
	head = [{"name": "From", "value": sender}, {"name": "To", "value": ADDRESS}, {"name": "Subject", "value": subject}, {"name": "Date", "value": "Mon, 12 May 2014 09:00:00 +0530"}]
	return {"id": id, "internalDate": str(at), "labelIds": ["INBOX"], "payload": {"headers": head, "mimeType": "text/plain", "body": {"data": _b64(text)}}}


THREADS = {
	"fake-tax-2014": {"id": "fake-tax-2014", "snippet": "Your 2014 income tax return is attached.", "messages": [_message("fake-m1", "Anil Shah <anil@ca-firm.example>",
		"Your 2014 tax return", "Your 2014 income tax return (assessment year 2014-15) is attached. Please keep it.", 1_399_900_000_000)]},
	"fake-tax-2019": {"id": "fake-tax-2019", "snippet": "Reminder: advance tax is due.", "messages": [_message("fake-m2", "Anil Shah <anil@ca-firm.example>",
		"Advance tax reminder", "Advance tax for 2019 is due on 15 March.", 1_550_000_000_000)]},
}


class FakeGmail:
	def profile(self):
		return {"emailAddress": ADDRESS}

	def list_threads(self, query, page_token=None, max_results=100):
		plain = re.sub(r"\b[a-z]+:\S+", " ", query.lower())  # the operators (in:inbox, after:2026/11/22) say where and when, not what
		words = [w for w in re.findall(r"[a-z0-9]{3,}", plain) if w not in ("find", "the")]
		found = [t for t in THREADS.values() if all(w in json.dumps(t).lower() for w in words)]
		return {"threads": [{"id": t["id"], "snippet": t["snippet"]} for t in found[:max_results]]}

	def get_thread(self, thread_id, fmt="full"):
		return THREADS[thread_id]

	def get_attachment(self, message_id, attachment_id):
		return b"fake attachment"


class FakeGoogle:
	"""Every call is recorded; nothing leaves the site."""

	def _note(self, what, **kw):
		frappe.cache.rpush(SENT_KEY, json.dumps({"call": what, **kw}, default=str))
		frappe.cache.ltrim(SENT_KEY, -50, -1)
		return {"id": f"fake-{what}-{frappe.generate_hash(length=6)}", "thread_id": kw.get("thread_id") or "fake-thread", "event_id": f"fake-event-{frappe.generate_hash(length=6)}"}

	def send(self, to, subject, body, thread_id=None, cc=None):
		return self._note("send", to=to, subject=subject, body=body, thread_id=thread_id)

	def draft(self, to, subject, body, thread_id=None, cc=None):
		return self._note("draft", to=to, subject=subject, body=body, thread_id=thread_id)

	def delete_draft(self, draft_id):
		self._note("delete_draft", id=draft_id)

	def archive(self, thread_id):
		self._note("archive", thread_id=thread_id)

	def unarchive(self, thread_id):
		self._note("unarchive", thread_id=thread_id)

	def label(self, thread_id, name):
		self._note("label", thread_id=thread_id, name=name)
		return "Label_1"

	def unlabel(self, thread_id, label_id):
		self._note("unlabel", thread_id=thread_id)

	def list_events(self, time_min, time_max, limit=50):
		return []

	def create_event(self, title, start, end, attendees=None, description=None, location=None):
		return {**self._note("create_event", title=title, start=start), "title": title, "start": start, "end": end}

	def move_event(self, event_id, start, end):
		self._note("move_event", event_id=event_id, start=start)
		return {"event_id": event_id, "start": start, "end": end, "title": ""}

	def respond(self, event_id, response, address):
		self._note("respond", event_id=event_id, response=response)
		return {"event_id": event_id, "response": response}

	def delete_event(self, event_id):
		self._note("delete_event", event_id=event_id)


def gmail():
	return FakeGmail()


def google():
	return FakeGoogle()


def calls():
	return [json.loads(x) for x in (frappe.cache.lrange(SENT_KEY, 0, -1) or [])]


def clear():
	frappe.cache.delete_value(SENT_KEY)
