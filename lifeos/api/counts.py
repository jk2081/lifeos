"""The counts of a screen, each with the list it opens (UX fixes, set 5). The rules are in lifeos/counts.py."""
import frappe

from lifeos import counts


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None, which: str = "open_band"):
	return counts.get(space=space, which=which)
