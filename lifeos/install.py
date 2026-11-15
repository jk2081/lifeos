"""Install and migrate steps: roles, the Event custom field, indexes, the two starting spaces."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from lifeos.constants import ROLES, STARTER_AREAS


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	make_roles()
	create_custom_fields({
		"Event": [{
			"fieldname": "life_space", "label": "Life Space", "fieldtype": "Link", "options": "Life Space",
			"insert_after": "event_type", "search_index": 1,
		}]
	}, ignore_validate=True)
	from lifeos import index
	index.ensure_indexes()
	make_spaces()
	frappe.db.commit()


def make_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1 if role == "Life Admin" else 0}).insert(ignore_permissions=True)
	# Frappe creates a role named in a DocType's permissions before after_install runs, with desk access on. Life User
	# and Life Agent never open the back office: turn it off, which also makes their users Website Users again.
	for role in ("Life User", "Life Agent"):
		doc = frappe.get_doc("Role", role)
		if doc.desk_access:
			doc.desk_access = 0
			doc.save(ignore_permissions=True)
			doc.update_user_type_on_change()  # on_update skips this while installing


def make_spaces():
	owner = frappe.db.get_value("Life Space", "Private", "owner_user") or "Administrator"
	for name in ("Private", "Shared"):
		if not frappe.db.exists("Life Space", name):
			frappe.get_doc({
				"doctype": "Life Space", "space_name": name, "owner_user": owner,
				"members": [{"user": owner, "access": "Write"}],
			}).insert(ignore_permissions=True)
	settings = frappe.get_single("Life Settings")
	if not settings.default_space:
		settings.default_space = "Private"
		settings.flags.ignore_permissions = True
		settings.save()
	from lifeos import seed
	seed.ensure_structure()


def set_owner(user):
	"""Make `user` the owner: Life Admin role, owner and member of Private and Shared.

	Run: bench --site SITE execute lifeos.install.set_owner --kwargs "{'user': 'you@example.com'}"
	"""
	if not frappe.db.exists("User", user):
		frappe.throw(f"User {user} does not exist.")
	frappe.get_doc("User", user).add_roles("Life Admin", "Life User")
	for name in ("Private", "Shared"):
		space = frappe.get_doc("Life Space", name)
		space.owner_user = user
		if user not in [m.user for m in space.members]:
			space.append("members", {"user": user, "access": "Write"})
		space.save(ignore_permissions=True)
	frappe.db.commit()


def add_member(space, user, access="Write", role="Life User"):
	"""Add a user to a space and give them a role.

	Run: bench --site SITE execute lifeos.install.add_member --kwargs "{'space': 'Shared', 'user': 'a@b.c'}"
	"""
	frappe.get_doc("User", user).add_roles(role)
	doc = frappe.get_doc("Life Space", space)
	for m in doc.members:
		if m.user == user:
			m.access = access
			break
	else:
		doc.append("members", {"user": user, "access": access})
	doc.save(ignore_permissions=True)
	frappe.db.commit()


def make_personal_space(user, space_name=None):
	"""Create a private space for a family member, with the starter areas."""
	from lifeos import seed
	space_name = space_name or f"{frappe.db.get_value('User', user, 'first_name') or user}'s space"
	doc = frappe.get_doc({"doctype": "Life Space", "space_name": space_name, "owner_user": user,
		"members": [{"user": user, "access": "Write"}]}).insert(ignore_permissions=True)
	seed.make_areas(doc.name, STARTER_AREAS)
	seed.make_dimensions(doc.name)
	return doc.name
