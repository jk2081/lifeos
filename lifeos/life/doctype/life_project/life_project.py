import frappe
from frappe import _
from frappe.model.document import Document


class LifeProject(Document):
	"""Kept read-only after set 6, when every project became a long-term goal,
	so the migration can be checked. Only the seed and the demo write here (they set `migrated_to`)."""

	def validate(self):
		if not self.flags.allow_migration:
			frappe.throw(_("Projects are now goals. Open the goal this project became instead."), frappe.PermissionError)
