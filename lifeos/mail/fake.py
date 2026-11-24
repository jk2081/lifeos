"""A stand-in for Gmail and Google on the acceptance site (site config lifeos_fake_gmail = 1). No test calls Google.

`gmail()` answers searches from two canned threads; `google()` records what would have been sent in the cache (last 50), so a check can assert it.
"""
import base64
import json
import re
import time

import frappe

SENT_KEY = "lifeos_fake_google_calls"
ADDRESS = "owner@example.com"


def _b64(text):
	return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _message(id, sender, subject, text, at, attachments=()):
	head = [{"name": "From", "value": sender}, {"name": "To", "value": ADDRESS}, {"name": "Subject", "value": subject}, {"name": "Date", "value": "Mon, 12 May 2014 09:00:00 +0530"}]
	if attachments:
		parts = [{"mimeType": "text/plain", "body": {"data": _b64(text)}}, *[{"mimeType": "application/pdf", "filename": n, "body": {"attachmentId": f"att-{n}", "size": 15}} for n in attachments]]
		return {"id": id, "internalDate": str(at), "labelIds": ["INBOX"], "payload": {"headers": head, "mimeType": "multipart/mixed", "parts": parts}}
	return {"id": id, "internalDate": str(at), "labelIds": ["INBOX"], "payload": {"headers": head, "mimeType": "text/plain", "body": {"data": _b64(text)}}}


THREADS = {
	"fake-tax-2014": {"id": "fake-tax-2014", "snippet": "Your 2014 income tax return is attached.", "messages": [_message("fake-m1", "Anil Shah <anil@ca-firm.example>",
		"Your 2014 tax return", "Your 2014 income tax return (assessment year 2014-15) is attached. Please keep it.", 1_399_900_000_000)]},
	"fake-tax-2019": {"id": "fake-tax-2019", "snippet": "Reminder: advance tax is due.", "messages": [_message("fake-m2", "Anil Shah <anil@ca-firm.example>",
		"Advance tax reminder", "Advance tax for 2019 is due on 15 March.", 1_550_000_000_000)]},
}


# issue 107: a busy fortnight (7 threads a day, 1 to 14 November 2026) that a search with `after:` and `before:` pages through, and one thread with an attachment
BULK_DAYS, BULK_PER_DAY = 14, 7
BLUEPRINT = {"id": "fake-blueprint", "snippet": "The SAP B1 Blueprint for Ambaji Food Products is attached.", "messages": [_message("fake-m3", "Anirudh Poddar <anirudh@sap-partner.example>",
	"SAP B1 Blueprint for Ambaji Food Products", "Hello, the SAP B1 Blueprint for Ambaji Food Products is attached.", 1_769_000_000_000, attachments=("SAP B1 Blueprint.pdf",))]}
MS_PER_HOUR = 3_600_000
DAY0_MS = 1_793_491_200_000  # 2026-11-01 00:00 UTC


def _bulk():
	out = {}
	for d in range(BULK_DAYS):
		for k in range(BULK_PER_DAY):
			at = DAY0_MS + d * 24 * MS_PER_HOUR + (3 + k) * MS_PER_HOUR
			i = f"fake-bulk-{d + 1:02d}-{k + 1}"
			out[i] = {"id": i, "snippet": f"Note {k + 1} of day {d + 1}", "messages": [_message(f"{i}-m", f"Person {k + 1} <p{k + 1}@bulk.example>", f"Bulk {d + 1:02d}.{k + 1}", f"Message {k + 1} on day {d + 1}.", at)]}
	return out


def _day_ms(text):
	"""The start of a day written 2026/11/05 in a Gmail query, in epoch ms."""
	from datetime import datetime, timezone

	y, m, d = (int(x) for x in text.split("/"))
	return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


class FakeGmail:
	def profile(self):
		return {"emailAddress": ADDRESS}

	def list_threads(self, query, page_token=None, max_results=100):
		bounds = re.search(r"\bafter:(\d{4}/\d+/\d+) before:(\d{4}/\d+/\d+)", query)
		if bounds:  # a date range: every thread inside it, newest first, a page at a time (and a moment each, as a real inbox takes, so a check can see the page it is on)
			time.sleep(0.5)
			lo, hi = _day_ms(bounds.group(1)), _day_ms(bounds.group(2))
			found = sorted((t for t in _bulk().values() if lo <= int(t["messages"][-1]["internalDate"]) < hi), key=lambda t: -int(t["messages"][-1]["internalDate"]))
			start = int(page_token or 0)
			page = found[start:start + max_results]
			return {"threads": [{"id": t["id"], "snippet": t["snippet"]} for t in page], "resultSizeEstimate": len(found),
				**({"nextPageToken": str(start + max_results)} if start + max_results < len(found) else {})}
		plain = re.sub(r"\b[a-z]+:\S+", " ", query.lower())  # the operators (in:inbox, after:2026/11/22) say where and when, not what
		words = [w for w in re.findall(r"[a-z0-9]{3,}", plain) if w not in ("find", "the")]
		found = [t for t in [*THREADS.values(), *([BLUEPRINT] if "blueprint" in plain else [])] if all(w in json.dumps(t).lower() for w in words)]
		return {"threads": [{"id": t["id"], "snippet": t["snippet"]} for t in found[:max_results]]}

	def get_thread(self, thread_id, fmt="full"):
		return THREADS.get(thread_id) or (BLUEPRINT if thread_id == BLUEPRINT["id"] else _bulk()[thread_id])

	def get_attachment(self, message_id, attachment_id):
		if attachment_id.lower().endswith(".pdf"):  # Frappe reads a PDF it is given: this one is a real, blank page
			from lifeos.tools.devtools import pdf_bytes

			return pdf_bytes()
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


MS_ADDRESS = "owner@outlook.example"
MS_MESSAGES = {
	"fake-ms-conv-1": [{"id": "fake-ms-1", "conversationId": "fake-ms-conv-1", "subject": "Your 2016 tax return", "from": {"emailAddress": {"name": "Rekha Iyer", "address": "rekha@ca-firm.example"}},
		"toRecipients": [{"emailAddress": {"address": MS_ADDRESS}}], "receivedDateTime": "2016-07-20T09:00:00Z", "bodyPreview": "Your 2016 return is attached.",
		"body": {"contentType": "text", "content": "Your 2016 return is attached. Please keep it."}, "webLink": "https://outlook.office.com/mail/fake-ms-1", "categories": [],
		"attachments": []}],
}


class FakeGraph:
	"""Microsoft Graph on the acceptance site (site config lifeos_fake_microsoft = 1): one canned conversation, found by any word in it."""

	def profile(self):
		return {"mail": MS_ADDRESS}

	def search_messages(self, search, top=10):
		plain = re.sub(r"\b[a-z]+[:<>=]+\S+", " ", search.lower())
		words = [w for w in re.findall(r"[a-z0-9]{3,}", plain) if w not in ("find", "the")]
		return {"value": [m for ms in MS_MESSAGES.values() for m in ms if all(w in json.dumps(m).lower() for w in words)][:top]}

	def conversation(self, conversation_id):
		return {"value": MS_MESSAGES.get(conversation_id, [])}

	def inbox_since(self, since, category="", top=100):
		return {"value": []}

	def get_attachment(self, message_id, attachment_id):
		return b"fake attachment"


def gmail():
	return FakeGmail()


def graph():
	return FakeGraph()


def google():
	return FakeGoogle()


def calls():
	return [json.loads(x) for x in (frappe.cache.lrange(SENT_KEY, 0, -1) or [])]


def clear():
	frappe.cache.delete_value(SENT_KEY)
