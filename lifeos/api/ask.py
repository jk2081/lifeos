"""Ask (UX fixes, set 5). Filled in at step 7; status is used by Reset and the Ask page."""
import frappe

from lifeos import permissions


@frappe.whitelist()
def status(space=None):
	"""Is Ask ready for this person in this space: set up (a key), on for the space, and under the monthly cap."""
	from lifeos.ai import client

	space = permissions.resolve_space(space)
	on = bool(frappe.db.get_value("Life Space", space, "ask_enabled"))
	st = client.spend_status()
	return {"ready": on and st["set_up"] and not st["reached"] and not permissions.is_agent(), "enabled": on, **st,
		"vault": bool(frappe.db.get_value("Life Space", space, "ask_can_read_vault"))}
