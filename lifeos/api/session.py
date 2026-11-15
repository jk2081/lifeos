"""Boot data for the front end."""
import frappe
from frappe.utils import today

from lifeos import permissions


@frappe.whitelist()
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
		},
		"today": today(),
		"time_zone": frappe.utils.get_system_timezone(),
	}


@frappe.whitelist()
def counts(space=None):
	"""Small numbers for the sidebar."""
	space = permissions.resolve_space(space)
	from lifeos.api import tasks as task_api

	# due: open tasks due today or overdue, the same number as Today's "Due today" and the list it opens
	return {"to_review": frappe.db.count("Life Inbox Item", {"space": space, "status": "To Review", "is_archived": 0}),
		"due": task_api.list(space=space, status="open_doing", due="today,overdue", page_length=1)["total"]}
