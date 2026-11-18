"""The weekly review (set 8): four tabs (Library, Tasks, Goals, Reflect) over one Life Review. People only: agents never
accept, park, discard, plan or lock.

Reads are GET and never write: before the first change the review is computed without being saved, so it can be read where
writes are refused. Every change is a POST that starts (or resumes) the review and saves its state at once.
"""
import frappe
from frappe import _

from lifeos import permissions
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
		_refresh(rv)
		for key in piles.KEYS:
			piles.PileSet(rv, key).load(ai=_ai(space))
		from lifeos.review import goals as goals_mod

		gp = goals_mod.GoalPlan(rv)
		gp.prefill(ai=_ai(space))  # next actions and slots, the assistant's within the cap; kept, so it is asked once
		if _ai(space):
			goals_mod.suggest_stars(gp)
			from lifeos.review import lock as lock_mod

			lock_mod.playback(rv)  # last week's note checked against this week, once
		rv.save()
	return rv.header()


def _refresh(rv):
	"""When the review opens: read the calendar (a failure is logged, the review goes on without it), link what was captured
	to the meetings, and find the period's follow-ups, readings waiting and meetings with nothing captured."""
	from lifeos.review import followups, gcal

	user, space = frappe.session.user, rv.doc.space
	frappe.db.savepoint("lifeos_review_calendar")
	try:
		gcal.sync_user(user)
	except Exception:
		frappe.db.rollback(save_point="lifeos_review_calendar")
		frappe.log_error(title="Life OS Google Calendar read")
	followups.refresh(space, user, rv.doc.period_start, rv.doc.period_end, ai=_ai(space))
	from lifeos.review import findings

	findings.revelations(rv)  # the five shown are kept, so acting on one leaves "4 left"


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


# ---- tab 1: Library ----

@frappe.whitelist(methods=["GET"])
def library(space: str | None = None):
	"""The calendar strip, what came in, the Inbox piles' split and the revelations."""
	from lifeos.review import library as lib

	rv = _current(space)
	return lib.data(rv, frappe.session.user)


@frappe.whitelist(methods=["GET"])
def meeting(space: str | None = None, event: str = ""):
	"""A meeting opened: linked records, follow-ups, the goal a task will link to, the previous and next meeting that matters."""
	from lifeos.review import library as lib

	rv = _current(space)
	return lib.meeting(rv, event)


@frappe.whitelist(methods=["GET"])
def meetings_list(space: str | None = None):
	"""The period's meetings that matter (the count in Came in opens this list)."""
	from lifeos.review import library as lib
	from lifeos.review import meetings

	rv = _current(space)
	rows = meetings.in_period(rv.doc.space, rv.doc.period_start, rv.doc.period_end, only_matter=True)
	marks = lib._marks([m.name for m in rows])
	return {"rows": [{"name": m.name, "title": m.subject, "start": str(m.starts_on)[:16], "mark": marks.get(m.name),
		"attendees": [a.get("name") or a["email"] for a in meetings.attendees(m)]} for m in rows]}


@frappe.whitelist(methods=["POST"])
def meeting_mark(space: str | None = None, event: str = "", matters: int | str | None = None):
	"""Mark a meeting as mattering (1) or not (0) by hand; empty goes back to the rule."""
	from lifeos.review import meetings

	rv = _open(space)
	_check_event(rv, event)
	meetings.mark(event, None if matters in (None, "") else bool(int(matters)))
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def meeting_link(space: str | None = None, event: str = "", doctype: str = "", name: str = "", unlink: str | None = None):
	"""Link a record to a meeting by hand, or unlink one (`unlink` names the link)."""
	from lifeos.review import meetings

	rv = _open(space)
	_check_event(rv, event)
	if unlink:
		if frappe.db.get_value("Life Meeting Link", unlink, "event") != event:
			frappe.throw(_("That link is not on this meeting."))
		meetings.unlink(unlink)
	else:
		if doctype not in ("Life Inbox Item", "Life Chat Log", "Life Note", "Life Task"):
			frappe.throw(_("Only captures, chats, notes and tasks link to a meeting."))
		meetings.link(event, doctype, name)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def meeting_plan(space: str | None = None, event: str = "", title: str = "", goal: str | None = None):
	"""A task from "Anything to plan from this meeting?", linked to the meeting and the goal chosen."""
	from lifeos.review import library as lib

	rv = _open(space)
	task = lib.plan_task(rv, event, title, goal)
	rv.save()
	return {"task": task, "header": rv.header()}


@frappe.whitelist(methods=["POST"])
def meeting_done(space: str | None = None, event: str = ""):
	rv = _open(space)
	_check_event(rv, event)
	done = rv.state.setdefault("meetings_done", [])
	if event not in done:
		done.append(event)
	rv.save()
	return {"header": rv.header()}


def _check_event(rv, event):
	if not isinstance(event, str) or frappe.db.get_value("Event", event, "life_space") != rv.doc.space:
		frappe.throw(_("That meeting is not in this review."))


@frappe.whitelist(methods=["POST"])
def finding_act(space: str | None = None, insight: str = "", index: int = 0, title: str | None = None, goal: str | None = None,
		value: float | None = None, reason: str | None = None):
	"""Act on a finding (Make task, Confirm a reading, Someday, Not needed). It leaves every list where it showed."""
	from lifeos.review import findings
	from lifeos.review import library as lib

	rv = _open(space)
	if frappe.db.get_value("Life Insight", insight, "space") != rv.doc.space:
		frappe.throw(_("That finding is not in this space."))
	out = findings.act(insight, index, {"title": title, "goal": goal, "value": value, "reason": reason})
	if out.get("task"):
		lib.note_created(rv, out["task"], goal or frappe.db.get_value("Life Task", out["task"], "goal"), "library")
	rv.save()
	return {**out, "header": rv.header()}


# ---- tab 2: Tasks ----

@frappe.whitelist(methods=["GET"])
def plate(space: str | None = None):
	"""Left your plate: the four Outbox piles for the review's period, and in against out, each a door to its list."""
	from lifeos.review import plate as plate_mod

	rv = _current(space)
	return plate_mod.left_your_plate(rv)


# ---- tab 3: Goals ----

@frappe.whitelist(methods=["GET"])
def goals(space: str | None = None):
	"""The cycle's goals with mark, progress and the prefilled plan; stars; what is left before Next; capacity; next week."""
	from lifeos.review import goals as goals_mod

	rv = _current(space)
	goals_mod.GoalPlan(rv).prefill(ai=False)  # an unsaved review shows the rule prefill; start() saved the assistant's
	return goals_mod.tab(rv)


@frappe.whitelist(methods=["GET"])
def goal(space: str | None = None, goal: str = ""):
	from lifeos.review import goals as goals_mod

	rv = _current(space)
	goals_mod.GoalPlan(rv).prefill(ai=False)
	return goals_mod.detail(rv, goal)


@frappe.whitelist(methods=["POST"])
def goal_save(space: str | None = None, goal: str = "", values: str | dict | None = None):
	"""Save a goal's plan from its drawer: next_action, task, slot (empty for no set time), minutes, who, note."""
	from lifeos.api.utils import parse
	from lifeos.review import goals as goals_mod

	rv = _open(space)
	vals = parse(values, {}) or {}
	if not isinstance(vals, dict):
		frappe.throw(_("values must be an object."))
	goals_mod.GoalPlan(rv).save(goal, {k: vals[k] for k in ("next_action", "task", "slot", "minutes", "who", "note") if k in vals})
	rv.save()
	return {"header": rv.header()}


@frappe.whitelist(methods=["POST"])
def goal_skip(space: str | None = None, goal: str = "", reason: str | None = None, undo: bool | int = 0):
	"""Skip this goal this week (a reason is required), or take the skip back."""
	from lifeos.review import goals as goals_mod

	rv = _open(space)
	gp = goals_mod.GoalPlan(rv)
	if goal not in [g.name for g in gp.goals()]:
		frappe.throw(_("That goal is not in this review."))
	gp.unskip(goal) if int(undo or 0) else gp.skip(goal, reason)
	rv.save()
	return {"header": rv.header()}


@frappe.whitelist(methods=["POST"])
def goal_star(space: str | None = None, goal: str = "", on: bool | int = 1):
	from lifeos.review import goals as goals_mod

	rv = _open(space)
	gp = goals_mod.GoalPlan(rv)
	if goal not in [g.name for g in gp.goals()]:
		frappe.throw(_("That goal is not in this review."))
	gp.set_star(goal, bool(int(on)))
	rv.save()
	return {"header": rv.header()}


@frappe.whitelist(methods=["POST"])
def goal_add(space: str | None = None, goal: str = ""):
	"""Plan one of the other goals in progress this week: it joins the rows."""
	from lifeos.review import goals as goals_mod

	rv = _open(space)
	gp = goals_mod.GoalPlan(rv)
	gp.add_other(goal)
	gp.prefill(ai=_ai(rv.doc.space))
	rv.save()
	return {"header": rv.header()}


# ---- tab 4: Reflect, and Lock the week ----

@frappe.whitelist(methods=["GET"])
def reflect(space: str | None = None):
	"""What went well and what to do differently, the week in numbers, last week's note played back, and what Lock will do."""
	from lifeos.review import lock as lock_mod

	rv = _current(space)
	return lock_mod.reflect(rv)


@frappe.whitelist(methods=["POST"])
def reflect_save(space: str | None = None, went_well: str | None = None, do_differently: str | None = None):
	from lifeos.review import lock as lock_mod

	rv = _open(space)
	lock_mod.save_words(rv, went_well, do_differently)
	rv.save()
	return {"header": rv.header()}


@frappe.whitelist(methods=["POST"])
def lock(space: str | None = None, went_well: str | None = None, do_differently: str | None = None):
	"""Lock the week: schedule and delegate the goal work, pin the top three to Today, store the numbers. Returns the done screen."""
	from lifeos.review import lock as lock_mod

	rv = _open(space)
	lock_mod.save_words(rv, went_well, do_differently)
	out = lock_mod.lock(rv)
	return {**out, "header": rv.header()}


@frappe.whitelist(methods=["GET"])
def done(space: str | None = None):
	"""The done screen of the review locked last."""
	from lifeos.review import lock as lock_mod

	rv = _current(space)
	if rv.doc.status != "Locked":
		frappe.throw(_("This review is not locked yet."))
	return lock_mod.summary(rv)
