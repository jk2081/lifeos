import frappe
from frappe import _
from frappe.model.document import Document


class LifeGoalReading(Document):
	"""One value of a number goal's measure on a date (set 7). The goal's current value is always its latest Confirmed
	reading, so every change here updates the goal."""

	def validate(self):
		goal = frappe.db.get_value("Life Goal", self.goal, ["space", "measure_kind", "title", "unit"], as_dict=True)
		if not goal:
			frappe.throw(_("Goal not found."), frappe.DoesNotExistError, title=_("Goal not found"))
		if goal.measure_kind != "Number":
			frappe.throw(_("Readings belong to a goal measured by a number."), title=_("Goal has no number measure"))
		self.space = goal.space
		if self.value is None:
			frappe.throw(_("A reading needs a value."), title=_("Reading needs a value"))
		unit = f" {goal.unit}" if goal.unit else ""
		self.title = f"{goal.title}: {_num(self.value)}{unit}"[:140]
		from lifeos.permissions import is_agent

		if self.status != "Suggested" and is_agent() and (self.is_new() or self.has_value_changed("status")):
			frappe.throw(_("Agents suggest readings; only a person confirms or rejects them."), frappe.PermissionError, title=_("Only a person confirms readings"))
		if self.status == "Confirmed" and not self.confirmed_on:
			self.confirmed_by = self.confirmed_by or frappe.session.user
			self.confirmed_on = frappe.utils.now_datetime()
		if self.status != "Confirmed":
			self.confirmed_by = self.confirmed_on = None

	def on_update(self):
		from lifeos import readings

		readings.refresh_current(self.goal)

	def after_delete(self):
		from lifeos import readings

		if frappe.db.exists("Life Goal", self.goal):
			readings.refresh_current(self.goal)


def _num(v):
	v = float(v or 0)
	return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")
