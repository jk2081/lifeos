"""Shared set-up for the lifeos tests: two spaces, an owner, a family member and an agent."""
import frappe
from frappe.tests import IntegrationTestCase

from lifeos import devtools, permissions, seed

OWNER, FAMILY, AGENT = devtools.OWNER, devtools.FAMILY, devtools.AGENT
PRIVATE, SHARED = "Test Private", "Test Shared"


class LifeTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		devtools.make_user(OWNER, "Jai", ["Life Admin", "Life User"])
		devtools.make_user(FAMILY, "Family", ["Life User"])
		devtools.make_user(AGENT, "Hermes", ["Life Agent"])
		for name in (PRIVATE, SHARED):
			devtools.purge_space(name)
		for name, members in ((PRIVATE, [OWNER, AGENT]), (SHARED, [OWNER, FAMILY, AGENT])):
			if not frappe.db.exists("Life Space", name):
				frappe.get_doc({"doctype": "Life Space", "space_name": name, "owner_user": OWNER,
					"members": [{"user": u, "access": "Write"} for u in members]}).insert()
		cls.areas = seed.make_areas(PRIVATE, ["Tea", "Personal", "Money"])
		cls.shared_areas = seed.make_areas(SHARED, ["Family", "Work"])
		seed.make_dimensions(PRIVATE)
		permissions.clear_cache()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in (PRIVATE, SHARED, "Anya's space"):
			devtools.purge_space(name, drop=True)
		frappe.db.commit()
		permissions.clear_cache()
		super().tearDownClass()

	def setUp(self):
		permissions.clear_cache()
		frappe.set_user(OWNER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.flags.lifeos_allow_early_close = False

	def as_user(self, user):
		permissions.clear_cache()
		frappe.set_user(user)

	def make(self, doctype, space=PRIVATE, **values):
		return frappe.get_doc({"doctype": doctype, "space": space, **values}).insert()
