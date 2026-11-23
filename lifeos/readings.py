"""Key results (set 7): how a goal's progress is measured, and the readings of a number goal.

A goal says how you will know it is done: a finish line (`done_when`, measure kind Milestone) or a number (measure kind
Number: what is measured, its unit, a start and a target). A number goal's current value is its latest Confirmed reading.
Readings are suggested by agents (a Reading proposal) or by the nightly job, and only a person confirms them."""
import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from lifeos import permissions

STALE_DAYS = 14  # the weekly review asks "Where is X now?" for a number goal with no reading for this long
WINDOW_DAYS = 7  # the nightly job reads this many days of captures and chat logs
MAX_RECORDS = 30
CHARS_PER_RECORD = 2000

# A frequency is a habit, not a goal: "daily", "every morning", "3 times a week", "twice a week", "weekly"
FREQUENCY = (r"\b(daily|every\s?day|each\s?day|every\s+(morning|evening|night|week|weekday|monday|tuesday|wednesday|thursday|friday|"
	r"saturday|sunday)|weekly|nightly|(\d+|once|twice|two|three|four|five|six)\s*(x|times?)?\s*(a|per|each|every)\s+(day|week)|"
	r"(once|twice)\s+(a|per)\s+(day|week))\b")
WORD_NUM = {"once": 1, "twice": 2, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def habit_of(*texts):
	"""When a goal's title or finish line reads as a frequency, the habit it really is: {title, days_per_week}; else None."""
	for text in texts:
		text = (text or "").strip()
		m = re.search(FREQUENCY, text, re.I)
		if not m:
			continue
		words = m.group(0).lower()
		days = 7
		n = re.search(r"(\d+|once|twice|two|three|four|five|six)\s*(x|times?)?\s*(a|per|each|every)\s+week", words)
		if n:
			days = int(n.group(1)) if n.group(1).isdigit() else WORD_NUM[n.group(1)]
		elif re.search(r"weekly|every\s+week|every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", words):
			days = 1
		elif re.search(r"every\s+weekday", words):
			days = 5
		return {"title": (texts[0] or text).strip()[:140], "days_per_week": max(1, min(7, days))}
	return None


EXAMPLES = {
	"12 weeks": ["The first three customers are using it and I have their feedback in writing.",
		"The new routine ran every week of the cycle and its results are filed."],
	"Month": ["The report is sent and the owner has replied.", "Every open item on the list is closed or has a new date."],
	"Year": ["The plant has run a full season at the new yield and the numbers are in the books.",
		"The new system is in daily use and the old one is switched off."],
	"Long term": ["The business runs without me in the weekly meeting.", "The land is planted, watered and producing."],
}


def examples_for(horizon):
	"""Two finish lines to start from, for a goal's type: what Suggest shows when no assistant answers."""
	return EXAMPLES.get(horizon) or EXAMPLES["Long term"]


def suggest_measure(title, notes=None, space=None, area=None, actions=None, tasks=None, horizon=None):
	"""The define-goal skill's proposal for a goal's kind and, for a number, its measure, unit and target, from the title and notes
	(a Milestone with its finish line, or a Number). `habit` is set when the title reads as a frequency. With no key, or when the skill
	says nothing, `kind` is None and the owner writes it themselves."""
	from lifeos.skills import call

	out = {"kind": None, "habit": habit_of(title, notes), "by": None, "examples": examples_for(horizon), "done_when": None, "measure": None, "unit": None, "target_value": None,
		"start_value": None}
	# the goal's area, weekly actions and open tasks go in with its notes, which the skill already reads
	more = [f"Area: {area}"] if area else []
	more += [f"Weekly actions: {'; '.join(actions)}"] if actions else []
	more += [f"Open tasks: {'; '.join(tasks)}"] if tasks else []
	got = call.ask("define-goal", {"request": "measure", "title": title, "notes": "\n".join([notes or "", *more]).strip()[:2000]}, space=space)
	kind = got.get("kind")
	if kind not in ("Milestone", "Number"):
		return out
	out.update(kind=kind, by=got.label)
	if kind == "Number":
		out.update(measure=(got.get("measure") or "")[:140] or None, unit=(got.get("unit") or "")[:40] or None,
			target_value=got.get("target_value"), start_value=got.get("start_value"))
	else:
		out["done_when"] = (got.get("done_when") or "")[:500] or None
	return out


def num(v):
	if v is None:
		return ""
	v = flt(v)
	return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")


def progress(start, target, current):
	"""(current − start) / (target − start), clamped to 0 to 100. Works for goals that go down (84 → 78) as well as up."""
	if start is None or target is None or flt(target) == flt(start):
		return None
	if current is None:
		return 0.0
	p = (flt(current) - flt(start)) / (flt(target) - flt(start))
	return round(100.0 * min(max(p, 0.0), 1.0), 1)


def direction(start, target):
	return "down" if flt(target) < flt(start) else "up"


def reached(goal):
	"""True when a number goal's current value has reached its target, in its direction."""
	if goal.get("measure_kind") != "Number" or not goal.get("current_on") or goal.get("target_value") is None:
		return False
	cur, tgt = flt(goal.get("current_value")), flt(goal.get("target_value"))
	return cur <= tgt if direction(goal.get("start_value"), tgt) == "down" else cur >= tgt


def has_finish_line(goal):
	kind = goal.get("measure_kind")
	if kind == "Number":
		return bool(goal.get("measure")) and goal.get("start_value") is not None and goal.get("target_value") is not None
	if kind == "Milestone":
		return bool((goal.get("done_when") or "").strip())
	# a goal from before set 7 with a "done when" has a finish line
	return bool((goal.get("done_when") or "").strip())


REQUIRED_MESSAGE = "Write what will be true when this goal is done. Stuck? Use Suggest."


def done_when_required():
	"""The setting "Require Done when on new goals": on unless the owner switched it off (a site that never saved it is on)."""
	# read the stored value itself: a Check that was never saved reads as 0 from the document, but the setting is on until it is switched off
	rows = frappe.db.sql("select value from `tabSingles` where doctype = 'Life Settings' and field = 'require_done_when'")
	return not rows or bool(int(rows[0][0] or 0))


def require_finish_line(values):
	"""Refuse a new goal with no finish line and no number with its target while the setting is on. `values` is a dict of the
	goal's fields (done_when, measure_kind, measure, start_value, target_value). Existing goals are never checked."""
	if done_when_required() and not has_finish_line(values):
		frappe.throw(_(REQUIRED_MESSAGE), frappe.ValidationError, title=_("Goal needs a measure"))


def check_goal(doc):
	"""The rule for a goal whose measure is set or changed: a milestone needs `done_when`; a number needs `measure`, a start
	and a target that differ. A goal from before set 7 with neither is not blocked (it shows under "Needs a finish line")."""
	kind = doc.get("measure_kind")
	if not kind:
		return
	if kind == "Milestone" and not (doc.get("done_when") or "").strip():
		frappe.throw(_("Say what will be true when this goal is done."), frappe.ValidationError, title=_("Goal needs a finish line"))
	if kind == "Number":
		if not (doc.get("measure") or "").strip():
			frappe.throw(_("Say what is measured, for example Ghillidary yield."), frappe.ValidationError, title=_("Measure is missing"))
		if doc.get("start_value") is None or doc.get("target_value") is None:
			frappe.throw(_("A number goal needs a start and a target."), frappe.ValidationError, title=_("Start and target missing"))
		if flt(doc.start_value) == flt(doc.target_value):
			frappe.throw(_("The target must differ from the start."), frappe.ValidationError, title=_("Target equals start"))


def refresh_current(goal):
	"""current_value and current_on always equal the latest Confirmed reading (by date, then the latest entered)."""
	row = frappe.db.sql("""select value, date from `tabLife Goal Reading` where goal=%s and status='Confirmed'
		order by date desc, creation desc limit 1""", goal, as_dict=True)
	value, on = (row[0].value, row[0].date) if row else (0, None)  # Float columns are never null: no reading is current_on unset
	frappe.db.set_value("Life Goal", goal, {"current_value": value, "current_on": on}, update_modified=False)
	return value, on


def summary(goal):
	"""How far a goal is, in one dict the screens share: kind (number, milestone, cycle, tasks), percent, and a label."""
	g = goal
	if g.get("measure_kind") == "Number" and g.get("target_value") is not None:
		p = progress(g.get("start_value"), g.get("target_value"), g.get("current_value") if g.get("current_on") else None)
		unit = f" {g.get('unit')}" if g.get("unit") else ""
		has = bool(g.get("current_on"))
		cur = num(g.get("current_value")) if has else num(g.get("start_value"))
		return {"kind": "number", "percent": p, "reached": reached(g), "direction": direction(g.get("start_value"), g.get("target_value")),
			"label": f"{cur}{unit}, target {num(g.get('target_value'))}{unit}" if has else f"No reading yet, target {num(g.get('target_value'))}{unit}",
			"start": g.get("start_value"), "current": g.get("current_value") if has else None, "target": g.get("target_value"), "unit": g.get("unit"),
			"measure": g.get("measure"), "current_on": str(g.get("current_on")) if g.get("current_on") else None}
	if g.get("horizon") == "12 weeks" and g.get("score") is not None:
		return {"kind": "cycle", "percent": round(flt(g.get("score")), 1), "label": f"{round(flt(g.get('score')))}% of ticks"}
	n, done = cint(g.get("tasks_counted")), cint(g.get("tasks_done"))
	if n:
		return {"kind": "tasks", "percent": round(100.0 * done / n, 1), "label": f"{done} of {n} tasks"}
	return {"kind": "none", "percent": None, "label": "No tasks yet"}


def reading_dict(r):
	return {"name": r.name, "goal": r.goal, "date": str(r.date), "value": r.value, "status": r.status, "excerpt": r.excerpt,
		"source_doctype": r.source_doctype, "source_name": r.source_name, "suggested_by": r.suggested_by,
		"confirmed_on": str(r.confirmed_on)[:19] if r.get("confirmed_on") else None}


def for_goal(goal):
	"""Confirmed readings (oldest first, for the chart) and Suggested ones (newest first) of a goal."""
	rows = frappe.get_all("Life Goal Reading", filters={"goal": goal, "status": ["in", ["Confirmed", "Suggested"]]},
		fields=["name", "goal", "date", "value", "status", "excerpt", "source_doctype", "source_name", "suggested_by", "confirmed_on", "creation"],
		order_by="date asc, creation asc", limit=500)
	return [reading_dict(r) for r in rows if r.status == "Confirmed"], [reading_dict(r) for r in reversed(rows) if r.status == "Suggested"]


def suggest(goal, value, on=None, excerpt=None, source_doctype=None, source_name=None, by="Agent"):
	"""Store a Suggested reading, unless the same value from the same source is already there."""
	on = str(getdate(on or today()))
	dup = frappe.db.exists("Life Goal Reading", {"goal": goal, "value": flt(value), "date": on, "status": ["!=", "Rejected"],
		"source_name": source_name or ("is", "not set")})
	if dup:
		return frappe.get_doc("Life Goal Reading", dup)
	return frappe.get_doc({"doctype": "Life Goal Reading", "space": frappe.db.get_value("Life Goal", goal, "space"), "goal": goal,
		"date": on, "value": flt(value), "status": "Suggested", "excerpt": (excerpt or "")[:1000] or None,
		"source_doctype": source_doctype if source_name else None, "source_name": source_name or None, "suggested_by": by,
	}).insert(ignore_permissions=True)


# ---- the nightly job: readings found in the last week's captures and chat logs ----

def number_goals(space):
	return frappe.get_all("Life Goal", filters={"space": space, "measure_kind": "Number", "outcome": "In Progress", "is_someday": 0, "is_archived": 0},
		fields=["name", "title", "measure", "unit", "start_value", "target_value", "current_value"], limit=50)


def from_recent(space, user):
	"""Look through the last 7 days of captures and chat logs, with the notice skill, for values matching a number goal's measure, and
	store them as Suggested readings with their excerpt. Returns (how many, a note when skipped)."""
	from lifeos.ai import client
	from lifeos.ai.tools import Context
	from lifeos.insights import recent_records
	from lifeos.skills import call

	goals = number_goals(space)
	if not goals:
		return 0, None
	if not client.is_set_up():
		return 0, "Readings skipped: no API key."
	ctx = Context(space, {"kind": "space", "label": "Everything in this space"}, user)
	records = recent_records(ctx, space, ("Chat", "Inbox"), WINDOW_DAYS, MAX_RECORDS, CHARS_PER_RECORD)
	if not records:
		return 0, None
	ids = {f"G{i + 1}": g for i, g in enumerate(goals)}
	got = call.ask("notice", {"request": "readings", "today": today(), "records": records,
		"goals": [{"goal": k, "title": g.title, "measure": g.measure, "unit": g.unit} for k, g in ids.items()]}, space=space, user=user)
	if not got:
		return 0, f"Readings skipped: {got.reason}"
	made = 0
	for c in (got.get("readings") or [])[:20]:
		g, ref = ids.get(c.get("goal")), ctx.refs.get(c.get("record"))
		if not g or not ref or not isinstance(c.get("value"), (int, float)):
			continue
		try:
			on = min(getdate(c.get("date") or ref.get("date") or today()), getdate(today()))
		except Exception:
			on = getdate(today())
		before = frappe.db.count("Life Goal Reading", {"goal": g.name})
		suggest(g.name, c["value"], on, (c.get("excerpt") or "")[:200], ref["doctype"], ref["name"], by=got.label)
		made += frappe.db.count("Life Goal Reading", {"goal": g.name}) - before
	return made, None


def run_for_space(space, user):
	"""Called by the nightly insights job for each space, as its owner, inside the job's savepoint."""
	frappe.db.savepoint("lifeos_readings")
	try:
		return from_recent(space, user)
	except Exception:
		frappe.db.rollback(save_point="lifeos_readings")
		frappe.log_error(title=f"Life OS readings for {space}")
		return 0, "Readings failed."


def stale_number_goals(space, goals=None):
	"""Number goals in progress with no Confirmed reading in the last 14 days."""
	cutoff = getdate(add_days(today(), -STALE_DAYS))
	goals = goals if goals is not None else number_goals(space)
	lasts = dict(frappe.db.sql("""select goal, max(date) from `tabLife Goal Reading` where goal in %s and status='Confirmed'
		group by goal""", ([g.name for g in goals] or [""],))) if goals else {}
	out = []
	for g in goals:
		last = lasts.get(g.name)
		if not last or getdate(last) < cutoff:
			out.append({**g, "last_reading_on": str(last) if last else None})
	return out


def confirm(reading, value=None, on=None):
	doc = permissions.get_doc_checked("Life Goal Reading", reading, "write")
	if value is not None and value != "":
		doc.value = flt(value)
	if on:
		doc.date = on
	doc.status = "Confirmed"
	doc.confirmed_by, doc.confirmed_on = frappe.session.user, now_datetime()
	doc.save()
	return doc
