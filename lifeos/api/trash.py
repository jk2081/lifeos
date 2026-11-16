"""The trash, for the Archive's Trash tab and the Delete buttons (UX fixes, set 5). The rules are in lifeos/trash.py."""
import frappe

from lifeos import trash


@frappe.whitelist()
def list(space=None, start=0, page_length=50, kind=None):
	return trash.list(space=space, start=start, page_length=page_length, kind=kind)


@frappe.whitelist(methods=["POST"])
def restore(name):
	return trash.restore(name)


@frappe.whitelist(methods=["POST"])
def delete(doctype, name):
	"""Move a record to the trash (30 days to restore). People only."""
	return trash.delete(doctype, name)
