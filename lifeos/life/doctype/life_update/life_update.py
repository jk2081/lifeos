import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

COMMIT = re.compile(r"^[0-9a-f]{40}$")


class LifeUpdate(Document):
	def before_insert(self):
		"""A request carries only a commit; who asked and when, and Queued, are set here, never by the caller."""
		self.to_commit = (self.to_commit or "").strip().lower()
		if not COMMIT.match(self.to_commit):
			frappe.throw(_("An update names one commit, 40 hexadecimal characters."), title=_("Not a commit"))
		self.requested_by = frappe.session.user
		self.requested_on = now_datetime()
		self.status = "Queued"
		self.log = self.started = self.finished = None
		if not self.from_commit:
			from lifeos.updater import status

			self.from_commit = (status.state().get("installed") or {}).get("commit")
