"""Archive rules of section 4a. Nothing is ever deleted here."""
import frappe
from frappe import _
from frappe.utils import add_days, cint, today

from lifeos.constants import ORG_DOCTYPES

AUTO_DOCTYPES = ("Life Task", "Life Inbox Item", "Life Chat Log")


def _sync_index(doctype, where="1=1", values=()):
	if doctype not in ORG_DOCTYPES:
		frappe.throw(_("Not an archivable DocType: {0}").format(doctype))
	# nosemgrep: frappe-sql-format-injection -- the table is one of ORG_DOCTYPES (checked above) and `where` a fixed fragment; values are parameters
	frappe.db.sql(
		f"""update `tabLife Index` i join `tab{doctype}` t on t.name = i.ref_name
		set i.is_archived = t.is_archived where i.ref_doctype = %s and i.is_archived != t.is_archived and {where}""",
		(doctype, *values),
	)


def run_daily(on=None) -> dict:
	"""The daily job. Run by the scheduler, or: bench --site SITE execute lifeos.archive.run_daily"""
	on = on or today()
	days = cint(frappe.db.get_single_value("Life Settings", "archive_after_days")) or 90
	cutoff = add_days(on, -days)
	out = {}
	frappe.db.sql(
		"""update `tabLife Task` set is_archived=1, archived_on=%s, archive_reason='Auto'
		where is_archived=0 and status in ('Done', 'Dropped') and completed_on is not null and completed_on <= %s""", (on, cutoff))
	out["Life Task"] = frappe.db.sql("select row_count()")[0][0]
	frappe.db.sql(
		"""update `tabLife Inbox Item` set is_archived=1, archived_on=%s, archive_reason='Auto'
		where is_archived=0 and status='Done' and finished_on is not null and finished_on <= %s""", (on, cutoff))
	out["Life Inbox Item"] = frappe.db.sql("select row_count()")[0][0]
	frappe.db.sql(
		"""update `tabLife Chat Log` c set c.is_archived=1, c.archived_on=%s, c.archive_reason='Auto'
		where c.is_archived=0 and c.date <= %s and not exists (
			select 1 from `tabLife Chat Open Item` o where o.parent=c.name and o.parenttype='Life Chat Log' and o.status='Open')""",
		(on, cutoff))
	out["Life Chat Log"] = frappe.db.sql("select row_count()")[0][0]
	for dt in AUTO_DOCTYPES:
		_sync_index(dt)
	return out


def set_archived(doctype, name, archived=True, reason="Manual"):
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	if doctype == "Life Goal":
		if archived:
			return archive_goal(doc, with_records=doc.goal_type == "Open")
		return restore_goal(doc)
	if doctype not in ORG_DOCTYPES:
		frappe.throw(f"{doctype} cannot be archived.")
	doc.is_archived = 1 if archived else 0
	doc.archived_on = today() if archived else None
	doc.archive_reason = reason if archived else ""
	doc.flags.keep_touched = True
	doc.save(ignore_permissions=True)
	return {"doctype": doctype, "name": name, "is_archived": doc.is_archived}


def goal_record_count(goal) -> int:
	total = 0
	for dt in ORG_DOCTYPES:
		total += frappe.db.count(dt, {"goal": goal, "is_archived": 0})
	return total


def archive_goal(goal, with_records=True) -> dict:
	"""Archive a goal and every record filed under it (`goal` points to it), as a project was archived before set 6.
	The records keep the reason code "Project" ("with its goal"), so older archives restore the same way."""
	count = 0
	for dt in ORG_DOCTYPES if with_records else ():  # a 12 Week Year or annual goal archived by hand goes alone
		frappe.db.sql(  # nosemgrep: frappe-sql-format-injection -- `dt` comes from the constant ORG_DOCTYPES
			f"update `tab{dt}` set is_archived=1, archived_on=%s, archive_reason='Project' where goal=%s and is_archived=0",
			(today(), goal.name))
		count += frappe.db.sql("select row_count()")[0][0]
		_sync_index(dt, "t.goal = %s", (goal.name,))
	frappe.db.set_value("Life Goal", goal.name, {"is_archived": 1, "archived_on": today()}, update_modified=False)
	goal.is_archived = 1
	return {"doctype": "Life Goal", "name": goal.name, "is_archived": 1, "records": count}


def restore_goal(goal) -> dict:
	count = 0
	for dt in ORG_DOCTYPES:
		frappe.db.sql(  # nosemgrep: frappe-sql-format-injection -- `dt` comes from the constant ORG_DOCTYPES
			f"update `tab{dt}` set is_archived=0, archived_on=null, archive_reason='' where goal=%s and is_archived=1 and archive_reason='Project'",
			goal.name)
		count += frappe.db.sql("select row_count()")[0][0]
		_sync_index(dt, "t.goal = %s", (goal.name,))
	if goal.goal_type == "Open" and (goal.outcome or "In Progress") != "In Progress":
		# reopened by a save, so the Outbox reverses the goal's exit (set 7); validate clears closed_on and completed_on
		doc = frappe.get_doc("Life Goal", goal.name)
		doc.is_archived, doc.archived_on, doc.outcome = 0, None, "In Progress"
		doc.flags.keep_touched = True
		doc.save(ignore_permissions=True)
	else:
		frappe.db.set_value("Life Goal", goal.name, {"is_archived": 0, "archived_on": None}, update_modified=False)
	return {"doctype": "Life Goal", "name": goal.name, "is_archived": 0, "records": count}


def archived_in_week(space, from_date, to_date) -> list:
	"""What the job archived in a date range, for the weekly review."""
	out = []
	for dt in AUTO_DOCTYPES:
		for r in frappe.get_all(dt, filters={"space": space, "is_archived": 1, "archive_reason": "Auto",
				"archived_on": ("between", [from_date, to_date])}, fields=["name", "title", "archived_on"], limit=100):
			out.append({"doctype": dt, **r})
	return out
