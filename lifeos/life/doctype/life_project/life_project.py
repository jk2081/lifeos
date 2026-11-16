import frappe
from frappe.model.document import Document
from frappe.utils import today


class LifeProject(Document):
	def validate(self):
		if self.status in ("Done", "Dropped"):
			if not self.completed_on:
				self.completed_on = today()
		else:
			self.completed_on = None
		self.last_activity_on = today()
		if self.status != "Someday" and not self.flags.keep_someday:
			self.someday_on = self.someday_review_on = None

	def on_update(self):
		from lifeos import archive

		before = self.get_doc_before_save()
		was = before.status if before else None
		if self.status in ("Done", "Dropped") and was not in ("Done", "Dropped") and not self.is_archived:
			archive.archive_project(self)
