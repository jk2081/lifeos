"""One call for the Today screen."""
import frappe
from frappe.utils import add_days, getdate, today

from lifeos import calendar_data, journal, permissions
from lifeos.api import tasks as task_api
from lifeos.api import vault as vault_api
from lifeos.api.utils import user_names

GROUP_ROWS = 7


def week_actions(cycle, week):
	"""The actions planned in a week of a cycle, with the ticks they have, for the This week card on Today."""
	doc = frappe.get_cached_doc("Life Cycle", cycle.name)
	actions, ticks = journal._actions(cycle.name), journal._ticks(cycle.name)
	goals = dict(frappe.get_all("Life Goal", filters={"cycle": cycle.name}, fields=["name", "title"], as_list=True))
	out = []
	for a in actions:
		if not journal.planned_in_week(doc, a, week):
			continue
		out.append({"name": a.name, "title": a.title, "goal": a.goal, "goal_title": goals.get(a.goal), "status": a.status,
			"per_week": int(a.per_week or 1), "count": ticks.get(a.name, {}).get(week, 0)})
	return out


@frappe.whitelist()
def get(space=None):
	"""Tasks due or overdue, today's events, habits with today's state, items to review, the current week of the active cycle,
	the open loops count and expiring documents."""
	space = permissions.resolve_space(space)
	now = getdate(today())

	open_due = "and t.status in ('Open', 'Doing', 'Waiting') and t.is_archived = 0 and t.due_date "
	due = task_api.query(space, open_due + "<= %(today)s", {"today": now}, None, 0, 30)
	# the screen shows two groups of at most GROUP_ROWS: due today first, then overdue (oldest first)
	due_today = task_api.query(space, open_due + "= %(today)s", {"today": now}, None, 0, GROUP_ROWS)
	overdue_rows = task_api.query(space, open_due + "< %(today)s", {"today": now}, None, 0, GROUP_ROWS)
	oldest = frappe.db.sql(f"select min(t.due_date) from `tabLife Task` t where t.space=%(space)s {open_due}< %(today)s",
		{"space": space, "today": now})[0][0]
	# the numbers are counted with the filters their links lead to, not from the rows shown
	due_count = task_api.count(space, due="today,overdue")
	today_count = task_api.count(space, due="today")
	overdue = task_api.count(space, due="overdue")

	review_items = frappe.get_all("Life Inbox Item", filters={"space": space, "status": "To Review", "is_archived": 0},
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
	to_review = frappe.db.count("Life Inbox Item", {"space": space, "status": "To Review", "is_archived": 0})
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
				"done": score["done"], "planned": score["planned"], "actions": week_actions(cycle, week)}
		else:
			cycle_out = {"name": cycle.name, "title": cycle.title, "week": None, "weeks": journal.WEEKS, "ended": week > journal.WEEKS,
				"start_date": str(cycle.start_date)}

	coming = []
	for d in calendar_data.expiring_documents(space, now):
		coming.append({"kind": "vault", **d})
	for d in sorted(calendar_data.important_dates_between(space, now, add_days(now, 14)), key=lambda x: x["date"]):
		coming.append({"kind": "important", "name": d["name"], "title": d["label"], "date": d["date"], "date_kind": d["kind"],
			"days": (getdate(d["date"]) - now).days})

	return {
		"date": str(now), "space": space,
		"cycle": cycle_out, "target": frappe.db.get_single_value("Life Settings", "score_target") or 85,
		"to_review": {"count": to_review, "proposals": proposals_waiting, "items": review_items},
		"tasks": {"items": due, "due": due_count, "overdue": overdue, "today": due_today, "today_count": today_count,
			"overdue_items": overdue_rows, "oldest_overdue": str(oldest) if oldest else None, "group_rows": GROUP_ROWS},
		"events": events, "habits": habits,
		"open_loops": task_api.open_loops_count(space),
		"coming_up": coming,
		"vault_soon": vault_api.expiry_counts(space)["soon"],
	}
