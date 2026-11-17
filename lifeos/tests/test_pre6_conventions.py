"""Pre-step 6: Frappe's conventions for whitelisted methods."""

import importlib.util
import inspect
import json
import pathlib

import frappe
from frappe.tests import IntegrationTestCase

APP = pathlib.Path(__file__).resolve().parents[2]


def lifeos_whitelisted():
	return [f for f in frappe.whitelisted if (getattr(f, "__module__", "") or "").startswith("lifeos.")]


class TestWhitelistConventions(IntegrationTestCase):
	def setUp(self):
		import lifeos.api  # noqa: F401
		for path in sorted((APP / "lifeos/api").glob("*.py")):
			importlib.import_module(f"lifeos.api.{path.stem}")
		importlib.import_module("lifeos.queries")

	def test_every_method_declares_http_methods_and_hints(self):
		methods = lifeos_whitelisted()
		self.assertGreater(len(methods), 150)
		for fn in methods:
			name = f"{fn.__module__}.{fn.__name__}"
			allowed = frappe.allowed_http_methods_for_whitelisted_func[fn]
			self.assertIn(allowed, (["GET"], ["POST"]), f"{name} declares {allowed}")
			for param in inspect.signature(fn).parameters.values():
				if param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
					continue
				self.assertIn(param.name, fn.__annotations__, f"{name}: {param.name} has no type hint")

	def test_front_end_list_of_get_methods_is_current(self):
		spec = importlib.util.spec_from_file_location("http_methods", APP / "scripts/http-methods.py")
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		on_disk = json.loads((APP / "frontend/src/lib/getMethods.json").read_text())
		self.assertEqual(on_disk, module.get_methods(APP), "run scripts/http-methods.py")
		get_only = sorted(f"{f.__module__}.{f.__name__}" for f in lifeos_whitelisted()
			if frappe.allowed_http_methods_for_whitelisted_func[f] == ["GET"])
		self.assertEqual(sorted(on_disk), get_only)
