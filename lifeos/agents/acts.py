"""What an agent does in Google through Life OS (issue 86): one connection for each person, held here; the agent acts through these tools.

Two kinds of request. `asked_by: owner` (the owner told the agent to do it, and the agent passes the owner's message) runs at once and is logged.
`asked_by: agent` (the agent's own idea) follows the owner's switch for it (`limits`): on its own runs, asks you waits in Needs you until the
owner approves, off is refused. Every act is a `Life Agent Action`: who asked, what was sent, what Google answered and, where Google allows, how
to undo it. There is no delete tool: `TOOLS` is the whole list, and a test reads it.

Plumbing only: switches, a log, a queue. What to suggest, and how to write it, is the agent's judgment.
"""
import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from lifeos import mail
from lifeos.agents import limits
from lifeos.mail.gmail import scrub

OWNER, AGENT = "owner", "agent"
# tool -> (switch under What it can do, what it is called, the fields it needs)
ACTS = {
	"email.draft": ("send_email", "Draft an email", ("to", "subject", "body")),
	"email.send": ("send_email", "Send an email", ("to", "subject", "body")),
	"email.archive": ("send_email", "Archive a thread", ("thread_id",)),
	"email.label": ("send_email", "Label a thread", ("thread_id", "label")),
	"calendar.create": ("change_calendar", "Add an event", ("title", "start", "end")),
	"calendar.move": ("change_calendar", "Move an event", ("event_id", "start", "end")),
	"calendar.respond": ("change_calendar", "Answer an invitation", ("event_id", "response")),
}
READS = {"mail.search": "read_email", "mail.get_thread": "read_email", "mail.get_attachment": "read_email", "calendar.list": "change_calendar"}
TOOLS = [*READS, *ACTS]
OPTIONAL = ("account", "thread_id", "cc", "subject", "attendees", "description", "location", "title")


def person_of(space: str) -> str:
	"""The person an agent acts for in a space: the space's owner. Their inboxes are the ones the agent may use."""
	owner = frappe.db.get_value("Life Space", space, "owner_user")
	if not owner:
		frappe.throw(_("This space has no owner to act for."), title=_("No owner"))
	return owner


def mode_of(space: str, agent: str, tool: str) -> str:
	key = READS.get(tool) or ACTS[tool][0]
	return limits.abilities(limits.config(space, agent))[key]


def blocked_areas(space: str, agent: str) -> set:
	"""The areas the owner switched off for this agent, with their parts and focuses."""
	return limits._below(space, set(limits.areas_off(limits.config(space, agent))))


def _need_switch(space: str, agent: str, tool: str):
	if mode_of(space, agent, tool) == limits.OFF:
		label = dict(limits.ACTIONS)[READS.get(tool) or ACTS[tool][0]]
		frappe.throw(_("The owner has switched “{0}” off for this agent.").format(label), frappe.PermissionError, title=_("Switched off"))


# ---------------------------------------------------------------- reads

def read(space: str, agent: str, tool: str, params: dict) -> dict:
	"""A read for an agent: refused when its switch is off, and leaving out mail already filed under an area the agent may not read."""
	if tool not in READS:
		frappe.throw(_("{0} is not a read tool.").format(tool), title=_("Unknown tool"))
	_need_switch(space, agent, tool)
	person, params = person_of(space), params or {}
	blocked = blocked_areas(space, agent)
	if tool == "mail.search":
		out = mail.search(person, space, params.get("fields") or {}, params.get("account"), params.get("max") or 10, agent=agent)
		out["hits"] = [h for h in out["hits"] if not blocked or _filed_area(space, h["thread_id"]) not in blocked]
		return out
	if tool == "mail.get_thread":
		if blocked and _filed_area(space, params.get("thread_id")) in blocked:
			frappe.throw(_("That email is in an area this agent may not read."), frappe.PermissionError, title=_("Area is off for this agent"))
		return mail.get_thread(person, space, params.get("thread_id") or "", params.get("account"))
	if tool == "mail.get_attachment":
		return mail.get_attachment(person, space, params.get("message_id") or "", params.get("attachment_id") or "", params.get("for_item") or "", params.get("account"),
			params.get("filename"))
	return {"events": calendar_list(space, person, params)}


def _filed_area(space: str, thread_id: str | None):
	"""The area a thread is filed under in Life OS, if it has been filed."""
	return frappe.db.get_value("Life Inbox Item", {"space": space, "source_system": ["in", ["gmail", "microsoft"]], "external_id": thread_id or ""}, "area") if thread_id else None


def _google_only(rows: list) -> list:
	"""The calendar is Google's (Microsoft's is not built): its tools use a Google inbox, and say so when the person has none."""
	rows = [r for r in rows if r.provider == "gmail"]
	if not rows:
		frappe.throw(_("No Google account is connected. Calendar tools work for Google inboxes only."), title=_("No account connected"))
	return rows


def calendar_list(space: str, person: str, params: dict) -> list:
	rows = _google_only(mail.accounts_for(person, space, params.get("account")))
	client = mail.google_for(frappe._dict(rows[0]))
	return client.list_events(str(params.get("time_min") or frappe.utils.today()), str(params.get("time_max") or frappe.utils.add_days(frappe.utils.today(), 14)),
		min(cint(params.get("max") or 50), 100))


# ---------------------------------------------------------------- acts

def _clean(tool: str, params) -> dict:
	params = params if isinstance(params, dict) else {}
	out = {k: v for k, v in params.items() if k in {*ACTS[tool][2], *OPTIONAL} and v not in (None, "")}
	missing = [k for k in ACTS[tool][2] if not str(out.get(k) or "").strip()]
	if missing:
		frappe.throw(_("{0} needs: {1}.").format(ACTS[tool][1], ", ".join(missing)), title=_("Something is missing"))
	if tool == "calendar.respond" and out["response"] not in ("accepted", "declined", "tentative"):
		frappe.throw(_("The answer must be accepted, declined or tentative."), title=_("Answer not understood"))
	if isinstance(out.get("attendees"), str):
		out["attendees"] = [a.strip() for a in out["attendees"].split(",") if a.strip()]
	return out


def _describe(tool: str, p: dict) -> tuple[str, str]:
	"""(the line a person reads, the draft to check before approving)."""
	if tool in ("email.send", "email.draft"):
		verb = "Send" if tool == "email.send" else "Draft"
		return f"{verb} “{p['subject']}” to {p['to']}", f"To: {p['to']}\nSubject: {p['subject']}\n\n{p['body']}"
	if tool == "email.archive":
		return f"Archive “{p.get('subject') or p['thread_id']}”", ""
	if tool == "email.label":
		return f"Label “{p.get('subject') or p['thread_id']}” {p['label']}", ""
	if tool == "calendar.create":
		return f"Add “{p['title']}” on {p['start']}", f"{p['title']}\n{p['start']} to {p['end']}" + (f"\nWith: {', '.join(p['attendees'])}" if p.get("attendees") else "")
	if tool == "calendar.move":
		return f"Move “{p.get('title') or p['event_id']}” to {p['start']}", f"{p['start']} to {p['end']}"
	return f"{p['response'].capitalize()}: “{p.get('title') or p['event_id']}”", ""


def request(space: str, agent: str, tool: str, params: dict, asked_by: str, owner_message: str | None = None) -> dict:
	"""An agent's act. Returns {status: done | waiting | failed, action, result}; refused (an error) when it is switched off or the request is not understood."""
	if tool not in ACTS:
		frappe.throw(_("{0} is not something an agent can do. The tools are: {1}.").format(tool, ", ".join(TOOLS)), title=_("Unknown tool"))
	if asked_by not in (OWNER, AGENT):
		frappe.throw(_("Say who asked: owner (the owner told the agent to) or agent (its own idea)."), title=_("Who asked?"))
	message = " ".join((owner_message or "").split())
	if asked_by == OWNER and not message:
		frappe.throw(_("An act the owner asked for carries the owner's message."), title=_("The owner's message is missing"))
	p = _clean(tool, params)
	if asked_by == AGENT:
		_need_switch(space, agent, tool)
	title, draft = _describe(tool, p)
	run_now = asked_by == OWNER or mode_of(space, agent, tool) == limits.AUTO
	row = frappe.get_doc({"doctype": "Life Agent Action", "space": space, "agent": agent, "action": ACTS[tool][0], "title": title[:200], "draft": draft[:5000],
		"status": "Waiting", "asked_by": asked_by, "request": message[:500] or None, "params": json.dumps({"tool": tool, **p}), "happened_on": now_datetime(),
		"delivered": 1}).insert(ignore_permissions=True)  # system: the agent's own log; the space write check is in the API
	if not run_now:
		return {"status": "waiting", "action": row.name, "title": title}
	return {**execute(row.name), "action": row.name, "title": title}


def _inbox(person: str, space: str, p: dict, tool: str = ""):
	"""The inbox an act is made in: the one named, the one the thread is in, or the person's default."""
	rows = mail.accounts_for(person, space, p.get("account"))
	if not rows:
		frappe.throw(_("No inbox is connected. Connect one in Brain > Sources."), title=_("No inbox connected"))
	if tool.startswith("calendar."):
		rows = _google_only(rows)
	if len(rows) > 1 and p.get("thread_id") and not p.get("account"):
		for row in rows:
			try:
				mail.adapter(frappe._dict(row)).get_thread(p["thread_id"])
				return frappe._dict(row)
			except frappe.PermissionError:
				raise
			except Exception:  # noqa: BLE001 - that inbox does not have the thread; try the next
				continue
	return frappe._dict(rows[0])


def execute(name: str) -> dict:
	"""Run an act that was logged: now (the owner's request) or after the owner approved it. Sets Done with what Google answered, or Failed with the reason."""
	row = frappe.get_doc("Life Agent Action", name)
	if row.status not in ("Waiting", "Approved") or not row.params:
		frappe.throw(_("That cannot be run."), title=_("Already decided"))
	p = json.loads(row.params)
	tool = p.pop("tool")
	person = person_of(row.space)
	try:
		account = _inbox(person, row.space, p, tool)
		result, undo = _run(tool, account, p)
	except frappe.PermissionError:
		raise
	except Exception as e:  # noqa: BLE001 - Google or the inbox failed: the log says so, without a token
		reason = scrub(e)[:300]
		frappe.db.set_value("Life Agent Action", row.name, {"status": "Failed", "error": reason, "happened_on": now_datetime()})
		return {"status": "failed", "error": reason}
	frappe.db.set_value("Life Agent Action", row.name, {"status": "Done", "result": json.dumps(result, default=str)[:900], "undo": json.dumps({**undo, "account": account.name}) if undo else None,
		"happened_on": now_datetime(), "error": None})
	return {"status": "done", "result": result, "undoable": int(bool(undo))}


def _run(tool: str, account, p: dict) -> tuple[dict, dict | None]:
	g = mail.google_for(account)
	if tool in ("email.send", "email.draft"):
		out = (g.send if tool == "email.send" else g.draft)(p["to"], p["subject"], p["body"], p.get("thread_id"), p.get("cc"))
		return {"id": out.get("id"), "thread_id": out.get("thread_id"), "from": account.address}, ({"call": "delete_draft", "id": out.get("id")} if tool == "email.draft" else None)
	if tool == "email.archive":
		g.archive(p["thread_id"])
		return {"thread_id": p["thread_id"]}, {"call": "unarchive", "thread_id": p["thread_id"]}
	if tool == "email.label":
		label_id = g.label(p["thread_id"], p["label"])
		return {"thread_id": p["thread_id"], "label": p["label"]}, {"call": "unlabel", "thread_id": p["thread_id"], "label_id": label_id}
	if tool == "calendar.create":
		ev = g.create_event(p["title"], p["start"], p["end"], p.get("attendees"), p.get("description"), p.get("location"))
		return {"event_id": ev.get("event_id"), "link": ev.get("link", "")}, {"call": "delete_event", "event_id": ev.get("event_id")}
	if tool == "calendar.move":
		ev = g.move_event(p["event_id"], p["start"], p["end"])
		return {"event_id": p["event_id"], "start": ev.get("start")}, None
	g.respond(p["event_id"], p["response"], account.address)
	return {"event_id": p["event_id"], "response": p["response"]}, None


def decide(name: str, approve: bool, user: str) -> dict:
	"""The owner's OK or No on an agent's own idea. Approving runs it (and moves it to Did); No discards it and what it would have sent."""
	row = frappe.get_doc("Life Agent Action", name)
	if row.status != "Waiting":
		frappe.throw(_("That was already decided."), title=_("Already decided"))
	frappe.db.set_value("Life Agent Action", name, {"decided_by": user, "decided_on": now_datetime(), **({} if approve else {"status": "Declined", "params": None, "draft": None})})
	if not approve:
		return {"name": name, "agent": row.agent, "status": "Declined"}
	done = execute(name)
	return {"name": name, "agent": row.agent, "status": "Done" if done["status"] == "done" else "Failed", **({"error": done["error"]} if done.get("error") else {})}


def undo(name: str) -> dict:
	"""Take back an act where Google allows it (a draft, an archive, a label, an event the agent made)."""
	row = frappe.get_doc("Life Agent Action", name)
	u = json.loads(row.undo) if row.undo else None
	if row.status != "Done" or not u or row.undone:
		frappe.throw(_("That cannot be undone."), title=_("Nothing to undo"))
	account = frappe._dict(frappe.db.get_value("Life Mail Account", u.pop("account"), ["name", "address", "provider", "connection", "user", "space", "label"], as_dict=True) or {})
	call = u.pop("call")
	try:
		getattr(mail.google_for(account), call)(*u.values())
	except Exception as e:  # noqa: BLE001
		frappe.throw(scrub(e)[:200], title=_("Could not undo"))
	frappe.db.set_value("Life Agent Action", name, "undone", 1)
	return {"name": name, "undone": 1}
