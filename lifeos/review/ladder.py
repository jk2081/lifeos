"""The ladder (issue 26): six levels of adoption, computed from the person's own data.

A level is reached when the one before it is in use, so levels never skip. The result is cached per person for a few
minutes; `forget` clears it.
"""
import frappe
from frappe.query_builder import functions as fn

from lifeos import permissions

CACHE_SECONDS = 180
DISMISSED_KEY = "lifeos_setup_dismissed"
HOW = "/how-it-works"

# title, what you do (the next step's text), the link it goes to
LEVELS = [
	{"level": 1, "title": "Task app", "step": "Add your first task",
	 "hint": "Add tasks, capture by voice", "gain": "Useful on day one, no AI", "to": "/goals/tasks"},
	{"level": 2, "title": "Connect a source", "step": "Connect a source",
	 "hint": "Email or calendar", "gain": "Tasks appear on their own", "to": "/brain/sources"},
	{"level": 3, "title": "Describe your life", "step": "Describe your life",
	 "hint": "3 to 5 areas, a few goals", "gain": "Things file themselves", "to": "/settings?tab=areas"},
	{"level": 4, "title": "Weekly rhythm", "step": "a weekly review",
	 "hint": "A 30-minute review", "gain": "You plan around goals", "to": "/review",
	 "detail": "30 minutes on Sunday. Review joins the menu after your first one."},
	{"level": 5, "title": "Give an agent work", "step": "give an agent work",
	 "hint": "Hermes, OpenClaw or built in", "gain": "Work done and filed back", "to": "/brain/sources",
	 "detail": "Hermes, OpenClaw or the built-in Brain. Work is done and filed back."},
	{"level": 6, "title": "Delegate", "step": "delegate",
	 "hint": "Agents and people, with rights", "gain": "A system that runs", "to": "/settings?tab=members",
	 "detail": "Give another person or an agent Write access in a space."},
]


def _done(user: str) -> list[bool]:
	"""Whether each level's own condition holds, in order. Not yet the ladder: see `compute`."""
	spaces = tuple(permissions.user_spaces(user))
	if not spaces:
		return [False] * 6
	spaces = list(spaces)

	def one(doctype, make):
		t = frappe.qb.DocType(doctype)
		return bool(frappe.qb.from_(t).select(1).where(make(t)).limit(1).run())  # system: the ladder asks only whether something exists

	area = frappe.qb.DocType("Life Area")
	areas = frappe.qb.from_(area).select(fn.Count("*")).where(area.space.isin(spaces) & (area.is_life_area == 1) & (area.is_on == 1) & (fn.IfNull(area.is_archived, 0) == 0)).run()[0][0]  # system: the ladder
	return [
		one("Life Task", lambda t: t.space.isin(spaces)),
		one("Life Inbox Item", lambda t: t.space.isin(spaces) & (~fn.IfNull(t.source_system, "").isin(["", "upload"]) | (t.source_type != "Upload"))),
		areas >= 3 and one("Life Goal", lambda t: t.space.isin(spaces)),
		one("Life Review", lambda t: (t.user == user) & (t.kind == "Weekly") & (t.status == "Locked")),
		one("Life Inbox Item", lambda t: t.space.isin(spaces) & t.status.isin(["To Review", "Done"]) & ((fn.IfNull(t.job_id, "") != "") | (fn.IfNull(t.claimed_by, "") != ""))),
		one("Life Space Member", lambda t: (t.parenttype == "Life Space") & t.parent.isin(spaces) & (t.access == "Write") & (t.user != user)),
	]


def compute(user: str) -> dict:
	done = _done(user)
	reached = 0
	while reached < 6 and done[reached]:
		reached += 1
	level = max(1, reached)
	complete = reached == 6
	nxt = None if complete else LEVELS[reached]
	return {
		"level": level, "of": 6, "complete": complete,
		"done": [{"level": x["level"], "title": x["title"], "done": i < reached} for i, x in enumerate(LEVELS)],
		"next": None if not nxt else {"level": nxt["level"], "title": nxt["title"], "text": next_text(nxt), "to": nxt["to"]},
		"levels": LEVELS, "dismissed": dismissed(user), "how": HOW,
	}


def next_text(step: dict) -> str:
	if step["level"] == 4:
		return f"Next: {step['step']} · {step['detail']}"
	if step["level"] > 4:
		return f"Next: {step['step']}. {step['detail']}"
	return f"Next: {step['step']}. {step['hint']}."


def cache_key(user: str) -> str:
	return f"lifeos_ladder:{user}"


def get(user: str) -> dict:
	cached = frappe.cache.get_value(cache_key(user))
	if cached is None:
		cached = compute(user)
		frappe.cache.set_value(cache_key(user), cached, expires_in_sec=CACHE_SECONDS)
	return {**cached, "dismissed": dismissed(user)}


def forget(user: str):
	frappe.cache.delete_value(cache_key(user))


def dismissed(user: str) -> bool:
	return bool(frappe.db.get_value("DefaultValue", {"parent": user, "defkey": DISMISSED_KEY}, "defvalue"))
