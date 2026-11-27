"""Install and migrate steps: roles, the Event custom field, indexes, the starting space."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from lifeos.constants import ROLES

# set 8: what the weekly review knows about a meeting read from Google Calendar
MEETING_FIELDS = [
	{"fieldname": "life_attendees", "label": "Life Attendees", "fieldtype": "Small Text", "insert_after": "life_space", "read_only": 1,
		"description": "JSON: the attendees' emails and names, as Google lists them."},
	{"fieldname": "life_recurring", "label": "Life Recurring", "fieldtype": "Check", "insert_after": "life_attendees", "read_only": 1},
	{"fieldname": "life_matters", "label": "Life Matters", "fieldtype": "Check", "insert_after": "life_recurring"},
	{"fieldname": "life_matters_set_by", "label": "Life Matters Set By", "fieldtype": "Select", "options": "\nRule\nOwner",
		"insert_after": "life_matters"},
	{"fieldname": "life_hidden", "label": "Hidden in Life OS", "fieldtype": "Check", "insert_after": "life_matters_set_by", "no_copy": 1,
		"description": "Life OS stops showing this event. Set from the event's drawer; nothing is deleted or sent to Google."},
	{"fieldname": "life_key_date", "label": "Key Date", "fieldtype": "Check", "insert_after": "life_hidden", "no_copy": 1, "search_index": 1,
		"description": "An event that shapes the plan (a trip, a birthday, a deadline, an exam), shown in Year and Month. Set by the key-date skill, or by hand."},
	{"fieldname": "life_key_date_set_by", "label": "Key Date Set By", "fieldtype": "Select", "options": "\nRule\nSkill\nOwner",
		"insert_after": "life_key_date", "no_copy": 1, "read_only": 1},
	{"fieldname": "life_followups_on", "label": "Life Follow-ups Read On", "fieldtype": "Datetime", "insert_after": "life_matters_set_by",
		"read_only": 1},
]
GOOGLE_FIELDS = [
	{"fieldname": "life_read_calendars", "label": "Life OS Reads", "fieldtype": "Small Text", "insert_after": "google_calendar_id",
		"description": "JSON list of the calendar IDs Life OS reads (read-only; nothing is ever written to Google)."},
	{"fieldname": "life_last_synced", "label": "Life OS Last Synced", "fieldtype": "Datetime", "insert_after": "life_read_calendars", "read_only": 1},
	{"fieldname": "life_sync_error", "label": "Life OS Sync Error", "fieldtype": "Small Text", "insert_after": "life_last_synced", "read_only": 1},
]

# issue 7: files of Life OS records are stored once per space by SHA-256, and an item's earlier versions point to the current file
FILE_FIELDS = [
	{"fieldname": "life_sha256", "label": "Life OS SHA-256", "fieldtype": "Data", "insert_after": "content_hash", "read_only": 1,
		"search_index": 1, "no_copy": 1},
	{"fieldname": "life_version_of", "label": "Life OS Earlier Version Of", "fieldtype": "Data", "insert_after": "life_sha256",
		"read_only": 1, "search_index": 1, "no_copy": 1, "description": "The current File row this earlier version was replaced by."},
]


# issue 97: what the person likes to be called; the full name on the account is left alone
USER_FIELDS = [{"fieldname": "preferred_name", "label": "Preferred Name", "fieldtype": "Data", "insert_after": "last_name", "no_copy": 1}]


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
		}, *MEETING_FIELDS],
		"Google Calendar": GOOGLE_FIELDS,
		"User": USER_FIELDS,
		"File": FILE_FIELDS,
	}, ignore_validate=True)
	from lifeos.calendar import key_dates
	key_dates.backfill()  # issue 100: the events already on the calendar get the rule's answer
	from lifeos.library import index
	index.ensure_indexes()
	make_spaces()
	from lifeos.library import globalsearch
	globalsearch.install()  # issue 98: search covers the whole app, through Frappe's Global Search
	from lifeos.skills import runner, store

	runner.ensure_brain_user()  # issue 28: the user skills run as
	store.install()  # the built-in skills and their examples; an owner's edit is kept
	from lifeos.brain import rules

	for space in frappe.get_all("Life Space", pluck="name"):  # system: setup runs before any person has roles
		rules.ensure_builtins(space)  # issue 117: each space has the two built-in rules
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- after_install: the spaces and index DDL must be kept before install-app goes on


def make_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1 if role == "Life Admin" else 0}).insert(ignore_permissions=True)  # system: install runs before any person has roles
	# Frappe creates a role named in a DocType's permissions before after_install runs, with desk access on. Life User
	# and Life Agent never open the back office: turn it off, which also makes their users Website Users again.
	for role in ("Life User", "Life Agent"):
		doc = frappe.get_doc("Role", role)
		if doc.desk_access:
			doc.desk_access = 0
			doc.save(ignore_permissions=True)  # system: install runs before any person has roles
			doc.update_user_type_on_change()  # on_update skips this while installing


# issue 46: a new site has one space. Spaces stay in the data model; a second one is made by hand (the acceptance site's
# `lifeos.tools.devtools.setup_users` makes Shared).
STARTING_SPACES = ("Private",)


def make_spaces():
	owner = frappe.db.get_value("Life Space", "Private", "owner_user") or "Administrator"
	for name in STARTING_SPACES:
		if not frappe.db.exists("Life Space", name):
			frappe.get_doc({
				"doctype": "Life Space", "space_name": name, "owner_user": owner,
				"members": [{"user": owner, "access": "Write"}],
			}).insert(ignore_permissions=True)  # system: install runs before any person has roles
	settings = frappe.get_single("Life Settings")
	if not settings.default_space:
		settings.default_space = "Private"
		settings.flags.ignore_permissions = True  # system: install runs before any person has roles
		settings.save()
	from lifeos.tools import seed
	seed.ensure_structure()


def set_owner(user):
	"""Make `user` the owner: Life Admin role, owner and member of every space the site has.

	Run: bench --site SITE execute lifeos.install.set_owner --kwargs "{'user': 'you@example.com'}"
	"""
	if not frappe.db.exists("User", user):
		frappe.throw(f"User {user} does not exist.", title=frappe._("User does not exist"))
	frappe.get_doc("User", user).add_roles("Life Admin", "Life User")
	for name in frappe.get_all("Life Space", pluck="name"):
		space = frappe.get_doc("Life Space", name)
		space.owner_user = user
		if user not in [m.user for m in space.members]:
			space.append("members", {"user": user, "access": "Write"})
		space.save(ignore_permissions=True)  # system: install runs before any person has roles


def new_owner(email, full_name, send_welcome_email=1, space="Private", use_focuses=0):
	"""Set up a new person's site (issue 49), once, by whoever made the site: a user with Life Admin who owns Private.

	No password is passed or set here: the person sets their own through Frappe's welcome email, or a reset link sent from
	the User record. If the site cannot send email yet, the command says so and the user is still made.

	`use_focuses=1` switches on "Use focuses" (issue 57), for an owner who asks for it; it is off for a new person.

	Run: bench --site SITE execute lifeos.install.new_owner --kwargs "{'email': 'you@example.com', 'full_name': 'Your Name'}"
	"""
	email = (email or "").strip().lower()
	full_name = " ".join((full_name or "").split())
	if not email or "@" not in email or not full_name:
		frappe.throw(frappe._("An email address and a full name are needed."), title=frappe._("Email and name needed"))
	if not frappe.db.exists("Life Space", space):
		setup()
	first, _sep, last = full_name.partition(" ")
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": first, "last_name": last, "user_type": "System User",
			"send_welcome_email": 0}).insert(ignore_permissions=True)  # system: install runs before any person has roles
		if int(send_welcome_email or 0):
			try:
				frappe.get_doc("User", email).send_welcome_mail_to_user()
			except Exception:
				frappe.clear_messages()
				print(f"The welcome email could not be sent. Send a password reset link to {email} from the User record once the site can send email.")
	frappe.get_doc("User", email).add_roles("Life Admin", "Life User")
	doc = frappe.get_doc("Life Space", space)
	doc.owner_user = email
	if email not in [m.user for m in doc.members]:
		doc.append("members", {"user": email, "access": "Write"})
	doc.save(ignore_permissions=True)  # system: install runs before any person has roles
	if int(use_focuses or 0):
		frappe.db.set_single_value("Life Settings", "use_focuses", 1)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- a bench execute command: the user and the space are kept when it ends
	return {"user": email, "space": space}


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
	doc.save(ignore_permissions=True)  # system: install runs before any person has roles

