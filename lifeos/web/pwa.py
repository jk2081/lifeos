"""The phone app (issue 50): the service worker for /life.

A service worker can only control the folder it is served from, so it is served at /life/sw.js (a page renderer; Frappe's static
renderer refuses .js files). The file itself is lifeos/public/life-sw.js. It caches only the app's own static files and never an
API response or a record, and it takes what other apps share to Life OS (the share target's POST) and keeps it on the phone."""
import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer

SW_PATH = "life/sw.js"


class ServiceWorkerPage(BaseRenderer):
	def can_render(self):
		# the path resolver has already turned /life/sw.js into the app's page ("life") by the route rule, so ask the request
		return frappe.local.request.path.strip("/ ") == SW_PATH

	def render(self):
		# nosemgrep: frappe-security-file-traversal -- a fixed file of this app; no part of the path comes from the request
		with open(frappe.get_app_path("lifeos", "public", "life-sw.js"), encoding="utf-8") as f:
			source = f.read()
		response = self.build_response(source, 200, {"Content-Type": "application/javascript; charset=utf-8", "Cache-Control": "no-cache",
			"Service-Worker-Allowed": "/life/"})
		return response
