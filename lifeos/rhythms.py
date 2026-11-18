"""Rhythm banners (UX fixes, set 6): Today shows at most one line, above the Open band, when a rhythm is due.

In order of precedence:
  1. the weekly review, on the review day from the review time until it is done or skipped;
  2. "Plan <Month>", in the first three days of a month until the month plan exists (when month plans are on);
  3. "Plan your next 12 weeks", in week 11 of a cycle until the next cycle is planned;
  4. "Close this cycle", in week 12.
Each occurrence has its own key ("review:2026-11-16", "month:2026-11", "plan-next:<cycle>", "close:<cycle>"). Skip and
Done are remembered per user, in the view state "rhythm-banners", so a skipped banner comes back at the next occurrence.
"""
import json

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from lifeos import journal

SCREEN = "rhythm-banners"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
KEEP = 60  # occurrences remembered


def clock(at=None):
	"""The moment the banners are worked out for. A test site may move it (site config lifeos_test_clock), never a live one."""
	if at and frappe.conf.get("lifeos_test_clock"):
		return get_datetime(at)
	return now_datetime()


def _state(user=None):
	user = user or frappe.session.user
	text = frappe.db.get_value("Life View State", {"user": user, "screen": SCREEN, "space": ("is", "not set")}, "state")
	try:
		state = json.loads(text) if text else {}
	except ValueError:
		state = {}
	return state if isinstance(state, dict) else {}


def _save(state, user=None):
	user = user or frappe.session.user
	text = json.dumps(state, separators=(",", ":"))
	name = frappe.db.get_value("Life View State", {"user": user, "screen": SCREEN, "space": ("is", "not set")})
	if name:
		frappe.db.set_value("Life View State", name, "state", text)
	else:
		frappe.get_doc({"doctype": "Life View State", "user": user, "screen": SCREEN, "state": text}).insert(ignore_permissions=True)


def dismiss(occurrence, how="skipped"):
	"""Skip a banner (or mark its rhythm done) until the next occurrence."""
	state = _state()
	seen = [k for k in state.get(how, []) if k != occurrence] + [occurrence]
	state[how] = seen[-KEEP:]
	_save(state)
	return {"occurrence": occurrence, how: True}


def _week_start(day):
	return add_days(day, -day.weekday())


def review_done(space, week_start, user=None):
	"""The weekly review of the week starting on `week_start` is done once a review was locked in that week (set 8; a
	review note of set 7 became a locked review dated by its week)."""
	return bool(frappe.db.exists("Life Review", {"space": space, "user": user or frappe.session.user, "kind": "Weekly", "status": "Locked",
		"period_end": (">=", week_start)}))


def banner(space, at=None):
	"""The one banner Today shows, or None. {key, occurrence, text, to: {path, query}, action}."""
	s = frappe.get_cached_doc("Life Settings")
	now = clock(at)
	day = getdate(now)
	state = _state()
	gone = set(state.get("skipped", [])) | set(state.get("done", []))

	# 1. the weekly review
	if DAYS[day.weekday()] == (s.weekly_review_day or "Sunday"):
		ws = _week_start(day)
		occ = f"review:{ws}"
		at_time = str(s.weekly_review_time or "18:00:00")
		if now.strftime("%H:%M:%S") >= at_time.zfill(8) and occ not in gone and not review_done(space, ws):
			return {"key": "review", "occurrence": occ, "text": "Your weekly review is ready", "action": "Start the review",
				"to": {"path": "/plan/week", "query": {"view": "review"}}}

	# 2. the month plan
	enabled = s.month_plan_enabled if s.month_plan_enabled is not None else 1
	if int(enabled) and day.day <= 3:
		occ = f"month:{day.year}-{day.month:02d}"
		has_plan = frappe.db.exists("Life Month Plan", {"space": space, "year": day.year, "month": day.month})
		if occ not in gone and not has_plan:
			return {"key": "month", "occurrence": occ, "text": f"Plan {MONTHS[day.month - 1]}", "action": "Open the month",
				"to": {"path": "/plan/month", "query": {"view": "plan"}}}

	# 3 and 4. the 12 Week cycle
	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "start_date", "end_date"], as_dict=True)
	if cycle:
		week = journal.week_of(cycle, day)
		if week == 11:
			occ = f"plan-next:{cycle.name}"
			planned = frappe.db.exists("Life Cycle", {"space": space, "status": "Planned", "start_date": (">", cycle.start_date)})
			if occ not in gone and not planned:
				return {"key": "plan-next", "occurrence": occ, "text": "Plan your next 12 weeks", "action": "Open 12 Weeks",
					"to": {"path": "/plan/12-weeks", "query": {}}}
		if week == 12:
			occ = f"close:{cycle.name}"
			if occ not in gone:
				return {"key": "close", "occurrence": occ, "text": "Close this cycle", "action": "Open 12 Weeks",
					"to": {"path": "/plan/12-weeks", "query": {}}}
	return None
