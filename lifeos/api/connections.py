"""Connections (UX fixes, set 4): one row per space and outside system (gmail, claude, chatgpt, google-calendar) with the
defaults agents use when filing what arrives from it, and when something last arrived. No credentials are stored here:
the agents hold their own access."""
import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from lifeos import permissions
from lifeos.api.utils import flag

INTENTS = ("Process", "Add to wiki", "Just keep")
# how long without anything new before a connection shows a warning, by system (hours)
QUIET_HOURS = {"gmail": 48, "claude": 48, "chatgpt": 48, "email": 48}
DEFAULT_QUIET_HOURS = 24 * 7


def connection(space, system):
	system = (system or "").strip().lower()
	if not system:
		return None
	return frappe.db.get_value("Life Connection", {"space": space, "system": system},
		["name", "system", "label", "default_area", "default_project", "default_intent", "active", "last_received_on", "last_received_what"], as_dict=True)


def touch(space, system, what=None):
	"""Something arrived from a system: note when, creating the connection row on first contact."""
	system = (system or "").strip().lower()
	if not system:
		return
	name = frappe.db.get_value("Life Connection", {"space": space, "system": system})
	values = {"last_received_on": now_datetime(), "last_received_what": (what or "")[:140]}
	if name:
		frappe.db.set_value("Life Connection", name, values, update_modified=False)
	else:
		frappe.get_doc({"doctype": "Life Connection", "space": space, "system": system, "active": 1, **values}).insert(ignore_permissions=True)


def _out(c):
	if not c:
		return None
	area = frappe.db.get_value("Life Area", c.default_area, "area_name") if c.default_area else None
	project = frappe.db.get_value("Life Project", c.default_project, "title") if c.default_project else None
	hours = QUIET_HOURS.get(c.system, DEFAULT_QUIET_HOURS)
	quiet = bool(c.active and (not c.last_received_on or c.last_received_on < add_to_date(now_datetime(), hours=-hours)))
	return {"name": c.name, "system": c.system, "label": c.label or c.system.title(), "default_area": c.default_area, "default_area_name": area,
		"default_project": c.default_project, "default_project_title": project, "default_intent": c.default_intent or "Process",
		"active": int(c.active or 0), "last_received_on": str(c.last_received_on) if c.last_received_on else None,
		"last_received_what": c.last_received_what, "quiet": quiet, "quiet_hours": hours}


@frappe.whitelist(methods=["GET"])
def defaults(space: str | None = None, system: str | None = None):
	"""The filing defaults for what arrives from `system` in `space`: default_area, default_project, default_intent and active.
	A system with no connection row answers Process with no area or project."""
	space = permissions.resolve_space(space)
	c = connection(space, system)
	if not c:
		return {"system": (system or "").lower(), "default_area": None, "default_project": None, "default_intent": "Process", "active": 1, "known": 0}
	return {**_out(c), "known": 1}


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None):
	"""Every connection of a space, with its defaults, when something last arrived and whether it has been quiet too long."""
	space = permissions.resolve_space(space)
	rows = frappe.get_all("Life Connection", filters={"space": space},
		fields=["name", "system", "label", "default_area", "default_project", "default_intent", "active", "last_received_on", "last_received_what"],
		order_by="label asc, system asc")
	return {"space": space, "connections": [_out(r) for r in rows]}


@frappe.whitelist(methods=["POST"])
def save(space: str | None = None, system: str | None = None, name: str | None = None, label: str | None = None,
		default_area: str | None = None, default_project: str | None = None, default_intent: str | None = None,
		active: bool | int | None = None):
	"""Create or change a connection. People with Write access only; agents read the defaults and cannot change them."""
	if permissions.is_agent():
		frappe.throw(_("Only a person can change a connection."), frappe.PermissionError)
	if name:
		doc = permissions.get_doc_checked("Life Connection", name, "write")
	else:
		space = permissions.resolve_space(space, write=True)
		doc = frappe.get_doc({"doctype": "Life Connection", "space": space, "system": system})
	if label is not None:
		doc.label = label
	if default_area is not None:
		doc.default_area = default_area or None
	if default_project is not None:
		doc.default_project = default_project or None
	if default_intent is not None:
		if default_intent not in INTENTS:
			frappe.throw(_("default_intent must be one of: {0}.").format(", ".join(INTENTS)))
		doc.default_intent = default_intent
	if active is not None:
		doc.active = 1 if flag(active) else 0
	doc.save() if name else doc.insert()
	return _out(connection(doc.space, doc.system))


# ---------- chat export import ----------

@frappe.whitelist(methods=["POST"])
def start_import(space: str | None = None, system: str | None = None, file_url: str | None = None):
	"""Import a Claude (system=claude) or ChatGPT (system=chatgpt) data export: the .zip uploaded as a private file.
	It runs in a background job; import_status shows its progress. People with Write access only."""
	from lifeos import chat_import

	if permissions.is_agent():
		frappe.throw(_("Only a person can import a chat export."), frappe.PermissionError)
	space = permissions.resolve_space(space, write=True)
	system = (system or "").strip().lower()
	if system not in chat_import.SYSTEMS:
		frappe.throw(_("system must be claude or chatgpt."))
	f = frappe.db.get_value("File", {"file_url": file_url}, ["name", "is_private", "file_name"], as_dict=True)
	if not f:
		frappe.throw(_("Upload the export first."))
	frappe.get_doc("File", f.name).check_permission("read")
	if not f.is_private:
		frappe.throw(_("The export must be stored as a private file."))
	cur = chat_import.progress(space, system)
	if cur and cur.get("status") in ("Reading", "Importing") and cur.get("started_on") and \
			frappe.utils.get_datetime(cur["started_on"]) > add_to_date(now_datetime(), hours=-2):
		frappe.throw(_("An import of this kind is already running in this space."))
	chat_import._set(space, system, status="Queued", file_name=f.file_name, error=None, user=frappe.session.user, started_on=str(now_datetime())[:19])
	frappe.enqueue("lifeos.chat_import.run", queue="long", timeout=4 * 3600, space=space, system=system, file_url=file_url,
		user=frappe.session.user, now=bool(frappe.flags.in_test or frappe.flags.lifeos_import_now))
	return chat_import.progress(space, system)


@frappe.whitelist(methods=["GET"])
def import_status(space: str | None = None, system: str | None = None):
	"""The progress of the last chat import of this kind in this space: status (Queued, Reading, Importing, Done, Failed),
	done and total, and the counts created, updated, unchanged and skipped (could not be read)."""
	from lifeos import chat_import

	space = permissions.resolve_space(space)
	return chat_import.progress(space, (system or "").lower()) or {"status": None}
