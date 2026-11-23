import json

import frappe
from frappe import _
from frappe.model.document import Document


class LifeProposal(Document):
	def before_validate(self):
		if self.inbox_item and not self.space:
			self.space = frappe.db.get_value("Life Inbox Item", self.inbox_item, "space")
		if isinstance(self.payload, (dict, list)):
			self.payload = json.dumps(self.payload)

	def before_insert(self):
		self.guess = self.payload  # what was first proposed; the owner's changes to the payload are told from it (skills/lessons.py)

	def validate(self):
		from lifeos import permissions

		if self.confidence is not None and not (0 <= float(self.confidence or 0) <= 1):
			frappe.throw(_("Confidence must be between 0 and 1."), title=_("Confidence out of range"))
		decided = (self.is_new() and self.status != "Pending") or (not self.is_new() and self.has_value_changed("status"))
		if decided and not self.flags.via_review:
			if permissions.is_agent():
				frappe.throw(_("Agents cannot accept or reject proposals."), frappe.PermissionError, title=_("Agents cannot decide proposals"))
			frappe.throw(_("Use review.decide to accept or reject a proposal."), title=_("Decide through review"))
		if not self.is_new() and self.get_doc_before_save() and self.get_doc_before_save().status != "Pending" and not self.flags.via_review:
			frappe.throw(_("A decided proposal cannot be changed."), title=_("Proposal already decided"))

	def payload_dict(self) -> dict:
		if not self.payload:
			return {}
		return json.loads(self.payload) if isinstance(self.payload, str) else dict(self.payload)
