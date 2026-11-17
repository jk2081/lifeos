"""Tasks: list, quick add, status, carry forward, open loops."""
import builtins
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos import datewords, journal, permissions
from lifeos.proposals import goal_for_project
from lifeos.api.utils import area_filter, extra_columns, flag, names_map, page, std_clause, std_order, summarise, tab_counts
from lifeos.api.utils import order_by as sort_order

OPEN = ("Open", "Doing", "Waiting")
FIELDS = ["name", "title", "status", "priority", "due_date", "area", "goal", "inbox_item", "carried_from", "waiting_on",
	"month_plan", "creation", "completed_on", "source_url", "is_archived", "notes_md", "last_touched_on", "owner", "scheduled_at", "duration_min"]
PRIORITY_ORDER = "case t.priority when 'I' then 1 when 'II' then 2 when 'III' then 3 when 'IV' then 4 else 5 end"
OPEN_LOOP_DAYS = 14


def decorate(rows):
	"""Add the names a list row shows: area, goal, tags."""
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	goals = names_map("Life Goal", [r.goal for r in rows], "title")
	sources = names_map("Life Inbox Item", [r.inbox_item for r in rows], "title")
	tags = {}
	if rows:
		for parent, tag in frappe.db.sql(
			"select l.parent, g.tag_name from `tabLife Tag Link` l join `tabLife Tag` g on g.name = l.tag where l.parenttype='Life Task' and l.parent in %s",
			([r.name for r in rows],)):
			tags.setdefault(parent, []).append(tag)
	for r in rows:
		r["area_name"], r["goal_title"] = areas.get(r.area), goals.get(r.goal)
		r["source_title"] = sources.get(r.inbox_item)
		r["tags"] = tags.get(r.name, [])
		for k in ("due_date", "creation", "completed_on", "last_touched_on"):
			r[k] = str(r[k])[:19] if r.get(k) else None
	return rows


def query(space, where="", values=None, order=None, start=0, page_length=50, fields=None):
	cols = ", ".join([f"t.`{f}`" for f in FIELDS] + extra_columns("Life Task", fields, "t", FIELDS))
	order = order or f"t.due_date is null, t.due_date asc, {PRIORITY_ORDER}, t.creation asc"
	# columns are FIELDS or pass column() (DocType meta); WHERE comes from where_clause and ORDER from SORTS or std_order
	# nosemgrep: frappe-sql-format-injection -- fixed SQL and meta-checked columns only; values are parameters
	rows = frappe.db.sql(
		f"select {cols} from `tabLife Task` t where t.space=%(space)s {where} order by {order} limit %(start)s, %(len)s",
		{"space": space, "start": start, "len": page_length, **(values or {})}, as_dict=True)
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


def where_clause(space, status="open_doing", area=None, project=None, tag=None, priority=None, goal=None, month_plan=None,
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
	if project and not goal:  # for one set after projects became goals (set 6): a project names the goal it became
		goal = project if project == "none" else (goal_for_project(project, space) or project)
	if tag:
		where.append("exists (select 1 from `tabLife Tag Link` tl where tl.parent = t.name and tl.parenttype='Life Task' and tl.tag = %(tag)s)")
		values["tag"] = tag
	if priority:
		where.append("ifnull(t.priority, '') = %(priority)s")
		values["priority"] = "" if priority == "none" else priority
	if goal:
		where.append("ifnull(t.goal, '') = %(goal)s")
		values["goal"] = "" if goal == "none" else goal
	if month_plan:
		where.append("t.month_plan = %(month_plan)s")
		values["month_plan"] = month_plan
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


def list_clause(space, status="open", area=None, project=None, tag=None, priority=None, goal=None, month_plan=None, include_archived=0,
		due=None, done=0, loops=0, completed_from=None, completed_to=None, filters=None):
	"""The WHERE of `list`, its values, and the part that came from `filters`."""
	clause, values = where_clause(space, status, area, project, tag, priority, goal, month_plan, include_archived, due, done, loops,
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
def list(space: str | None = None, status: str | None = "open", area: str | None = None, project: str | None = None,
		tag: str | None = None, priority: str | None = None, goal: str | None = None, month_plan: str | None = None,
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
	clause, values, extra = list_clause(space, status, area, project, tag, priority, goal, month_plan, include_archived, due, done,
		loops, completed_from, completed_to, filters)
	# the tab counts: the same filters without the status and the open-loops switch, which are what a tab stands for
	t_clause, t_values = where_clause(space, "any", area, project, tag, priority, goal, month_plan, include_archived, due, 0, 0,
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


@frappe.whitelist(methods=["GET"])
def get(task: str):
	"""One task with its filing, source and tags."""
	doc = permissions.get_doc_checked("Life Task", task)
	row = decorate([frappe._dict({f: doc.get(f) for f in FIELDS})])[0]
	row["also_in"] = [r.area for r in doc.also_in]
	row["tag_ids"] = [r.tag for r in doc.tags]
	row["space"] = doc.space
	from lifeos import links

	row["links"] = links.outgoing(doc)  # the [[links]] in its notes, for the editor's chips
	return row


@frappe.whitelist(methods=["POST"])
def quick_add(text: str, space: str | None = None, area: str | None = None, project: str | None = None, goal: str | None = None,
		due_date: str | date | None = None, priority: str | None = None, month_plan: str | None = None):
	"""Create a task from one line of text. A date word such as "tomorrow" or "fri" at the start or end sets the due date."""
	space = permissions.resolve_space(space, write=True)
	title, when = datewords.parse(text)
	if not title:
		frappe.throw(_("Type a title for the task."))
	if project and not goal:
		goal = goal_for_project(project, space) or project
	if goal and not area:
		area = frappe.db.get_value("Life Goal", goal, "area")
	doc = frappe.get_doc({"doctype": "Life Task", "space": space, "title": title[:140], "due_date": due_date or when, "area": area,
		"goal": goal, "priority": priority, "month_plan": month_plan, "status": "Open"}).insert()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def set_status(task: str, status: str, waiting_on: str | None = None):
	"""Change a task's status. Done fills completed_on. Waiting needs waiting_on."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	if status == "Someday" and doc.status != "Someday":  # parking goes through Someday, which agents may not do
		from lifeos.api import someday

		someday.park("Life Task", task)
		return get(task)
	doc.status = status
	if waiting_on is not None:
		doc.waiting_on = waiting_on
	doc.save()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def update(task: str, values: str | dict):
	"""Change fields of a task. Only task fields a person edits are accepted."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	values = frappe.parse_json(values) or {}
	allowed = {"title", "status", "priority", "due_date", "goal", "notes_md", "waiting_on", "area", "source_url", "month_plan", "scheduled_at", "duration_min"}
	if values.get("project") and not values.get("goal"):  # for one set: a project names the goal it became
		values["goal"] = goal_for_project(values["project"], doc.space) or values["project"]
	values.pop("project", None)
	for k, v in values.items():
		if k == "also_in":
			doc.set("also_in", [{"area": a} for a in v or []])
		elif k == "tag_ids":
			doc.set("tags", [{"tag": t} for t in v or []])
		elif k in allowed:
			doc.set(k, v or None)
		else:
			frappe.throw(_("Field {0} cannot be changed here.").format(k))
	doc.save()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def carry_forward(task: str):
	"""Copy an open task into next month's plan, mark the old one Carried and set carried_from."""
	out = journal.carry_task(task)
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
	"""Open tasks not touched for `stale_task_days`. Never archived; the weekly review lists them under Decide."""
	days = frappe.db.get_single_value("Life Settings", "stale_task_days") or 90
	return query(space, "and t.status in ('Open', 'Doing', 'Waiting') and t.is_archived = 0 and ifnull(t.last_touched_on, date(t.creation)) <= %(cutoff)s",
		{"cutoff": add_days(today(), -days)}, "t.creation asc", 0, limit)


@frappe.whitelist(methods=["POST"])
def decide_stale(task: str, decision: str):
	"""The three buttons under Decide in the weekly review: do (due this week), carry, drop."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	if decision == "do":
		now = getdate(today())
		doc.due_date = add_days(now, 6 - now.weekday())
		doc.save()
	elif decision == "carry":
		return carry_forward(task)
	elif decision == "drop":
		doc.status = "Dropped"
		doc.save()
	else:
		frappe.throw(_("decision must be do, carry or drop."))
	return get(doc.name)


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
