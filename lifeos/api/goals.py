"""Goals of every horizon: Long term, Year, 12 weeks (in a cycle, with weekly actions) and Month. One list across
horizons with the share of their tasks that is done."""
import builtins

import frappe
from frappe import _
from frappe.utils import getdate

from lifeos import journal as rules
from lifeos import permissions, readings
from lifeos.life.doctype.life_goal.life_goal import HORIZONS, derive_horizon, planning_in_quarters
from lifeos.areas import off as areas_off
from lifeos.areas import off_clause
from lifeos.api.utils import area_filter, names_map, parse, page, std_clause, std_order, summarise, tab_counts
from lifeos.api.utils import order_by as sort_order

TYPES = ("12 weeks", "Month", "Year", "Long term")  # the order lists show them in
CLOSED = ("Partly Achieved", "Not Achieved", "Carried", "Dropped")
OUTCOMES = ("In Progress", "Achieved", *CLOSED)
# the state tabs of the Goals screen
# Someday goals (UX fixes, set 5) leave In progress and have their own tab; their outcome is not changed
TABS = {"in_progress": "g.outcome = 'In Progress' and g.is_someday = 0 and g.is_archived = 0", "achieved": "g.outcome = 'Achieved'",
	"closed": "g.outcome in ('Partly Achieved', 'Not Achieved', 'Carried', 'Dropped')", "someday": "g.is_someday = 1", "all": "g.is_someday = 0"}
COUNTED = ("Open", "Doing", "Waiting", "Done")
SORTS = {"title": "g.title", "target_date": "g.target_date is null, g.target_date", "completion": "_completion",
	"creation": "g.creation", "serves": "s.title is null, s.title, g.serves, g.horizon, g.title"}


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


def where_clause(space, state=None, horizon=None, area=None, cycle=None, target_from=None, target_to=None, serves=None):
	where, values = [], {}
	if state:
		if state not in TABS:
			frappe.throw(_("Unknown state."))
		where.append(TABS[state])
	if horizon:
		where.append("g.horizon = %(horizon)s")
		values["horizon"] = horizon
	if area:
		where.append(area_filter(space, area, "g.area", values))
	off = off_clause(space, "g.area", values)  # goals of an area that is off are hidden (issue 11)
	if off:
		where.append(off[len(" and "):])
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
def list(space: str | None = None, state: str | None = "in_progress", horizon: str | None = None, area: str | None = None,
		cycle: str | None = None, target_from: str | None = None, target_to: str | None = None, sort: str | None = None, dir: str | None = None, start: int = 0, page_length: int = 50,
		filters: str | builtins.list | None = None, order_by: str | None = None, summary: str | dict | None = None, serves: str | None = None):
	"""Goals of a space of every type. state: in_progress (default), achieved, closed (Partly Achieved, Not Achieved,
	Carried, Dropped) or all. Each row has tasks_done and tasks_counted, and `score` (the 12 Week Year percentage; None
	for other types). `tabs` counts each state under the other filters; `summary_line` has goals in progress and tasks
	done out of counted across the goals the filters match. `serves` keeps the goals that serve one goal. Each row also has on_hold, done_when, serves and its title, and last_activity_on."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = where_clause(space, state, horizon, area, cycle, target_from, target_to, serves)
	extra, values = std_clause("Life Goal", filters, "g", values)
	where += extra
	t_where, t_values = where_clause(space, None, horizon, area, cycle, target_from, target_to, serves)
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
		order = sort_order(sort, dir, {k: v for k, v in SORTS.items() if k != "completion"}, "field(g.horizon, '12 weeks', 'Month', 'Year', 'Long term'), g.target_date is null, g.target_date, g.creation")
	# nosemgrep: frappe-sql-format-injection -- WHERE from where_clause (TABS map) and std_clause (meta-checked columns); ORDER from SORTS or std_order
	rows = frappe.db.sql(f"""select g.name, g.title, g.horizon, g.area, g.serves, g.cycle, g.target_date, g.outcome, g.closed_on,
		g.result_note, g.final_score, g.on_hold, g.done_when, g.last_activity_on, g.is_archived, g.is_someday,
		g.measure_kind, g.measure, g.unit, g.start_value, g.target_value, g.current_value, g.current_on,
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
	scores = _scores([r for r in rows if r.horizon == "12 weeks" and r.cycle])
	for r in rows:
		r["target_date"] = str(r.target_date) if r.target_date else None
		r["closed_on"] = str(r.closed_on) if r.closed_on else None
		r["last_activity_on"] = str(r.last_activity_on) if r.last_activity_on else None
		r["score"] = scores.get(r.name) if r.horizon == "12 weeks" else None
		r["current_on"] = str(r.current_on) if r.current_on else None
		r["progress"] = readings.summary(r)
		r["reached"] = readings.reached(r)
	return {"goals": rows, "total": len(names), "tabs": tabs,
		"summary_line": {"in_progress": tabs["in_progress"], "tasks_done": total_done, "tasks_counted": total_counted}}


SHOWS = {
	"cycle": "g.outcome = 'In Progress' and g.is_someday = 0 and g.is_archived = 0 and c.status = 'Active'",
	"open": TABS["in_progress"],
	"finished": "g.outcome != 'In Progress' and g.is_someday = 0",
}


def _next_actions(space, names):
	"""{goal: (task row, open count)}: the first open or doing task of each goal (planned time, then due date, then age) and how
	many there are, counted as the goal page's Open tasks tab counts them."""
	if not names:
		return {}
	hidden = set(areas_off(space))
	rows = frappe.get_all("Life Task", filters={"goal": ("in", names), "status": ("in", ("Open", "Doing")), "is_archived": 0},
		fields=["name", "title", "goal", "scheduled_at", "due_date", "area"], limit=5000)
	rows = [r for r in rows if not r.area or r.area not in hidden]
	rows.sort(key=lambda r: (r.scheduled_at is None, r.scheduled_at or 0, r.due_date is None, r.due_date or 0))
	out = {}
	for r in rows:
		first, n = out.get(r.goal, (None, 0))
		out[r.goal] = (first or r, n + 1)
	return out


def _done_when_line(g):
	"""The finish line in words: a number as "84 → 78 kg", otherwise the goal's own Done when text."""
	if g.measure_kind == "Number" and g.target_value is not None:
		unit = f" {g.unit}" if g.unit else ""
		return f"{readings.num(g.start_value)} → {readings.num(g.target_value)}{unit}"
	return g.done_when or None


@frappe.whitelist(methods=["GET"])
def by_area(space: str | None = None, show: str = "cycle", sort: str = "order"):
	"""Goals → By area: one section for each area that is on, with its parts as sub-groups. `show` is cycle (goals in the active
	12 Week Year), open (every goal in progress) or finished. `sort` is order (the owner's order, set by reorder) or score. Each
	goal has its Done when, progress, the cycle's current week and score, the next action, the open task count and what it
	serves. Areas that are off have no section and are listed in `off` for the chips."""
	space = permissions.resolve_space(space)
	if show not in SHOWS:
		frappe.throw(_("Unknown filter."))
	if sort not in ("order", "score"):
		frappe.throw(_("Unknown sort."))
	values = {"space": space}
	off = off_clause(space, "g.area", values)
	# nosemgrep: frappe-sql-format-injection -- SHOWS is a constant map, off is off_clause's fixed SQL; values are parameters
	rows = frappe.db.sql(f"""select g.name, g.title, g.horizon, g.area, g.serves, g.cycle, g.target_date, g.outcome, g.on_hold, g.done_when,
		g.measure_kind, g.measure, g.unit, g.start_value, g.target_value, g.current_value, g.current_on, g.sort_order,
		c.title as cycle_title, c.start_date as cycle_start, s.title as serves_title
		from `tabLife Goal` g left join `tabLife Cycle` c on c.name = g.cycle left join `tabLife Goal` s on s.name = g.serves
		where g.space = %(space)s and {SHOWS[show]} {off} order by g.sort_order, g.creation""", values, as_dict=True)
	names = [r.name for r in rows]
	counts = task_counts(names)
	nxt = _next_actions(space, names)
	scores = _scores([r for r in rows if r.horizon == "12 weeks" and r.cycle])
	week_of = {c: rules.current_week(frappe.get_doc("Life Cycle", c)) for c in {r.cycle for r in rows if r.cycle}}
	for r in rows:
		r["tasks_done"], r["tasks_counted"] = counts.get(r.name, (0, 0))
		is_cycle = r.horizon == "12 weeks" and r.cycle
		r["score"] = scores.get(r.name) if is_cycle else None
		r["week"] = week_of.get(r.cycle) if is_cycle else None
		r["progress"] = readings.summary(r)
		r["done_when_line"] = _done_when_line(r)
		task, n = nxt.get(r.name, (None, 0))
		r["open_tasks"] = n
		r["next_action"] = {"name": task.name, "title": task.title, "scheduled_at": str(task.scheduled_at) if task.scheduled_at else None,
			"due_date": str(task.due_date) if task.due_date else None} if task else None
		r["target_date"] = str(r.target_date) if r.target_date else None
		r["current_on"] = str(r.current_on) if r.current_on else None
		r["cycle_start"] = str(r.cycle_start) if r.cycle_start else None
	if sort == "score":
		rows.sort(key=lambda r: -(r.score if r.score is not None else (r.progress.get("percent") or 0)))
	tree = frappe.get_all("Life Area", filters={"space": space, "is_archived": 0}, fields=["name", "area_name", "parent_area", "is_life_area", "is_on", "colour", "sort_order"],
		order_by="sort_order asc, area_name asc", limit=5000)
	top = [a for a in tree if not a.parent_area]
	hidden = set(areas_off(space))
	by_area_name = {}
	for r in rows:
		by_area_name.setdefault(r.area or "", []).append(r)
	sections = []
	for a in top:
		if a.name in hidden:
			continue
		parts = [p for p in tree if p.parent_area == a.name and p.name not in hidden]
		groups = [{"area": None, "goals": by_area_name.get(a.name, [])}]
		groups += [{"area": {"name": p.name, "area_name": p.area_name}, "goals": by_area_name.get(p.name, [])} for p in parts]
		groups = [g for g in groups if g["goals"]]
		n = sum(len(g["goals"]) for g in groups)
		sections.append({"area": a.name, "area_name": a.area_name, "colour": a.colour, "count": n,
			"parts": [{"name": p.name, "area_name": p.area_name} for p in parts], "groups": groups if n else []})
	known = {a.name for a in tree}
	loose = [r for r in rows if not r.area or r.area not in known]
	return {"space": space, "show": show, "sort": sort, "total": len(rows), "sections": sections,
		"no_area": loose, "areas_on": len([s for s in sections if s["area"]]),
		"off": [{"name": a.name, "area_name": a.area_name} for a in top if a.name in hidden]}


@frappe.whitelist(methods=["POST"])
def reorder(goals: str | builtins.list):
	"""Save the owner's order of goals (Goals → By area, drag): the first name gets the lowest sort order. People only; each goal
	must be one the user can write."""
	_person_only()
	names = parse(goals, [])
	if not isinstance(names, builtins.list) or not names or len(names) > 200:
		frappe.throw(_("Give the goals in their new order."))
	docs = [permissions.get_doc_checked("Life Goal", n) for n in names]
	slots = sorted(d.sort_order or 0 for d in docs)
	if len(set(slots)) < len(slots):
		slots = builtins.list(range(min(slots), min(slots) + len(slots)))
	for d, slot in zip(docs, slots):
		if (d.sort_order or 0) != slot:
			d.check_permission("write")
			d.db_set("sort_order", slot, update_modified=False)
	return {"ok": True}


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


MEASURE_FIELDS = ("measure_kind", "measure", "unit", "start_value", "target_value")


def measure_values(measure_kind=None, done_when=None, measure=None, unit=None, start_value=None, target_value=None):
	"""The key-result fields of a new or edited goal (set 7). A finish line given without a kind is a milestone."""
	if measure_kind and measure_kind not in ("Milestone", "Number"):
		frappe.throw(_("Choose a finish line or a number."))
	if not measure_kind and (done_when or "").strip():
		measure_kind = "Milestone"
	out = {"measure_kind": measure_kind or None}
	if measure_kind == "Number":
		out.update({"measure": (measure or "").strip() or None, "unit": (unit or "").strip() or None,
			"start_value": _float(start_value), "target_value": _float(target_value)})
	return out


def _float(v):
	if v is None or v == "":
		return None
	try:
		return float(v)
	except (TypeError, ValueError):
		frappe.throw(_("{0} is not a number.").format(v))


@frappe.whitelist(methods=["GET"])
def suggest_horizon(space: str | None = None, target_date: str | None = None, cycle: str | None = None):
	"""The horizon the goal form sets from the target date (the owner may change it), and whether 12-week goals follow the
	calendar quarter (Rhythms) instead of a cycle."""
	space = permissions.resolve_space(space)
	return {"horizon": derive_horizon(target_date, cycle, space), "quarters": planning_in_quarters()}


@frappe.whitelist(methods=["POST"])
def create(title: str, horizon: str | None = None, space: str | None = None, area: str | None = None, target_date: str | None = None,
		cycle: str | None = None, serves: str | None = None, done_when: str | None = None, notes_md: str | None = None,
		measure_kind: str | None = None, measure: str | None = None, unit: str | None = None, start_value: float | str | None = None,
		target_value: float | str | None = None):
	"""Create a goal. Its horizon (Long term, Year, 12 weeks, Month) is worked out from the target date and the cycle when
	not given. A 12-week goal needs a cycle (or, planning in quarters, a date in the quarter); a Year or Month goal needs a
	target date. `serves` is the longer goal it
	serves; Key results (set 7): `measure_kind`
	Milestone needs `done_when`; Number needs `measure`, `start_value` and `target_value` (with `unit`)."""
	_person_only()
	if cycle:
		c = permissions.get_doc_checked("Life Cycle", cycle, "write")
		space = c.space
	space = permissions.resolve_space(space, write=True)
	horizon = horizon or derive_horizon(target_date, cycle, space)
	if horizon not in HORIZONS:
		frappe.throw(_("Unknown horizon."))
	measure_fields = measure_values(measure_kind, done_when, measure, unit, start_value, target_value)
	readings.require_finish_line({"done_when": done_when, **measure_fields})
	last = frappe.db.sql("select ifnull(max(sort_order), 0) from `tabLife Goal` where space=%s", space)[0][0]
	doc = frappe.get_doc({"doctype": "Life Goal", "space": space, "title": (title or "").strip(), "horizon": horizon, "area": area or None,
		"serves": serves or None, "done_when": done_when or None, "notes_md": notes_md or None,
		"target_date": target_date or None, "cycle": cycle if horizon == "12 weeks" else None, "sort_order": last + 1,
		**measure_fields})
	doc.insert()
	return {"name": doc.name, "title": doc.title}


@frappe.whitelist(methods=["POST"])
def close(goal: str, outcome: str, result_note: str | None = None):
	"""Set the outcome of an Annual or Open goal, with an optional result note. 12 Week Year goals close with their cycle."""
	_person_only()
	doc = permissions.get_doc_checked("Life Goal", goal, "write")
	if doc.horizon == "12 weeks":
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
	if doc.horizon == "12 weeks":
		frappe.throw(_("This goal is already in a 12 Week Year."))
	c = permissions.get_doc_checked("Life Cycle", cycle, "write")
	if c.space != doc.space:
		frappe.throw(_("The cycle is in another space."))
	if c.status not in ("Active", "Planned"):
		frappe.throw(_("Choose the current or a planned cycle."))
	doc.horizon, doc.cycle, doc.target_date = "12 weeks", c.name, doc.target_date
	doc.sort_order = frappe.db.sql("select ifnull(max(sort_order), 0) from `tabLife Goal` where cycle=%s", c.name)[0][0] + 1
	doc.save()
	return {"name": doc.name, "cycle": c.name}


@frappe.whitelist(methods=["GET"])
def picker(space: str | None = None):
	"""Every goal in progress, grouped by type, for the goal picker on a task."""
	space = permissions.resolve_space(space)
	values = {"space": space}
	off = off_clause(space, "g.area", values)  # not goals of an area that is off (issue 11)
	# nosemgrep: frappe-sql-format-injection -- `off` is off_clause's fixed SQL; values are parameters
	rows = frappe.db.sql(f"""select g.name, g.title, g.horizon, g.area, c.title as cycle_title from `tabLife Goal` g
		left join `tabLife Cycle` c on c.name = g.cycle where g.space=%(space)s and g.outcome = 'In Progress'
		and (g.horizon != '12 weeks' or c.status in ('Active', 'Planned')){off}
		order by field(g.horizon, '12 weeks', 'Month', 'Year', 'Long term'), g.sort_order, g.title""", values, as_dict=True)
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
	served_by = frappe.get_all("Life Goal", filters={"serves": doc.name, "space": space}, fields=["name", "title", "horizon", "outcome", "is_someday", "on_hold",
		"cycle", "measure_kind", "measure", "unit", "start_value", "target_value", "current_value", "current_on"], order_by="creation asc", limit=100)
	served_by.sort(key=lambda r: TYPES.index(r.horizon) if r.horizon in TYPES else 9)
	cycles = names_map("Life Cycle", [r.cycle for r in served_by], "title")
	for r in served_by:
		r["status"] = status_of(r)
		r["cycle_title"] = cycles.get(r.cycle) if r.cycle else None
	with_progress(served_by)
	serves = None
	if doc.serves:  # always in the goal's own space (check_serves)
		serves = frappe.db.get_value("Life Goal", doc.serves, ["name", "title", "horizon", "cycle", "measure_kind", "measure", "unit", "start_value",
			"target_value", "current_value", "current_on"], as_dict=True)
		with_progress([serves])
	g["progress"] = with_progress([frappe._dict(doc.as_dict())])[0]["progress"]
	g["has_finish_line"] = readings.has_finish_line(doc)
	cycle = frappe.db.get_value("Life Cycle", doc.cycle, ["name", "title", "status"], as_dict=True) if doc.cycle else None
	confirmed, suggested = readings.for_goal(doc.name) if doc.measure_kind == "Number" else ([], [])
	inc = 1 if doc.is_archived else 0
	return {"goal": g, "cycle": cycle, "space": space, "served_by": served_by, "serves": serves, "readings": confirmed, "suggested": suggested,
		"record_count": archive.goal_record_count(doc.name), "tabs": tab_counts_of(space, doc.name, inc)}


def with_progress(rows):
	"""Add `progress` to goal rows: a number goal's result against its target, a 12 Week Year goal's score, else the share
	of its tasks done (readings.summary). Rows need name, horizon, cycle and the measure fields."""
	if not rows:
		return rows
	with_tasks(rows)
	scores = _scores([r for r in rows if r.get("horizon") == "12 weeks" and r.get("cycle")])
	for r in rows:
		score = r.get("score") if r.get("score") is not None else scores.get(r["name"])
		r["progress"] = readings.summary({**r, "score": score if r.get("horizon") == "12 weeks" else None})
	return rows


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
	if doc.horizon == "12 weeks":
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


def _apply_values(doc, values, allowed):
	"""Set the fields a person edits on a goal. Changing the key result applies the rule of a new goal."""
	for k, v in values.items():
		if k not in allowed:
			frappe.throw(_("Field {0} cannot be changed here.").format(k))
		if k == "horizon" and v not in ("Long term", "Year", "Month", "12 weeks"):
			frappe.throw(_("Choose Long term, Year, Month or 12 weeks."))
		doc.set(k, _float(v) if k in ("start_value", "target_value") else (v if v == 0 else v or None))
	if "measure_kind" not in values and values.get("done_when") and not doc.measure_kind:
		doc.measure_kind = "Milestone"


@frappe.whitelist(methods=["POST"])
def update(goal: str, values: str | dict):
	"""Change the fields of a goal a person edits: title, area, serves, done_when, notes_md, target_date, horizon (Long term, Year or Month; a goal joins 12 weeks with
	add_to_cycle), result_note, and its
	key result (measure_kind, measure, unit, start_value, target_value). Changing the key result applies the rule of a new goal."""
	_person_only()
	doc = permissions.get_doc_checked("Life Goal", goal, "write")
	values = frappe.parse_json(values) or {}
	if not isinstance(values, dict):
		frappe.throw(_("values must be an object of fields."))
	if values.get("horizon") == "12 weeks":
		frappe.throw(_("A goal joins a 12 Week Year with Add to a 12 Week Year."))
	_apply_values(doc, values, {"title", "area", "serves", "done_when", "notes_md", "target_date", "result_note", "horizon", *MEASURE_FIELDS})
	doc.save()
	return get(doc.name)


EDIT_FIELDS = {"title", "area", "serves", "done_when", "target_date", "horizon", "cycle", *MEASURE_FIELDS}


@frappe.whitelist(methods=["POST"])
def edit(goal: str, values: str | dict, actions: str | builtins.list | None = None):
	"""The Edit form of a goal: title, area, type (`horizon`), cycle, target date, done_when and serves, and for a 12 Week Year goal its
	weekly actions as a list of {name?, title, per_week, retired?} in the order shown. An action in the list is renamed, retired
	(status Dropped, its ticks kept) or brought back; a new one is added; one not in the list is left as it is. The change is
	written to the goal's timeline."""
	_person_only()
	doc = permissions.get_doc_checked("Life Goal", goal, "write")
	values = frappe.parse_json(values) or {}
	if not isinstance(values, dict):
		frappe.throw(_("values must be an object of fields."))
	before = {k: doc.get(k) for k in values}
	if values.get("cycle"):
		c = permissions.get_doc_checked("Life Cycle", values["cycle"], "write")
		if c.space != doc.space:
			frappe.throw(_("The cycle is in another space."))
	if values.get("horizon") and values["horizon"] != "12 weeks":
		values["cycle"] = None
	_apply_values(doc, values, EDIT_FIELDS)
	actions = parse(actions)
	if actions is not None:
		_set_actions(doc, actions)
	doc.save()
	changed = [k for k in values if before.get(k) != doc.get(k)]
	if "title" in changed:
		doc.add_comment("Info", _("Edited: renamed from {0} to {1}.").format(before["title"], doc.title))
	other = [doc.meta.get_label(k) for k in changed if k != "title"]
	if other or actions is not None:
		doc.add_comment("Info", _("Edited: {0}.").format(", ".join([*other, *([_("weekly actions")] if actions is not None else [])])))
	return get(doc.name)


def _set_actions(doc, actions):
	if doc.horizon != "12 weeks" and actions:
		frappe.throw(_("Weekly actions belong to 12-week goals."))
	rows = {a.name: a for a in doc.actions}
	ordered, seen = [], set()
	for a in actions:
		title = (a.get("title") or "").strip()
		if not title:
			continue
		per_week = max(1, min(7, int(a.get("per_week") or 1)))
		row = rows.get(a.get("name"))
		if row:
			row.title, row.per_week = title, per_week
			if a.get("retired"):
				row.status = "Dropped"
			elif row.status == "Dropped":
				row.status = "Open"
			seen.add(row.name)
		else:
			row = {"title": title, "per_week": per_week, "status": "Dropped" if a.get("retired") else "Open"}
		ordered.append(row)
	ordered += [r for n, r in rows.items() if n not in seen]  # an action the form did not list stays, after the ones it did
	doc.set("actions", ordered)
	for i, row in enumerate(doc.actions, 1):  # a row that was already there keeps its old idx unless it is set
		row.idx = i


# ---- key results (set 7): suggestions, habits, readings ----

@frappe.whitelist(methods=["POST"])
def suggest_measure(title: str, notes: str | None = None, space: str | None = None, goal: str | None = None, horizon: str | None = None):
	"""Propose how a goal will be known to be done: Milestone (a finish line) or Number (measure, unit, target), from its
	title and notes (and, with `goal`, its area, weekly actions and open tasks). `examples` are two finish lines for its type, for when no one answers. The assistant answers within the spend cap; without a key, simple rules do. `habit` is set when the
	title reads as a frequency ("daily", "3 times a week"): it is a habit, not a goal."""
	_person_only()
	space = permissions.resolve_space(space, write=True)
	area = actions = tasks = None
	if goal:  # an existing goal: its area, weekly actions and open tasks tell the skill what it is about
		doc = permissions.get_doc_checked("Life Goal", goal, "write")
		space, horizon = doc.space, horizon or doc.horizon
		area = frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None
		actions = [a.title for a in doc.actions if a.status != "Dropped"][:20]
		tasks = frappe.get_all("Life Task", filters={"goal": doc.name, "status": ("in", ["Open", "Doing", "Waiting"])}, pluck="title", limit=20)
	return readings.suggest_measure((title or "").strip()[:300], notes, space, area=area, actions=actions, tasks=tasks, horizon=horizon)


@frappe.whitelist(methods=["POST"])
def make_habit(title: str, space: str | None = None, area: str | None = None, days_per_week: int | None = None):
	"""Make a frequency a habit instead of a goal: the habit is created (or reused by title) and added to the current month's
	plan. No goal is created."""
	from lifeos import journal

	_person_only()
	space = permissions.resolve_space(space, write=True)
	title = (title or "").strip()[:140]
	if not title:
		frappe.throw(_("Name the habit."))
	guess = readings.habit_of(title)
	days = int(days_per_week or (guess and guess["days_per_week"]) or 7)
	name = frappe.db.get_value("Life Habit", {"space": space, "title": title}) or frappe.get_doc(
		{"doctype": "Life Habit", "space": space, "title": title, "area": area or None}).insert().name
	now = getdate()
	plan = journal.habits_month(space, now.year, now.month)
	rows = [{"habit": h["habit"], "days_per_week": h["days_per_week"]} for h in plan["habits"] if not h["removed"] and h["habit"] != name]
	journal.set_month_habits(space, now.year, now.month, [*rows, {"habit": name, "days_per_week": max(1, min(7, days))}])
	return {"habit": name, "title": title, "days_per_week": days, "month": f"{now.year}-{now.month:02d}"}


@frappe.whitelist(methods=["GET"])
def goal_readings(goal: str):
	"""A number goal's Confirmed readings (oldest first, for the chart) and its Suggested ones waiting (newest first)."""
	doc = permissions.get_doc_checked("Life Goal", goal)
	confirmed, suggested = readings.for_goal(doc.name)
	return {"goal": doc.name, "confirmed": confirmed, "suggested": suggested}


@frappe.whitelist(methods=["POST"])
def add_reading(goal: str, value: float | str, date: str | None = None, note: str | None = None):
	"""A person records a number goal's value by hand. It is Confirmed at once and becomes the current value when latest."""
	_person_only()
	doc = permissions.get_doc_checked("Life Goal", goal, "write")
	if doc.measure_kind != "Number":
		frappe.throw(_("Readings belong to a goal measured by a number."))
	r = frappe.get_doc({"doctype": "Life Goal Reading", "space": doc.space, "goal": doc.name, "date": date or frappe.utils.today(),
		"value": _float(value), "status": "Confirmed", "suggested_by": "Owner", "excerpt": (note or "").strip()[:1000] or None}).insert()
	return _goal_now(doc.name, r.name)


@frappe.whitelist(methods=["POST"])
def confirm_reading(reading: str, value: float | str | None = None, date: str | None = None):
	"""Confirm a Suggested reading, optionally with the value or date edited first. People only."""
	_person_only()
	r = readings.confirm(reading, _float(value), date)
	return _goal_now(r.goal, r.name)


@frappe.whitelist(methods=["POST"])
def reject_reading(reading: str):
	"""Reject a Suggested reading. It stays as Rejected, so the same suggestion is not stored again."""
	_person_only()
	r = permissions.get_doc_checked("Life Goal Reading", reading, "write")
	r.status = "Rejected"
	r.save()
	return _goal_now(r.goal, r.name)


def _goal_now(goal, reading):
	g = frappe.db.get_value("Life Goal", goal, ["name", "title", "horizon", "measure_kind", "measure", "unit", "start_value", "target_value",
		"current_value", "current_on"], as_dict=True)
	return {"reading": reading, "goal": goal, "current_value": g.current_value if g.current_on else None, "current_on": str(g.current_on) if g.current_on else None,
		"progress": readings.summary(g), "reached": readings.reached(g)}
