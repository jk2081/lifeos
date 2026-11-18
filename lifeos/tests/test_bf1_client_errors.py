"""Bug fix 1: a screen that fails in the browser is written to the Error Log under its reference, for logged-in users
only, with the path's query dropped and every field clipped, and the endpoint is POST-only and rate-limited."""
import frappe

from lifeos.api import client_errors
from lifeos.tests.base import OWNER, LifeTestCase


class ClientErrorCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user(OWNER)
		frappe.db.delete("Error Log", {"method": ["like", f"{client_errors.TITLE} %"]})

	def logged(self, reference):
		return frappe.get_all("Error Log", filters={"method": f"{client_errors.TITLE} {reference}"}, pluck="error")

	def test_logs_one_entry_with_the_reference_and_no_query(self):
		out = client_errors.log(reference="ABC123", message="Cannot read properties of null", stack="TypeError\n at x",
			path="/life/plan/week?view=review&q=secret#frag", component="WeeklyReview", info="14", kind="render")
		self.assertEqual(out, {"reference": "ABC123"})
		[body] = self.logged("ABC123")
		self.assertIn("path: /life/plan/week\n", body)
		self.assertNotIn("secret", body)
		self.assertIn("user: " + OWNER, body)
		self.assertIn("Cannot read properties of null", body)

	def test_fields_are_clipped(self):
		client_errors.log(reference="CLIP01", message="m" * 5000, stack="s" * 50000, path="/" + "p" * 1000)
		[body] = self.logged("CLIP01")
		self.assertLess(len(body), 5200)

	def test_a_reference_is_required(self):
		self.assertRaises(frappe.ValidationError, client_errors.log, reference=" ", message="x")

	def test_guests_are_refused(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, client_errors.log, reference="GUEST1", message="x")
		frappe.set_user(OWNER)
		self.assertFalse(self.logged("GUEST1"))

	def test_post_only_and_rate_limited(self):
		fn = client_errors.log
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(fn), ["POST"])
		self.assertNotIn(fn, frappe.guest_methods)
		self.assertTrue(hasattr(fn, "__wrapped__"), "the rate limit wraps the method")
