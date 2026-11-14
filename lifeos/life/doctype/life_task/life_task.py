import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

CLOSED = ("Done", "Dropped", "Carried")


class LifeTask(Document):
	def validate(self):
		self.title = (self.title or "").strip()
		if self.status == "Done" and not self.completed_on:
			self.completed_on = today()
		if self.status in ("Dropped", "Carried") and not self.completed_on:
			self.completed_on = today()
		if self.status not in CLOSED:
			self.completed_on = None
		if self.status == "Waiting" and not (self.waiting_on or "").strip():
			frappe.throw(_("Say who or what this task is waiting on."), frappe.MandatoryError)
		if not self.flags.keep_touched:
			self.last_touched_on = today()
