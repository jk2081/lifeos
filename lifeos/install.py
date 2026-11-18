"""Install and migrate steps: roles, the Event custom field, indexes, the two starting spaces."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from lifeos.constants import ROLES, STARTER_AREAS

# set 8: what the weekly review knows about a meeting read from Google Calendar
MEETING_FIELDS = [
	{"fieldname": "life_attendees", "label": "Life Attendees", "fieldtype": "Small Text", "insert_after": "life_space", "read_only": 1,
		"description": "JSON: the attendees' emails and names, as Google lists them."},
	{"fieldname": "life_recurring", "label": "Life Recurring", "fieldtype": "Check", "insert_after": "life_attendees", "read_only": 1},
	{"fieldname": "life_matters", "label": "Life Matters", "fieldtype": "Check", "insert_after": "life_recurring"},
	{"fieldname": "life_matters_set_by", "label": "Life Matters Set By", "fieldtype": "Select", "options": "\nRule\nOwner",
		"insert_after": "life_matters"},
	{"fieldname": "life_followups_on", "label": "Life Follow-ups Read On", "fieldtype": "Datetime", "insert_after": "life_matters_set_by",
		"read_only": 1},
]
GOOGLE_FIELDS = [
	{"fieldname": "life_read_calendars", "label": "Life OS Reads", "fieldtype": "Small Text", "insert_after": "google_calendar_id",
		"description": "JSON list of the calendar IDs Life OS reads (read-only; nothing is ever written to Google)."},
	{"fieldname": "life_last_synced", "label": "Life OS Last Synced", "fieldtype": "Datetime", "insert_after": "life_read_calendars", "read_only": 1},
	{"fieldname": "life_sync_error", "label": "Life OS Sync Error", "fieldtype": "Small Text", "insert_after": "life_last_synced", "read_only": 1},
]


def after_install():
	setup()
	from lifeos.patches.v7 import lens_areas

	lens_areas.execute()  # the starter areas get their colours and are pinned, as on sites migrated in set 6


def after_migrate():
	setup()


def setup():
	make_roles()
	create_custom_fields({
		"Event": [{
			"fieldname": "life_space", "label": "Life Space", "fieldtype": "Link", "options": "Life Space",
			"insert_after": "event_type", "search_index": 1,
		}, *MEETING_FIELDS],
		"Google Calendar": GOOGLE_FIELDS,
	}, ignore_validate=True)
	from lifeos import index
	index.ensure_indexes()
	make_spaces()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- after_install: the spaces and index DDL must be kept before install-app goes on


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


def make_personal_space(user, space_name=None):
	"""Create a private space for a family member, with the starter areas."""
	from lifeos import seed
	space_name = space_name or f"{frappe.db.get_value('User', user, 'first_name') or user}'s space"
	doc = frappe.get_doc({"doctype": "Life Space", "space_name": space_name, "owner_user": user,
		"members": [{"user": user, "access": "Write"}]}).insert(ignore_permissions=True)
	seed.make_areas(doc.name, STARTER_AREAS)
	seed.make_dimensions(doc.name)
	return doc.name
