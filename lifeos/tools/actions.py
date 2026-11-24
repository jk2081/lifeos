"""What every Ask tool that writes shares (issue 107): who is calling, the log, Undo and the agent's switches.

A tool is a plain function with typed parameters and a docstring a model can read. Ask calls it for the owner, an MCP agent calls it as a whitelisted
method (`lifeos.api.tools`), and a later engine (Frappe Flow) can register it under `flow_tools` with `@tool` without any change to the function.

A tool that writes is two functions: the public one (`pages.create`), which runs `write`, and `_do`, which does the work in a space and returns
`(the line the owner reads, the result, how to undo it)`. `write` decides whether it runs now:

- the owner asked (a person): it runs now and is logged as a `Life Agent Action` with `asked_by: owner`, with the undo token;
- an agent called it: it follows the owner's switch for that agent (`limits`): on its own runs now (`asked_by: agent`), asks you waits in Needs you
  until the owner approves, off is refused.

Plumbing only: a log, a switch, an undo. What to write, and in which words, is the model's judgment.
"""
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from lifeos import permissions
from lifeos.agents import limits

OWNER, AGENT = "owner", "agent"
ASK = "ask"  # the `agent` of a log row the owner's own Ask wrote
# the tool -> (the switch under What it can do, what the owner reads in Needs you)
ABILITY = {
	"mail.save_attachment": ("save_files", "Save an attachment"),
	"pages.create": ("write_pages", "Create a page"),
	"pages.update": ("write_pages", "Change a page"),
	"people.add": ("write_pages", "Add a person"),
	"notes.save": ("write_pages", "Save a note"),
}


def run_for(tool: str):
	"""The `_do` of a tool by name (for an approved request)."""
	from lifeos.tools import mail, notes, pages, people, work

	return {"mail.save_attachment": mail._save_attachment, "pages.create": pages._create, "pages.update": pages._update, "people.add": people._add,
		"notes.save": notes._save, "tasks.add": work._add_task, "events.add": work._add_event}[tool]


def agent_key(space: str, source_system: str | None) -> str:
	key = (source_system or "").strip().lower()
	if not key:
		frappe.throw(_("An agent names itself with source_system."), title=_("Agent not named"))
	return key


def person_of_space(space: str) -> str:
	"""The person an agent reads for in a space: its owner."""
	from lifeos.agents import acts

	return acts.person_of(space)


def check_read(space: str, source_system: str | None = None) -> None:
	"""A read tool: a person reads their own inboxes and records; an agent only while its Read email switch is not off."""
	if permissions.is_agent():
		from lifeos.agents import acts

		acts._need_switch(space, agent_key(space, source_system), "mail.search")


def write(tool: str, space: str | None, params: dict, source_system: str | None = None, request: str | None = None) -> dict:
	"""Run a tool that writes, or hold it for the owner. Returns the tool's result with `done` (a line), `undo` (the log row to undo it with) and `action`;
	or {waiting: <log row>, title} when an agent's request waits in Needs you."""
	space = permissions.resolve_space(space, write=True)
	ability, label = ABILITY.get(tool, (None, None))
	title, draft = _describe(tool, params)
	if not permissions.is_agent():
		return _run(tool, space, params, ASK, OWNER, request, title, draft)
	if not ability:  # a task or an event the owner asked Ask for: agents have their own ways to make these
		frappe.throw(_("Only the owner asks for this."), frappe.PermissionError, title=_("Owner only"))
	agent = agent_key(space, source_system)
	mode = limits.abilities(limits.config(space, agent))[ability]
	if mode == limits.OFF:
		frappe.throw(_("The owner has switched “{0}” off for this agent.").format(dict(limits.ACTIONS)[ability]), frappe.PermissionError, title=_("Switched off"))
	if mode == limits.ASK:
		row = frappe.get_doc({"doctype": "Life Agent Action", "space": space, "agent": agent, "action": ability, "title": f"{label}: {title}"[:200], "draft": draft[:5000],
			"status": "Waiting", "asked_by": AGENT, "params": json.dumps({"tool": tool, **params}, default=str), "happened_on": now_datetime(),
			"delivered": 1}).insert(ignore_permissions=True)  # system: the agent's own log; the space write check is above
		return {"waiting": row.name, "title": title}
	return _run(tool, space, params, agent, AGENT, request, title, draft)


def _describe(tool: str, p: dict) -> tuple[str, str]:
	"""(a short name for the request, the draft the owner reads before approving)."""
	name = p.get("title") or p.get("name") or p.get("page") or p.get("attachment_id") or ""
	draft = "\n".join(f"{k}: {str(v)[:300]}" for k, v in p.items() if v not in (None, "", []))
	return str(name)[:120], draft


def _run(tool: str, space: str, params: dict, agent: str, asked_by: str, request: str | None, title: str, draft: str, existing: str | None = None) -> dict:
	line, result, undo = run_for(tool)(space, **params)
	values = {"status": "Done", "result": json.dumps({"line": line, **{k: v for k, v in result.items() if isinstance(v, (str, int, float, bool))}}, default=str)[:900],
		"undo": json.dumps(undo) if undo else None, "happened_on": now_datetime(), "error": None, "title": line[:200]}
	if existing:
		frappe.db.set_value("Life Agent Action", existing, values)
		name = existing
	else:
		name = frappe.get_doc({"doctype": "Life Agent Action", "space": space, "agent": agent, "action": ABILITY.get(tool, (tool,))[0], "draft": draft[:5000], "asked_by": asked_by,
			"request": (request or "")[:500] or None, "params": json.dumps({"tool": tool, **params}, default=str)[:60000], "delivered": 1, **values}).insert(ignore_permissions=True).name  # system: the log of what was done; the space write check is in `write`
	return {**result, "done": line, "undo": name if undo else None, "action": name}


def approved(name: str) -> dict:
	"""The owner approved a request an agent held: run it as the owner and log what it did (called by `acts.execute`)."""
	row = frappe.get_doc("Life Agent Action", name)
	p = json.loads(row.params)
	tool = p.pop("tool")
	try:
		out = _run(tool, row.space, p, row.agent, AGENT, None, "", "", existing=row.name)
	except frappe.PermissionError:
		raise
	except Exception as e:  # noqa: BLE001 - the log says why, without a stack
		from lifeos.mail.gmail import scrub

		reason = scrub(e)[:300]
		frappe.db.set_value("Life Agent Action", row.name, {"status": "Failed", "error": reason, "happened_on": now_datetime()})
		return {"status": "failed", "error": reason}
	return {"status": "done", "result": out, "undoable": int(bool(out.get("undo")))}


# ---------------------------------------------------------------- undo

def undo(action: str) -> dict:
	"""Take back what a logged tool did. People only: an agent never undoes (or deletes). Returns {undone: <action>, removed: [what went]}."""
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Agents cannot undo."), frappe.PermissionError, title=_("Agents cannot undo"))
	row = frappe.db.get_value("Life Agent Action", action, ["name", "space", "status", "undo", "undone", "action"], as_dict=True)
	if not row:
		frappe.throw(_("That is not something Life OS did."), frappe.DoesNotExistError, title=_("Action not found"))
	permissions.require_space(row.space, write=True)
	if row.status != "Done" or not row.undo or row.undone:
		frappe.throw(_("That cannot be undone."), title=_("Nothing to undo"))
	data = json.loads(row.undo)
	removed = []
	for doctype, name, field in data.get("clear") or []:  # a link to what goes is taken off first
		if frappe.db.exists(doctype, name):
			permissions.get_doc_checked(doctype, name, "write")
			frappe.db.set_value(doctype, name, field, None)
	for page, item in data.get("unsource") or []:  # a page no longer cites the email this call filed
		if frappe.db.exists("Life Note", page):
			doc = permissions.get_doc_checked("Life Note", page, "write")
			doc.set("sources", [r for r in doc.sources if (r.source_doctype, r.source_name) != ("Life Inbox Item", item)])
			doc.save()
	for doctype, name in data.get("delete") or []:
		if frappe.db.exists(doctype, name):
			permissions.get_doc_checked(doctype, name, "delete")
			if doctype == "Life Note":  # a page this tool made has only its own history ("Created", and any change made since): it goes with the page
				frappe.db.delete("Life Wiki Change", {"note": name})
			frappe.delete_doc(doctype, name)
			removed.append(name)
	for event in data.get("events") or []:  # an event made in Life OS goes the way calendar.delete_event takes it
		from lifeos.api import calendar

		calendar.delete_event(event)
		removed.append(event)
	if data.get("restore_change"):
		from lifeos.api import wiki

		got = wiki.undo(data["restore_change"], 1)
		removed.append(got.get("name") or data["restore_change"])
	if data.get("restore_text") is not None:
		doc = permissions.get_doc_checked("Life Note", data["page"], "write")
		doc.content_md = data["restore_text"]
		doc.save()
	frappe.db.set_value("Life Agent Action", row.name, "undone", 1)
	return {"undone": row.name, "removed": removed}


def area_of(space: str, area: str | None, part: str | None = None) -> str | None:
	"""The Life Area an area (and a part of it) names: by id or by its name. A part is looked for under the area."""
	def find(name, parent=None):
		if not name:
			return None
		flt = {"space": space, **({"parent_area": parent} if parent else {})}
		return frappe.db.get_value("Life Area", {**flt, "name": name}) or frappe.db.get_value("Life Area", {**flt, "area_name": name}, order_by="creation asc")

	top = find(area)
	if area and not top:
		frappe.throw(_("There is no area called {0} in this space.").format(area), frappe.DoesNotExistError, title=_("Area not found"))
	if part:
		got = find(part, top) if top else find(part)
		if not got:
			frappe.throw(_("There is no part called {0} under {1}.").format(part, area) if area else _("There is no part called {0}.").format(part), frappe.DoesNotExistError,
				title=_("Part not found"))
		return got
	return top
