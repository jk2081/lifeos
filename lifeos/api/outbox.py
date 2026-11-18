"""The Outbox (set 7): what left the plate, by pile, for a period; what came in; an 8-week chart of in against out; and Bring
back. A record, not a place to work: the only action is Bring back. People only; agents never read exits."""
import builtins

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

from lifeos import outbox, permissions
from lifeos.api.utils import area_filter, lens_area, names_map, page, std_clause

TABS = ("Done", "Delegated", "Parked", "Discarded", "all", "in")
LABEL = {"Life Task": "Task", "Life Goal": "Goal", "Life Inbox Item": "Capture", "Life Idea": "Idea"}


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("The Outbox is for people."), frappe.PermissionError)


def _out_where(space, area, start, end, pile=None, filters=None):
	values = {"space": space, "start": start, "end": end}
	where = "e.space = %(space)s and e.reversed = 0 and e.exited_on >= %(start)s and e.exited_on < %(end)s"
	if filters:
		extra, values = std_clause("Life Exit", filters, "e", values)
		where += extra
	if pile and pile != "all":
		where += " and e.pile = %(pile)s"
		values["pile"] = pile
	if area:
		where += " and " + area_filter(space, area, "e.area", values)
	return where, values


# what came in: captures received, and tasks, goals and ideas created directly (not from a capture, not made from an idea,
# not carried from an earlier task or goal)
IN_PARTS = {
	"Life Inbox Item": "select 'Life Inbox Item' as doctype, x.name, x.title, x.area, x.creation as came_on, x.is_sensitive from `tabLife Inbox Item` x where {w}",
	"Life Task": """select 'Life Task', x.name, x.title, x.area, x.creation, 0 from `tabLife Task` x where {w} and ifnull(x.inbox_item, '') = ''
		and ifnull(x.carried_from, '') = '' and not exists (select 1 from `tabLife Idea` i where i.brought_to_doctype = 'Life Task' and i.brought_to_name = x.name)""",
	"Life Goal": """select 'Life Goal', x.name, x.title, x.area, x.creation, 0 from `tabLife Goal` x where {w} and ifnull(x.carried_from, '') = ''
		and not exists (select 1 from `tabLife Idea` i where i.brought_to_doctype = 'Life Goal' and i.brought_to_name = x.name)""",
	"Life Idea": "select 'Life Idea', x.name, x.title, x.area, x.creation, 0 from `tabLife Idea` x where {w} and ifnull(x.source_doctype, '') != 'Life Inbox Item'",
}


def _in_sql(space, area, start, end):
	values = {"space": space, "start": start, "end": end}
	w = "x.space = %(space)s and x.creation >= %(start)s and x.creation < %(end)s"
	if area:
		w += " and " + area_filter(space, area, "x.area", values)
	return " union all ".join(f"({q.format(w=w)})" for q in IN_PARTS.values()), values


def in_count(space, area, start, end):
	sql, values = _in_sql(space, area, start, end)
	# nosemgrep: frappe-sql-format-injection -- the parts are constant SQL; the area condition comes from area_filter; values are parameters
	return frappe.db.sql(f"select count(*) from ({sql}) t", values)[0][0]


def out_counts(space, area, start, end, filters=None):
	where, values = _out_where(space, area, start, end, filters=filters)
	# nosemgrep: frappe-sql-format-injection -- WHERE from _out_where (constant SQL and area_filter); values are parameters
	rows = dict(frappe.db.sql(f"select e.pile, count(*) from `tabLife Exit` e where {where} group by e.pile", values))
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
		where, values = _out_where(space, area, start_dt, end_dt, pile, filters)
		# nosemgrep: frappe-sql-format-injection -- WHERE from _out_where (constant SQL and area_filter); values are parameters
		rows = frappe.db.sql(f"""select e.name, e.record_doctype as doctype, e.record_name as record, e.title, e.kind, e.pile, e.exited_on as `on`,
			e.exited_by as `by`, e.area, e.note from `tabLife Exit` e where {where} order by e.exited_on desc, e.creation desc
			limit %(s)s, %(n)s""", {**values, "s": start, "n": page_length}, as_dict=True)
		total = tabs[pile]
		_decorate(rows)
	areas = names_map("Life Area", [r["area"] for r in rows], "area_name")
	for r in rows:
		r["area_name"] = areas.get(r["area"])
		r["on"] = str(r["on"])[:19]
	return {"rows": rows, "total": total, "tabs": tabs, "period": period,
		"from": str(start_dt)[:10], "to": str(add_days(getdate(end_dt), -1))}


def _in_rows(space, area, start_dt, end_dt, start, page_length):
	sql, values = _in_sql(space, area, start_dt, end_dt)
	# nosemgrep: frappe-sql-format-injection -- the parts are constant SQL; the area condition comes from area_filter; values are parameters
	rows = frappe.db.sql(f"select * from ({sql}) t order by came_on desc limit %(s)s, %(n)s", {**values, "s": start, "n": page_length}, as_dict=True)
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
			fields += ["goal_type", "cycle"]
		for x in frappe.get_all(dt, filters={"name": ("in", names)}, fields=fields):
			live[(dt, x.name)] = x
	trashed = {(d.deleted_doctype, d.deleted_name) for d in frappe.get_all("Deleted Document", filters={
		"deleted_name": ("in", [r.record for r in rows] or ["-"]), "restored": 0, "creation": (">=", add_days(now_datetime(), -30))},
		fields=["deleted_doctype", "deleted_name"])}
	closed = set(frappe.get_all("Life Cycle", filters={"name": ("in", [x.cycle for x in live.values() if x.get("cycle")] or ["-"]), "status": "Closed"},
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
		if live.get("goal_type") == "12 Week Year" and row.pile != "Parked":
			return live.get("cycle") not in closed_cycles
		return True
	return False  # a capture done or parked, an idea brought back: their result is elsewhere


@frappe.whitelist(methods=["POST"])
def bring_back(exit: str):
	"""Undo one exit where the record allows: reopen a task or a goal, bring a task or goal back from Someday, or restore a
	deleted record from the trash. The record's own hooks then mark the exit reversed."""
	_person()
	e = permissions.get_doc_checked("Life Exit", exit)
	permissions.require_space(e.space, write=True)
	if e.reversed:
		frappe.throw(_("This has already been brought back."))
	dt, name = e.record_doctype, e.record_name
	if not frappe.db.exists(dt, name):
		from lifeos import trash

		dd = frappe.db.get_value("Deleted Document", {"deleted_doctype": dt, "deleted_name": name, "restored": 0}, "name", order_by="creation desc")
		if not dd:
			frappe.throw(_("{0} is no longer in the trash, so it cannot be brought back.").format(frappe.bold(e.title)))
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
		if doc.goal_type == "12 Week Year":
			if frappe.db.get_value("Life Cycle", doc.cycle, "status") == "Closed":
				frappe.throw(_("A goal of a closed cycle cannot be reopened."))
			doc.outcome = "In Progress"
			doc.save()
		else:
			goals.set_status(name, "Active")
	else:
		frappe.throw(_("{0} cannot be brought back from here.").format(frappe.bold(e.title)))
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
			frappe.throw(_("Choose a period of at most a year."))
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
	"""Today's line: this week's in and out, each a count with the list it opens (lifeos/counts.py)."""
	from lifeos import counts

	return {"in": counts.outbox(space, area, "in", "came in"), "out": counts.outbox(space, area, "all", "out")}
