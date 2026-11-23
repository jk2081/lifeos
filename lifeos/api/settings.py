"""The Settings screen: spaces and members, areas, habits, review time, archive days."""
import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder import functions as fn

from lifeos import permissions
from lifeos.goals import readings
from lifeos.api.utils import parse

SETTING_FIELDS = ("default_space", "weekly_review_day", "weekly_review_time", "score_target", "archive_after_days", "stale_task_days",
	# UX fixes, set 5: Reset rules and the AI behind Ask (the key has its own method and is never sent back)
	"stuck_after_days", "stuck_limit", "open_task_goal", "someday_review_months", "ask_model", "short_model", "monthly_cap_usd",
	# UX fixes, set 6: Rhythms
	"start_of_day", "week_starts_on", "cycle_break_week", "planning_period", "require_done_when", "use_focuses",
	# set 7: working hours, for the weekly review's goal work
	"work_days", "work_start", "work_end", "old_inbox_mode", "old_inbox_days", "own_domains",
	# issue 32: the mailbox people forward to, and who may
	"email_in_account", "email_in_senders")
TIME_FIELDS = ("weekly_review_time", "start_of_day", "work_start", "work_end")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
LISTS = {
	"area": ("Life Area", "area_name"),
	"habit": ("Life Habit", "title"), "person": ("Life Person", "full_name"),
}


def _admin_only():
	permissions.require_login()
	if not permissions.is_admin():
		frappe.throw(_("Only the owner can change this."), frappe.PermissionError, title=_("Only the owner can change this"))


def _counts(kind, space, names):
	"""The quiet count beside each row: areas, active records filed there; habits, days ticked."""
	if not names:
		return {}
	if kind == "area":
		out = {}
		from lifeos.api.timeline import index_where
		from lifeos.api.utils import area_criterion, count_where

		x = frappe.qb.DocType("Life Index")
		for n in names:  # as the Timeline counts an area: filed there or also filed there
			out[n] = count_where("Life Index", index_where(space, [x.is_archived == 0, (x.area == n) | area_criterion(space, n, x, also_in="index")]))
		return out
	if kind == "habit":
		from lifeos.api.utils import count_by

		log = frappe.qb.DocType("Life Habit Log")
		return count_by("Life Habit Log", "habit", [log.habit.isin(names), log.done == 1])
	return {}


def _visible_user(user):
	return user not in ("Administrator", "Guest")


LIFE_ROLES = ("Life Admin", "Life User", "Life Agent")
# the roles Add member may give a user who has no Life OS role yet: never Life Admin
GRANTABLE = {"Person": "Life User", "Agent": "Life Agent"}


def _people(users):
	"""{user: {full_name, image, is_agent, kind}} for many users, in two queries. An agent has Life Agent and no other Life
	role, as permissions.is_agent decides; a person has Life User or Life Admin; kind is None for a user with no Life role."""
	users = sorted({u for u in users if u})
	if not users:
		return {}
	out = {r.name: {"full_name": r.full_name or r.name, "image": r.user_image, "roles": set()}
		for r in frappe.get_all("User", filters={"name": ("in", users)}, fields=["name", "full_name", "user_image"])}  # system: user and role lookups and the admin's space list are not space records
	for r in frappe.get_all("Has Role", filters={"parent": ("in", users), "parenttype": "User",  # system: user and role lookups and the admin's space list are not space records
			"role": ("in", list(LIFE_ROLES))}, fields=["parent", "role"]):
		if r.parent in out:
			out[r.parent]["roles"].add(r.role)
	for p in out.values():
		roles = p.pop("roles")
		p["is_agent"] = "Life Agent" in roles and not roles & {"Life Admin", "Life User"}
		p["kind"] = "Agent" if p["is_agent"] else "Person" if roles & {"Life Admin", "Life User"} else None
	return out


def _member_rows(space, people):
	"""Everyone in a space, people and agents together (issue 1): the owner first, then people, then agents, each by name."""
	rows = []
	for m in space.members:
		if not _visible_user(m.user):
			continue
		p = people.get(m.user, {})
		is_owner = m.user == space.owner_user
		rows.append({"user": m.user, "access": m.access, "full_name": p.get("full_name", m.user), "image": p.get("image"),
			"is_owner": is_owner, "is_agent": bool(p.get("is_agent")), "kind": "Owner" if is_owner else "Agent" if p.get("is_agent") else "Person"})
	return sorted(rows, key=lambda r: (not r["is_owner"], r["is_agent"], (r["full_name"] or "").lower()))


def _last_filed(users):
	"""{user: when each last filed a proposal or a chat log}, in two grouped queries."""
	if not users:
		return {}
	out = {}
	for doctype in ("Life Proposal", "Life Chat Log"):
		for user, when in frappe.get_all(doctype, filters={"owner": ("in", users)}, fields=["owner", {"MAX": "creation"}],  # system: user and role lookups and the admin's space list are not space records
				group_by="owner", as_list=True):
			if when and (user not in out or when > out[user]):
				out[user] = when
	return out


def _agents(spaces):
	"""One card per agent for Settings > Members > Agents: every agent account, its access in each space (None
	where it is not a member; read from the same member rows as Members), whether agents may open that space's sensitive
	items, and when it last filed something."""
	reach = {}
	for s in spaces:
		for m in s["members"]:
			if m["is_agent"]:
				reach.setdefault(m["user"], []).append({"space": s["name"], "access": m["access"], "agents_can_read_vault": s["agents_can_read_vault"]})
	users = set(reach) | set(frappe.get_all("Has Role", filters={"role": "Life Agent", "parenttype": "User"}, pluck="parent", distinct=True))  # system: user and role lookups and the admin's space list are not space records
	people = _people([u for u in users if _visible_user(u)])
	last = _last_filed(list(people))
	out = []
	for u, p in people.items():
		if not p["is_agent"]:
			continue
		mine = {r["space"]: r for r in reach.get(u, [])}
		out.append({"user": u, "full_name": p["full_name"], "image": p["image"], "last_filed": str(last[u]) if last.get(u) else None,
			"spaces": [mine.get(s["name"]) or {"space": s["name"], "access": None, "agents_can_read_vault": s["agents_can_read_vault"]} for s in spaces]})
	return sorted(out, key=lambda a: a["full_name"].lower())


def _spaces(names):
	"""The spaces with their members, in three queries whatever their number."""
	rows = frappe.get_all("Life Space", filters={"name": ("in", names or ["-"])},  # system: user and role lookups and the admin's space list are not space records
		fields=["name", "owner_user", "agents_can_read_vault", "ask_enabled", "ask_can_read_vault"], order_by="name asc")
	members = {}
	for m in frappe.get_all("Life Space Member", filters={"parent": ("in", names or ["-"]), "parenttype": "Life Space"},  # system: user and role lookups and the admin's space list are not space records
			fields=["parent", "user", "access"], order_by="idx asc"):
		members.setdefault(m.parent, []).append(m)
	for r in rows:
		r["members"] = members.get(r.name, [])
	return rows


@frappe.whitelist(methods=["GET"])
def focus_offers(kind: str):
	"""The focuses offered for a kind of part (Company, Estate, Household, Other), each with its suggested standard: [{name, standard}]."""
	permissions.require_login()
	from lifeos.goals import focus_defaults

	return [{"name": n, "standard": st} for n, st in focus_defaults.offered(kind)]


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None):
	"""Everything the Settings screen shows for one space: the plain settings, the four lists with a count per row (archived
	rows too, for the Archived section), the spaces with everyone in them (people and agents, `is_agent` on each row), and
	the agents across spaces, built from the same member rows. Role names are never sent.
	The built-in Administrator is left out of every list."""
	space = permissions.resolve_space(space)
	s = frappe.get_cached_doc("Life Settings")
	lists = {}
	for kind, (doctype, field, key, extra, order) in {
		"area": ("Life Area", "area_name", "areas", ["parent_area", "sort_order", "colour", "is_pinned", "is_life_area", "is_on", "description",
			"is_focus", "standard", "part_kind"],
			"sort_order, area_name"),
		"habit": ("Life Habit", "title", "habits", [], "title"),
	}.items():
		rows = frappe.get_list(doctype, filters={"space": space}, fields=["name", field, "is_archived", "archived_on", *extra], order_by=order, limit=1000)
		counts = _counts(kind, space, [r.name for r in rows])
		for r in rows:
			r["count"] = counts.get(r.name, 0)
			r["archived_on"] = str(r.archived_on) if r.archived_on else None
		lists[key] = rows
	from lifeos.goals import areas

	hidden = set(areas.hidden_focuses(space))  # existing focuses are hidden, not deleted, while "Use focuses" is off
	lists["areas"] = [r for r in lists["areas"] if r.name not in hidden]
	goals = areas.goal_counts(space)  # issue 12: the goal count beside each area and part
	for r in lists["areas"]:
		r["goals"] = goals.get(r.name, 0)
	out = {
		"space": space, "is_admin": permissions.is_admin(), "user": frappe.session.user,
		"settings": {f: (str(s.get(f)) if f in TIME_FIELDS and s.get(f) else s.get(f)) for f in SETTING_FIELDS},
		**lists,
		"cycle": _cycle_info(space), "rules_note": frappe.db.get_value("Life Note", {"space": space, "collection": "Wiki", "is_rules": 1}),
		"people": frappe.get_list("Life Person", filters={"space": space}, fields=["name", "full_name", "relation"], order_by="full_name", limit=500),
		"spaces": [], "agents": [],
	}
	names = frappe.get_all("Life Space", pluck="name") if permissions.is_admin() else list(permissions.user_spaces())  # system: user and role lookups and the admin's space list are not space records
	docs = _spaces(names)
	people = _people([m.user for d in docs for m in d.members] + [d.owner_user for d in docs])
	access = permissions.user_spaces()
	for doc in docs:
		members = _member_rows(doc, people)
		agents = sum(1 for m in members if m["is_agent"])
		out["spaces"].append({"name": doc.name, "owner_user": doc.owner_user,
			"owner_name": people.get(doc.owner_user, {}).get("full_name", doc.owner_user) if doc.owner_user else None,
			"access": access.get(doc.name), "agents_can_read_vault": int(doc.agents_can_read_vault or 0), "members": members,
			"people_count": len(members) - agents, "agent_count": agents,
			"ask_enabled": int(doc.ask_enabled or 0), "ask_can_read_vault": int(doc.ask_can_read_vault or 0)})
	if permissions.is_admin():
		out["agents"] = _agents(out["spaces"])
		out["ai"] = ai_settings()
		out["backups"] = backups()
	out["settings"]["require_done_when"] = int(readings.done_when_required())  # a Check never saved reads 0 here; the setting is on until switched off
	return out


def _cycle_info(space):
	"""The current 12 Week cycle for Settings > Rhythms: its dates and this week's number (read-only there)."""
	from lifeos.goals import cycles

	c = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "title", "start_date", "end_date"], as_dict=True)
	if not c:
		return None
	return {"name": c.name, "title": c.title, "start_date": str(c.start_date), "end_date": str(c.end_date), "week": cycles.week_of(c)}


BACKUP_KEYS = ("backup_frequency", "backup_with_files", "backup_path", "encrypt_backup", "keep_backups_for_hours", "backup_limit")


def backups():
	"""What is backed up and when, read from the site's configuration (Settings > Advanced > Backups). Never a secret: only the
	keys above, whether S3 backups are switched on, and the dates and sizes of the latest backup files on this server."""
	conf = frappe.get_site_config() or {}
	keys = {k: conf.get(k) for k in BACKUP_KEYS if conf.get(k) not in (None, "")}
	s3 = bool(frappe.db.exists("DocType", "S3 Backup Settings") and frappe.db.get_single_value("S3 Backup Settings", "enabled"))
	files = []
	try:
		from frappe.utils.backups import get_backup_path

		import os

		folder = get_backup_path()
		for f in sorted(os.listdir(folder), reverse=True)[:6]:  # nosemgrep: frappe-security-file-traversal -- the site's own backup folder, names only
			if f.endswith((".sql.gz", ".tar", ".json")):
				files.append({"name": f, "size": os.path.getsize(os.path.join(folder, f))})
	except Exception:
		files = []
	return {"configured": bool(keys.get("backup_frequency") or s3), "settings": keys, "s3": s3, "latest": files}


def ai_settings():
	"""Settings, Advanced, AI key and cost: whether a key is set (never the key), the models, the cap, the prices, and this month's spend by
	purpose and by user."""
	from lifeos.ai import client

	s = frappe.get_cached_doc("Life Settings")
	month = client.month()
	u = frappe.qb.DocType("Life AI Usage")
	day = fn.Date(u.creation)

	def usage(fields, group, *order):
		query = frappe.qb.get_query("Life AI Usage", fields=fields, ignore_permissions=False).where(u.month == month).groupby(group)
		for term in order:
			query = query.orderby(term, order=Order.desc)
		return query.run()

	by_purpose = usage([u.purpose, fn.Sum(u.cost), fn.Sum(u.input_tokens), fn.Sum(u.output_tokens)], u.purpose)
	by_user = usage([u.user, fn.Sum(u.cost)], u.user)
	by_day = usage([day, fn.Sum(u.cost), fn.Count("*")], day, day)
	calls = frappe.get_list("Life AI Usage", fields=["creation", "purpose", "model", "input_tokens", "output_tokens", "cached_tokens", "cost", "user",
		"reference_doctype", "reference_name"], order_by="creation desc, name desc", limit=50)
	caps = client.feature_caps()
	features = sorted({p for p, *_r in by_purpose} | set(caps))
	return {"key_set": client.is_set_up(), "ask_model": s.get("ask_model") or client.DEFAULT_ASK_MODEL, "short_model": s.get("short_model") or client.DEFAULT_SHORT_MODEL,
		"monthly_cap_usd": client.cap(), "spend": client.spend_status(),
		"prices": [{"model": m, "input_per_mtok": p[0], "output_per_mtok": p[1], "cached_per_mtok": p[2]} for m, p in client.price_table().items()],
		"by_day": [{"day": str(d), "cost": round(c or 0, 2), "calls": int(n)} for d, c, n in by_day],
		"calls": [{"when": str(c.creation), "feature": c.purpose, "model": c.model, "input_tokens": c.input_tokens or 0, "output_tokens": c.output_tokens or 0,
			"cached_tokens": c.cached_tokens or 0, "cost": round(c.cost or 0, 4), "user": c.user, "full_name": frappe.utils.get_fullname(c.user),
			"reference": f"{c.reference_doctype} {c.reference_name}" if c.reference_name else None} for c in calls],
		"feature_caps": [{"feature": f, "cap": caps.get(f) or 0, "spent": round(client.spent(feature=f), 2)} for f in features],
		"by_purpose": [{"purpose": p, "cost": round(c or 0, 2), "input_tokens": int(i or 0), "output_tokens": int(o or 0)} for p, c, i, o in by_purpose],
		"by_user": [{"user": u, "full_name": frappe.utils.get_fullname(u), "cost": round(c or 0, 2)} for u, c in by_user]}


@frappe.whitelist(methods=["POST"])
def set_ai_key(key: str | None = None):
	"""Store or clear the Anthropic API key (a Password field, encrypted by Frappe). The key is never returned."""
	_admin_only()
	doc = frappe.get_doc("Life Settings")
	doc.anthropic_api_key = (key or "").strip() or None
	doc.save()
	from lifeos.ai import client

	return {"key_set": client.is_set_up()}


@frappe.whitelist(methods=["POST"])
def set_feature_cap(feature: str, cap: float = 0):
	"""A monthly cap in dollars for one feature (Ask, Area guess, …); 0 removes it."""
	_admin_only()
	import json

	if float(cap) < 0:
		frappe.throw(_("A cap cannot be negative."), title=_("Cap cannot be negative"))
	doc = frappe.get_doc("Life Settings")
	caps = json.loads(doc.feature_caps or "{}")
	if float(cap):
		caps[feature] = float(cap)
	else:
		caps.pop(feature, None)
	doc.feature_caps = json.dumps(caps)
	doc.save()
	return {"feature_caps": caps}


@frappe.whitelist(methods=["POST"])
def set_ai_price(model: str, input_per_mtok: float, output_per_mtok: float, cached_per_mtok: float | None = None):
	_admin_only()
	doc = frappe.get_doc("Life Settings")
	row = next((r for r in doc.ai_prices if r.model == model), None) or doc.append("ai_prices", {"model": model})
	row.input_per_mtok, row.output_per_mtok = float(input_per_mtok), float(output_per_mtok)
	if cached_per_mtok is not None:
		row.cached_per_mtok = float(cached_per_mtok)
	if row.input_per_mtok < 0 or row.output_per_mtok < 0:
		frappe.throw(_("Prices cannot be negative."), title=_("Prices cannot be negative"))
	doc.save()
	return {"saved": True}


@frappe.whitelist(methods=["POST"])
def set_space_ask(space: str, ask_enabled: bool | int | None = None, ask_can_read_vault: bool | int | None = None):
	"""Ask on or off for a space, and whether Ask may read its Vault documents. Owner only."""
	_admin_only()
	doc = frappe.get_doc("Life Space", space)
	if ask_enabled is not None:
		doc.ask_enabled = 1 if str(ask_enabled) in ("1", "true", "True") else 0
	if ask_can_read_vault is not None:
		doc.ask_can_read_vault = 1 if str(ask_can_read_vault) in ("1", "true", "True") else 0
	doc.save()
	return {"ask_enabled": doc.ask_enabled, "ask_can_read_vault": doc.ask_can_read_vault}


@frappe.whitelist(methods=["POST"])
def save(values: str | dict):
	"""Change Life Settings. Owner only."""
	_admin_only()
	values = parse(values, {}) or {}
	doc = frappe.get_doc("Life Settings")
	for k, v in values.items():
		if k not in SETTING_FIELDS:
			frappe.throw(_("Unknown setting {0}.").format(k), title=_("Unknown setting"))
		doc.set(k, v)
	for f in ("score_target", "archive_after_days", "stale_task_days", "stuck_after_days", "someday_review_months"):
		if int(doc.get(f) or 0) <= 0:
			frappe.throw(_("{0} must be a positive number.").format(doc.meta.get_label(f)), title=_("Number must be positive"))
	for f in ("stuck_limit", "open_task_goal"):
		if int(doc.get(f) or 0) < 0:
			frappe.throw(_("{0} cannot be negative.").format(doc.meta.get_label(f)), title=_("Number cannot be negative"))
	if float(doc.get("monthly_cap_usd") or 0) < 0:
		frappe.throw(_("The monthly cap cannot be negative."), title=_("Monthly cap cannot be negative"))
	if doc.get("old_inbox_mode") not in (None, "", "Suggest", "Park", "Discard"):
		frappe.throw(_("Choose Suggest, Park or Discard."), title=_("Unknown old inbox action"))
	if "old_inbox_days" in values and int(doc.get("old_inbox_days") or 0) <= 0:
		frappe.throw(_("{0} must be a positive number.").format(doc.meta.get_label("old_inbox_days")), title=_("Number must be positive"))
	if "work_days" in values:
		days = [d.strip() for d in str(doc.work_days or "").split(",") if d.strip()]
		if not days or any(d not in WEEKDAYS for d in days):
			frappe.throw(_("Choose at least one working day."), title=_("Working day needed"))
		doc.work_days = ",".join(d for d in WEEKDAYS if d in days)
	if doc.work_start and doc.work_end and str(doc.work_end).zfill(8) <= str(doc.work_start).zfill(8):
		frappe.throw(_("The working day must end after it starts."), title=_("Working day ends too early"))
	if int(doc.score_target) > 100:
		frappe.throw(_("The score target is a percentage."), title=_("Score target is a percentage"))
	doc.save()
	return {"saved": True}


ARCHIVABLE = ("area", "habit")


@frappe.whitelist(methods=["POST"])
def save_item(kind: str, space: str | None = None, name: str | None = None, title: str | None = None, parent_area: str | None = None,
		relation: str | None = None, sort_order: int | None = None, is_archived: bool | int | None = None, delete: bool | int = 0,
		with_children: bool | int = 1, colour: str | None = None, is_pinned: bool | int | None = None, is_on: bool | int | None = None,
		description: str | None = None, move_to: str | None = None, part_kind: str | None = None, is_focus: bool | int | None = None,
		standard: str | None = None, principles: str | list | None = None, focuses: str | list | None = None):
	"""Add, rename, reorder, nest, archive or restore one area or habit of a space, or a person.
	Archiving sets archived_on to today; records filed under the heading are not changed. Archiving an area archives its
	parts with it. Restoring an area puts it back under its old area of life, and with_children=1 restores the parts
	archived on the same day with it.
	Areas (issue 11): a new area is a part of `parent_area`, one of the seven areas of life, or of Career when none is given.
	The seven cannot be renamed or archived; `is_on` switches an area on or off, which hides or shows it, its parts and
	their goals and tasks without deleting anything.
	Issue 12: only Life Admin changes areas. Archiving a part that holds open goals or tasks needs `move_to`: its own area
	of life or another of its parts, where they are moved first.
	Issue 57: `is_focus` makes the area a focus under `parent_area` (a part, or an area of life), with its `standard` and its
	`principles` (a list of short lines, in order). `part_kind` (Company, Estate, Household, Other) is the kind of a part; with
	"Use focuses" on, the focuses its kind offers are created under it, or only those named in `focuses`.
	delete=1 removes the row for good; the Settings screen does not offer it, agents and tests may use it."""
	if kind not in LISTS:
		frappe.throw(_("Unknown list."), title=_("Unknown list"))
	if kind == "area":
		_areas_admin_only(is_on)
	doctype, field = LISTS[kind]
	if name:
		doc = permissions.get_doc_checked(doctype, name, "write")
		if int(delete or 0):
			doc.check_permission("delete")
			try:
				doc.delete()
			except frappe.LinkExistsError:
				frappe.throw(_("{0} is still used by other records. Remove it from them first{1}.").format(
					doc.get(field), _(", or archive it") if kind in ARCHIVABLE else ""),
					title=_("Still used by other records"))
			return {"deleted": name}
	else:
		space = permissions.resolve_space(space, write=True)
		doc = frappe.get_doc({"doctype": doctype, "space": space})
	if title is not None:
		if not title.strip():
			frappe.throw(_("A name is needed."), title=_("Name needed"))
		doc.set(field, title.strip())
	if kind == "area" and parent_area is not None:
		doc.parent_area = parent_area or None
	if kind == "area" and not name and not doc.parent_area:  # a new area is a part; Career when no area of life is named
		from lifeos.goals import areas

		doc.parent_area = areas.ensure(doc.space)[areas.DEFAULT_PARENT]
	if kind == "area" and is_on is not None:
		doc.is_on = 1 if int(is_on or 0) else 0
	if kind == "area" and description is not None:
		doc.description = description.strip()
	if kind == "area" and colour is not None:  # the dot in the lens and the sidebar (set 6)
		doc.colour = colour or None
	if kind == "area" and is_pinned is not None:  # "Focus on an area" in the sidebar (set 6)
		doc.is_pinned = 1 if int(is_pinned or 0) else 0
	if kind == "area" and is_focus is not None and not name:
		doc.is_focus = 1 if int(is_focus or 0) else 0
	if kind == "area" and part_kind is not None:
		doc.part_kind = part_kind or None
	if kind == "area" and standard is not None:
		doc.standard = standard.strip()
	if kind == "area" and principles is not None:
		doc.set("principles", [{"line": ln.strip()} for ln in (parse(principles, []) or []) if str(ln).strip()])
	if kind == "person" and relation is not None:
		doc.relation = relation
	if sort_order is not None and doc.meta.has_field("sort_order"):
		doc.sort_order = int(sort_order)
	restored = []
	archived = []
	if is_archived is not None and kind in ARCHIVABLE and int(is_archived) != int(doc.get("is_archived") or 0):
		if int(is_archived):
			if kind == "area" and doc.is_life_area:
				frappe.throw(_("{0} is one of the seven areas of life. Switch it off instead of archiving it.").format(doc.area_name), title=_("Core area cannot be archived"))
			if kind == "area":
				_move_open_work(doc, move_to)
			doc.is_archived, doc.archived_on = 1, frappe.utils.today()
			if kind == "area":
				for child in frappe.get_list("Life Area", filters={"parent_area": doc.name, "is_archived": 0}, pluck="name"):
					frappe.db.set_value("Life Area", child, {"is_archived": 1, "archived_on": doc.archived_on})
					archived.append(child)
		else:
			when = doc.archived_on
			doc.is_archived, doc.archived_on = 0, None
			if kind == "area":
				if doc.parent_area and frappe.db.get_value("Life Area", doc.parent_area, "is_archived"):
					from lifeos.goals import areas# its old parent is archived: back under Career

					doc.parent_area = areas.ensure(doc.space)[areas.DEFAULT_PARENT]
				if int(with_children or 0):
					f = {"parent_area": doc.name, "is_archived": 1}
					if when:
						f["archived_on"] = when
					for child in frappe.get_list("Life Area", filters=f, pluck="name"):
						frappe.db.set_value("Life Area", child, {"is_archived": 0, "archived_on": None})
						restored.append(child)
	doc.save() if name else doc.insert()
	made = []
	if kind == "area" and doc.part_kind and not doc.is_focus and (part_kind is not None or not name):
		from lifeos.goals import areas

		wanted = parse(focuses, None)
		made = areas.add_offered_focuses(doc.name, wanted if isinstance(wanted, list) else None)
	return {"name": doc.name, "title": doc.get(field), "archived_children": archived, "restored_children": restored, "focuses": made}


def _areas_admin_only(is_on=None):
	"""Only Life Admin changes areas (issue 12). An agent switching one gets the reason of issue 11."""
	permissions.require_login()
	if permissions.is_admin():
		return
	if is_on is not None and permissions.is_agent():
		frappe.throw(_("Only a person can switch an area on or off."), frappe.PermissionError, title=_("Only a person can switch areas"))
	frappe.throw(_("Only the owner can change areas."), frappe.PermissionError, title=_("Only the owner can change areas"))


def _move_open_work(doc, move_to):
	"""Before a part is archived, its open goals and tasks go to `move_to`; without it, a part that holds any is refused."""
	from lifeos.goals import areas

	work = areas.open_work(doc.name)
	if not (work["goals"] or work["tasks"]):
		return
	if not move_to:
		goals, tasks = len(work["goals"]), len(work["tasks"])
		frappe.throw(_("{0} has {1} and {2}. Choose where to move them before archiving it.").format(doc.area_name,
			_("1 open goal") if goals == 1 else _("{0} open goals").format(goals), _("1 open task") if tasks == 1 else _("{0} open tasks").format(tasks)),
			title=_("Area still has open records"))
	areas.move_work(doc.name, move_to)


@frappe.whitelist(methods=["GET"])
def area_open_work(area: str):
	"""What archiving a part would leave behind: how many open goals and tasks it holds, and the areas they can move to
	(its own area of life, then its other parts). Life Admin only."""
	_admin_only()
	from lifeos.goals import areas

	permissions.get_doc_checked("Life Area", area, "read")
	work = areas.open_work(area)
	return {"goals": len(work["goals"]), "tasks": len(work["tasks"]), "targets": areas.move_targets(area)}


@frappe.whitelist(methods=["POST"])
def create_space(space_name: str, owner_user: str | None = None):
	"""Create a space, for example a private space for a family member. Owner only. Every new space gets the seven areas of
	life with Career and Health on (issue 11)."""
	_admin_only()

	owner_user = owner_user or frappe.session.user
	if not frappe.db.exists("User", owner_user):
		frappe.throw(_("User {0} does not exist.").format(owner_user), title=_("User does not exist"))
	doc = frappe.get_doc({"doctype": "Life Space", "space_name": space_name.strip(), "owner_user": owner_user,
		"members": [{"user": owner_user, "access": "Write"}]}).insert()
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def set_member(space: str, user: str, access: str | None = None, remove: bool | int = 0, grant_role: str | None = None):
	"""Add a person or an agent to a space, change their access, or remove them. The one method for space access: Members
	and Agents both call it. Life Admin only. The user must already exist. Access defaults to Write for a person and Read
	for an agent. A user with no Life OS role is refused unless `grant_role` says which role to give: "Life User" for a
	person or "Life Agent" for an agent, and only then. This method never gives Life Admin, and never gives a role to a user
	who already has one. The owner of a space cannot be removed and keeps Write."""
	_admin_only()
	doc = frappe.get_doc("Life Space", space)
	if user in ("Administrator", "Guest"):
		frappe.throw(_("This account cannot be a member."), title=_("Account cannot be a member"))
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} does not exist. Create the user in Frappe first.").format(user), title=_("User does not exist"))
	if access not in (None, "", "Read", "Write"):
		frappe.throw(_("Access is Read or Write."), title=_("Access level not recognised"))
	row = next((m for m in doc.members if m.user == user), None)
	if grant_role:
		_check_grant(user, grant_role)
	if int(remove or 0):
		if user == doc.owner_user:
			frappe.throw(_("The owner of a space cannot be removed from it."), title=_("Space owner cannot be removed"))
		if row:
			doc.remove(row)
	elif row:
		if user == doc.owner_user and access == "Read":
			frappe.throw(_("The owner of a space always has Can edit."), title=_("Space owner must edit"))
		row.access = access or row.access
	else:
		_give_role(user, grant_role)
		doc.append("members", {"user": user, "access": access or ("Read" if permissions.is_agent(user) else "Write")})
	doc.save()
	people = _people([m.user for m in doc.members])
	return {"space": doc.name, "members": _member_rows(doc, people)}


def _life_roles(user):
	return set(frappe.get_roles(user)) & set(LIFE_ROLES)


def _check_grant(user, grant_role):
	"""Add member's role rule (issue 1): only Life User or Life Agent, and only to a user with no Life role yet. So an agent
	is never given Life User or Life Admin here."""
	if grant_role not in GRANTABLE.values():
		frappe.throw(_("Add member gives only the person or the agent role."), frappe.PermissionError, title=_("Role not allowed for member"))
	if _life_roles(user) - {grant_role}:
		frappe.throw(_("{0} already has a Life OS role. Change roles in Frappe.").format(user), frappe.PermissionError, title=_("User already has a role"))


def _give_role(user, grant_role):
	"""A user who has a Life role keeps it; one who has none gets the role the owner confirmed, and is refused without one."""
	if _life_roles(user):
		return
	if not grant_role:
		frappe.throw(_("{0} has no Life OS role yet. Choose whether they are a person or an agent.").format(user), title=_("Member needs a role"))
	u = frappe.get_doc("User", user)
	u.flags.ignore_permissions = True  # system: Life Admin only (checked by the caller); _check_grant allowed only Life User or Life Agent
	u.add_roles(grant_role)
	permissions.clear_cache()


@frappe.whitelist(methods=["POST"])
def set_agent_vault(space: str, allowed: bool | int):
	"""Let agents open the documents of one space's Vault, or not. Off by default. Life Admin only."""
	_admin_only()
	doc = frappe.get_doc("Life Space", space)
	doc.agents_can_read_vault = 1 if int(allowed or 0) else 0
	doc.save()
	return {"space": doc.name, "agents_can_read_vault": doc.agents_can_read_vault}


@frappe.whitelist(methods=["GET"])
def find_users(txt: str | None = "", space: str | None = None):
	"""Users who can be added to a space, people and agents alike: enabled users, never Administrator or Guest. Each has
	its kind (Person, Agent, or None for no Life OS role yet) and, with `space`, whether it is already a member. Admin only."""
	_admin_only()
	like = f"%{txt or ''}%"
	rows = frappe.get_all("User", filters={"enabled": 1, "name": ("not in", ["Administrator", "Guest"])},  # system: user and role lookups and the admin's space list are not space records
		or_filters={"name": ("like", like), "full_name": ("like", like)}, fields=["name", "full_name"], order_by="full_name asc", limit=20)
	people = _people([r.name for r in rows])
	members = set(frappe.get_all("Life Space Member", filters={"parent": space, "parenttype": "Life Space"}, pluck="user")) if space else set()  # system: user and role lookups and the admin's space list are not space records
	return [{"name": r.name, "full_name": r.full_name or r.name, "kind": people.get(r.name, {}).get("kind"),
		"is_member": r.name in members} for r in rows]


@frappe.whitelist(methods=["POST"])
def reorder(kind: str, names: str | list, parent_area: str | None = None):
	"""Put the rows of one ordered list (areas) in this order, in one call. For areas, `names` are siblings
	and `parent_area` is their parent ("" for the top level): moving an area into this list nests it there."""
	from lifeos.api.utils import parse

	if kind != "area":
		frappe.throw(_("Only areas have an order."), title=_("Only areas have an order"))
	_areas_admin_only()
	doctype = LISTS[kind][0]
	names = parse(names, []) or []
	for i, name in enumerate(names):
		doc = permissions.get_doc_checked(doctype, name, "write")
		if parent_area is not None and (doc.parent_area or "") != (parent_area or ""):
			save_item("area", name=name, parent_area=parent_area or "")
			doc.reload()
		if doc.sort_order != i + 1:
			frappe.db.set_value(doctype, name, "sort_order", i + 1)
	return {"names": names}
