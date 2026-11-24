"""First run on a new person's site (issue 49): a short guide to level 1 of the ladder.

The guide shows once, to a person with Life Admin on a site that has no tasks, goals or captures. Finishing it or skipping it
is kept as a user default, so it does not come back; a System Manager can reset it from Settings, Advanced.
"""
from zoneinfo import available_timezones

import frappe
from frappe import _

from lifeos.review import ladder
from lifeos import permissions

KEY = "lifeos_onboarding"
STATUSES = ("done", "skipped")
MAX_FIRST_THINGS = 3
CONTENT = ("Life Task", "Life Goal", "Life Inbox Item")


def is_empty(user: str) -> bool:
	"""Whether the person's spaces hold no task, goal or capture yet."""
	spaces = list(permissions.user_spaces(user))
	if not spaces:
		return True
	return not any(frappe.db.exists(dt, {"space": ("in", spaces)}) for dt in CONTENT)


def status_of(user: str) -> str | None:
	return frappe.db.get_value("DefaultValue", {"parent": user, "defkey": KEY}, "defvalue") or None


def _is_system_manager() -> bool:
	return "System Manager" in frappe.get_roles() or frappe.session.user == "Administrator"


@frappe.whitelist(methods=["GET"])
def state():
	"""Whether the guide was done or skipped, whether it should show now, and whether the site is still empty."""
	permissions.require_login()
	user = frappe.session.user
	status = status_of(user)
	empty = is_empty(user)
	person = permissions.is_admin() and not permissions.is_agent()
	return {
		"status": status, "done": bool(status), "empty": empty, "show": bool(person and not status and empty),
		"is_system_manager": _is_system_manager(),
		"full_name": frappe.utils.get_fullname(user), "time_zone": frappe.utils.get_system_timezone(),
		"call_me": call_me(user), "ai_set": ai_set(), "google_connected": google_connected(user),
	}


def call_me(user: str) -> str:
	"""What the person likes to be called: the name they chose, else the first word of the full name on the account."""
	chosen = frappe.db.get_value("User", user, "preferred_name")
	full = frappe.utils.get_fullname(user)
	return chosen or ("" if full in (user, "Administrator") else full.split()[0])


def ai_set() -> bool:
	from lifeos.ai import client

	return client.is_set_up()


def google_connected(user: str) -> bool:
	"""Whether a Gmail mailbox or the person's Google Calendar is connected."""
	from lifeos.review import gcal

	mail = frappe.get_all("Life Connection", filters={"system": "gmail", "active": 1, "mailbox": ("is", "set")}, limit=1)  # system: only whether one exists
	return bool(mail) or bool(gcal.is_connected(user))


@frappe.whitelist(methods=["POST"])
def complete(status: str = "done"):
	"""Record that the guide was finished ("done") or closed ("skipped"), so it does not show again."""
	permissions.require_login()
	if status not in STATUSES:
		frappe.throw(_("The guide is either done or skipped."), title=_("Guide already finished"))
	frappe.defaults.set_user_default(KEY, status, frappe.session.user)
	ladder.forget(frappe.session.user)
	return state()


@frappe.whitelist(methods=["POST"])
def reset(user: str | None = None):
	"""Show the guide again (a System Manager's call); it opens again only while the site has no tasks, goals or captures."""
	frappe.only_for("System Manager")
	user = user or frappe.session.user
	frappe.defaults.clear_default(KEY, parent=user)
	ladder.forget(user)
	return {"reset": user}


@frappe.whitelist(methods=["POST"])
def save_you(call_me: str, time_zone: str):
	"""Step 2: what the person is called (`User.preferred_name`; the full name on the account is left alone), and the site's time zone
	(a site belongs to one person)."""
	permissions.require_login()
	if not permissions.is_admin():
		frappe.throw(_("Only the owner can set this."), frappe.PermissionError, title=_("Only the owner sets this"))
	call_me = " ".join((call_me or "").split())
	if not call_me:
		frappe.throw(_("Type what we should call you."), title=_("Name is missing"))
	if time_zone not in available_timezones():
		frappe.throw(_("{0} is not a time zone.").format(time_zone), title=_("Time zone is not valid"))
	frappe.db.set_value("User", frappe.session.user, "preferred_name", call_me[:140])
	if frappe.db.get_single_value("System Settings", "time_zone") != time_zone:
		# set directly: a site made by bench new-site may lack other required System Settings fields, which a save would refuse
		frappe.db.set_single_value("System Settings", "time_zone", time_zone)
		frappe.clear_cache()
	frappe.clear_cache(user=frappe.session.user)
	return {"call_me": call_me, "time_zone": time_zone}


@frappe.whitelist(methods=["POST"])
def save_ai_key(key: str):
	"""Step 4 of 6, "Turn on the Brain": store the key (encrypted, in Life Settings) and check it with one cheap call. A key that does not work is
	taken out again."""
	from lifeos.ai import client

	permissions.require_login()
	if not permissions.is_admin():
		frappe.throw(_("Only the owner can set this."), frappe.PermissionError, title=_("Only the owner sets this"))
	key = (key or "").strip()
	if not key:
		frappe.throw(_("Paste the key first."), title=_("Key is missing"))
	doc = frappe.get_doc("Life Settings")
	before = doc.get_password("anthropic_api_key", raise_exception=False)
	doc.anthropic_api_key = key
	doc.save()
	if not client.test_connection().get("ok"):
		doc.reload()
		doc.anthropic_api_key = before
		doc.save()
		frappe.throw(_("That key didn't work. Check it and try again."), title=_("The key did not work"))
	return {"ai_set": True}


@frappe.whitelist(methods=["POST"])
def guess_area(task: str):
	"""Step 5: ask the model where a first thing belongs, with all seven areas of life, each marked on or off. A pick that is on is applied
	(still a guess); a pick that is off is only returned, for the person to switch on. {area, area_name, is_on} or None."""
	from lifeos.ai import client
	from lifeos.brain import area_guess

	doc = permissions.get_doc_checked("Life Task", task, "write")
	if not (doc.area_guessed and doc.area_confidence == area_guess.FALLBACK_CONFIDENCE) or not client.is_set_up():
		return None
	rows = frappe.get_all("Life Area", filters={"space": doc.space, "is_life_area": 1, "is_archived": 0},  # system: the task's own space, write-checked above
		fields=["name", "area_name", "parent_area", "is_life_area", "description", "is_on"], order_by="sort_order asc, area_name asc", limit=20)
	found = area_guess.ask_model(doc, rows)
	if not found:
		return None
	pick = next(r for r in rows if r.name == found["area"])
	if pick.is_on:
		doc.area, doc.area_confidence = pick.name, found["confidence"]
		doc.flags.area_guess = True  # still a guess: keep the mark, log no correction
		doc.flags.keep_touched = True
		doc.save()
	return {"area": pick.name, "area_name": pick.area_name, "is_on": int(pick.is_on)}


@frappe.whitelist(methods=["POST"])
def add_first_things(things: str | list, space: str | None = None):
	"""Step 4: up to three things on the person's mind. Each becomes a task, with its area guessed."""
	from lifeos.api import tasks
	from lifeos.brain import area_guess

	permissions.require_login()
	space = permissions.resolve_space(space, write=True)
	lines = [" ".join(str(t).split()) for t in (frappe.parse_json(things) or [])]
	lines = [t for t in lines if t][:MAX_FIRST_THINGS]
	frappe.flags.lifeos_no_refine = True  # the guide asks the model itself (guess_area) and waits for it
	try:
		out = [tasks.quick_add(text=t, space=space) for t in lines]
	finally:
		frappe.flags.lifeos_no_refine = False
	ladder.forget(frappe.session.user)
	return [{"name": t["name"], "title": t["title"], "area": t.get("area"), "area_name": t.get("area_name"),
		"unsure": int(frappe.db.get_value("Life Task", t["name"], "area_confidence") == area_guess.FALLBACK_CONFIDENCE)} for t in out]


@frappe.whitelist(methods=["POST"])
def remove_first_thing(task: str):
	"""Step 5: take back a first thing the person just made (the × on its row). Only a task made in the last hour, with no goal, can be removed here."""
	doc = permissions.get_doc_checked("Life Task", task, "delete")
	if doc.goal or frappe.utils.time_diff_in_seconds(frappe.utils.now_datetime(), doc.creation) > 3600:
		frappe.throw(_("Only a task the guide just made can be removed here."), frappe.PermissionError, title=_("Task is not new"))
	frappe.delete_doc("Life Task", task)
	ladder.forget(frappe.session.user)
	return {"removed": task}
