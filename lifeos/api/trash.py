"""The trash, for the Archive's Trash tab and the Delete buttons (UX fixes, set 5). The rules are in lifeos/library/trash.py."""
import frappe

from lifeos.library import trash


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, start: int = 0, page_length: int = 50, kind: str | None = None):
	return trash.list(space=space, start=start, page_length=page_length, kind=kind)


@frappe.whitelist(methods=["POST"])
def restore(name: str):
	return trash.restore(name)


@frappe.whitelist(methods=["POST"])
def delete(doctype: str, name: str):
	"""Move a record to the trash (30 days to restore). People only."""
	return trash.delete(doctype, name)
