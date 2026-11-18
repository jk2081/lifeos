"""Tab 1, Library (set 8): last week's calendar strip, what came in by source (each count opens its list), the Inbox piles'
suggested split, and the revelations. A meeting opened shows what is linked to it, its follow-ups, and a line to plan from it."""
from collections import Counter
from datetime import timedelta

import frappe
from frappe.utils import add_days, get_datetime, getdate

from lifeos.review import findings, gcal, meetings

DAY = "%a %-d"


def data(review, user):
	space, start, end = review.doc.space, getdate(review.doc.period_start), getdate(review.doc.period_end)
	from lifeos.ai import client
	from lifeos.review.piles import PileSet

	ai = client.is_set_up() and bool(frappe.db.get_value("Life Space", space, "ask_enabled"))
	shown = findings.revelations(review)
	rows = findings.rows(shown)
	return {"strip": strip(space, start, end, user), "came_in": came_in(space, start, end), "inbox": PileSet(review, "inbox").split(),
		"revelations": [_revelation(r) for r in rows if r.status == "New"], "revelations_shown": len(rows), "ai": ai}


def strip(space, start, end, user):
	"""The period's days, each with its events. None when no calendar is connected and nothing was read from one."""
	events = meetings.in_period(space, start, end)
	connected = gcal.state(user)["connected"] or any(1 for e in events if e.get("life_attendees"))
	if not connected:
		return None
	marks = _marks([e.name for e in events if e.life_matters])
	days = []
	d = start
	while d <= end:
		day = [e for e in events if getdate(e.starts_on) == d]
		days.append({"date": str(d), "label": d.strftime(DAY), "events": [{"name": e.name, "title": e.subject, "start": str(e.starts_on)[:16],
			"all_day": e.all_day, "matters": bool(e.life_matters), "mark": marks.get(e.name) if e.life_matters else None} for e in day]})
		d = add_days(d, 1)
	return {"days": days, "matters": [e.name for e in events if e.life_matters]}


def _marks(names):
	"""'linked' when something is linked or a follow-up was found; 'none' when nothing was captured."""
	if not names:
		return {}
	linked = set(frappe.get_all("Life Meeting Link", filters={"event": ("in", names), "removed": 0}, pluck="event", distinct=True))
	found = set(frappe.get_all("Life Insight", filters={"meeting": ("in", names)}, pluck="meeting", distinct=True))
	return {n: "linked" if n in linked or n in found else "none" for n in names}


def came_in(space, start, end):
	"""Counts for the period by source, each a door to the list that shows exactly those rows."""
	from lifeos import counts
	from lifeos.api import library, sources

	a, b = str(start), str(end)
	f = counts._f

	def src(label, key, tab="all", conds=()):
		n = sources.list(space=space, tab=tab, from_date=a, to_date=b, filters=f(*conds), page_length=1)["total"]
		query = {k: v for k, v in {"tab": None if tab == "all" else tab, "from": a, "to": b, "f": f(*conds)}.items() if v}
		return {"key": key, "label": label, "n": int(n), "to": {"path": "/library/captures", "query": query}}

	captures = src("Captures and voice notes", "captures", conds=[("ref_doctype", "=", "Life Inbox Item"), ("media_kind", "not in", ["Email", "Email Digest"])])
	chats = src("Claude and other chats", "chats", tab="chats")
	emails = src("Emails from people", "emails", tab="email")
	conds = [("modified", ">=", f"{a} 00:00:00"), ("modified", "<=", f"{b} 23:59:59")]
	n = library.list(space=space, filters=f(*conds), page_length=1, collection="all")["total"]
	notes = {"key": "notes", "label": "Notes changed", "n": int(n), "to": {"path": "/library/notes", "query": {"view": "list", "f": f(*conds)}}}
	matter = meetings.in_period(space, start, end, only_matter=True)
	meets = {"key": "meetings", "label": "Meetings that matter", "n": len(matter), "drawer": "meetings"}
	rows = [captures, chats, emails, notes, meets]
	return {"rows": rows, "total": sum(r["n"] for r in rows)}


def _revelation(r):
	return {"name": r.name, "kind": r.kind, "title": r.title, "source": r.source_line or r.based_on, "meeting": r.meeting, "reading": r.reading,
		"actions": [{"index": i, "label": a.get("label"), "kind": a.get("kind"), "events": a.get("events")} for i, a in enumerate(r.actions)]}


# ---- a meeting opened ----

def meeting(review, event):
	space, start, end = review.doc.space, review.doc.period_start, review.doc.period_end
	ev = frappe.get_doc("Event", event)
	if ev.life_space != space or not frappe.has_permission("Event", "read", doc=ev):
		frappe.throw(frappe._("That meeting is not in this review."), frappe.PermissionError)
	links = meetings.linked(event)
	from lifeos.pane_refs import ref_of

	recs = [{"link": l.name, "how": l.how, "doctype": l.record_doctype, "name": l.record_name, "title": l.title,
		"kind": meetings.label_of(l.record_doctype, l.record_name), "ref": ref_of(l.record_doctype, l.record_name)} for l in links]
	order = [m.name for m in meetings.in_period(space, start, end, only_matter=True)]
	i = order.index(event) if event in order else -1
	goal = _goal_for(links)
	return {"name": ev.name, "title": ev.subject, "start": str(ev.starts_on)[:16], "end": str(ev.ends_on)[:16] if ev.ends_on else None,
		"all_day": ev.all_day, "attendees": meetings.attendees(ev), "matters": bool(ev.life_matters), "set_by": ev.life_matters_set_by,
		"area_name": _area_of(links), "linked": recs, "followups": [_revelation(r) for r in findings.for_meeting(event)],
		"goal": goal, "goals": goal_options(space), "prev": order[i - 1] if i > 0 else None, "next": order[i + 1] if 0 <= i < len(order) - 1 else None,
		"done": event in (review.state.get("meetings_done") or []), "candidates": candidates(space, ev, recs)}


def _area_of(links):
	areas = Counter(a for l in links for a in [frappe.db.get_value(l.record_doctype, l.record_name, "area")] if a)
	if not areas:
		return None
	return frappe.db.get_value("Life Area", areas.most_common(1)[0][0], "area_name")


def _goal_for(links):
	"""The goal a task from this meeting will link to: the goal of what is linked, most often first."""
	goals = Counter(g for l in links if frappe.get_meta(l.record_doctype).has_field("goal")
		for g in [frappe.db.get_value(l.record_doctype, l.record_name, "goal")] if g)
	return goals.most_common(1)[0][0] if goals else None


def goal_options(space):
	return frappe.db.sql("""select g.name as value, g.title as label from `tabLife Goal` g left join `tabLife Cycle` c on c.name = g.cycle
		where g.space = %s and g.outcome = 'In Progress' and g.is_someday = 0 and g.is_archived = 0
		and (g.goal_type != '12 Week Year' or c.status = 'Active') order by g.goal_type = '12 Week Year' desc, g.title limit 100""", space, as_dict=True)


def candidates(space, ev, recs):
	"""Records from the meeting's day and the day after, to link by hand."""
	have = {(r["doctype"], r["name"]) for r in recs}
	a = get_datetime(ev.starts_on).replace(hour=0, minute=0, second=0)
	b = a + timedelta(days=2)
	from lifeos.pane_refs import ref_of

	out = []
	for dt, when in (("Life Inbox Item", "ifnull(received_on, creation)"), ("Life Chat Log", "creation"), ("Life Note", "creation")):
		# nosemgrep: frappe-sql-format-injection -- dt and the date column come from the fixed tuple above; values are parameters
		for name, title in frappe.db.sql(f"select name, title from `tab{dt}` where space = %s and {when} between %s and %s order by {when} limit 30",
				(space, a, b)):
			if (dt, name) not in have:
				out.append({"doctype": dt, "name": name, "title": title, "kind": meetings.label_of(dt, name), "ref": ref_of(dt, name)})
	return out[:40]


def plan_task(review, event, title, goal=None):
	"""A line in the meeting drawer becomes a task linked to the meeting, under the goal chosen."""
	ev = frappe.get_doc("Event", event)
	if ev.life_space != review.doc.space:
		frappe.throw(frappe._("That meeting is not in this review."))
	title = " ".join((title or "").split())[:140]
	if not title:
		frappe.throw(frappe._("Type the task."))
	area = frappe.db.get_value("Life Goal", goal, "area") if goal else None
	t = frappe.get_doc({"doctype": "Life Task", "space": review.doc.space, "title": title, "status": "Open", "goal": goal or None, "area": area}).insert()
	meetings.link(event, "Life Task", t.name)
	note_created(review, t.name, goal, "library")
	return t.name


def note_created(review, task, goal, tab):
	"""Tasks made during the review, so the Goals tab can offer them first as a goal's next action."""
	review.state.setdefault("created_tasks", []).append({"task": task, "goal": goal, "tab": tab})
