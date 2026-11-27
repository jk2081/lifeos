"""Connections (UX fixes, set 4): one row per space and outside system (gmail, claude, chatgpt, google-calendar) with the
defaults agents use when filing what arrives from it, and when something last arrived. No credentials are stored here: an
agent holds its own access, and Life OS's own read of Gmail (issue 58, `lifeos/mail/gmail.py`) keeps its token in Frappe's Token Cache,
one mailbox for each Gmail card."""
import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder import functions as fn
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime, nowdate

from lifeos import permissions
from lifeos.api.utils import flag, parse
from lifeos.mail import gmail
from lifeos.review import gcal, gcal_write

INTENTS = ("Process", "Add to wiki", "Just keep")
# how long without anything new before a connection shows a warning, by system (hours)
QUIET_HOURS = {"gmail": 48, "microsoft": 48, "claude": 48, "chatgpt": 48, "email": 48}
DEFAULT_QUIET_HOURS = 24 * 7


# What can be switched on in Brain > Sources (issue 19). `system` is the connection's key and the `source_system` an agent sends.
# kind is the second line of its card; note is said after this week's count. Upload is always on and has no connection row.
CATALOG = {
	"gmail": {"label": "Gmail", "kind": "Email · Read only", "hint": "Email from real people", "note": "only people, not newsletters", "icon": "M"},
	"microsoft": {"label": "Microsoft", "kind": "Email · Outlook and Microsoft 365", "hint": "Email from real people", "note": "only people, not newsletters", "icon": "O"},
	"google-calendar": {"label": "Google Calendar", "kind": "Read only", "hint": "Meetings and events", "icon": "31"},
	"hermes": {"label": "Your assistant", "kind": "Agent", "hint": "Captures and finished work", "icon": "A"},
	"claude": {"label": "Claude", "kind": "Chat logs and agent", "hint": "Chats summarised, and work filed by Claude", "icon": "C"},
	"chatgpt": {"label": "ChatGPT chats", "kind": "Chat export", "hint": "Chats summarised", "icon": "G"},
	"openclaw": {"label": "Another agent", "kind": "Agent", "hint": "An agent that files for you", "icon": "A"},
}
UPLOAD = {"label": "Capture", "kind": "Always on", "hint": "Files, photos, voice and text you add yourself", "icon": "U"}
# shown as "Coming" tiles: not built, so they cannot be switched on
COMING = {"github": ("GitHub", "PRs and issues"), "whatsapp": ("WhatsApp", "Starred chats"), "wearable": ("Wearable", "Voice all day"),
	"tally": ("Tally", "Overdue bills"), "drive": ("Drive", "Shared docs"), "erpnext": ("ERPNext", "Overdue orders and approvals")}
ALWAYS_ON = ("upload", "phone")
# What Sources lists (issue 101): the sources in use. `lifeos_more_sources` in the site config brings back the rest (Microsoft, ChatGPT, other agents, "Coming").
SHOWN = ("google-calendar", "gmail", "hermes", "claude")
MORE = ("microsoft", "chatgpt", "openclaw")
NOT_NAMED = {"hermes": "Your assistant", "openclaw": "Another agent"}  # the bundled agent and an MCP agent are never named in the product
CONFIRMED_KEY = "lifeos_redirects_confirmed"
GOOGLE_CONSOLE = "https://console.cloud.google.com/apis/credentials"
AZURE_CONSOLE = "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
PENDING_MINUTES = 60

# Where each source goes (issue 58): who processes what it brings, and where it lands. Everything not listed here is an agent's.
MAIL = ("gmail", "microsoft")  # the providers of a person's inboxes (one card for each inbox)
BRAIN_SOURCES = ("upload", "phone", *MAIL, "email")
KEPT_AS_IS = ("claude", "chatgpt", "google-calendar")
LANDS = {
	"upload": "Needs you, or filed on its own; then tasks, notes and dates. The capture stays on its page and in Activity.",
	"gmail": "Needs you, or filed on its own; then tasks, notes and dates. The capture stays on its page and in Activity.",
	"microsoft": "Needs you, or filed on its own; then tasks, notes and dates. The capture stays on its page and in Activity.",
	"claude": "Library, Chats. Open items become tasks only with Make task.",
	"chatgpt": "Library, Chats. Open items become tasks only with Make task.",
	"google-calendar": "Today and the calendar views, and meetings in the review (not captures).",
}
AGENT_LANDS = "The same, plus wiki pages and the chat log."


def more_sources() -> bool:
	return bool(frappe.conf.get("lifeos_more_sources") or frappe.get_site_config().get("lifeos_more_sources"))  # the file too: a web process keeps its conf from when it started


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


def ensure(space, system):
	"""The connection row of a source that is connected somewhere else (Settings), so Brain > Sources lists it."""
	if not frappe.db.exists("Life Connection", {"space": space, "system": system}):
		frappe.get_doc({"doctype": "Life Connection", "space": space, "system": system, "label": CATALOG.get(system, {}).get("label"), "active": 1}).insert(ignore_permissions=True)  # system: a sync job of the person's own calendar


def _out(c):
	if not c:
		return None
	area = frappe.db.get_value("Life Area", c.default_area, "area_name") if c.default_area else None
	goal = frappe.db.get_value("Life Goal", c.default_goal, "title") if c.default_goal else None
	hours = QUIET_HOURS.get(c.system, DEFAULT_QUIET_HOURS)
	quiet = bool(c.active and (not c.last_received_on or c.last_received_on < add_to_date(now_datetime(), hours=-hours)))
	return {"name": c.name, "system": c.system, "label": NOT_NAMED.get(c.system) or c.label or c.system.title(), "default_area": c.default_area, "default_area_name": area,
		"default_goal": c.default_goal, "default_goal_title": goal, "default_intent": c.default_intent or "Process",
		"active": int(c.active or 0), "last_received_on": str(c.last_received_on) if c.last_received_on else None,
		"last_received_what": c.last_received_what, "quiet": quiet, "quiet_hours": hours}


def _week_start():
	d = getdate(nowdate())
	return add_to_date(d, days=-d.weekday())


def _week_counts(space, system):
	"""Captures that came in from `system` since Monday: all of them, and how many were a finished piece of work (a job)."""
	i = frappe.qb.DocType("Life Inbox Item")
	cond = (i.source_system.isnull() | i.source_system.isin(["", "upload"])) if system == "upload" else (i.source_system == system)
	has_job = fn.Sum(Case().when(fn.IfNull(i.job_id, "") != "", 1).else_(0))
	n, jobs = frappe.qb.get_query("Life Inbox Item", fields=[fn.Count("*"), fn.Coalesce(has_job, 0)], ignore_permissions=False).where(
		(i.space == space) & (i.creation >= _week_start()) & cond).run()[0]
	return int(n), int(jobs)


GMAIL_FIELDS = ["mailbox", "connected_app", "label_name", "always_include", "always_skip", "always_sensitive", "last_error", "creation"]
FIELDS = ["name", "system", "label", "default_area", "default_goal", "default_intent", "active", "last_received_on", "last_received_what"]
SYNC_DAYS = 7  # a calendar's count is the events it synced in this many days


def _events_synced(space):
	"""Events a calendar read brought in or changed in the last week: what that source actually brought in (a sync that finds nothing new leaves `modified` alone)."""
	since = add_to_date(now_datetime(), days=-SYNC_DAYS)
	return len(frappe.get_list("Event", filters={"life_space": space, "pulled_from_google_calendar": 1, "modified": [">=", since]}, pluck="name", limit_page_length=0))


def _calendar_card(space, row, out, meta):
	"""Google Calendar: the events it synced this week, and a warning only when the last read is over a day old or failed."""
	when, error = gcal.last_sync(frappe.session.user)
	n = _events_synced(space)
	quiet = bool(row.active and (error or not when or get_datetime(when) < add_to_date(now_datetime(), days=-1)))
	last = f"Last read {frappe.utils.pretty_date(when)}" if when else "Not read yet"
	return {**out, "kind": meta["kind"], "icon": meta["icon"], "this_week": n, "quiet": quiet, "error": error, "state": "On" if row.active else "Off",
		"line": f"{n} event{'s' if n != 1 else ''} synced in the last 7 days · {last}", "processed_by": processed_by(row.system), "lands": LANDS[row.system]}


def _card(space, row):
	"""One source for the Sources screen: its look, its state (On, Off, Waiting), what it brought in, and who processes it."""
	meta = CATALOG.get(row.system) or ({"label": "Email", "kind": "Email · Forwarded", "icon": "@"} if row.system == "email" else {})
	out = _out(row)
	if row.system in MAIL and (row.connected_app or row.mailbox):  # one Life OS reads itself; a bare gmail row is only the defaults for what agents file
		return _gmail_card(row, out, meta)
	if row.system == "google-calendar":
		return _calendar_card(space, row, out, meta)
	n, jobs = _week_counts(space, row.system)
	counts = [f"{n} this week" if not jobs else f"{n - jobs} captures · {jobs} piece{'s' if jobs != 1 else ''} of work filed"]
	if meta.get("note"):
		counts.append(meta["note"])
	return {**out, "kind": meta.get("kind") or "Agent", "icon": meta.get("icon") or out["label"][:1].upper(), "this_week": n, "line": " · ".join(counts),
		"state": "On" if row.active else "Off", "processed_by": processed_by(row.system, out["label"]), "lands": LANDS.get(row.system, AGENT_LANDS)}


def _gmail_card(row, out, meta):
	"""A mailbox: when it was last read for the digest, its lists and settings, and what Google said when it refused. A card still waiting for
	sign-in has no mailbox yet: it shows the address Google must be told about and can be removed."""
	pending = not row.mailbox
	provider = "Microsoft" if row.system == "microsoft" else "Google"
	line = _("Waiting for you to finish signing in with {0}.").format(provider) if pending else _("Daily digest, and searched live by Chat and your agent")
	return {**out, "kind": meta["kind"], "icon": meta["icon"], "this_week": 0, "line": line, "pending": int(pending), "mailbox": row.mailbox,
		"state": "Waiting" if pending else ("On" if row.active else "Off"), "quiet": False,
		"redirect_uri": gmail.redirect_uri(row.connected_app) if pending and row.connected_app else None,
		"label_name": row.label_name or "", "always_include": row.always_include or "", "always_skip": row.always_skip or "",
		"always_sensitive": row.always_sensitive or "", "error": row.last_error,
		"processed_by": processed_by(row.system), "lands": LANDS[row.system]}


def _placeholder(system):
	"""A source in use that is not connected yet: a row with its Connect button."""
	meta = CATALOG[system]
	return {"name": None, "system": system, "label": meta["label"], "kind": meta["kind"], "icon": meta["icon"], "hint": meta["hint"], "state": "Not connected", "connected": 0,
		"active": 0, "line": meta["hint"], "processed_by": processed_by(system, meta["label"]), "lands": LANDS.get(system, AGENT_LANDS)}


@frappe.whitelist(methods=["GET"])
def sources(space: str | None = None):
	"""Brain > Sources, one list (issue 101). `capture`: Capture, always on, a line and this week's count. `sources`: Google Calendar, Gmail (one row for each
	inbox, then "add another" on the last connected one), Your assistant and Claude, each a card with its `state` (On, Off, Waiting) or, when not connected
	yet, a row with `connected` 0 and a Connect button. A source that is connected or half connected shows once. `email_in`: the forwarding address, its
	allowed senders and how to use it (issue 32). With `lifeos_more_sources` in the site config, Microsoft, ChatGPT chats, other agents and the sources
	not built yet (`coming`) are listed too; `more` says so."""
	space = permissions.resolve_space(space)
	rows = frappe.get_list("Life Connection", filters={"space": space}, fields=FIELDS + GMAIL_FIELDS, order_by="creation asc")
	more = more_sources()
	shown = SHOWN + (MORE if more else ())
	out = []
	for system in shown:
		mine = [r for r in rows if r.system == system and (system not in MAIL or r.connected_app or r.mailbox)]
		cards = [_card(space, r) for r in mine] or [_placeholder(system)]
		if system in MAIL and mine and all(not c["pending"] for c in cards):
			cards[-1]["add_another"] = 1  # "Add another Gmail" sits on the row, once the first is fully connected
		out += cards
	if more:  # whatever else is connected: other agents, the forwarding address's own row
		out += [_card(space, r) for r in rows if r.system not in shown]
	from lifeos.brain import email_in

	return {"space": space, "more": int(more), "capture": {"system": "upload", "label": UPLOAD["label"], "line": UPLOAD["hint"], "this_week": _week_counts(space, "upload")[0],
		"processed_by": processed_by("upload"), "lands": LANDS["upload"]},
		"sources": out, "email_in": email_in.info(),
		"coming": [{"system": k, "label": v[0], "hint": v[1]} for k, v in COMING.items()] if more else []}


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


@frappe.whitelist(methods=["POST"])
def save(space: str | None = None, system: str | None = None, name: str | None = None, label: str | None = None,
		default_area: str | None = None, default_goal: str | None = None, default_intent: str | None = None,
		active: bool | int | None = None, label_name: str | None = None, always_include: str | None = None, always_skip: str | None = None,
		always_sensitive: str | None = None):
	"""Create or change a connection. People with Write access only; agents read the defaults and cannot change them.
	A Gmail mailbox also takes label_name (the digest reads mail with this Gmail label; empty reads the Inbox), and the always_include, always_skip
	and always_sensitive lists (senders or domains, one per line)."""
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
	if doc.system in MAIL:
		for field, value in (("label_name", label_name), ("always_include", always_include), ("always_skip", always_skip), ("always_sensitive", always_sensitive)):
			if value is not None:
				doc.set(field, value.strip()[:2000])
	if active is not None:
		doc.active = 1 if flag(active) else 0
	doc.save() if name else doc.insert()
	if doc.system in MAIL and doc.mailbox:  # the mailbox's mail account follows its switch and its name
		from lifeos import mail

		mail.account_for_connection(doc)
	return _out(connection(doc.space, doc.system)) if doc.system not in MAIL else _out(frappe.get_doc("Life Connection", doc.name))


# ---------- Gmail (issue 58): Life OS reads it itself, read only ----------

def _people_only():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Only a person can connect a mailbox."), frappe.PermissionError, title=_("Only people connect mailboxes"))


@frappe.whitelist(methods=["GET"])
def gmail_setup():
	"""What Connect Gmail shows before it sends you to Google: whether Google sign-in is set up (Google Settings, the OAuth client), the permissions
	asked for, and the redirect address to allow in Google Cloud for the next mailbox."""
	from lifeos.mail import gmail

	permissions.require_login()
	return {"ready": int(gmail.configured()), "scope": gmail.SCOPE, "scopes": [*gmail.SCOPES],
		"redirect_uri": gmail.redirect_uri(gmail.free_app_name()), "confirmed": int(redirect_confirmed(gmail.redirect_uri(gmail.free_app_name()))),
		"console_url": GOOGLE_CONSOLE, "nothing_changes": _("Life OS reads your mail only when you or your agent search it, and copies none of it. It sends, drafts, archives or labels mail and changes your calendar only when you ask your agent to, or approve what it suggests. It never deletes.")}


@frappe.whitelist(methods=["POST"])
def gmail_connect(space: str | None = None, success_uri: str | None = None):
	"""Start Connect Gmail: a card for the mailbox, a Connected App for it from Google Settings, and Google's sign-in address for the
	signed-in person (read, and what an agent acts with: see gmail.SCOPES). The browser goes there; Frappe stores the token and returns to `success_uri`
	(a path in this site). Finish with gmail_finish. Nothing secret is typed or shown."""
	from lifeos.mail import gmail

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
	from lifeos.mail import gmail

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
	confirm_redirect(conn)
	return gmail_card(conn.name)


def gmail_card(name):
	conn = frappe.get_doc("Life Connection", name)
	return _gmail_card(conn, _out(conn), CATALOG[conn.system])


# ---------- Microsoft (issue 88): Outlook and Microsoft 365, one card for each inbox ----------

@frappe.whitelist(methods=["GET"])
def microsoft_setup():
	"""What Connect Microsoft shows before it sends you to Microsoft: whether the Azure app registration is in the site config, the permissions asked for,
	and the redirect address to register in Azure for the next inbox."""
	from lifeos.mail import gmail, microsoft

	permissions.require_login()
	return {"ready": int(microsoft.configured()), "scopes": [*microsoft.SCOPES], "redirect_uri": gmail.redirect_uri(microsoft.free_app_name()),
		"confirmed": int(redirect_confirmed(gmail.redirect_uri(microsoft.free_app_name()))), "console_url": AZURE_CONSOLE, "nothing_changes": _("Life OS reads your mail only when you or your agent search it, and copies none of it. It sends or drafts mail, and archives or labels it, only when you ask your agent to, or approve what it suggests. It never deletes.")}


@frappe.whitelist(methods=["POST"])
def microsoft_connect(space: str | None = None, success_uri: str | None = None):
	"""Start Connect Microsoft: a card for the inbox, a Connected App for it from the site config's Azure client, and Microsoft's sign-in address for the
	signed-in person. The browser goes there; Frappe stores the token and returns to `success_uri` (a path in this site). Finish with microsoft_finish."""
	from lifeos.mail import microsoft

	_people_only()
	space = permissions.resolve_space(space, write=True)
	if not microsoft.configured():
		frappe.throw(_("Microsoft sign-in is not set up yet. Put the Azure app's client ID and secret in the site config (docs/MICROSOFT.md), then try again."), title=_("Microsoft sign-in not set up"))
	app = microsoft.make_app(microsoft.free_app_name())
	conn = frappe.get_doc({"doctype": "Life Connection", "space": space, "system": "microsoft", "label": "Microsoft", "active": 0,
		"connected_app": app.name, "connected_by": frappe.session.user}).insert()
	success = success_uri if (success_uri or "").startswith("/") and not (success_uri or "").startswith("//") else "/life/brain/sources"
	url = app.initiate_web_application_flow(frappe.session.user, f"{success}{'&' if '?' in success else '?'}microsoft={conn.name}")
	return {"connection": conn.name, "url": url}


@frappe.whitelist(methods=["POST"])
def microsoft_finish(name: str):
	"""After Microsoft sends the person back: read the inbox's address and switch it on. A card whose sign-in was abandoned is removed."""
	from lifeos.mail import microsoft

	_people_only()
	conn = permissions.get_doc_checked("Life Connection", name, "write")
	if conn.system != "microsoft":
		frappe.throw(_("This is not a Microsoft connection."), title=_("Not a Microsoft connection"))
	try:
		microsoft.finish(conn)
	except microsoft.MicrosoftError as e:
		if not conn.mailbox:
			frappe.delete_doc("Life Connection", conn.name, ignore_permissions=True, force=True)  # system: admin-only screen; the space write check is above
		frappe.throw(str(e), title=_("Microsoft sign-in failed"))
	confirm_redirect(conn)
	return gmail_card(conn.name)


@frappe.whitelist(methods=["POST"])
def gmail_remove(name: str):
	"""(Gmail or Microsoft.) Stop reading a mailbox and forget its sign-in. What it already brought in stays."""
	_people_only()
	conn = permissions.get_doc_checked("Life Connection", name, "write")
	if conn.system not in MAIL:
		frappe.throw(_("This is not a mailbox connection."), title=_("Not a mailbox connection"))
	remove_connection(conn)
	return {"removed": name}


def remove_connection(conn):
	"""A mailbox connection with its mail account, its token and its Connected App."""
	app = conn.connected_app
	for account in frappe.get_all("Life Mail Account", filters={"connection": conn.name}, pluck="name"):  # system: the account goes with its sign-in; the caller checked the space write access
		frappe.delete_doc("Life Mail Account", account, ignore_permissions=True, force=True)  # system: as above
	for cache in frappe.get_all("Token Cache", filters={"connected_app": app}, pluck="name") if app else []:  # system: Frappe's token cache, not a space record
		frappe.delete_doc("Token Cache", cache, ignore_permissions=True, force=True)  # system: as above
	frappe.delete_doc("Life Connection", conn.name, ignore_permissions=True, force=True)  # system: as above
	if app and frappe.db.exists("Connected App", app):
		frappe.delete_doc("Connected App", app, ignore_permissions=True, force=True)  # system: the app was made for this mailbox alone; a new one is made on the next connect


def clean_abandoned():
	"""Hourly: a Gmail or Microsoft connection still without a mailbox an hour after it was started was abandoned: remove it with its Connected App."""
	c = frappe.qb.DocType("Life Connection")
	old = frappe.qb.from_(c).select(c.name).where(c.system.isin([*MAIL]) & (fn.IfNull(c.mailbox, "") == "") & (fn.IfNull(c.connected_app, "") != "")
		& (c.creation < add_to_date(now_datetime(), minutes=-PENDING_MINUTES))).run(pluck=True)  # system: the job cleans every space
	for name in old:
		remove_connection(frappe.get_doc("Life Connection", name))


# ---------- the return address (issue 101) ----------

def redirect_confirmed(uri: str) -> bool:
	"""Whether a successful sign-in has already come back to this address, so it is known to be allowed in Google Cloud or Azure."""
	return uri in (frappe.db.get_default(CONFIRMED_KEY) or "").split("\n")


def confirm_redirect(conn):
	"""A sign-in came back through this connection's address: it is allowed, so the step that asks the owner to add it is not shown again."""
	if not conn.connected_app:
		return
	uri = gmail.redirect_uri(conn.connected_app)
	known = [u for u in (frappe.db.get_default(CONFIRMED_KEY) or "").split("\n") if u]
	if uri not in known:
		frappe.db.set_default(CONFIRMED_KEY, "\n".join([*known, uri]))


def sign_in_error(code: str, provider: str, detail: str | None) -> str:
	if code == "redirect_uri_mismatch":
		where = "Azure" if provider == "Microsoft" else "Google Cloud"
		return _("{0} does not know this return address. Add the address below in {1}, then try again.").format(provider, where)
	return _("{0} sent you back with an error: {1}").format(provider, (detail or code).strip()[:160])


@frappe.whitelist(methods=["GET"], allow_guest=True)  # nosemgrep: guest-whitelisted-method -- the same door as Frappe's own callback, which sends a guest to log in
def oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None, error_description: str | None = None):
	"""Frappe's Connected App return address, wrapped (hooks override_whitelisted_methods). When the provider sends the person back with an error
	(for example redirect_uri_mismatch) there is no code to exchange: keep what it said on the mailbox's card and go back to Sources. Anything else is Frappe's own."""
	from frappe.integrations.doctype.connected_app.connected_app import callback

	try:
		path = frappe.request.path
	except RuntimeError:  # not a web request: only a browser coming back from the provider reaches this
		frappe.throw(_("Invalid Parameters."), title=_("Not a sign-in return"))
	if not error or frappe.session.user == "Guest":
		return callback(code=code, state=state)
	parts = path[1:].split("/")
	app = parts[3] if len(parts) == 4 else None
	conn = frappe.db.get_value("Life Connection", {"connected_app": app, "connected_by": frappe.session.user, "system": ["in", [*MAIL]]}, ["name", "system"], as_dict=True) if app else None
	if conn:
		from lifeos.mail.gmail import scrub

		frappe.db.set_value("Life Connection", conn.name, "last_error",
			scrub(sign_in_error(error, "Microsoft" if conn.system == "microsoft" else "Google", error_description))[:140], update_modified=False)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit, whitelisted-side-effect-on-get -- Frappe's return address is a GET and rolls back at its end; the card must keep what the provider said
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = "/life/brain/sources"


# ---------- chat export import ----------

@frappe.whitelist(methods=["POST"])
def start_import(space: str | None = None, system: str | None = None, file_url: str | None = None):
	"""Import a Claude (system=claude) or ChatGPT (system=chatgpt) data export: the .zip uploaded as a private file.
	It runs in a background job; import_status shows its progress. People with Write access only."""
	from lifeos.brain import chat_import

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
	frappe.enqueue("lifeos.brain.chat_import.run", queue="long", timeout=4 * 3600, space=space, system=system, file_url=file_url,
		user=frappe.session.user, now=bool(frappe.flags.in_test or frappe.flags.lifeos_import_now))
	return chat_import.progress(space, system)


@frappe.whitelist(methods=["GET"])
def import_status(space: str | None = None, system: str | None = None):
	"""The progress of the last chat import of this kind in this space: status (Queued, Reading, Importing, Done, Failed),
	done and total, and the counts created, updated, unchanged and skipped (could not be read)."""
	from lifeos.brain import chat_import

	space = permissions.resolve_space(space)
	return chat_import.progress(space, (system or "").lower()) or {"status": None}


# ---------------------------------------------------------------- Google Calendar (Settings > Me > Calendar), connected through Frappe's own OAuth flow

def _calendar_person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Calendars are connected by people."), frappe.PermissionError, title=_("Calendars are for people"))
	return frappe.session.user


@frappe.whitelist(methods=["GET"])
def gcal_state():
	"""Whether Google Settings is configured, whether this user is connected, which calendars are read, last synced, your domains."""
	return gcal.state(_calendar_person())


@frappe.whitelist(methods=["POST"])
def gcal_connect():
	"""Start Frappe's OAuth flow for this user's calendar (read by Life OS only). Returns {"url"} to open."""
	user = _calendar_person()
	if not gcal.configured():
		frappe.throw(_("Google is not set up on this site. The owner enters the OAuth client in Google Settings first."), title=_("Google is not set up"))
	return gcal.connect(user)


@frappe.whitelist(methods=["POST"])
def gcal_disconnect():
	return gcal.disconnect(_calendar_person())


@frappe.whitelist(methods=["GET"])
def gcal_calendars():
	"""The user's calendars on Google (a read), to choose which ones Life OS reads."""
	user = _calendar_person()
	acc = gcal.account(user)
	if not frappe.conf.get("lifeos_fake_calendar") and not (acc and acc.enable):
		return {"calendars": []}
	return {"calendars": gcal.source_for(acc).calendars(), "read": gcal.read_ids(acc) if acc else ["primary"], "write": gcal_write.chosen(user)}


@frappe.whitelist(methods=["POST"])
def gcal_set_read(ids: str | list):
	ids = parse(ids, []) or []
	return gcal.set_read(_calendar_person(), ids if isinstance(ids, list) else [])


@frappe.whitelist(methods=["POST"])
def gcal_set_write(calendar: str | None = None):
	"""Choose the calendar Life OS writes accepted events and goal blocks to; empty turns writing off."""
	return gcal_write.choose(_calendar_person(), calendar)


@frappe.whitelist(methods=["POST"])
def gcal_sync():
	"""Read now: the last 21 days and the next 14."""
	user = _calendar_person()
	n = gcal.sync_user(user)
	return {"read": n, **gcal.state(user)}
