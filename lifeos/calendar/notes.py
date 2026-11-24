"""Notes on calendar events: Frappe's own Comment rows on the Event (issue 99). Never written to Google.

A note hangs on the Event's name, so every re-sync keeps it. A repeating event shares one Event record across its repeats, so
its notes are keyed by the occurrence's date, held in the Comment's own `subject`; an event that does not repeat has no key.
"""
import frappe
from frappe import _
from frappe.utils import get_fullname, getdate

from lifeos import permissions

MAX_NOTE = 5000


def _event(event, write=False):
	"""The Event, checked: the person may read it (write when asked), and it belongs to a space they are in."""
	doc = permissions.get_doc_checked("Event", event, "read")
	if not doc.get("life_space"):
		frappe.throw(_("This event does not belong to a Life OS space."), frappe.PermissionError, title=_("Event is not in a space"))
	permissions.require_space(doc.life_space, write=write)
	return doc


def _key(doc, occurrence):
	"""The occurrence date a note is filed under: only for an event that repeats."""
	return str(getdate(occurrence)) if doc.repeat_this_event and occurrence else ""


def _filters(doc, occurrence):
	f = {"reference_doctype": "Event", "reference_name": doc.name, "comment_type": "Comment"}
	if doc.repeat_this_event:
		f["subject"] = _key(doc, occurrence)
	return f


def _row(c, tasks):
	agent = permissions.is_agent(c.comment_email) if c.comment_email else False
	task = tasks.get(c.name)
	return {"name": c.name, "text": c.content, "by": "You" if c.comment_email == frappe.session.user else (c.comment_by or c.comment_email),
		"agent": bool(agent), "mine": c.comment_email == frappe.session.user, "at": str(c.creation), "task": task}


def listing(event, occurrence=None):
	"""The notes of an event (of one repeat of it), oldest first, so the newest is last."""
	doc = _event(event)
	rows = frappe.get_all("Comment", filters=_filters(doc, occurrence), fields=["name", "content", "comment_email", "comment_by", "creation", "reference_name"],
		order_by="creation asc, name asc", limit=500, ignore_permissions=True)  # system: the event was read-checked above
	made = frappe.get_all("Life Task", filters={"event": doc.name}, fields=["name", "source_url"], limit=500, ignore_permissions=True)  # system: the event was read-checked above
	tasks = {t.source_url[5:]: t.name for t in made if (t.source_url or "").startswith("note:")}
	return [_row(frappe._dict(r), tasks) for r in rows]


def add(event, text, occurrence=None):
	doc = _event(event, write=True)
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Write the note first."), title=_("Note is empty"))
	if len(text) > MAX_NOTE:
		frappe.throw(_("A note can be {0} characters at most.").format(MAX_NOTE), title=_("Note is too long"))
	c = frappe.get_doc({"doctype": "Comment", "comment_type": "Comment", "reference_doctype": "Event", "reference_name": doc.name,
		"subject": _key(doc, occurrence), "content": text, "comment_email": frappe.session.user, "comment_by": get_fullname(frappe.session.user)})
	c.insert(ignore_permissions=True)  # system: the space check above is the rule; Comment itself asks for desk roles
	return _row(c, {})


def _own(note):
	"""A note the person may change: their own, never by an agent, on an event of a space they write to."""
	c = frappe.get_doc("Comment", note)
	if c.reference_doctype != "Event" or c.comment_type != "Comment":
		frappe.throw(_("Note not found."), frappe.DoesNotExistError, title=_("Note not found"))
	_event(c.reference_name, write=True)
	if permissions.is_agent():
		frappe.throw(_("Agents can add notes but not change or remove them."), frappe.PermissionError, title=_("Agents cannot change notes"))
	return c


def update(note, text):
	c = _own(note)
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Write the note first."), title=_("Note is empty"))
	c.db_set("content", text[:MAX_NOTE])
	return _row(c, {})


def remove(note):
	c = _own(note)
	frappe.delete_doc("Comment", c.name, ignore_permissions=True, force=True)  # system: checked by _own
	return {"deleted": note}


def make_task(note):
	"""A task titled with the note, linked to the event. Once for each note."""
	c = frappe.get_doc("Comment", note)
	if c.reference_doctype != "Event" or c.comment_type != "Comment":
		frappe.throw(_("Note not found."), frappe.DoesNotExistError, title=_("Note not found"))
	ev = _event(c.reference_name, write=True)
	url = f"note:{c.name}"
	if name := frappe.db.get_value("Life Task", {"event": ev.name, "source_url": url}, "name"):
		return {"task": name, "made": False}
	title = " ".join((frappe.utils.strip_html(c.content or "")).split())[:140]
	task = frappe.get_doc({"doctype": "Life Task", "space": ev.life_space, "title": title, "status": "Open", "event": ev.name, "source_url": url}).insert()
	return {"task": task.name, "made": True}
