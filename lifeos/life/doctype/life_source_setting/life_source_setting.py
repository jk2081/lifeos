import frappe
from frappe import _
from frappe.model.document import Document


class LifeSourceSetting(Document):
	def validate(self):
		self.source = (self.source or "").strip().lower()
		if not self.source:
			frappe.throw(_("A source setting needs a source."), title=_("Source setting needs a source"))
		self.auto_file_confidence = min(max(int(self.auto_file_confidence if self.auto_file_confidence is not None else 80), 0), 100)
		if frappe.db.exists("Life Source Setting", {"space": self.space, "source": self.source, "name": ["!=", self.name or ""]}):
			frappe.throw(_("{0} already has settings in this space.").format(self.source), frappe.DuplicateEntryError, title=_("Source settings already exist"))
