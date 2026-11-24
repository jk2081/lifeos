"""Today > Year (issues 16 and 100): the cycles around today, and the week's goal work for Today > Week.

The year view is four columns: the last cycle, the current one, the next and the one after (or four calendar quarters when no 12 Week Year
is running). Rows: each cycle's score, one row for each area that is on with its goals as bars, key dates by week, and the weekly reviews
since the site was set up. The API methods in lifeos.api.calendar call these. Everything is read through the permission helpers of the
caller: the space is resolved there, and a record the user cannot see in the space is not read here.
"""
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos.goals import areas
from lifeos.calendar import calendar_data as data
from lifeos.goals import cycles as rules
from lifeos.api.utils import descendants

GREY = ("Achieved", "Partly Achieved", "Not Achieved", "Carried", "Dropped")
OUTCOME_WORD = {"Achieved": "done", "Partly Achieved": "partly done", "Not Achieved": "not achieved", "Carried": "carried", "Dropped": "dropped"}
COLUMNS = 4
CYCLE_DAYS = rules.WEEKS * 7


def monday_of(day):
	day = getdate(day)
	return day - timedelta(days=day.weekday())


# ---- the four columns ----
def _window(row):
	return {"start": getdate(row.start_date), "end": getdate(row.end_date), "cycle": row.name, "status": row.status, "title": row.title}


def _next_window(space, window):
	"""The cycle that starts after this one, as planned; else the 12 weeks that would follow it."""
	row = frappe.get_all("Life Cycle", filters={"space": space, "start_date": (">", window["end"])}, fields=["name", "title", "start_date", "end_date", "status"],
		order_by="start_date asc", limit=1)
	if row:
		return _window(row[0])
	start = rules.next_monday(window["end"])
	return {"start": start, "end": add_days(start, CYCLE_DAYS - 1), "cycle": None, "status": None, "title": None}


def _previous_window(space, window):
	row = frappe.get_all("Life Cycle", filters={"space": space, "end_date": ("<", window["start"])}, fields=["name", "title", "start_date", "end_date", "status"],
		order_by="end_date desc", limit=1)
	if row:
		return _window(row[0])
	end = add_days(window["start"], -1)
	return {"start": add_days(end, -(CYCLE_DAYS - 1)), "end": end, "cycle": None, "status": None, "title": None}


def _cycle_windows(space, shift, active):
	"""Windows for the columns shift-1 … shift+2, counted from the running cycle (index 0)."""
	first, last = min(shift - 1, 0), max(shift + COLUMNS - 2, 0)
	found = {0: _window(active)}
	for i in range(1, last + 1):
		found[i] = _next_window(space, found[i - 1])
	for i in range(-1, first - 1, -1):
		found[i] = _previous_window(space, found[i + 1])
	return [(i, found[i]) for i in range(shift - 1, shift + COLUMNS - 1)]


def _quarter_windows(shift, now):
	"""Calendar quarters, from the one that holds today, moved by `shift`."""
	base = now.year * 4 + (now.month - 1) // 3
	out = []
	for i in range(shift, shift + COLUMNS):
		year, quarter = divmod(base + i, 4)
		start = date(year, quarter * 3 + 1, 1)
		end = add_days(date(year + (quarter == 3), (quarter + 1) * 3 % 12 + 1, 1), -1)
		out.append((i, {"start": start, "end": end, "cycle": None, "status": None, "title": f"Q{quarter + 1} {year}"}))
	return out


def _name_of(index, kind, window):
	"""What a column is called, by its place around today."""
	if kind == "quarter":
		return {0: _("This quarter"), 1: _("Next quarter"), -1: _("Last quarter")}.get(index, window["title"])
	if index == 0:
		return _("This cycle")
	return {-1: _("Last cycle"), 1: _("Next cycle"), 2: _("The cycle after")}.get(index) or (
		_("{0} cycles back").format(-index) if index < 0 else _("In {0} cycles").format(index))


def columns(space, shift, now):
	"""The four columns of the year view and what kind they are ("cycle", or "quarter" when no 12 Week Year is running)."""
	active = frappe.get_all("Life Cycle", filters={"space": space, "status": "Active"}, fields=["name", "title", "start_date", "end_date", "status"],
		order_by="start_date desc", limit=1)
	kind = "cycle" if active else "quarter"
	windows = _cycle_windows(space, shift, active[0]) if active else _quarter_windows(shift, now)
	out = []
	for index, w in windows:
		current = w["start"] <= now <= w["end"]
		score, week = None, None
		if w["cycle"] and w["status"] == "Closed":
			score = frappe.db.get_value("Life Cycle", w["cycle"], "final_score")
		elif w["cycle"] and w["status"] == "Active":
			grid = rules.grid(w["cycle"])
			score, week = grid["average"], grid["current_week"]
		label = _name_of(index, kind, w)
		if current and kind == "cycle" and week:
			label = f"{label} · {_('week')} {week}"
		out.append({"index": index, "label": label, "start": str(w["start"]), "end": str(w["end"]), "cycle": w["cycle"], "status": w["status"],
			"when": "current" if current else "past" if w["end"] < now else "future", "week": week, "score": None if score is None else round(float(score))})
	return kind, out


# ---- goals by area ----
def goal_span(goal, cycle, start, end):
	"""The dates a goal's bar covers. A goal of a 12 Week Year covers its cycle; any other starts when it was made and runs to its
	target date (the end of the range when it has none), or to the day it was closed."""
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
	"""One lane for each area that is on, its parts as rows under it, with the goals that fall in the range. Areas that are off
	have no lane, and neither do their goals. A goal's deadline is its target date when that falls in the range."""
	ordered = areas.ordered(space)
	keep = set(descendants(space, area)) if area else None
	cycles = {c.name: c for c in frappe.get_all("Life Cycle", filters={"space": space}, fields=["name", "start_date", "end_date"], limit=200)}
	goals = frappe.get_all("Life Goal", filters={"space": space, "is_archived": 0, "is_someday": 0},
		fields=["name", "title", "area", "horizon", "cycle", "target_date", "closed_on", "completed_on", "outcome", "creation"],
		order_by="creation asc", limit=2000)
	by_area = {}
	for g in goals:
		cycle = cycles.get(g.cycle)
		if g.horizon == "12 weeks" and cycle and (getdate(cycle.end_date) < start or getdate(cycle.start_date) > end):
			continue
		if g.horizon != "12 weeks" and (getdate(g.creation) > end or (g.target_date and getdate(g.target_date) < start)):
			continue
		first, last = goal_span(g, cycle, start, end)
		word = OUTCOME_WORD.get(g.outcome)
		deadline = g.target_date and start <= getdate(g.target_date) <= end
		by_area.setdefault(g.area, []).append({"name": g.name, "title": g.title, "start": str(first), "end": str(last), "outcome": g.outcome,
			"grey": g.outcome in GREY, "label": f"{g.title} · {word}" if word else g.title, "deadline": str(g.target_date) if deadline else None})
	out = []
	parents = {a.name: a for a in ordered if not a.parent_area}
	for a in ordered:
		if keep is not None and a.name not in keep:
			continue
		rows = by_area.get(a.name, [])
		# a part with no goal in the range has no row; a life area keeps its row while it is on
		if a.parent_area and not rows:
			continue
		parent = parents.get(a.parent_area)
		out.append({"area": a.name, "name": a.area_name, "colour": a.colour or (parent.colour if parent else None), "part_of": parent.area_name if parent else None, "goals": rows})
	return out


# ---- key dates by week ----
def key_dates(space, start, end):
	"""The key dates in the range: important dates, events the key-date skill (or the owner) marked, and documents that expire. Each
	has `ref`, what the record pane opens."""
	out = []
	for d in data.important_dates_between(space, start, end):
		out.append({"date": d["date"], "title": d["label"] or d["title"], "kind": "important", "ref": f"date:{d['name']}"})
	for e in data.events_between(space, start, end):
		if e["key_date"]:
			out.append({"date": e["date"], "title": e["title"], "kind": "trip" if e["multi_day"] else "event",
				"ref": f"event:{e['name']}" + (f"@{e['date']}" if e["repeats"] else "")})
	for v in data.vault_expiries_between(space, start, end):
		out.append({"date": v["date"], "title": v["title"], "kind": "vault", "ref": f"vault:{v['name']}"})
	return sorted(out, key=lambda k: (k["date"], k["title"]))


def key_weeks(space, start, end):
	"""The key dates grouped by the week they fall in: [{start, count, items}], weeks with none left out."""
	weeks = {}
	for k in key_dates(space, start, end):
		weeks.setdefault(str(monday_of(k["date"])), []).append(k)
	return [{"start": w, "count": len(items), "items": items} for w, items in sorted(weeks.items())]


# ---- weekly reviews since setup ----
def setup_date(space):
	"""When Life OS was set up: the day the person finished the guide, or else when the first space they belong to was made."""
	from lifeos import permissions
	from lifeos.api.onboarding import KEY

	done = frappe.db.get_value("DefaultValue", {"parent": frappe.session.user, "parenttype": "__default", "defkey": KEY}, "modified")
	if done:
		return getdate(done)
	made = frappe.get_all("Life Space", filters={"name": ("in", list(permissions.user_spaces()) or [space])}, pluck="creation", order_by="creation asc", limit=1)
	return getdate(made[0]) if made else getdate(today())


def reviews_since_setup(space, start, end, now):
	"""A tick for each week of the range from the week Life OS was set up: done when a weekly review was locked in it; a week still
	running is not counted as missed. `done` and `total` count from setup to this week, not only the range."""
	first = monday_of(setup_date(space))
	locked = {monday_of(r.period_start) for r in frappe.get_all("Life Review", filters={"space": space, "user": frappe.session.user, "kind": "Weekly",
		"status": "Locked", "period_start": (">=", add_days(first, -6))}, fields=["period_start"], limit=1000)}
	this_week = monday_of(now)
	weeks, day = [], max(monday_of(start), first)
	while day <= end:
		weeks.append({"start": str(day), "done": day in locked, "future": day >= this_week and day not in locked})
		day = add_days(day, 7)
	total = max((this_week - first).days // 7 + 1, 0)
	return {"weeks": weeks, "done": sum(1 for w in locked if first <= w <= this_week), "total": total, "since": str(first)}


def year_plan(space, shift=0, area=None):
	now = getdate(today())
	shift = int(shift or 0)
	kind, cols = columns(space, shift, now)
	start, end = getdate(cols[0]["start"]), getdate(cols[-1]["end"])
	lane_rows = lanes(space, start, end, area)
	return {"space": space, "today": str(now), "kind": kind, "shift": shift, "columns": cols, "start": str(start), "end": str(end),
		"lanes": lane_rows, "goal_count": sum(len(lane["goals"]) for lane in lane_rows),
		"key_weeks": key_weeks(space, start, end), "reviews": reviews_since_setup(space, start, end, now)}


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
