"""Shared set-up for the lifeos tests: two spaces, an owner, a family member and an agent."""
import frappe
from frappe.tests import IntegrationTestCase

from lifeos import areas, devtools, permissions, seed

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
		frappe.db.commit()  # the full-text index drops deleted rows only at commit
		for name, members in ((PRIVATE, [OWNER, AGENT]), (SHARED, [OWNER, FAMILY, AGENT])):
			if not frappe.db.exists("Life Space", name):
				frappe.get_doc({"doctype": "Life Space", "space_name": name, "owner_user": OWNER,
					"members": [{"user": u, "access": "Write"} for u in members]}).insert()
		cls.areas = seed.make_areas(PRIVATE, ["Tea", "Personal", "Money"], under={"Personal": "Health"})
		cls.shared_areas = seed.make_areas(SHARED, ["Family", "Work"], under={"Family": "Relationships"})
		# issue 11: the seven areas of life of each space; "Tea" and "Work" are parts of Career, "Personal" of Health
		cls.life = areas.life_areas(PRIVATE)
		cls.shared_life = areas.life_areas(SHARED)
		seed.make_dimensions(PRIVATE)
		permissions.clear_cache()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Life Settings", "require_done_when", 1)  # the default again, as the tests commit
		for name in (PRIVATE, SHARED, "Anya's space"):
			devtools.purge_space(name, drop=True)
		frappe.db.commit()
		permissions.clear_cache()
		super().tearDownClass()

	def setUp(self):
		permissions.clear_cache()
		frappe.set_user(OWNER)
		# issue 56: new goals need a finish line by default; the tests that make goals through the API without one
		# predate that, and test_goals switches the setting back on
		frappe.db.set_single_value("Life Settings", "require_done_when", 0)
		# issue 57: Open goals are retired; the tests that make one through the API predate that, and test_goals switches it off
		frappe.flags.lifeos_allow_open_goals = True
		# issue 58: process-capture ships on, so every new capture would start a Brain run; the tests that predate it are about agents
		# and the Inbox, and the tests that want the Brain (test_skills, test_brain) switch it on themselves
		frappe.db.set_value("Life Skill", "process-capture", "active", 0)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.flags.lifeos_allow_early_close = False
		frappe.flags.lifeos_allow_open_goals = False

	def as_user(self, user):
		permissions.clear_cache()
		frappe.set_user(user)

	def make(self, doctype, space=PRIVATE, **values):
		return frappe.get_doc({"doctype": doctype, "space": space, **values}).insert()
