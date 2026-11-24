import frappe
from frappe import _
from frappe.model.document import Document


class LifeConnection(Document):
	def validate(self):
		self.system = (self.system or "").strip().lower()
		if not self.system:
			frappe.throw(_("A connection needs a system, for example gmail."), title=_("Connection needs a system"))
		self.label = (self.label or "").strip() or self.system.title()
		self.default_intent = self.default_intent or "Process"
		other = {"space": self.space, "system": self.system, "name": ["!=", self.name or ""]}
		if self.system in ("gmail", "microsoft"):  # several mailboxes, one card each (issues 58 and 88)
			if self.mailbox:
				other["mailbox"] = self.mailbox
			elif self.connected_app:  # a sign-in under way
				return
			else:  # the bare row of defaults for what agents file as gmail: one for a space
				other["mailbox"], other["connected_app"] = ["is", "not set"], ["is", "not set"]
		if frappe.db.get_value("Life Connection", other):
			frappe.throw(_("This space already has a connection for {0}.").format(self.mailbox or self.system), frappe.DuplicateEntryError, title=_("Connection already exists"))
