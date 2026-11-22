"""The monthly and the 12-week review (issue 47), in the weekly review's shell. People only.

Reads are GET and never write: before the first change the review is computed without being saved. Every change is a POST that
starts (or resumes) the review and saves its state at once; nothing reaches the plan or the cycle until `lock`.
"""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.utils import parse
from lifeos.review import periodic
from lifeos.review.periodic import Periodic


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Reviews are for people."), frappe.PermissionError)


def _clock(at):
	from lifeos import rhythms

	return rhythms.clock(at).date() if at else None


def _current(space, kind, at=None):
	_person()
	space = permissions.resolve_space(space)
	rv = Periodic.current(space, frappe.session.user, periodic.kind_of(kind), _clock(at))
	if rv is None:
		frappe.throw(_("This review is not due."))
	return rv


def _open(space, kind, at=None):
	_person()
	space = permissions.resolve_space(space, write=True)
	rv = Periodic.begin(space, frappe.session.user, periodic.kind_of(kind), _clock(at))
	if rv.doc.status == "Locked":
		frappe.throw(_("This review is locked."))
	return rv


def _saved(rv, **extra):
	rv.save()
	return {"header": rv.header(), **extra}


@frappe.whitelist(methods=["GET"])
def due(space: str | None = None, at: str | None = None):
	"""The reviews due now, in the order to do them, and the past reviews of every kind with their kind."""
	_person()
	space = permissions.resolve_space(space)
	return {"due": periodic.due(space, frappe.session.user, _clock(at)), "past": periodic.past(frappe.session.user, space)}


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None, kind: str = "monthly", at: str | None = None):
	return _current(space, kind, at).header()


@frappe.whitelist(methods=["POST"])
def start(space: str | None = None, kind: str = "monthly", at: str | None = None):
	"""Resume the Open review or start one."""
	return _open(space, kind, at).header()


@frappe.whitelist(methods=["POST"])
def visit(space: str | None = None, kind: str = "monthly", tab: str = "", at: str | None = None):
	rv = _open(space, kind, at)
	rv.visit(tab)
	return _saved(rv)


@frappe.whitelist(methods=["GET"])
def look(space: str | None = None, kind: str = "monthly", at: str | None = None):
	"""Tab 1: the month looked back on, or the cycle's score."""
	return _current(space, kind, at).look()


@frappe.whitelist(methods=["GET"])
def decisions(space: str | None = None, kind: str = "monthly", at: str | None = None):
	"""Tab 2: the goals up for decision, their piles and what is still missing."""
	return _current(space, kind, at).decision_rows()


@frappe.whitelist(methods=["POST"])
def decide(space: str | None = None, kind: str = "monthly", goal: str = "", pile: str = "", date: str | None = None, reason: str | None = None,
	target: float | str | None = None, undo: bool | int = 0, at: str | None = None):
	"""Put a goal in a pile (saved at once): finish with a date, carry (with a new target for a cycle goal), drop with a reason."""
	rv = _open(space, kind, at)
	if int(undo or 0):
		rv.undecide(goal)
	else:
		rv.decide(goal, pile, date, reason, target)
	return _saved(rv, **rv.decision_rows())


@frappe.whitelist(methods=["GET"])
def plan(space: str | None = None, kind: str = "monthly", at: str | None = None):
	"""Tab 3: next month's goals and habits, or the next cycle's dates, goals and lead actions."""
	return _current(space, kind, at).plan()


@frappe.whitelist(methods=["POST"])
def plan_save(space: str | None = None, kind: str = "monthly", extra: str | list | None = None, habits: str | list | None = None,
	edits: str | dict | None = None, confirm: bool | int = 0, at: str | None = None):
	"""Save the plan as it is made. `extra`: the goals added here, in order; `habits`: next month's habits; `edits`: what was
	changed on carried goals (a cycle's Done when, lead actions, target). `confirm` marks the tab done."""
	rv = _open(space, kind, at)
	rv.plan_save(extra=parse(extra), habits=parse(habits), edits=parse(edits), confirm=bool(int(confirm or 0)))
	return _saved(rv, **rv.plan())


@frappe.whitelist(methods=["GET"])
def reflect(space: str | None = None, kind: str = "monthly", at: str | None = None):
	rv = _current(space, kind, at)
	return rv.reflection()


@frappe.whitelist(methods=["POST"])
def reflect_save(space: str | None = None, kind: str = "monthly", went_well: str | None = None, not_well: str | None = None,
	change: str | None = None, at: str | None = None):
	rv = _open(space, kind, at)
	rv.save_words(went_well, not_well, change)
	return _saved(rv)


@frappe.whitelist(methods=["POST"])
def lock(space: str | None = None, kind: str = "monthly", went_well: str | None = None, not_well: str | None = None,
	change: str | None = None, at: str | None = None):
	"""Lock: writes next month's plan, or closes the cycle and makes the next one, and stores the review."""
	rv = _open(space, kind, at)
	rv.save_words(went_well, not_well, change)
	out = periodic.lock(rv)
	return {"header": rv.header(), **out}


@frappe.whitelist(methods=["GET"])
def done(space: str | None = None, kind: str = "monthly", at: str | None = None):
	rv = _current(space, kind, at)
	if rv.doc.status != "Locked":
		frappe.throw(_("This review is not locked yet."))
	return periodic.summary(rv)
