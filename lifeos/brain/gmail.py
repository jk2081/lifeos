"""Life OS reads Gmail itself (issue 58), read only.

The sign-in is Frappe's own: Google Settings holds the OAuth client, and a Connected App for each mailbox (named life-os-gmail-1, -2,
so the redirect address to register with Google is the same every time) holds the token in a Token Cache. The only scope asked for is
`gmail.readonly`. `GmailClient` has no method that changes mail: it can list threads, get a thread, get an attachment and read the
profile, all with GET. Nothing in Gmail is marked read, labelled, moved or deleted.

Every 15 minutes `fetch_all` reads each connected mailbox's new threads (the Inbox, or one label). Cheap rules in code first: Gmail's
Promotions, Social, Updates and Forums, `List-Unsubscribe`, `Precedence: bulk` and no-reply senders are skipped, and each mailbox has an
always-include and an always-skip list. What is left goes to the `ingest-email` skill, which decides what matters. A kept thread is one
capture (source gmail, external_id the thread's ID); a new reply updates it, and a finished one goes back to the Brain.
"""
import base64
import calendar
import datetime
import html
import re
from email.utils import parseaddr
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, getdate, nowdate, sanitize_html

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
AUTHORIZATION_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
APP_PREFIX = "life-os-gmail-"
CATEGORIES = ("CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS")
NO_REPLY = re.compile(r"(^|[^a-z0-9])(no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer-daemon|postmaster)([^a-z0-9]|$)")
ATTACHMENT_CAP = 10_000_000  # bytes of one attachment kept
FIRST_DAYS = 3  # a mailbox just connected reads this many days back
OVERLAP_SECONDS = 300  # each run starts a little before the last one ended, so nothing in between is missed
THREADS_PER_RUN = 150
EARLIER_CHARS, TEXT_CHARS = 1200, 20000


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

	def list_threads(self, query: str, page_token: str | None = None) -> dict:
		return self._get("/threads", {"q": query, "maxResults": 100, **({"pageToken": page_token} if page_token else {})})

	def get_thread(self, thread_id: str) -> dict:
		return self._get(f"/threads/{quote(thread_id, safe='')}", {"format": "full"})

	def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
		data = self._get(f"/messages/{quote(message_id, safe='')}/attachments/{quote(attachment_id, safe='')}").get("data") or ""
		return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def client_for(conn) -> GmailClient:
	"""A client for a mailbox, with the token of the person who connected it."""
	if not conn.connected_app or not frappe.db.exists("Connected App", conn.connected_app):
		raise GmailError(_("This mailbox is not connected."))
	app = frappe.get_doc("Connected App", conn.connected_app)
	user = conn.connected_by or "Administrator"

	def headers():
		cache = app.get_active_token(user)
		if not cache or not cache.get_password("access_token", raise_exception=False):
			raise GmailError(_("This mailbox is not connected."))
		return cache.get_auth_header()

	return GmailClient(headers)


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
	"""The Connected App of one mailbox, from Google Settings, asking for read-only Gmail."""
	s = frappe.get_doc("Google Settings")
	values = {"provider_name": name, "client_id": s.client_id, "client_secret": s.get_password("client_secret"),
		"authorization_uri": AUTHORIZATION_URI, "token_uri": TOKEN_URI}
	if frappe.db.exists("Connected App", name):
		app = frappe.get_doc("Connected App", name)
		app.update(values)
		app.set("scopes", [{"scope": SCOPE}])
		app.set("query_parameters", [{"key": "access_type", "value": "offline"}, {"key": "prompt", "value": "consent"}])
		app.save(ignore_permissions=True)
		return app
	app = frappe.get_doc({"doctype": "Connected App", **values, "scopes": [{"scope": SCOPE}],
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


def body_of(thread) -> str:
	"""The latest message's text, then the thread's earlier messages folded under it, each shortened."""
	messages = thread.get("messages") or []
	latest = messages[-1]
	head = headers_of(latest)
	out = [f"From: {who(head)}\nDate: {head.get('date', '')}\n\n{text_of(latest)}"]
	earlier = []
	for m in reversed(messages[:-1]):
		h = headers_of(m)
		words = text_of(m)
		if len(words) > EARLIER_CHARS:
			words = words[:EARLIER_CHARS].rstrip() + " …"
		earlier.append(f"**{who(h)}**, {h.get('date', '')}\n" + "\n".join("» " + line for line in words.splitlines()))
	if earlier:
		out.append("---\nEarlier in this thread:\n\n" + "\n\n".join(earlier))
	return "\n\n".join(out)[:TEXT_CHARS]


def link_of(thread_id: str, mailbox: str) -> str:
	return f"https://mail.google.com/mail/?authuser={quote(mailbox or '', safe='@')}#all/{thread_id}"


def triage(conn, thread):
	"""The ingest-email skill's say on a thread that passed the cheap rules: (keep, reason). With no answer (no key, over the cap,
	the skill switched off or failed) it is kept: mail from a real person is never dropped because the AI could not look."""
	from lifeos.skills import call

	latest = (thread.get("messages") or [{}])[-1]
	head = headers_of(latest)
	answer = call.ask("ingest-email", {"from": head.get("from", ""), "to": head.get("to", ""), "subject": subject_of(thread),
		"snippet": text_of(latest)[:600], "mailbox": conn.mailbox, "messages_in_thread": len(thread.get("messages") or [])}, conn.space)
	if not answer:
		return True, ""
	return bool(answer.get("keep", True)), str(answer.get("reason") or "")[:140]


def file_thread(conn, client, thread: dict) -> str:
	"""Make or update the one capture of a thread. Returns "created", "updated" or "unchanged"."""
	from lifeos.api import inbox

	thread_id = thread["id"]
	existing = frappe.db.get_value("Life Inbox Item", {"space": conn.space, "source_system": "gmail", "external_id": thread_id})
	# written as Frappe will keep them (it makes saved text safe, and doing it first keeps a second read of the same mail "unchanged")
	common = {"title": sanitize_html(subject_of(thread)), "raw_text": sanitize_html(body_of(thread)), "source_url": link_of(thread_id, conn.mailbox)}
	if existing:  # a reply: only what changed is written, and a finished capture goes back to the Brain
		done = inbox.create_item(space=conn.space, source_type="Email", source_system="gmail", external_id=thread_id, **common)
		result = "updated" if done.get("changed") else "unchanged"
		name = existing
	else:
		done = inbox.create_item(space=conn.space, source_type="Email", source_system="gmail", external_id=thread_id,
			intent=conn.default_intent or None, area=conn.default_area, goal=conn.default_goal, **common)
		name, result = done["name"], "created"
	if listed_any(thread, conn.always_sensitive):
		frappe.db.set_value("Life Inbox Item", name, "is_sensitive", 1, update_modified=False)
	if conn.attach_files:
		attach(name, client, thread)
	return result


def listed_any(thread, text) -> bool:
	patterns = _lines(text)
	return bool(patterns) and any(listed(sender_of(m), patterns) for m in thread.get("messages") or [])


def attach(item: str, client, thread: dict):
	"""The thread's attachments up to 10 MB each, as files of the capture; one already kept (by name) is not fetched again."""
	have = {f.file_name for f in frappe.get_all("File", filters={"attached_to_doctype": "Life Inbox Item", "attached_to_name": item}, fields=["file_name"])}
	for m in thread.get("messages") or []:
		for a in attachments_of(m):
			if a["name"] in have or a["size"] > ATTACHMENT_CAP:
				continue
			content = client.get_attachment(m["id"], a["id"])
			if not content or len(content) > ATTACHMENT_CAP:
				continue
			frappe.db.savepoint("lifeos_gmail_file")
			try:
				frappe.get_doc({"doctype": "File", "file_name": a["name"][:140], "attached_to_doctype": "Life Inbox Item", "attached_to_name": item,
					"is_private": 1, "content": content}).insert(ignore_permissions=True)
			except Exception as e:  # a file that cannot be kept (a broken PDF) never costs the capture
				frappe.db.rollback(save_point="lifeos_gmail_file")
				frappe.log_error(title="Life OS Gmail: an attachment could not be kept", message=f"{type(e).__name__}: {scrub(e)[:200]}")
			have.add(a["name"])


# ---------------------------------------------------------------- one run

def _week_counts(conn):
	"""The week's counters, started again on Monday."""
	monday = add_to_date(getdate(nowdate()), days=-getdate(nowdate()).weekday())
	if not conn.week_start or getdate(conn.week_start) != monday:
		conn.week_start, conn.seen_week, conn.kept_week = monday, 0, 0


def utcnow() -> datetime.datetime:
	"""The cursor is kept in UTC (a Datetime field has no zone), so Gmail's epoch seconds do not depend on the server's zone."""
	return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def epoch(moment) -> int:
	return calendar.timegm(get_datetime(moment).timetuple())


def query_for(conn, since) -> str:
	where = f"label:{re.sub(r'[^A-Za-z0-9_.-]+', '-', conn.label_name.strip())}" if (conn.label_name or "").strip() else "in:inbox"
	return f"{where} after:{epoch(since)}"


def fetch(conn_name: str, client=None) -> dict:
	"""Read one mailbox's new threads and file them. Returns {seen, kept, updated, skipped: {reason: n}}."""
	conn = frappe.get_doc("Life Connection", conn_name)
	started = utcnow()
	client = client or client_for(conn)
	stats = {"seen": 0, "kept": 0, "updated": 0, "skipped": {}}
	try:
		if not conn.mailbox:
			finish(conn, client)
		since = add_to_date(get_datetime(conn.fetched_until) if conn.fetched_until else started, seconds=-OVERLAP_SECONDS,
			days=0 if conn.fetched_until else -FIRST_DAYS)
		cursor = epoch(since) + OVERLAP_SECONDS
		_week_counts(conn)
		page, handled = None, 0
		while handled < THREADS_PER_RUN:
			listing = client.list_threads(query_for(conn, since), page)
			for ref in listing.get("threads") or []:
				handled += 1
				one(conn, client, ref["id"], cursor, stats)
			page = listing.get("nextPageToken")
			if not page:
				break
		conn.fetched_until, conn.last_error = started, None
		conn.seen_week = (conn.seen_week or 0) + stats["seen"]
		conn.kept_week = (conn.kept_week or 0) + stats["kept"]
	except GmailError as e:
		conn.last_error = scrub(e)[:140]
		stats["error"] = conn.last_error
	conn.save(ignore_permissions=True)
	return stats


def one(conn, client, thread_id, cursor, stats):
	"""One thread: fetched, judged, filed. A failure is logged for this thread only (without the token) and the run goes on."""
	try:
		thread = client.get_thread(thread_id)
		messages = thread.get("messages") or []
		if not messages:
			return
		fresh = int(messages[-1].get("internalDate") or 0) / 1000 > cursor
		known = frappe.db.exists("Life Inbox Item", {"space": conn.space, "source_system": "gmail", "external_id": thread["id"]})
		if fresh and not known:
			stats["seen"] += 1
		keep, why = judge(thread, conn.mailbox, conn.always_include, conn.always_skip)
		if keep and not known and why != "always include":
			keep, why = triage(conn, thread)
		if not keep:
			stats["skipped"][why] = stats["skipped"].get(why, 0) + 1
			return
		frappe.flags.lifeos_touch_connection = conn.name
		try:
			result = file_thread(conn, client, thread)
		finally:
			frappe.flags.lifeos_touch_connection = None
		stats["kept" if result == "created" else "updated"] += 1 if result != "unchanged" else 0
	except GmailError:
		raise
	except Exception as e:
		frappe.log_error(title="Life OS Gmail: a thread could not be filed", message=f"{type(e).__name__}: {scrub(e)[:200]}")


def fetch_all():
	"""Every 15 minutes: each switched-on mailbox, one after the other. One failing does not stop the rest."""
	for name in frappe.get_all("Life Connection", filters={"system": "gmail", "active": 1, "connected_app": ["is", "set"]}, pluck="name"):
		try:
			fetch(name)
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(title="Life OS Gmail: a mailbox could not be read", message=f"{type(e).__name__}: {scrub(e)[:200]}")
