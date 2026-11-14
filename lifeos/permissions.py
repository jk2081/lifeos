"""Space permissions. A user sees a record only if they are a member of its space."""
import frappe
from frappe import _


def user_spaces(user=None) -> dict:
	"""Return {space: access} for the user. access is 'Read' or 'Write'."""
	user = user or frappe.session.user
	cache = getattr(frappe.local, "lifeos_spaces", None)
	if cache is None:
		cache = frappe.local.lifeos_spaces = {}
	if user not in cache:
		out = {}
		if user and user != "Guest":
			for row in frappe.db.sql(
				"select parent, access from `tabLife Space Member` where user=%s and parenttype='Life Space'", user
			):
				if row[1] == "Write" or row[0] not in out:
					out[row[0]] = row[1]
			for (name,) in frappe.db.sql("select name from `tabLife Space` where owner_user=%s", user):
				out[name] = "Write"
		cache[user] = out
	return cache[user]


def clear_cache():
	frappe.local.lifeos_spaces = {}


def is_agent(user=None) -> bool:
	"""True for a user who acts only as an agent."""
	roles = frappe.get_roles(user or frappe.session.user)
	return "Life Agent" in roles and "Life Admin" not in roles and "Life User" not in roles


def is_admin(user=None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or "Life Admin" in frappe.get_roles(user)


def has_app_permission():
	return bool(set(frappe.get_roles()) & {"Life Admin", "Life User", "Life Agent"}) or frappe.session.user == "Administrator"


def _in_list(spaces) -> str:
	return ", ".join(frappe.db.escape(s) for s in spaces)


def query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return ""
	spaces = user_spaces(user)
	if not spaces:
		return "1=0"
	return f"`tab{doctype}`.`space` in ({_in_list(spaces)})"


def has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	if ptype == "delete" and is_agent(user):
		return False
	space = doc.get("space")
	if not space:
		return True  # a new record with no space yet; validate requires one
	access = user_spaces(user).get(space)
	if not access:
		return False
	if ptype in ("write", "create", "delete", "submit", "cancel", "amend") and access != "Write":
		return False
	return True


def space_query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if is_admin(user):
		return ""
	spaces = user_spaces(user)
	if not spaces:
		return "1=0"
	return f"`tabLife Space`.`name` in ({_in_list(spaces)})"


def space_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if is_admin(user):
		return True
	if ptype not in ("read", "select", "report", "print", "email", "export"):
		return False
	return doc.name in user_spaces(user)


def event_query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return ""
	spaces = user_spaces(user)
	free = "ifnull(`tabEvent`.`life_space`, '') = ''"
	if not spaces:
		return f"({free})"
	return f"({free} or `tabEvent`.`life_space` in ({_in_list(spaces)}))"


def event_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if user == "Administrator" or not doc.get("life_space"):
		return True
	if ptype == "delete" and is_agent(user):
		return False
	access = user_spaces(user).get(doc.life_space)
	if not access:
		return False
	if ptype in ("write", "create", "delete") and access != "Write":
		return False
	return True


# ---- helpers for API methods ----

def require_login():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in."), frappe.PermissionError)


def require_space(space, write=False):
	"""Stop unless the session user is a member of the space (with Write access when asked)."""
	require_login()
	if not space or not frappe.db.exists("Life Space", space):
		frappe.throw(_("Space not found."), frappe.PermissionError)
	if frappe.session.user == "Administrator":
		return space
	access = user_spaces().get(space)
	if not access or (write and access != "Write"):
		frappe.throw(_("You do not have access to this space."), frappe.PermissionError)
	return space


def default_space(user=None):
	"""The user's own private space if they own one, else the site default if they belong to it, else any."""
	user = user or frappe.session.user
	spaces = user_spaces(user)
	if user == "Administrator" and not spaces:
		return frappe.db.get_single_value("Life Settings", "default_space")
	owned = frappe.db.get_value("Life Space", {"owner_user": user, "name": ("in", list(spaces) or [""])}, "name", order_by="creation asc")
	if owned:
		return owned
	default = frappe.db.get_single_value("Life Settings", "default_space")
	if default in spaces:
		return default
	return next(iter(spaces), None)


def resolve_space(space=None, write=False):
	"""Return the given space, or the user's default one, after checking membership."""
	space = space or default_space()
	if not space:
		frappe.throw(_("You are not a member of any space."), frappe.PermissionError)
	return require_space(space, write=write)


def get_doc_checked(doctype, name, ptype="read"):
	"""Load a record and stop unless the session user may `ptype` it."""
	require_login()
	doc = frappe.get_doc(doctype, name)
	doc.check_permission(ptype)
	return doc
