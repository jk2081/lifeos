"""The Settings screen: spaces and members, areas, tags, dimensions, habits, review time, archive days."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.utils import parse

SETTING_FIELDS = ("default_space", "weekly_review_day", "weekly_review_time", "score_target", "archive_after_days", "stale_task_days")
LISTS = {
	"area": ("Life Area", "area_name"), "tag": ("Life Tag", "tag_name"), "dimension": ("Life Dimension", "dimension_name"),
	"habit": ("Life Habit", "title"), "person": ("Life Person", "full_name"),
}


def _admin_only():
	permissions.require_login()
	if not permissions.is_admin():
		frappe.throw(_("Only the owner can change this."), frappe.PermissionError)


@frappe.whitelist()
def get(space=None):
	"""Everything the Settings screen shows for one space."""
	space = permissions.resolve_space(space)
	s = frappe.get_cached_doc("Life Settings")
	out = {
		"space": space, "is_admin": permissions.is_admin(),
		"settings": {f: (str(s.get(f)) if f == "weekly_review_time" and s.get(f) else s.get(f)) for f in SETTING_FIELDS},
		"areas": frappe.get_all("Life Area", filters={"space": space}, fields=["name", "area_name", "parent_area", "sort_order", "is_archived"], order_by="sort_order, area_name", limit=1000),
		"tags": frappe.get_all("Life Tag", filters={"space": space}, fields=["name", "tag_name"], order_by="tag_name", limit=500),
		"dimensions": frappe.get_all("Life Dimension", filters={"space": space}, fields=["name", "dimension_name", "sort_order"], order_by="sort_order", limit=50),
		"habits": frappe.get_all("Life Habit", filters={"space": space}, fields=["name", "title"], order_by="title", limit=200),
		"people": frappe.get_all("Life Person", filters={"space": space}, fields=["name", "full_name", "relation"], order_by="full_name", limit=500),
		"spaces": [],
	}
	names = frappe.get_all("Life Space", pluck="name") if permissions.is_admin() else list(permissions.user_spaces())
	for name in sorted(names):
		doc = frappe.get_cached_doc("Life Space", name)
		out["spaces"].append({"name": doc.name, "owner_user": doc.owner_user,
			"members": [{"user": m.user, "access": m.access, "full_name": frappe.utils.get_fullname(m.user),
				"roles": [r for r in frappe.get_roles(m.user) if r.startswith("Life ")]} for m in doc.members]})
	return out


@frappe.whitelist(methods=["POST"])
def save(values):
	"""Change Life Settings. Owner only."""
	_admin_only()
	values = parse(values, {}) or {}
	doc = frappe.get_doc("Life Settings")
	for k, v in values.items():
		if k not in SETTING_FIELDS:
			frappe.throw(_("Unknown setting {0}.").format(k))
		doc.set(k, v)
	for f in ("score_target", "archive_after_days", "stale_task_days"):
		if int(doc.get(f) or 0) <= 0:
			frappe.throw(_("{0} must be a positive number.").format(doc.meta.get_label(f)))
	if int(doc.score_target) > 100:
		frappe.throw(_("The score target is a percentage."))
	doc.save()
	return {"saved": True}


@frappe.whitelist(methods=["POST"])
def save_item(kind, space=None, name=None, title=None, parent_area=None, relation=None, sort_order=None, is_archived=None, delete=0):
	"""Add, rename, reorder or remove one area, tag, dimension, habit or person of a space."""
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
					doc.get(field), _(", or archive it") if kind == "area" else ""))
			return {"deleted": name}
	else:
		space = permissions.resolve_space(space, write=True)
		doc = frappe.get_doc({"doctype": doctype, "space": space})
	if title is not None:
		if not title.strip():
			frappe.throw(_("A name is needed."))
		doc.set(field, title.strip())
	if kind == "area":
		if parent_area is not None:
			doc.parent_area = parent_area or None
		if is_archived is not None:
			doc.is_archived = int(is_archived)
	if kind == "person" and relation is not None:
		doc.relation = relation
	if sort_order is not None and doc.meta.has_field("sort_order"):
		doc.sort_order = int(sort_order)
	doc.save() if name else doc.insert()
	return {"name": doc.name, "title": doc.get(field)}


@frappe.whitelist(methods=["POST"])
def create_space(space_name, owner_user=None, starter_areas=1):
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
def set_member(space, user, access="Write", remove=0):
	"""Add a user to a space, change their access, or remove them. Owner only. The user must already exist."""
	_admin_only()
	doc = frappe.get_doc("Life Space", space)
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} does not exist. Create the user in Frappe first.").format(user))
	if access not in ("Read", "Write"):
		frappe.throw(_("Access is Read or Write."))
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
