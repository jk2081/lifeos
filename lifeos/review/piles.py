"""Needs you and the three piles (set 8): Keep, Park in Someday, Let go. One component for Library (Inbox items) and Tasks
(stuck tasks and tasks waiting on others).

The assistant sorts first, each item with a one-line reason (short model, batched, within the cap); without a key the rules
below sort. Only what cannot be decided goes under Needs you, at most five; the rest of those join Keep as "not sure". A row
settles one item at once; accepting a pile settles every item still in it. Every decision and its Undo are kept in the
review's state, so an Undo reverses exactly what was done (and the Outbox exits with it).
"""
import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from lifeos.review import pile_actions

KEYS = ("inbox", "tasks")
PILES = ("keep", "park", "letgo")
NEEDS = "needs"
NEEDS_MAX = 5
CHASE_AFTER = 7  # a waiting item asked more than this many days ago is kept as Chase
PARK_AFTER, LET_GO_AFTER = 60, 120  # a stuck task untouched this long is parked, then let go


class PileSet:
	"""The piles of one tab (`inbox` or `tasks`) inside a review's state."""

	def __init__(self, review, key):
		if key not in KEYS:
			frappe.throw(_("Unknown piles."))
		self.review, self.key = review, key
		self.space = review.doc.space
		self.data = review.state.setdefault("piles", {}).setdefault(key, {"items": [], "accepted": {}})
		self._loaded = False

	# ---- keeping the piles current ----

	def load(self, ai=False):
		"""Bring the piles up to date: unsettled items that left the plate elsewhere drop out, new ones are sorted in."""
		if self._loaded:
			return self
		from lifeos.review import pile_sort

		cands = {c["ref"]: c for c in pile_sort.candidates(self.space, self.key, self.review.doc.period_start)}
		kept = []
		for it in self.data["items"]:
			if it.get("settled") or it["ref"] in cands:
				if it["ref"] in cands:
					it.update({k: cands[it["ref"]][k] for k in ("title", "age", "area", "area_name", "sensitive")})
				kept.append(it)
		have = {it["ref"] for it in kept}
		new = [c for c in cands.values() if c["ref"] not in have]
		if new:
			by = pile_sort.sort(self.space, new, ai=ai)
			self.data["by"] = "assistant" if by == "assistant" or self.data.get("by") == "assistant" else "rules"
		self.data["items"] = kept + new
		self._cap_needs()
		self._loaded = True
		return self

	def _cap_needs(self):
		needs = [it for it in self.data["items"] if it["pile"] == NEEDS and not it.get("settled")]
		needs.sort(key=lambda it: -cint(it.get("age")))
		for it in needs[NEEDS_MAX:]:
			it.update({"pile": "keep", "orig": "keep", "reason": "Not sure; kept for now."})

	# ---- reading ----

	def items(self):
		return self.load().data["items"]

	def find(self, ref):
		it = next((i for i in self.items() if i["ref"] == ref), None)
		if not it:
			frappe.throw(_("That item is not in the review's piles any more."))
		return it

	def cleared(self):
		return all(it.get("settled") for it in self.items())

	def summary(self):
		"""What the tab shows: Needs you, and per pile its count, the first three items, and its done state."""
		items = self.items()
		piles = {}
		for p in PILES:
			members = [i for i in items if i["pile"] == p]
			unsettled = [i for i in members if not i.get("settled")]
			acc = self.data["accepted"].get(p)
			moved = {}
			for i in items:
				if i.get("moved_from") == p and i["pile"] != p:
					moved[i["pile"]] = moved.get(i["pile"], 0) + 1
			piles[p] = {"count": len(members), "left": len(unsettled), "first": [_row(i) for i in (unsettled or members)[:3]],
				"accepted": acc, "moved": moved, "done": bool(members) and not unsettled, "empty": not members,
				"sources": _sources(members)}
		needs = [i for i in items if i["pile"] == NEEDS or i.get("moved_from") == NEEDS]
		left = sum(1 for i in items if not i.get("settled"))
		return {"key": self.key, "by": self.data.get("by") or "rules", "piles": piles, "needs": [_row(i) for i in needs],
			"needs_left": sum(1 for i in needs if not i.get("settled")), "total": len(items), "left": left,
			"settled": len(items) - left, "cleared": left == 0}

	def drawer(self, pile):
		"""Every item in a pile, and those moved out of it (shown as moved, with Undo)."""
		if pile not in (*PILES, NEEDS):
			frappe.throw(_("Unknown pile."))
		rows = [_row(i) for i in self.items() if i["pile"] == pile or i.get("moved_from") == pile]
		return {"pile": pile, "rows": rows, "sources": _sources([i for i in self.items() if i["pile"] == pile]),
			"needs": sum(1 for i in self.items() if i["pile"] == NEEDS and not i.get("settled")),
			"left": sum(1 for r in rows if not r["settled"] and r["pile"] == pile)}

	# ---- deciding ----

	def settle(self, ref, decision, chase=None):
		"""Settle one item now. A decision other than its pile's moves it to that pile."""
		it = self.find(ref)
		if it.get("settled"):
			frappe.throw(_("Already settled. Undo it first."))
		chase = it.get("chase") if chase is None else bool(chase)
		ops = pile_actions.apply(it, decision, chase=chase, from_needs=it["pile"] == NEEDS)
		if decision != it["pile"]:
			it["moved_from"] = it["pile"]
			it["pile"] = decision
		it["settled"] = {"decision": decision, "chase": bool(chase), "via": "row", "on": str(now_datetime())[:19], "undo": ops}
		return it

	def accept(self, pile):
		"""Apply a pile's decision to every item still in it."""
		if pile not in PILES:
			frappe.throw(_("Unknown pile."))
		n = 0
		for it in self.items():
			if it["pile"] == pile and not it.get("settled"):
				ops = pile_actions.apply(it, pile, chase=it.get("chase"), from_needs=False)
				it["settled"] = {"decision": pile, "chase": bool(it.get("chase")), "via": "pile", "on": str(now_datetime())[:19], "undo": ops}
				n += 1
		self.data["accepted"][pile] = {"on": str(now_datetime())[:19], "n": sum(1 for i in self.items() if i["pile"] == pile)}
		return n

	def undo(self, ref):
		it = self.find(ref)
		if not it.get("settled"):
			return it
		pile_actions.undo(it["settled"].get("undo"))
		it["settled"] = None
		if it.get("moved_from"):
			it["pile"] = it.pop("moved_from")
		self.data["accepted"].pop(it["pile"], None)
		return it

	def undo_pile(self, pile):
		"""Undo a whole pile: what it settled, and the items moved out of it, newest first."""
		mine = [i for i in self.items() if i.get("settled") and ((i["pile"] == pile) or i.get("moved_from") == pile)]
		for it in sorted(mine, key=lambda i: i["settled"]["on"], reverse=True):
			self.undo(it["ref"])
		self.data["accepted"].pop(pile, None)
		return len(mine)

	def split(self):
		"""The suggested split, for the Library's Inbox line: Accept 5 · Park 4 · Let go 2 · 0 need you."""
		items = self.items()
		return {p: sum(1 for i in items if i["pile"] == p and not i.get("settled")) for p in (*PILES, NEEDS)}


def _row(i):
	s = i.get("settled") or None
	return {"ref": i["ref"], "doctype": i["doctype"], "name": i["name"], "title": i["title"], "source": i["source"], "area": i.get("area"),
		"area_name": i.get("area_name"), "age": i.get("age"), "reason": i.get("reason"), "pile": i["pile"], "chase": bool(i.get("chase")),
		"waiting_on": i.get("waiting_on"), "sensitive": bool(i.get("sensitive")), "moved_from": i.get("moved_from"),
		"settled": {"decision": s["decision"], "via": s["via"], "chase": s.get("chase")} if s else None}


def _sources(items):
	out = {}
	for i in items:
		out[i["source"]] = out.get(i["source"], 0) + 1
	return out


def cleared_count(review):
	"""Items settled in the review's piles, for the week's numbers."""
	return sum(1 for key in KEYS for i in (review.state.get("piles", {}).get(key) or {}).get("items", []) if i.get("settled"))
