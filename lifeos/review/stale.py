"""The weekly review's stale tasks: one list, each task with Keep, Someday and Drop.

A stale task is an open task nobody has touched for the stuck threshold (Settings > Rhythms), made before this review's
period began. Keep touches it, so it is not stale again next week; Someday parks it; Drop drops it. What was decided is kept
in the review's state, for the week's numbers.
"""
import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos import counts, permissions
from lifeos.api import someday
from lifeos.api.utils import names_map

DECISIONS = ("keep", "someday", "drop")
OPEN = ("Open", "Doing", "Waiting")
MAX_ITEMS = 100


def candidates(space, period_start):
	"""The stale tasks of a space, oldest first, each with its area and how many days it has stood."""
	cutoff = add_days(today(), -counts.rules()["stuck_after_days"])
	rows = frappe.db.sql("""select name, title, area, goal, status, waiting_on, ifnull(last_touched_on, date(creation)) as touched
		from `tabLife Task` where space = %(space)s and is_archived = 0 and status in ('Open', 'Doing', 'Waiting')
		and date(creation) < %(start)s and ifnull(last_touched_on, date(creation)) <= %(cutoff)s
		order by touched asc limit %(limit)s""", {"space": space, "start": getdate(period_start), "cutoff": cutoff, "limit": MAX_ITEMS},
		as_dict=True)
	areas = names_map("Life Area", list({r.area for r in rows if r.area}), "area_name")
	return [{"name": r.name, "title": r.title, "area": r.area, "area_name": areas.get(r.area), "goal": r.goal, "status": r.status,
		"waiting_on": r.waiting_on, "age": (getdate(today()) - getdate(r.touched)).days} for r in rows]


def settle(review, task, decision):
	"""Carry out one decision on one stale task and remember it in the review."""
	if decision not in DECISIONS:
		frappe.throw(_("Choose Keep, Someday or Drop."), title=_("Decision is not valid"))
	doc = permissions.get_doc_checked("Life Task", task, "write")
	if doc.status not in OPEN:
		frappe.throw(_("{0} is no longer open.").format(doc.title), title=_("Task is no longer open"))
	if decision == "someday":
		someday.park_doc(doc)
	elif decision == "drop":
		doc.status = "Dropped"
		doc.save()
	else:
		doc.save()  # a save touches the task, so it is not stale again next week
	review.state.setdefault("stale", {})[doc.name] = decision
	return doc


def tab(review):
	"""What the Tasks tab lists: the stale tasks still to decide, and how many were decided in this review."""
	rows = candidates(review.doc.space, review.doc.period_start)
	return {"tasks": rows, "left": len(rows), "decided": decided_count(review)}


def cleared(review):
	return not candidates(review.doc.space, review.doc.period_start)


def decided_count(review):
	return len(review.state.get("stale") or {})
