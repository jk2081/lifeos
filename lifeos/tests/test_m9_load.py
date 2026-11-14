"""Load test at the size in section 4b: 100,000 index rows, 20 users, 50 spaces. Each read must return in under 500 ms.

Set LIFEOS_LOAD_ROWS to a smaller number for a quick run.
"""
import os

import frappe
from frappe.tests import IntegrationTestCase

from lifeos import loadtest


class TestLoad(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.rows = int(os.environ.get("LIFEOS_LOAD_ROWS") or 100000)
		cls.seeded = loadtest.seed(rows=cls.rows)

	@classmethod
	def tearDownClass(cls):
		loadtest.remove()
		frappe.set_user("Administrator")
		super().tearDownClass()

	def test_size(self):
		self.assertGreaterEqual(self.seeded["rows"], self.rows * 0.99)
		self.assertEqual(self.seeded["users"], 20)
		self.assertEqual(self.seeded["spaces"], 50)

	def test_reads_meet_the_target(self):
		out = loadtest.measure()
		for key in ("today", "timeline", "area_page", "search_common_word", "search_rare_word", "search_all_spaces"):
			self.assertLess(out[key]["median_ms"], loadtest.TARGET_MS, f"{key}: {out[key]}")

	def test_a_user_outside_the_big_space_finds_nothing_in_it(self):
		from lifeos.api import search
		from lifeos.devtools import FAMILY

		frappe.set_user(FAMILY)
		self.assertEqual(search.query(loadtest.RARE_WORD)["results"], [])
		frappe.set_user("Administrator")
