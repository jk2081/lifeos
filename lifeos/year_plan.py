"""Today > Year (issue 16): the year as a timeline, and the week's goal work for Today > Week.

The API methods in lifeos.api.calendar call these. Everything is read through the permission helpers of the caller:
the space is resolved there, and a record the user cannot see in the space is not read here.
"""
from datetime import date, timedelta

import frappe
from frappe.utils import add_days, getdate, today

from lifeos import areas, permissions
from lifeos import calendar_data as data
from lifeos import journal as rules
from lifeos.api.utils import descendants

FINISHED = ("Achieved", "Partly Achieved")
GREY = ("Achieved", "Partly Achieved", "Not Achieved", "Carried", "Dropped")
OUTCOME_WORD = {"Achieved": "done", "Partly Achieved": "partly done", "Not Achieved": "not achieved", "Carried": "carried", "Dropped": "dropped"}
INSIGHT_KINDS = ("Theme", "Keeps coming up", "12 Week Year")
PLANNING_OPENS_WEEK = 11  # the banner "Plan your next 12 weeks" starts in week 11 of a cycle (lifeos/rhythms.py)


def monday_of(day):
	day = getdate(day)
	return day - timedelta(days=day.weekday())


def cycle_rows(space, start, end):
	"""The cycles that touch the year, each with its score: the final score of a closed one, the running average of the active one."""
	out = []
	for c in frappe.get_all("Life Cycle", filters={"space": space, "start_date": ("<=", end), "end_date": (">=", start)},
			fields=["name", "title", "start_date", "end_date", "status", "final_score"], order_by="start_date asc", limit=20):
		score, week = None, None
		if c.status == "Closed":
			score = c.final_score
		elif c.status == "Active":
			grid = rules.grid(c.name)
			score, week = grid["average"], grid["current_week"]
		out.append({"name": c.name, "title": c.title, "start": str(c.start_date), "end": str(c.end_date), "status": c.status,
			"score": None if score is None else round(float(score)), "week": week})
	return out


def goal_span(goal, cycle, start, end):
	"""The dates a goal's bar covers. A goal of a 12 Week Year covers its cycle; any other starts when it was made and runs to its
	target date (the end of the year when it has none), or to the day it was closed."""
	if goal.horizon == "12 weeks" and cycle:
		first, last = getdate(cycle.start_date), getdate(cycle.end_date)
	else:
		first = getdate(goal.creation)
		last = getdate(goal.target_date) if goal.target_date else end
	closed = goal.closed_on or goal.completed_on
	if closed and goal.outcome in GREY and goal.horizon != "12 weeks":
		last = min(last, getdate(closed)) if getdate(closed) >= first else last
	return max(first, start), min(max(last, first), end)


def lanes(space, start, end, area=None):
	"""One lane for each area that is on, its parts as rows under it, with the goals that fall in the year. Areas that are off
	have no lane, and neither do their goals."""
	ordered = areas.ordered(space)
	keep = set(descendants(space, area)) if area else None
	cycles = {c.name: c for c in frappe.get_all("Life Cycle", filters={"space": space}, fields=["name", "start_date", "end_date"], limit=200)}
	goals = frappe.get_all("Life Goal", filters={"space": space, "is_archived": 0, "is_someday": 0},
		fields=["name", "title", "area", "horizon", "cycle", "target_date", "closed_on", "completed_on", "outcome", "creation"],
		order_by="creation asc", limit=2000)
	by_area = {}
	for g in goals:
		first, last = goal_span(g, cycles.get(g.cycle), start, end)
		cycle = cycles.get(g.cycle)
		if g.horizon == "12 weeks" and cycle and (getdate(cycle.end_date) < start or getdate(cycle.start_date) > end):
			continue
		if g.horizon != "12 weeks" and (getdate(g.creation) > end or (g.target_date and getdate(g.target_date) < start)):
			continue
		word = OUTCOME_WORD.get(g.outcome)
		by_area.setdefault(g.area, []).append({"name": g.name, "title": g.title, "start": str(first), "end": str(last), "outcome": g.outcome,
			"grey": g.outcome in GREY, "label": f"{g.title} · {word}" if word else g.title})
	out = []
	parents = {a.name: a for a in ordered if not a.parent_area}
	for a in ordered:
		if keep is not None and a.name not in keep:
			continue
		rows = by_area.get(a.name, [])
		# a part with no goal this year has no row; a life area keeps its lane while it is on
		if a.parent_area and not rows:
			continue
		parent = parents.get(a.parent_area)
		out.append({"area": a.name, "name": a.area_name, "colour": a.colour or (parent.colour if parent else None), "part_of": parent.area_name if parent else None, "goals": rows})
	return out


def key_dates(space, start, end):
	"""Pins: important dates, trips and other all-day events, and documents that expire."""
	out = []
	for d in data.important_dates_between(space, start, end):
		out.append({"date": d["date"], "title": d["label"] or d["title"], "kind": "important", "name": d["name"]})
	for e in data.events_between(space, start, end):
		if e["all_day"]:
			out.append({"date": e["date"], "title": e["title"], "kind": "trip" if e["multi_day"] else "event", "name": e["name"]})
	for v in data.vault_expiries_between(space, start, end):
		out.append({"date": v["date"], "title": v["title"], "kind": "vault", "name": v["name"]})
	return sorted(out, key=lambda k: (k["date"], k["title"]))


def review_ticks(space, start, end):
	"""One tick for each week of the year: done when a weekly review was locked in it. A week still running is not counted
	as missed, and neither is one to come."""
	now = getdate(today())
	done = {monday_of(r.period_start) for r in frappe.get_all("Life Review", filters={"space": space, "user": frappe.session.user, "kind": "Weekly",
		"status": "Locked", "period_start": ("between", [add_days(start, -6), end])}, fields=["period_start"], limit=200)}
	weeks, day = [], monday_of(start)
	if day < start:
		day = add_days(day, 7)
	while day <= end:
		over = add_days(day, 6) < now
		weeks.append({"start": str(day), "done": day in done, "future": not over and day not in done})
		day = add_days(day, 7)
	return {"weeks": weeks, "done": sum(1 for w in weeks if w["done"]), "total": sum(1 for w in weeks if not w["future"])}


def next_cycle(space, cycles):
	"""When the next 12 Week Year starts and when planning for it opens."""
	now = getdate(today())
	planned = [c for c in cycles if c["status"] == "Planned" and getdate(c["start"]) > now]
	if planned:
		start = getdate(planned[0]["start"])
		return {"start": str(start), "planned": True, "planning_opens": str(add_days(start, -14))}
	active = next((c for c in cycles if c["status"] == "Active"), None)
	if not active:
		return None
	start = rules.next_monday(active["end"])
	opens = add_days(getdate(active["start"]), 7 * (PLANNING_OPENS_WEEK - 1))
	return {"start": str(start), "planned": False, "planning_opens": str(opens)}


def summary(space, start, end, cycles, area=None):
	"""This year so far: goals finished, carried over and dropped, and the average 12 Week score."""
	cycle_names = [c["name"] for c in cycles]
	filters = {"space": space, "is_archived": 0, "is_someday": 0, "cycle": ("in", cycle_names or ["-"])}
	if area:
		filters["area"] = ("in", list(descendants(space, area)))
	counts = {"finished": 0, "carried": 0, "dropped": 0}
	for g in frappe.get_all("Life Goal", filters=filters, fields=["outcome"], limit=5000):
		if g.outcome in FINISHED:
			counts["finished"] += 1
		elif g.outcome in ("Carried", "Dropped"):
			counts[g.outcome.lower()] += 1
	scores = [c["score"] for c in cycles if c["score"] is not None and c["status"] != "Planned"]
	return {**counts, "average": round(sum(scores) / len(scores)) if scores else None}


def noticed(space):
	"""The Brain's most important observation about the year, or None. An agent never sees insights (api/insights)."""
	if permissions.is_agent():
		return None
	row = frappe.db.sql("""select name, title, body from `tabLife Insight` where space=%s and status='New' and kind in %s
		order by rank asc, creation desc limit 1""", (space, INSIGHT_KINDS), as_dict=True)
	return {"name": row[0].name, "title": row[0].title, "body": row[0].body} if row else None


def year_plan(space, year, area=None):
	year = int(year)
	start, end = date(year, 1, 1), date(year, 12, 31)
	cycles = cycle_rows(space, start, end)
	pins = key_dates(space, start, end)
	lane_rows = lanes(space, start, end, area)
	return {"space": space, "year": year, "today": today(), "cycles": cycles, "lanes": lane_rows, "key_dates": pins,
		"reviews": review_ticks(space, start, end), "summary": summary(space, start, end, cycles, area),
		"next_cycle": next_cycle(space, cycles) if year >= getdate(today()).year else None,
		"insight": noticed(space) if year == getdate(today()).year else None,
		"goal_count": sum(len(lane["goals"]) for lane in lane_rows)}


def week_plan(space, week_start, area=None):
	"""Today > Week: the week's place in the 12 Week Year and its score, the top three, and the goal work planned in it
	(tasks planned at a time that serve a goal), by goal."""
	first = getdate(week_start)
	last = add_days(first, 6)
	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "start_date", "end_date"], as_dict=True)
	score = None
	if cycle and cycle.start_date <= last and cycle.end_date >= first:
		week = rules.week_of(cycle, first)
		if 1 <= week <= rules.WEEKS:
			score = {**rules.week_score(cycle.name, week), "week": week, "weeks": rules.WEEKS}
	filters = {"space": space, "is_archived": 0, "status": ("in", ["Open", "Doing", "Waiting"])}
	if area:
		filters["area"] = ("in", list(descendants(space, area)))
	top = frappe.get_all("Life Task", filters={**filters, "is_top_three": 1}, fields=["name", "title", "due_date", "goal"], order_by="creation asc", limit=3)
	blocks = frappe.get_all("Life Task", filters={**filters, "goal": ("is", "set"), "scheduled_at": ("between", [first, add_days(last, 1)])},
		fields=["name", "title", "goal", "duration_min"], limit=500)
	titles = dict(frappe.get_all("Life Goal", filters={"name": ("in", [b.goal for b in blocks] or ["-"])}, fields=["name", "title"], as_list=True))
	goals = {}
	for b in blocks:
		g = goals.setdefault(b.goal, {"goal": b.goal, "title": titles.get(b.goal, b.goal), "minutes": 0, "tasks": 0})
		g["minutes"] += b.duration_min or 60
		g["tasks"] += 1
	rows = sorted(goals.values(), key=lambda g: -g["minutes"])
	return {"week_start": str(first), "week_end": str(last), "score": score, "target": frappe.db.get_single_value("Life Settings", "score_target") or 85,
		"top": [{"name": t.name, "title": t.title, "due_date": str(t.due_date) if t.due_date else None} for t in top],
		"goal_minutes": sum(g["minutes"] for g in rows), "goals": rows}
