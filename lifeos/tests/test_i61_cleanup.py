"""Issue 61: the old screens, routes, upgrade patches and personal seed data are gone, and nothing is left unreachable."""
import ast
import re
from pathlib import Path

import frappe
from frappe.modules.patch_handler import get_patches_from_app
from frappe.tests import IntegrationTestCase

from lifeos import install

APP = Path(frappe.get_app_path("lifeos"))
SRC = APP.parent / "frontend" / "src"
# the owner's known goal titles and names: none may be in seed.py
PERSONAL = ["RMT", "GHL", "Tea & Coffee", "Business That Works", "Unstoppable", "Ruchi", "Anya", "Japa", "Mala", "Golf", "Arjun",
	"Nowrojee", "Sarjapur", "MoneyOS", "Get super-fit", "Close open loops", "Mind and learning", "Oct to Dec 2026", "Driver's licence",
	"Merrill", "Dalmia", "Mithun"]

# whitelisted methods that no screen, skill, agent or test calls by name, with the reason each stays (none now)
KEPT = {}


def imports_of(path, text):
	for m in re.finditer(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""", text):
		spec = m.group(1)
		base = SRC / spec[2:] if spec.startswith("@/") else (path.parent / spec if spec.startswith(".") else None)
		if base is None:
			continue
		for cand in (base, Path(f"{base}.js"), Path(f"{base}.vue"), base / "index.js"):
			if cand.is_file():
				yield cand.resolve()
				break
	for m in re.finditer(r"page\('([^']+)'\)", text):
		yield (SRC / "pages" / f"{m.group(1)}.vue").resolve()


class TestCleanup(IntegrationTestCase):
	def test_every_front_end_file_is_imported_or_routed(self):
		# I61.2
		seen, todo = set(), [(SRC / "main.js").resolve()]
		while todo:
			path = todo.pop()
			if path in seen:
				continue
			seen.add(path)
			todo.extend(imports_of(path, path.read_text()))
		files = {p.resolve() for p in SRC.rglob("*") if p.suffix in (".vue", ".js")}
		self.assertEqual(sorted(str(p.relative_to(SRC.resolve())) for p in files - seen), [])

	def test_patches_txt_is_empty_and_a_site_installs_and_migrates_without_patches(self):
		# I61.3
		lines = [x.strip() for x in (APP / "patches.txt").read_text().splitlines()]
		self.assertEqual([x for x in lines if x and not x.startswith(("#", "["))], [])
		self.assertFalse((APP / "patches").exists())
		self.assertEqual(get_patches_from_app("lifeos"), [])
		install.after_migrate()
		install.after_migrate()  # again: the schema comes from the DocTypes and setup is repeatable

	def test_seed_has_no_personal_names_goals_or_amounts(self):
		# I61.4
		text = (APP / "seed.py").read_text()
		for word in PERSONAL:
			self.assertNotIn(word.lower(), text.lower(), word)
		self.assertNotRegex(text, r"\d[\d,]{3,}\s*(?:rs|inr|usd|\$)|(?:rs|inr|usd|\$)\s*\d{3,}")

	def test_every_whitelisted_method_has_a_caller(self):
		# I61.5: a report of the methods nothing calls; any that stays is in KEPT with its reason (and in DECISIONS.md)
		corpus = "\n".join(p.read_text(errors="ignore") for p in [*SRC.rglob("*.vue"), *SRC.rglob("*.js")])
		corpus += "\n".join(p.read_text(errors="ignore") for p in (APP / "skills").rglob("*.md"))
		corpus += (APP.parent / "agent" / "fake_agent.py").read_text() + (APP.parent / "tools" / "acceptance.mjs").read_text()
		tests = "\n".join(p.read_text() for p in (APP / "tests").glob("test_*.py") if p.name != Path(__file__).name)
		python = {p: p.read_text() for p in APP.rglob("*.py") if "tests" not in p.parts}
		orphans = []
		for path, text in python.items():
			module = ".".join(path.relative_to(APP.parent).with_suffix("").parts)
			for node in ast.walk(ast.parse(text)):
				if not isinstance(node, ast.FunctionDef) or not any("whitelist" in ast.unparse(d) for d in node.decorator_list):
					continue
				short = module.split(".")[-1]
				name = node.name
				called = (
					re.search(rf"\b{short}\.{name}\b", corpus + tests + "\n".join(python.values()))
					or re.search(rf"['\"`][\w.]*{name}['\"`]", corpus)  # a name passed to the review's r.act and r.read
					or len(re.findall(rf"(?<!def )\b{name}\(", text)) > 0  # called inside its own module
					or re.search(rf"import[^\n]*\b{name}\b", "\n".join(python.values()) + tests)
				)
				if not called and f"{module}.{name}" not in KEPT:
					orphans.append(f"{module}.{name}")
		self.assertEqual(sorted(orphans), [])
