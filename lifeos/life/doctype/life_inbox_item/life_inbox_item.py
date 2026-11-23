import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, today


class LifeInboxItem(Document):
	def before_insert(self):
		if not self.received_on:
			self.received_on = now_datetime()

	def validate(self):
		from lifeos.brain import sources

		self.intent = self.intent or "Process"
		sources.set_media_kind(self)
		sources.check_external_id(self)
		if self.status == "Done" and not self.finished_on:
			self.finished_on = today()
		if self.status != "Done":
			self.finished_on = None
		if self.status == "New":
			self.claimed_by = None
			self.claimed_on = None

	def on_trash(self):
		for name in frappe.get_all("Life Proposal", filters={"inbox_item": self.name}, pluck="name"):
			frappe.delete_doc("Life Proposal", name, ignore_permissions=True, force=True)
