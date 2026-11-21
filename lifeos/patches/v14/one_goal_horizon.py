"""Issue 60: one kind of goal (a horizon, not a type, and no separate month goals), one parking lot (Someday, no ideas) and
no tags. The live site is reinstalled fresh, so this only keeps a development bench in step: the goal type becomes a
horizon and the DocTypes that no longer exist are deleted."""
import frappe

HORIZON_OF = {"12 Week Year": "12 weeks", "Annual": "Year", "Open": "Long term"}
GONE = ("Life Month Plan Goal", "Life Idea", "Life Tag Link", "Life Tag")


def execute():
	if frappe.db.has_column("Life Goal", "goal_type"):
		for old, new in HORIZON_OF.items():
			frappe.db.sql("update `tabLife Goal` set horizon=%s where goal_type=%s and ifnull(horizon, '') = ''", (new, old))
		frappe.db.sql_ddl("alter table `tabLife Goal` drop column goal_type")
	for dt in GONE:
		if frappe.db.exists("DocType", dt):
			frappe.delete_doc("DocType", dt, force=True, ignore_missing=True, delete_permanently=True)
		frappe.db.sql_ddl(f"drop table if exists `tab{dt}`")
	for dt in ("Life Task", "Life Note", "Life Inbox Item", "Life Vault Document", "Life Chat Log", "Life Journal Page"):
		if frappe.db.has_column(dt, "tags"):
			frappe.db.sql_ddl(f"alter table `tab{dt}` drop column tags")
