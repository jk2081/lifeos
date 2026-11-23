"""Tasks: list, quick add, status, carry forward, open loops."""
import builtins
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos import cycles, datewords, gone_names, permissions
from lifeos.areas import off_clause
from lifeos.api.utils import area_filter, extra_columns, flag, names_map, page, std_clause, std_order, summarise, tab_counts
from lifeos.api.utils import order_by as sort_order

OPEN = ("Open", "Doing", "Waiting")
FIELDS = ["name", "title", "status", "priority", "due_date", "area", "area_guessed", "area_confidence", "goal", "inbox_item", "carried_from", "waiting_on",
	"waiting_on_person", "delegated_to", "creation", "completed_on", "source_url", "is_archived", "notes_md", "last_touched_on", "owner", "scheduled_at", "duration_min"]
PRIORITY_ORDER = "case t.priority when 'I' then 1 when 'II' then 2 when 'III' then 3 when 'IV' then 4 else 5 end"
OPEN_LOOP_DAYS = 14


def decorate(rows):
	"""Add the names a list row shows: area, goal, source."""
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	goals = names_map("Life Goal", [r.goal for r in rows], "title")
	sources = names_map("Life Inbox Item", [r.inbox_item for r in rows], "title")
	for r in rows:
		r["area_name"], r["goal_title"] = areas.get(r.area), goals.get(r.goal)
		r["source_title"] = sources.get(r.inbox_item)
		for k in ("due_date", "creation", "completed_on", "last_touched_on"):
			r[k] = str(r[k])[:19] if r.get(k) else None
	return rows


def query(space, where="", values=None, order=None, start=0, page_length=50, fields=None, hide_off=True):
	cols = ", ".join([f"t.`{f}`" for f in FIELDS] + extra_columns("Life Task", fields, "t", FIELDS))
	order = order or f"t.due_date is null, t.due_date asc, {PRIORITY_ORDER}, t.creation asc"
	values = dict(values or {})
	if hide_off:
		where = (where or "") + off_clause(space, "t.area", values, "query_off_areas")  # areas switched off (issue 11)
	# columns are FIELDS or pass column() (DocType meta); WHERE comes from where_clause and ORDER from SORTS or std_order
	# nosemgrep: frappe-sql-format-injection -- fixed SQL and meta-checked columns only; values are parameters
	rows = frappe.db.sql(
		f"select {cols} from `tabLife Task` t where t.space=%(space)s {where} order by {order} limit %(start)s, %(len)s",
		{**values, "space": space, "start": start, "len": page_length}, as_dict=True)
	return decorate(rows)


DUE = {
	"overdue": "t.due_date < %(today)s",
	"today": "t.due_date = %(today)s",
	"week": "t.due_date between %(week_start)s and %(week_end)s",
	"none": "t.due_date is null",
}
SORTS = {"due_date": "t.due_date is null, t.due_date", "priority": PRIORITY_ORDER, "title": "t.title", "status": "t.status",
	"creation": "t.creation", "completed_on": "t.completed_on"}


# The state tabs of the Tasks screen, as SQL on one task row. "Open" on the screen is Open and Doing; Waiting has its own tab.
TABS = {
	"open": "t.status in ('Open', 'Doing')",
	"loops": "t.status in ('Open', 'Doing', 'Waiting') and t.due_date is null and t.creation < %(cutoff)s",
	"Waiting": "t.status = 'Waiting'",
	"Done": "t.status = 'Done'",
	"Someday": "t.status = 'Someday'",
	# All leaves out tasks parked on the Someday list (UX fixes, set 5); the Someday tab lists them
	"all": "t.status != 'Someday'",
}


def where_clause(space, status="open_doing", area=None, priority=None, goal=None,
		include_archived=0, due=None, done=0, loops=0, completed_from=None, completed_to=None):
	"""The WHERE of a task list. Every count in the app that leads to a task list is made with this, so the two agree.
	The default status, open_doing, is what the Open tab of the Tasks screen shows; "open" also holds Waiting tasks."""
	where, values = [], {}
	if status == "open_doing":
		where.append("t.status in ('Open', 'Doing')")
	elif status == "open" and flag(done):
		where.append("t.status in ('Open', 'Doing', 'Waiting', 'Done', 'Dropped')")
	elif status == "open":
		where.append("t.status in ('Open', 'Doing', 'Waiting')")
	elif status == "done":
		where.append("t.status in ('Done', 'Dropped', 'Carried')")
	elif status == "all":
		where.append("t.status != 'Someday'")
	elif status and status != "any":
		where.append("t.status = %(status)s")
		values["status"] = status
	if not flag(include_archived):
		where.append("t.is_archived = 0")
	if area:
		where.append(area_filter(space, area, "t.area", values, also_in="Life Task"))
	off = off_clause(space, "t.area", values)  # tasks of an area that is off are hidden (issue 11)
	if off:
		where.append(off[len(" and "):])
	if priority:
		where.append("ifnull(t.priority, '') = %(priority)s")
		values["priority"] = "" if priority == "none" else priority
	if goal:
		where.append("ifnull(t.goal, '') = %(goal)s")
		values["goal"] = "" if goal == "none" else goal
	if due:
		parts = [DUE[d.strip()] for d in str(due).split(",") if d.strip() in DUE]
		if not parts:
			frappe.throw(_("due must be one or more of: {0}.").format(", ".join(DUE)))
		now = getdate(today())
		values.update({"today": now, "week_start": add_days(now, -now.weekday()), "week_end": add_days(now, 6 - now.weekday())})
		where.append("(" + " or ".join(parts) + ")")
	if flag(loops):
		where.append("t.due_date is null and t.creation < %(cutoff)s")
		values["cutoff"] = add_days(today(), -OPEN_LOOP_DAYS)
	if completed_from:
		where.append("t.completed_on >= %(completed_from)s")
		values["completed_from"] = getdate(completed_from)
	if completed_to:
		where.append("t.completed_on <= %(completed_to)s")
		values["completed_to"] = getdate(completed_to)
	return ((" and " + " and ".join(where)) if where else ""), values


def count(space, **filters):
	clause, values = where_clause(space, **filters)
	# nosemgrep: frappe-sql-format-injection -- the WHERE comes from where_clause (fixed fragments); values are parameters
	return frappe.db.sql(f"select count(*) from `tabLife Task` t where t.space=%(space)s {clause}", {"space": space, **values})[0][0]


def list_clause(space, status="open", area=None, priority=None, goal=None, include_archived=0,
		due=None, done=0, loops=0, completed_from=None, completed_to=None, filters=None):
	"""The WHERE of `list`, its values, and the part that came from `filters`."""
	clause, values = where_clause(space, status, area, priority, goal, include_archived, due, done, loops,
		completed_from, completed_to)
	extra, values = std_clause("Life Task", filters, "t", values)
	return clause + extra, values, extra


def total(space, status="open", due=None, filters=None, area=None):
	"""The `total` that `list` answers for these arguments, without its rows or tab counts: the counts on Today, Reset and
	the sidebar (lifeos/counts.py) use it, and the same WHERE keeps the number and the list in step."""
	space = permissions.resolve_space(space)
	clause, values, _extra = list_clause(space, status, area=area, due=due, filters=filters)
	# nosemgrep: frappe-sql-format-injection -- where_clause and std_clause give fixed fragments and meta-checked columns; values are parameters
	return frappe.db.sql(f"select count(*) from `tabLife Task` t where t.space=%(space)s {clause}", {"space": space, **values})[0][0]


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, status: str | None = "open", area: str | None = None,
		priority: str | None = None, goal: str | None = None,
		include_archived: bool | int = 0, start: int | str | None = 0, page_length: int | str | None = 50, due: str | None = None,
		done: bool | int = 0, loops: bool | int = 0, completed_from: str | date | None = None, completed_to: str | date | None = None,
		sort: str | None = None, dir: str | None = None, filters: str | builtins.list | dict | None = None, order_by: str | None = None,
		fields: str | builtins.list | None = None, summary: str | dict | None = None):
	"""Tasks of a space. status: open (Open, Doing and Waiting), open_doing, done, all, or one status; done=1 adds Done and Dropped to open.
	area takes an area (its sub-areas and also-in count) or "none". due: overdue, today, week, none, or several with commas.
	loops=1 keeps open tasks older than 14 days with no date. completed_from and completed_to bound completed_on.
	Sorted by due date, then priority I first, unless sort (due_date, priority, title, status, creation, completed_on) and dir say otherwise.
	filters is a standard Frappe filter list on Life Task fields, order_by a standard order string, fields extra columns to return;
	every field name is checked against the DocType.
	`tabs` in the answer counts the tasks on each state tab of the Tasks screen (open = Open and Doing, loops, Waiting, Done, all)
	under the same filters, whatever status was asked for."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	clause, values, extra = list_clause(space, status, area, priority, goal, include_archived, due, done,
		loops, completed_from, completed_to, filters)
	# the tab counts: the same filters without the status and the open-loops switch, which are what a tab stands for
	t_clause, t_values = where_clause(space, "any", area, priority, goal, include_archived, due, 0, 0,
		completed_from, completed_to)
	t_values = {**t_values, **values, "space": space, "cutoff": add_days(today(), -OPEN_LOOP_DAYS)}
	tabs = tab_counts(f"from `tabLife Task` t where t.space=%(space)s {t_clause}{extra}", t_values, TABS)
	if summary:
		return {"summary": summarise("Life Task", f"from `tabLife Task` t where t.space=%(space)s {clause}", {"space": space, **values},
			"t", summary, start, page_length), "today": today(), "tabs": tabs}
	default = "t.completed_on desc, t.modified desc" if status in ("done", "Done", "Carried", "Dropped") else None
	order = std_order("Life Task", order_by, "t", SORTS) or sort_order(sort, dir, SORTS, default)
	if order and order != default:
		order += ", t.creation asc"
	rows = query(space, clause, values, order, start, page_length, fields)
	# nosemgrep: frappe-sql-format-injection -- where_clause and std_clause give fixed fragments and meta-checked columns; values are parameters
	total = frappe.db.sql(f"select count(*) from `tabLife Task` t where t.space=%(space)s {clause}", {"space": space, **values})[0][0]
	return {"tasks": rows, "total": total, "start": start, "page_length": page_length, "today": today(), "tabs": tabs}


ALL_SHOWS = {
	"open": "t.status in ('Open', 'Doing', 'Waiting')",
	"due": "t.status in ('Open', 'Doing', 'Waiting') and t.due_date is not null and t.due_date <= %(week_end)s",
	"waiting": "t.status = 'Waiting'",
	"stuck": "t.status in ('Open', 'Doing', 'Waiting') and t.last_touched_on <= %(stuck_cut)s",
	"someday": "t.status = 'Someday'",
	"done": "t.status = 'Done'",
}
ALL_CAP = 1000
DUE_GROUPS = (("overdue", "Overdue"), ("today", "Today"), ("week", "This week"), ("later", "Later"), ("none", "No date"))


def _due_group(task, now, week_end):
	if not task.due_date:
		return "none"
	d = getdate(task.due_date)
	return "overdue" if d < now else "today" if d == now else "week" if d <= week_end else "later"


@frappe.whitelist(methods=["GET"])
def all_tasks(space: str | None = None, group: str = "area", show: str = "open", area: str | None = None, q: str | None = None):
	"""Goals → All tasks: the tasks of one filter in groups, each task once. `show`: open (Open, Doing and Waiting), due (open and
	due by the end of this week), stuck (open and untouched for the stuck-after days, 30 by default), waiting, someday or done. `group`: area (the areas that are on, each with its parts; tasks with
	no area last), goal (a group for each goal, then no goal) or due (overdue, today, this week, later, no date). `area` keeps one area
	of life with its parts; `q` searches titles. `counts` gives the tasks under each filter for the same area and search.
	At most 1,000 tasks come back (`truncated`); Done keeps the newest first."""
	space = permissions.resolve_space(space)
	if show not in ALL_SHOWS:
		frappe.throw(_("Unknown filter."))
	if group not in ("area", "goal", "due"):
		frappe.throw(_("Unknown grouping."))
	now = getdate(today())
	from lifeos import counts

	stuck_days = counts.rules()["stuck_after_days"]
	values = {"today": now, "week_end": add_days(now, 6 - now.weekday()), "stuck_cut": add_days(now, -stuck_days)}
	base = " and t.is_archived = 0"
	if area:
		base += " and " + area_filter(space, area, "t.area", values)
	if q and q.strip():
		base += " and t.title like %(q)s"
		values["q"] = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
	where = base + " and " + ALL_SHOWS[show]
	order = "t.completed_on desc, t.modified desc" if show == "done" else None
	rows = query(space, where, values, order, 0, ALL_CAP + 1, ["is_top_three"])
	truncated = len(rows) > ALL_CAP
	rows = rows[:ALL_CAP]
	# the same filters (and the areas that are off) without the tab's own condition, so each filter's count agrees with its list
	cond = ", ".join(f"ifnull(sum({c}), 0)" for c in ALL_SHOWS.values())
	off = off_clause(space, "t.area", values, "count_off_areas")
	# nosemgrep: frappe-sql-format-injection -- ALL_SHOWS is a constant map, base and off are fixed SQL; values are parameters
	tab_numbers = dict(zip(ALL_SHOWS, [int(n) for n in frappe.db.sql(
		f"select {cond} from `tabLife Task` t where t.space=%(space)s {base} {off}", {**values, "space": space})[0]]))
	groups = {"area": _by_area, "goal": _by_goal, "due": _by_due}[group](space, rows, show, now, values["week_end"])
	areas = frappe.get_list("Life Area", filters={"space": space, "is_archived": 0, "is_life_area": 1}, fields=["name", "area_name", "colour", "is_on"],
		order_by="sort_order asc, area_name asc", limit=50)
	return {"space": space, "group": group, "show": show, "total": len(rows), "truncated": truncated, "counts": tab_numbers, "stuck_days": stuck_days, "groups": groups,
		"areas": [a for a in areas if a.is_on], "today": str(now)}


def _by_area(space, rows, show, now, week_end):
	from lifeos.areas import off as areas_off

	tree = frappe.get_list("Life Area", filters={"space": space, "is_archived": 0}, fields=["name", "area_name", "parent_area", "colour", "is_focus"],
		order_by="sort_order asc, area_name asc", limit=5000)
	hidden = set(areas_off(space))
	focus_part = {x.name: x.parent_area for x in tree if x.is_focus}  # a task under a focus is listed under its part (issue 57)
	by = {}
	for r in rows:
		by.setdefault(focus_part.get(r.area) or r.area or "", []).append(r)
	out = []
	for a in [x for x in tree if not x.parent_area and x.name not in hidden]:
		parts = [x for x in tree if x.parent_area == a.name and x.name not in hidden and not x.is_focus]
		subs = [{"name": "", "label": "", "area": a.name, "tasks": by.pop(a.name, [])}]
		subs += [{"name": p.name, "label": p.area_name, "area": p.name, "tasks": by.pop(p.name, [])} for p in parts]
		subs = [s for s in subs if s["tasks"]]
		if subs:
			out.append({"key": a.name, "label": a.area_name, "colour": a.colour, "area": a.name, "count": sum(len(s["tasks"]) for s in subs), "parts": subs})
	loose = [t for ts in by.values() for t in ts]  # no area, or an area that is gone: listed last so no task is hidden
	if loose:
		out.append({"key": "none", "label": "No area", "colour": None, "area": "", "count": len(loose), "parts": [{"name": "", "label": "", "area": "", "tasks": loose}]})
	return out


def _by_goal(space, rows, show, now, week_end):
	by = {}
	for r in rows:
		by.setdefault(r.goal or "", []).append(r)
	goals = frappe.get_list("Life Goal", filters={"name": ("in", [g for g in by if g] or [""])}, fields=["name", "title", "area"], order_by="sort_order asc, creation asc", limit=0)
	out = [{"key": g.name, "label": g.title, "colour": None, "goal": g.name, "area": g.area or "", "count": len(by[g.name]),
		"parts": [{"name": "", "label": "", "area": g.area or "", "tasks": by[g.name]}]} for g in goals]
	if by.get(""):
		out.append({"key": "none", "label": "No goal", "colour": None, "goal": "", "area": "", "count": len(by[""]),
			"parts": [{"name": "", "label": "", "area": "", "tasks": by[""]}]})
	return out


def _by_due(space, rows, show, now, week_end):
	if show == "done":
		return [{"key": "done", "label": "Done", "colour": None, "area": "", "count": len(rows), "parts": [{"name": "", "label": "", "area": "", "tasks": rows}]}] if rows else []
	by = {k: [] for k, _label in DUE_GROUPS}
	for r in rows:
		by[_due_group(r, now, week_end)].append(r)
	return [{"key": k, "label": label, "colour": None, "area": "", "count": len(by[k]), "parts": [{"name": "", "label": "", "area": "", "tasks": by[k]}]}
		for k, label in DUE_GROUPS if by[k]]


NO_GOAL = "and t.is_archived = 0 and t.status in ('Open', 'Doing', 'Waiting') and ifnull(t.goal, '') = '' and ifnull(t.standalone, 0) = 0"


def no_goal_count(space):
	"""Open tasks with no goal that nobody has marked as fine without one. Tasks of an area that is off count too: they are
	listed on Goals > No goal until the owner decides."""
	# nosemgrep: frappe-sql-format-injection -- NO_GOAL is a constant fragment
	return frappe.db.sql(f"select count(*) from `tabLife Task` t where t.space=%(space)s {NO_GOAL}", {"space": space})[0][0]


@frappe.whitelist(methods=["GET"])
def no_goal_total(space: str | None = None):
	"""The number on the Goals > No goal tab."""
	return {"count": no_goal_count(permissions.resolve_space(space))}


@frappe.whitelist(methods=["GET"])
def no_goal(space: str | None = None):
	"""Goals → No goal: open tasks with no goal, grouped by the area of life they are filed in (a part sits under its area; an
	area that is off still shows, marked, until the owner decides). Each group has `suggestion` when three or more of its tasks
	share a word ({word, title, tasks}): a goal they may belong to, made only by `make_goal`. `goals` are the goals in progress
	for the picker, the group's own first."""
	from lifeos import goal_suggest
	from lifeos.areas import off as areas_off

	space = permissions.resolve_space(space)
	rows = query(space, NO_GOAL, {}, None, 0, ALL_CAP + 1, ["standalone"], hide_off=False)
	truncated = len(rows) > ALL_CAP
	rows = rows[:ALL_CAP]
	tree = frappe.get_list("Life Area", filters={"space": space, "is_archived": 0}, fields=["name", "area_name", "parent_area", "colour"],
		order_by="sort_order asc, area_name asc", limit=5000)
	hidden = set(areas_off(space))
	top = {a.name: a.parent_area or a.name for a in tree}
	label = {a.name: a.area_name for a in tree}
	by = {}
	for r in rows:
		r["part"] = label.get(r.area) if top.get(r.area) not in (None, r.area) else None
		by.setdefault(top.get(r.area, ""), []).append(r)
	groups = []
	for a in [x for x in tree if not x.parent_area]:
		if a.name in by:
			ts = by.pop(a.name)
			groups.append({"key": a.name, "label": a.area_name, "colour": a.colour, "area": a.name, "is_on": a.name not in hidden, "count": len(ts),
				"tasks": ts, "suggestion": goal_suggest.cluster(ts) if a.name not in hidden else None})
	loose = [t for ts in by.values() for t in ts]
	if loose:
		groups.append({"key": "none", "label": "No area", "colour": None, "area": "", "is_on": True, "count": len(loose), "tasks": loose, "suggestion": None})
	from lifeos.api import goals

	return {"space": space, "total": len(rows), "truncated": truncated, "groups": groups, "goals": goals.picker(space), "today": today()}


@frappe.whitelist(methods=["POST"])
def keep_standalone(task: str):
	"""Fine as is: the task stays without a goal and leaves Goals > No goal. Its guessed area, if any, is confirmed."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	doc.standalone = 1
	doc.area_guessed = 0
	doc.area_confidence = 0
	doc.save()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def make_goal(tasks: str | builtins.list, space: str | None = None, area: str | None = None, title: str | None = None, done_when: str | None = None,
		measure_kind: str | None = None, measure: str | None = None, unit: str | None = None, start_value: float | str | None = None,
		target_value: float | str | None = None):
	"""Make it a goal: one Open goal in `area` (named `title`, else by the assistant when a key is set, else from the task
	titles) and every one of `tasks` put under it. With the setting "Require Done when on new goals" on, it needs `done_when` or a number. Only open tasks with no goal in this space are taken."""
	from lifeos import goal_suggest
	from lifeos.api import goals

	space = permissions.resolve_space(space, write=True)
	names = frappe.parse_json(tasks) if isinstance(tasks, str) else tasks
	docs = [permissions.get_doc_checked("Life Task", n, "write") for n in names or []]
	if not docs:
		frappe.throw(_("Choose the tasks for the goal."))
	for d in docs:
		if d.space != space or d.goal or d.status not in OPEN:
			frappe.throw(_("{0} is not an open task without a goal.").format(frappe.bold(d.title)))
	if area and frappe.db.get_value("Life Area", area, "space") != space:
		frappe.throw(_("That area is not in this space."))
	area = area or next((d.area for d in docs if d.area), None)
	title = (title or "").strip() or goal_suggest.title_for([d.title for d in docs], space)
	goal = goals.create(title=title, horizon="Year", target_date=goals.year_end(), space=space, area=area, done_when=done_when, measure_kind=measure_kind, measure=measure,
		unit=unit, start_value=start_value, target_value=target_value)
	for d in docs:
		d.goal = goal["name"]
		d.save()
	return {"goal": goal["name"], "title": goal["title"], "area": area, "tasks": [d.name for d in docs]}


@frappe.whitelist(methods=["GET"])
def get(task: str):
	"""One task with its filing and source."""
	doc = permissions.get_doc_checked("Life Task", task)
	row = decorate([frappe._dict({f: doc.get(f) for f in FIELDS})])[0]
	row["also_in"] = [r.area for r in doc.also_in]
	row["space"] = doc.space
	from lifeos import links

	row["links"] = links.outgoing(doc)  # the [[links]] in its notes, for the editor's chips
	return row


@frappe.whitelist(methods=["POST"])
def quick_add(text: str, space: str | None = None, area: str | None = None, goal: str | None = None,
		due_date: str | date | None = None, priority: str | None = None):
	"""Create a task from one line of text. A date word such as "tomorrow" or "fri" at the start or end sets the due date."""
	space = permissions.resolve_space(space, write=True)
	title, when = datewords.parse(text)
	if not title:
		frappe.throw(_("Type a title for the task."))
	if goal and not area:
		area = frappe.db.get_value("Life Goal", goal, "area")
	doc = frappe.get_doc({"doctype": "Life Task", "space": space, "title": title[:140], "due_date": due_date or when, "area": area,
		"goal": goal, "priority": priority, "status": "Open"}).insert()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def set_status(task: str, status: str, waiting_on: str | None = None):
	"""Change a task's status. Done fills completed_on. Waiting needs waiting_on."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	if status == "Someday" and doc.status != "Someday":  # parking goes through Someday, which agents may not do
		from lifeos.api import someday

		someday.park("Life Task", task)
		return get(task)
	was_done = doc.status == "Done"
	doc.status = status
	if waiting_on is not None:
		doc.waiting_on = waiting_on
	doc.save()
	if status == "Done" and not was_done:
		tick_lead_action(doc)
	return get(doc.name)


def tick_lead_action(task):
	"""Issue 55: finishing a task planned under a goal of the active cycle ticks the goal's lead action of the same title for
	this week, once more (up to its times a week). A task with no matching lead action ticks nothing."""
	if not task.goal:
		return
	cycle = frappe.db.get_value("Life Goal", task.goal, "cycle")
	if not cycle or frappe.db.get_value("Life Cycle", cycle, "status") != "Active":
		return
	week = cycles.week_of(frappe.get_doc("Life Cycle", cycle), getdate(today()))
	if not 1 <= week <= cycles.WEEKS:
		return
	title = (task.title or "").strip().lower()
	for a in frappe.get_list("Life Goal Action", filters={"parent": task.goal, "status": "Open"}, fields=["name", "title", "per_week"], parent_doctype="Life Goal"):
		if (a.title or "").strip().lower() == title:
			have = cycles._ticks(cycle).get(a.name, {}).get(week, 0)
			try:
				cycles.set_tick(a.name, week, have + 1)
			except frappe.PermissionError:  # someone who may finish the task but not change the goal's ticks
				pass
			return


@frappe.whitelist(methods=["POST"])
def update(task: str, values: str | dict):
	"""Change fields of a task. Only task fields a person edits are accepted."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	values = frappe.parse_json(values) or {}
	gone_names.refuse(values)
	allowed = {"title", "status", "priority", "due_date", "goal", "notes_md", "waiting_on", "waiting_on_person", "delegated_to", "area", "source_url", "scheduled_at", "duration_min"}
	for k, v in values.items():
		if k == "also_in":
			doc.set("also_in", [{"area": a} for a in v or []])
		elif k in allowed:
			doc.set(k, v or None)
		else:
			frappe.throw(_("Field {0} cannot be changed here.").format(k))
	doc.save()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def confirm_area(task: str, area: str | None = None):
	"""Confirm the area the Brain guessed for a task, or move the task to `area`. Either clears the guess mark; a move is
	kept as a correction (issue 13)."""
	from lifeos import area_guess

	doc = permissions.get_doc_checked("Life Task", task, "write")
	area_guess.confirm(doc, area or None)
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def carry_forward(task: str):
	"""Copy an open task, mark the old one Carried and set carried_from."""
	out = cycles.carry_task(task)
	return {**out, "new_task": get(out["task"])}


def open_loops_where():
	return "and t.status in ('Open', 'Doing', 'Waiting') and t.is_archived = 0 and t.due_date is null and t.creation < %(cutoff)s"


def open_loops_count(space):
	return frappe.db.sql(  # nosemgrep: frappe-sql-format-injection -- open_loops_where() is a constant fragment
		f"select count(*) from `tabLife Task` t where t.space=%(space)s {open_loops_where()}",
		{"space": space, "cutoff": add_days(today(), -OPEN_LOOP_DAYS)})[0][0]


@frappe.whitelist(methods=["GET"])
def open_loops(space: str | None = None, start: int | str | None = 0, page_length: int | str | None = 50):
	"""Open tasks older than 14 days with no due date."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	rows = query(space, open_loops_where(), {"cutoff": add_days(today(), -OPEN_LOOP_DAYS)}, "t.creation asc", start, page_length)
	return {"tasks": rows, "total": open_loops_count(space), "today": today()}


def stale_tasks(space, limit=50):
	"""Open tasks not touched for `stale_task_days`. Never archived."""
	days = frappe.db.get_single_value("Life Settings", "stale_task_days") or 90
	return query(space, "and t.status in ('Open', 'Doing', 'Waiting') and t.is_archived = 0 and ifnull(t.last_touched_on, date(t.creation)) <= %(cutoff)s",
		{"cutoff": add_days(today(), -days)}, "t.creation asc", 0, limit)


@frappe.whitelist(methods=["POST"])
def reschedule_overdue(space: str | None = None, to_date: str | date | None = None):
	"""Move every open overdue task of a space (Open, Doing or Waiting, not archived, due before today) to `to_date`,
	today by default. Each task is saved on its own, with the same write check as `update`. Returns how many moved."""
	space = permissions.resolve_space(space, write=True)
	now = getdate(today())
	to = getdate(to_date) if to_date else now
	if to < now:
		frappe.throw(_("Overdue tasks can only be moved to today or later."))
	names = frappe.db.sql_list(
		"select name from `tabLife Task` where space=%s and status in ('Open', 'Doing', 'Waiting') and is_archived=0 and due_date < %s",
		(space, now))
	for name in names:
		doc = permissions.get_doc_checked("Life Task", name, "write")
		doc.due_date = to
		doc.save()
	return {"moved": len(names), "due_date": str(to)}
