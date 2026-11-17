"""Journal: 12 Week Year, goals across cycles, month plans, habits, check-ins, pages, weekly review."""
import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos import journal as rules
from lifeos import permissions
from lifeos.api.utils import flag, names_map, page, parse


def _cycle(cycle=None, space=None):
	"""A cycle by name, or the active (else latest) cycle of a space."""
	if cycle:
		return permissions.get_doc_checked("Life Cycle", cycle)
	space = permissions.resolve_space(space)
	name = (frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"})
		or frappe.db.get_value("Life Cycle", {"space": space}, "name", order_by="start_date desc"))
	return frappe.get_doc("Life Cycle", name) if name else None


# ---------- 12 Week Year ----------

@frappe.whitelist(methods=["GET"])
def grid(cycle: str | None = None, space: str | None = None):
	"""The 12 Week Year grid of a cycle: goals, actions, ticks per week, week scores and the average."""
	doc = _cycle(cycle, space)
	if not doc:
		return None
	out = rules.grid(doc.name)
	out["cycles"] = frappe.get_all("Life Cycle", filters={"space": doc.space}, fields=["name", "title", "status", "start_date"], order_by="start_date desc", limit=40)
	for c in out["cycles"]:
		c["start_date"] = str(c.start_date)
	return out


@frappe.whitelist(methods=["POST"])
def tick(action: str, week: int, count: int):
	"""Set the ticks of a goal action in a week. Returns that week's score."""
	permissions.require_login()
	return rules.set_tick(action, week, count)


@frappe.whitelist(methods=["GET"])
def week_score(cycle: str | None = None, week: int | None = None, space: str | None = None):
	"""Done over planned for a week of a cycle. Defaults: the active cycle and its current week."""
	doc = _cycle(cycle, space)
	if not doc:
		frappe.throw(_("No cycle found."))
	return rules.week_score(doc.name, week or rules.current_week(doc))


@frappe.whitelist(methods=["POST"])
def set_action_status(action: str, status: str):
	"""Mark an action Done once and for all, Dropped, or Open again."""
	permissions.require_login()
	return rules.set_action_status(action, status)


@frappe.whitelist(methods=["POST"])
def save_goal(goal: str | None = None, cycle: str | None = None, title: str | None = None, area: str | None = None, project: str | None = None, actions: str | list | None = None):
	"""Create or change a goal and its actions. `actions` is a list of {name?, title, per_week}."""
	permissions.require_login()
	actions = parse(actions)
	if goal:
		doc = permissions.get_doc_checked("Life Goal", goal, "write")
	else:
		c = permissions.get_doc_checked("Life Cycle", cycle, "write")
		last = frappe.db.sql("select ifnull(max(sort_order), 0) from `tabLife Goal` where cycle=%s", c.name)[0][0]
		doc = frappe.get_doc({"doctype": "Life Goal", "space": c.space, "cycle": c.name, "sort_order": last + 1})
	if title is not None:
		doc.title = title
	if area is not None:
		doc.area = area or None
	if project is not None:
		doc.project = project or None
	if actions is not None:
		existing = {a.name: a for a in doc.actions}
		rows = []
		for a in actions:
			if not (a.get("title") or "").strip():
				continue
			row = existing.get(a.get("name"))
			if row:
				row.title, row.per_week = a["title"].strip(), a.get("per_week") or 1
				rows.append(row)
			else:
				rows.append({"title": a["title"].strip(), "per_week": a.get("per_week") or 1, "status": "Open"})
		removed = [n for n in existing if n not in [getattr(r, "name", None) for r in rows]]
		doc.set("actions", rows)
		for n in removed:
			frappe.db.delete("Life Action Log", {"action_id": n})
	doc.save() if goal else doc.insert()
	return {"goal": doc.name}


@frappe.whitelist(methods=["POST"])
def delete_goal(goal: str):
	"""Delete a goal. Refused for agents, who cannot delete."""
	doc = permissions.get_doc_checked("Life Goal", goal, "delete")
	doc.delete()
	return {"deleted": goal}


def _goal_links(goals):
	"""Titles a goal row shows, for many goals in four queries: its project, and the cycles it was carried from and into."""
	names = [g["name"] for g in goals]
	carried_from = [g["carried_from"] for g in goals if g["carried_from"]]
	into = {}
	for r in frappe.get_all("Life Goal", filters={"carried_from": ("in", names or ["-"])}, fields=["carried_from", "cycle"], order_by="creation asc"):
		into.setdefault(r.carried_from, r.cycle)
	from_cycle = dict(frappe.get_all("Life Goal", filters={"name": ("in", carried_from or ["-"])}, fields=["name", "cycle"], as_list=True))
	cycles = names_map("Life Cycle", [*into.values(), *from_cycle.values()], "title")
	projects = names_map("Life Project", [g["project"] for g in goals], "title")
	return {"into_cycle": into, "from_cycle": from_cycle, "cycles": cycles, "projects": projects}


@frappe.whitelist(methods=["GET"])
def goals(space: str | None = None, area: str | None = None):
	"""Every goal across every cycle, grouped by cycle: planned, active, then closed, newest first."""
	space = permissions.resolve_space(space)
	cycles = frappe.get_all("Life Cycle", filters={"space": space}, fields=["name", "title", "status", "start_date", "end_date", "final_score"],
		order_by="start_date desc", limit=60)
	order = {"Planned": 0, "Active": 1, "Closed": 2}
	cycles.sort(key=lambda c: order.get(c.status, 3))
	target = frappe.db.get_single_value("Life Settings", "score_target") or 85
	out = []
	grids = {c.name: rules.grid(c.name) for c in cycles}
	links = _goal_links([goal for g in grids.values() for goal in g["goals"]])
	for c in cycles:
		g = grids[c.name]
		rows = []
		for goal in g["goals"]:
			if area and goal["area"] != area:
				continue
			rows.append({
				"name": goal["name"], "title": goal["title"], "area": goal["area"], "area_name": goal["area_name"], "project": goal["project"],
				"project_title": links["projects"].get(goal["project"]) if goal["project"] else None,
				"actions": len([a for a in goal["actions"] if a["status"] != "Dropped"]),
				"actions_done": len([a for a in goal["actions"] if a["status"] == "Done"]),
				"percent": goal["final_score"] if c.status == "Closed" else goal["percent"],
				"outcome": goal["outcome"], "result_note": goal["result_note"], "carried_from": goal["carried_from"],
				"carried_from_cycle": links["cycles"].get(links["from_cycle"].get(goal["carried_from"])) if goal["carried_from"] else None,
				"carried_into_cycle": links["cycles"].get(links["into_cycle"].get(goal["name"])),
			})
		out.append({"name": c.name, "title": c.title, "status": c.status, "start_date": str(c.start_date), "end_date": str(c.end_date),
			"current_week": g["current_week"], "average": g["average"], "past_end": g["past_end"], "goals": rows})
	areas = frappe.get_all("Life Area", filters={"space": space, "parent_area": ("is", "not set"), "is_archived": 0}, fields=["name", "area_name"], order_by="sort_order")
	used = {r[0] for r in frappe.db.sql("select distinct area from `tabLife Goal` where space=%s", space)}
	from lifeos.api.goals import with_tasks

	with_tasks([r for c in out for r in c["goals"]])
	return {"cycles": out, "target": target, "areas": [a for a in areas if a.name in used]}


@frappe.whitelist(methods=["GET"])
def goal(goal: str):
	"""A goal page: the goal, its actions, and its history across cycles through the carried_from chain."""
	from lifeos.api.goals import task_counts

	doc = permissions.get_doc_checked("Life Goal", goal)
	done, counted = task_counts([doc.name]).get(doc.name, (0, 0))
	order = ["Doing", "Open", "Waiting", "Done", "Dropped", "Carried"]
	tf = {"goal": doc.name}
	if frappe.session.user != "Administrator":  # a member sees only the tasks of their own spaces
		tf["space"] = ("in", [*permissions.user_spaces()] or [""])
	tasks = sorted(frappe.get_all("Life Task", filters=tf,
		fields=["name", "title", "status", "due_date", "is_archived"], limit=200),
		key=lambda t: (order.index(t.status) if t.status in order else 9, t.due_date is None, str(t.due_date or "")))
	common = {"space": doc.space, "goal_type": doc.goal_type or "12 Week Year", "target_date": str(doc.target_date) if doc.target_date else None,
		"closed_on": str(doc.closed_on) if doc.closed_on else None, "tasks": tasks, "tasks_done": done, "tasks_counted": counted,
		"is_someday": doc.is_someday, "someday_review_on": str(doc.someday_review_on) if doc.someday_review_on else None}
	if not doc.cycle:
		g = {"name": doc.name, "title": doc.title, "area": doc.area, "area_name": frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None,
			"project": doc.project, "actions": [], "percent": None, "outcome": doc.outcome, "result_note": doc.result_note, "carried_from": None}
		cycles = frappe.get_all("Life Cycle", filters={"space": doc.space, "status": ("in", ["Active", "Planned"])}, fields=["name", "title", "status"], order_by="start_date")
		return {"goal": g, "cycle": None, "cycles": cycles, "history": [], **common}
	g = next((x for x in rules.grid(doc.cycle)["goals"] if x["name"] == doc.name), None)
	cycle = frappe.db.get_value("Life Cycle", doc.cycle, ["title", "status", "start_date", "end_date"], as_dict=True)
	return {"goal": g, "cycle": {"name": doc.cycle, "title": cycle.title, "status": cycle.status},
		"history": rules.goal_history(doc.name), **common}


@frappe.whitelist(methods=["POST"])
def close_cycle(cycle: str, outcomes: str | list | None = None):
	"""Close an active cycle after its end date. `outcomes` is a list of {goal, outcome, result_note}."""
	permissions.require_login()
	return rules.close_cycle(cycle, parse(outcomes, []))


@frappe.whitelist(methods=["POST"])
def plan_next_cycle(cycle: str, goals: str | list | None = None, title: str | None = None):
	"""Create the next cycle, starting the Monday after this one ends, and carry the chosen goals with their open actions."""
	permissions.require_login()
	return rules.plan_next_cycle(cycle, parse(goals, []), title)


@frappe.whitelist(methods=["POST"])
def start_cycle(cycle: str):
	"""Make a planned cycle the active one."""
	doc = permissions.get_doc_checked("Life Cycle", cycle, "write")
	if doc.status != "Planned":
		frappe.throw(_("Only a planned cycle can be started."))
	doc.status = "Active"
	doc.save()
	return {"cycle": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def create_cycle(space: str | None = None, start_date: str | None = None, title: str | None = None):
	"""Create the first cycle of a space. It starts on the given date, or next Monday."""
	space = permissions.resolve_space(space, write=True)
	start = getdate(start_date) if start_date else rules.next_monday(add_days(today(), -1))
	status = "Planned" if frappe.db.exists("Life Cycle", {"space": space, "status": "Active"}) else "Active"
	doc = frappe.get_doc({"doctype": "Life Cycle", "space": space, "title": title or rules.cycle_title(start), "start_date": start, "status": status}).insert()
	return {"cycle": doc.name}


# ---------- month plan ----------

def _plan_dict(plan):
	areas = names_map("Life Area", [g.area for g in plan.goals], "area_name")
	return {
		"name": plan.name, "year": plan.year, "month": plan.month, "space": plan.space,
		"mindsweep_md": plan.mindsweep_md or "", "projects_md": plan.projects_md or "",
		"goals": [{"row": g.name, "title": g.title, "priority": g.priority, "status": g.status, "area": g.area, "area_name": areas.get(g.area),
			"task": g.task, "carried_from": g.carried_from} for g in plan.goals],
	}


@frappe.whitelist(methods=["POST"])
def month(space: str | None = None, year: int | None = None, month: int | None = None, create: bool | int = 0):
	"""The plan of one month: goals, mindsweep, habits with their month so far, and the latest check-in."""
	space = permissions.resolve_space(space)
	now = getdate(today())
	year, month = int(year or now.year), int(month or now.month)
	if flag(create):
		permissions.require_space(space, write=True)
	plan = rules.get_month_plan(space, year, month, create=flag(create))
	latest = frappe.get_all("Life Check-in", filters={"space": space}, fields=["name", "date"], order_by="date desc", limit=1)
	checkin = None
	if latest:
		checkin = _checkin_dict(frappe.get_doc("Life Check-in", latest[0].name))
	return {"year": year, "month": month, "plan": _plan_dict(plan) if plan else None, "habits": rules.habits_month(space, year, month),
		"latest_checkin": checkin, "today": str(now)}


@frappe.whitelist(methods=["POST"])
def save_month_goal(plan: str, row: str | None = None, title: str | None = None, priority: str | None = None, status: str | None = None, area: str | None = None, delete: bool | int = 0):
	"""Add, change or remove one goal of a month plan."""
	doc = permissions.get_doc_checked("Life Month Plan", plan, "write")
	if row:
		r = next((g for g in doc.goals if g.name == row), None)
		if not r:
			frappe.throw(_("Goal not found."), frappe.DoesNotExistError)
		if flag(delete):
			doc.remove(r)
		else:
			for k, v in (("title", title), ("priority", priority), ("status", status), ("area", area)):
				if v is not None:
					r.set(k, v or None)
			if status and r.task and frappe.db.exists("Life Task", r.task):
				task_status = {"Done": "Done", "Dropped": "Dropped", "Open": "Open"}.get(status)
				if task_status and frappe.db.get_value("Life Task", r.task, "status") != task_status:
					t = frappe.get_doc("Life Task", r.task)
					t.status = task_status
					t.save()
	else:
		if not (title or "").strip():
			frappe.throw(_("Type a title for the goal."))
		doc.append("goals", {"title": title.strip(), "priority": priority, "status": status or "Open", "area": area})
	doc.save()
	return _plan_dict(doc)


@frappe.whitelist(methods=["POST"])
def save_month_text(plan: str, mindsweep_md: str | None = None, projects_md: str | None = None):
	"""Save the mindsweep or the projects text of a month plan (autosave)."""
	doc = permissions.get_doc_checked("Life Month Plan", plan, "write")
	if mindsweep_md is not None:
		doc.mindsweep_md = mindsweep_md
	if projects_md is not None:
		doc.projects_md = projects_md
	doc.save()
	return {"plan": doc.name}


@frappe.whitelist(methods=["POST"])
def carry_month_goal(plan: str, row: str):
	"""Carry an open month goal into next month's plan. The old one is marked Carried."""
	permissions.require_login()
	return rules.carry_month_goal(plan, row)


@frappe.whitelist(methods=["POST"])
def make_task_from_goal(plan: str, row: str):
	"""Create a Life Task linked to a month goal."""
	doc = permissions.get_doc_checked("Life Month Plan", plan, "write")
	r = next((g for g in doc.goals if g.name == row), None)
	if not r:
		frappe.throw(_("Goal not found."), frappe.DoesNotExistError)
	if r.task and frappe.db.exists("Life Task", r.task):
		return {"task": r.task, "existing": True}
	task = frappe.get_doc({"doctype": "Life Task", "space": doc.space, "title": r.title, "priority": r.priority, "area": r.area,
		"month_plan": doc.name, "status": "Open"}).insert()
	r.task = task.name
	doc.save()
	return {"task": task.name, "existing": False}


# ---------- habits ----------

@frappe.whitelist(methods=["GET"])
def habits(space: str | None = None, year: int | None = None, month: int | None = None):
	"""The habit grid of one month: each tracked habit with its done days, count, target and percentage."""
	space = permissions.resolve_space(space)
	now = getdate(today())
	return rules.habits_month(space, int(year or now.year), int(month or now.month))


@frappe.whitelist(methods=["POST"])
def toggle_habit(habit: str, date: str | None = None, done: bool | int | None = None):
	"""Tick or untick a habit on a day."""
	permissions.require_login()
	return rules.toggle_habit(habit, date, done)


@frappe.whitelist(methods=["GET"])
def habit_library(space: str | None = None):
	"""Every habit ever tracked in a space."""
	space = permissions.resolve_space(space)
	return frappe.get_all("Life Habit", filters={"space": space, "is_archived": 0}, fields=["name", "title", "area"], order_by="title", limit=200)


@frappe.whitelist(methods=["POST"])
def set_month_habits(space: str | None = None, year: int | None = None, month: int | None = None, habits: str | list | None = None):
	"""Set the habits tracked in one month. `habits` is an ordered list of {habit or title, days_per_week}. Other months are untouched."""
	space = permissions.resolve_space(space, write=True)
	rows = []
	for h in parse(habits, []):
		name = h.get("habit")
		if not name:
			title = (h.get("title") or "").strip()
			if not title:
				continue
			name = frappe.db.get_value("Life Habit", {"space": space, "title": title}) or frappe.get_doc(
				{"doctype": "Life Habit", "space": space, "title": title}).insert().name
		elif frappe.db.get_value("Life Habit", name, "space") != space:
			frappe.throw(_("That habit belongs to another space."), frappe.PermissionError)
		rows.append({"habit": name, "days_per_week": h.get("days_per_week") or 7})
	return rules.set_month_habits(space, year, month, rows)


@frappe.whitelist(methods=["GET"])
def habits_year(space: str | None = None, year: int | None = None):
	"""Each habit's monthly percentage for the months of a year in which it was tracked."""
	space = permissions.resolve_space(space)
	return rules.habits_year(space, year or getdate(today()).year)


# ---------- check-ins ----------

def _checkin_dict(doc):
	dims = names_map("Life Dimension", [s.dimension for s in doc.scores], "dimension_name")
	return {"name": doc.name, "date": str(doc.date), "reflection_md": doc.reflection_md or "",
		"scores": [{"dimension": s.dimension, "dimension_name": dims.get(s.dimension), "habits_low": s.habits_low, "habits_high": s.habits_high,
			"situation_low": s.situation_low, "situation_high": s.situation_high, "note": s.note or ""} for s in doc.scores]}


@frappe.whitelist(methods=["GET"])
def checkins(space: str | None = None, start: int = 0, page_length: int = 30):
	"""Check-ins of a space, newest first, with the dimensions and a series per dimension for the charts (midpoint of each range)."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	names = frappe.get_all("Life Check-in", filters={"space": space}, pluck="name", order_by="date desc", limit_start=start, limit=page_length)
	rows = [_checkin_dict(frappe.get_doc("Life Check-in", n)) for n in names]
	dims = frappe.get_all("Life Dimension", filters={"space": space}, fields=["name", "dimension_name", "is_archived"], order_by="sort_order", limit=50)
	series = []
	for d in dims:
		points = []
		for c in reversed(rows):
			s = next((x for x in c["scores"] if x["dimension"] == d.name), None)
			if s:
				mid = lambda lo, hi: None if lo is None else round((lo + (hi if hi is not None else lo)) / 2.0, 2)  # noqa: E731
				points.append({"date": c["date"], "habits": mid(s["habits_low"], s["habits_high"]), "situation": mid(s["situation_low"], s["situation_high"])})
		series.append({"dimension": d.name, "dimension_name": d.dimension_name, "points": points})
	return {"checkins": rows, "dimensions": dims, "series": series}


@frappe.whitelist(methods=["POST"])
def save_checkin(space: str | None = None, date: str | None = None, scores: str | list | None = None, reflection_md: str | None = None, name: str | None = None):
	"""Create or change a check-in. Each score is {dimension, habits, situation, note}; a score is a number or a range such as 2-3."""
	from lifeos.life.doctype.life_check_in.life_check_in import parse_range

	if name:
		doc = permissions.get_doc_checked("Life Check-in", name, "write")
	else:
		space = permissions.resolve_space(space, write=True)
		doc = frappe.get_doc({"doctype": "Life Check-in", "space": space})
	doc.date = date or doc.date or today()
	if reflection_md is not None:
		doc.reflection_md = reflection_md
	rows = []
	for s in parse(scores, []):
		hl, hh = parse_range(s.get("habits"))
		sl, sh = parse_range(s.get("situation"))
		if hl is None and sl is None and not s.get("note"):
			continue
		rows.append({"dimension": s["dimension"], "habits_low": hl, "habits_high": hh, "situation_low": sl, "situation_high": sh, "note": s.get("note")})
	doc.set("scores", rows)
	doc.save() if name else doc.insert()
	return _checkin_dict(doc)


# ---------- pages ----------

@frappe.whitelist(methods=["GET"])
def pages(space: str | None = None, start: int = 0, page_length: int = 24):
	"""Photographed journal pages by date, newest first."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	rows = frappe.get_all("Life Journal Page", filters={"space": space, "is_archived": 0},
		fields=["name", "page_date", "page_number", "image", "inbox_item"], order_by="page_date desc, creation desc", limit_start=start, limit=page_length)
	for r in rows:
		r["page_date"] = str(r.page_date)
	return {"pages": rows, "has_more": len(rows) == page_length}


@frappe.whitelist(methods=["GET"])
def page_detail(page: str):
	"""One journal page: image, transcript, and the records created from the same inbox item."""
	from lifeos import links

	doc = permissions.get_doc_checked("Life Journal Page", page)
	created = []
	if doc.inbox_item:
		for p in frappe.get_all("Life Proposal", filters={"inbox_item": doc.inbox_item, "status": "Accepted"},
				fields=["kind", "preview", "created_doctype", "created_name"], order_by="sort_order", limit=100):
			if p.created_doctype == "Life Journal Page" and p.created_name == doc.name:
				continue
			if p.created_name and frappe.db.exists(p.created_doctype, p.created_name):
				created.append({"kind": p.kind, "title": p.preview, "route": links.route_of(p.created_doctype, p.created_name)})
	return {"name": doc.name, "space": doc.space, "page_date": str(doc.page_date), "page_number": doc.page_number, "image": doc.image,
		"transcript_md": doc.transcript_md or "", "inbox_item": doc.inbox_item, "area": doc.area, "created": created}


@frappe.whitelist(methods=["POST"])
def save_page_transcript(page: str, transcript_md: str):
	"""Correct the transcript of a journal page."""
	doc = permissions.get_doc_checked("Life Journal Page", page, "write")
	doc.transcript_md = transcript_md
	doc.save()
	return {"page": doc.name}


# ---------- weekly review ----------

@frappe.whitelist(methods=["GET"])
def weekly_review(space: str | None = None, week_start: str | None = None):
	"""Everything the weekly review gathers for one week (Monday to Sunday)."""
	from lifeos import archive
	from lifeos.api import tasks as task_api

	space = permissions.resolve_space(space)
	now = getdate(today())
	start = getdate(week_start) if week_start else add_days(now, -now.weekday())
	start = add_days(start, -start.weekday())
	end = add_days(start, 6)

	cycle_out = None
	cycle = frappe.db.sql(
		"select name, title, status from `tabLife Cycle` where space=%s and start_date <= %s and end_date >= %s order by start_date desc limit 1",
		(space, end, start), as_dict=True)
	if cycle:
		c = frappe.get_doc("Life Cycle", cycle[0].name)
		week = min(max(rules.week_of(c, min(end, getdate(c.end_date))), 1), rules.WEEKS)
		cycle_out = {"name": c.name, "title": c.title, "week": week, **rules.week_score(c.name, week)}

	habits = []
	months = {(start.year, start.month), (end.year, end.month)}
	seen = set()
	for y, m in sorted(months):
		for h in rules.habits_month(space, y, m)["habits"]:
			if h["habit"] in seen:
				continue
			seen.add(h["habit"])
			done = frappe.db.count("Life Habit Log", {"habit": h["habit"], "date": ("between", [start, end]), "done": 1})
			habits.append({"habit": h["habit"], "title": h["title"], "done": done, "target": h["days_per_week"]})

	done_tasks = task_api.query(space, "and t.status = 'Done' and t.completed_on between %(a)s and %(b)s", {"a": start, "b": end}, "t.completed_on desc", 0, 100)
	carried = task_api.query(space, "and t.status = 'Carried' and t.completed_on between %(a)s and %(b)s", {"a": start, "b": end}, "t.completed_on desc", 0, 100)
	loops = task_api.open_loops(space=space, page_length=20)
	latest = frappe.get_all("Life Check-in", filters={"space": space, "date": ("<=", end)}, pluck="name", order_by="date desc", limit=1)
	title = f"Weekly review, {start.strftime('%-d %b %Y')}"
	note = frappe.db.get_value("Life Note", {"space": space, "title": title}, ["name", "content_md"], as_dict=True)
	return {
		"space": space, "week_start": str(start), "week_end": str(end), "cycle": cycle_out, "habits": habits,
		"done_total": _count_tasks(space, "Done", start, end), "carried_total": _count_tasks(space, "Carried", start, end),
		"done": done_tasks, "carried": carried, "open_loops": loops["tasks"], "open_loops_total": loops["total"],
		"decide": task_api.stale_tasks(space, 30),
		"archived": archive.archived_in_week(space, start, end),
		"latest_checkin": _checkin_dict(frappe.get_doc("Life Check-in", latest[0])) if latest else None,
		"note": {"title": title, "name": note.name if note else None, "content_md": note.content_md if note else ""},
		"stale_days": frappe.db.get_single_value("Life Settings", "stale_task_days") or 90,
	}


@frappe.whitelist(methods=["POST"])
def save_review_note(space: str | None = None, week_start: str | None = None, content_md: str = ""):
	"""Save the owner's notes for a week as a Life Note under the Reviews parent note."""
	space = permissions.resolve_space(space, write=True)
	start = getdate(week_start)
	title = f"Weekly review, {start.strftime('%-d %b %Y')}"
	parent = frappe.db.get_value("Life Note", {"space": space, "title": "Reviews", "parent_note": ("is", "not set")})
	if not parent:
		parent = frappe.get_doc({"doctype": "Life Note", "space": space, "title": "Reviews",
			"content_md": "Weekly review notes live under this note."}).insert().name
	existing = frappe.db.get_value("Life Note", {"space": space, "title": title, "parent_note": parent})
	if existing:
		doc = frappe.get_doc("Life Note", existing)
		doc.check_permission("write")
		doc.content_md = content_md
		doc.save()
	else:
		doc = frappe.get_doc({"doctype": "Life Note", "space": space, "title": title, "parent_note": parent, "content_md": content_md,
			"area": frappe.db.get_value("Life Note", parent, "area")}).insert()
	return {"note": doc.name, "title": title}


def _count_tasks(space, status, start, end):
	"""How many tasks closed with this status in the week, for the numbers that lead to the Tasks screen (the lists show 100)."""
	return frappe.db.sql("select count(*) from `tabLife Task` t where t.space=%s and t.status=%s and t.completed_on between %s and %s",
		(space, status, start, end))[0][0]
