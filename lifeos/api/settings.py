"""The Settings screen: spaces and members, areas, tags, dimensions, habits, review time, archive days."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.utils import parse

SETTING_FIELDS = ("default_space", "weekly_review_day", "weekly_review_time", "score_target", "archive_after_days", "stale_task_days",
	# UX fixes, set 5: Reset rules and the AI behind Ask (the key has its own method and is never sent back)
	"stuck_after_days", "stuck_limit", "open_task_goal", "someday_review_months", "ask_model", "short_model", "monthly_cap_usd")
LISTS = {
	"area": ("Life Area", "area_name"), "tag": ("Life Tag", "tag_name"), "dimension": ("Life Dimension", "dimension_name"),
	"habit": ("Life Habit", "title"), "person": ("Life Person", "full_name"),
}


def _admin_only():
	permissions.require_login()
	if not permissions.is_admin():
		frappe.throw(_("Only the owner can change this."), frappe.PermissionError)


def _counts(kind, space, names):
	"""The quiet count beside each row: areas, active records filed there; tags, tagged records; habits, months that
	track it; dimensions, check-ins that scored it."""
	if not names:
		return {}
	if kind == "area":
		out = {}
		from lifeos.index import also_in_sql

		for n in names:  # as the Timeline counts an area: filed there or also filed there
			# nosemgrep: frappe-sql-format-injection -- also_in_sql and vault_guard return fixed fragments; space and area are parameters
			out[n] = frappe.db.sql(f"""select count(*) from `tabLife Index` where space=%(space)s and is_archived=0
				and (area=%(area)s or {also_in_sql('area')}){permissions.vault_guard(space)}""", {"space": space, "area": n})[0][0]
		return out
	if kind == "tag":
		return dict(frappe.db.sql("""select tag, count(distinct parenttype, parent) from `tabLife Tag Link`
			where tag in %s group by tag""", (names,)))
	if kind == "habit":
		return dict(frappe.db.sql("""select habit, count(distinct parent) from `tabLife Month Plan Habit`
			where habit in %s group by habit""", (names,)))
	if kind == "dimension":
		return dict(frappe.db.sql("""select dimension, count(distinct parent) from `tabLife Check-in Score`
			where dimension in %s group by dimension""", (names,)))
	return {}


def _visible_user(user):
	return user not in ("Administrator", "Guest")


def _member_rows(doc):
	return [{"user": m.user, "access": m.access, "full_name": frappe.utils.get_fullname(m.user),
		"image": frappe.db.get_value("User", m.user, "user_image"), "is_owner": m.user == doc.owner_user}
		for m in doc.members if _visible_user(m.user) and not permissions.is_agent(m.user)]


def _agents(spaces):
	"""Users who are agents (Life Agent and no other Life role), with the spaces each reaches and when each last filed something."""
	users = frappe.get_all("Has Role", filters={"role": "Life Agent", "parenttype": "User"}, pluck="parent", distinct=True)
	out = []
	for u in sorted(set(users)):
		if not _visible_user(u) or not permissions.is_agent(u):
			continue
		reach = []
		for s in spaces:
			row = next((m for m in s.members if m.user == u), None)
			reach.append({"space": s.name, "access": row.access if row else None, "agents_can_read_vault": int(s.get("agents_can_read_vault") or 0)})
		last = frappe.db.sql("""select max(creation) from `tabLife Proposal` where owner=%s""", u)[0][0]
		last_chat = frappe.db.sql("""select max(creation) from `tabLife Chat Log` where owner=%s""", u)[0][0]
		last = max([d for d in (last, last_chat) if d], default=None)
		out.append({"user": u, "full_name": frappe.utils.get_fullname(u), "spaces": reach, "last_filed": str(last) if last else None})
	return out


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None):
	"""Everything the Settings screen shows for one space: the plain settings, the four lists with a count per row (archived
	rows too, for the Archived section), the spaces with their members, and the agents. Role names are never sent.
	The built-in Administrator is left out of every list."""
	space = permissions.resolve_space(space)
	s = frappe.get_cached_doc("Life Settings")
	lists = {}
	for kind, (doctype, field, key, extra, order) in {
		"area": ("Life Area", "area_name", "areas", ["parent_area", "sort_order"], "sort_order, area_name"),
		"tag": ("Life Tag", "tag_name", "tags", [], "tag_name"),
		"habit": ("Life Habit", "title", "habits", [], "title"),
		"dimension": ("Life Dimension", "dimension_name", "dimensions", ["sort_order"], "sort_order, dimension_name"),
	}.items():
		rows = frappe.get_all(doctype, filters={"space": space}, fields=["name", field, "is_archived", "archived_on", *extra], order_by=order, limit=1000)
		counts = _counts(kind, space, [r.name for r in rows])
		for r in rows:
			r["count"] = counts.get(r.name, 0)
			r["archived_on"] = str(r.archived_on) if r.archived_on else None
		lists[key] = rows
	out = {
		"space": space, "is_admin": permissions.is_admin(), "user": frappe.session.user,
		"settings": {f: (str(s.get(f)) if f == "weekly_review_time" and s.get(f) else s.get(f)) for f in SETTING_FIELDS},
		**lists,
		"people": frappe.get_all("Life Person", filters={"space": space}, fields=["name", "full_name", "relation"], order_by="full_name", limit=500),
		"spaces": [], "agents": [],
	}
	names = frappe.get_all("Life Space", pluck="name") if permissions.is_admin() else list(permissions.user_spaces())
	docs = [frappe.get_doc("Life Space", n) for n in sorted(names)]
	for doc in docs:
		out["spaces"].append({"name": doc.name, "owner_user": doc.owner_user, "owner_name": frappe.utils.get_fullname(doc.owner_user),
			"access": permissions.user_spaces().get(doc.name), "agents_can_read_vault": int(doc.agents_can_read_vault or 0), "members": _member_rows(doc),
			"ask_enabled": int(doc.ask_enabled or 0), "ask_can_read_vault": int(doc.ask_can_read_vault or 0)})
	if permissions.is_admin():
		out["agents"] = _agents(docs)
		out["ai"] = ai_settings()
	return out


def ai_settings():
	"""Settings, Admin, AI: whether a key is set (never the key), the models, the cap, the prices, and this month's spend by
	purpose and by user."""
	from lifeos.ai import client

	s = frappe.get_cached_doc("Life Settings")
	month = client.month()
	by_purpose = frappe.db.sql("select purpose, sum(cost), sum(input_tokens), sum(output_tokens) from `tabLife AI Usage` where month=%s group by purpose", month)
	by_user = frappe.db.sql("select user, sum(cost) from `tabLife AI Usage` where month=%s group by user", month)
	return {"key_set": client.is_set_up(), "ask_model": s.get("ask_model") or client.DEFAULT_ASK_MODEL, "short_model": s.get("short_model") or client.DEFAULT_SHORT_MODEL,
		"monthly_cap_usd": client.cap(), "spend": client.spend_status(),
		"prices": [{"model": m, "input_per_mtok": p[0], "output_per_mtok": p[1]} for m, p in client.prices().items()],
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
def set_ai_price(model: str, input_per_mtok: float, output_per_mtok: float):
	_admin_only()
	doc = frappe.get_doc("Life Settings")
	row = next((r for r in doc.ai_prices if r.model == model), None) or doc.append("ai_prices", {"model": model})
	row.input_per_mtok, row.output_per_mtok = float(input_per_mtok), float(output_per_mtok)
	if row.input_per_mtok < 0 or row.output_per_mtok < 0:
		frappe.throw(_("Prices cannot be negative."))
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
			frappe.throw(_("Unknown setting {0}.").format(k))
		doc.set(k, v)
	for f in ("score_target", "archive_after_days", "stale_task_days", "stuck_after_days", "someday_review_months"):
		if int(doc.get(f) or 0) <= 0:
			frappe.throw(_("{0} must be a positive number.").format(doc.meta.get_label(f)))
	for f in ("stuck_limit", "open_task_goal"):
		if int(doc.get(f) or 0) < 0:
			frappe.throw(_("{0} cannot be negative.").format(doc.meta.get_label(f)))
	if float(doc.get("monthly_cap_usd") or 0) < 0:
		frappe.throw(_("The monthly cap cannot be negative."))
	if int(doc.score_target) > 100:
		frappe.throw(_("The score target is a percentage."))
	doc.save()
	return {"saved": True}


ARCHIVABLE = ("area", "tag", "habit", "dimension")


@frappe.whitelist(methods=["POST"])
def save_item(kind: str, space: str | None = None, name: str | None = None, title: str | None = None, parent_area: str | None = None,
		relation: str | None = None, sort_order: int | None = None, is_archived: bool | int | None = None, delete: bool | int = 0,
		with_children: bool | int = 1):
	"""Add, rename, reorder, nest, archive or restore one area, tag, dimension or habit of a space, or a person.
	Archiving sets archived_on to today; records filed under the heading are not changed. Archiving an area archives its
	sub-areas with it. Restoring an area puts it back under its old parent if that parent is active, otherwise at the top
	level, and with_children=1 restores the sub-areas archived on the same day with it.
	delete=1 removes the row for good; the Settings screen does not offer it, agents and tests may use it."""
	if kind not in LISTS:
		frappe.throw(_("Unknown list."))
	doctype, field = LISTS[kind]
	if name:
		doc = permissions.get_doc_checked(doctype, name, "write")
		if int(delete or 0):
			doc.check_permission("delete")
			try:
				doc.delete()
			except frappe.LinkExistsError:
				frappe.throw(_("{0} is still used by other records. Remove it from them first{1}.").format(
					doc.get(field), _(", or archive it") if kind in ARCHIVABLE else ""))
			return {"deleted": name}
	else:
		space = permissions.resolve_space(space, write=True)
		doc = frappe.get_doc({"doctype": doctype, "space": space})
	if title is not None:
		if not title.strip():
			frappe.throw(_("A name is needed."))
		doc.set(field, title.strip())
	if kind == "area" and parent_area is not None:
		parent_area = parent_area or None
		if parent_area:
			if frappe.db.get_value("Life Area", parent_area, "parent_area"):
				frappe.throw(_("Areas nest one level deep: {0} is already inside another area.").format(frappe.db.get_value("Life Area", parent_area, "area_name")))
			if name and frappe.db.exists("Life Area", {"parent_area": name}):
				frappe.throw(_("An area with sub-areas stays at the top level."))
		doc.parent_area = parent_area
	if kind == "person" and relation is not None:
		doc.relation = relation
	if sort_order is not None and doc.meta.has_field("sort_order"):
		doc.sort_order = int(sort_order)
	restored = []
	archived = []
	if is_archived is not None and kind in ARCHIVABLE and int(is_archived) != int(doc.get("is_archived") or 0):
		if int(is_archived):
			doc.is_archived, doc.archived_on = 1, frappe.utils.today()
			if kind == "area":
				for child in frappe.get_all("Life Area", filters={"parent_area": doc.name, "is_archived": 0}, pluck="name"):
					frappe.db.set_value("Life Area", child, {"is_archived": 1, "archived_on": doc.archived_on})
					archived.append(child)
		else:
			when = doc.archived_on
			doc.is_archived, doc.archived_on = 0, None
			if kind == "area":
				if doc.parent_area and frappe.db.get_value("Life Area", doc.parent_area, "is_archived"):
					doc.parent_area = None  # its parent is archived: back at the top level
				if int(with_children or 0):
					f = {"parent_area": doc.name, "is_archived": 1}
					if when:
						f["archived_on"] = when
					for child in frappe.get_all("Life Area", filters=f, pluck="name"):
						frappe.db.set_value("Life Area", child, {"is_archived": 0, "archived_on": None})
						restored.append(child)
	doc.save() if name else doc.insert()
	return {"name": doc.name, "title": doc.get(field), "archived_children": archived, "restored_children": restored}


@frappe.whitelist(methods=["POST"])
def create_space(space_name: str, owner_user: str | None = None, starter_areas: bool | int = 1):
	"""Create a space, for example a private space for a family member, with the starter areas. Owner only."""
	_admin_only()
	from lifeos import seed
	from lifeos.constants import STARTER_AREAS

	owner_user = owner_user or frappe.session.user
	if not frappe.db.exists("User", owner_user):
		frappe.throw(_("User {0} does not exist.").format(owner_user))
	doc = frappe.get_doc({"doctype": "Life Space", "space_name": space_name.strip(), "owner_user": owner_user,
		"members": [{"user": owner_user, "access": "Write"}]}).insert()
	if int(starter_areas or 0):
		seed.make_areas(doc.name, STARTER_AREAS)
		seed.make_dimensions(doc.name)
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def set_member(space: str, user: str, access: str = "Write", remove: bool | int = 0):
	"""Add a user to a space, change their access, or remove them. Owner only. The user must already exist."""
	_admin_only()
	doc = frappe.get_doc("Life Space", space)
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} does not exist. Create the user in Frappe first.").format(user))
	if access not in ("Read", "Write"):
		frappe.throw(_("Access is Read or Write."))
	if user in ("Administrator", "Guest"):
		frappe.throw(_("This account cannot be a member."))
	row = next((m for m in doc.members if m.user == user), None)
	if int(remove or 0):
		if user == doc.owner_user:
			frappe.throw(_("The owner of a space cannot be removed from it."))
		if row:
			doc.remove(row)
	elif row:
		row.access = access
	else:
		doc.append("members", {"user": user, "access": access})
		if not set(frappe.get_roles(user)) & {"Life Admin", "Life User", "Life Agent"}:
			frappe.get_doc("User", user).add_roles("Life User")
	doc.save()
	return {"space": doc.name, "members": [{"user": m.user, "access": m.access} for m in doc.members]}


@frappe.whitelist(methods=["POST"])
def set_agent_vault(space: str, allowed: bool | int):
	"""Let agents open the documents of one space's Vault, or not. Off by default. Life Admin only."""
	_admin_only()
	doc = frappe.get_doc("Life Space", space)
	doc.agents_can_read_vault = 1 if int(allowed or 0) else 0
	doc.save()
	return {"space": doc.name, "agents_can_read_vault": doc.agents_can_read_vault}


@frappe.whitelist(methods=["GET"])
def find_users(txt: str | None = ""):
	"""People who can be added to a space: enabled website or desk users, never Administrator, Guest or an agent. Admin only."""
	_admin_only()
	like = f"%{txt or ''}%"
	rows = frappe.db.sql("""select name, full_name from `tabUser` where enabled=1 and name not in ('Administrator', 'Guest')
		and (name like %s or full_name like %s) order by full_name limit 20""", (like, like), as_dict=True)
	return [r for r in rows if not permissions.is_agent(r.name)]


@frappe.whitelist(methods=["POST"])
def reorder(kind: str, names: str | list, parent_area: str | None = None):
	"""Put the rows of one ordered list (areas, dimensions) in this order, in one call. For areas, `names` are siblings
	and `parent_area` is their parent ("" for the top level): moving an area into this list nests it there."""
	from lifeos.api.utils import parse

	if kind not in ("area", "dimension"):
		frappe.throw(_("Only areas and check-in dimensions have an order."))
	doctype = LISTS[kind][0]
	names = parse(names, []) or []
	for i, name in enumerate(names):
		doc = permissions.get_doc_checked(doctype, name, "write")
		if kind == "area" and parent_area is not None and (doc.parent_area or "") != (parent_area or ""):
			save_item("area", name=name, parent_area=parent_area or "")
			doc.reload()
		if doc.sort_order != i + 1:
			frappe.db.set_value(doctype, name, "sort_order", i + 1)
	return {"names": names}
