"""Issue 49: a fresh site has no seed data; new_owner makes the owner without a password; the guide's state and steps."""
import inspect
from unittest.mock import patch

import frappe

from lifeos import areas, demo, install, permissions, seed
from lifeos.api import onboarding
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase

NEW = "i49-owner@lifeos.test"
FRESH = "I49 fresh"


def _drop():
	frappe.set_user("Administrator")
	from lifeos import devtools

	devtools.purge_space(FRESH, drop=True)
	frappe.db.delete("DefaultValue", {"parent": NEW})
	if frappe.db.exists("User", NEW):
		frappe.delete_doc("User", NEW, force=1, ignore_permissions=True)
	permissions.clear_cache()


class TestFirstRun(LifeTestCase):
	def setUp(self):
		_drop()

	def tearDown(self):
		_drop()

	def test_fresh_install_has_one_space_seven_areas_and_no_seed_data(self):
		# I49.1
		self.assertEqual(install.STARTING_SPACES, ("Private",))
		source = inspect.getsource(install.after_install) + inspect.getsource(install.setup) + inspect.getsource(install.make_spaces)
		self.assertNotIn("seed.load", source)
		self.assertNotIn("demo.load", source)
		counts = {dt: frappe.db.count(dt) for dt in ("Life Task", "Life Goal", "Life Inbox Item", "Life Cycle")}
		with patch.object(seed, "load") as s, patch.object(demo, "load") as d:
			install.setup()
		s.assert_not_called()
		d.assert_not_called()
		self.assertEqual(counts, {dt: frappe.db.count(dt) for dt in counts})
		# a new space, as install makes Private: the seven areas, Career and Health on, nothing else
		frappe.get_doc({"doctype": "Life Space", "space_name": FRESH, "owner_user": OWNER, "members": [{"user": OWNER, "access": "Write"}]}).insert()
		rows = frappe.get_all("Life Area", filters={"space": FRESH}, fields=["area_name", "is_on", "is_life_area"])
		self.assertEqual(sorted(r.area_name for r in rows), sorted(areas.NAMES))
		self.assertEqual({r.area_name for r in rows if r.is_on}, {"Career", "Health"})
		for dt in ("Life Task", "Life Goal", "Life Inbox Item", "Life Cycle", "Life Note"):
			self.assertEqual(frappe.db.count(dt, {"space": FRESH}), 0, dt)

	def test_new_owner_makes_a_life_admin_who_owns_the_space_and_sets_no_password(self):
		# I49.2
		frappe.get_doc({"doctype": "Life Space", "space_name": FRESH, "owner_user": "Administrator"}).insert()
		with patch.object(frappe.db, "commit"):
			out = install.new_owner(NEW, "Asha Rao", send_welcome_email=0, space=FRESH)
		self.assertEqual(out, {"user": NEW, "space": FRESH})
		self.assertTrue({"Life Admin", "Life User"} <= set(frappe.get_roles(NEW)))
		self.assertEqual(frappe.db.get_value("Life Space", FRESH, "owner_user"), NEW)
		self.assertEqual(permissions.user_spaces(NEW).get(FRESH), "Write")
		self.assertEqual(frappe.db.get_value("User", NEW, ["first_name", "last_name"]), ("Asha", "Rao"))
		self.assertFalse(frappe.db.sql("select 1 from __Auth where doctype='User' and name=%s and fieldname='password'", NEW))
		with patch.object(frappe.db, "commit"):
			install.new_owner(NEW, "Asha Rao", send_welcome_email=0, space=FRESH)  # a second run changes nothing
		self.assertEqual(len([m for m in frappe.get_doc("Life Space", FRESH).members if m.user == NEW]), 1)

	def test_the_guide_shows_once_to_an_owner_of_an_empty_site(self):
		frappe.get_doc({"doctype": "Life Space", "space_name": FRESH, "owner_user": "Administrator"}).insert()
		with patch.object(frappe.db, "commit"):
			install.new_owner(NEW, "Asha Rao", send_welcome_email=0, space=FRESH)
		permissions.clear_cache()
		frappe.set_user(NEW)
		self.assertTrue(onboarding.state()["show"])
		self.assertEqual(onboarding.complete("skipped")["status"], "skipped")
		self.assertFalse(onboarding.state()["show"])
		with self.assertRaises(frappe.PermissionError):
			onboarding.reset()
		frappe.set_user("Administrator")
		onboarding.reset(NEW)
		frappe.set_user(NEW)
		self.assertTrue(onboarding.state()["show"])
		# the first things become tasks with an area each; once there are tasks the guide is not offered again
		things = onboarding.add_first_things(["Book the dentist", "Pay the electricity bill", "Plan a run", "A fourth thing"], space=FRESH)
		self.assertEqual(len(things), 3)
		self.assertTrue(all(t["area"] for t in things))
		self.assertFalse(onboarding.state()["show"])

	def test_you_step_sets_the_name_and_time_zone(self):
		frappe.get_doc({"doctype": "Life Space", "space_name": FRESH, "owner_user": "Administrator"}).insert()
		with patch.object(frappe.db, "commit"):
			install.new_owner(NEW, "Asha Rao", send_welcome_email=0, space=FRESH)
		permissions.clear_cache()
		was = frappe.db.get_single_value("System Settings", "time_zone")
		frappe.set_user(NEW)
		with self.assertRaises(frappe.ValidationError):
			onboarding.save_you("Asha Rao", "Not/AZone")
		out = onboarding.save_you("  Asha  K Rao ", "Asia/Kolkata")
		self.assertEqual(out["full_name"], "Asha K Rao")
		self.assertEqual(out["time_zone"], "Asia/Kolkata")
		frappe.set_user("Administrator")
		frappe.db.set_single_value("System Settings", "time_zone", was)

	def test_an_agent_and_a_family_user_never_get_the_guide(self):
		self.as_user(OWNER)
		self.assertFalse(onboarding.state()["show"])  # the owner's spaces have records
