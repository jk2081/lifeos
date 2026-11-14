"""Schema help for agents and for the review screen."""
import frappe

from lifeos import permissions, proposals


@frappe.whitelist()
def proposal_schema():
	"""For each proposal kind: the allowed payload fields and an example. Call once before the first submission."""
	permissions.require_login()
	return proposals.schema()


@frappe.whitelist()
def space_context(space=None):
	"""Areas, projects, tags, people, habits, dimensions and active goals of a space, for filing proposals."""
	from lifeos.api.inbox import space_context as ctx

	return ctx(permissions.resolve_space(space))
