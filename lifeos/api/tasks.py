"""Tasks: list, quick add, status, carry forward, open loops."""
import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos import datewords, journal, permissions
from lifeos.api.utils import flag, names_map, page

OPEN = ("Open", "Doing", "Waiting")
FIELDS = ["name", "title", "status", "priority", "due_date", "area", "project", "goal", "inbox_item", "carried_from", "waiting_on",
	"month_plan", "creation", "completed_on", "source_url", "is_archived", "notes_md", "last_touched_on", "owner"]
PRIORITY_ORDER = "case t.priority when 'I' then 1 when 'II' then 2 when 'III' then 3 when 'IV' then 4 else 5 end"
OPEN_LOOP_DAYS = 14


def decorate(rows):
	"""Add the names a list row shows: area, project, goal, tags."""
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	projects = names_map("Life Project", [r.project for r in rows], "title")
	goals = names_map("Life Goal", [r.goal for r in rows], "title")
	sources = names_map("Life Inbox Item", [r.inbox_item for r in rows], "title")
	tags = {}
	if rows:
		for parent, tag in frappe.db.sql(
			"select l.parent, g.tag_name from `tabLife Tag Link` l join `tabLife Tag` g on g.name = l.tag where l.parenttype='Life Task' and l.parent in %s",
			([r.name for r in rows],)):
			tags.setdefault(parent, []).append(tag)
	for r in rows:
		r["area_name"], r["project_title"], r["goal_title"] = areas.get(r.area), projects.get(r.project), goals.get(r.goal)
		r["source_title"] = sources.get(r.inbox_item)
		r["tags"] = tags.get(r.name, [])
		for k in ("due_date", "creation", "completed_on", "last_touched_on"):
			r[k] = str(r[k])[:19] if r.get(k) else None
	return rows


def query(space, where="", values=None, order=None, start=0, page_length=50):
	cols = ", ".join(f"t.`{f}`" for f in FIELDS)
	order = order or f"t.due_date is null, t.due_date asc, {PRIORITY_ORDER}, t.creation asc"
	rows = frappe.db.sql(
		f"select {cols} from `tabLife Task` t where t.space=%(space)s {where} order by {order} limit %(start)s, %(len)s",
		{"space": space, "start": start, "len": page_length, **(values or {})}, as_dict=True)
	return decorate(rows)


@frappe.whitelist()
def list(space=None, status="open", area=None, project=None, tag=None, priority=None, goal=None, month_plan=None,
		include_archived=0, start=0, page_length=50):
	"""Tasks of a space. status: open, done, all, or one status. Sorted by due date, then priority I first."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = [], {}
	if status == "open":
		where.append("t.status in ('Open', 'Doing', 'Waiting')")
	elif status == "done":
		where.append("t.status in ('Done', 'Dropped', 'Carried')")
	elif status and status != "all":
		where.append("t.status = %(status)s")
		values["status"] = status
	if not flag(include_archived):
		where.append("t.is_archived = 0")
	if area:
		where.append("(t.area = %(area)s or exists (select 1 from `tabLife Also In` ai where ai.parent = t.name and ai.parenttype='Life Task' and ai.area = %(area)s))")
		values["area"] = area
	if project:
		where.append("t.project = %(project)s")
		values["project"] = project
	if tag:
		where.append("exists (select 1 from `tabLife Tag Link` tl where tl.parent = t.name and tl.parenttype='Life Task' and tl.tag = %(tag)s)")
		values["tag"] = tag
	if priority:
		where.append("ifnull(t.priority, '') = %(priority)s")
		values["priority"] = "" if priority == "none" else priority
	if goal:
		where.append("t.goal = %(goal)s")
		values["goal"] = goal
	if month_plan:
		where.append("t.month_plan = %(month_plan)s")
		values["month_plan"] = month_plan
	clause = (" and " + " and ".join(where)) if where else ""
	order = "t.completed_on desc, t.modified desc" if status == "done" else None
	rows = query(space, clause, values, order, start, page_length)
	total = frappe.db.sql(f"select count(*) from `tabLife Task` t where t.space=%(space)s {clause}", {"space": space, **values})[0][0]
	return {"tasks": rows, "total": total, "start": start, "page_length": page_length, "today": today()}


@frappe.whitelist()
def get(task):
	doc = permissions.get_doc_checked("Life Task", task)
	row = decorate([frappe._dict({f: doc.get(f) for f in FIELDS})])[0]
	row["also_in"] = [r.area for r in doc.also_in]
	row["tag_ids"] = [r.tag for r in doc.tags]
	row["space"] = doc.space
	return row


@frappe.whitelist(methods=["POST"])
def quick_add(text, space=None, area=None, project=None, goal=None, due_date=None, priority=None, month_plan=None):
	"""Create a task from one line of text. A date word such as "tomorrow" or "fri" at the start or end sets the due date."""
	space = permissions.resolve_space(space, write=True)
	title, when = datewords.parse(text)
	if not title:
		frappe.throw(_("Type a title for the task."))
	if project and not area:
		area = frappe.db.get_value("Life Project", project, "area")
	if goal and not area:
		area = frappe.db.get_value("Life Goal", goal, "area")
	doc = frappe.get_doc({"doctype": "Life Task", "space": space, "title": title[:140], "due_date": due_date or when, "area": area,
		"project": project, "goal": goal, "priority": priority, "month_plan": month_plan, "status": "Open"}).insert()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def set_status(task, status, waiting_on=None):
	"""Change a task's status. Done fills completed_on. Waiting needs waiting_on."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	doc.status = status
	if waiting_on is not None:
		doc.waiting_on = waiting_on
	doc.save()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def update(task, values):
	"""Change fields of a task. Only task fields a person edits are accepted."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	values = frappe.parse_json(values) or {}
	allowed = {"title", "status", "priority", "due_date", "goal", "notes_md", "waiting_on", "area", "project", "source_url", "month_plan"}
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
def carry_forward(task):
	"""Copy an open task into next month's plan, mark the old one Carried and set carried_from."""
	out = journal.carry_task(task)
	return {**out, "new_task": get(out["task"])}


def open_loops_where():
	return "and t.status in ('Open', 'Doing', 'Waiting') and t.is_archived = 0 and t.due_date is null and t.creation < %(cutoff)s"


def open_loops_count(space):
	return frappe.db.sql(
		f"select count(*) from `tabLife Task` t where t.space=%(space)s {open_loops_where()}",
		{"space": space, "cutoff": add_days(today(), -OPEN_LOOP_DAYS)})[0][0]


@frappe.whitelist()
def open_loops(space=None, start=0, page_length=50):
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
def decide_stale(task, decision):
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
