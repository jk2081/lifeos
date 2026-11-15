import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today


def check_cycle_open(cycle, flags=None):
	if flags and flags.allow_closed:
		return
	if cycle and frappe.db.get_value("Life Cycle", cycle, "status") == "Closed":
		frappe.throw(_("A closed cycle is read-only."))


class LifeGoal(Document):
	def before_validate(self):
		if self.cycle and not self.space:
			self.space = frappe.db.get_value("Life Cycle", self.cycle, "space")

	def validate(self):
		self.goal_type = self.goal_type or "12 Week Year"
		if self.goal_type == "12 Week Year" and not self.cycle:
			frappe.throw(_("A 12 Week Year goal belongs to a cycle."))
		if self.goal_type != "12 Week Year" and self.cycle:
			frappe.throw(_("Only a 12 Week Year goal belongs to a cycle. Use Add to a 12 Week Year to move it into one."))
		if self.goal_type == "Annual" and not self.target_date:
			frappe.throw(_("An annual goal needs a target date."))
		if self.goal_type != "12 Week Year" and self.actions:
			frappe.throw(_("Weekly actions belong to 12 Week Year goals."))
		# closed_on: the day the outcome left In Progress
		if (self.outcome or "In Progress") == "In Progress":
			self.closed_on = None
		elif not self.closed_on:
			self.closed_on = today()
		check_cycle_open(self.cycle, self.flags)
		for a in self.actions:
			a.per_week = max(1, int(a.per_week or 1))
			if a.status == "Done" and not a.done_on:
				a.done_on = today()
			if a.status != "Done":
				a.done_on = None

	def on_trash(self):
		check_cycle_open(self.cycle, self.flags)
		frappe.db.delete("Life Action Log", {"goal": self.name})
