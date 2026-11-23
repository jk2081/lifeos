import frappe
from frappe import _
from frappe.model.document import Document


class LifeHabitLog(Document):
	def autoname(self):
		self.name = f"{self.habit}-{self.date}"

	def before_validate(self):
		if self.habit and not self.space:
			self.space = frappe.db.get_value("Life Habit", self.habit, "space")

	def validate(self):
		if frappe.db.exists("Life Habit Log", {"habit": self.habit, "date": self.date, "name": ("!=", self.name or "")}):
			frappe.throw(_("This habit already has a log for that date."), frappe.DuplicateEntryError, title=_("Habit already logged"))
