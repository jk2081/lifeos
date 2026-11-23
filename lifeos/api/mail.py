"""Live mail search (issue 86): a person's inboxes searched when asked, never copied into Life OS. `search`, `get_thread` and `get_attachment` are the tools
Ask is offered and agents use over the API or MCP; `file` makes one thread a Brain item once the owner says so. A person reaches only their own inboxes; an
agent reaches the inboxes of the person it acts for, when the owner's "Read email" switch for it is not off."""
import frappe
from frappe import _

from lifeos import mail, permissions
from lifeos.agents import acts
from lifeos.api.utils import parse


def _agent_key(space: str, source_system: str | None) -> str:
	key = (source_system or "").strip().lower()
	if not key:
		frappe.throw(_("An agent names itself with source_system."), title=_("Agent not named"))
	return key


def _for(tool: str, params: dict, space: str | None, source_system: str | None):
	"""Run a read tool as the agent (through its switches and areas) or as the signed-in person (their own inboxes)."""
	permissions.require_login()
	space = permissions.resolve_space(space)
	if permissions.is_agent():
		return acts.read(space, _agent_key(space, source_system), tool, params)
	return None, space


@frappe.whitelist(methods=["POST"])
def search(fields: str | dict | None = None, account: str | None = None, max: int = 10, space: str | None = None, source_system: str | None = None):
	"""Search the inbox live. `fields`: text, from, to, subject, has_attachment, filename, after, before (2014-04-05) and raw (the provider's own query);
	`account` one inbox (its name, address or label), or all of this person's. Returns hits newest first: subject, from, date, snippet, thread_id and inbox."""
	got = _for("mail.search", {"fields": parse(fields, {}), "account": account, "max": max}, space, source_system)
	if isinstance(got, dict):
		return got
	return mail.search(frappe.session.user, got[1], parse(fields, {}), account, max)


@frappe.whitelist(methods=["GET"])
def get_thread(thread_id: str, account: str | None = None, space: str | None = None, source_system: str | None = None):
	"""One thread: each message's plain text and its attachments (attachment_id, filename, size)."""
	got = _for("mail.get_thread", {"thread_id": thread_id, "account": account}, space, source_system)
	if isinstance(got, dict):
		return got
	return mail.get_thread(frappe.session.user, got[1], thread_id, account)


@frappe.whitelist(methods=["POST"])
def get_attachment(message_id: str, attachment_id: str, for_item: str, account: str | None = None, filename: str | None = None, space: str | None = None,
		source_system: str | None = None):
	"""Save an attachment as a File of the item that asked for it, stored once; asking again links the same file."""
	got = _for("mail.get_attachment", {"message_id": message_id, "attachment_id": attachment_id, "for_item": for_item, "account": account, "filename": filename}, space, source_system)
	if isinstance(got, dict):
		return got
	return mail.get_attachment(frappe.session.user, got[1], message_id, attachment_id, for_item, account, filename)


@frappe.whitelist(methods=["POST"])
def file(thread_id: str, area: str | None = None, account: str | None = None, space: str | None = None):
	"""The owner says keep it: the thread becomes a Brain item with a link back to Gmail. People only; filing a thread again is the same item."""
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Only the owner files an email. An agent asks, and the owner says yes."), frappe.PermissionError, title=_("Only people file email"))
	space = permissions.resolve_space(space, write=True)
	return mail.file_thread(frappe.session.user, space, thread_id, area, account)
