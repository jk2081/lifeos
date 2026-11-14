"""Helpers for the local test site and the test suite. Not used in production."""
import frappe

OWNER, FAMILY, AGENT = "owner@lifeos.test", "family@lifeos.test", "hermes@lifeos.test"


def make_user(email, first_name, roles, password=None):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0,
			"user_type": "System User"}).insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
	user.add_roles(*roles)
	if password:
		from frappe.utils.password import update_password
		update_password(email, password)
	return user


def setup_users(password=None):
	"""Create the three test users: the owner, a family member who is only in Shared, and an agent.

	Run: bench --site SITE execute lifeos.devtools.setup_users --kwargs "{'password': '...'}"
	"""
	from lifeos import install, permissions

	make_user(OWNER, "Jai", ["Life Admin", "Life User"], password)
	make_user(FAMILY, "Family", ["Life User"], password)
	make_user(AGENT, "Hermes", ["Life Agent"], password)
	install.set_owner(OWNER)
	install.add_member("Shared", FAMILY, "Write", "Life User")
	install.add_member("Private", AGENT, "Write", "Life Agent")
	install.add_member("Shared", AGENT, "Write", "Life Agent")
	permissions.clear_cache()
	frappe.db.commit()
	return "Users ready."


def agent_api_key(user=AGENT):
	"""Create an API key and secret for an agent user and print them once. Never stored in the repo."""
	doc = frappe.get_doc("User", user)
	secret = frappe.generate_hash(length=15)
	if not doc.api_key:
		doc.api_key = frappe.generate_hash(length=15)
	doc.api_secret = secret
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return f"{doc.api_key}:{secret}"
