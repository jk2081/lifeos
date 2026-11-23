import frappe
from frappe import _
from frappe.model.document import Document

from lifeos.life.doctype.life_goal.life_goal import check_cycle_open

AREA_CORRECTION = "Area correction"


class LifeActionLog(Document):
	"""A dated tick of a 12 Week Year action, or (issue 13) the owner's correction of an area the Brain guessed for a task."""

	def autoname(self):
		if self.kind == AREA_CORRECTION:
			self.name = f"area-{self.task}-{frappe.generate_hash(length=8)}"
		else:
			self.name = f"{self.action_id}-{self.date}"

	def before_validate(self):
		if self.goal and not self.space:
			self.space = frappe.db.get_value("Life Goal", self.goal, "space")
		if self.task and not self.space:
			self.space = frappe.db.get_value("Life Task", self.task, "space")

	def validate(self):
		if self.kind == AREA_CORRECTION:
			if not (self.task and self.new_area):
				frappe.throw(_("An area correction names the task and the area it moved to."), frappe.MandatoryError, title=_("Correction is incomplete"))
			return
		for field in ("goal", "action_id", "cycle", "week"):
			if not self.get(field) and self.get(field) != 0:
				frappe.throw(_("{0} is required.").format(_(self.meta.get_label(field))), frappe.MandatoryError, title=_("Field is required"))
		check_cycle_open(self.cycle, self.flags)

	def on_trash(self):
		if self.kind != AREA_CORRECTION:
			check_cycle_open(self.cycle, self.flags)
