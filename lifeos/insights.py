"""Insights (UX fixes, set 5): findings that push stuck things to a decision.

Rule detectors run first (Stuck, Waiting on you, 12 Week Year, Habit, Check-in, Someday); the notice skill
adds Waiting on you, Promise and Theme candidates when a key is set. Every insight carries its
evidence; its fingerprint is the kind plus the sorted evidence, so a dismissed one is not shown again unless the
evidence changes. Snoozed ones come back after their date. At most 12 new insights a day per space, ranked by kind.
"""
import hashlib
import json

import frappe
from frappe.utils import add_days, add_months, cint, getdate, now_datetime, today

from lifeos import counts, journal

KINDS = ["Stuck", "Waiting on you", "Promise", "12 Week Year", "Habit", "Check-in", "Theme", "Someday"]
RANK = {k: i for i, k in enumerate(KINDS)}
ACTIONABLE = ("Stuck", "Waiting on you", "Promise", "Someday")
MAX_NEW_PER_DAY = 12
STUCK_GROUP_MIN = 3  # a group of stuck tasks smaller than this is not worth an insight of its own
HABIT_MARGIN = 20  # percentage points a habit's rate must fall, this month against last
LOW_SCORE = 5  # a check-in dimension at or below this, three times in a row, is low
WAITING_DAYS = 3  # a chat open item still open after this many days is someone waiting


def fingerprint(kind, evidence):
	keys = sorted(f"{e['ref_doctype']}:{e['ref_name']}" for e in evidence)
	return hashlib.sha1((kind + "|" + "|".join(keys)).encode()).hexdigest()[:40]


def candidate(kind, title, evidence, body="", actions=None, area=None, source="Rule", source_line=None):
	return {"kind": kind, "title": title[:255], "body": body, "evidence": evidence, "actions": actions or [], "area": area,
		"source": source, "source_line": source_line}


def ev(doctype, name, label=""):
	return {"ref_doctype": doctype, "ref_name": name, "label": (label or "")[:140]}


# ---- rule detectors ----

def detect_stuck(space):
	"""Open tasks untouched past the stuck threshold, grouped by goal (or area); idle open-ended goals; old inbox items."""
	r = counts.rules()
	days = r["stuck_after_days"]
	cutoff = add_days(today(), -days)
	rows = frappe.db.sql("""select t.name, t.title, t.area, t.goal, ifnull(t.last_touched_on, date(t.creation)) as touched
		from `tabLife Task` t where t.space=%s and t.status in ('Open', 'Doing', 'Waiting') and t.is_archived=0
		and ifnull(t.last_touched_on, date(t.creation)) <= %s order by touched""", (space, cutoff), as_dict=True)
	groups = {}
	for t in rows:
		key = ("Life Goal", t.goal) if t.goal else ("Life Area", t.area or "")
		groups.setdefault(key, []).append(t)
	out = []
	for (dt, name), items in groups.items():
		if len(items) < STUCK_GROUP_MIN:
			continue
		label = (frappe.db.get_value(dt, name, "title" if dt == "Life Goal" else "area_name") if name else None) or "Unfiled"
		oldest = min(getdate(i.touched) for i in items)
		names = [i.name for i in items]
		area = items[0].area if dt == "Life Area" else frappe.db.get_value("Life Goal", name, "area") if name else None
		out.append(candidate("Stuck", f"{len(items)} {label} tasks have not moved in {days} days",
			[ev("Life Task", i.name, i.title) for i in items[:200]], body=f"The oldest has not changed since {oldest.strftime('%-d %b %Y')}.",
			actions=[{"kind": "open_reset", "label": "Open in Reset", "names": names}, {"kind": "move_someday", "label": "Move all to Someday",
				"items": [{"doctype": "Life Task", "name": n} for n in names]}], area=area))
	idle = frappe.db.sql("""select name, title, area from `tabLife Goal` where space=%s and horizon='Long term' and outcome='In Progress'
		and on_hold=0 and is_someday=0 and is_archived=0 and ifnull(last_activity_on, date(modified)) <= %s""", (space, cutoff), as_dict=True)
	for p in idle:
		out.append(candidate("Stuck", f"The goal {p.title} has had no activity for {days} days", [ev("Life Goal", p.name, p.title)],
			actions=[{"kind": "open_record", "label": "Open goal", "ref": "goal:" + p.name},
				{"kind": "move_someday", "label": "Move to Someday", "items": [{"doctype": "Life Goal", "name": p.name}]}], area=p.area))
	old_inbox = frappe.db.sql("""select name, title from `tabLife Inbox Item` where space=%s and status='To Review' and is_archived=0
		and received_on < %s order by received_on""", (space, add_days(today(), -7)), as_dict=True)
	if len(old_inbox) >= STUCK_GROUP_MIN:
		out.append(candidate("Stuck", f"{len(old_inbox)} inbox items have waited more than a week for review",
			[ev("Life Inbox Item", i.name, i.title) for i in old_inbox[:200]], actions=[{"kind": "open_list", "label": "Open the Inbox",
				"to": counts.inbox_old(space)["to"]}]))
	return out


def detect_waiting(space):
	"""Chat open items still open after a few days: someone is waiting on the owner."""
	rows = frappe.db.sql("""select c.name as chat, c.title as chat_title, c.area, c.date, o.name as row, o.text
		from `tabLife Chat Open Item` o join `tabLife Chat Log` c on c.name = o.parent
		where c.space=%s and o.status='Open' and c.is_archived=0 and c.date <= %s order by c.date""", (space, add_days(today(), -WAITING_DAYS)), as_dict=True)
	by_chat = {}
	for r in rows:
		by_chat.setdefault(r.chat, []).append(r)
	out = []
	for chat, items in by_chat.items():
		c = items[0]
		days = (getdate(today()) - getdate(c.date)).days
		title = (f"“{items[0].text[:90]}” has waited {days} days" if len(items) == 1
			else f"{len(items)} open items from the chat {c.chat_title} have waited {days} days")
		out.append(candidate("Waiting on you", title, [ev("Life Chat Log", chat, c.chat_title)],
			body="; ".join(i.text for i in items[:5]),
			actions=[{"kind": "make_task", "label": "Make task", "title": items[0].text[:140], "area": c.area, "chat": chat, "row": items[0].row},
				{"kind": "open_record", "label": "Open chat", "ref": "chat:" + chat}], area=c.area))
	return out


def detect_cycle(space):
	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "title", "start_date", "end_date"], as_dict=True)
	if not cycle:
		return []
	week = journal.week_of(cycle, getdate(today()))
	if not 1 <= week <= journal.WEEKS:
		return []
	out = []
	target = cint(frappe.db.get_single_value("Life Settings", "score_target")) or 85
	goals = frappe.get_all("Life Goal", filters={"cycle": cycle.name, "outcome": "In Progress", "is_someday": 0}, fields=["name", "title", "area"])
	if week >= 2:
		prev = journal.week_score(cycle.name, week - 1)
		if prev["planned"] and prev["percent"] < target:
			out.append(candidate("12 Week Year", f"Week {week - 1} ended at {round(prev['percent'])}% against your {target}% target",
				[ev("Life Cycle", cycle.name, cycle.title)], body=f"{prev['done']} of {prev['planned']} planned ticks were done.",
				actions=[{"kind": "open_list", "label": "Open the grid", "to": {"path": "/journal", "query": {}}}]))
	no_ticks, no_tasks = counts.goal_sets(space)
	if no_ticks:
		titles = {g.name: g.title for g in goals}
		out.append(candidate("12 Week Year", f"{len(no_ticks)} goal{'s have' if len(no_ticks) > 1 else ' has'} had no ticks for three weeks",
			[ev("Life Goal", g, titles.get(g, "")) for g in no_ticks], actions=[{"kind": "open_list", "label": "Open the goals",
				"to": counts.goals(space, None, "with no ticks for 3 weeks", no_ticks)["to"]}]))
	if no_tasks:
		titles = dict(frappe.get_all("Life Goal", filters={"name": ["in", no_tasks]}, fields=["name", "title"], as_list=True))
		out.append(candidate("12 Week Year", f"{len(no_tasks)} goal{'s have' if len(no_tasks) > 1 else ' has'} no tasks and no open actions",
			[ev("Life Goal", g, titles.get(g, "")) for g in no_tasks], actions=[{"kind": "open_list", "label": "Open the goals",
				"to": counts.goals(space, None, "with no tasks", no_tasks)["to"]}]))
	return out


def detect_habits(space):
	now = getdate(today())
	if now.day < 7:
		return []
	this = journal.habits_month(space, now.year, now.month)
	prev_d = add_months(now, -1)
	last = {h["habit"]: h for h in journal.habits_month(space, prev_d.year, prev_d.month)["habits"]}
	out = []
	for h in this["habits"]:
		before = last.get(h["habit"])
		if h["removed"] or not before or not before["tracked_days"] or not h["tracked_days"]:
			continue
		if before["percent"] - h["percent"] >= HABIT_MARGIN:
			rate = lambda x: round(7.0 * x["done"] / max(x["tracked_days"], 1), 1)
			out.append(candidate("Habit", f"{h['title']} slipped from {rate(before):g} days a week last month to {rate(h):g} so far this month",
				[ev("Life Habit", h["habit"], h["title"])], body=f"{before['percent']}% last month, {h['percent']}% this month.",
				actions=[{"kind": "open_list", "label": "Open habits", "to": {"path": "/journal/habits", "query": {}}}]))
	return out


def detect_checkins(space):
	rows = frappe.db.sql("""select c.name, c.date, s.dimension, s.habits_low, s.habits_high, s.situation_low, s.situation_high
		from `tabLife Check-in` c join `tabLife Check-in Score` s on s.parent = c.name where c.space=%s order by c.date desc limit 400""", space, as_dict=True)
	by_dim = {}
	for r in rows:
		vals = [v for v in (r.habits_low, r.habits_high, r.situation_low, r.situation_high) if v is not None]
		if vals:
			by_dim.setdefault(r.dimension, []).append((r.name, r.date, sum(vals) / len(vals)))
	names = dict(frappe.get_all("Life Dimension", filters={"space": space}, fields=["name", "dimension_name"], as_list=True))
	out = []
	for dim, pts in by_dim.items():
		last3 = pts[:3]
		if len(last3) < 3:
			continue
		label = names.get(dim, dim)
		evidence = [ev("Life Check-in", n, str(d)) for n, d, _ in last3]
		if all(v <= LOW_SCORE for _, _, v in last3):
			out.append(candidate("Check-in", f"{label} has scored {LOW_SCORE} or lower in three check-ins in a row", evidence,
				actions=[{"kind": "open_list", "label": "Open check-ins", "to": {"path": "/journal/checkins", "query": {}}}]))
		elif last3[0][2] < last3[1][2] < last3[2][2]:
			out.append(candidate("Check-in", f"{label} is trending down: {last3[2][2]:g}, {last3[1][2]:g}, {last3[0][2]:g}", evidence,
				actions=[{"kind": "open_list", "label": "Open check-ins", "to": {"path": "/journal/checkins", "query": {}}}]))
	return out


def detect_someday(space):
	from lifeos.api import someday

	due = someday.list(space=space, tab="due", page_length=100)
	if not due["total"]:
		return []
	return [candidate("Someday", f"{due['total']} Someday item{'s are' if due['total'] > 1 else ' is'} due for review",
		[ev(r.doctype, r.name, r.title) for r in due["rows"]],
		actions=[{"kind": "open_list", "label": "Review them", "to": counts.someday_due(space)["to"]}])]


RULES = [detect_stuck, detect_waiting, detect_cycle, detect_habits, detect_checkins, detect_someday]


# ---- the notice skill ----

WINDOW_DAYS = 14
MAX_RECORDS = 40
CHARS_PER_RECORD = 1500
KINDS_AI = ("Waiting on you", "Promise", "Theme")


def recent_records(ctx, space, kinds, days, limit, chars):
	"""The records of the last `days` days of these kinds, read through get_record, so the space, Vault and permission rules apply."""
	from lifeos.ai.tools import t_get_record

	# nosemgrep: frappe-sql-format-injection -- only the code-owned vault fragment of the tool context is inserted; the rest are parameters
	rows = frappe.db.sql(f"""select ref_doctype, ref_name from `tabLife Index` x where x.space=%s and x.is_archived=0 and x.kind in %s
		and x.modified >= %s{ctx.vault_sql()} order by x.modified desc limit %s""", (space, kinds, add_days(today(), -days), limit), as_dict=True)
	out = []
	for r in rows:
		try:
			got = t_get_record(ctx, doctype=r.ref_doctype, name=r.ref_name)
		except (frappe.PermissionError, frappe.DoesNotExistError):
			continue  # a record the user may not read is never sent
		if not got.get("error"):
			got["text"] = (got.get("text") or "")[:chars]
			out.append(got)
	return out


def noticed(space, user):
	"""([candidates], note) from the notice skill: Waiting on you, Promise and Theme over the last 14 days. Nothing when it has no key;
	the rule insights still run. The last 30 dismissals, with their reasons, are sent as guidance."""
	from lifeos.ai import client
	from lifeos.ai.tools import Context
	from lifeos.skills import call

	if not client.is_set_up():
		return [], "AI insights skipped: no API key."
	ctx = Context(space, {"kind": "space", "label": "Everything in this space"}, user)
	records = recent_records(ctx, space, ("Chat", "Inbox", "Note"), WINDOW_DAYS, MAX_RECORDS, CHARS_PER_RECORD)
	if not records:
		return [], None
	dismissed = [{"kind": r.kind, "title": r.title, "reason": r.dismiss_reason or "no reason"} for r in frappe.get_all("Life Insight",
		filters={"space": space, "status": "Dismissed"}, fields=["kind", "title", "dismiss_reason"], order_by="modified desc", limit=30)]
	got = call.ask("notice", {"request": "insights", "today": today(), "records": records, "dismissed": dismissed,
		"open_task_titles": frappe.get_all("Life Task", filters={"space": space, "status": ["in", ["Open", "Doing", "Waiting"]], "is_archived": 0},
			pluck="title", limit=300)}, space=space, user=user)
	if not got:
		return [], f"AI insights skipped: {got.reason}"
	found = []
	for c in (got.get("insights") or [])[:6]:
		if c.get("kind") not in KINDS_AI or not c.get("title"):
			continue
		evidence = [ev(ctx.refs[r]["doctype"], ctx.refs[r]["name"], ctx.refs[r]["title"]) for r in c.get("evidence") or [] if r in ctx.refs]
		if not evidence:
			continue
		actions = []
		if c["kind"] in ("Waiting on you", "Promise"):
			area = next((ctx.refs[r].get("area") for r in c.get("evidence") or [] if r in ctx.refs and ctx.refs[r].get("area")), None)
			actions.append({"kind": "make_task", "label": "Make task", "title": (c.get("task_title") or c["title"])[:140], "area": area})
		actions.append({"kind": "open_record", "label": "Open", "ref": next((ctx.refs[r]["pane"] for r in c["evidence"] if r in ctx.refs), None)})
		found.append(candidate(c["kind"], c["title"], evidence, body=c.get("body") or "", actions=actions, source="AI", source_line=f"Suggested by {got.label}"))
	return found, None


# ---- the run ----

def _valid_evidence(evidence, user):
	"""Keep only evidence that exists and the user may read (AI candidates are checked the same way)."""
	from lifeos import permissions

	out = []
	for e in evidence:
		dt, name = e.get("ref_doctype"), e.get("ref_name")
		if not dt or not name or not frappe.db.exists(dt, name):
			continue
		try:
			doc = frappe.get_doc(dt, name)
			if not frappe.has_permission(dt, "read", doc=doc, user=user):
				continue
			if dt == "Life Vault Document" and permissions.vault_hidden(doc.space, user):
				continue
		except frappe.PermissionError:
			continue
		out.append(e)
	return out


def run(space, ai=True, user=None):
	"""Find insights for a space now. Returns {"created": n, "returned": n, "kept": n, "skipped_dismissed": n}."""
	user = user or frappe.session.user
	day = getdate(today())
	stats = {"created": 0, "returned": 0, "kept": 0, "skipped_dismissed": 0, "ai": None}
	# snoozed insights whose date has come are new again
	for name in frappe.get_all("Life Insight", filters={"space": space, "status": "Snoozed", "snooze_until": ["<=", day]}, pluck="name"):
		frappe.db.set_value("Life Insight", name, {"status": "New", "snooze_until": None})
		stats["returned"] += 1
	cands = []
	for fn in RULES:
		cands += fn(space)
	if ai:
		got, note = noticed(space, user)
		cands += got
		stats["ai"] = note
	existing = {r.fingerprint: r for r in frappe.get_all("Life Insight", filters={"space": space},
		fields=["name", "fingerprint", "status", "source"])}
	seen = set()
	cands.sort(key=lambda c: (RANK.get(c["kind"], 99), -len(c["evidence"])))
	room = MAX_NEW_PER_DAY - frappe.db.count("Life Insight", {"space": space, "found_on": day})
	for c in cands:
		c["evidence"] = _valid_evidence(c["evidence"], user)
		if not c["evidence"]:
			continue
		fp = fingerprint(c["kind"], c["evidence"])
		if fp in seen:
			continue
		seen.add(fp)
		old = existing.get(fp)
		if old:
			if old.status == "Dismissed":
				stats["skipped_dismissed"] += 1
			else:
				stats["kept"] += 1
			continue
		if room <= 0:
			continue
		frappe.get_doc({"doctype": "Life Insight", "space": space, "kind": c["kind"], "title": c["title"], "body": c.get("body"),
			"evidence": c["evidence"], "actions": json.dumps(c.get("actions") or []), "status": "New", "fingerprint": fp,
			"source": c.get("source") or "Rule", "source_line": c.get("source_line"), "area": c.get("area") or None, "found_on": day, "rank": RANK.get(c["kind"], 99)}).insert(ignore_permissions=True)
		room -= 1
		stats["created"] += 1
	# rule insights still New whose finding is no longer true are removed (their evidence changed or went away)
	# (the weekly review's own rule findings, set 8, are kept current by lifeos/review/findings.py, not here)
	for name, fp in frappe.db.sql("""select name, fingerprint from `tabLife Insight` where space=%s and status='New' and source='Rule'
			and kind in %s""", (space, KINDS)):
		if fp not in seen:
			frappe.delete_doc("Life Insight", name, ignore_permissions=True, delete_permanently=True)
	frappe.db.set_single_value("Life Settings", "insights_run_on", now_datetime())
	return stats


def run_nightly():
	"""06:00 every day: each space for its owner. The session is not switched: `run` reads and checks every record as
	that user, so the AI sees only what the owner may read."""
	for s in frappe.get_all("Life Space", fields=["name", "owner_user", "ask_enabled"]):
		if not s.owner_user:
			continue
		# a space that fails is undone alone; the scheduler commits the rest when the job ends
		frappe.db.savepoint("lifeos_insights")
		try:
			run(s.name, ai=bool(s.ask_enabled), user=s.owner_user)
			if s.ask_enabled:  # set 7: values of number goals read from the week's captures and chat logs, as Suggested readings
				from lifeos import readings

				readings.run_for_space(s.name, s.owner_user)
			from lifeos.review import followups  # set 8: meetings linked, their follow-ups, readings waiting

			followups.nightly(s.name, s.owner_user, ai=bool(s.ask_enabled))
		except Exception:
			frappe.db.rollback(save_point="lifeos_insights")
			frappe.log_error(title=f"Life OS insights for {s.name}")
