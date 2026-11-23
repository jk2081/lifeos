import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate


class LifeCycle(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if before and before.status == "Closed" and not self.flags.allow_closed:
			frappe.throw(_("A closed cycle is read-only."), title=_("Cycle already closed"))
		self.end_date = add_days(getdate(self.start_date), 83)
		if self.status == "Active":
			other = frappe.db.get_value("Life Cycle", {"space": self.space, "status": "Active", "name": ("!=", self.name or "")})
			if other:
				frappe.throw(_("This space already has an active cycle. Close it first."), title=_("Space already has a cycle"))

	def on_trash(self):
		if self.status == "Closed" and not self.flags.allow_closed:
			frappe.throw(_("A closed cycle is read-only."), title=_("Cycle already closed"))
