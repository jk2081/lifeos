"""Journal rules: 12 Week Year scores, cycles, month plans and habits. API methods in lifeos.api.journal call these."""
import calendar
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos.life.doctype.life_month_plan.life_month_plan import plan_name

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
	return frappe.db.sql(
		"""select a.name, a.parent as goal, a.title, a.per_week, a.status, a.done_on, a.idx
		from `tabLife Goal Action` a join `tabLife Goal` g on g.name = a.parent
		where g.cycle = %s and a.parenttype = 'Life Goal' order by g.sort_order, g.creation, a.idx""",
		cycle_name, as_dict=True,
	)


def _ticks(cycle_name) -> dict:
	out = {}
	for r in frappe.db.sql(
		"select action_id, week, sum(`count`) as n from `tabLife Action Log` where cycle=%s group by action_id, week", cycle_name
	):
		out.setdefault(r[0], {})[int(r[1])] = int(r[2])
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
		fields=["name", "title", "area", "project", "outcome", "result_note", "carried_from", "final_score", "sort_order"],
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
		frappe.throw(_("Action not found."), frappe.DoesNotExistError)
	goal = frappe.get_doc("Life Goal", row.parent)
	return row, goal


def set_tick(action_id, week, count, inbox_item=None) -> dict:
	"""Set the number of ticks an action has in a week. Each tick is kept as a dated Life Action Log row."""
	row, goal = find_action(action_id)
	goal.check_permission("write")
	cycle = frappe.get_doc("Life Cycle", goal.cycle)
	if cycle.status == "Closed":
		frappe.throw(_("A closed cycle is read-only."))
	week = int(week)
	if not 1 <= week <= WEEKS:
		frappe.throw(_("Week must be 1 to 12."))
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
	total = frappe.db.sql("select ifnull(sum(`count`), 0) from `tabLife Action Log` where action_id=%s", action_id)[0][0]
	frappe.db.set_value("Life Goal Action", action_id, "ticks", str(int(total)), update_modified=False)


def set_action_status(action_id, status) -> dict:
	"""Mark an action Done once and for all, Dropped, or Open again."""
	if status not in ("Open", "Done", "Dropped"):
		frappe.throw(_("Unknown status."))
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
		frappe.throw(_("This cycle is already closed."))
	if cycle.status != "Active":
		frappe.throw(_("Only an active cycle can be closed."))
	if getdate(today()) <= getdate(cycle.end_date) and not frappe.flags.lifeos_allow_early_close:
		frappe.throw(_("A cycle can be closed after its end date."))
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
			frappe.throw(_("Outcome for {0} must be one of {1}.").format(goal.title, ", ".join(allowed)))
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
			frappe.throw(_("The next cycle is already closed."))
	else:
		new = frappe.get_doc({"doctype": "Life Cycle", "space": cycle.space, "title": title or cycle_title(start),
			"start_date": start, "status": "Planned"}).insert(ignore_permissions=True)
	carried = []
	for name in goals or []:
		old = frappe.get_doc("Life Goal", name)
		if old.cycle != cycle.name:
			frappe.throw(_("{0} is not a goal of this cycle.").format(old.title))
		if frappe.db.exists("Life Goal", {"cycle": new.name, "carried_from": old.name}):
			continue
		copy = frappe.get_doc({
			"doctype": "Life Goal", "space": old.space, "cycle": new.name, "title": old.title, "area": old.area,
			"project": old.project, "sort_order": old.sort_order, "carried_from": old.name, "outcome": "In Progress",
			"actions": [{"title": a.title, "per_week": a.per_week, "status": "Open"} for a in old.actions if a.status == "Open"],
		}).insert(ignore_permissions=True)
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


# ---------- month plans and habits ----------

def month_bounds(year, month):
	first = date(int(year), int(month), 1)
	return first, first.replace(day=calendar.monthrange(int(year), int(month))[1])


def next_month(year, month):
	return (int(year) + 1, 1) if int(month) == 12 else (int(year), int(month) + 1)


def get_month_plan(space, year, month, create=False):
	name = plan_name(space, year, month)
	if frappe.db.exists("Life Month Plan", name):
		return frappe.get_doc("Life Month Plan", name)
	if not create:
		return None
	return frappe.get_doc({"doctype": "Life Month Plan", "space": space, "year": int(year), "month": int(month)}).insert(ignore_permissions=True)


def habit_stats(row, first, last, done_dates, upto=None) -> dict:
	"""Score one habit for one month. Only days inside its tracked period, and not in the future, can be missed."""
	upto = getdate(upto or today())
	start = max(first, getdate(row.tracked_from)) if row.tracked_from else first
	end = min(last, getdate(row.tracked_until)) if row.tracked_until else last
	counted_end = min(end, upto)
	tracked_days = (counted_end - start).days + 1 if counted_end >= start else 0
	done = sum(1 for d in done_dates if start <= d <= end)
	per_week = min(7, max(1, int(row.days_per_week or 7)))
	target = tracked_days if per_week >= 7 else int(round(tracked_days * per_week / 7.0))
	if tracked_days and not target:
		target = 1
	percent = min(100, round(100.0 * done / target)) if target else 0
	return {"tracked_from": str(start), "tracked_until": str(end), "tracked_days": tracked_days, "done": done,
		"target": target, "percent": percent, "days_per_week": per_week}


def habits_month(space, year, month) -> dict:
	first, last = month_bounds(year, month)
	plan = get_month_plan(space, year, month)
	out = {"year": int(year), "month": int(month), "plan": plan.name if plan else None, "days_in_month": last.day,
		"today": today(), "habits": []}
	if not plan:
		return out
	rows = sorted(plan.habits, key=lambda r: (r.sort_order or 0, r.idx))
	ids = [r.habit for r in rows]
	logs = {}
	if ids:
		for h, d in frappe.db.sql(
			"select habit, date from `tabLife Habit Log` where habit in %s and date between %s and %s and done=1", (ids, first, last)
		):
			logs.setdefault(h, set()).add(getdate(d))
	titles = dict(frappe.get_all("Life Habit", filters={"name": ("in", ids or [""])}, fields=["name", "title"], as_list=True))
	for r in rows:
		done_dates = logs.get(r.habit, set())
		stats = habit_stats(r, first, last, done_dates)
		out["habits"].append({"habit": r.habit, "title": titles.get(r.habit, r.habit), "row": r.name, "sort_order": r.sort_order,
			"removed": bool(r.tracked_until and getdate(r.tracked_until) < last),
			"done_days": sorted(d.day for d in done_dates), **stats})
	return out


def toggle_habit(habit, on, done=None) -> dict:
	h = frappe.get_doc("Life Habit", habit)
	h.check_permission("write")
	on = getdate(on or today())
	existing = frappe.db.get_value("Life Habit Log", {"habit": habit, "date": on}, ["name", "done"], as_dict=True)
	if done is None:
		done = not (existing and existing.done)
	done = bool(int(done)) if not isinstance(done, bool) else done
	if done and on > getdate(today()):
		frappe.throw(_("A habit cannot be ticked for a day that has not come yet."))
	if existing and not done:
		frappe.delete_doc("Life Habit Log", existing.name, ignore_permissions=True, force=True)
	elif not existing and done:
		frappe.get_doc({"doctype": "Life Habit Log", "space": h.space, "habit": habit, "date": on, "done": 1}).insert(ignore_permissions=True)
	return {"habit": habit, "date": str(on), "done": done}


def set_month_habits(space, year, month, habits) -> dict:
	"""Replace the habit list of one month. `habits` is a list of {habit, days_per_week}, in order.

	A habit dropped mid-month keeps its row with `tracked_until` set, so its earlier days still count.
	"""
	plan = get_month_plan(space, year, month, create=True)
	plan.check_permission("write")
	first, last = month_bounds(year, month)
	now = getdate(today())
	in_month = first <= now <= last
	wanted = {h["habit"]: h for h in habits}
	order = {h["habit"]: i + 1 for i, h in enumerate(habits)}
	keep = []
	for row in plan.habits:
		if row.habit in wanted:
			row.days_per_week = wanted[row.habit].get("days_per_week") or row.days_per_week
			row.sort_order = order[row.habit]
			if row.tracked_until:  # added back
				row.tracked_until = None
			keep.append(row)
		elif in_month and getdate(row.tracked_from or first) < now and not row.tracked_until:
			row.tracked_until = add_days(now, -1)
			row.sort_order = 100 + (row.sort_order or 0)
			keep.append(row)
		elif row.tracked_until:
			keep.append(row)
		# otherwise the habit is dropped from the month outright
	have = {r.habit for r in keep}
	plan.set("habits", keep)
	for h in habits:
		if h["habit"] not in have:
			plan.append("habits", {"habit": h["habit"], "days_per_week": h.get("days_per_week") or 7, "sort_order": order[h["habit"]],
				"tracked_from": now if in_month else first})
	plan.save(ignore_permissions=True)
	return habits_month(space, year, month)


def habits_year(space, year) -> dict:
	"""Each habit's percentage for every month of the year in which it was tracked."""
	year = int(year)
	out = {}
	for month in range(1, 13):
		data = habits_month(space, year, month)
		for h in data["habits"]:
			if h["tracked_days"]:
				out.setdefault(h["habit"], {"habit": h["habit"], "title": h["title"], "months": {}})["months"][str(month)] = {
					"percent": h["percent"], "done": h["done"], "target": h["target"]}
	return {"year": year, "habits": list(out.values())}


def carry_month_goal(plan_name_, row_name) -> dict:
	"""Copy an open month goal into next month's plan and mark the old one Carried."""
	plan = frappe.get_doc("Life Month Plan", plan_name_)
	plan.check_permission("write")
	row = next((r for r in plan.goals if r.name == row_name), None)
	if not row:
		frappe.throw(_("Goal not found in this plan."), frappe.DoesNotExistError)
	if row.status != "Open":
		frappe.throw(_("Only an open goal can be carried forward."))
	ny, nm = next_month(plan.year, plan.month)
	target = get_month_plan(plan.space, ny, nm, create=True)
	new = target.append("goals", {"title": row.title, "priority": row.priority, "status": "Open", "area": row.area,
		"task": row.task, "carried_from": row.name})
	target.save(ignore_permissions=True)
	row.status = "Carried"
	plan.save(ignore_permissions=True)
	if row.task and frappe.db.exists("Life Task", row.task):
		frappe.db.set_value("Life Task", row.task, "month_plan", target.name, update_modified=False)
	return {"plan": target.name, "row": new.name, "year": ny, "month": nm}


def carry_task(task_name) -> dict:
	"""Copy an open task into next month's plan, mark the old one Carried and set carried_from."""
	old = frappe.get_doc("Life Task", task_name)
	old.check_permission("write")
	if old.status in ("Done", "Dropped", "Carried"):
		frappe.throw(_("Only an open task can be carried forward."))
	now = getdate(today())
	if old.month_plan:
		py, pm = frappe.db.get_value("Life Month Plan", old.month_plan, ["year", "month"])
		ny, nm = next_month(py, pm)
		if (ny, nm) < (now.year, now.month):
			ny, nm = next_month(now.year, now.month)
	else:
		ny, nm = next_month(now.year, now.month)
	target = get_month_plan(old.space, ny, nm, create=True)
	new = frappe.copy_doc(old)
	new.update({"status": "Open", "carried_from": old.name, "month_plan": target.name, "completed_on": None,
		"due_date": None, "is_archived": 0, "archived_on": None, "archive_reason": ""})
	new.insert(ignore_permissions=True)
	old.status = "Carried"
	old.save(ignore_permissions=True)
	moved = False
	if old.month_plan:
		src = frappe.get_doc("Life Month Plan", old.month_plan)
		for r in src.goals:
			if r.task == old.name and r.status == "Open":
				r.status = "Carried"
				target.append("goals", {"title": r.title, "priority": r.priority, "status": "Open", "area": r.area,
					"task": new.name, "carried_from": r.name})
				moved = True
		if moved:
			src.save(ignore_permissions=True)
	if not moved:
		target.append("goals", {"title": new.title, "priority": new.priority, "status": "Open", "area": new.area, "task": new.name})
	target.save(ignore_permissions=True)
	return {"task": new.name, "plan": target.name, "year": ny, "month": nm}
