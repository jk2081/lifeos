"""The weekly review (set 8): four tabs (Library, Tasks, Goals, Reflect) over one Life Review. People only: agents never
accept, park, discard, plan or lock.

Reads are GET and never write: before the first change the review is computed without being saved, so it can be read where
writes are refused. Every change is a POST that starts (or resumes) the review and saves its state at once.
"""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.utils import parse
from lifeos.review import piles
from lifeos.review.record import TABS, Review


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("The weekly review is for people."), frappe.PermissionError)


def _current(space):
	_person()
	space = permissions.resolve_space(space)
	return Review.current(space, frappe.session.user)


def _open(space):
	"""The review to change: the Open one, or a new one. A locked review cannot change."""
	_person()
	space = permissions.resolve_space(space, write=True)
	rv = Review.start(space, frappe.session.user)
	if rv.doc.status == "Locked":
		frappe.throw(_("This review is locked."))
	return rv


def _ai(space):
	return bool(frappe.db.get_value("Life Space", space, "ask_enabled"))


# ---- the review ----

@frappe.whitelist(methods=["GET"])
def get(space: str | None = None):
	"""The review's header: period, tabs done and openable, the first unfinished tab, the estimate."""
	rv = _current(space)
	return rv.header()


@frappe.whitelist(methods=["POST"])
def start(space: str | None = None, fresh: bool | int = 0):
	"""Resume the Open review or start one (a review locked in the last days is returned as it is, unless `fresh`). Sorting
	the piles may call the assistant, within the cap."""
	_person()
	space = permissions.resolve_space(space, write=True)
	rv = Review.start(space, frappe.session.user, fresh=bool(int(fresh or 0)))
	if rv.doc.status == "Open":
		for key in piles.KEYS:
			piles.PileSet(rv, key).load(ai=_ai(space))
		rv.save()
	return rv.header()


@frappe.whitelist(methods=["POST"])
def visit(space: str | None = None, tab: str | None = None):
	"""Mark a tab as visited (Library is done once visited)."""
	if tab not in TABS:
		frappe.throw(_("Unknown tab."))
	rv = _open(space)
	rv.visit(tab)
	rv.save()
	return rv.header()


# ---- piles ----

@frappe.whitelist(methods=["GET"])
def pile_summary(space: str | None = None, key: str = "tasks"):
	rv = _current(space)
	return piles.PileSet(rv, key).summary()


@frappe.whitelist(methods=["GET"])
def pile_drawer(space: str | None = None, key: str = "tasks", pile: str = "keep"):
	rv = _current(space)
	return piles.PileSet(rv, key).drawer(pile)


@frappe.whitelist(methods=["POST"])
def pile_settle(space: str | None = None, key: str = "tasks", ref: str = "", decision: str = "keep", chase: bool | int | None = None):
	"""Settle one item now: Keep, Park or Let go (Keep with `chase` for a waiting item)."""
	rv = _open(space)
	ps = piles.PileSet(rv, key)
	ps.settle(ref, decision, None if chase is None else bool(int(chase)))
	rv.save()
	return {"summary": ps.summary(), "header": rv.header()}


@frappe.whitelist(methods=["POST"])
def pile_accept(space: str | None = None, key: str = "tasks", pile: str = "keep"):
	"""Apply a pile's decision to every item still in it."""
	rv = _open(space)
	ps = piles.PileSet(rv, key)
	n = ps.accept(pile)
	rv.save()
	return {"done": n, "summary": ps.summary(), "header": rv.header()}


@frappe.whitelist(methods=["POST"])
def pile_undo(space: str | None = None, key: str = "tasks", ref: str | None = None, pile: str | None = None):
	"""Undo one item (`ref`) or a whole pile (`pile`), reversing every exit it recorded."""
	rv = _open(space)
	ps = piles.PileSet(rv, key)
	if ref:
		ps.undo(ref)
	elif pile:
		ps.undo_pile(pile)
	else:
		frappe.throw(_("Say what to undo."))
	rv.save()
	return {"summary": ps.summary(), "header": rv.header()}


def parse_list(value):
	got = parse(value, []) or []
	return got if isinstance(got, list) else []
