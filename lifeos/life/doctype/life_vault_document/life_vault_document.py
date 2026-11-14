import re

import frappe
from frappe import _
from frappe.model.document import Document

LONG_NUMBER = re.compile(r"(?:\d[ -]?){9,}")


class LifeVaultDocument(Document):
	def validate(self):
		self.number_last4 = (self.number_last4 or "").strip()
		if len(self.number_last4) > 4:
			frappe.throw(_("Store only the last four characters of a number."), frappe.ValidationError)
		# a full identity, card or account number must never sit in a field
		for field in ("title", "notes_md"):
			if LONG_NUMBER.search(self.get(field) or ""):
				frappe.throw(_("{0} looks like it holds a full number. Keep only the last four characters.").format(self.meta.get_label(field)), frappe.ValidationError)
		if self.remind_days_before is None:
			self.remind_days_before = 60
		if self.is_archived and self.archive_reason == "Auto":
			frappe.throw(_("Vault documents are never auto-archived."))
