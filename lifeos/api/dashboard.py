"""The Today dashboard (issue 123): four cards and two panels at the top of each Today view (Day, Week, Month, Year).

`get(view, date)` loads a whole view in one request; `list(kind, view, date)` is the list a count opens in the side pane. Every number here
is a door: the card carries `open`, the pane reference (`list:needs-you`, `goal:<name>`, ...) of what it counts. Plumbing only: numbers,
dates and counts. A sensitive item is counted and never named. With simple mode on (`Life Settings.simple_mode`, #109) a card that is about
goals is replaced by one that is not; the dashboard never shows an empty card for something switched off.
"""
import calendar as pycalendar

import frappe
from frappe import _
from frappe.query_builder import Field
from frappe.query_builder import functions as fn
from pypika.terms import Function
from frappe.utils import add_days, add_to_date, cint, flt, getdate, today

from lifeos import permissions
from lifeos.api import brain as brain_api
from lifeos.api import goals as goals_api
from lifeos.api import rules as rules_api
from lifeos.api.utils import names_map
from lifeos.brain import asks, rules as rules_engine
from lifeos.calendar import calendar_data
from lifeos.goals import cycles, habits as habit_rules, readings, year_plan

VIEWS = ("day", "week", "month", "year")
LIST_KINDS = ("needs-you", "waiting", "waiting-overdue", "waiting-due", "rules", "filed-alone", "came-in", "done", "active", "score", "coming-up", "habits",
	"week-work", "cycle", "goals-due", "key-dates", "plate", "top-three")
OPEN = ("Open", "Doing", "Waiting")
COMING_ROWS = 6
LIST_MAX = 100


class MONTH(Function):
	def __init__(self, term, alias=None):
		super().__init__("MONTH", term, alias=alias)


SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _people_only(space):
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("The dashboard is for people."), frappe.PermissionError, title=_("People only"))
	return permissions.resolve_space(space)


def simple_mode() -> bool:
	"""Areas and goals switched off (#109's switch)."""
	return bool(cint(frappe.db.get_single_value("Life Settings", "simple_mode")))


# ---- the period a view covers ----
def bounds(view, on):
	"""First and last day of the period of `view` that holds `on`: the day, the week (Monday, or Sunday by Settings), the month, the year."""
	on = getdate(on)
	if view == "day":
		return on, on
	if view == "week":
		first = add_days(on, -on.weekday())
		if frappe.db.get_single_value("Life Settings", "week_starts_on") == "Sunday":
			first = add_days(on, -((on.weekday() + 1) % 7))
		return first, add_days(first, 6)
	if view == "month":
		return on.replace(day=1), on.replace(day=pycalendar.monthrange(on.year, on.month)[1])
	return on.replace(month=1, day=1), on.replace(month=12, day=31)


def _before(view, start):
	"""The same period one step earlier."""
	if view == "year":
		return bounds("year", start.replace(year=start.year - 1))
	if view == "month":
		return bounds("month", add_days(start, -1))
	return bounds(view, add_days(start, -(1 if view == "day" else 7)))


def _dt_range(start, end):
	return f"{start} 00:00:00", f"{add_days(end, 1)} 00:00:00"


def _is_new(space) -> bool:
	"""A brand-new space: no task, no capture, no goal."""
	return not any(frappe.db.exists(d, {"space": space}) for d in ("Life Task", "Life Inbox Item", "Life Goal"))


# ---- numbers ----
def needs_you(space):
	"""Pending proposals of captures the user reads: how many and how old the oldest is."""
	i, p = frappe.qb.DocType("Life Inbox Item"), frappe.qb.DocType("Life Proposal")
	guard = brain_api.sees(space, i)
	q = (frappe.qb.get_query("Life Proposal", fields=[fn.Count("*"), fn.Min(i.received_on)], ignore_permissions=False).join(i).on(i.name == p.inbox_item)
		.where((p.status == "Pending") & (i.space == space) & (i.is_archived == 0)))
	if guard is not None:
		q = q.where(guard)
	n, oldest = q.run()[0]
	age = (getdate(today()) - getdate(oldest)).days if oldest else None
	return {"n": int(n or 0), "oldest_days": age}


def waiting(space):
	"""The waiting pile: how many, how many are past their check-by date, and how many are due today or past it."""
	t = frappe.qb.DocType("Life Task")
	now = getdate(today())
	row = (frappe.qb.get_query("Life Task", fields=[fn.Count("*"), fn.Sum(frappe.query_builder.Case().when(t.check_by < now, 1).else_(0)),
		fn.Sum(frappe.query_builder.Case().when(t.check_by <= now, 1).else_(0))], ignore_permissions=False)
		.where((t.space == space) & (t.status == "Waiting") & (t.is_archived == 0))).run()[0]
	return {"n": int(row[0] or 0), "past": int(row[1] or 0), "due": int(row[2] or 0)}


def filed_alone(space, start, end):
	"""What the Brain did with the captures of a period: `came_in`, `filed` on its own, `waiting` for the owner, `decided` by the owner, `dropped`
	and `pct`, the share filed alone of those the Brain has finished with. An item the owner changed does not count as filed alone."""
	i = frappe.qb.DocType("Life Inbox Item")
	lo, hi = _dt_range(start, end)
	where = [i.space == space, i.is_archived == 0, i.received_on >= lo, i.received_on < hi]
	if (g := brain_api.sees(space, i)) is not None:
		where.append(g)
	inner = brain_api.captures([brain_api.outcome_term(i).as_("o")], where).as_("t")
	got = dict(frappe.qb.from_(inner).select(Field("o"), fn.Count("*")).groupby(Field("o")).run())  # system: wrapped query, permissions applied inside
	n = {k: int(got.get(k, 0)) for k in ("filed", "decided", "waiting", "dropped", "failed", "working")}
	done = n["filed"] + n["decided"] + n["waiting"] + n["dropped"]
	return {**n, "came_in": sum(n.values()), "pct": round(100.0 * n["filed"] / done) if done else None}


def filed_by_month(space, year):
	"""The share filed alone for each month of a year, in one query: {month: pct}."""
	i = frappe.qb.DocType("Life Inbox Item")
	lo, hi = _dt_range(getdate(f"{year}-01-01"), getdate(f"{year}-12-31"))
	where = [i.space == space, i.is_archived == 0, i.received_on >= lo, i.received_on < hi]
	if (g := brain_api.sees(space, i)) is not None:
		where.append(g)
	inner = brain_api.captures([brain_api.outcome_term(i).as_("o"), MONTH(i.received_on).as_("m")], where).as_("t")
	by = {}
	for o, m, c in frappe.qb.from_(inner).select(Field("o"), Field("m"), fn.Count("*")).groupby(Field("o"), Field("m")).run():  # system: wrapped query, permissions applied inside
		if o in ("filed", "decided", "waiting", "dropped"):
			row = by.setdefault(int(m), [0, 0])
			row[1] += c
			row[0] += c if o == "filed" else 0
	return {m: round(100.0 * a / b) for m, (a, b) in by.items() if b}


def rules_learned(space, start, end):
	lo, hi = _dt_range(start, end)
	return frappe.get_list("Life Rule", filters={"space": space, "made_by": ("in", ("Brain", "Owner")), "learned_from": ("is", "set"), "creation": ("between", [lo, hi])},
		pluck="name", limit=LIST_MAX, order_by="creation desc")


def to_waiting(space, start, end):
	"""Tasks the Brain made from captures of the period that went to the waiting pile."""
	lo, hi = _dt_range(start, end)
	t = frappe.qb.DocType("Life Task")
	q = frappe.qb.get_query("Life Task", fields=[fn.Count("*")], ignore_permissions=False).where((t.space == space) & (fn.IfNull(t.inbox_item, "") != "")
		& (fn.IfNull(t.waiting_on, "") != "") & (t.creation >= lo) & (t.creation < hi))
	return int(q.run()[0][0] or 0)


def tasks_done(space, start, end):
	t = frappe.qb.DocType("Life Task")
	q = frappe.qb.get_query("Life Task", fields=[fn.Count("*")], ignore_permissions=False).where((t.space == space) & (t.status == "Done") & (t.completed_on >= start) & (t.completed_on <= end))
	return int(q.run()[0][0] or 0)


def done_by_month(space, year):
	t = frappe.qb.DocType("Life Task")
	rows = (frappe.qb.get_query("Life Task", fields=[MONTH(t.completed_on), fn.Count("*")], ignore_permissions=False)
		.where((t.space == space) & (t.status == "Done") & (t.completed_on >= f"{year}-01-01") & (t.completed_on <= f"{year}-12-31")).groupby(MONTH(t.completed_on)).run())
	return {int(m): int(n) for m, n in rows}


def most_active(space, start, end, limit=5):
	"""The people and companies with the most links made in the period, each with what happened ("6 emails · 2 tasks"). One query for the links,
	one for the kinds of the inbox items among them."""
	lo, hi = _dt_range(start, end)
	link = frappe.qb.DocType("Life Link")
	rows = (frappe.qb.get_query("Life Link", fields=[link.to_name, link.from_doctype, link.from_name], ignore_permissions=False)
		.where((link.space == space) & (link.to_doctype == "Life Person") & (link.creation >= lo) & (link.creation < hi)).limit(5000).run())
	if not rows:
		return []
	items = [r[2] for r in rows if r[1] == "Life Inbox Item"]
	kinds = dict(frappe.get_list("Life Inbox Item", filters={"name": ("in", items or [""])}, fields=["name", "source_type"], as_list=True)) if items else {}
	per = {}
	for person, doctype, name in rows:
		word = "tasks" if doctype == "Life Task" else "emails" if kinds.get(name) in ("Email", "Email Digest") else "notes" if doctype == "Life Note" else "items"
		bucket = per.setdefault(person, {})
		bucket[word] = bucket.get(word, 0) + 1
	top = sorted(per.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:limit]
	names = names_map("Life Person", [p for p, _w in top], "full_name")
	return [{"person": p, "title": names.get(p) or p, "n": sum(w.values()), "what": " · ".join(f"{n} {word if n != 1 else word.rstrip('s')}" for word, n in sorted(w.items(), key=lambda kv: (-kv[1], kv[0])))}
		for p, w in top]


def habits_today(space, on):
	"""The habits with whether each is done on `on`; empty when there are none."""
	month = habit_rules.habits_month(space, on.year, on.month)
	return [{"habit": h["habit"], "title": h["title"], "done": on.day in h["done_days"]} for h in month["habits"] if not h["removed"]]


# ---- the cycle: scores, goals ----
def active_cycle(space):
	return frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "title", "start_date", "end_date"], as_dict=True)


def cycle_weeks(cycle):
	"""[(week number, monday, score)] for each week of the cycle up to this week."""
	actions, ticks = cycles._actions(cycle.name), cycles._ticks(cycle.name)
	upto = cycles.week_of(cycle)
	out = []
	for w in range(1, min(upto, cycles.WEEKS) + 1):
		s = cycles.week_score(cycle, w, actions, ticks)
		out.append({"week": w, "start": str(cycles.week_dates(cycle, w)[0]), "score": s["percent"] if s["planned"] else None, "done": s["done"], "planned": s["planned"]})
	return out


def goal_rows(space, now, horizon_filter=None, limit=60):
	"""Each active goal as a bar: percent, and `behind` when it is behind its time and its date is close."""
	filters = {"space": space, "is_archived": 0, "is_someday": 0, "outcome": "In Progress"}
	rows = frappe.get_list("Life Goal", filters=filters, fields=["name", "title", "area", "horizon", "cycle", "target_date", "creation", "measure_kind", "start_value", "target_value",
		"current_value", "current_on", "unit", "measure"], order_by="sort_order asc, creation asc", limit=limit)
	counts = goals_api.task_counts([r.name for r in rows])
	cyc = {c.name: c for c in frappe.get_list("Life Cycle", filters={"space": space}, fields=["name", "start_date", "end_date", "status"], limit=200)}
	ticks_of = {}
	for r in rows:
		cycle = cyc.get(r.cycle) if r.horizon == "12 weeks" else None
		done, n = counts.get(r.name, (0, 0))
		percent = None
		if cycle:
			if cycle.name not in ticks_of:
				ticks_of[cycle.name] = (cycles._actions(cycle.name), cycles._ticks(cycle.name))
			actions, ticks = ticks_of[cycle.name]
			percent = cycles.goal_percent(cycle, [a for a in actions if a.goal == r.name], ticks)
		elif r.measure_kind == "Number" and r.target_value is not None:
			percent = readings.summary(r).get("percent")
		elif n:
			percent = round(100.0 * done / n, 1)
		first = getdate(cycle.start_date) if cycle else getdate(r.creation)
		last = getdate(cycle.end_date) if cycle else (getdate(r.target_date) if r.target_date else None)
		r["percent"] = None if percent is None else round(flt(percent))
		r["days_left"] = (last - now).days if last else None
		expected = 100.0 * (now - first).days / max((last - first).days, 1) if last and last > first else None
		r["behind"] = bool(percent is not None and expected is not None and r["days_left"] is not None and r["days_left"] <= 21 and flt(percent) < expected - 10)
		r["date"] = str(last) if last else None
	return rows


# ---- cards and panels ----
def card(key, label, value=None, sub=None, open=None, tone=None, empty=None, parts=None, **extra):
	"""One card. `value` is the number as shown; `open` the pane reference it leads to; `empty` is shown instead of the number when there is
	nothing to count: {line, action?, to?}. `parts` are extra doors inside the card: [{text, open, tone}]."""
	return {"key": key, "label": label, "value": value, "sub": sub, "open": open, "tone": tone, "empty": empty, "parts": parts or [], **extra}


def row(title, sub=None, ref=None, **extra):
	return {"title": title, "sub": sub, "ref": ref, **extra}


def panel(key, title, rows, empty=None, more=None, kind="rows", **extra):
	return {"key": key, "title": title, "rows": rows, "empty": empty, "more": more, "kind": kind, **extra}


def _line(new, line, action=None, to=None):
	"""The empty state of a card: what will appear there, and (for a brand-new user) the one action that fills it."""
	return {"line": line, "action": action if new else None, "to": to if new else None}


def needs_card(space, new):
	n = needs_you(space)
	return card("needs", _("Needs you"), n["n"], _("oldest {0} d").format(n["oldest_days"]) if n["oldest_days"] else None, "list:needs-you" if n["n"] else None,
		empty=None if n["n"] else _line(new, _("Nothing needs you. Things you capture or connect will show up here."), _("Connect"), "/settings?tab=sources"))


def waiting_card(space, new, label=None):
	w = waiting(space)
	parts = [{"text": _("{0} past check date").format(w["past"]), "open": "list:waiting-overdue", "tone": "warn"}] if w["past"] else []
	return card("waiting", label or _("Waiting on others"), w["n"], None if w["past"] else (_("on someone else") if w["n"] else None), "list:waiting" if w["n"] else None, parts=parts,
		empty=None if w["n"] else _line(new, _("Things you wait on others for will show up here."), _("Chat"), "chat"))


def filed_card(space, new, view, start, end):
	"""Brain filed alone: this period's share, compared with the month before (Week and Month) or as a trend through the year (Year)."""
	f = filed_alone(space, start, end)
	empty = _line(new, _("Connect a source and the Brain starts filing."), _("Connect"), "/settings?tab=sources")
	if view == "year":
		by = filed_by_month(space, start.year)
		months = sorted(by)
		trend = f"{by[months[0]]}% → {by[months[-1]]}%, {SHORT[months[0] - 1]} to {SHORT[months[-1] - 1]}" if len(months) > 1 else None
		return card("filed", _("Brain filed alone"), None if f["pct"] is None else f"{f['pct']}%", trend or (_("filed alone") if f["pct"] is not None else None),
			"list:filed-alone" if f["filed"] else None, empty=None if f["pct"] is not None else empty)
	prev = filed_alone(space, *(bounds("month", add_days(start.replace(day=1), -1)) if view in ("week", "month") else _before(view, start)))
	sub = _("{0} of {1} done").format(f["filed"], f["came_in"] - f["working"] - f["failed"]) if f["pct"] is not None else None
	if f["pct"] is not None and prev["pct"] is not None:
		last = add_days(start.replace(day=1), -1) if view in ("week", "month") else None
		word = _("up from") if f["pct"] > prev["pct"] else _("down from") if f["pct"] < prev["pct"] else _("same as")
		sub = f"{word} {prev['pct']}% in {SHORT[last.month - 1] if last else _('the period before')}"
	return card("filed", _("Brain filed alone"), None if f["pct"] is None else f"{f['pct']}%", sub, "list:filed-alone" if f["filed"] else None,
		empty=None if f["pct"] is not None else empty)


def done_card(space, new, view, start, end):
	n = tasks_done(space, start, end)
	pstart, pend = _before(view, start)
	last = tasks_done(space, pstart, pend)
	word = {"week": _("this week"), "month": _("this month"), "year": _("this year"), "day": _("today")}[view]
	return card("done", _("Done {0}").format(word), n, {"week": _("last week {0}"), "month": _("last month {0}"), "year": _("last year {0}"), "day": _("yesterday {0}")}[view].format(last),
		"list:done" if n else None, empty=None if n else _line(new, _("Tasks you finish will show up here."), _("Chat"), "chat"))


def active_card(space, view, start, end):
	people = most_active(space, start, end)
	word = {"week": _("week"), "month": _("month"), "year": _("year"), "day": _("day")}[view]
	return card("active", _("Most active this {0}").format(word), people[0]["title"] if people else None, people[0]["what"] if people else None, "list:active" if people else None,
		empty=None if people else _line(False, _("The people and companies you hear from most will show up here.")))


def habits_card(space, new, on):
	habits = habits_today(space, on)
	done = sum(1 for h in habits if h["done"])
	return card("habits", _("Habits"), f"{done} of {len(habits)}" if habits else None, _("done today") if habits else None, "list:habits" if habits else None,
		empty=None if habits else _line(new, _("A habit you track shows here, ticked each day."), _("Set a habit"), "/goals/habits"))


def brain_line(space, start, end):
	f = filed_alone(space, start, end)
	n_rules = len(rules_learned(space, start, end))
	parts = [{"text": _("{0} came in").format(f["came_in"]), "open": "list:came-in"}, {"text": _("{0} filed alone").format(f["filed"]), "open": "list:filed-alone"},
		{"text": _("{0} to waiting").format(to_waiting(space, start, end)), "open": "list:waiting"}, {"text": _("{0} to you").format(f["waiting"]), "open": "list:needs-you"},
		{"text": _("{0} rules learned").format(n_rules), "open": "list:rules"}]
	return {"parts": parts, "numbers": {"came_in": f["came_in"], "filed": f["filed"], "to_waiting": to_waiting(space, start, end), "to_you": f["waiting"], "rules": n_rules}}


def goals_panel(space, now, new):
	rows = goal_rows(space, now)
	areas = names_map("Life Area", [r.area for r in rows if r.area], "area_name")
	by = {}
	for r in rows:
		by.setdefault(r.area, []).append(row(r.title, _("{0}% · by {1}").format(r.percent, r.date) if r.percent is not None and r.date else (f"{r.percent}%" if r.percent is not None else r.date),
			f"goal:{r.name}", percent=r.percent, tone="warn" if r.behind else None))
	groups = [{"area": areas.get(a) or _("No area"), "rows": rs} for a, rs in by.items()]
	return panel("goals", _("Goals by area"), [], groups=groups, kind="goals",
		empty=None if groups else _line(new, _("Your goals show here, grouped by area, each as a bar."), _("Set a goal"), "/goals?new=goal"))


def coming_up(space, now, limit=COMING_ROWS):
	"""The next seven days: events, key dates, tasks due and expiring documents, in date order."""
	end = add_days(now, 6)
	out = []
	for e in calendar_data.events_between(space, now, end):
		out.append((e["date"], e["start"] or "", row(e["title"], str(e["date"]), f"event:{e['name']}")))
	for d in calendar_data.important_dates_between(space, now, end):
		out.append((d["date"], "", row(d["label"], str(d["date"]), f"date:{d['name']}")))
	for d in calendar_data.vault_expiries_between(space, now, end):
		out.append((d["date"], "", row(d["title"], str(d["date"]), f"vault:{d['name']}")))
	t = frappe.qb.DocType("Life Task")
	for name, title, due in (frappe.qb.get_query("Life Task", fields=[t.name, t.title, t.due_date], ignore_permissions=False)
			.where((t.space == space) & t.status.isin(OPEN) & (t.is_archived == 0) & (t.due_date >= now) & (t.due_date <= end)).orderby(t.due_date).limit(40).run()):
		out.append((str(due), "", row(title, str(due), f"task:{name}")))
	out.sort(key=lambda x: (str(x[0]), x[1]))
	rows = [r for _d, _s, r in out]
	for r in rows:
		r["sub"] = _short(r["sub"])
	return rows[:limit], max(len(rows) - limit, 0)


def _short(d):
	d = getdate(d)
	return f"{d.day} {SHORT[d.month - 1]}"


def coming_panel(space, now, new):
	rows, more = coming_up(space, now)
	return panel("coming", _("Coming up"), rows, more=more and {"n": more, "open": "list:coming-up"}, empty=_line(new, _("Meetings, due dates and key dates of the next seven days show here."), _("Chat"), "chat"))


def key_dates_panel(space, start, end, new):
	rows = [row(k["title"], _short(k["date"]), k["ref"]) for k in year_plan.key_dates(space, start, end)]
	return panel("key-dates", _("Key dates"), rows[:LIST_MAX], empty=_line(new, _("Birthdays, trips and expiries you add show here."), _("Add a key date"), "/today/month"))


# ---- the four views ----
def _day(space, on, new, simple):
	now = getdate(today())
	cards, panels = [], []
	events = calendar_data.events_between(space, on, add_days(on, 1))
	events.sort(key=lambda e: e["start"] or "")
	sched = [row(e["title"], "All day" if e.get("all_day") else str(e["start"])[11:16], f"event:{e['name']}", at=str(e["start"])[11:16] if not e.get("all_day") else "") for e in events]
	t = frappe.qb.DocType("Life Task")
	if simple:
		due = (frappe.qb.get_query("Life Task", fields=[t.name, t.title, t.due_date], ignore_permissions=False)
			.where((t.space == space) & t.status.isin(OPEN) & (t.is_archived == 0) & (t.due_date <= on)).orderby(t.due_date).limit(LIST_MAX).run())
		cards.append(card("plate", _("Your plate today"), len(due), _("{0} overdue").format(sum(1 for _n, _t, d in due if d < on)) if any(d < on for _n, _t, d in due) else None, "list:plate" if due else None,
			empty=_line(new, _("Tasks due today show here."), _("Chat"), "chat")))
		plate_panel = panel("plate", _("Your plate"), [row(title, _short(d), f"task:{n}", tone="warn" if d < on else None) for n, title, d in due[:8]], more=len(due) > 8 and {"n": len(due) - 8, "open": "list:plate"},
			empty=_line(new, _("Tasks due today show here."), _("Chat"), "chat"))
	else:
		week_start = bounds("week", on)[0]
		top = frappe.get_list("Life Task", filters={"space": space, "is_top_three": 1, "top_three_week": week_start, "is_archived": 0}, fields=["name", "title", "status"], order_by="creation asc", limit=3)
		done = sum(1 for r in top if r.status == "Done")
		cards.append(card("top", _("Top three"), f"{done} of 3" if top else None, _("done this week") if top else None, "list:top-three" if top else None,
			empty=_line(new, _("Your three most important tasks of the week show here."), _("Chat"), "chat")))
		plate_panel = panel("top", _("Top three"), [row(r.title, _("Done") if r.status == "Done" else None, f"task:{r.name}", done=r.status == "Done") for r in top],
			empty=_line(new, _("The weekly review sets your top three."), _("Chat"), "chat"))
	cards.append(needs_card(space, new))
	w = waiting(space)
	cards.append(card("check", _("Check today"), w["due"], _("waiting items to chase") if w["due"] else None, "list:waiting-due" if w["due"] else None,
		empty=_line(new, _("Waiting items whose check date has come show here."), _("Chat"), "chat")))
	habits = habits_today(space, on)
	if habits or not simple:
		cards.append(habits_card(space, new, on))
	panels.append(panel("schedule", _("Schedule"), sched, now_line=str(now) == str(on), empty=_line(new, _("Meetings and time blocks of the day show here."), _("Connect"), "/settings?tab=sources")))
	panels.append(plate_panel)
	return cards, panels, None


def _week(space, on, new, simple):
	start, end = bounds("week", on)
	now = getdate(today())
	cards, panels = [], []
	if simple:
		cards.append(done_card(space, new, "week", start, end))
	else:
		cycle = active_cycle(space)
		score = prev = None
		target = cint(frappe.db.get_single_value("Life Settings", "score_target")) or 85
		if cycle:
			wk = cycles.week_of(cycle, start)
			if 1 <= wk <= cycles.WEEKS:
				score = cycles.week_score(cycle, wk)
				prev = cycles.week_score(cycle, wk - 1)["percent"] if wk > 1 else None
		if score and score["planned"]:
			sub = _("target {0}%").format(target) + (" · " + _("last week {0}%").format(round(prev)) if prev is not None else "")
			cards.append(card("score", _("Week score"), f"{round(score['percent'])}%", sub, "list:score", tone=None if score["percent"] >= target else "warn"))
		else:
			cards.append(card("score", _("Week score"), None, empty=_line(new or not cycle, _("Your week score appears once you have a 12-week goal."), _("Set a goal"), "/goals?new=goal")))
	cards.append(needs_card(space, new))
	cards.append(waiting_card(space, new))
	cards.append(filed_card(space, new, "week", start, end))
	if simple:
		people = most_active(space, start, end)
		panels.append(panel("active", _("Most active this week"), [row(p["title"], p["what"], f"person:{p['person']}") for p in people], empty=_line(False, _("The people and companies you hear from most show here."))))
	else:
		panels.append(goals_panel(space, now, new))
	coming = coming_panel(space, now, new)
	habits = habits_today(space, now)
	coming["habits"] = habits if (habits or not simple) else []
	coming["habits_empty"] = None if habits or simple else _line(new, _("A habit you track shows here, ticked each day."), _("Set a habit"), "/goals/habits")
	panels.append(coming)
	return cards, panels, brain_line(space, start, end)


def _month(space, on, new, simple):
	start, end = bounds("month", on)
	cards, panels = [], []
	cycle = active_cycle(space)
	weeks = []
	first_week = bounds("week", start)[0]
	scores = {}
	if cycle and not simple:
		scores = {w["start"]: w for w in cycle_weeks(cycle)}
	day = first_week
	while day <= end:
		weeks.append(day)
		day = add_days(day, 7)
	if simple:
		cards.append(done_card(space, new, "month", start, end))
		cards.append(active_card(space, "month", start, end))
		keys = year_plan.key_dates(space, start, end)
		cards.append(card("keys", _("Key dates due"), len(keys), None, "list:key-dates" if keys else None, empty=_line(new, _("Birthdays, trips and expiries you add show here."), _("Add a key date"), "/today/month")))
	else:
		in_month = [scores[str(w)]["score"] for w in weeks if str(w) in scores and scores[str(w)]["score"] is not None]
		avg = round(sum(in_month) / len(in_month)) if in_month else None
		cards.append(card("score", _("Month score"), None if avg is None else f"{avg}%", _("average of {0} weeks").format(len(in_month)) if in_month else None,
			"list:score" if in_month else None, empty=None if in_month else _line(new or not cycle, _("Your month score appears once you have a 12-week goal."), _("Set a goal"), "/goals?new=goal")))
		mg = cycles.month_goals(space, start.year, start.month)
		met = sum(1 for g in mg if g["status"] == "Done")
		cards.append(card("plan", _("Month plan"), f"{met} of {len(mg)}" if mg else None, _("outcomes met") if mg else None, "list:goals-due" if mg else None,
			empty=_line(new or not mg, _("Your month's outcomes show here once you plan the month."), _("Plan the month"), "/goals/cycles")))
		due = frappe.get_list("Life Goal", filters={"space": space, "is_archived": 0, "outcome": "In Progress", "target_date": ("between", [start, end])}, fields=["name", "target_date"], limit=LIST_MAX)
		behind = sum(1 for g in due if getdate(g.target_date) < getdate(today()))
		cards.append(card("due", _("Goals due this month"), len(due), _("{0} behind").format(behind) if behind else None, "list:goals-due" if due else None, tone="warn" if behind else None,
			empty=_line(new, _("Goals with a date this month show here."), _("Set a goal"), "/goals?new=goal")))
	cards.append(filed_card(space, new, "month", start, end))
	rows = []
	for w in weeks:
		s = scores.get(str(w))
		if simple:
			n = tasks_done(space, w, add_days(w, 6))
			rows.append(row(_("Week of {0}").format(_short(w)), _("{0} done").format(n), f"list:week-work:{w}", accent=w <= getdate(today()) <= add_days(w, 6)))
		else:
			rows.append(row(_("Week of {0}").format(_short(w)), f"{round(s['score'])}%" if s and s["score"] is not None else None, f"list:week-work:{w}", percent=s["score"] if s else None,
				accent=w <= getdate(today()) <= add_days(w, 6)))
	panels.append(panel("weeks", _("Weeks of the month"), rows, kind="weeks" if not simple else "rows"))
	panels.append(key_dates_panel(space, start, add_days(end, 7), new))
	return cards, panels, None


def _year(space, on, new, simple):
	start, end = bounds("year", on)
	cards, panels = [], []
	locked = year_plan.reviews_since_setup(space, start, end, getdate(today()))
	reviews = card("reviews", _("Reviews locked"), f"{locked['done']} of {locked['total']}" if locked["done"] else None, _("weeks so far") if locked["done"] else None,
		empty=None if locked["done"] else _line(new, _("Each weekly review you lock counts here."), _("Chat"), "chat"))
	by_month = filed_by_month(space, start.year)
	if simple:
		cards += [done_card(space, new, "year", start, end), reviews, needs_card(space, new), filed_card(space, new, "year", start, end)]
		people = most_active(space, start, end, 8)
		panels.append(panel("active", _("Most active this year"), [row(p["title"], p["what"], f"person:{p['person']}") for p in people], empty=_line(False, _("The people and companies you hear from most show here."))))
		panels.append(panel("filed-months", _("Brain filed alone, by month"), [row(LONG[m - 1], f"{by_month[m]}%", None, percent=by_month[m]) for m in sorted(by_month)],
			kind="months", empty=_line(new, _("Connect a source and the Brain starts filing."), _("Connect"), "/settings?tab=sources")))
		return cards, panels, None
	goals = frappe.get_list("Life Goal", filters={"space": space, "is_archived": 0, "horizon": "Year", "target_date": ("between", [start, end])}, fields=["name", "outcome", "title", "area"], limit=LIST_MAX)
	met = sum(1 for g in goals if g.outcome == "Achieved")
	cards.append(card("year-goals", _("Year goals met"), f"{met} of {len(goals)}" if goals else None, _("achieved") if goals else None, "list:goals-due" if goals else None,
		empty=_line(new or not goals, _("Your year goals show here once you set one."), _("Set a goal"), "/goals?new=goal")))
	cycle = active_cycle(space)
	wk = cycles.week_of(cycle) if cycle else 0
	if cycle and 1 <= wk <= cycles.WEEKS:
		avg = cycles.cycle_average(cycle, cycles._actions(cycle.name), cycles._ticks(cycle.name), wk)
		cards.append(card("cycle", _("This cycle's score"), f"{round(avg)}%", _("week {0} of {1}").format(wk, cycles.WEEKS), f"list:cycle:{cycle.name}"))
	else:
		cards.append(card("cycle", _("This cycle's score"), None, empty=_line(new or not cycle, _("Your cycle score appears once a 12 Week Year is running."), _("Set a goal"), "/goals?new=goal")))
	cards += [reviews, filed_card(space, new, "year", start, end)]
	panels.append(goals_panel(space, getdate(today()), new))
	all_cycles = frappe.get_list("Life Cycle", filters={"space": space, "start_date": ("<=", end), "end_date": (">=", start)}, fields=["name", "title", "status", "final_score", "start_date", "end_date"], order_by="start_date asc", limit=12)
	rows = []
	for c in all_cycles:
		score = c.final_score
		if score is None and c.status == "Active":
			w = cycles.week_of(c)
			score = cycles.cycle_average(c, cycles._actions(c.name), cycles._ticks(c.name), min(max(w, 1), cycles.WEEKS))
		rows.append(row(c.title, f"{round(score)}%" if score is not None else None, f"list:cycle:{c.name}", percent=score, accent=c.status == "Active"))
	panels.append(panel("cycles", _("Cycles"), rows, kind="cycles", empty=_line(new, _("Each 12 Week Year and its score show here."), _("Set a goal"), "/goals?new=goal")))
	return cards, panels, None


@frappe.whitelist(methods=["GET"])
def get(view: str = "week", date: str | None = None, space: str | None = None):
	"""One Today view's dashboard: `cards` (four), `panels` (two), and for Week `brain_line`. `simple` says goals are switched off."""
	space = _people_only(space)
	view = view if view in VIEWS else "week"
	on = getdate(date or today())
	simple, new = simple_mode(), _is_new(space)
	cards, panels, line = {"day": _day, "week": _week, "month": _month, "year": _year}[view](space, on, new, simple)
	start, end = bounds(view, on)
	return {"view": view, "date": str(on), "start": str(start), "end": str(end), "simple": simple, "new": new, "cards": cards, "panels": panels, "brain_line": line}


# ---- the lists a count opens ----
def _task_rows(rows, sub=None):
	return [row(r.title, sub(r) if sub else None, f"task:{r.name}", done=r.status == "Done") for r in rows]


def _masked(title, sensitive):
	return _("A sensitive item") if sensitive else title


@frappe.whitelist(methods=["GET"])
def list(kind: str, view: str = "week", date: str | None = None, space: str | None = None):
	"""What a number counts: `{title, rows}`. Each row has `ref` (the record it opens in the pane) and the list is in the order the screen shows.
	The period is the view's, around `date`. `kind` may carry an argument after a colon (`week-work:2026-11-23`, `cycle:<name>`)."""
	space = _people_only(space)
	base, _s, arg = str(kind).partition(":")
	if base not in LIST_KINDS:
		frappe.throw(_("There is no list called {0}.").format(base), title=_("Unknown list"))
	view = view if view in VIEWS else "week"
	on = getdate(date or today())
	start, end = bounds(view, on)
	now = getdate(today())
	out = {"needs-you": lambda: _l_needs(space), "waiting": lambda: _l_waiting(space, "all"), "waiting-overdue": lambda: _l_waiting(space, "past"), "waiting-due": lambda: _l_waiting(space, "due"),
		"rules": lambda: _l_rules(space, start, end), "filed-alone": lambda: _l_items(space, start, end, "filed"), "came-in": lambda: _l_items(space, start, end, None),
		"done": lambda: _l_done(space, start, end), "active": lambda: _l_active(space, start, end), "score": lambda: _l_score(space, start, view), "coming-up": lambda: _l_coming(space, now),
		"habits": lambda: _l_habits(space, on if view == "day" else now), "week-work": lambda: _l_week_work(space, getdate(arg or start)), "cycle": lambda: _l_cycle(arg),
		"goals-due": lambda: _l_goals_due(space, start, end), "key-dates": lambda: _l_keys(space, start, end), "plate": lambda: _l_plate(space, on), "top-three": lambda: _l_top(space, on)}[base]()
	return {"kind": kind, "view": view, "start": str(start), "end": str(end), **out}


def _l_needs(space):
	rows = brain_api.needs_you(space, limit=50)["rows"]
	return {"title": _("Needs you"), "rows": [row(_masked(r["title"], False), r["kind_label"], f"inbox:{r['item']}", proposal=r["proposal"]) for r in rows]}


def _l_waiting(space, which):
	now = getdate(today())
	rows = asks.waiting_rows(space)
	rows = [r for r in rows if which == "all" or (which == "past" and r["past"]) or (which == "due" and r["check_by"] and getdate(r["check_by"]) <= now)]
	title = {"all": _("Waiting on others"), "past": _("Past their check date"), "due": _("Check today")}[which]
	return {"title": title, "rows": [row(r["title"], _("{0} · check by {1}").format(r["who"], _short(r["check_by"])) if r["check_by"] else r["who"], f"task:{r['name']}", tone="warn" if r["past"] else None) for r in rows]}


def _l_rules(space, start, end):
	names = rules_learned(space, start, end)
	return {"title": _("Rules learned"), "rules": [rules_api.card(frappe.get_doc("Life Rule", n)) for n in names], "rows": []}


def _l_items(space, start, end, outcome):
	i = frappe.qb.DocType("Life Inbox Item")
	lo, hi = _dt_range(start, end)
	where = [i.space == space, i.is_archived == 0, i.received_on >= lo, i.received_on < hi]
	if (g := brain_api.sees(space, i)) is not None:
		where.append(g)
	inner = brain_api.captures([i.name.as_("item"), i.title, i.source_type, i.received_on, i.is_sensitive, brain_api.outcome_term(i).as_("o")], where).as_("t")
	q = frappe.qb.from_(inner).select(inner.star)
	if outcome:
		q = q.where(Field("o") == outcome)
	rows = q.orderby(Field("received_on"), order=frappe.query_builder.Order.desc).limit(LIST_MAX).run(as_dict=True)  # system: wrapped query, permissions applied inside
	return {"title": _("Filed alone") if outcome else _("Came in"), "rows": [row(_masked(r.title, r.is_sensitive), f"{r.source_type} · {str(r.received_on)[:16]}", f"inbox:{r.item}") for r in rows]}


def _l_done(space, start, end):
	rows = frappe.get_list("Life Task", filters={"space": space, "status": "Done", "completed_on": ("between", [start, end])}, fields=["name", "title", "status", "completed_on"], order_by="completed_on desc", limit=LIST_MAX)
	return {"title": _("Done"), "rows": _task_rows(rows, lambda r: _short(r.completed_on))}


def _l_active(space, start, end):
	return {"title": _("Most active"), "rows": [row(p["title"], p["what"], f"person:{p['person']}") for p in most_active(space, start, end, 20)]}


def _l_score(space, start, view):
	cycle = active_cycle(space)
	if not cycle:
		return {"title": _("Score"), "rows": []}
	wk = min(max(cycles.week_of(cycle, start), 1), cycles.WEEKS)
	ticks = cycles._ticks(cycle.name)
	rows = []
	for a in cycles._actions(cycle.name):
		p = cycles.planned_in_week(cycle, a, wk)
		if p:
			rows.append(row(a.title, _("{0} of {1} this week").format(min(ticks.get(a.name, {}).get(wk, 0), p), p), f"goal:{a.goal}"))
	return {"title": _("Week {0} score").format(wk), "rows": rows}


def _l_coming(space, now):
	rows, _m = coming_up(space, now, limit=200)
	return {"title": _("Coming up"), "rows": rows}


def _l_habits(space, on):
	return {"title": _("Habits"), "habits": habits_today(space, on), "date": str(on), "rows": []}


def _l_week_work(space, monday):
	end = add_days(monday, 6)
	planned = frappe.get_list("Life Task", filters={"space": space, "status": ("in", (*OPEN, "Done")), "due_date": ("between", [monday, end])}, fields=["name", "title", "status", "due_date"], order_by="due_date asc", limit=LIST_MAX)
	done = frappe.get_list("Life Task", filters={"space": space, "status": "Done", "completed_on": ("between", [monday, end]), "name": ("not in", [r.name for r in planned] or [""])}, fields=["name", "title", "status", "completed_on"], limit=LIST_MAX)
	return {"title": _("Week of {0}").format(_short(monday)), "rows": [*_task_rows(planned, lambda r: _("Done") if r.status == "Done" else _("planned {0}").format(_short(r.due_date))), *_task_rows(done, lambda r: _("done {0}").format(_short(r.completed_on)))]}


def _l_cycle(name):
	cycle = permissions.get_doc_checked("Life Cycle", name, "read")
	wk = min(max(cycles.week_of(cycle), 1), cycles.WEEKS)
	actions, ticks = cycles._actions(cycle.name), cycles._ticks(cycle.name)
	goals = frappe.get_list("Life Goal", filters={"cycle": cycle.name, "is_archived": 0}, fields=["name", "title", "final_score"], order_by="sort_order asc, creation asc", limit=LIST_MAX)
	rows = []
	for g in goals:
		pct = g.final_score if g.final_score is not None else cycles.goal_percent(cycle, [a for a in actions if a.goal == g.name], ticks, wk)
		rows.append(row(g.title, f"{round(pct)}%", f"goal:{g.name}", percent=pct))
	return {"title": cycle.title, "rows": rows}


def _l_goals_due(space, start, end):
	rows = frappe.get_list("Life Goal", filters={"space": space, "is_archived": 0, "target_date": ("between", [start, end])}, fields=["name", "title", "target_date", "outcome"], order_by="target_date asc", limit=LIST_MAX)
	return {"title": _("Goals due"), "rows": [row(r.title, f"{_short(r.target_date)} · {r.outcome}", f"goal:{r.name}") for r in rows]}


def _l_keys(space, start, end):
	return {"title": _("Key dates"), "rows": [row(k["title"], _short(k["date"]), k["ref"]) for k in year_plan.key_dates(space, start, end)]}


def _l_plate(space, on):
	t = frappe.qb.DocType("Life Task")
	rows = (frappe.qb.get_query("Life Task", fields=[t.name, t.title, t.due_date], ignore_permissions=False)
		.where((t.space == space) & t.status.isin(OPEN) & (t.is_archived == 0) & (t.due_date <= on)).orderby(t.due_date).limit(LIST_MAX).run())
	return {"title": _("Your plate today"), "rows": [row(title, _short(d), f"task:{n}", tone="warn" if d < on else None) for n, title, d in rows]}


def _l_top(space, on):
	rows = frappe.get_list("Life Task", filters={"space": space, "is_top_three": 1, "top_three_week": bounds("week", on)[0], "is_archived": 0}, fields=["name", "title", "status"], order_by="creation asc", limit=3)
	return {"title": _("Top three"), "rows": _task_rows(rows)}
