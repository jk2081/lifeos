import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from lifeos.brain import area_guess

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
		for field in ("waiting_on_person", "delegated_to"):
			if self.get(field) and frappe.db.get_value("Life Person", self.get(field), "space") != self.space:
				frappe.throw(_("{0} must be someone in the task's space.").format(_(self.meta.get_label(field))), title=_("Person is in another space"))
		if self.status == "Waiting" and self.waiting_on_person and not (self.waiting_on or "").strip():
			self.waiting_on = frappe.db.get_value("Life Person", self.waiting_on_person, "full_name")
		if self.status == "Waiting" and not (self.waiting_on or "").strip():
			frappe.throw(_("Say who or what this task is waiting on."), frappe.MandatoryError, title=_("Waiting needs a reason"))
		if not self.flags.keep_touched:
			self.last_touched_on = today()
		if self.status != "Someday":
			self.someday_on = self.someday_review_on = None
			self.someday_with = None
		area_guess.track_change(self)  # issue 13: every task has an area

	def on_update(self):
		area_guess.after_save(self)
		# a goal's last activity follows its tasks (UX fixes, set 5: idle projects, now open-ended goals)
		if self.goal and not self.flags.keep_touched:
			frappe.db.set_value("Life Goal", self.goal, "last_activity_on", today(), update_modified=False)

	def on_trash(self):
		# its area corrections go with it, so they do not block the delete (issue 13)
		frappe.db.delete("Life Action Log", {"task": self.name, "kind": "Area correction"})
