"""Schema help for agents and for the review screen."""
import frappe

from lifeos import permissions
from lifeos.brain import proposals


@frappe.whitelist(methods=["GET"])
def proposal_schema():
	"""For each proposal kind: the allowed payload fields and an example. Call once before the first submission."""
	permissions.require_login()
	return proposals.schema()


@frappe.whitelist(methods=["GET"])
def space_context(space: str | None = None):
	"""Areas, people, habits and active goals of a space, for filing proposals."""
	from lifeos.api.inbox import space_context as ctx

	return ctx(permissions.resolve_space(space))


@frappe.whitelist(methods=["GET"])
def setup_level():
	"""The person's level on the ladder (1 to 6), what is done, and the next step's text and link. Cached for a few minutes."""
	permissions.require_login()
	from lifeos.review import ladder

	return ladder.get(frappe.session.user)


@frappe.whitelist(methods=["POST"])
def dismiss_setup(undo: int = 0):
	"""Hide the "Your setup" card for this person (or show it again with undo=1)."""
	permissions.require_login()
	from lifeos.review import ladder

	user = frappe.session.user
	if int(undo):
		frappe.defaults.clear_default(ladder.DISMISSED_KEY, parent=user)
	else:
		frappe.defaults.set_user_default(ladder.DISMISSED_KEY, "1", user)
	return ladder.get(user)
