"""The ladder (issue 26): six levels of adoption, computed from the person's own data.

A level is reached when the one before it is in use, so levels never skip. The result is cached per person for a few
minutes; `forget` clears it.
"""
import frappe

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
	v = {"spaces": spaces, "user": user}

	def one(sql):
		return bool(frappe.db.sql(sql + " limit 1", v))

	return [
		one("select 1 from `tabLife Task` where space in %(spaces)s"),
		one("select 1 from `tabLife Inbox Item` where space in %(spaces)s and (ifnull(source_system, '') not in ('', 'upload') or source_type != 'Upload')"),
		frappe.db.sql("select count(*) from `tabLife Area` where space in %(spaces)s and is_life_area = 1 and is_on = 1 and ifnull(is_archived, 0) = 0", v)[0][0] >= 3
			and one("select 1 from `tabLife Goal` where space in %(spaces)s"),
		one("select 1 from `tabLife Review` where user = %(user)s and kind = 'Weekly' and status = 'Locked'"),
		one("select 1 from `tabLife Inbox Item` where space in %(spaces)s and status in ('To Review', 'Done') and (ifnull(job_id, '') != '' or ifnull(claimed_by, '') != '')"),
		one("select 1 from `tabLife Space Member` where parenttype = 'Life Space' and parent in %(spaces)s and access = 'Write' and user != %(user)s"),
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
