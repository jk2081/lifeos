"""The Goals tab's rows, the coming week and its capacity (set 8): each goal's mark and progress, the free slots, goal work
planned against free working hours, and the glance calendar of next week's working days."""
from datetime import timedelta

import frappe
from frappe.utils import cint, get_datetime, getdate

from lifeos.goals import cycles, readings
from lifeos.tasks import weekplan

DAY = "%a"


def percent(gp, g):
	"""How far a goal is, 0 to 100: its ticks this cycle, else its result, else its tasks done."""
	m = mark_of(gp, g)
	return m["percent"] if m["percent"] is not None else 0


def _cycle_data(gp):
	if not hasattr(gp, "_cyc"):
		cyc = gp.cycle()
		gp._cyc = (frappe.get_doc("Life Cycle", cyc.name), cycles._actions(cyc.name), cycles._ticks(cyc.name)) if cyc else (None, [], {})
	return gp._cyc


def mark_of(gp, g):
	"""No ticks (none this week though some were planned), Slipping (behind the target or the calendar), or On track."""
	cycle, actions, ticks = _cycle_data(gp)
	target = cint(frappe.db.get_single_value("Life Settings", "score_target")) or 85
	mine = [a for a in actions if a.goal == g.name]
	if cycle and mine and g.cycle == cycle.name:
		week = cycles.current_week(cycle)
		planned = sum(cycles.planned_in_week(cycle, a, week) for a in mine)
		done = sum(min(ticks.get(a.name, {}).get(week, 0), cycles.planned_in_week(cycle, a, week)) for a in mine)
		pct = cycles.goal_percent(cycle, mine, ticks)
		if planned and not done:
			return {"mark": "No ticks", "percent": pct}
		return {"mark": "On track" if pct >= target else "Slipping", "percent": pct}
	prog = progress_of(g)
	if prog["percent"] is None:
		return {"mark": "No ticks" if cycle and g.cycle == cycle.name else None, "percent": None}
	elapsed = 100.0 * max(cycles.current_week(cycle), 1) / cycles.WEEKS if cycle and g.cycle == cycle.name else 50.0
	return {"mark": "On track" if prog["percent"] >= elapsed - 10 else "Slipping", "percent": prog["percent"]}


def progress_of(g):
	"""Number goals: current of target; milestone goals: tasks done of total."""
	full = frappe.db.get_value("Life Goal", g.name, ["measure_kind", "measure", "unit", "start_value", "target_value", "current_value", "current_on",
		"done_when", "horizon"], as_dict=True)
	if full.measure_kind == "Number":
		s = readings.summary(full)
		cur = f"{s['current']:,g}" if s.get("current") is not None else "—"
		return {"kind": "number", "percent": s["percent"], "label": f"{cur} of {full.target_value:,g}"}
	n = frappe.db.count("Life Task", {"goal": g.name, "status": ("not in", ["Dropped", "Someday"])})
	done = frappe.db.count("Life Task", {"goal": g.name, "status": "Done"})
	return {"kind": "tasks", "percent": round(100.0 * done / n, 1) if n else None, "label": f"{done} of {n} tasks" if n else "No tasks yet"}


def taken_by_plans(gp, but=None):
	out = []
	for name, p in gp.st["plans"].items():
		if name == but or p.get("skip") or not p.get("slot"):
			continue
		s = get_datetime(p["slot"])
		out.append((s, s + timedelta(minutes=cint(p.get("minutes")) or weekplan.DEFAULT_MINUTES)))
	return out


def free_left(gp, now=None, extra_taken=()):
	"""Free working time in the coming week, less goal work already scheduled and what the review's plans take."""
	a, b = weekplan.window(now)
	free = weekplan.free_time(gp.space, now)
	sched = [t for t in weekplan.scheduled(gp.space, a, b) if t.goal]
	taken = [(get_datetime(t.scheduled_at), get_datetime(t.scheduled_at) + timedelta(minutes=cint(t.duration_min) or weekplan.DEFAULT_MINUTES))
		for t in sched if t.name not in {p.get("task") for p in gp.st["plans"].values()}]
	return weekplan.subtract(free, [*taken, *extra_taken])


def slots(gp, goal, minutes, n=3, now=None):
	"""The first free slots where this goal's next action fits, on different days where possible."""
	free = free_left(gp, now, extra_taken=taken_by_plans(gp, but=goal))
	out, days = [], set()
	for s, e in free:
		start = weekplan.first_slot([(s, e)], minutes)
		if start and start.date() not in days:
			out.append(str(start)[:16])
			days.add(start.date())
		if len(out) >= n:
			break
	return out


def capacity(gp, now=None):
	"""Goal work planned (the review's plans with a time, plus goal work already scheduled outside them) against free hours."""
	a, b = weekplan.window(now)
	free = weekplan.minutes_in(weekplan.free_time(gp.space, now))
	plans = {p.get("task") for p in gp.st["plans"].values()}
	sched = sum(cint(t.duration_min) or weekplan.DEFAULT_MINUTES for t in weekplan.scheduled(gp.space, a, b) if t.goal and t.name not in plans)
	planned = sched + sum(cint(p.get("minutes")) or weekplan.DEFAULT_MINUTES for n, p in gp.st["plans"].items()
		if n in [g.name for g in gp.goals()] and not p.get("skip") and p.get("slot") and (p.get("next_action") or "").strip())
	return {"planned_minutes": planned, "free_minutes": free, "over": planned > free}


def glance(gp, now=None):
	"""Next week's working days, with events and other scheduled tasks in grey and goal work in blue."""
	a, b = weekplan.window(now)
	h = weekplan.hours()
	days, d = [], a.date()
	while d < b.date():
		if weekplan.DAYS[d.weekday()] in h["days"]:
			days.append({"date": str(d), "label": d.strftime(DAY), "blocks": []})
		d += timedelta(days=1)
	by = {x["date"]: x for x in days}
	titles = {g.name: g.title for g in gp.goals()}

	def put(start, minutes, title, kind, goal=None, ref=None):
		day = by.get(str(getdate(start)))
		if day:
			day["blocks"].append({"start": str(start)[:16], "minutes": int(minutes), "title": title, "kind": kind, "goal": goal, "ref": ref})

	from lifeos.calendar import calendar_data

	for e in calendar_data.events_between(gp.space, a.date(), b.date()):
		if not e.get("all_day"):
			s, en = get_datetime(e["start"]), get_datetime(e["end"])
			put(s, max((en - s).total_seconds() // 60, 15), e["title"], "event", ref="event:" + e["name"])
	plans = {p.get("task"): n for n, p in gp.st["plans"].items() if p.get("task")}
	for t in weekplan.scheduled(gp.space, a, b):
		if t.name in plans:
			continue
		put(t.scheduled_at, cint(t.duration_min) or weekplan.DEFAULT_MINUTES, t.title, "goal" if t.goal else "event", t.goal, "task:" + t.name)
	for name, p in gp.st["plans"].items():
		if name in titles and not p.get("skip") and p.get("slot"):
			put(get_datetime(p["slot"]), cint(p.get("minutes")) or weekplan.DEFAULT_MINUTES, p.get("next_action") or titles[name], "goal", name)
	for x in days:
		x["blocks"].sort(key=lambda b: b["start"])
	return {"days": days, "start": "%02d:%02d" % h["start"], "end": "%02d:%02d" % h["end"]}
