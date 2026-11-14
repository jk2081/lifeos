import frappe
from frappe.model.document import Document

from lifeos.life.doctype.life_goal.life_goal import check_cycle_open


class LifeActionLog(Document):
	def autoname(self):
		self.name = f"{self.action_id}-{self.date}"

	def before_validate(self):
		if self.goal and not self.space:
			self.space = frappe.db.get_value("Life Goal", self.goal, "space")

	def validate(self):
		check_cycle_open(self.cycle, self.flags)

	def on_trash(self):
		check_cycle_open(self.cycle, self.flags)
