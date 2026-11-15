"""UX fixes, set 3: the new switch "agents can read the Vault" starts off for every existing space.
Archived areas, tags, habits and dimensions keep a blank archived_on: the date was not stored before."""
import frappe


def execute():
	frappe.db.sql("update `tabLife Space` set agents_can_read_vault = 0")
