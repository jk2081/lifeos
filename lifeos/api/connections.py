"""Connections (UX fixes, set 4): one row per space and outside system (gmail, claude, chatgpt, google-calendar) with the
defaults agents use when filing what arrives from it, and when something last arrived. No credentials are stored here:
the agents hold their own access."""
import frappe
from frappe import _
from frappe.utils import add_to_date, getdate, now_datetime, nowdate

from lifeos import permissions
from lifeos.api.utils import flag

INTENTS = ("Process", "Add to wiki", "Just keep")
# how long without anything new before a connection shows a warning, by system (hours)
QUIET_HOURS = {"gmail": 48, "claude": 48, "chatgpt": 48, "email": 48}
DEFAULT_QUIET_HOURS = 24 * 7


# What can be switched on in Brain > Sources (issue 19). `system` is the connection's key and the `source_system` an agent sends.
# kind is the second line of its card; note is said after this week's count. Upload is always on and has no connection row.
CATALOG = {
	"gmail": {"label": "Gmail", "kind": "Email · Read only", "hint": "Email from real people", "note": "only people, not newsletters", "icon": "M"},
	"google-calendar": {"label": "Google Calendar", "kind": "Read only", "hint": "Meetings and events", "icon": "31"},
	"hermes": {"label": "Hermes", "kind": "Agent · Telegram", "hint": "Captures and finished work", "icon": "H"},
	"claude": {"label": "Claude chats", "kind": "Chat export · Nightly", "hint": "Chats summarised", "icon": "C"},
	"chatgpt": {"label": "ChatGPT chats", "kind": "Chat export", "hint": "Chats summarised", "icon": "G"},
	"openclaw": {"label": "OpenClaw", "kind": "Agent", "hint": "An agent that files for you", "icon": "O"},
}
UPLOAD = {"label": "Upload", "kind": "Always on", "hint": "Files, photos, voice and text you add yourself", "icon": "U"}
# shown as "Coming" tiles: not built, so they cannot be switched on
COMING = {"github": ("GitHub", "PRs and issues"), "whatsapp": ("WhatsApp", "Starred chats"), "wearable": ("Wearable", "Voice all day"),
	"tally": ("Tally", "Overdue bills"), "drive": ("Drive", "Shared docs"), "erpnext": ("ERPNext", "Overdue orders and approvals")}
ALWAYS_ON = ("upload", "phone")


def require_on(space, system):
	"""Refuse a capture from a source that is switched off in Brain > Sources. Upload is always on; a system never connected is allowed."""
	system = (system or "").strip().lower()
	if not system or system in ALWAYS_ON:
		return
	c = connection(space, system)
	if c and not c.active:
		frappe.throw(_("{0} is switched off in Brain, Sources, so Life OS is not accepting captures from it. Switch it on there to continue.")
			.format(c.label or system.title()), frappe.PermissionError)


def connection(space, system):
	system = (system or "").strip().lower()
	if not system:
		return None
	return frappe.db.get_value("Life Connection", {"space": space, "system": system},
		["name", "system", "label", "default_area", "default_goal", "default_intent", "active", "last_received_on", "last_received_what"], as_dict=True)


def touch(space, system, what=None):
	"""Something arrived from a system: note when, creating the connection row on first contact."""
	system = (system or "").strip().lower()
	if not system or system == "phone":  # the phone is the person's own device, not a connection to switch on or off (issue 50)
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
	goal = frappe.db.get_value("Life Goal", c.default_goal, "title") if c.default_goal else None
	hours = QUIET_HOURS.get(c.system, DEFAULT_QUIET_HOURS)
	quiet = bool(c.active and (not c.last_received_on or c.last_received_on < add_to_date(now_datetime(), hours=-hours)))
	return {"name": c.name, "system": c.system, "label": c.label or c.system.title(), "default_area": c.default_area, "default_area_name": area,
		"default_goal": c.default_goal, "default_goal_title": goal, "default_intent": c.default_intent or "Process",
		"active": int(c.active or 0), "last_received_on": str(c.last_received_on) if c.last_received_on else None,
		"last_received_what": c.last_received_what, "quiet": quiet, "quiet_hours": hours}


def _week_start():
	d = getdate(nowdate())
	return add_to_date(d, days=-d.weekday())


def _week_counts(space, system):
	"""Captures that came in from `system` since Monday: all of them, and how many were a finished piece of work (a job)."""
	if system == "upload":
		cond, args = "(source_system is null or source_system in ('', 'upload'))", []
	else:
		cond, args = "source_system = %s", [system]
	n, jobs = frappe.db.sql(f"select count(*), coalesce(sum(job_id is not null and job_id != ''), 0) from `tabLife Inbox Item` "
		f"where space = %s and creation >= %s and {cond}", [space, _week_start(), *args])[0]
	return int(n), int(jobs)


def _card(space, row):
	"""One connected source for the Sources screen: its look, whether it is on, and what came in this week."""
	meta = CATALOG.get(row.system) or {}
	n, jobs = _week_counts(space, row.system)
	counts = [f"{n} this week" if not jobs else f"{n - jobs} captures · {jobs} piece{'s' if jobs != 1 else ''} of work filed"]
	if meta.get("note"):
		counts.append(meta["note"])
	out = _out(row)
	return {**out, "kind": meta.get("kind") or "Agent", "icon": meta.get("icon") or out["label"][:1].upper(), "this_week": n, "line": " · ".join(counts)}


@frappe.whitelist(methods=["GET"])
def sources(space: str | None = None):
	"""Brain > Sources. `connected`: one card for each connected source (system, label, kind, active, this_week, line and its defaults).
	`available`: sources that can be added (Upload, always on, first), each with `always_on`; those already connected are left out.
	`coming`: sources not built yet; they cannot be switched on."""
	space = permissions.resolve_space(space)
	fields = ["name", "system", "label", "default_area", "default_goal", "default_intent", "active", "last_received_on", "last_received_what"]
	rows = frappe.get_all("Life Connection", filters={"space": space}, fields=fields, order_by="creation asc")
	have = {r.system for r in rows}
	available = [{"system": "upload", "label": UPLOAD["label"], "hint": UPLOAD["hint"], "always_on": 1, "this_week": _week_counts(space, "upload")[0]}]
	available += [{"system": k, "label": v["label"], "hint": v["hint"], "always_on": 0} for k, v in CATALOG.items() if k not in have]
	return {"space": space, "connected": [_card(space, r) for r in rows], "available": available,
		"coming": [{"system": k, "label": v[0], "hint": v[1]} for k, v in COMING.items()]}


@frappe.whitelist(methods=["GET"])
def defaults(space: str | None = None, system: str | None = None):
	"""The filing defaults for what arrives from `system` in `space`: default_area, default_goal, default_intent and active.
	A system with no connection row answers Process with no area or goal."""
	space = permissions.resolve_space(space)
	c = connection(space, system)
	if not c:
		return {"system": (system or "").lower(), "default_area": None, "default_goal": None, "default_intent": "Process",
			"active": 1, "known": 0}
	return {**_out(c), "known": 1}


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None):
	"""Every connection of a space, with its defaults, when something last arrived and whether it has been quiet too long."""
	space = permissions.resolve_space(space)
	rows = frappe.get_all("Life Connection", filters={"space": space},
		fields=["name", "system", "label", "default_area", "default_goal", "default_intent", "active", "last_received_on", "last_received_what"],
		order_by="label asc, system asc")
	return {"space": space, "connections": [_out(r) for r in rows]}


@frappe.whitelist(methods=["POST"])
def save(space: str | None = None, system: str | None = None, name: str | None = None, label: str | None = None,
		default_area: str | None = None, default_goal: str | None = None, default_intent: str | None = None,
		active: bool | int | None = None):
	"""Create or change a connection. People with Write access only; agents read the defaults and cannot change them."""
	if permissions.is_agent():
		frappe.throw(_("Only a person can change a connection."), frappe.PermissionError)
	if name:
		doc = permissions.get_doc_checked("Life Connection", name, "write")
		if doc.system in COMING and active is not None and flag(active):
			frappe.throw(_("{0} is not built yet, so it cannot be switched on.").format(COMING[doc.system][0]))
	else:
		space = permissions.resolve_space(space, write=True)
		key = (system or "").strip().lower()
		if key in COMING:
			frappe.throw(_("{0} is not built yet, so it cannot be switched on.").format(COMING[key][0]))
		doc = frappe.get_doc({"doctype": "Life Connection", "space": space, "system": system, "label": CATALOG.get(key, {}).get("label")})
	if label is not None:
		doc.label = label
	if default_area is not None:
		doc.default_area = default_area or None
	if default_goal is not None:
		doc.default_goal = default_goal or None
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
	require_on(space, system)
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
