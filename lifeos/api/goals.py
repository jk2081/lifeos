"""Goals of every type: 12 Week Year goals (in a cycle, with weekly actions), Annual goals (with a target date) and
Open goals. One list across types with the share of their tasks that is done."""
import builtins

import frappe
from frappe import _
from frappe.utils import getdate

from lifeos import journal as rules
from lifeos import permissions
from lifeos.api.utils import area_filter, page, std_clause, std_order, summarise, tab_counts
from lifeos.proposals import goal_for_project
from lifeos.api.utils import order_by as sort_order

TYPES = ("12 Week Year", "Annual", "Open")
CLOSED = ("Partly Achieved", "Not Achieved", "Carried", "Dropped")
OUTCOMES = ("In Progress", "Achieved", *CLOSED)
# the state tabs of the Goals screen
# Someday goals (UX fixes, set 5) leave In progress and have their own tab; their outcome is not changed
TABS = {"in_progress": "g.outcome = 'In Progress' and g.is_someday = 0 and g.is_archived = 0", "achieved": "g.outcome = 'Achieved'",
	"closed": "g.outcome in ('Partly Achieved', 'Not Achieved', 'Carried', 'Dropped')", "someday": "g.is_someday = 1", "all": "g.is_someday = 0"}
COUNTED = ("Open", "Doing", "Waiting", "Done")
SORTS = {"title": "g.title", "target_date": "g.target_date is null, g.target_date", "completion": "_completion",
	"creation": "g.creation"}


def task_counts(goals):
	"""{goal: (done, counted)} in one grouped query. Counted tasks are those filed under the goal itself whose status is
	Open, Doing, Waiting or Done; archived ones count, so the figure does not fall when done tasks are archived. Tasks
	that serve it through another goal count only under that goal. Only tasks in the user's spaces are counted."""
	goals = [g for g in goals if g]
	spaces = [*permissions.user_spaces()] if frappe.session.user != "Administrator" else None
	if not goals or spaces == []:
		return {}
	sp = "and t.space in %(spaces)s" if spaces is not None else ""
	# nosemgrep: frappe-sql-format-injection -- `sp` is one of two constant fragments; values are parameters
	rows = frappe.db.sql(f"""select t.goal, sum(t.status = 'Done'), count(*) from `tabLife Task` t
		where t.goal in %(goals)s and t.status in %(counted)s {sp} group by t.goal""",
		{"goals": goals, "counted": COUNTED, "spaces": spaces or [""]})
	return {g: (int(done or 0), int(n or 0)) for g, done, n in rows}


def with_tasks(rows, key="name"):
	counts = task_counts([r[key] for r in rows])
	for r in rows:
		done, n = counts.get(r[key], (0, 0))
		r["tasks_done"], r["tasks_counted"] = done, n
	return rows


def where_clause(space, state=None, goal_type=None, area=None, cycle=None, target_from=None, target_to=None, serves=None):
	where, values = [], {}
	if state:
		if state not in TABS:
			frappe.throw(_("Unknown state."))
		where.append(TABS[state])
	if goal_type:
		where.append("g.goal_type = %(goal_type)s")
		values["goal_type"] = goal_type
	if area:
		where.append(area_filter(space, area, "g.area", values))
	if serves:
		where.append("g.serves = %(serves)s")
		values["serves"] = serves
	if cycle:
		where.append("g.cycle = %(cycle)s")
		values["cycle"] = cycle
	if target_from:
		where.append("g.target_date >= %(target_from)s")
		values["target_from"] = target_from
	if target_to:
		where.append("g.target_date <= %(target_to)s")
		values["target_to"] = target_to
	return "".join(" and " + w for w in where), values


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, state: str | None = "in_progress", goal_type: str | None = None, area: str | None = None,
		cycle: str | None = None, target_from: str | None = None, target_to: str | None = None, sort: str | None = None, dir: str | None = None, start: int = 0, page_length: int = 50,
		filters: str | builtins.list | None = None, order_by: str | None = None, summary: str | dict | None = None, serves: str | None = None):
	"""Goals of a space of every type. state: in_progress (default), achieved, closed (Partly Achieved, Not Achieved,
	Carried, Dropped) or all. Each row has tasks_done and tasks_counted, and `score` (the 12 Week Year percentage; None
	for other types). `tabs` counts each state under the other filters; `summary_line` has goals in progress and tasks
	done out of counted across the goals the filters match. `serves` keeps the goals that serve one goal. Former projects are
	goals of type Open (set 6): each row also has on_hold, done_when, serves and its title, and last_activity_on."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = where_clause(space, state, goal_type, area, cycle, target_from, target_to, serves)
	extra, values = std_clause("Life Goal", filters, "g", values)
	where += extra
	t_where, t_values = where_clause(space, None, goal_type, area, cycle, target_from, target_to, serves)
	base = {"space": space}
	tabs = tab_counts(f"from `tabLife Goal` g where g.space=%(space)s {t_where}{extra}", {**t_values, **values, **base}, TABS)
	if summary:
		return {"summary": summarise("Life Goal", f"from `tabLife Goal` g where g.space=%(space)s {where}", {**base, **values}, "g", summary, start, page_length), "tabs": tabs}
	# nosemgrep: frappe-sql-format-injection -- WHERE from where_clause (TABS map) and std_clause (meta-checked columns); values are parameters
	names = frappe.db.sql(f"select g.name from `tabLife Goal` g where g.space=%(space)s {where}", {**base, **values}, pluck=True)
	counts = task_counts(names)
	total_done = sum(counts.get(n, (0, 0))[0] for n in names)
	total_counted = sum(counts.get(n, (0, 0))[1] for n in names)
	completion = (order_by or "").startswith("completion") or sort == "completion"
	order = None if completion else std_order("Life Goal", order_by, "g")
	if not order and not completion:
		order = sort_order(sort, dir, {k: v for k, v in SORTS.items() if k != "completion"}, "field(g.goal_type, '12 Week Year', 'Annual', 'Open'), g.target_date is null, g.target_date, g.creation")
	# nosemgrep: frappe-sql-format-injection -- WHERE from where_clause (TABS map) and std_clause (meta-checked columns); ORDER from SORTS or std_order
	rows = frappe.db.sql(f"""select g.name, g.title, g.goal_type, g.area, g.serves, g.cycle, g.target_date, g.outcome, g.closed_on,
		g.result_note, g.final_score, g.on_hold, g.done_when, g.last_activity_on, g.is_archived, g.is_someday,
		a.area_name, c.title as cycle_title, c.status as cycle_status, s.title as serves_title
		from `tabLife Goal` g left join `tabLife Area` a on a.name = g.area left join `tabLife Cycle` c on c.name = g.cycle
		left join `tabLife Goal` s on s.name = g.serves
		where g.space=%(space)s {where} order by {order or 'g.creation'}""" + ("" if completion else " limit %(start)s, %(len)s"),
		{**base, **values, "start": start, "len": page_length}, as_dict=True)
	with_tasks(rows)
	if completion:
		desc = "desc" in (order_by or dir or "").lower()
		rows.sort(key=lambda r: (r.tasks_done / r.tasks_counted) if r.tasks_counted else -1, reverse=desc)
		rows = rows[start:start + page_length]
	scores = _scores([r for r in rows if r.goal_type == "12 Week Year" and r.cycle])
	for r in rows:
		r["target_date"] = str(r.target_date) if r.target_date else None
		r["closed_on"] = str(r.closed_on) if r.closed_on else None
		r["last_activity_on"] = str(r.last_activity_on) if r.last_activity_on else None
		r["score"] = scores.get(r.name) if r.goal_type == "12 Week Year" else None
	return {"goals": rows, "total": len(names), "tabs": tabs,
		"summary_line": {"in_progress": tabs["in_progress"], "tasks_done": total_done, "tasks_counted": total_counted}}


def _scores(rows):
	"""The 12 Week Year percentage of each goal, as the grid shows it (the final score once the cycle is closed)."""
	out = {}
	for cycle in {r.cycle for r in rows}:
		for g in rules.grid(cycle)["goals"]:
			status = frappe.db.get_value("Life Cycle", cycle, "status")
			out[g["name"]] = g["final_score"] if status == "Closed" and g.get("final_score") is not None else g["percent"]
	return out


def _person_only():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Agents cannot create, close or move goals. Propose a task under a goal instead."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def create(title: str, goal_type: str = "Open", space: str | None = None, area: str | None = None, project: str | None = None, target_date: str | None = None,
		cycle: str | None = None, serves: str | None = None, done_when: str | None = None, notes_md: str | None = None):
	"""Create a goal. A 12 Week Year goal needs a cycle; an Annual goal needs a target date. `serves` is the longer goal it
	serves; `project` is read as the goal that project became, for one set (set 6)."""
	_person_only()
	if goal_type not in TYPES:
		frappe.throw(_("Unknown goal type."))
	if goal_type == "12 Week Year":
		if not cycle:
			frappe.throw(_("Choose the cycle of this 12 Week Year goal."))
		c = permissions.get_doc_checked("Life Cycle", cycle, "write")
		space = c.space
	space = permissions.resolve_space(space, write=True)
	last = frappe.db.sql("select ifnull(max(sort_order), 0) from `tabLife Goal` where space=%s", space)[0][0]
	doc = frappe.get_doc({"doctype": "Life Goal", "space": space, "title": (title or "").strip(), "goal_type": goal_type, "area": area or None,
		"serves": serves or (project and goal_for_project(project, space)) or None, "done_when": done_when or None, "notes_md": notes_md or None,
		"target_date": target_date or None, "cycle": cycle if goal_type == "12 Week Year" else None, "sort_order": last + 1})
	doc.insert()
	return {"name": doc.name, "title": doc.title}


@frappe.whitelist(methods=["POST"])
def close(goal: str, outcome: str, result_note: str | None = None):
	"""Set the outcome of an Annual or Open goal, with an optional result note. 12 Week Year goals close with their cycle."""
	_person_only()
	doc = permissions.get_doc_checked("Life Goal", goal, "write")
	if doc.goal_type == "12 Week Year":
		frappe.throw(_("A 12 Week Year goal is closed with its cycle, through Close cycle."))
	if outcome not in OUTCOMES:
		frappe.throw(_("Unknown outcome."))
	doc.outcome = outcome
	if result_note is not None:
		doc.result_note = result_note
	doc.save()
	return {"name": doc.name, "outcome": doc.outcome, "closed_on": str(doc.closed_on) if doc.closed_on else None}


@frappe.whitelist(methods=["POST"])
def add_to_cycle(goal: str, cycle: str):
	"""Move an Annual or Open goal into the active or a planned 12 Week Year. It becomes a 12 Week Year goal in that cycle
	and keeps its tasks. carried_from is left empty: it records carrying between cycles."""
	_person_only()
	doc = permissions.get_doc_checked("Life Goal", goal, "write")
	if doc.goal_type == "12 Week Year":
		frappe.throw(_("This goal is already in a 12 Week Year."))
	c = permissions.get_doc_checked("Life Cycle", cycle, "write")
	if c.space != doc.space:
		frappe.throw(_("The cycle is in another space."))
	if c.status not in ("Active", "Planned"):
		frappe.throw(_("Choose the current or a planned cycle."))
	doc.goal_type, doc.cycle, doc.target_date = "12 Week Year", c.name, doc.target_date
	doc.sort_order = frappe.db.sql("select ifnull(max(sort_order), 0) from `tabLife Goal` where cycle=%s", c.name)[0][0] + 1
	doc.save()
	return {"name": doc.name, "cycle": c.name}


@frappe.whitelist(methods=["GET"])
def picker(space: str | None = None):
	"""Every goal in progress, grouped by type, for the goal picker on a task."""
	space = permissions.resolve_space(space)
	rows = frappe.db.sql("""select g.name, g.title, g.goal_type, g.area, c.title as cycle_title from `tabLife Goal` g
		left join `tabLife Cycle` c on c.name = g.cycle where g.space=%s and g.outcome = 'In Progress'
		and (g.goal_type != '12 Week Year' or c.status in ('Active', 'Planned'))
		order by field(g.goal_type, '12 Week Year', 'Annual', 'Open'), g.sort_order, g.title""", space, as_dict=True)
	return rows


@frappe.whitelist(methods=["GET"])
def cycles(space: str | None = None):
	"""The current and planned 12 Week Years of a space: where a new 12 Week Year goal can go, or an open goal can move."""
	space = permissions.resolve_space(space)
	return frappe.get_all("Life Cycle", filters={"space": space, "status": ("in", ["Active", "Planned"])}, fields=["name", "title", "status"], order_by="start_date")


# ---- open-ended goals: what a project page did before set 6 ----

STATUS = {"Active": ("In Progress", 0), "On Hold": ("In Progress", 1), "Done": ("Achieved", 0), "Dropped": ("Dropped", 0)}


def status_of(doc):
	"""An open-ended goal's state in a project's words: Active, On Hold, Done, Dropped or Someday."""
	if doc.get("is_someday"):
		return "Someday"
	outcome = doc.get("outcome") or "In Progress"
	if outcome == "In Progress":
		return "On Hold" if doc.get("on_hold") else "Active"
	return "Done" if outcome == "Achieved" else "Dropped"


@frappe.whitelist(methods=["GET"])
def get(goal: str):
	"""A goal page: the goal with what it serves and what serves it, its open and finished tasks, the counts of what is
	filed under it (notes, captures, chats), the number of records that would move to the Archive when it is completed,
	and the count on each tab. Reads only what the user may read."""
	from lifeos import archive

	doc = permissions.get_doc_checked("Life Goal", goal)
	space = doc.space
	g = doc.as_dict()
	for k in ("target_date", "closed_on", "completed_on", "last_activity_on", "archived_on", "someday_on", "someday_review_on", "creation", "modified"):
		g[k] = str(g[k])[:19] if g.get(k) else None
	g.pop("actions", None)
	g["status"] = status_of(doc)
	g["area_name"] = frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None
	g["serves_title"] = frappe.db.get_value("Life Goal", doc.serves, "title") if doc.serves else None
	g["cycle_title"] = frappe.db.get_value("Life Cycle", doc.cycle, "title") if doc.cycle else None
	served_by = frappe.get_all("Life Goal", filters={"serves": doc.name, "space": space}, fields=["name", "title", "goal_type", "outcome", "is_someday", "on_hold"],
		order_by="creation asc", limit=100)
	served_by.sort(key=lambda r: TYPES.index(r.goal_type) if r.goal_type in TYPES else 9)
	for r in served_by:
		r["status"] = status_of(r)
	inc = 1 if doc.is_archived else 0
	return {"goal": g, "space": space, "served_by": served_by, "record_count": archive.goal_record_count(doc.name),
		"tabs": tab_counts_of(space, doc.name, inc)}


def tab_counts_of(space, goal, include_archived=0):
	"""The count on each tab of the goal page: what that tab's list shows when it opens, asked of the same list method the
	main screen uses, so the number equals that screen filtered by this goal."""
	from lifeos.api import chats, library, links, sources
	from lifeos.api import tasks as task_api

	inc = include_archived
	return {
		"tasks": task_api.list(space=space, goal=goal, status="open_doing", include_archived=inc, page_length=1)["total"],
		"notes": library.list(space=space, goal=goal, include_archived=inc, page_length=1, collection="all")["total"],
		"captures": sources.list(space=space, goal=goal, include_archived=inc, page_length=1)["total"],
		"chats": chats.list(space=space, goal=goal, include_archived=inc, page_length=1)["total"],
		"links": len(links.backlinks("Life Goal", goal)),
	}


@frappe.whitelist(methods=["GET"])
def completion_info(goal: str):
	"""How many records will move to the Archive when an open-ended goal is completed. Shown in the confirm dialog."""
	from lifeos import archive

	doc = permissions.get_doc_checked("Life Goal", goal)
	return {"goal": doc.name, "title": doc.title, "records": archive.goal_record_count(doc.name)}


@frappe.whitelist(methods=["POST"])
def set_status(goal: str, status: str):
	"""Change an open-ended goal's state as a project's was changed: Active, On Hold, Done or Dropped. Done or Dropped
	archives it at once with every record filed under it; Active or On Hold brings an archived one back."""
	from lifeos import archive

	_person_only()
	doc = permissions.get_doc_checked("Life Goal", goal, "write")
	if status not in STATUS:
		frappe.throw(_("Unknown status."))
	if doc.goal_type == "12 Week Year":
		frappe.throw(_("A 12 Week Year goal is closed with its cycle, through Close cycle."))
	outcome, on_hold = STATUS[status]
	records = archive.goal_record_count(doc.name) if outcome != "In Progress" else 0
	if outcome == "In Progress" and doc.is_archived:
		archive.restore_goal(doc)
		doc.reload()
	doc.outcome, doc.on_hold = outcome, on_hold
	doc.save()
	return {"goal": doc.name, "status": status_of(doc), "is_archived": frappe.db.get_value("Life Goal", doc.name, "is_archived"),
		"archived_records": records}


@frappe.whitelist(methods=["POST"])
def update(goal: str, values: str | dict):
	"""Change the fields of a goal a person edits: title, area, serves, done_when, notes_md, target_date, result_note."""
	_person_only()
	doc = permissions.get_doc_checked("Life Goal", goal, "write")
	values = frappe.parse_json(values) or {}
	allowed = {"title", "area", "serves", "done_when", "notes_md", "target_date", "result_note"}
	for k, v in values.items():
		if k not in allowed:
			frappe.throw(_("Field {0} cannot be changed here.").format(k))
		doc.set(k, v or None)
	doc.save()
	return get(doc.name)


@frappe.whitelist(methods=["GET"])
def for_project(project: str):
	"""The goal a project became (set 6), for old links to a project. People only: projects are hidden from agents."""
	_person_only()
	doc = permissions.get_doc_checked("Life Project", project)
	if not doc.migrated_to:
		frappe.throw(_("This project has not been moved to a goal yet."), frappe.DoesNotExistError)
	return {"project": doc.name, "goal": doc.migrated_to}
