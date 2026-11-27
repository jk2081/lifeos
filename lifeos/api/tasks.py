"""Tasks: list, quick add, status, carry forward, open loops."""
import builtins
from datetime import date

import frappe
from frappe import _
from frappe.query_builder import Case, Order
from frappe.query_builder import functions as fn
from frappe.utils import add_days, getdate, today

from lifeos.goals import cycles
from lifeos.tasks import datewords
from lifeos.web import gone_names
from lifeos import permissions
from lifeos.goals.areas import off_criterion
from lifeos.api.utils import (area_criterion, count_tabs, extra_fields, filter_criteria, flag, group_summary, list_query, names_map, null_last,
	order_terms, page, sort_terms)

OPEN = ("Open", "Doing", "Waiting")
FIELDS = ["name", "title", "status", "priority", "due_date", "area", "area_guessed", "area_confidence", "goal", "inbox_item", "carried_from", "waiting_on",
	"waiting_on_person", "delegated_to", "handed_off_how", "creation", "completed_on", "source_url", "is_archived", "notes_md", "last_touched_on", "owner", "scheduled_at", "duration_min"]
OPEN_LOOP_DAYS = 14


def priority_rank(t):
	"""Priority I first, then II, III, IV, and tasks with none last."""
	return Case().when(t.priority == "I", 1).when(t.priority == "II", 2).when(t.priority == "III", 3).when(t.priority == "IV", 4).else_(5)


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


def query(space, where=(), order=(), start=0, page_length=50, fields=None, hide_off=True):
	"""The rows of a task list: `where` is a list of criteria over `frappe.qb.DocType("Life Task")`, `order` a list of (term, Order)."""
	t = frappe.qb.DocType("Life Task")
	where = [t.space == space, *where]
	off = off_criterion(space, t.area) if hide_off else None  # areas switched off (issue 11)
	if off is not None:
		where.append(off)
	order = order or [(term, Order.asc) for term in (*null_last(t.due_date), priority_rank(t), t.creation)]
	cols = [*FIELDS, *extra_fields("Life Task", fields, t, FIELDS)]
	return decorate(list_query("Life Task", cols, where, order).limit(page_length).offset(start).run(as_dict=True))


def due_criteria(t, now):
	week_start = add_days(now, -now.weekday())
	return {"overdue": t.due_date < now, "today": t.due_date == now, "week": t.due_date.between(week_start, add_days(now, 6 - now.weekday())),
		"none": t.due_date.isnull()}


DUE_KEYS = ("overdue", "today", "week", "none")
SORTS = {"due_date": lambda t: null_last(t.due_date), "priority": lambda t: [priority_rank(t)], "title": lambda t: [t.title], "status": lambda t: [t.status],
	"creation": lambda t: [t.creation], "completed_on": lambda t: [t.completed_on]}


def tab_criteria(t):
	"""The state tabs of the Tasks screen as criteria over the task table. "Open" on the screen is Open and Doing; Waiting has its own tab."""
	cutoff = add_days(today(), -OPEN_LOOP_DAYS)
	return {
		"open": t.status.isin(["Open", "Doing"]),
		"loops": t.status.isin(OPEN) & t.due_date.isnull() & (t.creation < cutoff),
		"Waiting": t.status == "Waiting",
		"Done": t.status == "Done",
		"Someday": t.status == "Someday",
		# All leaves out tasks parked on the Someday list (UX fixes, set 5); the Someday tab lists them
		"all": t.status != "Someday",
	}


def where_criteria(space, status="open_doing", area=None, priority=None, goal=None,
		include_archived=0, due=None, done=0, loops=0, completed_from=None, completed_to=None):
	"""The criteria of a task list. Every count in the app that leads to a task list is made with this, so the two agree.
	The default status, open_doing, is what the Open tab of the Tasks screen shows; "open" also holds Waiting tasks."""
	t = frappe.qb.DocType("Life Task")
	where = [t.space == space]
	if status == "open_doing":
		where.append(t.status.isin(["Open", "Doing"]))
	elif status == "open" and flag(done):
		where.append(t.status.isin(["Open", "Doing", "Waiting", "Done", "Dropped"]))
	elif status == "open":
		where.append(t.status.isin(OPEN))
	elif status == "done":
		where.append(t.status.isin(["Done", "Dropped", "Carried"]))
	elif status == "all":
		where.append(t.status != "Someday")
	elif status and status != "any":
		where.append(t.status == status)
	if not flag(include_archived):
		where.append(t.is_archived == 0)
	if area:
		where.append(area_criterion(space, area, t, also_in="Life Task"))
	off = off_criterion(space, t.area)  # tasks of an area that is off are hidden (issue 11)
	if off is not None:
		where.append(off)
	if priority:
		where.append(fn.IfNull(t.priority, "") == ("" if priority == "none" else priority))
	if goal:
		where.append(fn.IfNull(t.goal, "") == ("" if goal == "none" else goal))
	if due:
		now = getdate(today())
		known = due_criteria(t, now)
		parts = [known[d.strip()] for d in str(due).split(",") if d.strip() in DUE_KEYS]
		if not parts:
			frappe.throw(_("due must be one or more of: {0}.").format(", ".join(DUE_KEYS)), title=_("Due filter is not valid"))
		crit = parts[0]
		for p in parts[1:]:
			crit = crit | p
		where.append(crit)
	if flag(loops):
		where.append(t.due_date.isnull() & (t.creation < add_days(today(), -OPEN_LOOP_DAYS)))
	if completed_from:
		where.append(t.completed_on >= getdate(completed_from))
	if completed_to:
		where.append(t.completed_on <= getdate(completed_to))
	return where


def count_where(where):
	query = frappe.qb.get_query("Life Task", fields=[fn.Count("*")], ignore_permissions=False)
	for crit in where:
		query = query.where(crit)
	return query.run()[0][0]


def count(space, **filters):
	return count_where(where_criteria(space, **filters))


def list_criteria(space, status="open", area=None, priority=None, goal=None, include_archived=0,
		due=None, done=0, loops=0, completed_from=None, completed_to=None, filters=None):
	"""The criteria of `list`, and the part that came from `filters`."""
	extra = filter_criteria("Life Task", filters, frappe.qb.DocType("Life Task"))
	return where_criteria(space, status, area, priority, goal, include_archived, due, done, loops, completed_from, completed_to) + extra, extra


def total(space, status="open", due=None, filters=None, area=None):
	"""The `total` that `list` answers for these arguments, without its rows or tab counts: the counts on Today, Reset and
	the sidebar (lifeos/review/counts.py) use it, and the same criteria keep the number and the list in step."""
	space = permissions.resolve_space(space)
	return count_where(list_criteria(space, status, area=area, due=due, filters=filters)[0])


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
	t = frappe.qb.DocType("Life Task")
	where, extra = list_criteria(space, status, area, priority, goal, include_archived, due, done,
		loops, completed_from, completed_to, filters)
	# the tab counts: the same filters without the status and the open-loops switch, which are what a tab stands for
	tabs = count_tabs("Life Task", where_criteria(space, "any", area, priority, goal, include_archived, due, 0, 0, completed_from, completed_to) + extra, tab_criteria(t))
	if summary:
		return {"summary": group_summary("Life Task", where, summary, start, page_length), "today": today(), "tabs": tabs}
	finished = status in ("done", "Done", "Carried", "Dropped")
	default = [(t.completed_on, Order.desc), (t.modified, Order.desc)] if finished else []
	terms = order_terms("Life Task", order_by, t, SORTS)
	custom = bool(terms)
	if not terms:
		terms = sort_terms(sort, dir, SORTS, t, default)
		custom = bool(sort and sort in SORTS)
	if custom:
		terms = [*terms, (t.creation, Order.asc)]
	rows = query(space, where[1:], terms, start, page_length, fields)
	return {"tasks": rows, "total": count_where(where), "start": start, "page_length": page_length, "today": today(), "tabs": tabs}


ALL_SHOWS = ("open", "due", "waiting", "stuck", "someday", "done")


def show_criteria(t, now, stuck_days):
	"""The filters of Goals > All tasks as criteria over the task table."""
	return {
		"open": t.status.isin(OPEN),
		"due": t.status.isin(OPEN) & t.due_date.isnotnull() & (t.due_date <= add_days(now, 6 - now.weekday())),
		"waiting": t.status == "Waiting",
		"stuck": t.status.isin(OPEN) & (t.last_touched_on <= add_days(now, -stuck_days)),
		"someday": t.status == "Someday",
		"done": t.status == "Done",
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
		frappe.throw(_("Unknown filter."), title=_("Filter is not known"))
	if group not in ("area", "goal", "due"):
		frappe.throw(_("Unknown grouping."), title=_("Grouping is not known"))
	now = getdate(today())
	from lifeos.review import counts

	stuck_days = counts.rules()["stuck_after_days"]
	week_end = add_days(now, 6 - now.weekday())
	t = frappe.qb.DocType("Life Task")
	shows = show_criteria(t, now, stuck_days)
	base = [t.space == space, t.is_archived == 0]
	if area:
		base.append(area_criterion(space, area, t))
	if q and q.strip():
		base.append(t.title.like("%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"))
	order = [(t.completed_on, Order.desc), (t.modified, Order.desc)] if show == "done" else ()
	rows = query(space, [*base[1:], shows[show]], order, 0, ALL_CAP + 1, ["is_top_three"])
	truncated = len(rows) > ALL_CAP
	rows = rows[:ALL_CAP]
	# the same filters (and the areas that are off) without the tab's own condition, so each filter's count agrees with its list
	off = off_criterion(space, t.area)
	tab_numbers = count_tabs("Life Task", base + ([off] if off is not None else []), shows)
	groups = {"area": _by_area, "goal": _by_goal, "due": _by_due}[group](space, rows, show, now, week_end)
	areas = frappe.get_list("Life Area", filters={"space": space, "is_archived": 0, "is_life_area": 1}, fields=["name", "area_name", "colour", "is_on"],
		order_by="sort_order asc, area_name asc", limit=50)
	return {"space": space, "group": group, "show": show, "total": len(rows), "truncated": truncated, "counts": tab_numbers, "stuck_days": stuck_days, "groups": groups,
		"areas": [a for a in areas if a.is_on], "today": str(now)}


def _by_area(space, rows, show, now, week_end):
	from lifeos.goals.areas import off as areas_off

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


def no_goal_criteria(t):
	return [t.is_archived == 0, t.status.isin(OPEN), fn.IfNull(t.goal, "") == "", fn.IfNull(t.standalone, 0) == 0]


def no_goal_count(space):
	"""Open tasks with no goal that nobody has marked as fine without one. Tasks of an area that is off count too: they are
	listed on Goals > No goal until the owner decides."""
	t = frappe.qb.DocType("Life Task")
	return count_where([t.space == space, *no_goal_criteria(t)])


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
	from lifeos.goals import goal_suggest
	from lifeos.goals.areas import off as areas_off

	space = permissions.resolve_space(space)
	rows = query(space, no_goal_criteria(frappe.qb.DocType("Life Task")), (), 0, ALL_CAP + 1, ["standalone"], hide_off=False)
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
def make_goal(tasks: str | builtins.list, space: str | None = None, area: str | None = None, title: str | None = None, done_when: str | None = None,
		measure_kind: str | None = None, measure: str | None = None, unit: str | None = None, start_value: float | str | None = None,
		target_value: float | str | None = None):
	"""Make it a goal: one Open goal in `area` (named `title`, else by the assistant when a key is set, else from the task
	titles) and every one of `tasks` put under it. With the setting "Require Done when on new goals" on, it needs `done_when` or a number. Only open tasks with no goal in this space are taken."""
	from lifeos.goals import goal_suggest
	from lifeos.api import goals

	space = permissions.resolve_space(space, write=True)
	names = frappe.parse_json(tasks) if isinstance(tasks, str) else tasks
	docs = [permissions.get_doc_checked("Life Task", n, "write") for n in names or []]
	if not docs:
		frappe.throw(_("Choose the tasks for the goal."), title=_("Choose tasks for the goal"))
	for d in docs:
		if d.space != space or d.goal or d.status not in OPEN:
			frappe.throw(_("{0} is not an open task without a goal.").format(frappe.bold(d.title)), title=_("Task cannot join goal"))
	if area and frappe.db.get_value("Life Area", area, "space") != space:
		frappe.throw(_("That area is not in this space."), title=_("Area is in another space"))
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
	from lifeos.library import links

	row["links"] = links.outgoing(doc)  # the [[links]] in its notes, for the editor's chips
	return row


@frappe.whitelist(methods=["POST"])
def quick_add(text: str, space: str | None = None, area: str | None = None, goal: str | None = None,
		due_date: str | date | None = None, priority: str | None = None):
	"""Create a task from one line of text. A date word such as "tomorrow" or "fri" at the start or end sets the due date."""
	space = permissions.resolve_space(space, write=True)
	title, when = datewords.parse(text)
	if not title:
		frappe.throw(_("Type a title for the task."), title=_("Task needs a title"))
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
			frappe.throw(_("Field {0} cannot be changed here.").format(k), title=_("Field cannot be changed"))
	doc.save()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def confirm_area(task: str, area: str | None = None):
	"""Confirm the area the Brain guessed for a task, or move the task to `area`. Either clears the guess mark; a move is
	kept as a correction (issue 13)."""
	from lifeos.brain import area_guess

	doc = permissions.get_doc_checked("Life Task", task, "write")
	area_guess.confirm(doc, area or None)
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def carry_forward(task: str):
	"""Copy an open task, mark the old one Carried and set carried_from."""
	out = cycles.carry_task(task)
	return {**out, "new_task": get(out["task"])}


def open_loops_criteria(t):
	return [t.status.isin(OPEN), t.is_archived == 0, t.due_date.isnull(), t.creation < add_days(today(), -OPEN_LOOP_DAYS)]


def open_loops_count(space):
	t = frappe.qb.DocType("Life Task")
	return count_where([t.space == space, *open_loops_criteria(t)])


def stale_tasks(space, limit=50):
	"""Open tasks not touched for `stale_task_days`. Never archived."""
	days = frappe.db.get_single_value("Life Settings", "stale_task_days") or 90
	t = frappe.qb.DocType("Life Task")
	where = [t.status.isin(OPEN), t.is_archived == 0, fn.IfNull(t.last_touched_on, fn.Date(t.creation)) <= add_days(today(), -days)]
	return query(space, where, [(t.creation, Order.asc)], 0, limit)


@frappe.whitelist(methods=["POST"])
def reschedule_overdue(space: str | None = None, to_date: str | date | None = None):
	"""Move every open overdue task of a space (Open, Doing or Waiting, not archived, due before today) to `to_date`,
	today by default. Each task is saved on its own, with the same write check as `update`. Returns how many moved."""
	space = permissions.resolve_space(space, write=True)
	now = getdate(today())
	to = getdate(to_date) if to_date else now
	if to < now:
		frappe.throw(_("Overdue tasks can only be moved to today or later."), title=_("Date is in the past"))
	names = frappe.get_list("Life Task", filters={"space": space, "status": ("in", OPEN), "is_archived": 0, "due_date": ("<", now)}, pluck="name", limit_page_length=0)
	for name in names:
		doc = permissions.get_doc_checked("Life Task", name, "write")
		doc.due_date = to
		doc.save()
	return {"moved": len(names), "due_date": str(to)}


# ---- handing off, nudging and the answer (issue 130) ----
def _writable(space: str | None) -> str:
	return permissions.resolve_space(space, write=True)


@frappe.whitelist(methods=["POST"])
def hand_off(person: str, what: str | None = None, check_by: str | None = None, how: str = "track", channel: str = "email", task: str | None = None,
		space: str | None = None):
	"""Hand something off to a person: a Waiting task with the check date. `how` is track (nothing sent, the default), draft (a message written for you to
	send, edit or drop) or send (an email goes at once). `task` hands off a task that exists. Life OS never sends WhatsApp: that is a link."""
	from lifeos.tasks import handoff

	space = frappe.db.get_value("Life Task", task, "space") if task else _writable(space)
	permissions.require_space(space, write=True)
	out = handoff.hand_off_task(space, person, what or "", check_by, how, channel, task, "owner", _("Hand off by button"), what)
	return {**out, "task_row": get(out["task"])}


@frappe.whitelist(methods=["GET"])
def handoff_get(task: str):
	"""What the task layer shows of a hand-off: what was asked, the message, the replies and nudges, the WhatsApp link."""
	from lifeos.tasks import handoff

	return handoff.detail(task)


@frappe.whitelist(methods=["POST"])
def handoff_edit(task: str, text: str):
	"""Change the words of a draft."""
	from lifeos.tasks import handoff

	return handoff.edit_message(task, text)


@frappe.whitelist(methods=["POST"])
def handoff_send(task: str, text: str | None = None):
	"""Send a drafted email now (the owner pressed Send)."""
	from lifeos.tasks import handoff

	return handoff.send_draft(task, text)


@frappe.whitelist(methods=["POST"])
def handoff_discard(task: str):
	"""Drop a draft; the task goes on as tracking only."""
	from lifeos.tasks import handoff

	return handoff.discard_draft(task)


@frappe.whitelist(methods=["POST"])
def person_phone(person: str, phone: str):
	"""Save a person's phone, asked for once when a WhatsApp link needs it."""
	from lifeos.tasks import handoff

	return handoff.set_phone(person, phone)


@frappe.whitelist(methods=["POST"])
def nudge(task: str, channel: str | None = None):
	"""A two-line follow-up in the owner's voice, opened the way the hand-off went (an email draft, or the WhatsApp link). The check date moves 3 days on."""
	from lifeos.tasks import handoff

	return handoff.nudge(task, channel)


@frappe.whitelist(methods=["POST"])
def nudge_decide(task: str, to: str):
	"""After two nudges: week (wait a week), plate (take it back) or drop."""
	from lifeos.tasks import handoff

	return handoff.decide_nudged(task, to)


@frappe.whitelist(methods=["POST"])
def looks_done_confirm(task: str):
	"""Confirm: the reply answered it, so the task is Done and the attachment is filed with it."""
	from lifeos.tasks import handoff

	return handoff.confirm(task)


@frappe.whitelist(methods=["POST"])
def looks_done_not_yet(task: str):
	"""Not yet: it stays waiting."""
	from lifeos.tasks import handoff

	return handoff.not_yet(task)


@frappe.whitelist(methods=["GET"])
def person_owed(person: str):
	"""A person's layer: what they owe you (open waiting tasks on them) and what you owe them (open tasks about them)."""
	from lifeos.tasks import handoff

	space = frappe.db.get_value("Life Person", person, "space")
	permissions.require_space(space)
	return handoff.owed(space, person)
