"""The Outbox (set 7): a record of everything that leaves the owner's plate, in four piles: Done, Delegated, Parked, Discarded.

Exits are written by the document hooks below and nowhere else. Each record's state says which pile it is in, if any
(`pile_of`); when a save moves it into a pile an exit is recorded, when a save takes it out again (a task reopened, an item
brought back from Someday, a record restored from the trash) its exit is marked `reversed` and no longer counts. A record has
at most one exit that counts: moving from one pile to another (Waiting, then Done) reverses the earlier exit.

"In" for a period is what arrived: captures received, plus tasks and goals created directly (not from a capture, not carried), so nothing is counted twice.
"""
import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

KIND = {"Life Task": "Task", "Life Goal": "Goal", "Life Inbox Item": "Capture"}
DOCTYPE = {v: k for k, v in KIND.items()}
PILES = ("Done", "Delegated", "Parked", "Discarded")
SELF = {"me", "myself", "self", "owner", "i"}


def _owner_names(space):
	"""The ways the space's owner may be written in `waiting_on`: a task waiting on them is not delegated."""
	user = frappe.db.get_value("Life Space", space, "owner_user")
	names = set(SELF)
	if user:
		full, first = frappe.db.get_value("User", user, ["full_name", "first_name"]) or (None, None)
		names |= {(full or "").strip().lower(), (first or "").strip().lower(), user.lower()}
	return names - {""}


def pile_of(doc):
	"""The pile a record's current state puts it in, or None while it is on the plate."""
	dt = doc.doctype
	if dt == "Life Task":
		s = doc.get("status")
		if s == "Done":
			return "Done"
		if s == "Someday":
			return "Parked"
		if s == "Dropped":
			return "Discarded"
		if s == "Waiting" and (doc.get("waiting_on") or "").strip() and (doc.get("waiting_on") or "").strip().lower() not in _owner_names(doc.space):
			return "Delegated"
		return None
	if dt == "Life Goal":
		if doc.get("is_someday"):
			return "Parked"
		outcome = doc.get("outcome") or "In Progress"
		if outcome in ("Achieved", "Partly Achieved"):
			return "Done"
		if outcome in ("Not Achieved", "Dropped"):
			return "Discarded"
		return None
	if dt == "Life Inbox Item":
		if doc.get("status") != "Done":
			return None
		decided = frappe.get_all("Life Proposal", filters={"inbox_item": doc.name}, pluck="status")
		if "Accepted" in decided or (doc.get("intent") or "Process") != "Process":
			return "Done"
		if frappe.db.exists("Life Note", {"inbox_item": doc.name, "is_someday": 1}):
			return "Parked"
		if decided and all(s == "Rejected" for s in decided):
			return "Discarded"
		return "Done"  # a capture kept with nothing to decide
	return None


def _title(doc):
	return (doc.get("title") or doc.name)[:140]


def active(doctype, name):
	return frappe.get_all("Life Exit", filters={"record_doctype": doctype, "record_name": name, "reversed": 0}, fields=["name", "pile"],
		order_by="exited_on desc")


def reverse(doctype, name, pile=None, on=None):
	"""Mark the exits of a record that still count as reversed (all of them, or those of one pile)."""
	for e in active(doctype, name):
		if pile and e.pile != pile:
			continue
		frappe.db.set_value("Life Exit", e.name, {"reversed": 1, "reversed_on": on or now_datetime()}, update_modified=False)


def record(doc, pile, on=None, note=None, kind=None):
	"""Write an exit for a record entering a pile. An earlier exit that still counts is reversed first, so a record is
	counted out once. Returns the exit's name."""
	if pile not in PILES:
		return None
	current = active(doc.doctype, doc.name)
	if current and current[0].pile == pile and len(current) == 1:
		return current[0].name
	reverse(doc.doctype, doc.name, on=on)
	area = doc.get("area") if doc.get("area") and frappe.db.get_value("Life Area", doc.get("area"), "space") == doc.space else None
	e = frappe.get_doc({"doctype": "Life Exit", "space": doc.space, "area": area, "record_doctype": doc.doctype,
		"record_name": doc.name, "title": _title(doc), "kind": kind or KIND[doc.doctype], "pile": pile, "exited_on": on or now_datetime(),
		"exited_by": frappe.session.user if frappe.session.user not in ("Guest",) else None, "note": note,
		"auto_rule": doc.flags.get("auto_rule") or frappe.flags.get("lifeos_auto_rule")})
	e.insert(ignore_permissions=True)  # system: the outbox entry is written for the Brain after the person's own check
	return e.name


# ---- document hooks (hooks.py) ----

def on_update(doc, method=None):
	if doc.doctype == "Life Note":
		# a capture parked as a Someday note is back on the plate once the note is brought back
		before = doc.get_doc_before_save()
		if doc.inbox_item and before and before.is_someday and not doc.is_someday and not doc.flags.get("no_exit"):
			reverse("Life Inbox Item", doc.inbox_item, "Parked")
		return
	if doc.doctype not in KIND or doc.flags.get("no_exit"):
		return
	before = doc.get_doc_before_save()
	old = pile_of(before) if before else None
	new = pile_of(doc)
	if new == old:
		return
	if new:
		record(doc, new)
	else:
		reverse(doc.doctype, doc.name)


def after_insert(doc, method=None):
	"""A record restored from the trash: its Discarded exit no longer counts. A note parked from a capture: the capture's
	exit is worked out again when the capture is saved."""
	if doc.doctype not in KIND:
		return
	if doc.flags.get("from_restore"):
		reverse(doc.doctype, doc.name, "Discarded")
		pile = pile_of(doc)
		if pile:
			record(doc, pile)


def on_trash(doc, method=None):
	"""Deleted (to the trash, or purged from Someday): Discarded."""
	if doc.doctype not in KIND or doc.flags.get("no_exit") or frappe.flags.get("lifeos_no_exit"):
		return
	if active(doc.doctype, doc.name):  # it had already left the plate (a done task deleted later): that exit stands
		return
	record(doc, "Discarded")


# ---- reading ----

PERIODS = ("week", "month", "12weeks")


def period_bounds(period="week", on=None):
	"""[start, end) datetimes of this week (Monday on), this month, or the last 12 weeks (from the Monday 11 weeks ago)."""
	day = getdate(on or today())
	period = period if period in PERIODS else "week"
	monday = add_days(day, -day.weekday())
	if period == "month":
		start = day.replace(day=1)
	elif period == "12weeks":
		start = add_days(monday, -77)
	else:
		start = monday
	return get_datetime(str(start)), get_datetime(str(add_days(day, 1)))
