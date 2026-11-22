"""Issue 46: a new site has one space, Private; a call that leaves the space out files there."""
from unittest.mock import patch

import frappe

from lifeos import install, permissions
from lifeos.api import inbox, session
from lifeos.tests.base import OWNER, PRIVATE, LifeTestCase


class TestOneSpace(LifeTestCase):
	def test_new_site_has_one_space_private(self):
		# I46.1: install makes Private only (the test site's second space comes from devtools.make_shared_space)
		self.assertEqual(install.STARTING_SPACES, ("Private",))
		frappe.set_user("Administrator")
		with patch.object(install, "STARTING_SPACES", ("Private",)):
			before = set(frappe.get_all("Life Space", pluck="name"))
			install.make_spaces()
			self.assertEqual(set(frappe.get_all("Life Space", pluck="name")), before)

	def test_create_item_without_a_space_files_into_private(self):
		# I46.2: on a one-space site
		self.as_user(OWNER)
		with patch.object(permissions, "user_spaces", return_value={PRIVATE: "Write"}):
			item = inbox.create_item(title="One space item", raw_text="x")
		self.assertEqual(item["space"], PRIVATE)

	def test_boot_lists_the_spaces(self):
		self.as_user(OWNER)
		self.assertIn(PRIVATE, [s["name"] for s in session.boot()["spaces"]])
