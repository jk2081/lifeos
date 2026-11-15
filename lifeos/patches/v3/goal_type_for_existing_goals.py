"""UX fixes, set 3: every goal that existed before goal types is a 12 Week Year goal. Nothing else changes."""
import frappe


def execute():
	frappe.db.sql("update `tabLife Goal` set goal_type = '12 Week Year' where ifnull(goal_type, '') = ''")
