"""The Gmail adapter and its client (issues 58 and 86).

The sign-in is Frappe's own: Google Settings holds the OAuth client, and a Connected App for each mailbox (named life-os-gmail-1, -2, so the
redirect address to register with Google is the same every time) holds the token in a Token Cache, encrypted. Gmail is never copied into Life OS:
`GmailAdapter` turns a search into a Gmail query and reads the few threads that match, live. `GmailClient` only reads (GET); what changes mail or
the calendar is `lifeos.mail.google`, reached only through `lifeos.agents.acts`.

The cheap rules for "mail from a real person" (`judge`) are used by the daily digest (`lifeos.mail.digest`).
"""
import base64
import html
import re
from email.utils import parseaddr
from urllib.parse import quote

import frappe
from frappe import _

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
# what the person is asked for, once: read, and (for the agent's acts, always through acts.py) send, drafts, archive and labels, calendar events
ACT_SCOPES = ("https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.modify",
	"https://www.googleapis.com/auth/calendar.events")
SCOPES = (SCOPE, *ACT_SCOPES)
API = "https://gmail.googleapis.com/gmail/v1/users/me"
AUTHORIZATION_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
APP_PREFIX = "life-os-gmail-"
CATEGORIES = ("CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS")
NO_REPLY = re.compile(r"(^|[^a-z0-9])(no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer-daemon|postmaster)([^a-z0-9]|$)")
ATTACHMENT_CAP = 10_000_000  # bytes of one attachment kept


SECRETS = re.compile(r"(?i)(ya29\.[\w.-]+|1//[\w.-]+|(bearer|token|secret|key|authorization)[\s:=\"']+[\w.~+/-]{8,})")


def scrub(text) -> str:
	"""Words for a log or a card with anything that looks like a token or a secret taken out."""
	return SECRETS.sub("[hidden]", str(text))


class GmailError(Exception):
	"""A Gmail call that failed. The message never holds a token or the response."""


# ---------------------------------------------------------------- the client (read only)

class GmailClient:
	"""Lists and gets, and nothing else. `headers` is a function that gives the authorization header (and refreshes the token)."""

	def __init__(self, headers):
		self.headers = headers

	def _get(self, path, params=None):
		import requests

		try:
			r = requests.get(API + path, headers=self.headers(), params=params or {}, timeout=30)
		except requests.RequestException as e:
			raise GmailError(_("Gmail could not be reached ({0}).").format(type(e).__name__)) from None
		if r.status_code in (401, 403):
			raise GmailError(_("Google refused access. Connect the mailbox again."))
		if r.status_code != 200:
			raise GmailError(_("Gmail answered {0}.").format(r.status_code))
		return r.json()

	def profile(self) -> dict:
		return self._get("/profile")

	def list_threads(self, query: str, page_token: str | None = None, max_results: int = 100) -> dict:
		return self._get("/threads", {"q": query, "maxResults": max_results, **({"pageToken": page_token} if page_token else {})})

	def get_thread(self, thread_id: str, fmt: str = "full") -> dict:
		extra = {"metadataHeaders": ["From", "To", "Subject", "Date"]} if fmt == "metadata" else {}
		return self._get(f"/threads/{quote(thread_id, safe='')}", {"format": fmt, **extra})

	def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
		data = self._get(f"/messages/{quote(message_id, safe='')}/attachments/{quote(attachment_id, safe='')}").get("data") or ""
		return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def headers_for(conn):
	"""A function that gives a mailbox's authorization header (and refreshes the token), with the token of the person who connected it."""
	if not conn.connected_app or not frappe.db.exists("Connected App", conn.connected_app):
		raise GmailError(_("This mailbox is not connected."))
	app = frappe.get_doc("Connected App", conn.connected_app)
	user = conn.connected_by or "Administrator"

	def headers():
		cache = app.get_active_token(user)
		if not cache or not cache.get_password("access_token", raise_exception=False):
			raise GmailError(_("This mailbox is not connected."))
		return cache.get_auth_header()

	return headers


def client_for(conn) -> GmailClient:
	return GmailClient(headers_for(conn))


# ---------------------------------------------------------------- connecting

def configured() -> bool:
	s = frappe.get_cached_doc("Google Settings")
	return bool(s.enable and s.client_id and s.get_password("client_secret", raise_exception=False))


def free_app_name() -> str:
	"""The lowest life-os-gmail-N not used by a mailbox: its redirect address is already known to Google."""
	used = set(frappe.get_all("Life Connection", filters={"system": "gmail", "connected_app": ["is", "set"]}, pluck="connected_app"))
	n = 1
	while f"{APP_PREFIX}{n}" in used:
		n += 1
	return f"{APP_PREFIX}{n}"


def redirect_uri(app_name: str) -> str:
	return frappe.utils.get_url(f"/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/{app_name}")


def make_app(name: str):
	"""The Connected App of one mailbox, from Google Settings, asking for read access and what agents act with (see SCOPES)."""
	s = frappe.get_doc("Google Settings")
	values = {"provider_name": name, "client_id": s.client_id, "client_secret": s.get_password("client_secret"),
		"authorization_uri": AUTHORIZATION_URI, "token_uri": TOKEN_URI}
	if frappe.db.exists("Connected App", name):
		app = frappe.get_doc("Connected App", name)
		app.update(values)
		app.set("scopes", [{"scope": x} for x in SCOPES])
		app.set("query_parameters", [{"key": "access_type", "value": "offline"}, {"key": "prompt", "value": "consent"}])
		app.save(ignore_permissions=True)
		return app
	app = frappe.get_doc({"doctype": "Connected App", **values, "scopes": [{"scope": x} for x in SCOPES],
		"query_parameters": [{"key": "access_type", "value": "offline"}, {"key": "prompt", "value": "consent"}]})
	frappe.flags.in_import = True  # the name is chosen here, not a random hash
	try:
		app.name = name
		app.insert(ignore_permissions=True)
	finally:
		frappe.flags.in_import = False
	return app


def finish(conn, client=None):
	"""After the sign-in: read the mailbox's address from Google, switch the card on. Safe to call again."""
	client = client or client_for(conn)
	email = (client.profile().get("emailAddress") or "").strip().lower()
	if not email:
		raise GmailError(_("Google did not say which mailbox this is."))
	other = frappe.db.get_value("Life Connection", {"space": conn.space, "system": "gmail", "mailbox": email, "name": ["!=", conn.name]})
	if other:
		raise GmailError(_("{0} is already connected.").format(email))
	conn.mailbox, conn.label, conn.active, conn.last_error = email, email, 1, None
	conn.save(ignore_permissions=True)
	from lifeos import mail

	mail.account_for_connection(conn)
	return conn


# ---------------------------------------------------------------- the rules in code

def _lines(text):
	return [x.strip().lower().lstrip("@") for x in re.split(r"[\n,;]+", text or "") if x.strip()]


def listed(sender: str, patterns) -> bool:
	"""A sender is on a list when it is the address itself, or its domain (or a sub-domain) is listed."""
	sender = (sender or "").lower()
	domain = sender.rpartition("@")[2]
	for p in patterns:
		if sender == p or (domain and (domain == p or domain.endswith("." + p))):
			return True
	return False


def headers_of(message) -> dict:
	return {h.get("name", "").lower(): h.get("value", "") for h in (message.get("payload") or {}).get("headers") or []}


def sender_of(message) -> str:
	return parseaddr(headers_of(message).get("from", ""))[1].lower()


def judge(thread: dict, mailbox: str, include="", skip="") -> tuple[bool, str]:
	"""Whether a thread passes the cheap rules, and why not. Looks at the latest message someone else wrote; always-include beats
	everything and always-skip beats the header rules."""
	include, skip = _lines(include), _lines(skip)
	mine = (mailbox or "").lower()
	messages = thread.get("messages") or []
	theirs = [m for m in messages if sender_of(m) != mine and "SENT" not in (m.get("labelIds") or [])]
	if not theirs:
		return False, "only your own messages"
	last = theirs[-1]
	if any(listed(sender_of(m), include) for m in theirs):
		return True, "always include"
	if any(listed(sender_of(m), skip) for m in theirs):
		return False, "always skip"
	if set(last.get("labelIds") or []) & set(CATEGORIES):
		return False, "Promotions, Social, Updates or Forums"
	head = headers_of(last)
	if "list-unsubscribe" in head or head.get("precedence", "").strip().lower() in ("bulk", "list", "junk"):
		return False, "a mailing list"
	if NO_REPLY.search(sender_of(last).split("@")[0] + " "):
		return False, "a no-reply sender"
	return True, ""


# ---------------------------------------------------------------- a thread as a capture

def _walk(part):
	yield part
	for p in part.get("parts") or []:
		yield from _walk(p)


def _decode(part) -> str:
	data = (part.get("body") or {}).get("data") or ""
	return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace") if data else ""


def text_of(message) -> str:
	"""The words of one message: its plain text, or its HTML with the tags taken out."""
	parts = list(_walk(message.get("payload") or {}))
	plain = "\n".join(_decode(p) for p in parts if p.get("mimeType") == "text/plain" and not p.get("filename"))
	if plain.strip():
		return plain.strip()
	raw = "\n".join(_decode(p) for p in parts if p.get("mimeType") == "text/html" and not p.get("filename"))
	raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
	raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", raw)
	text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
	return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def attachments_of(message) -> list:
	return [{"name": p["filename"], "id": p["body"]["attachmentId"], "size": int(p["body"].get("size") or 0)}
		for p in _walk(message.get("payload") or {}) if p.get("filename") and (p.get("body") or {}).get("attachmentId")]


def subject_of(thread) -> str:
	for m in thread.get("messages") or []:
		if headers_of(m).get("subject", "").strip():
			return re.sub(r"\s+", " ", headers_of(m)["subject"]).strip()[:140]
	return _("(no subject)")


def who(head) -> str:
	"""A sender as "Name (address)": Frappe takes anything between angle brackets for HTML and removes it from a saved text."""
	name, address = parseaddr(head.get("from", ""))
	return f"{name} ({address})" if name and address else address or name


def link_of(thread_id: str, mailbox: str) -> str:
	return f"https://mail.google.com/mail/?authuser={quote(mailbox or '', safe='@')}#all/{thread_id}"


# ---------------------------------------------------------------- the adapter (issue 86)

OPERATORS = (("from", "from"), ("to", "to"), ("subject", "subject"), ("filename", "filename"))
SNIPPET_CHARS, THREAD_CHARS = 300, 12000


def _quoted(value) -> str:
	value = " ".join(str(value).split()).replace('"', "")
	return f'"{value}"' if re.search(r"\s", value) else value


def _day(value) -> str:
	"""A date as Gmail wants it, 2014/04/05 (the plain field is 2014-04-05)."""
	m = re.match(r"^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*$", str(value))
	if not m:
		frappe.throw(_("A date must be written 2014-04-05."), title=_("Date not understood"))
	return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"


def build_query(fields: dict) -> str:
	"""The plain search fields as Gmail's own syntax. `raw` is Gmail's query, passed through for experts, and is added to what the fields say."""
	fields = fields or {}
	parts = []
	if str(fields.get("text") or "").strip():
		parts.append(" ".join(str(fields["text"]).split()))
	for field, operator in OPERATORS:
		if str(fields.get(field) or "").strip():
			parts.append(f"{operator}:{_quoted(fields[field])}")
	if fields.get("has_attachment") not in (None, "", 0, "0", False, "false"):
		parts.append("has:attachment")
	if str(fields.get("after") or "").strip():
		parts.append(f"after:{_day(fields['after'])}")
	if str(fields.get("before") or "").strip():
		parts.append(f"before:{_day(fields['before'])}")
	if str(fields.get("raw") or "").strip():
		parts.append(str(fields["raw"]).strip())
	return " ".join(parts)


class GmailAdapter:
	"""One inbox, as the rest of Life OS sees every inbox: search, get_thread, get_attachment, send and draft. Nothing outside says it is Gmail."""

	provider = "gmail"

	def __init__(self, account, client):
		self.account = account
		self.client = client

	def query(self, fields: dict) -> str:
		return build_query(fields)

	def search(self, fields: dict, max_results: int = 10) -> list:
		listing = self.client.list_threads(self.query(fields), None, max(1, min(int(max_results or 10), 25)))
		hits = []
		for ref in listing.get("threads") or []:
			thread = self.client.get_thread(ref["id"], "metadata")
			messages = thread.get("messages") or []
			if not messages:
				continue
			head = headers_of(messages[-1])
			first = headers_of(messages[0])
			hits.append({"thread_id": thread["id"], "subject": subject_of(thread), "from": who(head), "date": head.get("date", ""),
				"at": int(messages[-1].get("internalDate") or 0) // 1000, "snippet": " ".join(str(ref.get("snippet") or thread.get("snippet") or "").split())[:SNIPPET_CHARS],
				"messages": len(messages), "started_by": who(first), "link": link_of(thread["id"], self.account.address)})
		return hits

	def get_thread(self, thread_id: str) -> dict:
		thread = self.client.get_thread(thread_id)
		out = []
		for m in thread.get("messages") or []:
			head = headers_of(m)
			out.append({"message_id": m["id"], "from": who(head), "to": head.get("to", ""), "date": head.get("date", ""), "text": text_of(m)[:THREAD_CHARS],
				"attachments": [{"attachment_id": a["id"], "filename": a["name"], "size": a["size"]} for a in attachments_of(m)]})
		return {"thread_id": thread.get("id") or thread_id, "subject": subject_of(thread), "link": link_of(thread_id, self.account.address), "messages": out}

	def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
		return self.client.get_attachment(message_id, attachment_id)

	def send(self, to: str, subject: str, body: str, thread_id: str | None = None, cc: str | None = None) -> dict:
		from lifeos import mail

		return mail.google_for(self.account).send(to, subject, body, thread_id, cc)

	def draft(self, to: str, subject: str, body: str, thread_id: str | None = None, cc: str | None = None) -> dict:
		from lifeos import mail

		return mail.google_for(self.account).draft(to, subject, body, thread_id, cc)

	def recent(self, since: str, label: str = "", include: str = "", skip: str = "", limit: int = 100) -> list:
		"""The inbox's threads since a day, for the digest: each with `person` true when the cheap rules say a real person wrote it (the Inbox, or one label)."""
		where = f"label:{re.sub(r'[^A-Za-z0-9_.-]+', '-', label.strip())}" if (label or "").strip() else "in:inbox"
		query = f"{where} after:{_day(since)}"
		out, page = [], None
		while len(out) < limit:
			listing = self.client.list_threads(query, page, min(100, limit - len(out)))
			for ref in listing.get("threads") or []:
				thread = self.client.get_thread(ref["id"])
				messages = thread.get("messages") or []
				if not messages:
					continue
				keep, why = judge(thread, self.account.address, include, skip)
				last = messages[-1]
				theirs = [m for m in messages if sender_of(m) != self.account.address.lower() and "SENT" not in (m.get("labelIds") or [])] or [last]
				head = headers_of(theirs[-1])
				out.append({"thread_id": thread["id"], "subject": subject_of(thread), "from": who(head), "sender": sender_of(theirs[-1]), "at": int(last.get("internalDate") or 0) // 1000,
					"snippet": " ".join(text_of(theirs[-1]).split())[:SNIPPET_CHARS], "person": keep, "why": why, "messages": len(messages),
					"link": link_of(thread["id"], self.account.address), "to": headers_of(theirs[-1]).get("to", ""), "date": head.get("date", "")})
			page = listing.get("nextPageToken")
			if not page:
				break
		return out
