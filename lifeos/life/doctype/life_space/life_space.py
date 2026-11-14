import frappe
from frappe import _
from frappe.model.document import Document


class LifeSpace(Document):
	def validate(self):
		if not self.owner_user:
			self.owner_user = frappe.session.user
		seen = set()
		for m in self.members:
			if m.user in seen:
				frappe.throw(_("{0} is listed twice.").format(m.user))
			seen.add(m.user)
		if self.owner_user not in seen:
			self.append("members", {"user": self.owner_user, "access": "Write"})

	def on_update(self):
		from lifeos import permissions
		permissions.clear_cache()

	def on_trash(self):
		if frappe.db.exists("Life Index", {"space": self.name}) or frappe.db.exists("Life Area", {"space": self.name}):
			frappe.throw(_("This space still holds records. Move or delete them first."))
		from lifeos import permissions
		permissions.clear_cache()
