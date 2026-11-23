"""Cycle rules: 12 Week Year scores and ticks, cycles and Month goals. API methods in lifeos.api.goals call these."""
import calendar
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.query_builder.functions import Max, Sum
from frappe.utils import add_days, getdate, today

OPEN_TASK_STATUSES = ("Open", "Doing", "Waiting")

WEEKS = 12


# ---------- 12 Week Year ----------

def week_of(cycle, on=None) -> int:
	"""Week number of a date inside a cycle. 0 before it starts, 13 after it ends."""
	on = getdate(on or today())
	start = getdate(cycle.start_date)
	if on < start:
		return 0
	return min((on - start).days // 7 + 1, WEEKS + 1)


def current_week(cycle) -> int:
	return min(max(week_of(cycle), 1), WEEKS)


def week_dates(cycle, week):
	start = add_days(getdate(cycle.start_date), (int(week) - 1) * 7)
	return start, add_days(start, 6)


def _actions(cycle_name):
	a, g = frappe.qb.DocType("Life Goal Action"), frappe.qb.DocType("Life Goal")
	return (frappe.qb.from_(a).join(g).on(g.name == a.parent)
		.select(a.name, a.parent.as_("goal"), a.title, a.per_week, a.status, a.done_on, a.idx)
		.where((g.cycle == cycle_name) & (a.parenttype == "Life Goal"))
		.orderby(g.sort_order).orderby(g.creation).orderby(a.idx).run(as_dict=True))  # system: the actions of one cycle the caller already read


def _ticks(cycle_name) -> dict:
	out = {}
	log = frappe.qb.DocType("Life Action Log")
	for action, week, n in (frappe.qb.from_(log).select(log.action_id, log.week, Sum(log["count"]))
			.where(log.cycle == cycle_name).groupby(log.action_id, log.week).run()):  # system: the ticks of one cycle the caller already read
		out.setdefault(action, {})[int(week)] = int(n)
	return out


def planned_in_week(cycle, action, week) -> int:
	"""Ticks an action is expected to get in a week. Dropped: none. Done early: none after the week it was finished."""
	if action.status == "Dropped":
		return 0
	if action.status == "Done":
		done_week = week_of(cycle, action.done_on) if action.done_on else WEEKS
		done_week = min(max(done_week, 1), WEEKS)
		return int(action.per_week or 1) if week <= done_week else 0
	return int(action.per_week or 1)


def _score(done, planned):
	return round(100.0 * done / planned, 1) if planned else 0.0


def week_score(cycle_name, week, actions=None, ticks=None) -> dict:
	cycle = frappe.get_cached_doc("Life Cycle", cycle_name) if isinstance(cycle_name, str) else cycle_name
	actions = _actions(cycle.name) if actions is None else actions
	ticks = _ticks(cycle.name) if ticks is None else ticks
	week = int(week)
	done = planned = 0
	for a in actions:
		p = planned_in_week(cycle, a, week)
		planned += p
		done += min(ticks.get(a.name, {}).get(week, 0), p)
	return {"cycle": cycle.name, "week": week, "done": done, "planned": planned, "percent": _score(done, planned)}


def cycle_average(cycle, actions, ticks, upto=None):
	upto = upto or current_week(cycle)
	scores = [week_score(cycle, w, actions, ticks)["percent"] for w in range(1, upto + 1)]
	return round(sum(scores) / len(scores), 1) if scores else 0.0


def goal_percent(cycle, goal_actions, ticks, upto=None):
	upto = upto or current_week(cycle)
	done = planned = 0
	for a in goal_actions:
		for w in range(1, upto + 1):
			p = planned_in_week(cycle, a, w)
			planned += p
			done += min(ticks.get(a.name, {}).get(w, 0), p)
	return _score(done, planned)


def grid(cycle_name) -> dict:
	cycle = frappe.get_doc("Life Cycle", cycle_name)
	actions, ticks = _actions(cycle.name), _ticks(cycle.name)
	cur = current_week(cycle)
	upto = WEEKS if cycle.status == "Closed" or week_of(cycle) > WEEKS else cur
	by_goal = {}
	for a in actions:
		by_goal.setdefault(a.goal, []).append(a)
	goals = []
	for g in frappe.get_all(
		"Life Goal", filters={"cycle": cycle.name},
		fields=["name", "title", "area", "serves", "outcome", "result_note", "carried_from", "final_score", "sort_order",
			"measure_kind", "done_when", "measure", "unit", "start_value", "target_value", "current_value", "current_on"],
		order_by="sort_order asc, creation asc",
	):
		acts = by_goal.get(g.name, [])
		g["area_name"] = frappe.db.get_value("Life Area", g.area, "area_name") if g.area else None
		g["percent"] = goal_percent(cycle, acts, ticks, upto)
		g["actions"] = [{
			"name": a.name, "title": a.title, "per_week": int(a.per_week or 1), "status": a.status,
			"done_week": (min(max(week_of(cycle, a.done_on), 1), WEEKS) if a.status == "Done" and a.done_on else None),
			"ticks": {str(w): n for w, n in ticks.get(a.name, {}).items()},
		} for a in acts]
		goals.append(g)
	# the longer goal each cycle goal serves, with its progress, shown beside it on the 12 Weeks tab (set 7)
	from lifeos.goals import readings

	served = {r.name: r for r in frappe.get_all("Life Goal", filters={"name": ("in", [g.serves for g in goals if g.serves] or ["-"])},
		fields=["name", "title", "horizon", "measure_kind", "measure", "unit", "start_value", "target_value", "current_value", "current_on"])}
	for g in goals:
		s = served.get(g.serves)
		g["serves_title"] = s.title if s else None
		g["serves_progress"] = readings.summary(s) if s and s.measure_kind == "Number" else None
		g["result"] = readings.summary({**g, "horizon": "12 weeks", "score": g["percent"]})
	weeks = [week_score(cycle, w, actions, ticks) for w in range(1, WEEKS + 1)]
	started = week_of(cycle) >= 1
	return {
		"cycle": {"name": cycle.name, "title": cycle.title, "start_date": str(cycle.start_date), "end_date": str(cycle.end_date),
			"status": cycle.status, "final_score": cycle.final_score, "space": cycle.space},
		"current_week": cur if started and cycle.status != "Closed" and week_of(cycle) <= WEEKS else None,
		"weeks_left": max(WEEKS - cur, 0) if started else WEEKS,
		"past_end": getdate(today()) > getdate(cycle.end_date),
		"average": cycle.final_score if cycle.status == "Closed" else (cycle_average(cycle, actions, ticks, upto) if started else 0.0),
		"target": frappe.db.get_single_value("Life Settings", "score_target") or 85,
		"weeks": weeks, "goals": goals,
	}


def find_action(action_id):
	row = frappe.db.get_value("Life Goal Action", action_id, ["name", "parent", "per_week", "status", "title"], as_dict=True)
	if not row:
		frappe.throw(_("Action not found."), frappe.DoesNotExistError, title=_("Action not found"))
	goal = frappe.get_doc("Life Goal", row.parent)
	return row, goal


def set_tick(action_id, week, count, inbox_item=None) -> dict:
	"""Set the number of ticks an action has in a week. Each tick is kept as a dated Life Action Log row."""
	row, goal = find_action(action_id)
	goal.check_permission("write")
	cycle = frappe.get_doc("Life Cycle", goal.cycle)
	if cycle.status == "Closed":
		frappe.throw(_("A closed cycle is read-only."), title=_("Cycle already closed"))
	week = int(week)
	if not 1 <= week <= WEEKS:
		frappe.throw(_("Week must be 1 to 12."), title=_("Week out of range"))
	count = max(0, min(int(count or 0), int(row.per_week or 1)))
	start, end = week_dates(cycle, week)
	for name in frappe.get_all("Life Action Log", filters={"action_id": action_id, "week": week}, pluck="name"):
		frappe.delete_doc("Life Action Log", name, ignore_permissions=True, force=True)
	if count:
		now = getdate(today())
		on = now if start <= now <= end else (end if now > end else start)
		frappe.get_doc({
			"doctype": "Life Action Log", "space": goal.space, "goal": goal.name, "action_id": action_id,
			"cycle": cycle.name, "week": week, "date": on, "count": count, "inbox_item": inbox_item,
		}).insert(ignore_permissions=True)
	_update_tick_summary(action_id)
	return week_score(cycle, week)


def _update_tick_summary(action_id):
	log = frappe.qb.DocType("Life Action Log")
	total = frappe.qb.from_(log).select(Sum(log.count)).where(log.action_id == action_id).run()[0][0] or 0
	frappe.db.set_value("Life Goal Action", action_id, "ticks", str(int(total)), update_modified=False)


def set_action_status(action_id, status) -> dict:
	"""Mark an action Done once and for all, Dropped, or Open again."""
	if status not in ("Open", "Done", "Dropped"):
		frappe.throw(_("Unknown status."), title=_("Unknown status"))
	row, goal = find_action(action_id)
	goal.check_permission("write")
	for a in goal.actions:
		if a.name == action_id:
			a.status = status
			a.done_on = today() if status == "Done" else None
	goal.save(ignore_permissions=True)
	cycle = frappe.get_doc("Life Cycle", goal.cycle)
	if status == "Done" and 1 <= week_of(cycle) <= WEEKS:
		wk = week_of(cycle)
		if not frappe.db.exists("Life Action Log", {"action_id": action_id, "week": wk}):
			set_tick(action_id, wk, int(row.per_week or 1))
	return {"goal": goal.name, "action": action_id, "status": status}


def close_cycle(cycle_name, outcomes=None) -> dict:
	"""Store an outcome and note per goal, the final score, and lock the cycle."""
	cycle = frappe.get_doc("Life Cycle", cycle_name)
	cycle.check_permission("write")
	if cycle.status == "Closed":
		frappe.throw(_("This cycle is already closed."), title=_("Cycle already closed"))
	if cycle.status != "Active":
		frappe.throw(_("Only an active cycle can be closed."), title=_("Cycle is not active"))
	if getdate(today()) <= getdate(cycle.end_date) and not frappe.flags.lifeos_allow_early_close:
		frappe.throw(_("A cycle can be closed after its end date."), title=_("Cycle has not ended"))
	outcomes = {o["goal"]: o for o in (outcomes or [])}
	actions, ticks = _actions(cycle.name), _ticks(cycle.name)
	by_goal = {}
	for a in actions:
		by_goal.setdefault(a.goal, []).append(a)
	allowed = ("Achieved", "Partly Achieved", "Not Achieved", "Carried", "Dropped")
	for name in frappe.get_all("Life Goal", filters={"cycle": cycle.name}, pluck="name"):
		goal = frappe.get_doc("Life Goal", name)
		o = outcomes.get(name) or {}
		outcome = o.get("outcome") or ("Not Achieved" if goal.outcome == "In Progress" else goal.outcome)
		if outcome not in allowed:
			frappe.throw(_("Outcome for {0} must be one of {1}.").format(goal.title, ", ".join(allowed)), title=_("Outcome not allowed"))
		goal.outcome = outcome
		goal.result_note = o.get("result_note") or goal.result_note
		goal.final_score = goal_percent(cycle, by_goal.get(name, []), ticks, WEEKS)
		goal.save(ignore_permissions=True)
	cycle.final_score = cycle_average(cycle, actions, ticks, WEEKS)
	cycle.status = "Closed"
	cycle.closed_on = today()
	cycle.save(ignore_permissions=True)
	return {"cycle": cycle.name, "final_score": cycle.final_score}


def next_monday(after) -> date:
	d = getdate(after) + timedelta(days=1)
	while d.weekday() != 0:
		d += timedelta(days=1)
	return d


def cycle_title(start) -> str:
	end = add_days(getdate(start), 83)
	return f"{getdate(start).strftime('%b')} to {end.strftime('%b %Y')}"


def plan_next_cycle(cycle_name, goals=None, title=None) -> dict:
	"""Create the next cycle, starting the Monday after this one ends, and carry the chosen goals with their open actions."""
	cycle = frappe.get_doc("Life Cycle", cycle_name)
	cycle.check_permission("write")
	start = next_monday(cycle.end_date)
	existing = frappe.db.get_value("Life Cycle", {"space": cycle.space, "start_date": start})
	if existing:
		new = frappe.get_doc("Life Cycle", existing)
		if new.status == "Closed":
			frappe.throw(_("The next cycle is already closed."), title=_("Next cycle already closed"))
	else:
		new = frappe.get_doc({"doctype": "Life Cycle", "space": cycle.space, "title": title or cycle_title(start),
			"start_date": start, "status": "Planned"}).insert(ignore_permissions=True)
	carried = []
	for name in goals or []:
		old = frappe.get_doc("Life Goal", name)
		if old.cycle != cycle.name:
			frappe.throw(_("{0} is not a goal of this cycle.").format(old.title), title=_("Goal is not in this cycle"))
		if frappe.db.exists("Life Goal", {"cycle": new.name, "carried_from": old.name}):
			continue
		copy = frappe.get_doc({
			"doctype": "Life Goal", "space": old.space, "cycle": new.name, "title": old.title, "area": old.area,
			"serves": old.serves, "sort_order": old.sort_order, "carried_from": old.name, "outcome": "In Progress",
			"done_when": old.done_when, "measure_kind": old.measure_kind, "measure": old.measure, "unit": old.unit,
			"start_value": old.start_value, "target_value": old.target_value,
			"actions": [{"title": a.title, "per_week": a.per_week, "status": "Open"} for a in old.actions if a.status == "Open"],
		}).insert(ignore_permissions=True)
		if old.measure_kind == "Number" and old.current_on:
			# the carried goal starts from where the old one got to
			frappe.get_doc({"doctype": "Life Goal Reading", "space": copy.space, "goal": copy.name, "date": old.current_on or today(),
				"value": old.current_value, "status": "Confirmed", "suggested_by": "Owner",
				"excerpt": "Carried from the previous cycle"}).insert(ignore_permissions=True)
		old.outcome = "Carried"
		old.flags.allow_closed = True
		old.save(ignore_permissions=True)
		carried.append(copy.name)
	return {"cycle": new.name, "title": new.title, "start_date": str(new.start_date), "carried": carried}


def goal_history(goal_name) -> list:
	"""Every cycle a goal appeared in, oldest first, following carried_from in both directions."""
	first = goal_name
	seen = {first}
	while True:
		prev = frappe.db.get_value("Life Goal", first, "carried_from")
		if not prev or prev in seen or not frappe.db.exists("Life Goal", prev):
			break
		first = prev
		seen.add(prev)
	chain, cur = [], first
	while cur:
		chain.append(cur)
		cur = frappe.db.get_value("Life Goal", {"carried_from": cur}, "name", order_by="creation asc")
		if cur in chain:
			break
	out = []
	for name in chain:
		g = frappe.db.get_value("Life Goal", name, ["name", "title", "cycle", "outcome", "result_note", "final_score"], as_dict=True)
		cycle = frappe.get_doc("Life Cycle", g.cycle)
		if cycle.status == "Closed":
			score = g.final_score or 0
		else:
			acts = [a for a in _actions(cycle.name) if a.goal == name]
			score = goal_percent(cycle, acts, _ticks(cycle.name)) if week_of(cycle) >= 1 else 0
		out.append({**g, "cycle_title": cycle.title, "cycle_status": cycle.status, "start_date": str(cycle.start_date), "score": score})
	return out


# ---------- Month goals: goals with the Month horizon ----------


def month_bounds(year, month):
	first = date(int(year), int(month), 1)
	return first, first.replace(day=calendar.monthrange(int(year), int(month))[1])


def next_month(year, month):
	return (int(year) + 1, 1) if int(month) == 12 else (int(year), int(month) + 1)


STATUS_OF = {"In Progress": "Open", "Achieved": "Done", "Dropped": "Dropped", "Carried": "Carried"}
OUTCOME_OF = {"Open": "In Progress", "Done": "Achieved", "Dropped": "Dropped", "Carried": "Carried"}


def month_goals(space, year, month) -> list[dict]:
	"""The month's goals: goals with horizon Month and a target date in that month, in the owner's priority order."""
	first, last = month_bounds(year, month)
	rows = frappe.get_all("Life Goal", filters={"space": space, "horizon": "Month", "is_archived": 0, "target_date": ("between", [first, last])},
		fields=["name", "title", "area", "outcome", "carried_from", "sort_order"], order_by="sort_order asc, creation asc")
	tasks = {}
	if rows:
		for goal, task in frappe.get_list("Life Task", filters={"goal": ("in", [r.name for r in rows]), "status": ("in", ("Open", "Doing", "Waiting"))},
				fields=["goal", "name"], order_by="creation desc", as_list=True, limit=5000):
			tasks[goal] = task
	from lifeos.api.goals import task_counts

	counts = task_counts([r.name for r in rows])
	from_month = {}
	if any(r.carried_from for r in rows):
		from_month = dict(frappe.get_all("Life Goal", filters={"name": ("in", [r.carried_from for r in rows if r.carried_from])},
			fields=["name", "target_date"], as_list=True))
	return [{"row": r.name, "title": r.title, "status": STATUS_OF.get(r.outcome, "Done"), "area": r.area, "task": tasks.get(r.name),
		"carried_from": r.carried_from, "carried_from_month": from_month[r.carried_from].month if from_month.get(r.carried_from) else None,
		"tasks_done": counts.get(r.name, (0, 0))[0], "tasks_counted": counts.get(r.name, (0, 0))[1]} for r in rows]


def last_sort_order(**filters):
	"""The highest sort_order among the goals matching the filters (a value, or an operator and a value); 0 when there are none."""
	goal = frappe.qb.DocType("Life Goal")
	query = frappe.qb.from_(goal).select(Max(goal.sort_order))
	for field, value in filters.items():
		query = query.where(goal[field].between(*value[1]) if isinstance(value, tuple) else goal[field] == value)
	return query.run()[0][0] or 0


def move_open_tasks(old, new):
	"""A carried goal's open tasks follow it to the goal it was carried into."""
	frappe.db.set_value("Life Task", {"goal": old, "status": ("in", OPEN_TASK_STATUSES)}, "goal", new)


def add_month_goal(space, year, month, title, area=None, carried_from=None, serves=None, ignore_permissions=False, done_when=None):
	"""Add a Month goal dated the last day of the month, at the end of the month's order."""
	first, last = month_bounds(year, month)
	top = last_sort_order(space=space, horizon="Month", target_date=("between", (first, last)))
	doc = frappe.get_doc({"doctype": "Life Goal", "space": space, "title": title, "horizon": "Month", "target_date": last, "area": area or None,
		"sort_order": top + 1, "carried_from": carried_from, "serves": serves or None, "done_when": (done_when or "").strip() or None})
	doc.insert(ignore_permissions=ignore_permissions)
	return doc


def carry_month_goal(goal_name) -> dict:
	"""Copy an open month goal into next month, mark the old one Carried and move its open tasks to the new one."""
	old = frappe.get_doc("Life Goal", goal_name)
	old.check_permission("write")
	if old.horizon != "Month" or old.outcome != "In Progress":
		frappe.throw(_("Only an open month goal can be carried forward."), title=_("Month goal is not open"))
	ny, nm = next_month(old.target_date.year, old.target_date.month)
	new = add_month_goal(old.space, ny, nm, old.title, old.area, carried_from=old.name, serves=old.serves)
	old.outcome = "Carried"
	old.save()
	move_open_tasks(old.name, new.name)
	return {"row": new.name, "year": ny, "month": nm}


def carry_task(task_name) -> dict:
	"""Copy an open task, mark the old one Carried and set carried_from."""
	old = frappe.get_doc("Life Task", task_name)
	old.check_permission("write")
	if old.status in ("Done", "Dropped", "Carried"):
		frappe.throw(_("Only an open task can be carried forward."), title=_("Task is not open"))
	new = frappe.copy_doc(old)
	new.update({"status": "Open", "carried_from": old.name, "completed_on": None,
		"due_date": None, "is_archived": 0, "archived_on": None, "archive_reason": ""})
	new.insert(ignore_permissions=True)
	old.status = "Carried"
	old.save(ignore_permissions=True)
	return {"task": new.name}
