"""Email-in (issue 32): the owner makes a mailbox, Frappe reads it by IMAP as an incoming Email Account, and each new email from an
allowed sender becomes a capture (source Email). Settings name the account (`email_in_account`) and the allowed senders
(`email_in_senders`, one address per line). Anything from anyone else is ignored and logged. The mailbox password is entered by
the owner on the server, never here.

The first line typed above the forwarded message is the capture's instruction; the forwarded message is its text; the
subject, without "Fwd:", is its title. The Message-ID is the `external_id`, so the same email twice is one capture."""
import re
from email.utils import parseaddr

import frappe
from frappe import _
from frappe.utils import strip_html, to_markdown

SYSTEM = "email"
FORWARD_MARK = re.compile(r"^\W*(-{2,}\s*forwarded message\s*-{2,}|begin forwarded message:?|-{2,}\s*original message\s*-{2,})\W*$", re.I)
PREFIX = re.compile(r"^\s*((fwd?|re)\s*:\s*)+", re.I)
INSTRUCTION_CAP = 500


def settings():
	return frappe.get_cached_doc("Life Settings")


def address() -> str | None:
	"""The mailbox people forward to: the incoming Email Account chosen in Settings, if it is on."""
	account = settings().get("email_in_account")
	if not account:
		return None
	row = frappe.db.get_value("Email Account", account, ["email_id", "enable_incoming"], as_dict=True)
	return row.email_id if row and row.enable_incoming else None


def allowed_senders() -> list[str]:
	return [a.strip().lower() for a in re.split(r"[\s,;]+", settings().get("email_in_senders") or "") if a.strip()]


def info() -> dict:
	"""For Settings > Sources: where to forward, who may, and a line on how."""
	mine = address()
	return {"address": mine, "senders": allowed_senders(), "configured": bool(mine),
		"how_to": _("Forward an email to this address from one of your own addresses. A line you type above the forwarded message tells the Brain what to do with it.")}


def split_forward(text: str) -> tuple[str, str]:
	"""(what was typed above the forwarded message, the forwarded message). Without a forward marker nothing is above."""
	lines = (text or "").replace("\r", "").split("\n")
	for i, line in enumerate(lines):
		if FORWARD_MARK.match(line.strip()):
			return "\n".join(lines[:i]).strip(), "\n".join(lines[i + 1:]).strip()
	return "", (text or "").strip()


def plain(content: str) -> str:
	content = content or ""
	return (to_markdown(content) if "<" in content else content).strip() if content else ""


def instruction_of(above: str) -> str | None:
	for line in above.split("\n"):
		line = strip_html(line).strip()
		if line:
			return line[:INSTRUCTION_CAP]
	return None


def communication_received(doc, method=None):
	"""Communication on_update: when a mail has been read with its attachments, file it. Never stops Frappe reading mail."""
	if doc.communication_medium != "Email" or doc.sent_or_received != "Received" or not doc.flags.in_receive:
		return
	if not isinstance(doc.get("_attachments"), list):  # the first write, before the files are kept; the save after it comes here again
		return
	mine = frappe.db.get_value("Email Account", doc.email_account, "name") if doc.email_account else None
	if not mine or mine != settings().get("email_in_account"):
		return
	try:
		file_email(doc)
	except Exception:
		frappe.log_error(title="Life OS email-in failed", message=f"{doc.name}: {frappe.get_traceback()[-600:]}")


def file_email(comm) -> str | None:
	"""Make the capture of one received email. Returns its name, or None when the sender is not allowed or it was filed before."""
	from lifeos.api import inbox

	sender = parseaddr(comm.sender or "")[1].lower()
	if sender not in allowed_senders():
		frappe.log_error(title="Life OS email-in: sender not allowed", message=f"Ignored an email from {sender or 'no address'} ({comm.name}).")
		return None
	space = settings().get("default_space")
	if not space:
		frappe.log_error(title="Life OS email-in: no default space", message="Choose a default space in Settings so email can be filed.")
		return None
	message_id = (comm.message_id or comm.name).strip().strip("<>").strip()[:255]  # without the angle brackets, which Frappe would take for a tag and blank
	if frappe.db.exists("Life Inbox Item", {"space": space, "source_system": SYSTEM, "external_id": message_id}):
		return None
	above, forwarded = split_forward(plain(comm.content))
	title = PREFIX.sub("", comm.subject or "").strip() or _("Email")
	done = inbox.create_item(space=space, title=title, source_type="Email", source_system=SYSTEM, external_id=message_id,
		raw_text=forwarded, instruction=instruction_of(above))
	keep_files(comm, done["name"])
	return done["name"]


def keep_files(comm, item: str):
	"""The email's attachments, as private files of the capture."""
	from lifeos import files

	for f in frappe.get_all("File",  # system: the mail was read by Frappe's job, not a signed-in person filters={"attached_to_doctype": "Communication", "attached_to_name": comm.name, "is_folder": 0},
			fields=["name", "file_name"]):
		content = files.read(frappe.get_doc("File", f.name))
		if content:
			frappe.get_doc({"doctype": "File", "file_name": f.file_name, "attached_to_doctype": "Life Inbox Item", "attached_to_name": item,
				"is_private": 1, "content": content}).insert(ignore_permissions=True)
