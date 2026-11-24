"""Ask tools for mail (issue 107): read every thread of a period, and save an attachment.

`list_threads` reads (a person's own inboxes, or an agent's when its Read email switch is on). `save_attachment` writes: through `actions.write`, so it
is logged with an undo token, and an agent's call follows the owner's "Save files" switch.
"""
import frappe
from frappe import _
from frappe.utils import add_days, getdate

from lifeos import mail, permissions
from lifeos.mail.gmail import GmailError, scrub
from lifeos.tools import actions

PAGE_SIZE = mail.PAGE_SIZE
UNDO_ORDER = ["File", "Life Vault Document", "Life Inbox Item"]  # what points at another thing goes first


def list_threads(after: str, before: str, query: str | None = None, page_token: str | None = None, space: str | None = None, account: str | None = None,
		source_system: str | None = None) -> dict:
	"""Every email thread from the day `after` to the day `before`, both included (YYYY-MM-DD), 25 to a page, newest first. Use it for any question about a
	period: it does not stop at the newest few. `query` narrows by words. When the answer has a `next_page_token`, call again with it for the next page;
	`pages` says how many pages the period holds. Reads only the inboxes of the person asking."""
	space = permissions.resolve_space(space)
	actions.check_read(space, source_system)
	lo, hi = getdate(after), getdate(before)
	if hi < lo:
		frappe.throw(_("The end of the period is before its start."), title=_("Period ends before it starts"))
	fields = {"after": str(lo), "before": str(add_days(hi, 1)), **({"text": query} if (query or "").strip() else {})}  # the provider's "before" leaves its day out
	user = frappe.session.user if not permissions.is_agent() else actions.person_of_space(space)
	try:
		got = mail.list_page(user, space, fields, page_token, account)
	except GmailError as e:
		frappe.throw(scrub(e), title=_("The inbox could not be read"))
	rows = [{k: h.get(k) for k in ("thread_id", "subject", "from", "date", "snippet", "inbox", "account", "link", "messages")} for h in got["threads"]]
	return {"threads": rows, "next_page_token": got["next_page_token"], "pages": max(1, -(-got["estimate"] // PAGE_SIZE)) if got["estimate"] else 1,
		"from": str(lo), "to": str(hi), "errors": got["errors"]}


def save_attachment(thread_id: str, attachment_id: str, area: str | None = None, part: str | None = None, page: str | None = None, vault_type: str | None = None,
		account: str | None = None, space: str | None = None, source_system: str | None = None) -> dict:
	"""Download one attachment of an email and save it in Life OS: under the `area` or `part` (names), attached to `page` (a page's name) when one is given.
	The email it came from is kept with it. For an ID card, a statement or another document that belongs in the Vault, pass `vault_type` (ID, Travel,
	Insurance, Property, Tax, Medical or Other): it is saved as a Vault document. Saving the same attachment twice keeps one file. Returns what was done,
	with an `undo` token that removes what this call made."""
	return actions.write("mail.save_attachment", space, {"thread_id": thread_id, "attachment_id": attachment_id, "area": area, "part": part, "page": page,
		"vault_type": vault_type, "account": account}, source_system)


def _save_attachment(space: str, thread_id: str, attachment_id: str, area: str | None = None, part: str | None = None, page: str | None = None,
		vault_type: str | None = None, account: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.library import files

	user = frappe.session.user if not permissions.is_agent() else actions.person_of_space(space)
	where = actions.area_of(space, area, part)
	target = permissions.get_doc_checked("Life Note", page, "write") if page else None
	if target and target.space != space:
		frappe.throw(_("That page is in another space."), title=_("Page is in another space"))
	if vault_type and vault_type not in ("ID", "Travel", "Insurance", "Property", "Tax", "Medical", "Other"):
		frappe.throw(_("A Vault type is ID, Travel, Insurance, Property, Tax, Medical or Other."), title=_("Vault type not understood"))
	inbox, thread = mail._find(user, space, thread_id, account)
	message_id, att = mail.attachment_of(thread, attachment_id)
	content = mail.adapter(inbox).get_attachment(message_id, attachment_id)
	if not content:
		frappe.throw(_("That attachment is empty."), title=_("Attachment is empty"))
	name = (att.get("filename") or f"attachment-{attachment_id[:8]}")[:140]
	made = []  # what this call made, for Undo
	filed = mail.file_thread(user, space, thread_id, where, inbox.name)  # the email it came from: one item, the same one when filed again
	item = filed["item"]
	if filed["created"]:
		made.append(("Life Inbox Item", item))
	if vault_type:
		doc = frappe.get_doc({"doctype": "Life Vault Document", "space": space, "title": name.rsplit(".", 1)[0][:140], "doc_type": vault_type, "area": where,
			"inbox_item": item}).insert()
		made.append(("Life Vault Document", doc.name))
		holder_doc, holder = "Life Vault Document", doc.name
		place = _("the Vault")
	else:
		holder_doc, holder = ("Life Note", target.name) if target else ("Life Inbox Item", item)
		place = target.title if target else (frappe.db.get_value("Life Area", where, "area_name") if where else _("Life OS"))
	digest = files.sha256(files.stored_bytes(name, content))
	file = files.same_on_record(holder_doc, holder, digest)
	if not file:
		file = frappe.get_doc({"doctype": "File", "file_name": name, "attached_to_doctype": holder_doc, "attached_to_name": holder, "is_private": 1, "content": content}).insert().name
		made.append(("File", file))
	if vault_type:
		frappe.db.set_value("Life Vault Document", holder, "file", frappe.db.get_value("File", file, "file_url"))
	unsource = []
	if target and (("Life Inbox Item", item) not in [(s.source_doctype, s.source_name) for s in target.sources]):
		target.append("sources", {"source_doctype": "Life Inbox Item", "source_name": item})
		target.save()
		unsource.append([target.name, item])
	f = frappe.db.get_value("File", file, ["file_name", "file_url", "file_size"], as_dict=True)
	return (_("Saved {0} to {1}").format(f.file_name, place),
		{"file": file, "file_name": f.file_name, "file_url": f.file_url, "size": f.file_size, "item": item, "page": target.name if target else None,
			"vault_document": holder if vault_type else None, "email": thread.get("link")},
		{"unsource": unsource, "delete": [[dt, n] for dt, n in sorted(made, key=lambda m: UNDO_ORDER.index(m[0]))]} if made or unsource else None)
