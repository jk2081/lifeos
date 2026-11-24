"""The Microsoft adapter and its Graph client (issue 88): Outlook and Microsoft 365 as the second mail provider.

The sign-in is Frappe's own, as for Gmail: a Connected App for each inbox (life-os-microsoft-1, -2, ...) holds the token in a Token Cache, encrypted. The
Azure app registration's client ID and secret are in the site config (`lifeos_microsoft_client_id`, `lifeos_microsoft_client_secret`, and
`lifeos_microsoft_tenant`, "common" when not set), never in the repository: see `docs/MICROSOFT.md`. Mail is never copied into Life OS: `MicrosoftAdapter`
turns a search into Graph's own search syntax and reads the few conversations that match, live. `GraphActs` changes things (send, drafts, archive,
categories) and is reached only through `lifeos.agents.acts`. A conversation is a thread: its `conversationId` is the `thread_id` Life OS uses.
"""
import re
from datetime import datetime
from urllib.parse import quote

import frappe
from frappe import _

from lifeos.mail import gmail
from lifeos.mail.gmail import GmailError, scrub

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ("offline_access", "User.Read", "Mail.Read", "Mail.ReadWrite", "Mail.Send")
APP_PREFIX = "life-os-microsoft-"
AUTHORITY = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
SNIPPET_CHARS, THREAD_CHARS = 300, 12000
LIST_FIELDS = "id,conversationId,subject,from,toRecipients,receivedDateTime,bodyPreview,webLink,categories,hasAttachments"


class MicrosoftError(GmailError):
	"""A Graph call that failed. The message never holds a token or the response."""


# ---------------------------------------------------------------- the client

class GraphClient:
	"""Reads, and the one call every change goes through. `headers` is a function that gives the authorization header (and refreshes the token)."""

	def __init__(self, headers):
		self.headers = headers

	def _call(self, method: str, path: str, params: dict | None = None, body: dict | None = None, extra: dict | None = None, raw: bool = False):
		import requests

		url = path if path.startswith("https://") else GRAPH + path
		try:
			r = requests.request(method, url, headers={**self.headers(), **(extra or {})}, params=params or {}, json=body, timeout=30)
		except requests.RequestException as e:
			raise MicrosoftError(_("Microsoft could not be reached ({0}).").format(type(e).__name__)) from None
		if r.status_code in (401, 403):
			raise MicrosoftError(_("Microsoft refused access. Connect the inbox again."))
		if r.status_code == 404:
			raise MicrosoftError(_("Microsoft could not find that."))
		if r.status_code >= 300:
			raise MicrosoftError(_("Microsoft answered {0}.").format(r.status_code))
		if raw:
			return r.content
		return r.json() if r.content else {}

	def profile(self) -> dict:
		return self._call("GET", "/me", {"$select": "mail,userPrincipalName"})

	def search_messages(self, search: str, top: int = 10, next_link: str | None = None) -> dict:
		"""Messages that match a Graph search string (KQL). Graph does not combine `$search` with `$filter` or `$orderby`, so every plain field is in the string."""
		if next_link:
			return self.next_page(next_link)
		return self._call("GET", "/me/messages", {"$search": f'"{search}"', "$top": top, "$select": LIST_FIELDS})

	def conversation(self, conversation_id: str) -> dict:
		"""Every message of one conversation, as plain text, with its attachments."""
		return self._call("GET", "/me/messages", {"$filter": f"conversationId eq '{conversation_id.replace(chr(39), chr(39) * 2)}'", "$top": 50,
			"$select": LIST_FIELDS + ",body,toRecipients,internetMessageId", "$expand": "attachments($select=id,name,size,isInline)"},
			{"Prefer": 'outlook.body-content-type="text"'})

	def inbox_since(self, since: str, category: str = "", top: int = 100) -> dict:
		flt = f"receivedDateTime ge {since}T00:00:00Z" + (f" and categories/any(c:c eq '{category.replace(chr(39), chr(39) * 2)}')" if category else "")
		return self._call("GET", "/me/mailFolders/inbox/messages", {"$filter": flt, "$top": top, "$select": LIST_FIELDS + ",internetMessageHeaders"})

	def next_page(self, url: str) -> dict:
		return self._call("GET", url)

	def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
		return self._call("GET", f"/me/messages/{quote(message_id, safe='')}/attachments/{quote(attachment_id, safe='')}/$value", raw=True)


class GraphActs(GraphClient):
	"""What changes in a person's mailbox: send and draft, archive and categorise a conversation. No delete except Undo of a draft Life OS made."""

	def _recipients(self, text: str | None) -> list:
		return [{"emailAddress": {"address": a.strip()}} for a in re.split(r"[,;]", text or "") if a.strip()]

	def _last_in(self, thread_id: str) -> str | None:
		if not thread_id:
			return None
		got = self.conversation(thread_id).get("value") or []
		got.sort(key=lambda m: m.get("receivedDateTime") or "")
		return got[-1]["id"] if got else None

	def send(self, to: str, subject: str, body: str, thread_id: str | None = None, cc: str | None = None) -> dict:
		last = self._last_in(thread_id)
		message = {"toRecipients": self._recipients(to), "ccRecipients": self._recipients(cc)}
		if last:  # a reply sits in its conversation
			self._call("POST", f"/me/messages/{quote(last, safe='')}/reply", body={"message": message, "comment": body})
			return {"id": None, "thread_id": thread_id}
		self._call("POST", "/me/sendMail", body={"message": {**message, "subject": subject, "body": {"contentType": "Text", "content": body}}, "saveToSentItems": True})
		return {"id": None, "thread_id": None}

	def draft(self, to: str, subject: str, body: str, thread_id: str | None = None, cc: str | None = None) -> dict:
		last = self._last_in(thread_id)
		content = {"toRecipients": self._recipients(to), "ccRecipients": self._recipients(cc), "body": {"contentType": "Text", "content": body}}
		if last:
			made = self._call("POST", f"/me/messages/{quote(last, safe='')}/createReply", body={})
			out = self._call("PATCH", f"/me/messages/{quote(made['id'], safe='')}", body=content)
		else:
			out = self._call("POST", "/me/messages", body={**content, "subject": subject})
		return {"id": out.get("id"), "thread_id": out.get("conversationId")}

	def delete_draft(self, draft_id: str) -> None:
		"""Only Undo of a draft the agent made."""
		self._call("DELETE", f"/me/messages/{quote(draft_id, safe='')}")

	def _messages(self, thread_id: str) -> list:
		return self.conversation(thread_id).get("value") or []

	def _move(self, thread_id: str, folder: str) -> None:
		for m in self._messages(thread_id):
			self._call("POST", f"/me/messages/{quote(m['id'], safe='')}/move", body={"destinationId": folder})

	def archive(self, thread_id: str) -> None:
		self._move(thread_id, "archive")

	def unarchive(self, thread_id: str) -> None:
		self._move(thread_id, "inbox")

	def label(self, thread_id: str, name: str) -> str:
		"""A label is an Outlook category."""
		for m in self._messages(thread_id):
			have = list(m.get("categories") or [])
			if name not in have:
				self._call("PATCH", f"/me/messages/{quote(m['id'], safe='')}", body={"categories": have + [name]})
		return name

	def unlabel(self, thread_id: str, label_id: str) -> None:
		for m in self._messages(thread_id):
			have = list(m.get("categories") or [])
			if label_id in have:
				self._call("PATCH", f"/me/messages/{quote(m['id'], safe='')}", body={"categories": [c for c in have if c != label_id]})

	# Microsoft's calendar is not built (issue 88): the calendar tools work for Google inboxes only.
	def _no_calendar(self, *a, **kw):
		raise MicrosoftError(_("Microsoft calendars are not connected yet. Calendar tools work for Google inboxes."))

	list_events = create_event = move_event = respond = delete_event = _no_calendar


def headers_for(conn):
	"""A function that gives an inbox's authorization header (and refreshes the token), with the token of the person who connected it."""
	return gmail.headers_for(conn)


def client_for(conn) -> GraphClient:
	return GraphClient(headers_for(conn))


# ---------------------------------------------------------------- connecting

def _conf(key: str) -> str:
	return str(frappe.conf.get(key) or "").strip()


def configured() -> bool:
	return bool(_conf("lifeos_microsoft_client_id") and _conf("lifeos_microsoft_client_secret"))


def _authority() -> str:
	return AUTHORITY.format(tenant=_conf("lifeos_microsoft_tenant") or "common")


def free_app_name() -> str:
	"""The lowest life-os-microsoft-N not used by an inbox: its redirect address is already known to Azure."""
	used = set(frappe.get_all("Life Connection", filters={"system": "microsoft", "connected_app": ["is", "set"]}, pluck="connected_app"))
	n = 1
	while f"{APP_PREFIX}{n}" in used:
		n += 1
	return f"{APP_PREFIX}{n}"


def make_app(name: str):
	"""The Connected App of one inbox, from the site config's Azure client, asking for read, send and what an agent acts with (see SCOPES)."""
	values = {"provider_name": name, "client_id": _conf("lifeos_microsoft_client_id"), "client_secret": _conf("lifeos_microsoft_client_secret"),
		"authorization_uri": f"{_authority()}/authorize", "token_uri": f"{_authority()}/token"}
	query = [{"key": "prompt", "value": "select_account"}]
	if frappe.db.exists("Connected App", name):
		app = frappe.get_doc("Connected App", name)
		app.update(values)
		app.set("scopes", [{"scope": x} for x in SCOPES])
		app.set("query_parameters", query)
		app.save(ignore_permissions=True)  # system: the app is Life OS's own, from the site config
		return app
	app = frappe.get_doc({"doctype": "Connected App", **values, "scopes": [{"scope": x} for x in SCOPES], "query_parameters": query})
	frappe.flags.in_import = True  # the name is chosen here, not a random hash
	try:
		app.name = name
		app.insert(ignore_permissions=True)  # system: as above
	finally:
		frappe.flags.in_import = False
	return app


def finish(conn, client=None):
	"""After the sign-in: read the inbox's address from Microsoft, switch the card on. Safe to call again."""
	client = client or client_for(conn)
	me = client.profile()
	email = (me.get("mail") or me.get("userPrincipalName") or "").strip().lower()
	if not email:
		raise MicrosoftError(_("Microsoft did not say which inbox this is."))
	other = frappe.db.get_value("Life Connection", {"space": conn.space, "system": "microsoft", "mailbox": email, "name": ["!=", conn.name]})
	if other:
		raise MicrosoftError(_("{0} is already connected.").format(email))
	conn.mailbox, conn.label, conn.active, conn.last_error = email, email, 1, None
	conn.save(ignore_permissions=True)  # system: the card the person just signed in
	from lifeos import mail

	mail.account_for_connection(conn)
	return conn


# ---------------------------------------------------------------- reading a message

def _address(entry) -> str:
	return ((entry or {}).get("emailAddress") or {}).get("address", "") or ""


def who(entry) -> str:
	"""A sender as "Name (address)", the way Gmail's `who` writes it."""
	a = (entry or {}).get("emailAddress") or {}
	name, address = (a.get("name") or "").strip(), (a.get("address") or "").strip()
	return f"{name} ({address})" if name and address and name.lower() != address.lower() else address or name


def _epoch(value: str | None) -> int:
	try:
		return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
	except (TypeError, ValueError):
		return 0


def _snippet(m) -> str:
	return " ".join(str(m.get("bodyPreview") or "").split())[:SNIPPET_CHARS]


def _subject(m) -> str:
	return re.sub(r"\s+", " ", m.get("subject") or "").strip()[:140] or _("(no subject)")


def headers_of(m) -> dict:
	return {h.get("name", "").lower(): h.get("value", "") for h in m.get("internetMessageHeaders") or []}


def judge(m: dict, mailbox: str, include="", skip="") -> tuple[bool, str]:
	"""The same cheap rules as Gmail's, on a Graph message: always-include beats everything, always-skip beats the header rules."""
	include, skip = gmail._lines(include), gmail._lines(skip)
	sender = _address(m.get("from")).lower()
	if sender == (mailbox or "").lower():
		return False, "only your own messages"
	if gmail.listed(sender, include):
		return True, "always include"
	if gmail.listed(sender, skip):
		return False, "always skip"
	head = headers_of(m)
	if "list-unsubscribe" in head or head.get("precedence", "").strip().lower() in ("bulk", "list", "junk"):
		return False, "a mailing list"
	if gmail.NO_REPLY.search(sender.split("@")[0] + " "):
		return False, "a no-reply sender"
	return True, ""


# ---------------------------------------------------------------- the adapter

OPERATORS = (("from", "from"), ("to", "to"), ("subject", "subject"), ("filename", "attachment"))


def _term(value) -> str:
	"""A value for a Graph search string: several words are grouped in brackets; characters that would end the quoted string are dropped."""
	value = " ".join(re.sub(r'["()\\]', " ", str(value)).split())
	return f"({value})" if re.search(r"\s", value) else value


def _day(value) -> str:
	m = re.match(r"^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*$", str(value))
	if not m:
		frappe.throw(_("A date must be written 2014-04-05."), title=_("Date not understood"))
	return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def build_query(fields: dict) -> str:
	"""The plain search fields as a Graph search string (KQL). `raw` is a Graph search string, passed through and added to what the fields say.
	Dates and attachments are in the string too: Graph does not allow `$filter` beside `$search` on messages."""
	fields = fields or {}
	parts = []
	if str(fields.get("text") or "").strip():
		parts.append(re.sub(r'["\\]', " ", " ".join(str(fields["text"]).split())))
	for field, operator in OPERATORS:
		if str(fields.get(field) or "").strip():
			parts.append(f"{operator}:{_term(fields[field])}")
	if fields.get("has_attachment") not in (None, "", 0, "0", False, "false"):
		parts.append("hasattachments:true")
	if str(fields.get("after") or "").strip():
		parts.append(f"received>={_day(fields['after'])}")
	if str(fields.get("before") or "").strip():
		parts.append(f"received<{_day(fields['before'])}")
	if str(fields.get("raw") or "").strip():
		parts.append(re.sub(r'"', " ", str(fields["raw"]).strip()))
	return " ".join(parts)


class MicrosoftAdapter:
	"""One Microsoft inbox, as the rest of Life OS sees every inbox: search, get_thread, get_attachment, send and draft."""

	provider = "microsoft"

	def __init__(self, account, client):
		self.account = account
		self.client = client

	def query(self, fields: dict) -> str:
		return build_query(fields)

	def search(self, fields: dict, max_results: int = 10) -> list:
		top = max(1, min(int(max_results or 10), 25))
		found = self.client.search_messages(self.query(fields), top * 2).get("value") or []
		seen, hits = set(), []
		for m in sorted(found, key=lambda m: m.get("receivedDateTime") or "", reverse=True):
			conv = m.get("conversationId") or m["id"]
			if conv in seen:
				continue
			seen.add(conv)
			hits.append({"thread_id": conv, "subject": _subject(m), "from": who(m.get("from")), "date": m.get("receivedDateTime", ""), "at": _epoch(m.get("receivedDateTime")),
				"snippet": _snippet(m), "messages": 1, "started_by": who(m.get("from")), "link": m.get("webLink") or ""})
		return hits[:top]

	def list_page(self, fields: dict, page_token: str | None = None, size: int = 25) -> dict:
		"""One page of the conversations the fields match (issue 107); the token is Graph's own next link. Graph gives no estimate of the whole."""
		listing = self.client.search_messages(self.query(fields), max(1, min(int(size or 25), 100)), page_token or None)
		seen, hits = set(), []
		for m in sorted(listing.get("value") or [], key=lambda m: m.get("receivedDateTime") or "", reverse=True):
			conv = m.get("conversationId") or m["id"]
			if conv in seen:
				continue
			seen.add(conv)
			hits.append({"thread_id": conv, "subject": _subject(m), "from": who(m.get("from")), "date": m.get("receivedDateTime", ""), "at": _epoch(m.get("receivedDateTime")),
				"snippet": _snippet(m), "messages": 1, "started_by": who(m.get("from")), "link": m.get("webLink") or ""})
		return {"hits": hits, "next": listing.get("@odata.nextLink") or None, "estimate": None}

	def get_thread(self, thread_id: str) -> dict:
		got = sorted(self.client.conversation(thread_id).get("value") or [], key=lambda m: m.get("receivedDateTime") or "")
		if not got:
			raise MicrosoftError(_("Microsoft could not find that conversation."))
		out = [{"message_id": m["id"], "from": who(m.get("from")), "to": ", ".join(_address(r) for r in m.get("toRecipients") or []), "date": m.get("receivedDateTime", ""),
			"text": str((m.get("body") or {}).get("content") or "").strip()[:THREAD_CHARS],
			"attachments": [{"attachment_id": a["id"], "filename": a.get("name") or "attachment", "size": int(a.get("size") or 0)}
				for a in m.get("attachments") or [] if not a.get("isInline")]} for m in got]
		return {"thread_id": thread_id, "subject": _subject(got[0]), "link": got[-1].get("webLink") or "", "messages": out}

	def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
		return self.client.get_attachment(message_id, attachment_id)

	def send(self, to: str, subject: str, body: str, thread_id: str | None = None, cc: str | None = None) -> dict:
		from lifeos import mail

		return mail.google_for(self.account).send(to, subject, body, thread_id, cc)

	def draft(self, to: str, subject: str, body: str, thread_id: str | None = None, cc: str | None = None) -> dict:
		from lifeos import mail

		return mail.google_for(self.account).draft(to, subject, body, thread_id, cc)

	def recent(self, since: str, label: str = "", include: str = "", skip: str = "", limit: int = 100) -> list:
		"""The inbox's conversations since a day, for the digest: each with `person` true when the cheap rules say a real person wrote it (the Inbox, or one category)."""
		listing, latest = self.client.inbox_since(_day(since), (label or "").strip(), min(100, limit)), {}
		for _page in range(5):
			for m in listing.get("value") or []:
				conv = m.get("conversationId") or m["id"]
				if conv not in latest or (m.get("receivedDateTime") or "") > (latest[conv].get("receivedDateTime") or ""):
					latest[conv] = m
			url = listing.get("@odata.nextLink")
			if not url or len(latest) >= limit:
				break
			listing = self.client.next_page(url)
		out = []
		for conv, m in list(latest.items())[:limit]:
			keep, why = judge(m, self.account.address, include, skip)
			out.append({"thread_id": conv, "subject": _subject(m), "from": who(m.get("from")), "sender": _address(m.get("from")).lower(), "at": _epoch(m.get("receivedDateTime")),
				"snippet": _snippet(m), "person": keep, "why": why, "messages": 1, "link": m.get("webLink") or "",
				"to": ", ".join(_address(r) for r in m.get("toRecipients") or []), "date": m.get("receivedDateTime", "")})
		return out


__all__ = ["MicrosoftAdapter", "MicrosoftError", "GraphClient", "GraphActs", "scrub"]
