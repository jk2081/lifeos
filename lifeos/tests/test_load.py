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


class TestRawSql(IntegrationTestCase):
	"""Raw SQL is rare: at most 30 `frappe.db.sql` calls outside tests, each with a reason comment, and at most 10 silenced
	`frappe-sql-format-injection` findings (issue 81). Everything else goes through `frappe.qb`, `get_list` or `get_value`."""

	APP = __import__("pathlib").Path(__file__).resolve().parents[1]

	def sources(self):
		for path in self.APP.rglob("*.py"):
			if "tests" not in path.relative_to(self.APP).parts:
				yield path, path.read_text().splitlines()

	def test_there_are_at_most_30_raw_queries_each_with_a_reason(self):
		calls = []
		for path, lines in self.sources():
			for i, line in enumerate(lines):
				code = line.split("#")[0]
				if "frappe.db.sql(" in code:
					above = lines[i - 1].strip() if i else ""
					calls.append((f"{path.name}:{i + 1}", "#" in line or above.startswith("#")))
		self.assertLessEqual(len(calls), 30, calls)
		self.assertEqual([c for c, reasoned in calls if not reasoned], [], "a raw query needs a one-line reason comment")

	def test_at_most_10_sql_injection_findings_are_silenced(self):
		silenced = [f"{path.name}:{i + 1}" for path, lines in self.sources() for i, line in enumerate(lines) if "nosemgrep: frappe-sql-format-injection" in line]
		self.assertLessEqual(len(silenced), 10, silenced)


class TestFrontEndFiles(IntegrationTestCase):
	"""The front end's own rules (issue 82): screens reach the server through `frontend/src/data/`, and no file is dead."""

	SRC = __import__("pathlib").Path(__file__).resolve().parents[2] / "frontend" / "src"

	def test_no_component_or_page_calls_api_directly(self):
		import re

		bad = []
		for folder in ("components", "pages"):
			for path in sorted((self.SRC / folder).rglob("*")):
				if path.suffix in (".vue", ".js") and re.search(r"\bapi\(", path.read_text(encoding="utf-8")):
					bad.append(str(path.relative_to(self.SRC)))
		app = (self.SRC / "App.vue").read_text(encoding="utf-8")
		if re.search(r"\bapi\(", app):
			bad.append("App.vue")
		self.assertEqual(bad, [], "these call api( directly; use a module of data/")

	def test_every_vue_file_is_imported_or_routed(self):
		import re

		everything = "\n".join(p.read_text(encoding="utf-8") for p in self.SRC.rglob("*") if p.suffix in (".vue", ".js"))
		# pages are routed by name: page('Name') in router.js
		routed = set(re.findall(r"page\('([A-Za-z]+)'\)", (self.SRC / "router.js").read_text(encoding="utf-8")))
		dead = []
		for path in sorted(self.SRC.rglob("*.vue")):
			rel = path.relative_to(self.SRC)
			if rel.parts[0] == "pages" and len(rel.parts) == 2 and path.stem in routed:
				continue
			if not re.search(r"[/'\"]" + re.escape(path.name) + r"['\"]", everything):
				dead.append(str(rel))
		self.assertEqual(dead, [], "these .vue files are neither imported nor routed; delete them")
