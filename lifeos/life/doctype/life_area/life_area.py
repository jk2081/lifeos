import frappe
from frappe import _
from frappe.model.document import Document


class LifeArea(Document):
	def validate(self):
		self.area_name = (self.area_name or "").strip()
		if self.parent_area and self.parent_area == self.name:
			frappe.throw(_("An area cannot be its own parent."))
		clash = frappe.db.get_value("Life Area", {
			"space": self.space, "area_name": self.area_name, "parent_area": self.parent_area or ("is", "not set"),
			"name": ("!=", self.name or ""),
		})
		if clash:
			frappe.throw(_("This space already has an area named {0} here.").format(self.area_name), frappe.DuplicateEntryError)
		seen, parent = {self.name}, self.parent_area
		while parent:
			if parent in seen:
				frappe.throw(_("Areas cannot form a loop."))
			seen.add(parent)
			parent = frappe.db.get_value("Life Area", parent, "parent_area")
