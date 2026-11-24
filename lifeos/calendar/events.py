"""Core Event records belong to a space through the custom field `life_space`."""
import frappe

from lifeos import permissions
from lifeos.calendar import key_dates


def validate_event(doc, method=None):
	if not doc.get("life_space"):
		owner = doc.owner or frappe.session.user
		roles = set(frappe.get_roles(owner))
		if roles & {"Life Admin", "Life User", "Life Agent"}:
			doc.life_space = permissions.default_space(owner)
	if doc.get("life_space"):
		if frappe.session.user != "Administrator" and not frappe.flags.in_migrate:
			access = permissions.user_spaces().get(doc.life_space)
			if doc.is_new() and access != "Write" and doc.owner == frappe.session.user:
				frappe.throw(frappe._("You do not have access to this space."), frappe.PermissionError, title=frappe._("No access to space"))
		# core Event shows a record to others only when it is Public; the space hook then narrows it to members
		doc.event_type = "Public"
	key_dates.track_change(doc)
