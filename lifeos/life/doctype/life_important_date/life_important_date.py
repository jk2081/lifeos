import calendar

import frappe
from frappe import _
from frappe.model.document import Document


class LifeImportantDate(Document):
	def validate(self):
		self.day, self.month = int(self.day or 0), int(self.month or 0)
		if not 1 <= self.month <= 12:
			frappe.throw(_("Month must be 1 to 12."))
		# 2024 is a leap year, so 29 February is allowed
		if not 1 <= self.day <= calendar.monthrange(2024, self.month)[1]:
			frappe.throw(_("That day does not exist in that month."))
		if self.year and not 1800 <= int(self.year) <= 2200:
			frappe.throw(_("Year looks wrong."))
