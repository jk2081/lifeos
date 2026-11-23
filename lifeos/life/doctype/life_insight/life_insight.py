from frappe.model.document import Document
from frappe.utils import add_days, today


class LifeInsight(Document):
	def validate(self):
		"""Snoozed means until a day (a week from now when none is given); back to New clears the snooze and the reason."""
		if self.status == "Snoozed" and not self.snooze_until:
			self.snooze_until = add_days(today(), 7)
		if self.status == "New":
			self.snooze_until, self.dismiss_reason = None, ""
