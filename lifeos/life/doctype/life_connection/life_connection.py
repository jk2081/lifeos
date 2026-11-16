import frappe
from frappe import _
from frappe.model.document import Document


class LifeConnection(Document):
	def validate(self):
		self.system = (self.system or "").strip().lower()
		if not self.system:
			frappe.throw(_("A connection needs a system, for example gmail."))
		self.label = (self.label or "").strip() or self.system.title()
		self.default_intent = self.default_intent or "Process"
		if frappe.db.get_value("Life Connection", {"space": self.space, "system": self.system, "name": ["!=", self.name or ""]}):
			frappe.throw(_("This space already has a connection for {0}.").format(self.system), frappe.DuplicateEntryError)
