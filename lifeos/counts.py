"""One rule for every number (UX fixes, set 5): each count is paired with the list that shows exactly those rows.

A count is {"n", "to": {"path", "query"}, "label"}. `n` is worked out by calling the same list method, with the same
arguments, that the screen at `to` calls for that query, so the number and the rows cannot disagree. Tasks, the most
counted, use `tasks.total`, which builds the same WHERE as `tasks.list` without fetching rows. Today's Open band,
Reset, Someday and the sidebar take every number from here; Ask's `counts` tool does too.
"""
import json

import frappe
from frappe.utils import add_days, add_months, cint, getdate, today

from lifeos.api.utils import area_filter, lens_area

OPEN = ["Open", "Doing", "Waiting"]


def rules():
	s = frappe.get_cached_doc("Life Settings")

	def val(field, default, low=1):
		v = s.get(field)
		return default if v in (None, "") else max(cint(v), low)

	return {"stuck_after_days": val("stuck_after_days", 30), "stuck_limit": val("stuck_limit", 50, 0),
		"open_task_goal": val("open_task_goal", 100, 0), "someday_review_months": val("someday_review_months", 3)}


def ago(days):
	return str(add_days(getdate(today()), -int(days)))


def _door(n, path, query, label, area=None):
	"""A count and its list. A link with no condition of its own carries all=1, so the list shows exactly that and not a
	view remembered from before (the rule of UX fixes, set 1)."""
	query = {k: v for k, v in {**query, "area": area}.items() if v not in (None, "")}
	if "f" not in query:
		query["all"] = 1
	return {"n": int(n or 0), "to": {"path": path, "query": query}, "label": label}


def _f(*conds):
	return json.dumps([list(c) for c in conds]) if conds else None


# ---- tasks: the Tasks screen with All and a status condition, so Waiting is included and Someday is not ----

def tasks(space, area, label, conds=(), due=None):
	conds = [("status", "in", OPEN), *conds]
	from lifeos.api import tasks as task_api

	n = task_api.total(space, status="all", area=area, due=due, filters=_f(*conds))
	return _door(n, "/tasks", {"status": "all", "due": due, "view": "list", "f": _f(*conds)}, label, area)


def untouched(lo=None, hi=None, field="last_touched_on"):
	"""Conditions for "untouched for at least lo and fewer than hi days" on a date field."""
	out = []
	if lo:
		out.append((field, "<=", ago(lo)))
	if hi:
		out.append((field, ">", ago(hi)))
	return out


def open_tasks(space, area=None):
	return tasks(space, area, "Open tasks")


def stuck_tasks(space, area=None):
	d = rules()["stuck_after_days"]
	return tasks(space, area, f"untouched {d}+ days", untouched(d))


def overdue_tasks(space, area=None):
	return tasks(space, area, "Overdue", due="overdue")


def due_today_tasks(space, area=None):
	return tasks(space, area, "Due today", due="today")


# ---- projects ----

def projects(space, area, label, conds=(), status="Active"):
	from lifeos.api import projects as project_api

	n = project_api.list(space=space, area=area, status=None if status == "all" else status, include_done=1 if status == "all" else 0,
		filters=_f(*conds), page_length=1)["total"]
	return _door(n, "/projects", {"status": status, "view": "list", "f": _f(*conds)}, label, area)


def active_projects(space, area=None):
	return projects(space, area, "Active projects")


def idle_projects(space, area=None):
	d = rules()["stuck_after_days"]
	return projects(space, area, f"idle {d}+ days", untouched(d, field="last_activity_on"))


# ---- goals ----

def goals(space, area, label, names=None, state="in_progress"):
	from lifeos.api import goals as goal_api

	conds = [("name", "in", sorted(names))] if names is not None else []
	if names is not None and not names:
		return _door(0, "/goals", {"status": state, "f": _f(("name", "in", ["-"]))}, label, area)
	n = goal_api.list(space=space, area=area, state=state, filters=_f(*conds), page_length=1)["total"]
	return _door(n, "/goals", {"status": state, "f": _f(*conds)}, label, area)


def goals_in_progress(space, area=None):
	return goals(space, area, "Goals in progress")


def goal_sets(space, area=None):
	"""In-progress 12 Week Year goals of the active cycle with no ticks in the last three weeks (once three weeks have
	passed), and in-progress goals with no tasks and no open actions."""
	from lifeos import journal

	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "start_date", "end_date"], as_dict=True)
	no_ticks = []
	if cycle:
		week = journal.week_of(cycle, getdate(today()))
		if week >= 4:
			since = add_days(getdate(today()), -21)
			in_progress = frappe.get_all("Life Goal", filters={"cycle": cycle.name, "outcome": "In Progress", "is_someday": 0}, pluck="name")
			ticked = set(frappe.get_all("Life Action Log", filters={"goal": ("in", in_progress or ["-"]), "date": [">=", since],
				"count": [">", 0]}, pluck="goal", distinct=True))
			no_ticks = [g for g in in_progress if g not in ticked]
	no_tasks = frappe.db.sql_list("""select g.name from `tabLife Goal` g where g.space=%s and g.outcome='In Progress' and g.is_someday=0
		and not exists (select 1 from `tabLife Task` t where t.goal = g.name and t.status in ('Open', 'Doing', 'Waiting', 'Done'))
		and not exists (select 1 from `tabLife Goal Action` a where a.parent = g.name and a.status = 'Open')""", space)
	return no_ticks, no_tasks


def goals_no_ticks(space, area=None):
	return goals(space, area, "with no ticks for 3 weeks", goal_sets(space, area)[0])


def goals_no_tasks(space, area=None):
	return goals(space, area, "with no tasks", goal_sets(space, area)[1])


# ---- inbox ----

def inbox(space, area, label, conds=()):
	from lifeos.api import inbox as inbox_api

	n = inbox_api.list(space=space, area=area, status=json.dumps(["To Review"]), filters=_f(*conds), page_length=1)["total"]
	return _door(n, "/inbox", {"status": "To Review", "f": _f(*conds)}, label, area)


def inbox_to_review(space, area=None):
	return inbox(space, area, "Items to review")


def inbox_old(space, area=None):
	return inbox(space, area, "older than a week", [("received_on", "<", ago(7))])


# ---- notes and sources ----

def notes_and_sources(space, area=None):
	from lifeos.api import timeline

	cond = ("kind", "in", ["Note", "Inbox", "Chat"])
	n = timeline.get(space=space, area=area, filters=_f(cond), page_length=1)["total"]
	return _door(n, "/timeline", {"f": _f(cond)}, "Notes and sources", area)


def notes(space, area, label, conds=()):
	from lifeos.api import library

	# My notes, as the Notes screen lists them; wiki pages are kept by the agent and the Wiki's Health tab
	n = library.list(space=space, area=area, filters=_f(*conds), page_length=1)["total"]
	return _door(n, "/library", {"view": "list", "f": _f(*conds)}, label, area)


def notes_unopened(space, area, days=90):
	return notes(space, area, f"notes not opened in {days} days", untouched(days, field="last_opened_on"))


# ---- someday ----

def someday(space, area, tab="all", conds=(), label="Someday"):
	from lifeos.api import someday as someday_api

	n = someday_api.list(space=space, area=area, tab=tab, filters=_f(*conds), page_length=1)["total"]
	return _door(n, "/someday", {"tab": None if tab == "all" else tab, "f": _f(*conds)}, label, area)


def someday_due(space, area=None):
	return someday(space, area, "due", label="Due for review")


# ---- the sets each screen shows ----

def open_band(space, area=None):
	r = rules()
	stuck = stuck_tasks(space, area)
	no_ticks, no_tasks = goal_sets(space, area)
	return {
		"open_tasks": open_tasks(space, area), "stuck": stuck, "over_limit": stuck["n"] > r["stuck_limit"], "rules": r,
		"projects": active_projects(space, area), "idle_projects": idle_projects(space, area),
		"goals": goals_in_progress(space, area),
		"goals_no_ticks": goals(space, area, "with no ticks for 3 weeks", no_ticks), "goals_no_tasks": goals(space, area, "with no tasks", no_tasks),
		"inbox": inbox_to_review(space, area), "inbox_old": inbox_old(space, area),
		"notes_sources": notes_and_sources(space, area), "notes_unopened": notes_unopened(space, area),
	}


def sidebar(space, area=None):
	r = rules()
	stuck = stuck_tasks(space, area)
	return {"inbox": inbox_to_review(space, area), "tasks": tasks(space, area, "due today or overdue", due="today,overdue"),
		"someday": someday(space, area), "stuck": stuck, "over_limit": stuck["n"] > r["stuck_limit"]}


BUCKETS = [("under_30", None, 30), ("30_90", 30, 90), ("90_180", 90, 180), ("over_180", 180, None), ("total", None, None)]


def inventory(space, area=None):
	"""Reset's Inventory: rows by kind, columns by time untouched. Every cell is a count with its list."""
	from lifeos.api import someday as someday_api

	rows = []
	def row(key, label, make):
		rows.append({"key": key, "label": label, "cells": {b: make(lo, hi) for b, lo, hi in BUCKETS}})
	row("tasks", "Open tasks", lambda lo, hi: tasks(space, area, "Open tasks", untouched(lo, hi)))
	row("projects", "Projects", lambda lo, hi: projects(space, area, "Active projects", untouched(lo, hi, "last_activity_on")))
	row("goals", "Goals", lambda lo, hi: _goal_cell(space, area, lo, hi))
	row("inbox", "Inbox items", lambda lo, hi: inbox(space, area, "Items to review", _received(lo, hi)))
	row("notes", "Notes not opened", lambda lo, hi: notes(space, area, "Notes", untouched(lo, hi, "last_opened_on")))
	row("chats", "Chats with open items", lambda lo, hi: _chats(space, area, lo, hi))
	row("someday", "Someday (since parked)", lambda lo, hi: someday(space, area, "all", untouched(lo, hi, "someday_on"), "Someday"))
	return {"rows": rows, "columns": [{"key": "under_30", "label": "Under 30 days"}, {"key": "30_90", "label": "30 to 90"},
		{"key": "90_180", "label": "90 to 180"}, {"key": "over_180", "label": "Over 180"}, {"key": "total", "label": "Total"}],
		"stuck_after_days": rules()["stuck_after_days"]}


def _received(lo, hi):
	out = []
	if lo:
		out.append(("received_on", "<", ago(lo - 1)))
	if hi:
		out.append(("received_on", ">=", ago(hi - 1)))
	return out


def _goal_cell(space, area, lo, hi):
	# a goal's last change: its own `modified` (ticks and edits both save it or its action log)
	conds = []
	if lo:
		conds.append(("modified", "<", ago(lo - 1)))
	if hi:
		conds.append(("modified", ">=", ago(hi - 1)))
	from lifeos.api import goals as goal_api

	n = goal_api.list(space=space, area=area, state="in_progress", filters=_f(*conds), page_length=1)["total"]
	return _door(n, "/goals", {"status": "in_progress", "f": _f(*conds)}, "Goals in progress", area)


def _chats(space, area, lo, hi):
	from lifeos.api import sources

	conds = []
	if lo:
		conds.append(("record_date", "<=", ago(lo)))
	if hi:
		conds.append(("record_date", ">", ago(hi)))
	n = sources.list(space=space, area=area, tab="chats", open_items=1, filters=_f(*conds), page_length=1)["total"]
	return _door(n, "/sources", {"tab": "chats", "open_items": 1, "f": _f(*conds)}, "Chats with open items", area)


def get(space=None, which="open_band", area=None):
	"""The counts of one screen: open_band (Today), sidebar, inventory (Reset)."""
	from lifeos import permissions

	space = permissions.resolve_space(space)
	area = lens_area(area)
	fn = {"open_band": open_band, "sidebar": sidebar, "inventory": inventory}.get(which)
	if not fn:
		frappe.throw(frappe._("Unknown set of counts."))
	return fn(space, area)
