"""Remembered list views: one saved state per user, per screen, per space."""
import json

import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.utils import parse

MAX_STATE = 20000  # characters of JSON; a state is filters, sort, columns and a view name
MAX_SCREEN = 60


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Agents have no saved views."), frappe.PermissionError)
	return frappe.session.user


@frappe.whitelist(methods=["GET"])
def get_all():
	"""Every saved list state of the session user, as {"<screen>|<space>": state}. Read once when the app starts."""
	user = _person()
	spaces = permissions.user_spaces(user)
	out = {}
	for row in frappe.get_all("Life View State", filters={"user": user}, fields=["screen", "space", "state"], limit=500, ignore_permissions=True):
		if row.space and row.space not in spaces and user != "Administrator":
			continue  # a space the user has since left
		state = parse(row.state, {})
		if isinstance(state, dict):
			out[f"{row.screen}|{row.space or ''}"] = state
	return out


@frappe.whitelist(methods=["POST"])
def save(screen: str, space: str | None = None, state: str | dict | None = None):
	"""Save the state of one screen in one space for the session user. It replaces what was saved before."""
	user = _person()
	screen = str(screen or "").strip()
	if not screen or len(screen) > MAX_SCREEN:
		frappe.throw(_("screen is required."), frappe.ValidationError)
	if space:
		permissions.require_space(space)
	state = parse(state, {})
	if not isinstance(state, dict):
		frappe.throw(_("state must be an object."), frappe.ValidationError)
	state.pop("open", None)  # the open record is never saved
	text = json.dumps(state, separators=(",", ":"))
	if len(text) > MAX_STATE:
		frappe.throw(_("This view is too large to save."), frappe.ValidationError)
	name = frappe.db.get_value("Life View State", {"user": user, "screen": screen, "space": space or ("is", "not set")}, "name")
	if name:
		frappe.db.set_value("Life View State", name, "state", text)
	else:
		frappe.get_doc({"doctype": "Life View State", "user": user, "screen": screen, "space": space or None, "state": text}).insert(ignore_permissions=True)
	return {"screen": screen, "space": space or "", "saved": True}
