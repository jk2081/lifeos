"""Ask (UX fixes, set 5): questions about the owner's own records, answered by an AI model through tools that run as
the asking user. Threads and messages are private to their user; agents cannot use Ask."""
import json
import time

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder import functions as fn
from frappe.utils import cint, now_datetime

from lifeos import permissions
from lifeos.api.utils import count_where, list_query, page, parse

SUGGESTED = ["What did I promise people this week?", "What is stuck, and what should I do about it?",
	"How am I doing on my 12 Week Year goals this cycle?", "What came in this week that I have not acted on?"]


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Agents cannot use Ask."), frappe.PermissionError, title=_("Agents cannot use Ask"))


@frappe.whitelist(methods=["GET"])
def status(space: str | None = None):
	"""Is Ask ready for this person in this space: set up (a key), on for the space, and under the monthly cap."""
	from lifeos.ai import client

	space = permissions.resolve_space(space)
	on = bool(frappe.db.get_value("Life Space", space, "ask_enabled"))
	st = client.spend_status()
	return {"ready": on and st["set_up"] and not st["reached"] and not permissions.is_agent(), "enabled": on, **st, "brain_off": client.brain_off(),
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


def _message_out(m):
	out = {"name": m.name, "thread": m.thread, "role": m.role, "text": m.text or "", "status": m.status, "error": m.error,
		"cited": parse(m.cited, []) or [], "actions": parse(m.actions, []) or [], "read": parse(m.records_read, []) or [],
		"cost": m.cost, "created": str(m.creation)[:19]}
	return out


@frappe.whitelist(methods=["POST"])
def ask(question: str, space: str | None = None, thread: str | None = None, scope: str | dict | None = None, client_id: str | None = None):
	"""Ask a question, or a follow-up in a thread (same scope unless `scope` changes it). Returns the thread and the
	answer. While it is written, `message` returns the text so far (and realtime events go to the asking user)."""
	from lifeos.ai import ask as engine
	from lifeos.ai import client

	_person()
	question = " ".join((question or "").split())
	if not question:
		frappe.throw(_("Type a question."), title=_("Question is empty"))
	if thread:
		t = _thread(thread)
		space = t.space
		permissions.require_space(space)
		if scope:
			sc = _scope(scope, space)
			t.scope_kind, t.scope_label, t.scope_doctype, t.scope_name = sc.get("kind"), sc.get("label"), sc.get("doctype"), sc.get("name")
		sc = _scope(scope, space) if scope else {"kind": t.scope_kind or "space", "label": t.scope_label, "doctype": t.scope_doctype, "name": t.scope_name,
			**({"items": parse(frappe.cache.hget("lifeos_ask_items", t.name), None) or []} if t.scope_kind == "items" else {})}
	else:
		space = permissions.resolve_space(space)
		sc = _scope(scope, space)
		t = frappe.get_doc({"doctype": "Life Ask Thread", "space": space, "user": frappe.session.user, "title": question[:140],
			"scope_kind": sc.get("kind"), "scope_label": sc.get("label"), "scope_doctype": sc.get("doctype"), "scope_name": sc.get("name")})
		t.insert(ignore_permissions=True)  # system: the thread and messages belong to the asker and the background answer writes them
	if sc.get("items"):
		frappe.cache.hset("lifeos_ask_items", t.name, json.dumps(sc["items"]))
	if not frappe.db.get_value("Life Space", space, "ask_enabled"):
		return _refuse(t, question, "off", _("Ask is turned off for this space."))
	try:
		client.check("Ask")
	except client.NotSetUp:
		return _refuse(t, question, "not_set_up", _("Ask needs an AI key. Add one in Settings › AI."))
	except client.CapReached as e:
		return _refuse(t, question, "cap", str(e))
	history = engine.history_messages(t.name)
	frappe.get_doc({"doctype": "Life Ask Message", "thread": t.name, "role": "user", "text": question, "status": "Done"}).insert(ignore_permissions=True)  # system: the thread and messages belong to the asker and the background answer writes them
	msg = frappe.get_doc({"doctype": "Life Ask Message", "thread": t.name, "role": "assistant", "text": "", "status": "Working"}).insert(ignore_permissions=True)  # system: the thread and messages belong to the asker and the background answer writes them
	t.last_message_on = now_datetime()
	t.save(ignore_permissions=True)  # system: the thread and messages belong to the asker and the background answer writes them
	# The screen polls `progress` with its own id while the answer is written. The text so far goes to the cache, not the
	# database, so the request commits once, at its end, and a failure leaves no half-written message behind.
	key = f"lifeos_ask_req:{frappe.session.user}:{client_id}" if client_id else None
	buf, last = [], [0.0]

	def show_progress(status="Working"):
		if key:
			frappe.cache.set_value(key, {"status": status, "text": "".join(buf), "thread": t.name, "message": msg.name}, expires_in_sec=900)

	def on_text(delta):
		buf.append(delta)
		frappe.publish_realtime("lifeos_ask", {"thread": t.name, "message": msg.name, "delta": delta}, user=frappe.session.user)
		if time.monotonic() - last[0] > 0.6:
			last[0] = time.monotonic()
			show_progress()

	show_progress()
	try:
		res = engine.answer(space, question, sc, history, on_text)
	except Exception as e:
		# an unexpected failure is logged and answered like a model error, so the usage already recorded is kept
		if not isinstance(e, client.AIError):
			frappe.log_error(title="Life OS Ask failed")
		text = str(e) if isinstance(e, client.AIError) else _("Something went wrong while answering. It has been logged.")
		msg.reload()
		msg.status, msg.error, msg.text = "Error", text, ""
		msg.save(ignore_permissions=True)  # system: the thread and messages belong to the asker and the background answer writes them
		buf.clear()
		show_progress("Error")
		return {"thread": t.name, "message": _message_out(msg), "error": "ai", "error_text": text}
	msg.reload()
	msg.update({"text": res["text"], "cited": json.dumps(res["cited"]), "actions": json.dumps(res["actions"]),
		"records_read": json.dumps(res["read"]), "input_tokens": res["input_tokens"], "output_tokens": res["output_tokens"],
		"cost": res["cost"], "status": "Done"})
	msg.save(ignore_permissions=True)  # system: the thread and messages belong to the asker and the background answer writes them
	buf[:] = [msg.text or ""]
	show_progress("Done")
	frappe.publish_realtime("lifeos_ask", {"thread": t.name, "message": msg.name, "done": 1}, user=frappe.session.user)
	return {"thread": t.name, "message": _message_out(msg), "scope": sc}


def _refuse(t, question, code, text):
	from lifeos.ai import client

	return {"thread": t.name, "error": code, "error_text": text, "spend": client.spend_status(), "question": question}


@frappe.whitelist(methods=["GET"])
def progress(client_id: str):
	"""The answer so far for a question still being written (polling, when realtime is not available)."""
	_person()
	got = frappe.cache.get_value(f"lifeos_ask_req:{frappe.session.user}:{client_id}")
	return got if isinstance(got, dict) else {"status": "Waiting", "text": ""}


@frappe.whitelist(methods=["GET"])
def message(name: str):
	"""One message, for polling while an answer is written."""
	_person()
	m = frappe.get_doc("Life Ask Message", name)
	_thread(m.thread)
	return _message_out(m)


@frappe.whitelist(methods=["GET"])
def thread(name: str):
	_person()
	t = _thread(name)
	msgs = frappe.get_list("Life Ask Message", filters={"thread": t.name}, fields=["*"], order_by="creation asc")
	return {"name": t.name, "title": t.title, "space": t.space, "scope": {"kind": t.scope_kind or "space", "label": t.scope_label,
		"doctype": t.scope_doctype, "name": t.scope_name}, "messages": [_message_out(frappe._dict(m)) for m in msgs]}


@frappe.whitelist(methods=["GET"])
def threads(space: str | None = None, q: str | None = None, start: int | str | None = 0, page_length: int | str | None = 30):
	"""The History tab: this person's threads in a space, newest first, searchable by their questions and answers."""
	_person()
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	t, m = frappe.qb.DocType("Life Ask Thread"), frappe.qb.DocType("Life Ask Message")
	where = [t.user == frappe.session.user, t.space == space]
	if q:
		said = frappe.qb.from_(m).select(m.thread).where(m.text.like(f"%{q}%"))
		where.append(t.title.like(f"%{q}%") | t.name.isin(said))
	questions = frappe.qb.from_(m).select(fn.Count("*")).where((m.thread == t.name) & (m.role == "user")).as_("questions")
	rows = list_query("Life Ask Thread", ["name", "title", "scope_label", "last_message_on", "creation"], where, [(fn.IfNull(t.last_message_on, t.creation), Order.desc)])
	rows = rows.select(questions).limit(page_length).offset(start).run(as_dict=True)
	total = count_where("Life Ask Thread", where)
	for r in rows:
		r["last_message_on"] = str(r.last_message_on or r.creation)[:16]
		r.pop("creation", None)
	return {"rows": rows, "total": total}


@frappe.whitelist(methods=["POST"])
def delete_thread(name: str):
	_person()
	t = _thread(name)
	frappe.db.delete("Life Ask Message", {"thread": t.name})
	frappe.delete_doc("Life Ask Thread", t.name, ignore_permissions=True, delete_permanently=True)  # system: the thread and messages belong to the asker and the background answer writes them
	return {"deleted": name}


@frappe.whitelist(methods=["POST"])
def run_action(message: str, index: int | str):
	"""Run one suggested action of an answer, with the person's own permissions, through the normal methods.
	Returns what the screen needs: a route, the record made, or the Undo log."""
	_person()
	m = frappe.get_doc("Life Ask Message", message)
	t = _thread(m.thread)
	actions = parse(m.actions, []) or []
	try:
		a = actions[int(index)]
	except (IndexError, ValueError, TypeError):
		frappe.throw(_("No such action."), title=_("Action not found"))
	kind = a.get("kind")
	if kind == "make_task":
		from lifeos.api import tasks

		task = tasks.quick_add(a.get("title") or a.get("label"), space=t.space, area=a.get("area"), due_date=a.get("due_date"))
		return {"kind": kind, "task": task["name"], "title": task["title"]}
	if kind == "file_mail":
		from lifeos import mail

		done = mail.file_thread(frappe.session.user, t.space, a.get("thread_id") or "", account=a.get("account"))
		return {"kind": kind, "item": done["item"], "title": done["title"]}
	if kind == "move_someday":
		from lifeos.api import reset

		res = reset.apply_batch("someday", a.get("items") or [], space=t.space)
		return {"kind": kind, "done": res["done"], "undo": res["undo"]}
	if kind == "open_reset":
		return {"kind": kind, "to": {"path": "/today/reset"}, "names": [i["name"] for i in a.get("items") or []]}
	if kind == "open_list":
		return {"kind": kind, "to": a.get("to")}
	if kind in ("snooze_insight", "dismiss_insight"):
		insight = permissions.get_doc_checked("Life Insight", a["insight"], "write")
		insight.status = "Snoozed" if kind == "snooze_insight" else "Dismissed"
		insight.save()
		return {"kind": kind, "insight": a["insight"]}
	frappe.throw(_("Unknown action."), title=_("Unknown action"))


@frappe.whitelist(methods=["POST"])
def undo_made_task(task: str):
	"""Undo of a suggested Make task: the task goes to the trash."""
	_person()
	from lifeos.library import trash

	return trash.delete("Life Task", task)
