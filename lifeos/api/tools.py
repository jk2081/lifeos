"""The Ask tools as methods (issue 107), for agents over MCP and for any other caller. Each is the plain function in `lifeos.tools`, unchanged: Ask calls
the same functions, and so can Frappe Flow. A person's call runs at once and is logged with an undo token; an agent's call follows the owner's switches
for it ("On its own", "Asks you", "Off"), so a write it may not do on its own waits in Needs you. An agent names itself with `source_system`."""
import frappe

from lifeos.api.utils import parse
from lifeos.tools import actions, digests, mail, notes, pages, people, work


@frappe.whitelist(methods=["GET"])
def mail_list_threads(after: str, before: str, query: str | None = None, page_token: str | None = None, account: str | None = None, space: str | None = None,
		source_system: str | None = None):
	"""Every email thread from `after` to `before` (YYYY-MM-DD, both included), 25 a page; pass `next_page_token` back for the next page."""
	return mail.list_threads(after, before, query, page_token, space, account, source_system)


@frappe.whitelist(methods=["GET"])
def digests_read(start: str, end: str, space: str | None = None, source_system: str | None = None):
	"""The daily email digests Life OS wrote for the days `start` to `end`, and the days that have none."""
	return digests.read(start, end, space, source_system)


@frappe.whitelist(methods=["POST"])
def mail_save_attachment(thread_id: str, attachment_id: str, area: str | None = None, part: str | None = None, page: str | None = None, vault_type: str | None = None,
		account: str | None = None, space: str | None = None, source_system: str | None = None, asked_by: str = "agent", owner_message: str | None = None):
	"""Save one attachment of an email as a file under an area or part, attached to a page when one is given; returns an undo token."""
	return mail.save_attachment(thread_id, attachment_id, area, part, page, vault_type, account, space, source_system, asked_by, owner_message)


@frappe.whitelist(methods=["POST"])
def pages_create(title: str, area: str, part: str | None = None, kind: str | None = None, body: str | None = None, sources: str | list | None = None,
		summary: str | None = None, space: str | None = None, source_system: str | None = None, asked_by: str = "agent", owner_message: str | None = None):
	"""Create a wiki page under an area or part; kind is Prospect, Client, Project, Person or Note."""
	return pages.create(title, area, part, kind, body, parse(sources, None), summary, space, source_system, asked_by, owner_message)


@frappe.whitelist(methods=["POST"])
def pages_update(page: str, body: str | None = None, add_links: str | list | None = None, space: str | None = None, source_system: str | None = None, asked_by: str = "agent", owner_message: str | None = None):
	"""Change a wiki page's text, or add links to it."""
	return pages.update(page, body, parse(add_links, None), space, source_system, asked_by, owner_message)


@frappe.whitelist(methods=["POST"])
def people_add(name: str, email: str | None = None, company: str | None = None, link_to: str | None = None, space: str | None = None,
		source_system: str | None = None, asked_by: str = "agent", owner_message: str | None = None):
	"""Add a person, with their company, linked to a page."""
	return people.add(name, email, company, link_to, space, source_system, asked_by, owner_message)


@frappe.whitelist(methods=["POST"])
def notes_save(title: str, body: str, area: str, part: str | None = None, space: str | None = None, source_system: str | None = None, asked_by: str = "agent", owner_message: str | None = None):
	"""Save a summary or an answer as a note under an area or part."""
	return notes.save(title, body, area, part, space, source_system, asked_by, owner_message)


@frappe.whitelist(methods=["POST"])
def tasks_add(title: str, area: str | None = None, part: str | None = None, due_date: str | None = None, person: str | None = None, space: str | None = None,
		source_system: str | None = None, asked_by: str = "agent", owner_message: str | None = None):
	"""Make a task under an area (and a part), with an optional due date (YYYY-MM-DD) and `person` (a name; the task links to them). The owner's request (`asked_by: owner` with `owner_message`) runs at once."""
	return work.add_task(title, area, part, due_date, person, space, source_system, asked_by, owner_message)


@frappe.whitelist(methods=["POST"])
def events_add(title: str, start: str, end: str | None = None, all_day: bool = False, description: str | None = None, space: str | None = None,
		source_system: str | None = None, asked_by: str = "agent", owner_message: str | None = None):
	"""Put an event on Life OS's calendar (`start`, `end`: YYYY-MM-DD or YYYY-MM-DD HH:MM). The owner's request runs at once."""
	return work.add_event(title, start, end, all_day, description, space, source_system, asked_by, owner_message)


@frappe.whitelist(methods=["POST"])
def undo(action: str):
	"""Take back what one of these tools did, by the token it returned. People only."""
	return actions.undo(action)
