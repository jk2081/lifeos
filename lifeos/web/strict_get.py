"""A development check: run every GET to a Life OS method in a read-only transaction.

Frappe rolls back a GET request, so a read that writes loses its write without a word. With `lifeos_strict_get`
set in a site's config (the acceptance site sets it), such a write fails loudly instead. Off everywhere else.
"""

import frappe


def before_request() -> None:
	request = getattr(frappe.local, "request", None)
	if not frappe.conf.get("lifeos_strict_get") or not request or request.method != "GET":
		return
	if not request.path.startswith("/api/method/lifeos."):
		return
	# a GET is rolled back at its end anyway, so nothing that ran before this is lost by rolling back now
	frappe.db.rollback()
	frappe.db.begin(read_only=True)
