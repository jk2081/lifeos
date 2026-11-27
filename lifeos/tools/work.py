"""Ask tools for what the owner plans (issue 107): a task and an event, made straight away when the owner asked for them, by the owner or through an agent
(issue 125). A task or an event Ask suggests on its own stays a button the owner clicks; an agent's own idea follows its "Add tasks and events" switch."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.tools import actions


def add_task(title: str, area: str | None = None, part: str | None = None, due_date: str | None = None, person: str | None = None, space: str | None = None, source_system: str | None = None, asked_by: str | None = None, owner_message: str | None = None) -> dict:
	"""Make a task called `title`, under an `area` (and a `part`) by their names, with an optional due date (YYYY-MM-DD) and the `person` it is about (by name; the task then links to them)."""
	return actions.write("tasks.add", space, {"title": title, "area": area, "part": part, "due_date": due_date, "person": person}, source_system, owner_message, asked_by)


def _add_task(space: str, title: str, area: str | None = None, part: str | None = None, due_date: str | None = None, person: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.api import tasks
	from lifeos.library import people

	where = actions.area_of(space, area, part) if area or part else None
	task = tasks.quick_add(title, space=space, area=where, due_date=due_date or None)
	found = people.find(space, person) if person else None
	if found:  # the task links to the person: a [[link]] in its notes, which Life OS resolves on save
		doc = frappe.get_doc("Life Task", task["name"])
		doc.notes_md = f"With [[{found.full_name}]]"
		doc.save()
	return _("Made task {0}").format(task["title"]), {"task": task["name"], "title": task["title"], "due_date": str(task.get("due_date") or ""), "person": found.full_name if found else ""}, {"delete": [["Life Task", task["name"]]]}


def hand_off(person: str, what: str, check_by: str | None = None, how: str = "track", channel: str = "email", space: str | None = None, source_system: str | None = None,
		asked_by: str | None = None, owner_message: str | None = None) -> dict:
	"""Hand something off to `person`: a Waiting task (`what`, looked at again on `check_by`). `how`: track (nothing is sent, the default), draft (a message is written for
	the owner to send, edit or drop) or send (an email goes at once: only when the owner said send). `channel` is email or whatsapp; Life OS never sends WhatsApp, it
	makes the link. `how: done` says the person already sent it: their waiting task is Done."""
	return actions.write("tasks.hand_off", space, {"person": person, "what": what, "check_by": check_by, "how": how, "channel": channel, "asked_by": asked_by or actions.OWNER,
		"owner_message": owner_message}, source_system, owner_message, asked_by)


def _hand_off(space: str, person: str, what: str, check_by: str | None = None, how: str = "track", channel: str = "email", asked_by: str = "owner",
		owner_message: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.tasks import handoff

	if how == "done":
		out = handoff.said_done(space, person, what)
		return _("Marked “{0}” done: {1} sent it").format(out["title"], out["who"]), {"task": out["task"], "title": out["title"]}, None
	out = handoff.hand_off_task(space, person, what, check_by, how, channel, None, asked_by, owner_message, what)
	if out["sent"]:
		line = _("Sent the email to {0} and waiting on them for {1} (look again {2})").format(out["who"], what, out["check_by"])
	elif out["waiting"]:
		line = _("Waiting on {0} for {1}; the email waits for your OK in Needs you").format(out["who"], what)
	elif out["how"] == "draft":
		line = _("Waiting on {0} for {1} (look again {2}); a message is drafted, nothing is sent").format(out["who"], what, out["check_by"])
	else:
		line = _("Waiting on {0} for {1} (look again {2}); nothing was sent").format(out["who"], what, out["check_by"])
	return line, {"task": out["task"], "title": what, "person": out["who"], "how": out["how"], "channel": channel, "check_by": out["check_by"], "message": out["message"] or "",
		"whatsapp": out["whatsapp"] or "", "needs_phone": int(out["needs_phone"])}, out["undo"]


def add_event(title: str, start: str, end: str | None = None, all_day: bool = False, description: str | None = None, space: str | None = None, source_system: str | None = None, asked_by: str | None = None, owner_message: str | None = None) -> dict:
	"""Put an event on the calendar: `start` and `end` as YYYY-MM-DD or YYYY-MM-DD HH:MM."""
	return actions.write("events.add", space, {"title": title, "start": start, "end": end, "all_day": all_day, "description": description}, source_system, owner_message, asked_by)


def _add_event(space: str, title: str, start: str, end: str | None = None, all_day: bool = False, description: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.api import calendar

	made = calendar.add_event(space=space, subject=title, starts_on=start, ends_on=end, all_day=1 if all_day else 0, description=description)
	return _("Added event {0} on {1}").format(title, str(start)[:16]), {"event": made["name"], "title": title}, {"events": [made["name"]]}


CHAT_AGENT = "lifeos-chat"  # the `agent` of a Google act the owner asked for in Chat


def find_events(space: str, query: str | None = None, date_from: str | None = None, date_to: str | None = None, limit: int = 20) -> list[dict]:
	"""Events of the space the person can see (not hidden), by words in the title, between two dates (30 days back to 120 days ahead by default)."""
	from frappe.utils import add_days, today

	filters = {"life_space": space, "life_hidden": 0, "starts_on": ["between", [date_from or add_days(today(), -30), (date_to or add_days(today(), 120)) + " 23:59:59"]]}
	if query:
		filters["subject"] = ["like", f"%{query}%"]
	return frappe.get_list("Event", filters=filters, fields=["name", "subject", "starts_on", "ends_on", "all_day", "google_calendar_event_id"], order_by="starts_on asc", limit=min(int(limit or 20), 50))


def add_note(doctype: str, name: str, text: str, space: str) -> tuple[str, dict]:
	"""A note on a record: on an event it is the event's own note (never written to Google); on anything else, a Comment, which the record shows under its notes."""
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Write the note first."), title=_("Note is empty"))
	doc = permissions.get_doc_checked(doctype, name, "write" if doctype != "Event" else "read")
	if doc.get("space") and doc.space != space or doc.get("life_space") and doc.life_space != space:
		frappe.throw(_("That record is in another space."), title=_("Record is in another space"))
	if doctype == "Event":
		from lifeos.calendar import notes

		notes.add(name, text)
	else:
		doc.add_comment("Comment", text)
	title = doc.get(frappe.get_meta(doctype).title_field or "name") or name
	return _("Added a note to {0}").format(title), {"title": title}


def cancel_event(space: str, event: str, message: str) -> dict:
	"""The owner said an event is cancelled (`message` is their own words). A Google event is cancelled in Google (through the same switch an agent's calendar change follows,
	here the owner's own request) and hidden in Life OS; an event Life OS made is deleted. Returns {done, title} or {waiting} when an agent asked."""
	from lifeos.agents import acts
	from lifeos.api import calendar

	doc = permissions.get_doc_checked("Event", event, "read")
	if doc.get("life_space") != space:
		frappe.throw(_("That event is in another space."), title=_("Event is in another space"))
	permissions.require_space(space, write=True)
	title = doc.subject
	gid = doc.get("google_calendar_event_id")
	if not gid:  # never sent to Google: the owner's own event
		calendar.delete_event(doc.name)
		return {"done": _("Cancelled {0}, deleted from your calendar").format(title), "title": title, "event": doc.name}
	out = acts.request(space, CHAT_AGENT, "calendar.cancel", {"event_id": gid, "title": title}, "owner", message)
	if out.get("status") == "failed":
		frappe.throw(out.get("error") or _("Google did not cancel it."), title=_("Not cancelled"))
	doc.db_set("life_hidden", 1, update_modified=False)  # a flag only: nothing more is sent to Google
	return {"done": _("Cancelled {0} in Google Calendar").format(title), "title": title, "event": doc.name}


# ---------------------------------------------------------------- finish, reopen and merge tasks (issue 149)

HANDOFF = ("waiting_on", "waiting_on_person", "check_by", "handed_off_how", "handed_off_channel", "handed_off_ask", "handed_off_message", "handed_off_thread", "handed_off_action")
LINKS = ("goal", "area", "delegated_to", "inbox_item")


def _task_in(space: str, task: str):
	doc = permissions.get_doc_checked("Life Task", task, "write")
	if doc.space != space:
		frappe.throw(_("That task is in another space."), title=_("Task is in another space"))
	return doc


def _was(doc) -> dict:
	"""What a status change puts back on Undo."""
	return {"status": doc.status, "completed_on": str(doc.completed_on) if doc.completed_on else None}


def finish_task(task: str, space: str | None = None, owner_message: str | None = None) -> dict:
	"""Set a task Done, the way the screens do (`tasks.set_status`)."""
	return actions.write("tasks.finish", space, {"task": task}, None, owner_message, actions.OWNER)


def _finish_task(space: str, task: str) -> tuple[str, dict, dict | None]:
	from lifeos.api import tasks

	doc = _task_in(space, task)
	if doc.status == "Done":
		return _("{0} was already done").format(doc.title), {"task": doc.name, "title": doc.title}, None
	was = _was(doc)
	tasks.set_status(doc.name, "Done")
	return _("Marked {0} done").format(doc.title), {"task": doc.name, "title": doc.title}, {"restore": [["Life Task", doc.name, was]]}


def reopen_task(task: str, space: str | None = None, owner_message: str | None = None) -> dict:
	"""A Done or Dropped task goes back to Open."""
	return actions.write("tasks.reopen", space, {"task": task}, None, owner_message, actions.OWNER)


def _reopen_task(space: str, task: str) -> tuple[str, dict, dict | None]:
	from lifeos.api import tasks

	doc = _task_in(space, task)
	if doc.status not in ("Done", "Dropped"):
		frappe.throw(_("{0} is not done or dropped.").format(doc.title), title=_("Nothing to reopen"))
	was = _was(doc)
	tasks.set_status(doc.name, "Open")
	return _("Reopened {0}").format(doc.title), {"task": doc.name, "title": doc.title}, {"restore": [["Life Task", doc.name, was]]}


def merge_tasks(keep: str, drop: str, space: str | None = None, owner_message: str | None = None) -> dict:
	"""Two tasks are the same: `keep` stays and takes what `drop` has that it lacks; `drop` is set Dropped."""
	return actions.write("tasks.merge", space, {"keep": keep, "drop": drop}, None, owner_message, actions.OWNER)


def _merge_tasks(space: str, keep: str, drop: str) -> tuple[str, dict, dict | None]:
	from lifeos.api import tasks

	if keep == drop:
		frappe.throw(_("Name two different tasks."), title=_("Same task"))
	kept, gone = _task_in(space, keep), _task_in(space, drop)
	gone_was = _was(gone)
	took, differ = {}, []
	for field in LINKS:  # a link moves over only where the kept task has none
		if gone.get(field) and not kept.get(field):
			took[field] = gone.get(field)
		elif field == "goal" and gone.get(field) and kept.get(field) != gone.get(field):
			differ.append(_("goal"))
	if any(gone.get(f) for f in HANDOFF):
		if not any(kept.get(f) for f in HANDOFF):
			took.update({f: gone.get(f) for f in HANDOFF if gone.get(f)})
		elif any(kept.get(f) != gone.get(f) for f in HANDOFF if gone.get(f)):
			differ.append(_("hand-off"))
	restore = [["Life Task", gone.name, gone_was]]
	if took:
		restore.append(["Life Task", kept.name, {f: kept.get(f) for f in took}])
		for f, v in took.items():
			kept.set(f, v)
		kept.save()
	comments = frappe.get_all("Comment", filters={"reference_doctype": "Life Task", "reference_name": gone.name, "comment_type": "Comment"}, pluck="name")
	for c in comments:  # the dropped task's notes move to the kept one
		frappe.db.set_value("Comment", c, "reference_name", kept.name, update_modified=False)
	added = [kept.add_comment("Comment", _("Merged from: {0}").format(gone.title)).name]
	tasks.set_status(gone.name, "Dropped")
	added.append(gone.add_comment("Comment", _("Merged into: {0}").format(kept.title)).name)
	line = _("Merged {0} into {1}").format(gone.title, kept.title)
	if differ:
		line += " " + _("(they had different {0}: kept the ones on {1})").format(", ".join(differ), kept.title)
	return line, {"task": kept.name, "title": kept.title, "dropped": gone.name, "differ": ", ".join(differ)}, {"restore": restore, "recomment": [[c, gone.name] for c in comments], "comments": added}
