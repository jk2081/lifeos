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
	}


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
def save_you(full_name: str, time_zone: str):
	"""Step 2: the person's name, and the site's time zone (a site belongs to one person)."""
	permissions.require_login()
	if not permissions.is_admin():
		frappe.throw(_("Only the owner can set this."), frappe.PermissionError, title=_("Only the owner sets this"))
	full_name = " ".join((full_name or "").split())
	if not full_name:
		frappe.throw(_("Type your name."), title=_("Name is missing"))
	if time_zone not in available_timezones():
		frappe.throw(_("{0} is not a time zone.").format(time_zone), title=_("Time zone is not valid"))
	first, _sep, last = full_name.partition(" ")
	user = frappe.get_doc("User", frappe.session.user)
	user.first_name, user.last_name = first, last
	user.flags.ignore_permissions = True  # system: a person saves their own name and time zone
	user.save()
	if frappe.db.get_single_value("System Settings", "time_zone") != time_zone:
		# set directly: a site made by bench new-site may lack other required System Settings fields, which a save would refuse
		frappe.db.set_single_value("System Settings", "time_zone", time_zone)
		frappe.clear_cache()
	frappe.clear_cache(user=frappe.session.user)  # the full name is cached per person
	return {"full_name": full_name, "time_zone": time_zone}


@frappe.whitelist(methods=["POST"])
def add_first_things(things: str | list, space: str | None = None):
	"""Step 4: up to three things on the person's mind. Each becomes a task, with its area guessed."""
	from lifeos.api import tasks

	permissions.require_login()
	space = permissions.resolve_space(space, write=True)
	lines = [" ".join(str(t).split()) for t in (frappe.parse_json(things) or [])]
	lines = [t for t in lines if t][:MAX_FIRST_THINGS]
	out = [tasks.quick_add(text=t, space=space) for t in lines]
	ladder.forget(frappe.session.user)
	return [{"name": t["name"], "title": t["title"], "area": t.get("area"), "area_name": t.get("area_name")} for t in out]
