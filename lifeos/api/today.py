"""One call for the Today screen."""
import re

import frappe
from frappe.utils import add_days, getdate, today

from lifeos import calendar_data, journal, permissions, rhythms
from lifeos.api import tasks as task_api
from lifeos.api import vault as vault_api
from lifeos.api.utils import area_filter, descendants, in_area, lens_area, user_names

GROUP_ROWS = 7


def task_lens(space, area):
	"""The lens as SQL on tasks (alias t): an " and ..." fragment and its values, or nothing for All of life."""
	if not area:
		return "", {}
	values = {}
	return f" and {area_filter(space, area, 't.area', values, also_in='Life Task')} ", values


def week_actions(cycle, week, space=None, area=None):
	"""The actions planned in a week of a cycle, with the ticks they have, for the This week card on Today. Under the lens,
	only the actions of goals in the area."""
	doc = frappe.get_cached_doc("Life Cycle", cycle.name)
	actions, ticks = journal._actions(cycle.name), journal._ticks(cycle.name)
	goal_filter = {"cycle": cycle.name}
	if area:
		goal_filter["area"] = ("in", descendants(space, area))
	goals = dict(frappe.get_all("Life Goal", filters=goal_filter, fields=["name", "title"], as_list=True))
	out = []
	for a in actions:
		if not journal.planned_in_week(doc, a, week) or (area and a.goal not in goals):
			continue
		out.append({"name": a.name, "title": a.title, "goal": a.goal, "goal_title": goals.get(a.goal), "status": a.status,
			"per_week": int(a.per_week or 1), "count": ticks.get(a.name, {}).get(week, 0)})
	return out


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None, area: str | None = None, at: str | None = None):
	"""Tasks due or overdue, today's events, habits with today's state, items to review, the current week of the active cycle,
	the open loops count and expiring documents. `area` is the lens (UX fixes, set 6): the band, Next and the rail keep to
	the area and its sub-areas. Events and important dates have no area, so they always show. `banner` is the one rhythm
	that is due (lifeos/rhythms.py); `at` moves its clock on a test site only."""
	space = permissions.resolve_space(space)
	area = lens_area(area)
	now = getdate(today())
	lens, lens_values = task_lens(space, area)

	open_due = lens + "and t.status in ('Open', 'Doing', 'Waiting') and t.is_archived = 0 and t.due_date "
	due = task_api.query(space, open_due + "<= %(today)s", {"today": now, **lens_values}, None, 0, 30)
	# the screen shows two groups of at most GROUP_ROWS: due today first, then overdue (oldest first)
	due_today = task_api.query(space, open_due + "= %(today)s", {"today": now, **lens_values}, None, 0, GROUP_ROWS)
	overdue_rows = task_api.query(space, open_due + "< %(today)s", {"today": now, **lens_values}, None, 0, GROUP_ROWS)
	# nosemgrep: frappe-sql-format-injection -- `lens` is area_filter's fixed SQL; values are parameters
	oldest = frappe.db.sql("select min(t.due_date) from `tabLife Task` t where t.space=%(space)s and t.status in ('Open', 'Doing', 'Waiting') "
		f"and t.is_archived = 0 and t.due_date < %(today)s {lens}",
		{"space": space, "today": now, **lens_values})[0][0]
	# the numbers are counted with the filters their links lead to, not from the rows shown
	due_count = task_api.count(space, due="today,overdue", area=area)
	today_count = task_api.count(space, due="today", area=area)
	overdue = task_api.count(space, due="overdue", area=area)

	from lifeos.api import inbox as inbox_api

	inbox_lens = inbox_api.list(space=space, status='["To Review"]', area=area, page_length=5) if area else None
	review_filter = {"space": space, "status": "To Review", "is_archived": 0}
	if inbox_lens is not None:
		review_filter["name"] = ("in", [r.name for r in inbox_lens["items"]] or ["-"])
	review_items = frappe.get_all("Life Inbox Item", filters=review_filter,
		fields=["name", "title", "source_type", "received_on", "owner", "claimed_by", "transcript_md", "summary_md"], order_by="received_on desc", limit=5)
	pending = {}
	if review_items:
		pending = dict(frappe.db.sql(
			"select inbox_item, count(*) from `tabLife Proposal` where inbox_item in %s group by inbox_item", ([r.name for r in review_items],)))
	waiting = {}
	if review_items:
		waiting = dict(frappe.db.sql(
			"select inbox_item, count(*) from `tabLife Proposal` where inbox_item in %s and status='Pending' group by inbox_item",
			([r.name for r in review_items],)))
	users = user_names([r.claimed_by for r in review_items])
	for r in review_items:
		r["proposals"] = pending.get(r.name, 0)
		r["pending"] = waiting.get(r.name, 0)
		r["state"] = "Transcribed" if r.pop("transcript_md") else ("Summary ready" if r.pop("summary_md", None) else "Processed")
		r.pop("summary_md", None)
		r["processed_by"] = users.get(r.claimed_by)
		r["received_on"] = str(r.received_on)[:19]
	to_review = inbox_lens["total"] if inbox_lens is not None else frappe.db.count("Life Inbox Item", {"space": space, "status": "To Review", "is_archived": 0})
	proposals_waiting = frappe.db.sql(
		"select count(*) from `tabLife Proposal` p join `tabLife Inbox Item` i on i.name = p.inbox_item "
		"where p.space=%s and p.status='Pending' and i.status='To Review' and i.is_archived=0", space)[0][0]

	events = [e for e in calendar_data.events_between(space, now, add_days(now, 1))]
	events.sort(key=lambda e: e["start"])

	month = journal.habits_month(space, now.year, now.month)
	habits = [{"habit": h["habit"], "title": h["title"], "done": now.day in h["done_days"]} for h in month["habits"] if not h["removed"]]

	cycle_out = None
	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "title", "start_date", "end_date"], as_dict=True)
	if cycle:
		week = journal.week_of(cycle, now)
		if 1 <= week <= journal.WEEKS:
			score = journal.week_score(cycle.name, week)
			cycle_out = {"name": cycle.name, "title": cycle.title, "week": week, "weeks": journal.WEEKS, "score": score["percent"],
				"done": score["done"], "planned": score["planned"], "actions": week_actions(cycle, week, space, area)}
		else:
			cycle_out = {"name": cycle.name, "title": cycle.title, "week": None, "weeks": journal.WEEKS, "ended": week > journal.WEEKS,
				"start_date": str(cycle.start_date)}

	coming = []
	docs = calendar_data.expiring_documents(space, now)
	keep = in_area(space, area, "Life Vault Document", [d["name"] for d in docs])
	for d in (d for d in docs if d["name"] in keep):
		coming.append({"kind": "vault", **d})
	for d in sorted(calendar_data.important_dates_between(space, now, add_days(now, 14)), key=lambda x: x["date"]):
		coming.append({"kind": "important", "name": d["name"], "title": d["label"], "date": d["date"], "date_kind": d["kind"],
			"days": (getdate(d["date"]) - now).days})

	from lifeos import counts

	band = counts.open_band(space, area)
	nxt = next_list(space, now, cycle_out, events, area)
	rail = rail_of(space, now, events, area)
	return {
		"band": band, "next": nxt, "rail": rail, "days_left": 6 - now.weekday(),
		"date": str(now), "space": space,
		"cycle": cycle_out, "target": frappe.db.get_single_value("Life Settings", "score_target") or 85,
		"to_review": {"count": to_review, "proposals": proposals_waiting, "items": review_items},
		"tasks": {"items": due, "due": due_count, "overdue": overdue, "today": due_today, "today_count": today_count,
			"overdue_items": overdue_rows, "oldest_overdue": str(oldest) if oldest else None, "group_rows": GROUP_ROWS},
		"events": events, "habits": habits,
		"open_loops": task_api.open_loops_count(space), "area": area,
		"banner": None if permissions.is_agent() else rhythms.banner(space, at),
		"coming_up": coming,
		"vault_soon": vault_api.expiry_counts(space)["soon"],
	}


# ---- UX fixes, set 5: the Next list and the right rail ----
NEXT_ROWS = 8  # rows shown before "N more"
GROUP_MAX = 30


def next_list(space, now, cycle, events, area=None):
	"""One list in a fixed order: Overdue, Today (events at their times and tasks due today), 12 Week Year this week
	(planned actions not yet ticked), Needs a decision (actionable insights). Someday items never appear."""
	from lifeos import counts
	from lifeos.api import insights as insight_api

	lens, lens_values = task_lens(space, area)
	open_due = lens + "and t.status in ('Open', 'Doing', 'Waiting') and t.is_archived = 0 and t.due_date "
	overdue = task_api.query(space, open_due + "< %(today)s", {"today": now, **lens_values}, "t.due_date asc, t.creation asc", 0, GROUP_MAX)
	for t in overdue:
		t["why"] = "Overdue"
		t["lead"] = f"{(now - getdate(t.due_date)).days} day{'s' if (now - getdate(t.due_date)).days != 1 else ''}"
	due_today = task_api.query(space, open_due + "= %(today)s", {"today": now, **lens_values}, None, 0, GROUP_MAX)
	today_rows = []
	for e in events:
		if e.get("date") and str(e["date"]) != str(now):
			continue
		today_rows.append({"type": "event", "name": e["name"], "title": e["title"], "why": "Event", "all_day": e.get("all_day"),
			"start": e.get("start"), "end": e.get("end"), "lead": "All day" if e.get("all_day") else str(e.get("start") or "")[11:16]})
	today_rows.sort(key=lambda r: (not r["all_day"], r["start"] or ""))
	for t in due_today:
		t["why"] = "Due today"
		t["type"] = "task"
		today_rows.append(t)
	twy = []
	if cycle and cycle.get("week"):
		for a in cycle["actions"]:
			if a["status"] == "Open" and a["count"] < a["per_week"]:
				twy.append({**a, "type": "action", "why": "12WY", "week": cycle["week"]})
	# insights are for people (set 5); an agent's Today has none
	ins = {"rows": [], "total": 0} if permissions.is_agent() else insight_api.list(space=space, status="New", actionable=1, area=area, page_length=GROUP_MAX)
	for r in ins["rows"]:
		r["type"] = "insight"
		r["why"] = r.kind
	return {
		"order": ["overdue", "today", "twy", "decisions"],
		"groups": [
			{"key": "overdue", "label": "Overdue", "rows": overdue, "total": counts.overdue_tasks(space, area)["n"], "door": counts.overdue_tasks(space, area)},
			{"key": "today", "label": "Today", "rows": today_rows, "total": len(today_rows), "tasks": counts.due_today_tasks(space, area),
				"events": len(today_rows) - len(due_today)},
			{"key": "twy", "label": "12 Week Year · this week", "rows": twy, "total": len(twy)},
			{"key": "decisions", "label": "Needs a decision", "rows": ins["rows"], "total": ins["total"],
				"door": {"n": ins["total"], "to": {"path": "/ask", "query": {"tab": "insights", "actionable": 1, **({"area": area} if area else {})}},
					"label": "need a decision"}},
		],
		"show": NEXT_ROWS,
	}


def rail_of(space, now, events, area=None):
	"""Today's events as a timeline, this week's important dates, renewals and the weekly review, and the other insights."""
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
	other = {"rows": [], "total": 0} if permissions.is_agent() else insight_api.list(space=space, status="New", actionable=0, area=area, page_length=5)
	timeline = [e for e in events if not e.get("date") or str(e["date"]) == str(now)]
	return {"events": timeline, "week": week, "insights": other["rows"], "insights_total": other["total"]}


OCCURRENCE = re.compile(r"^(review:\d{4}-\d{2}-\d{2}|month:\d{4}-\d{2}|(plan-next|close):[\w-]{1,40})$")


@frappe.whitelist(methods=["POST"])
def skip_banner(occurrence: str, how: str = "skipped"):
	"""Hide Today's rhythm banner until its next occurrence: `how` is skipped, or done (the weekly review's Finish)."""
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(frappe._("Agents have no Today."), frappe.PermissionError)
	if how not in ("skipped", "done") or not OCCURRENCE.match(str(occurrence or "")):
		frappe.throw(frappe._("Unknown banner."))
	return rhythms.dismiss(occurrence, how)
