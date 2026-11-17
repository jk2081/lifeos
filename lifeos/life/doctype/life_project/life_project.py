import frappe
from frappe import _
from frappe.model.document import Document


class LifeProject(Document):
	"""Kept read-only after set 6, when every project became an open-ended goal (lifeos.patches.v7.projects_into_goals),
	so the migration can be checked. Only that patch writes here (it sets `migrated_to`)."""

	def validate(self):
		if not self.flags.allow_migration:
			frappe.throw(_("Projects are now goals. Open the goal this project became instead."), frappe.PermissionError)
