"""Findings for the weekly review (set 8): one Life Insight per finding, shown wherever it belongs (a promise is a revelation in
Library and a follow-up in its meeting's drawer) and cleared everywhere at once when it is acted on or dismissed.

Rule findings: Goal reading (a Suggested reading waiting; confirming either confirms both) and Not captured (meetings that
matter with nothing linked, one per review period). With a key and within the cap, the nightly job reads each meeting that
matters with linked records for Promise and Date findings linked to the meeting. Precision matters more than recall: every
finding carries its source, and the model is told to leave out what it is unsure of.
"""
import json

import frappe
from frappe.utils import add_days, getdate, today

from lifeos import insights

REVELATIONS = ["Promise", "Goal reading", "Blocker", "Date", "Waiting on you", "Keeps coming up", "Theme", "Not captured"]
RANK = {k: i for i, k in enumerate(REVELATIONS)}
NEW_KINDS = ("Goal reading", "Blocker", "Keeps coming up", "Not captured", "Date")
MAX_SHOWN = 5


def add(space, kind, title, evidence, actions, meeting=None, reading=None, source="Rule", source_line=None, found_for=None, area=None, body=""):
	"""Store a finding once: the same kind and evidence (and meeting, or period) is never stored twice, dismissed or not."""
	key = evidence + ([{"ref_doctype": "Event", "ref_name": meeting}] if meeting else []) + ([{"ref_doctype": "Period", "ref_name": str(found_for)}] if found_for else [])
	fp = insights.fingerprint(kind, key)
	got = frappe.db.get_value("Life Insight", {"space": space, "fingerprint": fp})
	if got:
		return got
	return frappe.get_doc({"doctype": "Life Insight", "space": space, "kind": kind, "title": title[:255], "body": body, "evidence": evidence,
		"actions": json.dumps(actions), "status": "New", "fingerprint": fp, "source": source, "area": area, "found_on": today(),
		"rank": RANK.get(kind, 99), "meeting": meeting, "reading": reading, "source_line": (source_line or "")[:140] or None,
		"found_for": found_for}).insert(ignore_permissions=True).name


# ---- rule findings ----

def detect_readings(space):
	"""A Goal reading finding for each Suggested reading of a goal in progress."""
	rows = frappe.db.sql("""select r.name, r.goal, r.value, r.date, r.excerpt, r.source_doctype, r.source_name, g.title, g.unit, g.area, g.current_value,
		g.current_on from `tabLife Goal Reading` r join `tabLife Goal` g on g.name = r.goal
		where r.space = %s and r.status = 'Suggested' and g.outcome = 'In Progress'""", space, as_dict=True)
	for r in rows:
		if frappe.db.exists("Life Insight", {"reading": r.name}):
			continue
		value = f"{r.value:,g}{(' ' + r.unit) if r.unit else ''}"
		last = f" {r.title} last read {r.current_value:,g}." if r.current_on else f" {r.title} has no reading yet."
		said = f"“{r.excerpt.strip()[:160]}”" if r.excerpt else f"{value} was read for {r.title}."
		evidence = [insights.ev(r.source_doctype, r.source_name, "")] if r.source_doctype and r.source_name else [insights.ev("Life Goal", r.goal, r.title)]
		add(space, "Goal reading", f"{said}{last}", evidence,
			[{"kind": "confirm_reading", "label": f"Confirm {value}", "reading": r.name}, {"kind": "dismiss", "label": "Skip"}],
			reading=r.name, source_line=_source_line(r.source_doctype, r.source_name, r.date), area=r.area)


def detect_not_captured(space, start, end):
	"""One Not captured finding for the period, listing its meetings that matter with nothing linked; kept current."""
	from lifeos.review import meetings

	empty = [m for m in meetings.in_period(space, start, end, only_matter=True) if getdate(m.starts_on) <= getdate(today())
		and not frappe.db.exists("Life Meeting Link", {"event": m.name, "removed": 0})]
	got = frappe.db.get_value("Life Insight", {"space": space, "kind": "Not captured", "found_for": getdate(start)}, ["name", "status"], as_dict=True)
	if got and got.status != "New":
		return got.name
	if not empty:
		if got:
			frappe.delete_doc("Life Insight", got.name, ignore_permissions=True, delete_permanently=True)
		return None
	names = ", ".join(m.subject for m in empty[:4]) + (f" and {len(empty) - 4} more" if len(empty) > 4 else "")
	n = len(empty)
	title = f"{n} meeting{'s' if n != 1 else ''} that matter{'' if n != 1 else 's'} left nothing: {names}."
	evidence = [insights.ev("Event", m.name, m.subject) for m in empty]
	actions = [{"kind": "open_meetings", "label": "Go through them", "events": [m.name for m in empty]}, {"kind": "dismiss", "label": "Dismiss"}]
	if got:
		doc = frappe.get_doc("Life Insight", got.name)
		doc.title, doc.actions = title, json.dumps(actions)
		doc.set("evidence", evidence)
		doc.save(ignore_permissions=True)
		return doc.name
	return add(space, "Not captured", title, evidence, actions, source_line="Calendar", found_for=getdate(start))


def _source_line(doctype, name, on=None):
	from lifeos.review import meetings

	if not doctype or not name or not frappe.db.exists(doctype, name):
		return None
	when = getdate(on or frappe.db.get_value(doctype, name, "creation"))
	return f"{meetings.label_of(doctype, name)}, {when.strftime('%a %-d')}"


# ---- the revelations of a review ----

def pool(space, start):
	return frappe.db.sql("""select name from `tabLife Insight` where space = %(space)s and status = 'New' and kind in %(kinds)s
		and (found_on >= %(start)s or found_for = %(start)s or kind = 'Goal reading') order by `rank` asc, found_on desc, creation desc limit 50""",
		{"space": space, "kinds": REVELATIONS, "start": getdate(start)}, pluck=True)


def revelations(review):
	"""At most five findings for the period, most useful first. The five are kept in the review once chosen, so acting on one
	leaves "3 left" rather than bringing in the next; while fewer than five were ever chosen, new ones join."""
	chosen = [n for n in review.state.get("revelations") or [] if frappe.db.exists("Life Insight", n)]
	if len(chosen) < MAX_SHOWN:
		for n in pool(review.doc.space, review.doc.period_start):
			if n not in chosen and len(chosen) < MAX_SHOWN:
				chosen.append(n)
	review.state["revelations"] = chosen
	return chosen


def rows(names):
	from lifeos.api.insights import _out

	if not names:
		return []
	got = frappe.get_all("Life Insight", filters={"name": ("in", names)}, fields=["name", "kind", "title", "body", "status", "actions", "area", "source",
		"found_on", "meeting", "reading", "source_line"], limit=len(names))
	by = {r.name: r for r in _out(got)}
	return [by[n] for n in names if n in by]


def for_meeting(event):
	got = frappe.get_all("Life Insight", filters={"meeting": event, "status": "New"}, fields=["name", "kind"], order_by="creation asc", limit=20)
	return rows([g.name for g in sorted(got, key=lambda g: RANK.get(g.kind, 99))])


# ---- acting ----

def act(name, index, extra=None):
	"""Carry out a finding's action, then mark it Acted (it leaves every list). Returns what was made."""
	from lifeos import permissions
	from lifeos.api.utils import parse

	doc = permissions.get_doc_checked("Life Insight", name, "write")
	actions = parse(doc.actions, []) or []
	try:
		a = actions[int(index)]
	except (IndexError, ValueError, TypeError):
		frappe.throw(frappe._("No such action."))
	extra = extra or {}
	kind = a.get("kind")
	out = {"kind": kind}
	if kind == "dismiss":
		return dismiss(name, extra.get("reason"))
	if kind == "make_task":
		out["task"] = make_task(doc, title=extra.get("title") or a.get("title") or doc.title, due=a.get("due_date"), goal=extra.get("goal") or a.get("goal"),
			area=a.get("area") or doc.area)
		doc.acted_note = "task made"
	elif kind == "confirm_reading":
		from lifeos.api import goals as goal_api

		goal_api.confirm_reading(a["reading"], extra.get("value"))  # as on the goal: the goal's current value follows
		return out  # the reading's hook has marked this finding Acted (reading_changed)
	elif kind in ("make_goal", "someday"):
		from lifeos.api import someday

		parked = someday.create(title=(a.get("title") or doc.title)[:140], space=doc.space, body_md=doc.title, area=doc.area)
		out["parked"] = parked.get("name")
		doc.acted_note = "parked in Someday" if kind == "someday" else "parked in Someday to make a goal from"
	elif kind == "open_meetings":
		out["events"] = a.get("events") or []
		return out  # going through the meetings is not acting on it
	else:
		from lifeos.api import insights as insight_api

		return insight_api.act(name, index)  # the actions of set 5's insights (Waiting on you, Theme)
	doc.status = "Acted"
	doc.save()
	return out


def make_task(doc, title, due=None, goal=None, area=None):
	"""A task from a finding, linked to its meeting when it has one."""
	from lifeos.review import meetings

	t = frappe.get_doc({"doctype": "Life Task", "space": doc.space, "title": title[:140], "status": "Open", "due_date": due or None,
		"goal": goal or None, "area": area or None}).insert()
	if doc.get("meeting"):
		meetings.link(doc.meeting, "Life Task", t.name)
	return t.name


def dismiss(name, reason=None):
	from lifeos import permissions

	doc = permissions.get_doc_checked("Life Insight", name, "write")
	doc.status, doc.dismiss_reason = "Dismissed", reason if reason in ("Not relevant", "Already done", "Wrong") else "Not relevant"
	doc.save()
	if doc.reading and frappe.db.get_value("Life Goal Reading", doc.reading, "status") == "Suggested":
		from lifeos.api import goals as goal_api

		goal_api.reject_reading(doc.reading)  # skipping a reading rejects it, so the goal does not ask again
	return {"kind": "dismiss", "status": "Dismissed"}


def reading_changed(doc, method=None):
	"""A reading confirmed or rejected anywhere (the goal, the review) clears its finding too."""
	if doc.status == "Suggested":
		return
	for name in frappe.get_all("Life Insight", filters={"reading": doc.name, "status": "New"}, pluck="name"):
		frappe.db.set_value("Life Insight", name, {"status": "Acted" if doc.status == "Confirmed" else "Dismissed",
			"acted_note": f"reading {doc.status.lower()}"})


def counts(space, start, end):
	"""Findings acted on and dismissed in the period, for the week's numbers."""
	rows = frappe.db.sql("""select status, count(*) from `tabLife Insight` where space = %s and kind in %s and status in ('Acted', 'Dismissed')
		and modified between %s and %s group by status""", (space, REVELATIONS, getdate(start), add_days(getdate(end), 1)))
	got = dict(rows)
	return {"acted": int(got.get("Acted") or 0), "dismissed": int(got.get("Dismissed") or 0)}
