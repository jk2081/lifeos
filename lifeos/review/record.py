"""A review's record (set 8): its period, where it was left, and which of its tabs are done.

The period runs from the day after the last locked review to today; with no earlier review it is the last seven days. One
review per user and space is Open at a time, and opening the review again resumes it. Until the first change the review is
not saved: `virtual` gives the same answer without writing, so the review can be read on a site that refuses writes.
"""
import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, today

TABS = ("library", "tasks", "goals", "reflect")
MINUTES = {"library": 10, "tasks": 8, "goals": 12, "reflect": 5}
IDLE_S = 600  # a gap longer than this between two changes is not counted as time spent
RECENT_LOCK_DAYS = 3  # a review locked this recently is shown as done instead of starting the next one
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


class Review:
	"""One Life Review and its tab state."""

	def __init__(self, doc):
		self.doc = doc
		try:
			state = json.loads(doc.tab_state) if isinstance(doc.tab_state, str) and doc.tab_state else doc.tab_state
		except ValueError:
			state = None
		self.state = state if isinstance(state, dict) else {}

	# ---- finding and starting ----

	@classmethod
	def find_open(cls, space, user, kind="Weekly"):
		name = frappe.db.get_value("Life Review", {"space": space, "user": user, "kind": kind, "status": "Open"})
		return cls(frappe.get_doc("Life Review", name)) if name else None

	@classmethod
	def latest_locked(cls, space, user, kind="Weekly"):
		name = frappe.db.get_value("Life Review", {"space": space, "user": user, "kind": kind, "status": "Locked"}, "name",
			order_by="period_end desc, locked_on desc")
		return cls(frappe.get_doc("Life Review", name)) if name else None

	@staticmethod
	def period(space, user, day=None, kind="Weekly"):
		"""(start, end): from the day after the last locked review's period to `day`; the last seven days when there is none."""
		end = getdate(day or today())
		last = frappe.db.get_value("Life Review", {"space": space, "user": user, "kind": kind, "status": "Locked"}, "period_end",
			order_by="period_end desc")
		start = add_days(getdate(last), 1) if last else add_days(end, -6)
		return min(getdate(start), end), end

	@classmethod
	def virtual(cls, space, user, day=None):
		"""The review that would start now, unsaved."""
		start, end = cls.period(space, user, day)
		doc = frappe.new_doc("Life Review")
		doc.update({"space": space, "user": user, "kind": "Weekly", "status": "Open", "period_start": start, "period_end": end,
			"title": title_of(start, end), "tab_state": "{}"})
		return cls(doc)

	@classmethod
	def current(cls, space, user, day=None):
		"""The Open review, or a recently locked one (shown as done), or the unsaved one that would start now."""
		got = cls.find_open(space, user)
		if got:
			got.extend_to(day)
			return got
		last = cls.latest_locked(space, user)
		if last and last.doc.locked_on and (getdate(day or today()) - getdate(last.doc.locked_on)).days < RECENT_LOCK_DAYS:
			return last
		return cls.virtual(space, user, day)

	@classmethod
	def start(cls, space, user, day=None, fresh=False):
		"""Resume the Open review, or start one. A review locked in the last days is returned as it is unless `fresh`."""
		got = cls.find_open(space, user)
		if got:
			if got.extend_to(day):
				got.save()
			return got
		if not fresh:
			last = cls.latest_locked(space, user)
			if last and last.doc.locked_on and (getdate(day or today()) - getdate(last.doc.locked_on)).days < RECENT_LOCK_DAYS:
				return last
		got = cls.virtual(space, user, day)
		got.state["started_on"] = str(now_datetime())[:19]
		got.doc.tab_state = json.dumps(got.state)
		got.doc.insert()
		return got

	def extend_to(self, day=None):
		"""An Open review left for a few days covers up to today. Returns True when it changed."""
		end = getdate(day or today())
		if self.doc.status != "Open" or getdate(self.doc.period_end) >= end:
			return False
		self.doc.period_end = end
		self.doc.title = title_of(self.doc.period_start, end)
		return True

	# ---- saving ----

	@property
	def saved(self):
		return not self.doc.is_new()

	def save(self):
		"""Save the state, counting the time since the last change when it is short enough to be work on the review."""
		if self.doc.status == "Locked" and not self.doc.flags.locking:
			frappe.throw(_("This review is locked."), title=_("Review is locked"))
		now = now_datetime()
		last = self.state.get("last_active")
		if last:
			gap = (now - get_datetime(last)).total_seconds()
			if 0 < gap <= IDLE_S:
				self.state["active_s"] = cint(self.state.get("active_s")) + int(gap)
		self.state["last_active"] = str(now)[:19]
		self.doc.tab_state = json.dumps(self.state, default=str)
		if self.doc.is_new():
			self.doc.insert()
		else:
			self.doc.save()

	def minutes(self):
		return max(1, round(cint(self.state.get("active_s")) / 60))

	# ---- tabs ----

	def done(self):
		"""Which tabs are done: Library once visited; Tasks once no stale task is left to decide; Goals once every cycle
		goal has a next action or a skip with a reason and the stars are exactly three; Reflect once locked."""
		from lifeos.review import goals, stale

		return {"library": bool((self.state.get("visited") or {}).get("library")),
			"tasks": stale.cleared(self),
			"goals": goals.GoalPlan(self).ready()["ok"],
			"reflect": self.doc.status == "Locked"}

	def openable(self, done=None):
		"""A tab ahead opens only when the tabs before it are done, except that Library never blocks."""
		done = done or self.done()
		out, ok = {}, True
		for tab in TABS:
			out[tab] = ok
			if tab != "library":
				ok = ok and done[tab]
		return out

	def first_unfinished(self, done=None):
		done = done or self.done()
		return next((t for t in TABS if not done[t]), "reflect")

	def visit(self, tab):
		if tab in TABS:
			self.state.setdefault("visited", {})[tab] = 1

	def header(self):
		start, end = getdate(self.doc.period_start), getdate(self.doc.period_end)
		days = (end - start).days + 1
		done = self.done()
		return {"name": self.doc.name if self.saved else None, "status": self.doc.status, "kind": self.doc.kind,
			"period_start": str(start), "period_end": str(end), "days": days, "title": self.doc.title or title_of(start, end),
			"period_text": period_text(start, end), "skipped": days > 7, "minutes": sum(MINUTES.values()), "tab_minutes": MINUTES,
			"done": done, "openable": self.openable(done), "first": self.first_unfinished(done), "locked_on": self.doc.locked_on,
			"minutes_spent": self.doc.minutes_spent if self.doc.status == "Locked" else None}


def span_text(start, end):
	"""16 to 22 November; 28 October to 3 November; 28 December 2026 to 3 January 2027."""
	start, end = getdate(start), getdate(end)
	if start.year != end.year:
		return f"{start.day} {MONTHS[start.month - 1]} {start.year} to {end.day} {MONTHS[end.month - 1]} {end.year}"
	if start.month != end.month:
		return f"{start.day} {MONTHS[start.month - 1]} to {end.day} {MONTHS[end.month - 1]}"
	return f"{start.day} to {end.day} {MONTHS[end.month - 1]}"


def period_text(start, end):
	"""The header's line: "Week of 16 to 22 November", or "Covers 9 to 22 November (you skipped last week)"."""
	days = (getdate(end) - getdate(start)).days + 1
	if days <= 7:
		return f"Week of {span_text(start, end)}"
	weeks = (days - 1) // 7
	skipped = "last week" if weeks == 1 else f"the last {weeks} weeks"
	return f"Covers {span_text(start, end)} (you skipped {skipped})"


def title_of(start, end):
	return f"Weekly review, {span_text(start, end)}"
