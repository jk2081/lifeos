"""Issue 48: remove the old Life Project table and the `project` columns.

Every project became an open-ended goal in set 6 (`Life Project.migrated_to`), and the records that had a project were
given its goal. Before anything is removed this checks both, and stops with the list, changing nothing, if either fails:
- every Life Project row has a `migrated_to` that names a goal which exists;
- every record whose old `project` column is set has a `goal` (a record the owner has filed under another goal since
  keeps that goal; the project's own goal is only the default it was given).
Then it deletes the DocType and its table and drops the columns itself (not `bench trim-tables`, so the check and the
removal are one step that either happens or does not). Back the site up first: dropping a column cannot be undone."""
import frappe

# every table that had a `project` column; Life Index mirrors the others and has no goal column to check
WITH_PROJECT = ("Life Task", "Life Note", "Life Inbox Item", "Life Chat Log", "Life Journal Page", "Life Vault Document", "Life Idea", "Life Goal", "Life Index")


def has_column(dt: str, column: str) -> bool:
	"""Read from the database itself: Frappe's own column cache goes stale after a DDL statement."""
	return has_table(dt) and bool(frappe.db.sql(f"show columns from `tab{dt}` like %s", column))  # nosemgrep: frappe-sql-format-injection -- `dt` is a constant DocType name


def has_table(dt: str) -> bool:
	return bool(frappe.db.sql("show tables like %s", f"tab{dt}"))


def problems() -> list[str]:
	"""What stops the removal, one line each; empty when it is safe."""
	out = []
	if has_table("Life Project"):
		for p in frappe.db.sql("select name, title, migrated_to from `tabLife Project`", as_dict=True):
			if not p.migrated_to:
				out.append(f"Life Project {p.name} ({p.title}) has no migrated_to")
			elif not frappe.db.exists("Life Goal", p.migrated_to):
				out.append(f"Life Project {p.name} ({p.title}) points to goal {p.migrated_to}, which does not exist")
	for dt in WITH_PROJECT:
		if not (has_table(dt) and has_column(dt, "project") and has_column(dt, "goal")):
			continue
		rows = frappe.db.sql(f"select name, project from `tab{dt}` where ifnull(project, '') != '' and ifnull(goal, '') = ''", as_dict=True)  # nosemgrep: frappe-sql-format-injection -- `dt` comes from the constant WITH_PROJECT
		out += [f"{dt} {r.name} has project {r.project} but no goal" for r in rows]
	return out


def execute():
	found = problems()
	if found:
		frappe.throw("The old projects cannot be removed yet. Nothing was changed. Fix these first:<br>" + "<br>".join(found[:200]))
	if frappe.db.exists("DocType", "Life Project"):
		frappe.delete_doc("DocType", "Life Project", force=True, ignore_missing=True, delete_permanently=True)
	frappe.db.sql_ddl("drop table if exists `tabLife Project`")
	for dt in WITH_PROJECT:
		if has_column(dt, "project"):
			frappe.db.sql_ddl(f"alter table `tab{dt}` drop column project")
