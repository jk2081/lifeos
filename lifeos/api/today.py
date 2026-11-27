"""One call for the Today screen."""
import re
from datetime import timedelta

import frappe
from frappe.query_builder import Order
from frappe.query_builder import functions as fn
from frappe.utils import add_days, get_datetime, getdate, today

from lifeos.ai import client as ai_client
from lifeos.calendar import calendar_data
from lifeos.goals import cycles, rhythms
from lifeos.brain import asks, old_inbox
from lifeos import permissions
from lifeos.goals import habits as habit_rules
from lifeos.api import tasks as task_api
from lifeos.api import vault as vault_api
from lifeos.api.utils import area_criterion, count_by, descendants, in_area, lens_area, user_names

GROUP_ROWS = 7


OPEN = ("Open", "Doing")  # the waiting pile is never on Today (issue 118); one line says when some of it is past its check-by date


def task_lens(space, area):
	"""The lens as criteria on tasks: a list, empty for All of life."""
	return [area_criterion(space, area, frappe.qb.DocType("Life Task"), also_in="Life Task")] if area else []


def open_tasks(t, space, area):
	"""The criteria of open, unarchived tasks in the lens."""
	return [*task_lens(space, area), t.status.isin(OPEN) | ((t.status == "Waiting") & (t.is_top_three == 1)), t.is_archived == 0]  # a waiting task the owner starred stays


def planned_this_week(space, now, area=None, cycle=None, limit=None):
	"""Open tasks planned this week (due or scheduled Monday to Sunday) under a goal of the active cycle (the weekly review's goal
	work), in the lens. Each carries its goal as `goal` and `goal_title`."""
	if not cycle:
		return []
	t, g = frappe.qb.DocType("Life Task"), frappe.qb.DocType("Life Goal")
	start = add_days(now, -now.weekday())
	a, b, end = str(start), str(add_days(start, 6)), str(add_days(start, 7))
	where = [*open_tasks(t, space, area), t.goal.isin(frappe.qb.from_(g).select(g.name).where(g.cycle == cycle)),
		t.due_date.between(a, b) | ((t.scheduled_at >= a) & (t.scheduled_at < end))]
	return task_api.query(space, where, [(t.due_date.isnull(), Order.asc), (t.due_date, Order.asc), (t.scheduled_at, Order.asc), (t.creation, Order.asc)],
		0, limit or GROUP_MAX)


def goals_without_plan(space, now, area=None, cycle=None):
	"""How many active goals of the current cycle have no task planned this week."""
	if not cycle:
		return 0
	goals = frappe.get_list("Life Goal", filters={"space": space, "cycle": cycle, "outcome": "In Progress", "is_archived": 0, "on_hold": 0, "is_someday": 0},
		pluck="name")
	if area and goals:
		keep = in_area(space, area, "Life Goal", goals)
		goals = [g for g in goals if g in keep]
	planned = {t.goal for t in planned_this_week(space, now, area, cycle, limit=1000)}
	return len([g for g in goals if g not in planned])


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None, area: str | None = None, at: str | None = None):
	"""Tasks due or overdue, today's events, habits with today's state, items to review, the current week of the active cycle,
	the open loops count and expiring documents. `area` is the lens (UX fixes, set 6): the band, Next and the rail keep to
	the area and its sub-areas. Events and important dates have no area, so they always show. `banner` is the one rhythm
	that is due (lifeos/goals/rhythms.py); `at` moves its clock on a test site only."""
	space = permissions.resolve_space(space)
	area = lens_area(area)
	now = getdate(today())
	t = frappe.qb.DocType("Life Task")
	open_now = open_tasks(t, space, area)
	due = task_api.query(space, [*open_now, t.due_date <= now], (), 0, 30)
	# the screen shows two groups of at most GROUP_ROWS: due today first, then overdue (oldest first)
	due_today = task_api.query(space, [*open_now, t.due_date == now], (), 0, GROUP_ROWS)
	overdue_rows = task_api.query(space, [*open_now, t.due_date < now], (), 0, GROUP_ROWS)
	oldest = list_query_one("Life Task", fn.Min(t.due_date), [t.space == space, *open_now, t.due_date < now])
	# the numbers are counted with the filters their links lead to, not from the rows shown
	due_count = task_api.count(space, due="today,overdue", area=area)
	today_count = task_api.count(space, due="today", area=area)
	overdue = task_api.count(space, due="overdue", area=area)

	from lifeos.api import inbox as inbox_api

	inbox_lens = inbox_api.list(space=space, status='["To Review"]', area=area, page_length=5) if area else None
	review_filter = {"space": space, "status": "To Review", "is_archived": 0}
	if inbox_lens is not None:
		review_filter["name"] = ("in", [r.name for r in inbox_lens["items"]] or ["-"])
	if permissions.vault_hidden(space):  # an agent: no sensitive item, and no source of a Vault document
		review_filter.update({"is_sensitive": 0, "vault_document": ("is", "not set")})
	review_items = frappe.get_list("Life Inbox Item", filters=review_filter,
		fields=["name", "title", "source_type", "received_on", "owner", "claimed_by", "transcript_md", "summary_md"], order_by="received_on desc", limit=5)
	pending = {}
	if review_items:
		pending = proposal_counts([r.name for r in review_items])
	waiting = {}
	if review_items:
		waiting = proposal_counts([r.name for r in review_items], "Pending")
	users = user_names([r.claimed_by for r in review_items])
	for r in review_items:
		r["proposals"] = pending.get(r.name, 0)
		r["pending"] = waiting.get(r.name, 0)
		r["state"] = "Transcribed" if r.pop("transcript_md") else ("Summary ready" if r.pop("summary_md", None) else "Processed")
		r.pop("summary_md", None)
		r["processed_by"] = users.get(r.claimed_by)
		r["received_on"] = str(r.received_on)[:19]
	to_review = inbox_lens["total"] if inbox_lens is not None else frappe.db.count("Life Inbox Item", {"space": space, "status": "To Review", "is_archived": 0})
	p, i = frappe.qb.DocType("Life Proposal"), frappe.qb.DocType("Life Inbox Item")
	proposals_waiting = frappe.qb.from_(p).join(i).on(i.name == p.inbox_item).select(fn.Count("*")).where(
		(p.space == space) & (p.status == "Pending") & (i.status == "To Review") & (i.is_archived == 0)).run()[0][0]

	events = [e for e in calendar_data.events_between(space, now, add_days(now, 1))]
	events.sort(key=lambda e: e["start"])

	month = habit_rules.habits_month(space, now.year, now.month)
	habits = [{"habit": h["habit"], "title": h["title"], "done": now.day in h["done_days"]} for h in month["habits"] if not h["removed"]]

	cycle_out = None
	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "title", "start_date", "end_date"], as_dict=True)
	if cycle:
		week = cycles.week_of(cycle, now)
		if 1 <= week <= cycles.WEEKS:
			score = cycles.week_score(cycle.name, week)
			cycle_out = {"name": cycle.name, "title": cycle.title, "week": week, "weeks": cycles.WEEKS, "score": score["percent"],
				"done": score["done"], "planned": score["planned"]}
		else:
			cycle_out = {"name": cycle.name, "title": cycle.title, "week": None, "weeks": cycles.WEEKS, "ended": week > cycles.WEEKS,
				"start_date": str(cycle.start_date)}

	coming = []
	docs = calendar_data.expiring_documents(space, now)
	keep = in_area(space, area, "Life Vault Document", [d["name"] for d in docs])
	for d in (d for d in docs if d["name"] in keep):
		coming.append({"kind": "vault", **d})
	for d in sorted(calendar_data.important_dates_between(space, now, add_days(now, 14)), key=lambda x: x["date"]):
		coming.append({"kind": "important", "name": d["name"], "title": d["label"], "date": d["date"], "date_kind": d["kind"],
			"days": (getdate(d["date"]) - now).days})

	nxt = next_list(space, now, cycle_out, events, area)
	rail = rail_of(space, now, events, area)
	return {
		"no_plan": goals_without_plan(space, now, area, cycle.name if cycle else None), "next": nxt, "rail": rail, "days_left": 6 - now.weekday(),
		"date": str(now), "space": space,
		"cycle": cycle_out, "target": frappe.db.get_single_value("Life Settings", "score_target") or 85,
		"to_review": {"count": to_review, "proposals": proposals_waiting, "items": review_items},
		"tasks": {"items": due, "due": due_count, "overdue": overdue, "today": due_today, "today_count": today_count,
			"overdue_items": overdue_rows, "oldest_overdue": str(oldest) if oldest else None, "group_rows": GROUP_ROWS},
		"events": events, "habits": habits,
		"open_loops": task_api.open_loops_count(space), "area": area, "waiting_past": None if permissions.is_agent() else asks.past_check(space),
		"banner": None if permissions.is_agent() else rhythms.banner(space, at),
		"brain_off": None if permissions.is_agent() else ai_client.brain_off(),  # issue 102: why the AI service is not answering, until a call works again
		"auto_inbox": None if permissions.is_agent() else old_inbox.recent_auto(space, area),
		"coming_up": coming,
		"vault_soon": vault_api.expiry_counts(space)["soon"],
	}


# ---- UX fixes, set 5: the Next list and the right rail ----
NEXT_ROWS = 8  # rows shown before "N more"
GROUP_MAX = 30


def next_list(space, now, cycle, events, area=None):
	"""Tasks only, in a fixed order: the top three, Overdue, Today (events at their times and tasks due today), and tasks planned this
	week under a goal of the cycle. No goal and no lead action is a row. Someday items never appear."""
	from lifeos.review import counts

	task = frappe.qb.DocType("Life Task")
	open_now = open_tasks(task, space, area)
	# set 8: the week's top three come first, starred, until the next review is locked
	top = task_api.query(space, [*open_now, task.is_top_three == 1], [(task.scheduled_at, Order.asc), (task.creation, Order.asc)], 0, 3)
	for t in top:
		t.update({"why": "Top three", "type": "task", "lead": str(t.scheduled_at)[11:16] if t.get("scheduled_at") else ""})
	tops = {t.name for t in top}
	overdue = task_api.query(space, [*open_now, task.due_date < now], [(task.due_date, Order.asc), (task.creation, Order.asc)], 0, GROUP_MAX)
	for t in overdue:
		t["why"] = "Overdue"
		t["lead"] = f"{(now - getdate(t.due_date)).days} day{'s' if (now - getdate(t.due_date)).days != 1 else ''}"
	overdue = [t for t in overdue if t.name not in tops]
	due_today = [t for t in task_api.query(space, [*open_now, task.due_date == now], (), 0, GROUP_MAX) if t.name not in tops]
	today_rows = []
	for e in events:
		if e.get("date") and str(e["date"]) != str(now):
			continue
		today_rows.append({"type": "event", "name": e["name"], "title": e["title"], "why": "Event", "all_day": e.get("all_day"),
			"start": e.get("start"), "end": e.get("end"), "lead": "All day" if e.get("all_day") else str(e.get("start") or "")[11:16]})
	# tasks planned at a time today (set 7, the weekly review's goal work) sit among the events at their time
	due_names = {t.name for t in due_today}
	for t in scheduled_today(space, now, area):
		if t.name in due_names or t.name in tops:
			continue
		t.update({"why": "Scheduled", "type": "task", "all_day": 0, "start": str(t.scheduled_at)[:19], "lead": str(t.scheduled_at)[11:16]})
		today_rows.append(t)
	today_rows.sort(key=lambda r: (not r["all_day"], r["start"] or ""))
	for t in due_today:
		t["why"] = "Due today"
		t["type"] = "task"
		if t.get("scheduled_at") and str(t.scheduled_at)[:10] == str(now):
			t["lead"] = str(t.scheduled_at)[11:16]
		today_rows.append(t)
	# issue 55: tasks planned this week under a goal of the cycle, once each; a goal with nothing planned has no row
	shown = tops | {t.name for t in overdue} | {t.name for t in due_today} | {r["name"] for r in today_rows if r.get("type") == "task"}
	week = [{**t, "type": "task", "why": "This week"} for t in planned_this_week(space, now, area, cycle["name"] if cycle else None) if t.name not in shown]
	return {
		"order": ["top", "overdue", "today", "week"],
		"groups": [
			{"key": "top", "label": "This week's top three", "rows": top, "total": len(top)},
			{"key": "overdue", "label": "Overdue", "rows": overdue, "total": counts.overdue_tasks(space, area)["n"], "door": counts.overdue_tasks(space, area)},
			{"key": "today", "label": "Today", "rows": today_rows, "total": len(today_rows), "tasks": counts.due_today_tasks(space, area),
				"events": len(today_rows) - len(due_today)},
			{"key": "week", "label": "This week · under your goals", "rows": week, "total": len(week)},
		],
		"show": NEXT_ROWS,
	}


def rail_of(space, now, events, area=None):
	"""Today's events as a timeline, this week's important dates, renewals and the weekly review, and the insights (each text once, at most three)."""
	from lifeos.api import insights as insight_api

	week_end = add_days(now, 6 - now.weekday())
	week = []
	for d in calendar_data.important_dates_between(space, now, add_days(now, 7)):
		week.append({"kind": "important", "name": d["name"], "title": d["label"], "date": d["date"], "when": str(d["date"])})
	docs = calendar_data.expiring_documents(space, now)
	keep = in_area(space, area, "Life Vault Document", [d["name"] for d in docs])
	for d in (d for d in docs if d["name"] in keep):
		days = d.get("days")
		if days is not None and days <= 45:
			week.append({"kind": "vault", "name": d["name"], "title": d.get("title"), "date": d.get("expiry_date"), "days": days})
	s = frappe.get_cached_doc("Life Settings")
	day = s.weekly_review_day or "Sunday"
	names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
	review_on = add_days(now, (names.index(day) - now.weekday()) % 7)
	week.append({"kind": "review", "title": "Weekly review", "date": str(review_on), "time": str(s.weekly_review_time or "18:00:00")[:5],
		"day": day[:3]})
	week.sort(key=lambda x: str(x.get("date") or ""))
	other = {"rows": [], "total": 0} if permissions.is_agent() else unique_insights(insight_api.list(space=space, status="New", area=area, page_length=50)["rows"])
	timeline = [e for e in events if not e.get("date") or str(e["date"]) == str(now)]
	for t in scheduled_today(space, now, area):  # planned tasks on the timeline too (set 7)
		start = get_datetime(t.scheduled_at)
		timeline.append({"source": "task", "name": t.name, "title": t.title, "start": str(start)[:19], "all_day": 0, "date": str(now),
			"end": str(start + timedelta(minutes=t.duration_min or 60))[:19]})
	timeline.sort(key=lambda e: (not e.get("all_day"), str(e.get("start") or "")))
	return {"events": timeline, "week": week, "insights": other["rows"], "insights_total": other["total"]}


def unique_insights(rows, limit=3):
	"""The Insights of the rail: each text once (the first, in rank order), at most `limit`; `total` counts the distinct texts."""
	seen, out = set(), []
	for r in rows:
		key = " ".join(str(r.get("title") or "").lower().split())
		if key not in seen:
			seen.add(key)
			out.append(r)
	return {"rows": out[:limit], "total": len(out)}


OCCURRENCE = re.compile(r"^(review:\d{4}-\d{2}-\d{2}|(plan-next|close):[\w-]{1,40})$")


@frappe.whitelist(methods=["POST"])
def skip_banner(occurrence: str, how: str = "skipped"):
	"""Hide Today's rhythm banner until its next occurrence: `how` is skipped, or done (the weekly review's Finish)."""
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(frappe._("Agents have no Today."), frappe.PermissionError, title=frappe._("Agents have no Today"))
	if how not in ("skipped", "done") or not OCCURRENCE.match(str(occurrence or "")):
		frappe.throw(frappe._("Unknown banner."), title=frappe._("Unknown banner"))
	return rhythms.dismiss(occurrence, how)


def scheduled_today(space, now, area=None):
	"""Open tasks planned at a time today, in the lens, earliest first."""
	t = frappe.qb.DocType("Life Task")
	where = [*open_tasks(t, space, area), t.scheduled_at >= str(now), t.scheduled_at < str(add_days(now, 1))]
	return task_api.query(space, where, [(t.scheduled_at, Order.asc)], 0, 50)


@frappe.whitelist(methods=["GET"])
def week_summary(space: str | None = None, week_start: str | None = None):
	"""Everything an agent needs to run the weekly review in chat, for one week (Monday to Sunday): the cycle's score, habits,
	tasks done and carried, open loops, stale tasks to decide, and what the archive job archived."""
	from lifeos.library import archive

	space = permissions.resolve_space(space)
	now = getdate(today())
	start = getdate(week_start) if week_start else add_days(now, -now.weekday())
	start = add_days(start, -start.weekday())
	end = add_days(start, 6)

	cycle_out = None
	cycle = frappe.get_list("Life Cycle", filters={"space": space, "start_date": ("<=", end), "end_date": (">=", start)}, fields=["name", "title", "status"],
		order_by="start_date desc", limit=1)
	if cycle:
		c = frappe.get_doc("Life Cycle", cycle[0].name)
		week = min(max(cycles.week_of(c, min(end, getdate(c.end_date))), 1), cycles.WEEKS)
		cycle_out = {"name": c.name, "title": c.title, "week": week, **cycles.week_score(c.name, week)}

	habit_rows, seen = [], set()
	for y, m in sorted({(start.year, start.month), (end.year, end.month)}):
		for h in habit_rules.habits_month(space, y, m)["habits"]:
			if h["habit"] in seen:
				continue
			seen.add(h["habit"])
			habit_rows.append({"habit": h["habit"], "title": h["title"], "done": 0, "target": h["days_per_week"]})
	if habit_rows:  # one query for every habit's ticks
		log = frappe.qb.DocType("Life Habit Log")
		ticks = count_by("Life Habit Log", "habit", [log.habit.isin([h["habit"] for h in habit_rows]), log.date.between(start, end), log.done == 1])
		for h in habit_rows:
			h["done"] = ticks.get(h["habit"], 0)

	t = frappe.qb.DocType("Life Task")
	done_tasks = task_api.query(space, [t.status == "Done", t.completed_on.between(start, end)], [(t.completed_on, Order.desc)], 0, 100)
	carried = task_api.query(space, [t.status == "Carried", t.completed_on.between(start, end)], [(t.completed_on, Order.desc)], 0, 100)
	loop_rows = task_api.query(space, task_api.open_loops_criteria(t), [(t.creation, Order.asc)], 0, 20)
	return {
		"space": space, "week_start": str(start), "week_end": str(end), "cycle": cycle_out, "habits": habit_rows,
		"done_total": _count_tasks(space, "Done", start, end), "carried_total": _count_tasks(space, "Carried", start, end),
		"done": done_tasks, "carried": carried, "open_loops": loop_rows, "open_loops_total": task_api.open_loops_count(space),
		"decide": task_api.stale_tasks(space, 30),
		"archived": archive.archived_in_week(space, start, end),
		"stale_days": frappe.db.get_single_value("Life Settings", "stale_task_days") or 90,
		"target": frappe.db.get_single_value("Life Settings", "score_target") or 85,
	}


def _count_tasks(space, status, start, end):
	"""How many tasks closed with this status in the week, for the numbers that lead to the Tasks screen (the lists show 100)."""
	t = frappe.qb.DocType("Life Task")
	return task_api.count_where([t.space == space, t.status == status, t.completed_on.between(start, end)])


def proposal_counts(items, status=None):
	"""The proposals of each inbox item, as {item: count}; with `status`, only those in that status."""
	p = frappe.qb.DocType("Life Proposal")
	return count_by("Life Proposal", "inbox_item", [p.inbox_item.isin(items), *([p.status == status] if status else [])])


def list_query_one(doctype, field, where):
	"""One aggregate over the DocType's rows the user may read."""
	query = frappe.qb.get_query(doctype, fields=[field], ignore_permissions=False)
	for crit in where:
		query = query.where(crit)
	return query.run()[0][0]

