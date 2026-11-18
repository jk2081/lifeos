import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class LifeReview(Document):
	"""One review (set 8): the weekly review's period, where it was left, and what was decided when it was locked."""

	def validate(self):
		if getdate(self.period_end) < getdate(self.period_start):
			frappe.throw(_("A review's period cannot end before it starts."))
		if self.status == "Open" and frappe.db.exists("Life Review", {"space": self.space, "user": self.user, "kind": self.kind,
				"status": "Open", "name": ("!=", self.name or "")}):
			frappe.throw(_("There is already an open review for this space."))
