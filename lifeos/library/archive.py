"""Archive rules of section 4a. Nothing is ever deleted here."""
import frappe
from frappe import _
from frappe.query_builder import functions as fn
from frappe.utils import add_days, cint, today

from lifeos.constants import ORG_DOCTYPES

AUTO_DOCTYPES = ("Life Task", "Life Inbox Item", "Life Chat Log")


def _sync_index(doctype, goal=None):
	"""Copy is_archived from the records of a DocType to their Life Index rows (all of them, or those filed under one goal)."""
	if doctype not in ORG_DOCTYPES:
		frappe.throw(_("Not an archivable DocType: {0}").format(doctype), title=_("DocType cannot be archived"))
	i, t = frappe.qb.DocType("Life Index"), frappe.qb.DocType(doctype)
	for flag in (1, 0):
		records = frappe.qb.from_(t).select(t.name).where(t.is_archived == flag)
		if goal:
			records = records.where(t.goal == goal)
		frappe.qb.update(i).set(i.is_archived, flag).where((i.ref_doctype == doctype) & (i.is_archived != flag) & i.ref_name.isin(records)).run()


def _archive(doctype, where, on):
	"""Archive the records of `doctype` that meet the criteria (made over its table) with the reason Auto; returns how many."""
	t = frappe.qb.DocType(doctype)
	n = frappe.qb.from_(t).select(fn.Count("*")).where(t.is_archived == 0).where(where).run()[0][0]
	frappe.qb.update(t).set(t.is_archived, 1).set(t.archived_on, on).set(t.archive_reason, "Auto").where(t.is_archived == 0).where(where).run()
	return n


def run_daily(on=None) -> dict:
	"""The daily job. Run by the scheduler, or: bench --site SITE execute lifeos.library.archive.run_daily"""
	on = on or today()
	days = cint(frappe.db.get_single_value("Life Settings", "archive_after_days")) or 90
	cutoff = add_days(on, -days)
	out = {}
	t, i, c, o = (frappe.qb.DocType(d) for d in ("Life Task", "Life Inbox Item", "Life Chat Log", "Life Chat Open Item"))
	out["Life Task"] = _archive("Life Task", t.status.isin(["Done", "Dropped"]) & t.completed_on.isnotnull() & (t.completed_on <= cutoff), on)
	out["Life Inbox Item"] = _archive("Life Inbox Item", (i.status == "Done") & i.finished_on.isnotnull() & (i.finished_on <= cutoff), on)
	open_chats = frappe.qb.from_(o).select(o.parent).where((o.parenttype == "Life Chat Log") & (o.status == "Open"))
	out["Life Chat Log"] = _archive("Life Chat Log", (c.date <= cutoff) & c.name.notin(open_chats), on)
	for dt in AUTO_DOCTYPES:
		_sync_index(dt)
	return out


def set_archived(doctype, name, archived=True, reason="Manual"):
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	if doctype == "Life Goal":
		if archived:
			return archive_goal(doc, with_records=doc.horizon == "Long term")
		return restore_goal(doc)
	if doctype not in ORG_DOCTYPES:
		frappe.throw(f"{doctype} cannot be archived.", title=_("DocType cannot be archived"))
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
		t = frappe.qb.DocType(dt)
		where = (t.goal == goal.name) & (t.is_archived == 0)
		count += frappe.qb.from_(t).select(fn.Count("*")).where(where).run()[0][0]
		frappe.qb.update(t).set(t.is_archived, 1).set(t.archived_on, today()).set(t.archive_reason, "Project").where(where).run()
		_sync_index(dt, goal.name)
	frappe.db.set_value("Life Goal", goal.name, {"is_archived": 1, "archived_on": today()}, update_modified=False)
	goal.is_archived = 1
	return {"doctype": "Life Goal", "name": goal.name, "is_archived": 1, "records": count}


def restore_goal(goal) -> dict:
	count = 0
	for dt in ORG_DOCTYPES:
		t = frappe.qb.DocType(dt)
		where = (t.goal == goal.name) & (t.is_archived == 1) & (t.archive_reason == "Project")
		count += frappe.qb.from_(t).select(fn.Count("*")).where(where).run()[0][0]
		frappe.qb.update(t).set(t.is_archived, 0).set(t.archived_on, None).set(t.archive_reason, "").where(where).run()
		_sync_index(dt, goal.name)
	if goal.horizon == "Long term" and (goal.outcome or "In Progress") != "In Progress":
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
