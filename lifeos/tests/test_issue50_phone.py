"""Issue 50: Life OS on the phone: the manifest, the service worker, captures from the phone (source Phone), sent once."""
import json
import re

import frappe

from lifeos.api import connections, inbox
from lifeos.pwa import SW_PATH
from lifeos.tests.base import PRIVATE, LifeTestCase


def _app_file(*parts):
	with open(frappe.get_app_path("lifeos", *parts), encoding="utf-8") as f:
		return f.read()


class TestPhone(LifeTestCase):
	def test_manifest_is_installable_and_takes_shares(self):
		m = json.loads(_app_file("public", "manifest.webmanifest"))
		self.assertEqual((m["name"], m["display"], m["start_url"]), ("Life OS", "standalone", "/life/today"))
		self.assertTrue(any(i["sizes"] == "512x512" for i in m["icons"]))
		target = m["share_target"]
		self.assertEqual((target["action"], target["method"], target["enctype"]), ("/life/share", "POST", "multipart/form-data"))
		self.assertEqual(target["params"]["files"][0]["name"], "files")

	def test_service_worker_caches_only_the_apps_static_files(self):
		self.assertEqual(SW_PATH, "life/sw.js")
		sw = _app_file("public", "life-sw.js")
		self.assertEqual(len(re.findall(r"cache\.put\(", sw)), 1)  # the one place a response is cached ...
		self.assertIn("url.pathname.startsWith(STATIC_PREFIX)", sw)  # ... is only reached for /assets/lifeos/ files
		self.assertIn("const STATIC_PREFIX = '/assets/lifeos/'", sw)
		self.assertNotIn("/api/", sw)

	def test_a_phone_capture_is_one_capture_however_often_it_is_sent(self):
		args = {"title": "I50 shared link", "source_type": "Phone", "space": PRIVATE, "raw_text": "https://example.com",
			"source_system": "phone", "external_id": "i50-a-uuid"}
		first = inbox.create_item(**args)
		again = inbox.create_item(**args)  # a retry after the answer was lost
		self.assertTrue(first["created"])
		self.assertEqual((again["created"], again["name"]), (False, first["name"]))
		self.assertEqual(frappe.db.count("Life Inbox Item", {"space": PRIVATE, "external_id": "i50-a-uuid"}), 1)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", first["name"], "source_type"), "Phone")

	def test_the_phone_is_not_a_connection_and_cannot_be_switched_off(self):
		inbox.create_item(title="I50 from the phone", source_type="Phone", space=PRIVATE, source_system="phone")
		self.assertFalse(frappe.db.exists("Life Connection", {"space": PRIVATE, "system": "phone"}))
		connections.require_on(PRIVATE, "phone")  # does not raise
