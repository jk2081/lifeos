"""Boot data for the front end."""
import frappe
from frappe.utils import today

from lifeos import areas, permissions, readings


@frappe.whitelist(methods=["GET"])
def boot():
	"""Who is logged in, which spaces they can use, and the settings the screens need."""
	permissions.require_login()
	spaces = permissions.user_spaces()
	if frappe.session.user == "Administrator" and not spaces:
		spaces = {name: "Write" for name in frappe.get_all("Life Space", pluck="name")}
	s = frappe.get_cached_doc("Life Settings")
	order = {"Private": 0, "Shared": 1}
	return {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"is_admin": permissions.is_admin(),
		"is_agent": permissions.is_agent(),
		"spaces": sorted(({"name": k, "access": v} for k, v in spaces.items()), key=lambda x: (order.get(x["name"], 2), x["name"])),
		"default_space": permissions.default_space(),
		"settings": {
			"score_target": s.score_target or 85, "weekly_review_day": s.weekly_review_day or "Sunday",
			"weekly_review_time": str(s.weekly_review_time or "18:00:00"), "archive_after_days": s.archive_after_days or 90,
			"stale_task_days": s.stale_task_days or 90,
			# Settings > Rhythms (set 6)
			"start_of_day": str(s.start_of_day or "06:00:00"), "week_starts_on": s.week_starts_on or "Monday",
			"require_done_when": int(readings.done_when_required()),
			"use_focuses": int(areas.use_focuses()),
		},
		"today": today(),
		"time_zone": frappe.utils.get_system_timezone(),
	}


@frappe.whitelist(methods=["GET"])
def counts(space: str | None = None, area: str | None = None):
	"""Small numbers for the sidebar, under the lens (`area`)."""
	space = permissions.resolve_space(space)
	from lifeos.api.utils import lens_area

	from lifeos.api import tasks as task_api

	from lifeos import counts as count_rules

	# every number comes with the list it opens (UX fixes, set 5): Inbox items to review, Tasks due today or overdue
	# (Open, Doing and Waiting), the Someday list, and the stuck count behind Reset's amber dot
	c = count_rules.sidebar(space, lens_area(area))
	return {"to_review": c["inbox"]["n"], "due": c["tasks"]["n"], "doors": {k: c[k] for k in ("inbox", "tasks", "someday", "stuck")},
		"over_limit": c["over_limit"], "reviewed": has_locked_review(), "review_due": monthly_or_cycle_due(space)}


def monthly_or_cycle_due(space: str) -> int:
	"""How many monthly or 12-week reviews are due now (issue 47): Review joins the sidebar while one is."""
	from lifeos.review import periodic

	if permissions.is_agent():
		return 0
	return sum(1 for d in periodic.due(space, frappe.session.user) if d["kind"] != "weekly")


def has_locked_review(user: str | None = None) -> bool:
	"""Whether the person has locked a weekly review in any space: Review then joins the sidebar (issue 14)."""
	return bool(frappe.db.exists("Life Review", {"user": user or frappe.session.user, "kind": "Weekly", "status": "Locked"}))
