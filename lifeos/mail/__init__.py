"""A person's inboxes (issue 86): one `Life Mail Account` for each, searched live and never copied.

Email does not have to be in Life OS to be found. Ask and an agent search the inbox when asked, read the few threads that match, and save only
what the owner decides to keep (`file_thread`). Each person connects their own inboxes; a person's inbox is searched only by that person's Ask
and by the agent that acts for them (`accounts_for` is the one gate). One adapter for each provider (`lifeos.mail.<provider>`) turns the plain
search fields into the provider's own syntax; nothing outside an adapter knows which provider an inbox is.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

PROVIDERS = {"gmail": "lifeos.mail.gmail.GmailAdapter", "microsoft": "lifeos.mail.microsoft.MicrosoftAdapter"}
PROVIDER_NAMES = {"gmail": "Gmail", "microsoft": "Outlook"}  # what "Open in ..." says
FIELDS = ("text", "from", "to", "subject", "has_attachment", "filename", "after", "before", "raw")
MAX_HITS = 25
TEXT_CHARS = 20000


def account_for_connection(conn):
	"""The mail account of a connected mailbox (Gmail or Microsoft): made when the sign-in finishes, the same one when it is called again."""
	user = conn.connected_by or frappe.session.user
	provider = "microsoft" if conn.system == "microsoft" else "gmail"
	name = frappe.db.get_value("Life Mail Account", {"user": user, "provider": provider, "address": conn.mailbox})
	if name:
		doc = frappe.get_doc("Life Mail Account", name)
		doc.update({"connection": conn.name, "label": conn.label or conn.mailbox, "active": conn.active, "space": conn.space})
		doc.save(ignore_permissions=True)  # system: kept in step with the connection the person just signed in
		return doc
	first = not frappe.db.exists("Life Mail Account", {"user": user})
	return frappe.get_doc({"doctype": "Life Mail Account", "space": conn.space, "user": user, "provider": provider, "address": conn.mailbox,
		"label": conn.label or conn.mailbox, "connection": conn.name, "is_default": int(first), "active": conn.active}).insert(ignore_permissions=True)  # system: as above


def accounts_for(user: str, space: str | None = None, account: str | None = None) -> list:
	"""The switched-on inboxes of this person (default one first). Another person's inbox is refused, never skipped: asking for it by name is an error."""
	filters = {"user": user, "active": 1, **({"space": space} if space else {})}
	rows = frappe.get_all("Life Mail Account", filters=filters, fields=["name", "address", "label", "provider", "connection", "is_default", "space", "user"],
		order_by="is_default desc, creation asc")  # system: this person's own inboxes; `user` is in the filter
	if account:
		rows = [r for r in rows if account in (r.name, r.address, r.label)]
		if not rows:
			frappe.throw(_("{0} is not one of your inboxes.").format(account), frappe.PermissionError, title=_("Not your inbox"))
	return rows


def no_inbox(user: str, space: str | None = None):
	"""Say which case it is when there is no inbox to search (issue 101): none connected, connected but switched off, or a sign-in left unfinished."""
	filters = {"system": ["in", ["gmail", "microsoft"]], "connected_by": user, **({"space": space} if space else {})}
	rows = frappe.get_all("Life Connection", filters=filters, fields=["mailbox", "active"])  # system: the person's own connections, named in the filter
	if any(r.mailbox and not r.active for r in rows):
		frappe.throw(_("Gmail is connected but switched off. Switch it on in Brain › Sources."), title=_("Gmail is switched off"))
	if any(not r.mailbox for r in rows):
		frappe.throw(_("Gmail sign-in wasn't finished. Connect again in Brain › Sources."), title=_("Gmail sign-in not finished"))
	frappe.throw(_("No inbox is connected. Connect Gmail in Brain › Sources."), title=_("No inbox connected"))


def label_of(account) -> str:
	return account.label or account.address


def google_for(account):
	"""The client that changes things for an inbox (tests and the acceptance site put their own in `frappe.flags.lifeos_google`)."""
	fake = (getattr(frappe.flags, "lifeos_google", None) or {}).get(account.address)
	if fake:
		return fake
	if frappe.conf.get("lifeos_fake_gmail") or (account.provider == "microsoft" and frappe.conf.get("lifeos_fake_microsoft")):
		from lifeos.mail import fake as site

		return site.google()
	if account.provider == "microsoft":
		from lifeos.mail import microsoft

		return microsoft.GraphActs(microsoft.headers_for(frappe.get_doc("Life Connection", account.connection)))
	from lifeos.mail import gmail, google

	return google.GoogleClient(gmail.headers_for(frappe.get_doc("Life Connection", account.connection)))


def client_for(account):
	"""The read client of an inbox. Tests put their own in `frappe.flags.lifeos_gmail` or `lifeos_microsoft` (by address); the acceptance site has fakes."""
	microsoft = account.provider == "microsoft"
	fake = (getattr(frappe.flags, "lifeos_microsoft" if microsoft else "lifeos_gmail", None) or {}).get(account.address)
	if fake:
		return fake
	if frappe.conf.get("lifeos_fake_microsoft" if microsoft else "lifeos_fake_gmail"):
		from lifeos.mail import fake as site

		return site.graph() if microsoft else site.gmail()
	if not account.connection:
		frappe.throw(_("This inbox is not connected."), title=_("Inbox not connected"))
	conn = frappe.get_doc("Life Connection", account.connection)
	if microsoft:
		from lifeos.mail import microsoft as ms

		return ms.client_for(conn)
	from lifeos.mail import gmail

	return gmail.client_for(conn)


def adapter(account):
	path = PROVIDERS.get(account.provider)
	if not path:
		frappe.throw(_("{0} inboxes are not supported yet.").format(account.provider), title=_("Provider not supported"))
	return frappe.get_attr(path)(account, client_for(account))


def _clean(fields) -> dict:
	fields = fields if isinstance(fields, dict) else {}
	out = {k: fields[k] for k in FIELDS if fields.get(k) not in (None, "", [], False)}
	if not out:
		frappe.throw(_("Say what to look for: words, a sender, a subject, an attachment or a date."), title=_("Nothing to search for"))
	return out


def search(user: str, space: str, fields: dict, account: str | None = None, max_results: int = 10, agent: str | None = None, cost: float = 0.0) -> dict:
	"""Search one inbox, or all of this person's inboxes when none is named, and merge the answers newest first, each marked with its inbox.
	One log record for the search. An inbox that fails is named in `errors`; the others still answer."""
	fields = _clean(fields)
	max_results = max(1, min(int(max_results or 10), MAX_HITS))
	accounts = accounts_for(user, space, account)
	if not accounts:
		no_inbox(user)
	hits, errors, queries = [], [], []
	for row in accounts:
		doc = frappe._dict(row)
		try:
			ad = adapter(doc)
			queries.append(f"{label_of(doc)}: {ad.query(fields)}")
			for h in ad.search(fields, max_results):
				hits.append({**h, "account": doc.name, "inbox": label_of(doc), "address": doc.address})
		except Exception as e:
			if isinstance(e, frappe.PermissionError):
				raise
			from lifeos.mail.gmail import scrub

			errors.append({"inbox": label_of(doc), "error": scrub(e)[:140]})
	hits.sort(key=lambda h: h.get("at") or 0, reverse=True)
	hits = hits[:max_results]
	frappe.get_doc({"doctype": "Life Mail Search", "space": space, "user": user, "agent": agent, "account": accounts[0].name if len(accounts) == 1 else None,
		"account_label": label_of(frappe._dict(accounts[0])) if len(accounts) == 1 else _("All {0} inboxes").format(len(accounts)),
		"query": "\n".join(queries)[:600], "results": len(hits), "cost": cost, "searched_on": now_datetime()}).insert(ignore_permissions=True)  # system: the person's own log
	return {"hits": hits, "errors": errors, "searched": [label_of(frappe._dict(a)) for a in accounts]}


def _find(user: str, space: str, thread_id: str, account: str | None):
	"""The inbox a thread is in: the one named, or the first of this person's that has it."""
	last = None
	for row in accounts_for(user, space, account):
		doc = frappe._dict(row)
		try:
			return doc, adapter(doc).get_thread(thread_id)
		except frappe.PermissionError:
			raise
		except Exception as e:
			last = e
	if last:
		raise last
	no_inbox(user)


def get_thread(user: str, space: str, thread_id: str, account: str | None = None) -> dict:
	doc, thread = _find(user, space, thread_id, account)
	return {**thread, "account": doc.name, "inbox": label_of(doc), "address": doc.address}


def get_attachment(user: str, space: str, message_id: str, attachment_id: str, for_item: str, account: str | None = None, filename: str | None = None) -> dict:
	"""Save an attachment as a File of the item that asked for it. The same bytes are stored once (#7): asking again links the same file."""
	from lifeos import permissions
	from lifeos.library import files

	item = permissions.get_doc_checked("Life Inbox Item", for_item, "write")
	if item.space != space:
		frappe.throw(_("That item is in another space."), title=_("Item is in another space"))
	rows = accounts_for(user, space, account)
	if len(rows) != 1:
		frappe.throw(_("Say which inbox the attachment is in."), title=_("Inbox not named"))
	doc = frappe._dict(rows[0])
	content = adapter(doc).get_attachment(message_id, attachment_id)
	if not content:
		frappe.throw(_("That attachment is empty."), title=_("Attachment is empty"))
	digest = files.sha256(files.stored_bytes(filename or "attachment", content))
	name = files.same_on_record("Life Inbox Item", item.name, digest)
	if not name:
		name = frappe.get_doc({"doctype": "File", "file_name": (filename or f"attachment-{attachment_id[:8]}")[:140], "attached_to_doctype": "Life Inbox Item",
			"attached_to_name": item.name, "is_private": 1, "content": content}).insert(ignore_permissions=True).name  # system: the item was write-checked above
	f = frappe.db.get_value("File", name, ["name", "file_name", "file_url", "file_size"], as_dict=True)
	return {"file": f.name, "file_name": f.file_name, "file_url": f.file_url, "size": f.file_size, "item": item.name, "sha256": digest}


def thread_text(thread: dict) -> str:
	out = []
	for m in thread.get("messages") or []:
		out.append(f"From: {m['from']}\nDate: {m['date']}\n\n{m['text']}")
	return ("\n\n---\n\n".join(out))[:TEXT_CHARS]


def file_thread(user: str, space: str, thread_id: str, area: str | None = None, account: str | None = None) -> dict:
	"""After the owner says so: the thread becomes a Brain item with a link back to it in Gmail; the Brain summarises it. Filing it again is the same item."""
	from lifeos.api import inbox
	from frappe.utils import sanitize_html

	doc, thread = _find(user, space, thread_id, account)
	done = inbox.create_item(space=space, source_type="Email", source_system=doc.provider, external_id=thread_id, title=sanitize_html(thread["subject"])[:140],
		raw_text=sanitize_html(thread_text(thread)), source_url=thread["link"], area=area or None)
	return {"item": done["name"], "created": bool(done.get("created", True)), "title": thread["subject"], "link": thread["link"]}
