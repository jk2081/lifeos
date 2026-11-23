"""Habit rules: the habits a space tracks, ticks on days, and each habit's score for a month or a year.

A habit is tracked from `tracked_from` until `tracked_until` (open ended while that is empty), on `days_per_week` days of
the week. API methods in lifeos.api.goals call these.
"""
import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos.cycles import month_bounds


def habit_stats(row, first, last, done_dates, upto=None) -> dict:
	"""Score one habit for one month. Only days inside its tracked period, and not in the future, can be missed."""
	upto = getdate(upto or today())
	start = max(first, getdate(row.tracked_from)) if row.tracked_from else first
	end = min(last, getdate(row.tracked_until)) if row.tracked_until else last
	counted_end = min(end, upto)
	tracked_days = (counted_end - start).days + 1 if counted_end >= start else 0
	done = sum(1 for d in done_dates if start <= d <= end)
	per_week = min(7, max(1, int(row.days_per_week or 7)))
	target = tracked_days if per_week >= 7 else int(round(tracked_days * per_week / 7.0))
	if tracked_days and not target:
		target = 1
	percent = min(100, round(100.0 * done / target)) if target else 0
	return {"tracked_from": str(start), "tracked_until": str(end), "tracked_days": tracked_days, "done": done,
		"target": target, "percent": percent, "days_per_week": per_week}


def tracked_habits(space, first, last):
	"""The habits tracked at any time between two days, in the owner's order."""
	rows = frappe.get_all("Life Habit", filters=[["space", "=", space], ["tracked_from", "is", "set"], ["tracked_from", "<=", last]],
		fields=["name", "title", "days_per_week", "sort_order", "tracked_from", "tracked_until"], order_by="sort_order asc, creation asc", limit=200)
	return [r for r in rows if not r.tracked_until or getdate(r.tracked_until) >= first]


def habits_month(space, year, month) -> dict:
	first, last = month_bounds(year, month)
	rows = tracked_habits(space, first, last)
	out = {"year": int(year), "month": int(month), "days_in_month": last.day, "today": today(), "habits": []}
	ids = [r.name for r in rows]
	logs = {}
	if ids:
		for h, d in frappe.db.sql(
			"select habit, date from `tabLife Habit Log` where habit in %s and date between %s and %s and done=1", (ids, first, last)
		):
			logs.setdefault(h, set()).add(getdate(d))
	for r in rows:
		done_dates = logs.get(r.name, set())
		out["habits"].append({"habit": r.name, "title": r.title, "sort_order": r.sort_order,
			"removed": bool(r.tracked_until and getdate(r.tracked_until) < last),
			"done_days": sorted(d.day for d in done_dates), **habit_stats(r, first, last, done_dates)})
	return out


def toggle_habit(habit, on, done=None) -> dict:
	h = frappe.get_doc("Life Habit", habit)
	h.check_permission("write")
	on = getdate(on or today())
	existing = frappe.db.get_value("Life Habit Log", {"habit": habit, "date": on}, ["name", "done"], as_dict=True)
	if done is None:
		done = not (existing and existing.done)
	done = bool(int(done)) if not isinstance(done, bool) else done
	if done and on > getdate(today()):
		frappe.throw(_("A habit cannot be ticked for a day that has not come yet."))
	if existing and not done:
		frappe.delete_doc("Life Habit Log", existing.name, ignore_permissions=True, force=True)
	elif not existing and done:
		frappe.get_doc({"doctype": "Life Habit Log", "space": h.space, "habit": habit, "date": on, "done": 1}).insert(ignore_permissions=True)
	return {"habit": habit, "date": str(on), "done": done}


def set_month_habits(space, year, month, habits) -> dict:
	"""Set the habits tracked from this month on. `habits` is a list of {habit, days_per_week}, in order.

	A habit dropped keeps the days it was tracked: it is tracked until the day before the change (yesterday, inside the
	month; the end of the month before, for a later one). One dropped before it ever counted is no longer tracked at all.
	"""
	first, last = month_bounds(year, month)
	now = getdate(today())
	in_month = first <= now <= last
	cutoff = add_days(now, -1) if in_month else add_days(first, -1)
	wanted = {h["habit"] for h in habits}
	for i, h in enumerate(habits):
		doc = frappe.get_doc("Life Habit", h["habit"])
		doc.check_permission("write")
		if doc.space != space:
			frappe.throw(_("That habit is in another space."))
		doc.days_per_week = min(7, max(1, int(h.get("days_per_week") or doc.days_per_week or 7)))
		doc.sort_order = i + 1
		if doc.tracked_until or not doc.tracked_from:  # new, or added back
			doc.tracked_from = now if in_month else first
			doc.tracked_until = None
		doc.save(ignore_permissions=True)
	for r in tracked_habits(space, first, last):
		if r.name in wanted or r.tracked_until:
			continue
		doc = frappe.get_doc("Life Habit", r.name)
		doc.check_permission("write")
		if getdate(doc.tracked_from) > cutoff:
			doc.tracked_from = None
		else:
			doc.tracked_until = cutoff
			doc.sort_order = 100 + (doc.sort_order or 0)
		doc.save(ignore_permissions=True)
	return habits_month(space, year, month)


def habits_year(space, year) -> dict:
	"""Each habit's percentage for every month of the year in which it was tracked."""
	year = int(year)
	out = {}
	for month in range(1, 13):
		data = habits_month(space, year, month)
		for h in data["habits"]:
			if h["tracked_days"]:
				out.setdefault(h["habit"], {"habit": h["habit"], "title": h["title"], "months": {}})["months"][str(month)] = {
					"percent": h["percent"], "done": h["done"], "target": h["target"]}
	return {"year": year, "habits": list(out.values())}
