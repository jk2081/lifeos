"""The Outbox (set 7): what left the plate, by pile, for a period; what came in; an 8-week chart of in against out; and Bring
back. A record, not a place to work: the only action is Bring back. People only; agents never read exits."""
import builtins

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder import functions as fn
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

from lifeos.brain import outbox
from lifeos import permissions
from pypika.terms import Criterion, ValueWrapper

from lifeos.api.utils import area_criterion, filter_criteria, lens_area, names_map, page

TABS = ("Done", "Delegated", "Parked", "Discarded", "all", "in")
LABEL = {"Life Task": "Task", "Life Goal": "Goal", "Life Inbox Item": "Capture"}


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("The Outbox is for people."), frappe.PermissionError, title=_("Outbox is for people"))


def _out_where(space, area, start, end, pile=None, filters=None):
	"""The criteria of the exits of a period: a list over `frappe.qb.DocType("Life Exit")`."""
	e = frappe.qb.DocType("Life Exit")
	where = [e.space == space, e.reversed == 0, e.exited_on >= start, e.exited_on < end, *filter_criteria("Life Exit", filters, e)]
	if pile and pile != "all":
		where.append(e.pile == pile)
	if area:
		where.append(area_criterion(space, area, e))
	return where


def _in_query(space, area, start, end):
	"""What came in: captures received, and tasks and goals created directly (not from a capture, not carried from an earlier task or
	goal), as one query of (doctype, name, title, area, came_on, is_sensitive)."""
	parts = []
	for dt in ("Life Inbox Item", "Life Task", "Life Goal"):
		x = frappe.qb.DocType(dt)
		where = (x.space == space) & (x.creation >= start) & (x.creation < end)
		if area:
			where = where & area_criterion(space, area, x)
		sensitive = x.is_sensitive if dt == "Life Inbox Item" else ValueWrapper(0)
		if dt == "Life Task":
			where = where & (fn.IfNull(x.inbox_item, "") == "") & (fn.IfNull(x.carried_from, "") == "")
		elif dt == "Life Goal":
			where = where & (fn.IfNull(x.carried_from, "") == "")
		parts.append(frappe.qb.from_(x).select(ValueWrapper(dt).as_("doctype"), x.name, x.title, x.area, x.creation.as_("came_on"), sensitive.as_("is_sensitive")).where(where))  # system: the Outbox counts the owner's own space
	return parts[0].union_all(parts[1]).union_all(parts[2])


def in_count(space, area, start, end):
	return frappe.qb.from_(_in_query(space, area, start, end).as_("t")).select(fn.Count("*")).run()[0][0]  # system: wrapped query over the owner's own space


def out_counts(space, area, start, end, filters=None):
	e = frappe.qb.DocType("Life Exit")
	rows = frappe.qb.from_(e).select(e.pile, fn.Count("*")).where(Criterion.all(_out_where(space, area, start, end, filters=filters))).groupby(e.pile).run()  # system: the Outbox is the owner's own
	rows = dict(rows)
	out = {p: int(rows.get(p, 0)) for p in outbox.PILES}
	out["all"] = sum(out.values())
	return out


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, pile: str | None = "Done", period: str | None = "week", area: str | None = None, start: int = 0,
		page_length: int = 50, filters: str | builtins.list | None = None, order_by: str | None = None, summary: str | dict | None = None,
		from_date: str | None = None, to_date: str | None = None):
	"""The Outbox for a period (week, the default; month; 12weeks): exits of one pile (Done, Delegated, Parked, Discarded,
	or all), newest first, or with pile `in` what came in (`filters` on Life Exit fields apply to the exits only). Each row has its kind, area, when, its pile, whether it is
	sensitive, and whether Bring back is possible. `tabs` counts every tab for the period under the lens."""
	_person()
	space = permissions.resolve_space(space)
	area = lens_area(area)
	pile = pile if pile in TABS else "Done"
	start_dt, end_dt, period = bounds(period, from_date, to_date)
	start, page_length = page(start, page_length)
	tabs = out_counts(space, area, start_dt, end_dt, filters)
	tabs["in"] = in_count(space, area, start_dt, end_dt)
	if pile == "in":
		rows, total = _in_rows(space, area, start_dt, end_dt, start, page_length), tabs["in"]
	else:
		e = frappe.qb.DocType("Life Exit")
		rows = (frappe.qb.from_(e).select(e.name, e.record_doctype.as_("doctype"), e.record_name.as_("record"), e.title, e.kind, e.pile, e.exited_on.as_("on"),
			e.exited_by.as_("by"), e.area, e.note).where(Criterion.all(_out_where(space, area, start_dt, end_dt, pile, filters)))  # system: the Outbox is the owner's own
			.orderby(e.exited_on, order=Order.desc).orderby(e.creation, order=Order.desc).limit(page_length).offset(start).run(as_dict=True))
		total = tabs[pile]
		_decorate(rows)
	areas = names_map("Life Area", [r["area"] for r in rows], "area_name")
	for r in rows:
		r["area_name"] = areas.get(r["area"])
		r["on"] = str(r["on"])[:19]
	return {"rows": rows, "total": total, "tabs": tabs, "period": period,
		"from": str(start_dt)[:10], "to": str(add_days(getdate(end_dt), -1))}


def _in_rows(space, area, start_dt, end_dt, start, page_length):
	t = _in_query(space, area, start_dt, end_dt).as_("t")
	rows = frappe.qb.from_(t).select(t.star).orderby(t.came_on, order=Order.desc).limit(page_length).offset(start).run(as_dict=True)  # system: wrapped query over the owner's own space
	return [{"name": f"in:{r.doctype}:{r.name}", "doctype": r.doctype, "record": r.name, "title": r.title, "kind": LABEL[r.doctype], "pile": "In",
		"on": r.came_on, "area": r.area, "sensitive": bool(r.is_sensitive), "exists": True, "can_bring_back": False} for r in rows]


def _decorate(rows):
	"""Whether each record still exists, is sensitive, and can be brought back."""
	by_type = {}
	for r in rows:
		by_type.setdefault(r.doctype, []).append(r.record)
	live = {}
	for dt, names in by_type.items():
		fields = ["name", "is_sensitive"] if dt == "Life Inbox Item" else ["name"]
		if dt == "Life Goal":
			fields += ["horizon", "cycle"]
		for x in frappe.get_list(dt, filters={"name": ("in", names)}, fields=fields):
			live[(dt, x.name)] = x
	trashed = {(d.deleted_doctype, d.deleted_name) for d in frappe.get_all("Deleted Document", filters={  # system: Frappe's trash is not a space record
		"deleted_name": ("in", [r.record for r in rows] or ["-"]), "restored": 0, "creation": (">=", add_days(now_datetime(), -30))},
		fields=["deleted_doctype", "deleted_name"])}
	closed = set(frappe.get_list("Life Cycle", filters={"name": ("in", [x.cycle for x in live.values() if x.get("cycle")] or ["-"]), "status": "Closed"},
		pluck="name"))
	for r in rows:
		x = live.get((r.doctype, r.record))
		r["exists"] = bool(x)
		r["sensitive"] = bool(x and x.get("is_sensitive"))
		r["can_bring_back"] = _can_bring_back(r, x, (r.doctype, r.record) in trashed, closed)


def _can_bring_back(row, live, trashed, closed_cycles):
	if not live:
		return trashed
	if row.doctype == "Life Task":
		return True
	if row.doctype == "Life Goal":
		if live.get("horizon") == "12 weeks" and row.pile != "Parked":
			return live.get("cycle") not in closed_cycles
		return True
	return False  # a capture done or parked: their result is elsewhere


@frappe.whitelist(methods=["POST"])
def bring_back(exit: str):
	"""Undo one exit where the record allows: reopen a task or a goal, bring a task or goal back from Someday, or restore a
	deleted record from the trash. The record's own hooks then mark the exit reversed."""
	_person()
	e = permissions.get_doc_checked("Life Exit", exit)
	permissions.require_space(e.space, write=True)
	if e.reversed:
		frappe.throw(_("This has already been brought back."), title=_("Already brought back"))
	dt, name = e.record_doctype, e.record_name
	if not frappe.db.exists(dt, name):
		from lifeos.library import trash

		dd = frappe.db.get_value("Deleted Document", {"deleted_doctype": dt, "deleted_name": name, "restored": 0}, "name", order_by="creation desc")
		if not dd:
			frappe.throw(_("{0} is no longer in the trash, so it cannot be brought back.").format(frappe.bold(e.title)), title=_("Record is not in trash"))
		trash.restore(dd)
	elif e.pile == "Parked" and dt in ("Life Task", "Life Goal"):
		from lifeos.api import someday

		someday.bring_back(dt, name)
	elif dt == "Life Task":
		doc = permissions.get_doc_checked(dt, name, "write")
		doc.status = "Open"
		doc.save()
	elif dt == "Life Goal":
		from lifeos.api import goals

		doc = permissions.get_doc_checked(dt, name, "write")
		if doc.horizon == "12 weeks":
			if frappe.db.get_value("Life Cycle", doc.cycle, "status") == "Closed":
				frappe.throw(_("A goal of a closed cycle cannot be reopened."), title=_("Goal cycle is closed"))
			doc.outcome = "In Progress"
			doc.save()
		else:
			goals.set_status(name, "Active")
	else:
		frappe.throw(_("{0} cannot be brought back from here.").format(frappe.bold(e.title)), title=_("Cannot bring back"))
	e.reload()
	if not e.reversed:  # the record's state did not take it off the pile (it was changed since): reverse it here
		outbox.reverse(dt, name, e.pile)
	return {"exit": e.name, "doctype": dt, "name": name, "reversed": 1}


@frappe.whitelist(methods=["GET"])
def chart(space: str | None = None, area: str | None = None, weeks: int = 8):
	"""In against out for each of the last `weeks` weeks (Monday to Sunday), oldest first, the current week last."""
	_person()
	space = permissions.resolve_space(space)
	area = lens_area(area)
	weeks = max(1, min(int(weeks or 8), 26))
	day = getdate(today())
	monday = add_days(day, -day.weekday())
	out = []
	for i in range(weeks - 1, -1, -1):
		s = add_days(monday, -7 * i)
		a, b = get_datetime(str(s)), get_datetime(str(add_days(s, 7)))
		out.append({"week_of": str(s), "in": in_count(space, area, a, b), "out": out_counts(space, area, a, b)["all"]})
	return {"weeks": out}


def bounds(period, from_date=None, to_date=None):
	"""[start, end) of a named period, or of the days from_date to to_date (set 8: a review's period), and the period's name."""
	if from_date and to_date:
		a, b = getdate(from_date), getdate(to_date)
		if b < a or (b - a).days > 400:
			frappe.throw(_("Choose a period of at most a year."), title=_("Period is too long"))
		return get_datetime(str(a)), get_datetime(str(add_days(b, 1))), "custom"
	start_dt, end_dt = outbox.period_bounds(period)
	return start_dt, end_dt, period if period in outbox.PERIODS else "week"


def total(space, pile, period="week", area=None, from_date=None, to_date=None):
	"""What `list` answers as `total` for the same arguments, without its rows or its other tabs (for the count doors)."""
	start_dt, end_dt, _p = bounds(period, from_date, to_date)
	if pile == "in":
		return in_count(space, area, start_dt, end_dt)
	return out_counts(space, area, start_dt, end_dt)[pile if pile in TABS else "Done"]


def week_line(space, area=None):
	"""Today's line: this week's in and out, each a count with the list it opens (lifeos/review/counts.py)."""
	from lifeos.review import counts

	return {"in": counts.outbox(space, area, "in", "came in"), "out": counts.outbox(space, area, "all", "out")}
