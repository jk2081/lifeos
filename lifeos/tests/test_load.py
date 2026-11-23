"""Tests for load."""
import os
import unittest

import frappe
from frappe.tests import IntegrationTestCase

from lifeos.tools import loadtest


class TestLoad(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.rows = int(os.environ.get("LIFEOS_LOAD_ROWS") or 100000)
		cls.seeded = loadtest.seed(rows=cls.rows)
		cls.sources = int(os.environ.get("LIFEOS_LOAD_SOURCES") or 2000)
		cls.seeded_sources = loadtest.seed_sources(sources=cls.sources, pages=max(cls.sources // 10, 50))

	@classmethod
	def tearDownClass(cls):
		loadtest.remove()
		frappe.set_user("Administrator")
		super().tearDownClass()

	def test_size(self):
		self.assertGreaterEqual(self.seeded["rows"], self.rows * 0.99)
		self.assertEqual(self.seeded["users"], 20)
		self.assertEqual(self.seeded["spaces"], 50)

	# Timings mean something only on a known machine: GitHub's shared runners measured the same reads at 1.3 to 2.4 s
	# from run to run. CI sets LIFEOS_SKIP_TIMINGS; the target is checked on the Docker bench.
	@unittest.skipIf(os.environ.get("LIFEOS_SKIP_TIMINGS"), "timings are checked on the Docker bench, not on CI runners")
	def test_reads_meet_the_target(self):
		out = loadtest.measure()
		for key in ("today", "timeline", "today_lens", "search_common_word", "search_rare_word", "search_all_spaces"):
			self.assertLess(out[key]["median_ms"], loadtest.TARGET_MS, f"{key}: {out[key]}")

	def test_sources_and_wiki_reads_meet_the_target(self):
		self.assertGreaterEqual(self.seeded_sources["sources"], self.sources)
		if os.environ.get("LIFEOS_SKIP_TIMINGS"):
			return
		out = loadtest.measure_sources()
		for key in ("sources_first_page", "sources_tab_photos", "search_full_text", "wiki_pages_list", "wiki_changes_list"):
			self.assertLess(out[key]["median_ms"], loadtest.TARGET_MS, f"{key}: {out[key]}")

	def test_a_user_outside_the_big_space_finds_nothing_in_it(self):
		from lifeos.api import search
		from lifeos.tools.devtools import FAMILY

		frappe.set_user(FAMILY)
		self.assertEqual(search.query(loadtest.RARE_WORD)["results"], [])
		frappe.set_user("Administrator")


class TestCodeShape(IntegrationTestCase):
	"""The shape of the code: modules grouped by place."""

	TOP = {"__init__", "constants", "hooks", "install", "permissions"}

	def test_no_loose_module_at_the_top(self):
		from pathlib import Path

		top = {p.stem for p in Path(frappe.get_app_path("lifeos")).glob("*.py")}
		self.assertEqual(top - self.TOP, set())
