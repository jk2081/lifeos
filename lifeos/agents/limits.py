"""What the owner lets an agent do and read (issue 85): a switch per action (on its own, asks you, off) and per area.

Plumbing only. The settings sit on one `Life Agent Config` per space and agent; the agent's connector reads them (`lifeos.api.agent_connector.pull`)
and Life OS enforces the areas itself, whatever the agent does: an area switched off is left out of every read an agent makes (`blocked`).
"""
import json

import frappe
from frappe import _

AUTO, ASK, OFF = "auto", "ask", "off"
MODES = (AUTO, ASK, OFF)
# key, what a person calls it
ACTIONS = (("read_email", "Read email"), ("send_email", "Send email"), ("change_calendar", "Change the calendar"), ("chase_people", "Chase people"),
	("use_websites", "Use websites"), ("save_files", "Save files"), ("write_pages", "Make pages and people"), ("pay", "Pay"))
DEFAULT_MODE = ASK
DEFAULT_NAME = "Your assistant"
# a doctype whose rows carry an `area`: the rows an agent cannot read when the area is off for it
AREA_DOCTYPES = ("Life Inbox Item", "Life Task", "Life Note", "Life Vault Document", "Life Chat Log", "Life Index", "Life Goal", "Life Person", "Life Habit")


def config(space: str, agent: str, create: bool = False):
	"""The agent's settings document in a space (None when it has never reported and `create` is off)."""
	name = frappe.db.get_value("Life Agent Config", {"space": space, "agent": agent})
	if name:
		return frappe.get_doc("Life Agent Config", name)
	if not create:
		return None
	doc = frappe.get_doc({"doctype": "Life Agent Config", "space": space, "agent": agent})
	doc.insert(ignore_permissions=True)  # system: the connector's own record; the space write check is in the API
	return doc


def _loads(text, default):
	try:
		value = json.loads(text) if text else default
	except ValueError:
		return default
	return value if isinstance(value, type(default)) else default


def abilities(cfg) -> dict:
	"""{action: mode} for every action; what was never set asks, and pay is always off."""
	saved = _loads(cfg.abilities, {}) if cfg else {}
	out = {key: saved.get(key) if saved.get(key) in MODES else DEFAULT_MODE for key, _label in ACTIONS}
	out["pay"] = OFF
	return out


def set_ability(cfg, action: str, mode: str) -> dict:
	if action not in dict(ACTIONS):
		frappe.throw(_("{0} is not something an agent can be given.").format(action), title=_("Unknown action"))
	if mode not in MODES:
		frappe.throw(_("Choose on its own, asks you or off."), title=_("Unknown setting"))
	if action == "pay" and mode != OFF:
		frappe.throw(_("An agent can never pay. Payments stay with you."), title=_("Pay stays off"))
	now = abilities(cfg)
	now[action] = mode
	cfg.abilities = json.dumps(now)
	cfg.save(ignore_permissions=True)  # system: only the owner reaches this, in the API
	return now


def areas_off(cfg) -> list:
	return _loads(cfg.areas_off, []) if cfg else []


def set_area(cfg, area: str, on: bool) -> list:
	if not frappe.db.exists("Life Area", {"name": area, "space": cfg.space}):
		frappe.throw(_("That area is not in this space."), frappe.DoesNotExistError, title=_("Area not found"))
	now = set(areas_off(cfg))
	now.discard(area) if on else now.add(area)
	cfg.areas_off = json.dumps(sorted(now))
	cfg.save(ignore_permissions=True)  # system: only the owner reaches this, in the API
	return sorted(now)


def _below(space: str, names: set) -> set:
	"""The areas switched off and everything under them (their parts, and the focuses of those parts)."""
	rows = frappe.get_all("Life Area", filters={"space": space}, fields=["name", "parent_area"], limit=5000)  # system: the permission layer itself
	out = set(names)
	while True:
		more = {r.name for r in rows if r.parent_area in out and r.name not in out}
		if not more:
			return out
		out |= more


def blocked(space: str | None = None, user: str | None = None) -> list:
	"""The areas (names) the signed-in agent may not read, in one space or in all of its spaces; empty for a person."""
	from lifeos import permissions

	user = user or frappe.session.user
	if user == "Administrator" or not permissions.is_agent(user):
		return []
	filters = {"agent_user": user, **({"space": space} if space else {})}
	out = set()
	for row in frappe.get_all("Life Agent Config", filters=filters, fields=["space", "areas_off"]):  # system: the permission layer itself
		off = set(_loads(row.areas_off, []))
		if off:
			out |= _below(row.space, off)
	return sorted(out)


def area_condition(doctype: str, blocked_areas: list) -> str:
	"""The SQL a permission query adds so an agent does not read rows under an area that is off for it."""
	if not blocked_areas:
		return ""
	names = ", ".join(frappe.db.escape(a) for a in blocked_areas)
	column = "name" if doctype == "Life Area" else "area"
	return f" and ifnull(`tab{doctype}`.`{column}`, '') not in ({names})"


def display_name(cfg) -> str:
	return (cfg.display_name if cfg and cfg.display_name else "").strip() or DEFAULT_NAME
