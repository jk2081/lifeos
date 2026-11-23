"""What changes in a person's Google account (issue 86): send and draft mail, archive and label a thread, and the calendar.

Reached only through `lifeos.agents.acts`, which decides whether an act runs now or waits for the owner and writes the log. There is no delete
here for mail or for a calendar event except what undoes a thing Life OS made itself (a draft, an event created by an agent): `delete_draft` and
`delete_event` are used by Undo and are not tools. A call that Google refuses for a missing permission says to connect the inbox again.
"""
import base64
from email.message import EmailMessage
from urllib.parse import quote

import frappe
from frappe import _

from lifeos.mail.gmail import API, GmailError

CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary"
RESPONSES = ("accepted", "declined", "tentative")


class GoogleError(GmailError):
	"""A Google call that failed. The message never holds a token or the response."""


def raw_message(to: str, subject: str, body: str, cc: str | None = None, sender: str | None = None, reply_to: dict | None = None) -> str:
	"""A message as Gmail takes it: RFC 822 text, base64url. Plain text only."""
	msg = EmailMessage()
	msg["To"], msg["Subject"] = to, subject
	if cc:
		msg["Cc"] = cc
	if sender:
		msg["From"] = sender
	if reply_to and reply_to.get("message_id"):
		msg["In-Reply-To"] = msg["References"] = reply_to["message_id"]
	msg.set_content(body)
	return base64.urlsafe_b64encode(msg.as_bytes()).decode()


class GoogleClient:
	"""The calls that change things. `headers` is a function that gives the authorization header (and refreshes the token)."""

	def __init__(self, headers):
		self.headers = headers

	def _call(self, method: str, url: str, body: dict | None = None, params: dict | None = None) -> dict:
		import requests

		try:
			r = requests.request(method, url, headers=self.headers(), json=body, params=params or {}, timeout=30)
		except requests.RequestException as e:
			raise GoogleError(_("Google could not be reached ({0}).").format(type(e).__name__)) from None
		if r.status_code in (401, 403):
			raise GoogleError(_("Google refused. Connect the inbox again and allow Life OS to send mail and change the calendar."))
		if r.status_code == 404:
			raise GoogleError(_("Google could not find that."))
		if r.status_code >= 300:
			raise GoogleError(_("Google answered {0}.").format(r.status_code))
		return r.json() if r.content else {}

	# ---- mail
	def _reply_headers(self, thread_id: str | None) -> tuple[dict | None, str | None]:
		"""The Message-ID of a thread's last message, so a reply sits in the thread."""
		if not thread_id:
			return None, None
		thread = self._call("GET", f"{API}/threads/{quote(thread_id, safe='')}", params={"format": "metadata", "metadataHeaders": ["Message-ID"]})
		last = (thread.get("messages") or [{}])[-1]
		ids = [h["value"] for h in (last.get("payload") or {}).get("headers") or [] if h.get("name", "").lower() == "message-id"]
		return ({"message_id": ids[0]} if ids else None), thread_id

	def send(self, to: str, subject: str, body: str, thread_id: str | None = None, cc: str | None = None) -> dict:
		reply, thread_id = self._reply_headers(thread_id)
		out = self._call("POST", f"{API}/messages/send", {"raw": raw_message(to, subject, body, cc, reply_to=reply), **({"threadId": thread_id} if thread_id else {})})
		return {"id": out.get("id"), "thread_id": out.get("threadId")}

	def draft(self, to: str, subject: str, body: str, thread_id: str | None = None, cc: str | None = None) -> dict:
		reply, thread_id = self._reply_headers(thread_id)
		out = self._call("POST", f"{API}/drafts", {"message": {"raw": raw_message(to, subject, body, cc, reply_to=reply), **({"threadId": thread_id} if thread_id else {})}})
		return {"id": out.get("id"), "thread_id": (out.get("message") or {}).get("threadId")}

	def delete_draft(self, draft_id: str) -> None:
		"""Only Undo of a draft the agent made."""
		self._call("DELETE", f"{API}/drafts/{quote(draft_id, safe='')}")

	def modify(self, thread_id: str, add: list | None = None, remove: list | None = None) -> dict:
		return self._call("POST", f"{API}/threads/{quote(thread_id, safe='')}/modify", {"addLabelIds": add or [], "removeLabelIds": remove or []})

	def archive(self, thread_id: str) -> None:
		self.modify(thread_id, remove=["INBOX"])

	def unarchive(self, thread_id: str) -> None:
		self.modify(thread_id, add=["INBOX"])

	def label_id(self, name: str) -> str:
		"""The id of a label by its name; made when it does not exist."""
		for row in self._call("GET", f"{API}/labels").get("labels") or []:
			if row.get("name", "").lower() == name.lower():
				return row["id"]
		return self._call("POST", f"{API}/labels", {"name": name}).get("id")

	def label(self, thread_id: str, name: str) -> str:
		label = self.label_id(name)
		self.modify(thread_id, add=[label])
		return label

	def unlabel(self, thread_id: str, label_id: str) -> None:
		self.modify(thread_id, remove=[label_id])

	# ---- calendar
	def list_events(self, time_min: str, time_max: str, limit: int = 50) -> list:
		out = self._call("GET", f"{CALENDAR}/events", params={"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "orderBy": "startTime", "maxResults": limit})
		return [event_out(e) for e in out.get("items") or []]

	def create_event(self, title: str, start: str, end: str, attendees: list | None = None, description: str | None = None, location: str | None = None) -> dict:
		body = {"summary": title, "start": when(start), "end": when(end), **({"description": description} if description else {}), **({"location": location} if location else {}),
			**({"attendees": [{"email": a} for a in attendees]} if attendees else {})}
		return event_out(self._call("POST", f"{CALENDAR}/events", body, {"sendUpdates": "all"} if attendees else None))

	def move_event(self, event_id: str, start: str, end: str) -> dict:
		return event_out(self._call("PATCH", f"{CALENDAR}/events/{quote(event_id, safe='')}", {"start": when(start), "end": when(end)}, {"sendUpdates": "all"}))

	def respond(self, event_id: str, response: str, address: str) -> dict:
		event = self._call("GET", f"{CALENDAR}/events/{quote(event_id, safe='')}")
		people = event.get("attendees") or []
		mine = [a for a in people if a.get("self") or a.get("email", "").lower() == address.lower()]
		if not mine:
			raise GoogleError(_("You are not on that event's guest list."))
		for a in mine:
			a["responseStatus"] = response
		return event_out(self._call("PATCH", f"{CALENDAR}/events/{quote(event_id, safe='')}", {"attendees": people}, {"sendUpdates": "all"}))

	def delete_event(self, event_id: str) -> None:
		"""Only Undo of an event the agent made."""
		self._call("DELETE", f"{CALENDAR}/events/{quote(event_id, safe='')}", params={"sendUpdates": "all"})


def when(value: str) -> dict:
	"""A date (2026-11-25) is an all-day time; anything longer is a date and time."""
	value = str(value).strip()
	return {"date": value} if len(value) == 10 else {"dateTime": value, "timeZone": frappe.utils.get_system_timezone()}


def event_out(e: dict) -> dict:
	start, end = e.get("start") or {}, e.get("end") or {}
	return {"event_id": e.get("id"), "title": e.get("summary") or "", "start": start.get("dateTime") or start.get("date"), "end": end.get("dateTime") or end.get("date"),
		"location": e.get("location") or "", "attendees": [a.get("email") for a in e.get("attendees") or []], "link": e.get("htmlLink") or "",
		"response": next((a.get("responseStatus") for a in e.get("attendees") or [] if a.get("self")), None)}
