import frappe

from lifeos.tests.base import LifeTestCase


class TestSkeleton(LifeTestCase):
	def test_app_is_installed(self):
		self.assertIn("lifeos", frappe.get_installed_apps())
		self.assertTrue(frappe.db.exists("Role", "Life Admin"))
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Event", "fieldname": "life_space"}))

	def test_life_route_rule(self):
		rules = frappe.get_hooks("website_route_rules")
		self.assertIn({"from_route": "/life/<path:app_path>", "to_route": "life"}, rules)

	def test_guest_is_redirected_to_login(self):
		from lifeos.www import life

		frappe.set_user("Guest")
		frappe.local.request = frappe._dict(path="/life")
		with self.assertRaises(frappe.Redirect):
			life.get_context(frappe._dict())
		self.assertIn("/login", frappe.local.flags.redirect_location)

	def test_guest_gets_nothing_from_the_api(self):
		from lifeos.api import session

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, session.boot)

	def test_boot_lists_spaces(self):
		from lifeos.api import session
		from lifeos.tests.base import PRIVATE, SHARED

		names = [s["name"] for s in session.boot()["spaces"]]
		self.assertIn(PRIVATE, names)
		self.assertIn(SHARED, names)
