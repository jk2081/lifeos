"""Handing off (issue 130): who owes what, by when. A message is optional, chosen each time.

A hand-off is a Waiting task with a person, a check-by date and how it went: **track** (nothing sent), **draft** (a message written for the owner to send,
edit or drop: a Gmail draft, or a WhatsApp link) or **send** (the email goes at once, through `google.act`'s `email.send` with `asked_by: owner`). Life OS never
sends WhatsApp, and never sends email without the owner's say. The words of a message are a skill's (`hand-off`); this module is plumbing: the task, the date,
the person, the log, the link.

The answer is noticed by the Brain (`lifeos.brain.asks`): a reply that says it is done is a proposal ("Looks done") the owner confirms here, and after three
confirmations for one person it closes that person's answers by itself.
"""
import json
import statistics
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, today

from lifeos import permissions
from lifeos.tasks import datewords

HOWS = ("track", "draft", "send")
CHANNELS = ("email", "whatsapp")
USUAL_AFTER = 3  # closed items a person needs before their usual time to answer counts
MIN_DAYS = 2
WORKING_DAYS = 3
NUDGE_DAYS = 3
MAX_NUDGES = 2
CONFIRMS_FOR_RULE = 3


# ---------------------------------------------------------------- dates

def working_days_after(n: int, start=None):
	day = getdate(start or today())
	while n > 0:
		day = add_days(day, 1)
		if day.weekday() < 5:
			n -= 1
	return day


def when_of(text, default=None):
	"""A date from an ISO date or a day word ("Friday", "in 3 days"); `default` when it says nothing."""
	if not text:
		return default
	if hasattr(text, "year"):
		return getdate(text)
	try:
		return getdate(str(text)) if len(str(text).strip()) == 10 and str(text).strip()[4] == "-" else (datewords.resolve(str(text)) or default)
	except Exception:
		return default


def usual_days(person) -> int | None:
	"""The median days this person has taken to answer (at least 2), once they have 3 or more closed items; None before."""
	rows = frappe.get_all("Life Task", filters={"waiting_on_person": person, "status": "Done", "completed_on": ("is", "set")}, fields=["creation", "completed_on"], limit=50)  # system: the owner's own waiting tasks
	days = [date_diff(r.completed_on, getdate(r.creation)) for r in rows]
	if len(days) < USUAL_AFTER:
		return None
	return max(MIN_DAYS, round(statistics.median(days)))


def default_check_by(space: str, person: str | None = None) -> str:
	"""The date to look again when the owner named none: the person's usual time to answer, else 3 working days."""
	usual = usual_days(person) if person else None
	return str(add_days(getdate(today()), usual) if usual else working_days_after(WORKING_DAYS))


# ---------------------------------------------------------------- the person

def person_of(space: str, who: str):
	"""The Life Person a name (or an id) means in the space; made, as a person, when the owner names someone new."""
	from lifeos.library import people as library

	who = " ".join((who or "").split())
	if not who:
		frappe.throw(_("Say who it is handed to."), title=_("Person is missing"))
	if frappe.db.exists("Life Person", {"name": who, "space": space}):
		return frappe.get_doc("Life Person", who)
	found = library.find(space, who)
	if found:
		return frappe.get_doc("Life Person", found.name)
	from lifeos.tools import people as tools_people

	_line, result, _undo = tools_people._add(space, who)
	return frappe.get_doc("Life Person", result["person"])


def space_user_of(person) -> str | None:
	"""The person's user, when they are in the same space (family, a team member)."""
	if not person.user:
		return None
	return person.user if person.space in permissions.user_spaces(person.user) else None


def whatsapp_link(phone: str | None, text: str) -> str | None:
	digits = "".join(c for c in (phone or "") if c.isdigit())
	return f"https://wa.me/{digits}?text={quote(text or '', safe='')}" if digits else None


def set_phone(person: str, phone: str) -> dict:
	doc = permissions.get_doc_checked("Life Person", person, "write")
	doc.phone = (phone or "").strip() or None
	doc.save()
	return {"person": doc.name, "phone": doc.phone}


# ---------------------------------------------------------------- the message

def owner_first(space: str) -> str:
	name = frappe.db.get_value("User", frappe.db.get_value("Life Space", space, "owner_user") or frappe.session.user, "first_name")
	return name or frappe.db.get_value("User", frappe.session.user, "first_name") or ""


def compose(space: str, kind: str, person, what: str, check_by, channel: str, task=None) -> dict:
	"""The message as {subject, body}: written by the `hand-off` skill in the owner's voice; with no model, one plain line."""
	from lifeos.skills import call

	first = (person.full_name or "").split(" ")[0]
	data = {"kind": kind, "channel": channel, "owner": owner_first(space), "person": person.full_name, "what": what, "by": str(check_by) if check_by else None,
		"nudges": cint(task.nudge_count) if task else 0, "asked_on": str(task.creation)[:10] if task else None}
	got = call.ask("hand-off", data, space)
	if got and str(got.get("body") or "").strip():
		return {"subject": str(got.get("subject") or "")[:140] if channel == "email" else "", "body": str(got.get("body")).strip()}
	if kind == "nudge":  # no model: a plain two-liner the owner can edit
		body = _("Hi {0}, a quick nudge on {1}. Could you let me know where it stands?").format(first, what)
	else:
		body = _("Hi {0}, could you send me {1}? Thanks.").format(first, _("{0} by {1}").format(what, check_by) if check_by else what)
	return {"subject": (_("Re: {0}") if kind == "nudge" else "{0}").format(what)[:140] if channel == "email" else "", "body": body}


def _request(space: str, tool: str, person, message: dict, thread_id=None, asked_by="owner", owner_message=None) -> dict:
	from lifeos.agents import acts
	from lifeos.tools import work

	if not person.email:
		frappe.throw(_("{0} has no email yet. Add it on their page, or hand off by WhatsApp.").format(person.full_name), title=_("No email address"))
	params = {"to": person.email, "subject": message["subject"] or _("A quick one"), "body": message["body"], **({"thread_id": thread_id} if thread_id else {})}
	return acts.request(space, work.CHAT_AGENT, tool, params, asked_by, owner_message or _("Hand off to {0}").format(person.full_name))


# ---------------------------------------------------------------- hand off

def _assign(task, person):
	"""A person with a user in the space gets the task in their own Life OS, through Frappe's own assignment. Nothing is sent."""
	user = space_user_of(person)
	if not user or user == frappe.session.user:
		return None
	from frappe.desk.form import assign_to

	if user not in [a.owner for a in assign_to.get({"doctype": "Life Task", "name": task.name})]:
		assign_to.add({"doctype": "Life Task", "name": task.name, "assign_to": [user], "description": task.title, "notify": 0})
	return user


def hand_off_task(space: str, person: str, what: str, check_by=None, how: str = "track", channel: str = "email", task: str | None = None,
		asked_by: str = "owner", owner_message: str | None = None, ask_words: str | None = None) -> dict:
	"""Hand `what` to `person`: a Waiting task with the check date, and (by `how`) a draft or the sent message. `task` hands off a task that exists.
	Returns {task, person, how, channel, message, whatsapp, needs_phone, undo}."""
	how = how if how in HOWS else "track"
	channel = channel if channel in CHANNELS else "email"
	what = " ".join((what or "").split())
	who = person_of(space, person)
	if task:
		doc = permissions.get_doc_checked("Life Task", task, "write")
		if doc.space != space:
			frappe.throw(_("That task is in another space."), title=_("Task is in another space"))
		what = what or doc.title
	if not what:
		frappe.throw(_("Say what is handed off."), title=_("Nothing to hand off"))
	check = when_of(check_by) or getdate(default_check_by(space, who.name))
	made = None
	if task:
		doc.update({"status": "Waiting", "waiting_on": who.full_name, "waiting_on_person": who.name, "delegated_to": who.name, "check_by": check,
			"handed_off_how": "track", "handed_off_channel": channel, "handed_off_ask": (ask_words or what)[:500], "nudge_count": 0})
		doc.save()
	else:
		doc = frappe.get_doc({"doctype": "Life Task", "space": space, "title": what[:140], "status": "Waiting", "waiting_on": who.full_name, "waiting_on_person": who.name,
			"delegated_to": who.name, "check_by": check, "handed_off_how": "track", "handed_off_channel": channel, "handed_off_ask": (ask_words or what)[:500]}).insert()
		made = doc.name
	_assign(doc, who)
	out = {"task": doc.name, "person": who.name, "who": who.full_name, "how": "track", "channel": channel, "check_by": str(check), "message": None, "whatsapp": None,
		"needs_phone": False, "sent": False, "waiting": None}
	if how != "track":
		_message(space, doc, who, how, channel, check, out, asked_by, owner_message)
	doc.reload()
	out["how"] = doc.handed_off_how
	out["undo"] = {"delete": [["Life Task", made]]} if made else None
	return out


def _message(space, doc, who, how, channel, check, out, asked_by, owner_message):
	"""Write the message; save it as a Gmail draft, send it (email only, and only when the owner said send), or make the WhatsApp link."""
	msg = compose(space, "ask", who, doc.title, check, channel, doc)
	values = {"handed_off_message": (f"{msg['subject']}\n\n" if msg["subject"] else "") + msg["body"], "handed_off_how": "draft"}
	if channel == "whatsapp":  # the owner sends it from his own number; Life OS never does
		values["handed_off_message"] = msg["body"]
		out.update(whatsapp=whatsapp_link(who.get("phone"), msg["body"]), needs_phone=not who.get("phone"))
	elif how == "send":
		got = _request(space, "email.send", who, msg, None, asked_by, owner_message)
		values.update(handed_off_how="sent" if got["status"] == "done" else "draft", handed_off_action=got.get("action"),
			handed_off_thread=(got.get("result") or {}).get("thread_id"))
		out.update(sent=got["status"] == "done", waiting=got.get("action") if got["status"] == "waiting" else None)
		if got["status"] == "failed":
			frappe.throw(got.get("error") or _("The email was not sent."), title=_("Not sent"))
	else:
		got = _request(space, "email.draft", who, msg, None, asked_by, owner_message)
		values.update(handed_off_action=got.get("action"), handed_off_thread=(got.get("result") or {}).get("thread_id"))
		if got["status"] == "failed":
			frappe.throw(got.get("error") or _("The draft was not saved."), title=_("Not saved"))
	frappe.db.set_value("Life Task", doc.name, values)
	out["message"] = values["handed_off_message"]


def _task(task: str, write: bool = True):
	doc = permissions.get_doc_checked("Life Task", task, "write" if write else "read")
	return doc, frappe.get_doc("Life Person", doc.waiting_on_person) if doc.waiting_on_person else None


def _split(text: str) -> dict:
	head, _sep, body = (text or "").partition("\n\n")
	return {"subject": head, "body": body} if _sep else {"subject": "", "body": text or ""}


def edit_message(task: str, text: str) -> dict:
	"""Change the words of a draft before it is sent."""
	doc, who = _task(task)
	if doc.handed_off_how != "draft":
		frappe.throw(_("There is no draft to edit."), title=_("No draft"))
	text = (text or "").strip()
	if not text:
		frappe.throw(_("A message needs words."), title=_("Message is empty"))
	doc.handed_off_message = text
	doc.save()
	link = whatsapp_link(who.get("phone"), text) if who and doc.handed_off_channel == "whatsapp" else None
	return {"task": doc.name, "message": text, "whatsapp": link}


def _drop_draft(doc):
	"""Take the Gmail draft back where Google allows it (the draft is deleted; the text stays on the task until it goes)."""
	if doc.handed_off_action and frappe.db.get_value("Life Agent Action", doc.handed_off_action, "undo"):
		from lifeos.agents import acts

		try:
			acts.undo(doc.handed_off_action)
		except frappe.ValidationError:
			frappe.clear_messages()


def send_draft(task: str, text: str | None = None) -> dict:
	"""Send the drafted email now (the owner pressed Send): the message goes through `email.send` in the same thread, then the old Gmail draft is deleted."""
	doc, who = _task(task)
	if doc.handed_off_how != "draft" or doc.handed_off_channel != "email":
		frappe.throw(_("There is no email draft to send."), title=_("No draft"))
	if text:
		edit_message(task, text)
		doc.reload()
	msg = _split(doc.handed_off_message)
	got = _request(doc.space, "email.send", who, msg, doc.handed_off_thread, "owner", _("Send the message to {0}").format(who.full_name))
	if got["status"] == "failed":  # the draft is kept until the email has gone
		frappe.throw(got.get("error") or _("The email was not sent."), title=_("Not sent"))
	sent = got["status"] == "done"
	if sent:
		_drop_draft(doc)
	frappe.db.set_value("Life Task", doc.name, {"handed_off_how": "sent" if sent else "draft", "handed_off_action": got.get("action"),
		"handed_off_thread": (got.get("result") or {}).get("thread_id") or doc.handed_off_thread})
	doc.add_comment("Info", _("Sent to {0}.").format(who.full_name))
	return {"task": doc.name, "sent": sent, "how": "sent" if sent else "draft"}


def discard_draft(task: str) -> dict:
	"""Drop the draft: the Gmail draft is deleted and the task goes on as tracking only."""
	doc, _who = _task(task)
	if doc.handed_off_how != "draft":
		frappe.throw(_("There is no draft to discard."), title=_("No draft"))
	_drop_draft(doc)
	frappe.db.set_value("Life Task", doc.name, {"handed_off_how": "track", "handed_off_message": None, "handed_off_action": None, "handed_off_thread": None})
	return {"task": doc.name, "how": "track"}


# ---------------------------------------------------------------- nudging

def nudge(task: str, channel: str | None = None) -> dict:
	"""A two-line follow-up, opened the way the hand-off went: an email draft (Send it from the task) or the WhatsApp link. The check date moves 3 days on."""
	doc, who = _task(task)
	if doc.status != "Waiting":
		frappe.throw(_("{0} is not waiting any more.").format(doc.title), title=_("Task is not waiting"))
	if cint(doc.nudge_count) >= MAX_NUDGES:
		frappe.throw(_("It was nudged twice already. Wait a week, take it back or drop it."), title=_("Nudged twice"))
	if not who:
		frappe.throw(_("Say who it waits on first."), title=_("Nobody to nudge"))
	channel = channel or doc.handed_off_channel or ("email" if who.email else "whatsapp")
	msg = compose(doc.space, "nudge", who, doc.title, doc.check_by, channel, doc)
	out = {"task": doc.name, "channel": channel, "whatsapp": None, "needs_phone": False, "how": "draft"}
	values = {"nudge_count": cint(doc.nudge_count) + 1, "check_by": add_days(getdate(today()), NUDGE_DAYS), "handed_off_channel": channel,
		"handed_off_message": (f"{msg['subject']}\n\n" if msg["subject"] else "") + msg["body"], "handed_off_how": "draft"}
	if channel == "whatsapp":
		values["handed_off_message"] = msg["body"]
		out.update(whatsapp=whatsapp_link(who.get("phone"), msg["body"]), needs_phone=not who.get("phone"))
	else:
		_drop_draft(doc)
		got = _request(doc.space, "email.draft", who, msg, doc.handed_off_thread)
		values.update(handed_off_action=got.get("action"), handed_off_thread=(got.get("result") or {}).get("thread_id") or doc.handed_off_thread)
	frappe.db.set_value("Life Task", doc.name, values)
	doc.add_comment("Info", _("Nudged {0} ({1}). Look again on {2}.").format(who.full_name, values["nudge_count"], values["check_by"]))
	out.update(message=values["handed_off_message"], check_by=str(values["check_by"]), nudges=values["nudge_count"])
	return out


def decide_nudged(task: str, to: str) -> dict:
	"""After two nudges: wait a week more, take it back to the owner's plate, or drop it."""
	doc, _who = _task(task)
	if to == "week":
		doc.check_by = add_days(max(getdate(doc.check_by or today()), getdate(today())), 7)
		doc.nudge_count = 0
	elif to == "plate":
		doc.update({"status": "Open", "waiting_on": None, "waiting_on_person": None, "check_by": None, "due_date": doc.due_date or today()})
	elif to == "drop":
		doc.status = "Dropped"
	else:
		frappe.throw(_("Choose Wait a week, Take it back or Drop it."), title=_("Choice is not valid"))
	doc.save()
	return {"task": doc.name, "status": doc.status, "check_by": str(doc.check_by) if doc.check_by else None}


def said_done(space: str, person: str, what: str | None = None) -> dict:
	"""The owner says the person sent it (by WhatsApp or phone): the best matching waiting task of theirs is Done."""
	who = person_of(space, person)
	rows = frappe.get_all("Life Task", filters={"space": space, "status": "Waiting", "waiting_on_person": who.name, "is_archived": 0}, fields=["name", "title"], order_by="creation desc", limit=20)  # system: the owner's own waiting tasks
	if not rows:
		frappe.throw(_("{0} owes you nothing right now.").format(who.full_name), title=_("Nothing is waiting"))
	words = set((what or "").lower().split())
	best = max(rows, key=lambda r: len(words & set(r.title.lower().split())))
	doc = permissions.get_doc_checked("Life Task", best.name, "write")
	doc.status = "Done"
	doc.save()
	_learn_confirmed(doc, who)
	return {"task": doc.name, "title": doc.title, "who": who.full_name}


# ---------------------------------------------------------------- noticing the answer

def _clear_looks_done(doc):
	doc.looks_done_item = None
	doc.looks_done_note = None


def looks_done(space: str) -> list:
	"""The waiting tasks a reply seems to have settled, which the owner confirms (Needs you, and the Waiting list's first group)."""
	rows = frappe.get_all("Life Task", filters={"space": space, "status": "Waiting", "is_archived": 0, "looks_done_item": ("is", "set")},  # system: the owner's own waiting tasks
		fields=["name", "title", "waiting_on", "waiting_on_person", "looks_done_item", "looks_done_note", "check_by", "modified"], order_by="modified desc", limit=100)
	return [{**r, "check_by": str(r.check_by) if r.check_by else None, "modified": str(r.modified)} for r in rows]


def propose_close(item, task: str, reason: str | None) -> bool:
	"""The model says this capture answers the task. The owner confirms, unless he has taught the Brain to close this person's answers by itself."""
	doc = frappe.get_doc("Life Task", task)
	who = doc.waiting_on_person
	if who and auto_closes(item.space, who):
		frappe.db.set_value("Life Task", task, {"status": "Done", "completed_on": today(), "closed_by_brain": 1, "closed_by_item": item.name})
		_file_attachments(item, task)
		return True
	frappe.db.set_value("Life Task", task, {"looks_done_item": item.name, "looks_done_note": " ".join((reason or doc.waiting_on or "").split())[:140] or None})
	doc.add_comment("Info", _("A reply came in: {0}").format(item.title or item.name))
	return False


def move_check(item, task: str, when, reason: str | None = None) -> bool:
	"""A reply gives a new date ("will send Monday"): the check date moves, with one line on the task."""
	day = when_of(when)
	if not day:
		return False
	doc = frappe.get_doc("Life Task", task)
	frappe.db.set_value("Life Task", task, "check_by", day)
	doc.add_comment("Info", _("Check date moved to {0}: {1}").format(day, " ".join((reason or item.title or "").split())[:140]))
	return True


def _file_attachments(item, task):
	for f in frappe.get_all("File", filters={"attached_to_doctype": "Life Inbox Item", "attached_to_name": item.name}, fields=["file_url", "file_name", "is_private"], limit=20):  # system: the capture's own files, filed with the task
		if not frappe.db.exists("File", {"attached_to_doctype": "Life Task", "attached_to_name": task, "file_url": f.file_url}):
			frappe.get_doc({"doctype": "File", "file_url": f.file_url, "file_name": f.file_name, "is_private": f.is_private, "attached_to_doctype": "Life Task",
				"attached_to_name": task}).insert(ignore_permissions=True)  # system: the same stored file, filed with the task as well


def confirm(task: str) -> dict:
	"""Confirm on Looks done: the task is Done, the item that answered is recorded, its attachment is filed with the task."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	if doc.status != "Waiting" or not doc.looks_done_item:
		frappe.throw(_("{0} is not waiting for a confirmation.").format(doc.title), title=_("Nothing to confirm"))
	item = frappe.get_doc("Life Inbox Item", doc.looks_done_item)
	who = frappe.get_doc("Life Person", doc.waiting_on_person) if doc.waiting_on_person else None
	doc.status = "Done"
	doc.closed_by_item = item.name
	_clear_looks_done(doc)
	doc.save()
	_file_attachments(item, doc.name)
	rule = _learn_confirmed(doc, who) if who else None
	return {"task": doc.name, "status": doc.status, "rule": rule}


def not_yet(task: str) -> dict:
	"""Not yet on Looks done: it stays waiting, and the Brain learns the person's answers are not to be taken as done."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	if not doc.looks_done_item:
		frappe.throw(_("{0} is not waiting for a confirmation.").format(doc.title), title=_("Nothing to confirm"))
	who = doc.waiting_on_person
	_clear_looks_done(doc)
	doc.save()
	if who:
		forget_rule(doc.space, who)
	return {"task": doc.name, "status": doc.status}


# ---------------------------------------------------------------- it learns

def _rule_of(space, person):
	rows = frappe.get_all("Life Rule", filters={"space": space, "action": "Route", "asks_to": "Close", "page_doctype": "Life Person", "page": person}, pluck="name", limit=1)  # system: the owner's space rules
	return rows[0] if rows else None


def auto_closes(space: str, person: str) -> bool:
	name = _rule_of(space, person)
	return bool(name and frappe.db.get_value("Life Rule", name, "enabled"))


def _learn_confirmed(doc, who) -> str | None:
	"""Each confirmation counts for the person; the third in a row, with no Not yet between, makes the rule "close their answers by itself"."""
	if not who or frappe.session.user == permissions.BRAIN_USER:
		return None
	n = cint(who.get("close_confirms")) + 1
	frappe.db.set_value("Life Person", who.name, "close_confirms", n, update_modified=False)
	if n < CONFIRMS_FOR_RULE or _rule_of(doc.space, who.name):
		return None
	return frappe.get_doc({"doctype": "Life Rule", "space": doc.space, "made_by": "Brain", "enabled": 1, "builtin": "close-answers", "action": "Route", "asks_to": "Close",
		"page_doctype": "Life Person", "page": who.name, "learned_from": doc.name}).insert(ignore_permissions=True).name  # system: the Brain makes the rule from the owner's own confirmations


def forget_rule(space: str, person: str):
	"""A Not yet: the count starts again and a rule that closed this person's answers by itself is removed."""
	frappe.db.set_value("Life Person", person, "close_confirms", 0, update_modified=False)
	name = _rule_of(space, person)
	if name:
		frappe.delete_doc("Life Rule", name, ignore_permissions=True, force=True)  # system: the rule the Brain made from the owner's confirmations


# ---------------------------------------------------------------- the waiting list

GROUPS = ("looks_done", "late", "week", "later")


def _row(r, now, week_end) -> dict:
	late = bool(r.check_by and getdate(r.check_by) < now)
	if r.looks_done_item:
		group = "looks_done"
	elif late:
		group = "late"
	elif not r.check_by or getdate(r.check_by) <= week_end:
		group = "week"
	else:
		group = "later"
	how = {"sent": _("by email"), "draft": _("by email") if r.handed_off_channel != "whatsapp" else _("WhatsApp")}.get(r.handed_off_how) or _("tracking only")
	if r.handed_off_how == "sent" and r.handed_off_channel == "whatsapp":
		how = _("WhatsApp")
	if cint(r.nudge_count) >= MAX_NUDGES:
		how = _("nudged twice")
	elif cint(r.nudge_count) == 1:
		how = _("nudged once")
	action = {"looks_done": "confirm", "late": "nudge" if cint(r.nudge_count) < MAX_NUDGES else "decide"}.get(group)
	return {"name": r.name, "title": r.title, "who": r.waiting_on or _("Someone"), "person": r.waiting_on_person, "check_by": str(r.check_by) if r.check_by else None,
		"how": how, "nudges": cint(r.nudge_count), "late": late, "group": group, "action": action, "note": r.looks_done_note if group == "looks_done" else None,
		"item": r.looks_done_item}


def waiting_list(space: str) -> dict:
	"""Everything the owner waits on, in the groups the Waiting list shows: Looks done, Late, This week, Later."""
	rows = frappe.get_list("Life Task", filters={"space": space, "status": "Waiting", "is_archived": 0},
		fields=["name", "title", "waiting_on", "waiting_on_person", "check_by", "handed_off_how", "handed_off_channel", "nudge_count", "looks_done_item", "looks_done_note"],
		order_by="check_by asc, creation asc", limit=300)
	rows = sorted(rows, key=lambda r: (r.check_by is None, str(r.check_by or "")))  # no date last
	now = getdate(today())
	week_end = add_days(now, 6 - now.weekday())
	out = {g: [] for g in GROUPS}
	for r in rows:
		row = _row(r, now, week_end)
		out[row["group"]].append(row)
	return out


def owed(space: str, person: str) -> dict:
	"""A person's layer: what they owe the owner (open waiting tasks on them), and what the owner owes them (open tasks that are about them)."""
	owe_me = [{"name": r.name, "title": r.title, "check_by": str(r.check_by) if r.check_by else None} for r in frappe.get_list("Life Task", filters={"space": space, "status": "Waiting", "waiting_on_person": person, "is_archived": 0}, fields=["name", "title", "check_by"], order_by="check_by asc", limit=50)]
	name = frappe.db.get_value("Life Person", person, "full_name")
	i_owe = []
	if name:
		i_owe = [{"name": r.name, "title": r.title, "due_date": str(r.due_date) if r.due_date else None} for r in frappe.get_list("Life Task", filters={"space": space, "status": ("in", ("Open", "Doing")), "is_archived": 0, "notes_md": ("like", f"%[[{name}]]%")}, fields=["name", "title", "due_date"], order_by="due_date asc", limit=50)]
	return {"owe_me": owe_me, "i_owe": i_owe}


def detail(task: str) -> dict:
	"""What the task layer shows for a hand-off: what was asked, the message, the replies, the nudges, and the WhatsApp link."""
	doc, who = _task(task, write=False)
	notes = frappe.get_all("Comment", filters={"reference_doctype": "Life Task", "reference_name": doc.name, "comment_type": "Info"}, fields=["content", "creation"], order_by="creation asc", limit=50)  # system: the task's own activity lines, read after the task's read check
	replies = [{"text": frappe.utils.strip_html(n.content), "on": str(n.creation)[:16]} for n in notes]
	link = whatsapp_link(who.get("phone"), doc.handed_off_message or "") if who and doc.handed_off_channel == "whatsapp" and doc.handed_off_message else None
	return {"task": doc.name, "person": who.name if who else None, "who": doc.waiting_on, "how": doc.handed_off_how or "", "channel": doc.handed_off_channel or "", "ask": doc.handed_off_ask,
		"message": doc.handed_off_message, "check_by": str(doc.check_by) if doc.check_by else None, "nudges": cint(doc.nudge_count), "activity": replies, "whatsapp": link,
		"needs_phone": bool(doc.handed_off_channel == "whatsapp" and who and not who.get("phone")), "looks_done": {"item": doc.looks_done_item, "note": doc.looks_done_note} if doc.looks_done_item else None,
		"has_email": bool(who and who.email), "status": doc.status}
