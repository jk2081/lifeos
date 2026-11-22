"""Names that were removed when projects were removed (issue 48): a call that still uses one gets a clear error.

Frappe drops an argument a method does not declare without a word, so a caller that still sent `project` would have
it ignored and file nothing under the goal. `before_request` refuses such a call instead.
"""

import frappe
from frappe import _

GONE = {"project": "goal", "default_project": "default_goal"}


def refuse(values) -> None:
	"""Raise a ValidationError that names the replacement when `values` (a dict of arguments) holds a removed name."""
	for old, new in GONE.items():
		if values and old in values:
			frappe.throw(_("Projects are goals now: send `{0}`, not `{1}`.").format(new, old), frappe.ValidationError)


def before_request() -> None:
	request = getattr(frappe.local, "request", None)
	if not request or not request.path.startswith(("/api/method/lifeos.", "/api/v2/method/lifeos.")):
		return
	refuse(frappe.local.form_dict)
