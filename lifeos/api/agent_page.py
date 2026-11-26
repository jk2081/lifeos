"""Brain > Sources > an agent (issue 85): what it waits for, knows, can do, may read, has scheduled and did. People only; only the owner changes anything."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.brain import agent_page as pages
from lifeos.brain import source_page


def _owner(space: str | None, key: str, write: bool = True):
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("An agent's page is for people."), frappe.PermissionError, title=_("Only people open an agent's page"))
	space = permissions.resolve_space(space, write=write)
	key = (key or "").strip().lower()
	if write and not permissions.is_admin():
		frappe.throw(_("Only the owner changes what an agent may do."), frappe.PermissionError, title=_("Only the owner changes an agent"))
	if not pages.is_agent_key(space, key):
		frappe.throw(_("There is no agent called {0}.").format(key), frappe.DoesNotExistError, title=_("Agent not found"))
	return space, key


@frappe.whitelist(methods=["GET"])
def get(key: str, space: str | None = None):
	"""The agent's sections: `waiting` (with the draft), `facts`, `can` (a mode for each action), `areas` and `vault` (what it may read), `jobs`, `did` (this week, with cost) and
	`changes` (how many of the owner's changes wait for the connector or failed). Each fact, job and switch carries its pending `change`."""
	space, key = _owner(space, key, write=False)
	return {**pages.sections(space, key), "can_edit": permissions.is_admin()}


@frappe.whitelist(methods=["POST"])
def edit_fact(key: str, fact: str, text: str, space: str | None = None):
	"""Change a fact in the agent's memory: it shows as waiting until the connector confirms it."""
	space, key = _owner(space, key)
	return pages.edit_fact(space, key, fact, text)


@frappe.whitelist(methods=["POST"])
def delete_fact(key: str, fact: str, space: str | None = None):
	"""Delete a fact from the agent's memory: it shows as waiting until the connector confirms it."""
	space, key = _owner(space, key)
	return pages.delete_fact(space, key, fact)


@frappe.whitelist(methods=["POST"])
def pause_job(key: str, job: str, paused: int = 1, space: str | None = None):
	"""Pause (or resume) one of the agent's scheduled jobs."""
	space, key = _owner(space, key)
	return pages.pause_job(space, key, job, bool(int(paused)))


@frappe.whitelist(methods=["POST"])
def set_ability(key: str, action: str, mode: str, space: str | None = None):
	"""One switch under What it can do: on its own (auto), asks you (ask) or off. Pay can only be off."""
	space, key = _owner(space, key)
	return pages.set_ability(space, key, action, mode)


@frappe.whitelist(methods=["POST"])
def set_area(key: str, area: str, on: int = 1, space: str | None = None):
	"""One switch under What it may read: an area the agent may or may not read. Life OS leaves it out of everything the agent reads."""
	space, key = _owner(space, key)
	return pages.set_area(space, key, area, bool(int(on)))


@frappe.whitelist(methods=["POST"])
def rename(key: str, name: str, space: str | None = None):
	"""The name the agent is shown under (empty goes back to Your assistant)."""
	space, key = _owner(space, key)
	return pages.rename(space, key, name)


@frappe.whitelist(methods=["POST"])
def set_owner_runs_now(key: str, on: int = 1, space: str | None = None):
	"""The safety switch: your requests through this agent run at once (on, the default) or wait in Needs you like the agent's own idea (off)."""
	space, key = _owner(space, key)
	return pages.set_owner_runs_now(space, key, bool(int(on)))


@frappe.whitelist(methods=["POST"])
def decide(request: str, decision: str, space: str | None = None):
	"""Approve (approve) or say no (no) to something an agent waits to do. The same list as Brain > Needs you."""
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("An agent cannot approve its own request."), frappe.PermissionError, title=_("Only people decide"))
	space = permissions.resolve_space(space, write=True)
	return pages.decide(space, request, decision, frappe.session.user)


@frappe.whitelist(methods=["POST"])
def undo(request: str, space: str | None = None):
	"""Take back something the agent did in Google (a draft, an archive, a label, an event it made) where Google allows it."""
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("An agent cannot undo its own acts."), frappe.PermissionError, title=_("Only people undo"))
	space = permissions.resolve_space(space, write=True)
	return pages.undo(space, request)
