"""Connections (UX fixes, set 4): one row per space and outside system (gmail, claude, chatgpt, google-calendar) with the
defaults agents use when filing what arrives from it, and when something last arrived. No credentials are stored here: an
agent holds its own access, and Life OS's own read of Gmail (issue 58, `lifeos/gmail.py`) keeps its token in Frappe's Token Cache,
one mailbox for each Gmail card."""
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

# Where each source goes (issue 58): who processes what it brings, and where it lands. Everything not listed here is an agent's.
BRAIN_SOURCES = ("upload", "phone", "gmail", "email")
KEPT_AS_IS = ("claude", "chatgpt", "google-calendar")
LANDS = {
	"upload": "Needs you, or filed on its own; then tasks, notes and dates. The capture stays on its page and in Activity.",
	"gmail": "Needs you, or filed on its own; then tasks, notes and dates. The capture stays on its page and in Activity.",
	"claude": "Library, Chats. Open items become tasks only with Make task.",
	"chatgpt": "Library, Chats. Open items become tasks only with Make task.",
	"google-calendar": "Today and the calendar views, and meetings in the review (not captures).",
}
AGENT_LANDS = "The same, plus wiki pages and the chat log."


def brain_is_on() -> bool:
	return bool(frappe.db.get_value("Life Skill", "process-capture", "active"))


def processed_by(system: str, label: str | None = None) -> str:
	"""The line on a source's card: who processes what comes from it."""
	system = (system or "").lower()
	if system in KEPT_AS_IS:
		return _("Not processed: kept as is")
	if system in BRAIN_SOURCES:
		return _("Processed by: the Brain") if brain_is_on() else _("Processed by: your agent (the Brain is switched off)")
	return _("Processed by: {0}").format(label or system.title())


def require_on(space, system):
	"""Refuse a capture from a source that is switched off in Brain > Sources. Upload is always on; a system never connected is allowed."""
	system = (system or "").strip().lower()
	if not system or system in ALWAYS_ON:
		return
	c = connection(space, system)
	if c and not c.active:
		frappe.throw(_("{0} is switched off in Brain, Sources, so Life OS is not accepting captures from it. Switch it on there to continue.")
			.format(c.label or system.title()), frappe.PermissionError, title=_("Source is switched off"))


def connection(space, system):
	system = (system or "").strip().lower()
	if not system:
		return None
	# several Gmail mailboxes share the system "gmail": one that is on answers for it
	return frappe.db.get_value("Life Connection", {"space": space, "system": system},
		["name", "system", "label", "default_area", "default_goal", "default_intent", "active", "last_received_on", "last_received_what"], as_dict=True,
		order_by="active desc, creation asc")


def touch(space, system, what=None):
	"""Something arrived from a system: note when, creating the connection row on first contact."""
	system = (system or "").strip().lower()
	if not system or system == "phone":  # the phone is the person's own device, not a connection to switch on or off (issue 50)
		return
	name = frappe.flags.lifeos_touch_connection or frappe.db.get_value("Life Connection", {"space": space, "system": system})
	values = {"last_received_on": now_datetime(), "last_received_what": (what or "")[:140]}
	if name:
		frappe.db.set_value("Life Connection", name, values, update_modified=False)
	else:
		frappe.get_doc({"doctype": "Life Connection", "space": space, "system": system, "active": 1, **values}).insert(ignore_permissions=True)  # system: admin-only screen; the space write check is above


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


GMAIL_FIELDS = ["mailbox", "connected_app", "label_name", "always_include", "always_skip", "always_sensitive", "attach_files", "last_error",
	"seen_week", "kept_week", "week_start"]
FIELDS = ["name", "system", "label", "default_area", "default_goal", "default_intent", "active", "last_received_on", "last_received_what"]


def _card(space, row):
	"""One connected source for the Sources screen: its look, whether it is on, what came in this week, and who processes it."""
	meta = CATALOG.get(row.system) or ({"label": "Email", "kind": "Email · Forwarded", "icon": "@"} if row.system == "email" else {})
	out = _out(row)
	if row.system == "gmail" and (row.connected_app or row.mailbox):  # one Life OS reads itself; a bare gmail row is only the defaults for what agents file
		return _gmail_card(row, out, meta)
	n, jobs = _week_counts(space, row.system)
	counts = [f"{n} this week" if not jobs else f"{n - jobs} captures · {jobs} piece{'s' if jobs != 1 else ''} of work filed"]
	if meta.get("note"):
		counts.append(meta["note"])
	return {**out, "kind": meta.get("kind") or "Agent", "icon": meta.get("icon") or out["label"][:1].upper(), "this_week": n, "line": " · ".join(counts),
		"processed_by": processed_by(row.system, out["label"]), "lands": LANDS.get(row.system, AGENT_LANDS)}


def _gmail_card(row, out, meta):
	"""A mailbox: "218 this week · 31 kept" (counted since Monday), its lists and settings, and an error when Google refused."""
	this_week = row.week_start and getdate(row.week_start) == getdate(_week_start())
	seen, kept = (row.seen_week or 0, row.kept_week or 0) if this_week else (0, 0)
	pending = not row.mailbox
	line = _("Waiting for you to finish signing in with Google.") if pending else f"{seen} this week · {kept} kept"
	return {**out, "kind": meta["kind"], "icon": meta["icon"], "this_week": kept, "line": line, "pending": int(pending), "mailbox": row.mailbox,
		"label_name": row.label_name or "", "always_include": row.always_include or "", "always_skip": row.always_skip or "",
		"always_sensitive": row.always_sensitive or "", "attach_files": int(row.attach_files or 0), "error": row.last_error,
		"processed_by": processed_by("gmail"), "lands": LANDS["gmail"], "seen_week": seen, "kept_week": kept}


@frappe.whitelist(methods=["GET"])
def sources(space: str | None = None):
	"""Brain > Sources. `connected`: one card for each connected source (system, label, kind, active, this_week, line, processed_by,
	lands and its defaults); `email_in`: the forwarding address, its allowed senders and how to use it (issue 32); each Gmail mailbox is its own card. `available`: sources that can be added (Upload, always on, first), each
	with `always_on`; those already connected are left out, except Gmail, which can be connected again for another mailbox.
	`coming`: sources not built yet; they cannot be switched on."""
	space = permissions.resolve_space(space)
	rows = frappe.get_list("Life Connection", filters={"space": space}, fields=FIELDS + GMAIL_FIELDS, order_by="creation asc")
	have = {r.system for r in rows}
	available = [{"system": "upload", "label": UPLOAD["label"], "hint": UPLOAD["hint"], "always_on": 1, "this_week": _week_counts(space, "upload")[0],
		"processed_by": processed_by("upload"), "lands": LANDS["upload"]}]
	available += [{"system": k, "label": v["label"], "hint": "Connect Gmail" if k == "gmail" else v["hint"], "always_on": 0,
		"processed_by": processed_by(k, v["label"])} for k, v in CATALOG.items() if k not in have or k == "gmail"]
	from lifeos import email_in

	return {"space": space, "connected": [_card(space, r) for r in rows], "available": available, "email_in": email_in.info(),
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
	rows = frappe.get_list("Life Connection", filters={"space": space},
		fields=["name", "system", "label", "default_area", "default_goal", "default_intent", "active", "last_received_on", "last_received_what"],
		order_by="label asc, system asc")
	return {"space": space, "connections": [_out(r) for r in rows]}


@frappe.whitelist(methods=["POST"])
def save(space: str | None = None, system: str | None = None, name: str | None = None, label: str | None = None,
		default_area: str | None = None, default_goal: str | None = None, default_intent: str | None = None,
		active: bool | int | None = None, label_name: str | None = None, always_include: str | None = None, always_skip: str | None = None,
		always_sensitive: str | None = None, attach_files: bool | int | None = None):
	"""Create or change a connection. People with Write access only; agents read the defaults and cannot change them.
	A Gmail mailbox also takes label_name (read only mail with this Gmail label; empty reads the Inbox), the always_include, always_skip
	and always_sensitive lists (senders or domains, one per line) and attach_files."""
	if permissions.is_agent():
		frappe.throw(_("Only a person can change a connection."), frappe.PermissionError, title=_("Only people change connections"))
	if name:
		doc = permissions.get_doc_checked("Life Connection", name, "write")
		if doc.system in COMING and active is not None and flag(active):
			frappe.throw(_("{0} is not built yet, so it cannot be switched on.").format(COMING[doc.system][0]), title=_("Source not built yet"))
	else:
		space = permissions.resolve_space(space, write=True)
		key = (system or "").strip().lower()
		if key in COMING:
			frappe.throw(_("{0} is not built yet, so it cannot be switched on.").format(COMING[key][0]), title=_("Source not built yet"))
		doc = frappe.get_doc({"doctype": "Life Connection", "space": space, "system": system, "label": CATALOG.get(key, {}).get("label")})
	if label is not None:
		doc.label = label
	if default_area is not None:
		doc.default_area = default_area or None
	if default_goal is not None:
		doc.default_goal = default_goal or None
	if default_intent is not None:
		if default_intent not in INTENTS:
			frappe.throw(_("default_intent must be one of: {0}.").format(", ".join(INTENTS)), title=_("Intent is not valid"))
		doc.default_intent = default_intent
	if doc.system == "gmail":
		for field, value in (("label_name", label_name), ("always_include", always_include), ("always_skip", always_skip), ("always_sensitive", always_sensitive)):
			if value is not None:
				doc.set(field, value.strip()[:2000])
		if attach_files is not None:
			doc.attach_files = 1 if flag(attach_files) else 0
	if active is not None:
		doc.active = 1 if flag(active) else 0
	doc.save() if name else doc.insert()
	return _out(connection(doc.space, doc.system)) if doc.system != "gmail" else _out(frappe.get_doc("Life Connection", doc.name))


# ---------- Gmail (issue 58): Life OS reads it itself, read only ----------

def _people_only():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Only a person can connect a mailbox."), frappe.PermissionError, title=_("Only people connect mailboxes"))


@frappe.whitelist(methods=["GET"])
def gmail_setup():
	"""What Connect Gmail shows before it sends you to Google: whether Google sign-in is set up (Google Settings, the OAuth client), the one
	permission asked for, and the redirect address to allow in Google Cloud for the next mailbox."""
	from lifeos import gmail

	permissions.require_login()
	return {"ready": int(gmail.configured()), "scope": gmail.SCOPE, "redirect_uri": gmail.redirect_uri(gmail.free_app_name()),
		"nothing_changes": _("Life OS only reads. It never marks, labels, moves or deletes your mail.")}


@frappe.whitelist(methods=["POST"])
def gmail_connect(space: str | None = None, success_uri: str | None = None):
	"""Start Connect Gmail: a card for the mailbox, a Connected App for it from Google Settings, and Google's sign-in address for the
	signed-in person (read only: gmail.readonly). The browser goes there; Frappe stores the token and returns to `success_uri`
	(a path in this site). Finish with gmail_finish. Nothing secret is typed or shown."""
	from lifeos import gmail

	_people_only()
	space = permissions.resolve_space(space, write=True)
	if not gmail.configured():
		frappe.throw(_("Google sign-in is not set up yet. In Frappe, open Google Settings and enter the OAuth client (client ID and secret), then try again."), title=_("Google sign-in not set up"))
	app = gmail.make_app(gmail.free_app_name())
	conn = frappe.get_doc({"doctype": "Life Connection", "space": space, "system": "gmail", "label": "Gmail", "active": 0,
		"connected_app": app.name, "connected_by": frappe.session.user}).insert()
	success = success_uri if (success_uri or "").startswith("/") and not (success_uri or "").startswith("//") else "/life/brain/sources"
	url = app.initiate_web_application_flow(frappe.session.user, f"{success}{'&' if '?' in success else '?'}gmail={conn.name}")
	return {"connection": conn.name, "url": url}


@frappe.whitelist(methods=["POST"])
def gmail_finish(name: str):
	"""After Google sends the person back: read the mailbox's address and switch it on. A card whose sign-in was abandoned is removed."""
	from lifeos import gmail

	_people_only()
	conn = permissions.get_doc_checked("Life Connection", name, "write")
	if conn.system != "gmail":
		frappe.throw(_("This is not a Gmail connection."), title=_("Not a Gmail connection"))
	try:
		gmail.finish(conn)
	except gmail.GmailError as e:
		if not conn.mailbox:
			frappe.delete_doc("Life Connection", conn.name, ignore_permissions=True, force=True)  # system: admin-only screen; the space write check is above
		frappe.throw(str(e), title=_("Gmail sign-in failed"))
	return gmail_card(conn.name)


def gmail_card(name):
	conn = frappe.get_doc("Life Connection", name)
	return _gmail_card(conn, _out(conn), CATALOG["gmail"])


@frappe.whitelist(methods=["POST"])
def gmail_remove(name: str):
	"""Stop reading a mailbox and forget its sign-in. What it already brought in stays."""
	_people_only()
	conn = permissions.get_doc_checked("Life Connection", name, "write")
	if conn.system != "gmail":
		frappe.throw(_("This is not a Gmail connection."), title=_("Not a Gmail connection"))
	app = conn.connected_app
	for cache in frappe.get_all("Token Cache", filters={"connected_app": app}, pluck="name") if app else []:  # system: Frappe's token cache, not a space record
		frappe.delete_doc("Token Cache", cache, ignore_permissions=True, force=True)  # system: admin-only screen; the space write check is above
	frappe.delete_doc("Life Connection", conn.name, ignore_permissions=True, force=True)  # system: admin-only screen; the space write check is above
	return {"removed": name}


# ---------- chat export import ----------

@frappe.whitelist(methods=["POST"])
def start_import(space: str | None = None, system: str | None = None, file_url: str | None = None):
	"""Import a Claude (system=claude) or ChatGPT (system=chatgpt) data export: the .zip uploaded as a private file.
	It runs in a background job; import_status shows its progress. People with Write access only."""
	from lifeos import chat_import

	if permissions.is_agent():
		frappe.throw(_("Only a person can import a chat export."), frappe.PermissionError, title=_("Only people import chats"))
	space = permissions.resolve_space(space, write=True)
	system = (system or "").strip().lower()
	if system not in chat_import.SYSTEMS:
		frappe.throw(_("system must be claude or chatgpt."), title=_("Chat system not supported"))
	require_on(space, system)
	f = frappe.db.get_value("File", {"file_url": file_url}, ["name", "is_private", "file_name"], as_dict=True)
	if not f:
		frappe.throw(_("Upload the export first."), title=_("Export file missing"))
	frappe.get_doc("File", f.name).check_permission("read")
	if not f.is_private:
		frappe.throw(_("The export must be stored as a private file."), title=_("Export must be private"))
	cur = chat_import.progress(space, system)
	if cur and cur.get("status") in ("Reading", "Importing") and cur.get("started_on") and \
			frappe.utils.get_datetime(cur["started_on"]) > add_to_date(now_datetime(), hours=-2):
		frappe.throw(_("An import of this kind is already running in this space."), title=_("Import already running"))
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
