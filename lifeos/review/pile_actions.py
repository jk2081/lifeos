"""What a pile decision does to one item, through the existing transitions, so the Outbox records it (set 8).

Keep: an Inbox item's proposals are accepted; a stuck task stays open (touched, and due this week when chosen under Needs
you); a waiting item marked Chase gets a task "Chase <person>: <title>" due today. Park: the item moves to Someday. Let go:
the task is dropped, the Inbox item discarded to the trash, a waiting item marked answered (done).

Each call returns the operations Undo needs. They are kept on the server, in the review's state, never taken from the browser.
"""
import frappe
from frappe import _
from frappe.utils import add_days, today

from lifeos import permissions

DECISIONS = ("keep", "park", "letgo")
OPEN = ("Open", "Doing", "Waiting")
THIS_WEEK_DAYS = 6


def apply(item, decision, chase=False, from_needs=False):
	"""Carry out one decision on one item; returns the undo operations."""
	if decision not in DECISIONS:
		frappe.throw(_("Choose Keep, Park or Let go."))
	if item["doctype"] == "Life Inbox Item":
		return _inbox(item, decision)
	if item["doctype"] == "Life Task":
		return _task(item, decision, chase, from_needs)
	frappe.throw(_("The review cannot decide on this record."))


def _inbox(item, decision):
	from lifeos import old_inbox

	doc = permissions.get_doc_checked("Life Inbox Item", item["name"], "delete" if decision == "letgo" else "write")
	if doc.status not in ("To Review", "New") or (doc.status == "New" and doc.claimed_by):
		frappe.throw(_("{0} has already been dealt with.").format(doc.title or doc.name))
	log = {"keep": old_inbox.accept, "park": old_inbox.park, "letgo": old_inbox.discard}[decision](doc)
	return [{"op": "inbox", "log": log}]


def _task(item, decision, chase, from_needs):
	from lifeos.api import reset, someday

	doc = permissions.get_doc_checked("Life Task", item["name"], "write")
	if doc.status not in OPEN:
		frappe.throw(_("{0} is no longer open.").format(doc.title))
	ops = [{"op": "snap", "snap": reset._snap(doc), "touched": str(doc.last_touched_on) if doc.last_touched_on else None}]
	if decision == "park":
		someday.park_doc(doc)
	elif decision == "letgo":
		# a waiting item let go has been answered; a stuck task is dropped
		doc.status = "Done" if item.get("source") == "Waiting" else "Dropped"
		doc.save()
	else:
		if chase and item.get("source") == "Waiting":
			ops.append({"op": "delete_task", "name": _chase(doc).name})
		if from_needs and item.get("source") == "Stuck" and (not doc.due_date or str(doc.due_date) < today()):
			doc.due_date = add_days(today(), THIS_WEEK_DAYS)
		doc.save()  # a save touches the task, so it is not stuck again next week
	return ops


def _chase(doc):
	who = (doc.waiting_on or "").strip() or "them"
	return frappe.get_doc({"doctype": "Life Task", "space": doc.space, "title": f"Chase {who}: {doc.title}"[:140], "status": "Open",
		"due_date": today(), "area": doc.area or None, "goal": doc.goal or None}).insert()


def undo(ops):
	"""Put back what `apply` did, newest first."""
	from lifeos import old_inbox
	from lifeos.api import someday

	for op in reversed(ops or []):
		kind = op.get("op")
		if kind == "inbox":
			old_inbox.undo([op.get("log") or {}])
		elif kind == "delete_task":
			name = op.get("name")
			if isinstance(name, str) and frappe.db.exists("Life Task", name):
				permissions.get_doc_checked("Life Task", name, "delete")
				frappe.local.lifeos_no_exit = True  # the chase task was made by the decision being undone: no Discarded exit
				try:
					frappe.delete_doc("Life Task", name, ignore_permissions=True, delete_permanently=True)
				finally:
					frappe.local.lifeos_no_exit = False
		elif kind == "snap":
			snap = op.get("snap") or {}
			someday.restore_snapshot(snap)
			if snap.get("doctype") == "Life Task" and op.get("touched"):
				frappe.db.set_value("Life Task", snap["name"], "last_touched_on", op["touched"], update_modified=False)
