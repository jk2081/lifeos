import frappe
from frappe import _
from frappe.model.document import Document


class (Document):
	def validate(self):
		self. = (self. or "").strip()
		if frappe.db.get_value(self.doctype, {"space": self.space, "": self., "name": ("!=", self.name or "")}):
			frappe.throw(_("This space already has a  named {0}.").format(self.), frappe.DuplicateEntryError)
