"""Chat (issue 119, once Ask): questions about the owner's own records and requests to file things, answered by Flow's agent through Life OS's tools,
which run as the asking user. Threads are private to their user; agents cannot use Chat. The model, its key and the loop are Flow's (`lifeos.ai.chat`)."""
import json

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder import functions as fn

from lifeos import permissions
from lifeos.api.utils import count_where, list_query, page, parse

SUGGESTED = ["What did I promise people this week?", "What is stuck, and what should I do about it?",
	"How am I doing on my 12 Week Year goals this cycle?", "What came in this week that I have not acted on?"]


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Agents cannot use Chat."), frappe.PermissionError, title=_("Agents cannot use Chat"))


@frappe.whitelist(methods=["GET"])
def status(space: str | None = None):
	"""Is Chat ready for this person in this space: a model set up in Flow, on for the space, and under the monthly cap."""
	from lifeos.ai import chat, client

	space = permissions.resolve_space(space)
	on = bool(frappe.db.get_value("Life Space", space, "ask_enabled"))
	set_up = chat.ready()
	st = {**client.spend_status(), "set_up": set_up}
	return {"ready": on and set_up and not st["reached"] and not permissions.is_agent(), "enabled": on, **st, "brain_off": client.brain_off(),
		"vault": bool(frappe.db.get_value("Life Space", space, "ask_can_read_vault")), "suggested": SUGGESTED,
		"is_admin": permissions.is_admin()}


def _thread(name):
	doc = frappe.get_doc("Life Ask Thread", name)
	if doc.user != frappe.session.user:
		raise frappe.DoesNotExistError(_("Thread not found."))
	return doc


def _scope(scope, space):
	"""A scope from the screen, checked: the record it names must be in the space and readable."""
	s = parse(scope, {}) or {}
	s = {k: s.get(k) for k in ("kind", "label", "doctype", "name", "items") if s.get(k) not in (None, "")}
	s.setdefault("kind", "space")
	if s.get("name") and not s.get("doctype"):
		s["doctype"] = {"area": "Life Area", "goal": "Life Goal"}.get(s["kind"])
		if not s["doctype"]:
			s.pop("name")
	if s.get("doctype") and s.get("name"):
		doc = permissions.get_doc_checked(s["doctype"], s["name"])
		if doc.get("space") and doc.space != space:
			frappe.throw(_("That record is in another space."), title=_("Record is in another space"))
	if s.get("kind") == "area" and s.get("name"):
		if frappe.db.get_value("Life Area", s["name"], "space") != space:
			frappe.throw(_("That area is in another space."), title=_("Area is in another space"))
	if s.get("items"):
		s["items"] = [{"doctype": i.get("doctype"), "name": i.get("name")} for i in s["items"][:200] if isinstance(i, dict)]
	return s


def _record(record, space):
	"""The record the owner has open, checked like a scope: readable, and in the space."""
	r = parse(record, {}) or {}
	if not (r.get("doctype") and r.get("name")):
		return None
	doc = permissions.get_doc_checked(r["doctype"], r["name"])
	if doc.get("space") and doc.space != space:
		frappe.throw(_("That record is in another space."), title=_("Record is in another space"))
	return {"doctype": r["doctype"], "name": r["name"]}


@frappe.whitelist(methods=["POST"])
def send(question: str, space: str | None = None, thread: str | None = None, scope: str | dict | None = None, record: str | dict | None = None):
	"""Send a message, or a follow-up in a thread (same scope unless `scope` changes it). `record` is the record the person has open ({doctype, name}).
	It checks the monthly cap, starts the run in the thread's Flow Session and returns at once with the thread and the answer, `Working`; the screen
	polls `progress` until it is Done."""
	from lifeos.ai import chat, client

	_person()
	question = " ".join((question or "").split())
	if not question:
		frappe.throw(_("Type a question."), title=_("Question is empty"))
	if thread:
		t = _thread(thread)
		if t.channel:  # a conversation the owner had on another channel: you answer there, not here (issue 125)
			frappe.throw(_("This conversation is on {0}. Reply there.").format(t.channel), title=_("Read only"))
		space = t.space
		permissions.require_space(space)
		if scope:
			sc = _scope(scope, space)
			t.scope_kind, t.scope_label, t.scope_doctype, t.scope_name = sc.get("kind"), sc.get("label"), sc.get("doctype"), sc.get("name")
			t.save(ignore_permissions=True)  # system: the thread belongs to the asker
		sc = _scope(scope, space) if scope else {"kind": t.scope_kind or "space", "label": t.scope_label, "doctype": t.scope_doctype, "name": t.scope_name}
	else:
		space = permissions.resolve_space(space)
		sc = _scope(scope, space)
		t = frappe.get_doc({"doctype": "Life Ask Thread", "space": space, "user": frappe.session.user, "title": question[:140],
			"scope_kind": sc.get("kind"), "scope_label": sc.get("label"), "scope_doctype": sc.get("doctype"), "scope_name": sc.get("name")})
		t.insert(ignore_permissions=True)  # system: the thread belongs to the asker
	if sc.get("items"):
		frappe.cache.hset("lifeos_ask_items", t.name, json.dumps(sc["items"]))
	rec = _record(record, space)
	if not frappe.db.get_value("Life Space", space, "ask_enabled"):
		return _refuse(t, question, "off", _("Chat is turned off for this space."))
	if not chat.ready():
		return _refuse(t, question, "not_set_up", _("Chat needs an AI key. Add one in Settings › AI."))
	try:
		client.check_cap(chat.PURPOSE)
	except client.CapReached as e:
		return _refuse(t, question, "cap", str(e))
	try:
		run = chat.start(t, question, sc, rec)
	except Exception as e:
		frappe.log_error(title="Life OS Chat failed")
		text = _("Something went wrong while starting the answer. It has been logged.")
		return {"thread": t.name, "message": {"role": "assistant", "text": "", "status": "Error", "error": text, "cited": [], "actions": [], "done": [], "read": []}, "error": "ai", "error_text": text}
	return {"thread": t.name, "message": {"name": run.name, "thread": t.name, "role": "assistant", "text": "", "status": "Working", "error": None, "cited": [], "actions": [], "done": [], "read": []},
		"scope": sc}


def _refuse(t, question, code, text):
	from lifeos.ai import client

	return {"thread": t.name, "error": code, "error_text": text, "spend": client.spend_status(), "question": question}


@frappe.whitelist(methods=["POST"])
def progress(thread: str, message: str | None = None):
	"""The answer of a run so far: the same message `thread` gives, `Working` until the run ends. It brings the run up to date from the Flow Server and writes the usage
	of a run that has ended, so it is a POST."""
	from lifeos.ai import chat

	_person()
	t = _thread(thread)
	return chat.latest_answer(t, message) or {"status": "Waiting", "text": ""}


def _title(t) -> str:
	"""A relayed thread is shown under the agent's current name."""
	from lifeos.api import chats

	return chats.relay_title(t.space, t.source_system, t.channel) if t.channel and t.source_system else t.title


@frappe.whitelist(methods=["GET"])
def thread(name: str):
	from lifeos.ai import chat

	_person()
	t = _thread(name)
	return {"name": t.name, "title": _title(t), "channel": t.channel or "", "readonly": int(bool(t.channel)), "space": t.space, "scope": {"kind": t.scope_kind or "space", "label": t.scope_label,
		"doctype": t.scope_doctype, "name": t.scope_name}, "messages": chat.messages_of(t)}


@frappe.whitelist(methods=["GET"])
def threads(space: str | None = None, q: str | None = None, start: int | str | None = 0, page_length: int | str | None = 30):
	"""The History tab: this person's threads in a space, newest first, searchable by their titles."""
	_person()
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	t = frappe.qb.DocType("Life Ask Thread")
	where = [t.user == frappe.session.user, t.space == space]
	if q:
		where.append(t.title.like(f"%{q}%") | t.transcript.like(f"%{q}%"))
	rows = list_query("Life Ask Thread", ["name", "title", "scope_label", "last_message_on", "creation", "channel", "source_system", "space", "flow_session", "transcript"], where, [(fn.IfNull(t.last_message_on, t.creation), Order.desc)])
	rows = rows.limit(page_length).offset(start).run(as_dict=True)
	total = count_where("Life Ask Thread", where)
	for r in rows:
		r["questions"] = _questions(r)
		r["last_message_on"] = str(r.last_message_on or r.creation)[:16]
		r["title"] = _title(r)
		r["channel"] = r.channel or ""
		for k in ("creation", "source_system", "space", "flow_session", "transcript"):
			r.pop(k, None)
	return {"rows": rows, "total": total}


def _questions(r) -> int:
	"""How many questions the thread holds: the owner's lines of its earlier messages, and its runs."""
	earlier = sum(1 for m in (frappe.parse_json(r.transcript) if r.transcript else []) if m.get("role") == "user")
	return earlier + (frappe.db.count("Flow Run", {"session": r.flow_session}) if r.flow_session else 0)


@frappe.whitelist(methods=["POST"])
def delete_thread(name: str):
	_person()
	t = _thread(name)
	if t.flow_session and frappe.db.exists("Flow Session", t.flow_session):
		frappe.delete_doc("Flow Session", t.flow_session, ignore_permissions=True)  # system: the chat's session is the person's own; the thread was checked above
	frappe.delete_doc("Life Ask Thread", t.name, ignore_permissions=True, delete_permanently=True)  # system: the thread belongs to the asker
	return {"deleted": name}


@frappe.whitelist(methods=["POST"])
def undo_done(message: str, index: int | str):
	"""Undo one line of an answer's "Done" list (issue 107): what Chat made is taken away again, and the line says so. `message` is the answer's name."""
	from lifeos.ai import chat
	from lifeos.tools import actions

	_person()
	session = frappe.db.get_value("Flow Run", message, "session")
	t = _thread(frappe.db.get_value("Life Ask Thread", {"flow_session": session}, "name") or "")
	lines = chat._done_lines(message, session)
	try:
		i = int(index)
		row = lines[i]
	except (IndexError, ValueError, TypeError):
		frappe.throw(_("No such line."), title=_("Line not found"))
	undone = frappe.parse_json(t.undone) if t.undone else {}
	if not row.get("undo") or undone.get(f"{message}:{i}"):
		frappe.throw(_("That cannot be undone."), title=_("Nothing to undo"))
	permissions.require_space(t.space, write=True)
	out = actions.undo(row["undo"])
	undone[f"{message}:{i}"] = 1
	t.db_set("undone", json.dumps(undone), update_modified=False)
	return {"undone": out["undone"], "index": i}
