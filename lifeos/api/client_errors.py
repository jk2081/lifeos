"""Screens that fail to render in the browser (bug fix 1). The front end's error boundary sends what failed here, so it
lands in Frappe's Error Log under a short reference the owner can quote. Only the error itself is kept: its message,
stack, the screen's path without its query, the component and Vue's error code. No record contents are sent or stored."""
import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from lifeos import permissions

TITLE = "Life OS screen error"
LIMITS = {"reference": 16, "path": 200, "message": 500, "stack": 4000, "component": 80, "info": 80, "kind": 20}


def _clip(value, size):
	return str(value or "").strip()[:size]


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60 * 60, user_based=True)
def log(reference: str, message: str, stack: str = "", path: str = "", component: str = "", info: str = "",
	kind: str = "render") -> dict:
	"""Write one screen error to the Error Log. Logged-in users only; at most 30 an hour per user."""
	permissions.require_login()
	path = _clip(path, LIMITS["path"]).split("?", 1)[0].split("#", 1)[0]
	fields = {"reference": _clip(reference, LIMITS["reference"]), "kind": _clip(kind, LIMITS["kind"]), "path": path,
		"component": _clip(component, LIMITS["component"]), "info": _clip(info, LIMITS["info"]), "user": frappe.session.user}
	if not fields["reference"]:
		frappe.throw(_("An error reference is required."), title=_("Error reference missing"))
	lines = [f"{k}: {v}" for k, v in fields.items()]
	body = "\n".join([*lines, "", _clip(message, LIMITS["message"]), "", _clip(stack, LIMITS["stack"])])
	frappe.log_error(title=f"{TITLE} {fields['reference']}", message=body)
	return {"reference": fields["reference"]}
