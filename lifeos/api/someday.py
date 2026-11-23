"""Someday, the one parking lot: park tasks, goals and notes out of the way, and bring them back, keep them for longer, or
purge them. An open-ended goal takes its open tasks with it. Parking keeps `creation`.
Agents may only propose parking."""
import builtins
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_months, cint, getdate, today

from lifeos import permissions
from lifeos.api.utils import names_map, page, parse, std_filters
from lifeos.review.counts import rules

PARKABLE = ("Life Task", "Life Goal", "Life Note")
TYPE_OF = {"Life Task": "Task", "Life Goal": "Goal", "Life Note": "Note"}
TAB_TYPE = {"tasks": "Life Task", "goals": "Life Goal", "notes": "Life Note"}
TABS = ("all", "due", "tasks", "goals", "notes")
# the SQL that says "parked" for each kind
PARKED = {"Life Task": "x.status = 'Someday' and x.is_archived = 0", "Life Goal": "x.is_someday = 1 and x.is_archived = 0",
	"Life Note": "x.is_someday = 1 and x.is_archived = 0"}


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Agents cannot park, bring back or purge. They may propose moving something to Someday."), frappe.PermissionError, title=_("Agents cannot park items"))


def review_date(on=None):
	return str(add_months(getdate(on or today()), rules()["someday_review_months"]))


def _sub(doctype, space, filters, values, i, area=None):
	"""One branch of the union: the parked rows of one DocType with the common columns."""
	where = [f"x.space = %(space)s", PARKED[doctype]]
	conds, values = std_filters(doctype, filters, "x", values, prefix=f"s{i}_")
	if area:
		from lifeos.api.utils import area_filter

		where.append(area_filter(space, area, "x.area", values, also_in="Life Task" if doctype == "Life Task" else None))
	extra = "''"
	if doctype == "Life Goal":
		extra = "(select count(*) from `tabLife Task` t where t.someday_with = x.name and t.status = 'Someday')"
	elif doctype == "Life Task":
		extra = "ifnull(x.goal, '')"
	return (f"select '{doctype}' as doctype, x.name, x.title, x.area, x.creation, x.someday_on, x.someday_review_on, "
		f"x.someday_note, {extra} as extra from `tab{doctype}` x where {' and '.join(where + conds)}"), values


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, tab: str | None = "all", area: str | None = None, filters: str | builtins.list | dict | None = None,
		order_by: str | None = None, start: int | str | None = 0, page_length: int | str | None = 50):
	"""Parked items of a space, oldest review first. tab: all, due (review date reached), tasks, goals, notes.
	filters: standard filters on the fields every parked kind has (title, area, someday_on, someday_review_on, name,
	creation). `tabs` counts each tab under the same filters."""
	space = permissions.resolve_space(space)
	tab = tab if tab in TABS else "all"
	start, page_length = page(start, page_length)
	filters = parse(filters, [])
	values = {"space": space, "today": getdate(today())}
	parts = []
	for i, dt in enumerate(PARKABLE):
		sql, values = _sub(dt, space, filters, values, i, area)
		parts.append(sql)
	union = " union all ".join(parts)
	# nosemgrep: frappe-sql-format-injection -- each branch is _sub's fixed SQL over a PARKABLE table, with std_filters columns checked against meta
	counts = frappe.db.sql(f"""select doctype, count(*), sum(ifnull(someday_review_on, '2999-01-01') <= %(today)s)
		from ({union}) u group by doctype""", values)
	by = {r[0]: int(r[1]) for r in counts}
	due = sum(int(r[2] or 0) for r in counts)
	tabs = {"all": sum(by.values()), "due": due, **{k: by.get(TAB_TYPE[k], 0) for k in TABS if k in TAB_TYPE}}
	where = ""
	if tab == "due":
		where = "where ifnull(someday_review_on, '2999-01-01') <= %(today)s"
	elif tab in TAB_TYPE:
		where = "where doctype = %(tab_type)s"
		values["tab_type"] = TAB_TYPE[tab]
	order = {"creation": "creation", "someday_on": "someday_on", "title": "title"}.get(str(order_by or "").split(" ")[0], "someday_review_on")
	way = "desc" if " desc" in str(order_by or "") else "asc"
	# nosemgrep: frappe-sql-format-injection -- the union as above; `order` and `way` come from fixed allowlists; values are parameters
	rows = frappe.db.sql(f"select * from ({union}) u {where} order by {order} {way}, creation asc limit %(start)s, %(len)s",
		{**values, "start": start, "len": page_length}, as_dict=True)
	total = tabs[tab]
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	parents = names_map("Life Area", [r.area for r in rows], "parent_area")
	parent_names = names_map("Life Area", [p for p in parents.values() if p], "area_name")
	now = getdate(today())
	for r in rows:
		r["type"] = TYPE_OF[r.doctype]
		r["area_name"] = areas.get(r.area)
		r["area_path"] = " · ".join(x for x in (parent_names.get(parents.get(r.area)), areas.get(r.area)) if x)
		r["due"] = bool(r.someday_review_on and getdate(r.someday_review_on) <= now)
		r["tasks"] = cint(r.extra) if r.doctype == "Life Goal" else None
		r["ref"] = {"Life Task": "task", "Life Goal": "goal", "Life Note": "note"}[r.doctype] + ":" + r.name
		for k in ("creation", "someday_on", "someday_review_on"):
			r[k] = str(r[k])[:10] if r.get(k) else None
		r.pop("extra", None)
	return {"rows": rows, "total": total, "tabs": tabs, "review_months": rules()["someday_review_months"], "today": str(now)}


def count(space):
	return list(space=space, page_length=1)["tabs"]


def _check(doctype):
	if doctype not in PARKABLE:
		frappe.throw(_("Only tasks, goals and notes can go on the Someday list."), title=_("Cannot go on Someday"))


def _goal_tasks(goal):
	"""The open tasks an open-ended goal takes with it to Someday."""
	return frappe.get_list("Life Task", filters={"goal": goal, "status": ["in", ["Open", "Doing", "Waiting"]], "is_archived": 0}, pluck="name")


def park_doc(doc, note=None):
	"""Park one record. Its creation is untouched; an open-ended goal takes its open tasks with it."""
	day = today()
	rev = review_date(day)
	if doc.doctype == "Life Task":
		if doc.status not in ("Open", "Doing", "Waiting", "Someday"):
			frappe.throw(_("Only an open task can go on the Someday list."), title=_("Task is not open"))
		doc.status = "Someday"
	elif doc.doctype == "Life Goal":
		if (doc.outcome or "In Progress") != "In Progress":
			frappe.throw(_("Only a goal in progress can go on the Someday list."), title=_("Goal is not in progress"))
		doc.is_someday = 1
	elif doc.doctype == "Life Note":
		doc.is_someday = 1
	doc.someday_on, doc.someday_review_on = day, rev
	if note is not None:
		doc.someday_note = note
	doc.save()
	if doc.doctype == "Life Goal" and doc.horizon == "Long term":
		for name in _goal_tasks(doc.name):
			t = frappe.get_doc("Life Task", name)
			t.check_permission("write")
			t.status, t.someday_on, t.someday_review_on, t.someday_with = "Someday", day, rev, doc.name
			t.save()
	return doc


@frappe.whitelist(methods=["POST"])
def park(doctype: str, name: str, note: str | None = None):
	"""Move a task or goal (an open-ended goal with its open tasks) to Someday. Returns what changed, for Undo."""
	_person()
	_check(doctype)
	doc = permissions.get_doc_checked(doctype, name, "write")
	before = _snapshot(doc)
	park_doc(doc, note)
	return {"doctype": doctype, "name": name, "title": doc.title, "review_on": doc.someday_review_on, "undo": before}


def _snapshot(doc):
	"""What Undo needs to put a record back: its status fields, and for an open-ended goal the open tasks it took."""
	out = {"doctype": doc.doctype, "name": doc.name, "status": doc.get("status"), "is_someday": doc.get("is_someday"),
		"due_date": doc.get("due_date"), "on_hold": doc.get("on_hold"), "outcome": doc.get("outcome")}
	if doc.doctype == "Life Goal" and doc.horizon == "Long term":
		out["tasks"] = frappe.get_list("Life Task", filters={"name": ["in", _goal_tasks(doc.name) or ["-"]]}, fields=["name", "status"])
	return out


@frappe.whitelist(methods=["POST"])
def bring_back(doctype: str, name: str, due_date: str | date | None = None, status: str | None = None, cycle: str | None = None,
		target_date: str | date | None = None):
	"""Make a parked item live again. A task: an optional due date. A goal: a cycle (12 Week Year goals) or a target date;
	a long-term goal also a status (Active or On Hold), and the tasks it took come back as Open. A note: it is simply no
	longer parked."""
	_person()
	_check(doctype)
	doc = permissions.get_doc_checked(doctype, name, "write")
	out = {"doctype": doctype, "name": name}
	if doctype == "Life Task":
		doc.status = "Open"
		doc.due_date = due_date or None
		doc.save()
	elif doctype == "Life Goal":
		doc.is_someday = 0
		if cycle and doc.horizon == "12 weeks":
			doc.cycle = cycle
		if target_date:
			doc.target_date = target_date
		if doc.horizon == "Long term":
			doc.on_hold = 1 if status == "On Hold" else 0
		doc.save()
		for t in frappe.get_list("Life Task", filters={"someday_with": doc.name, "status": "Someday"}, pluck="name"):
			td = frappe.get_doc("Life Task", t)
			td.status = "Open"
			td.save()
	else:
		doc.is_someday = 0
		doc.save()
	return out


@frappe.whitelist(methods=["POST"])
def keep(doctype: str, name: str, months: int | str | None = None):
	"""Keep a parked item for another review period (3 months by default) from today."""
	_person()
	_check(doctype)
	doc = permissions.get_doc_checked(doctype, name, "write")
	doc.someday_review_on = str(add_months(getdate(today()), cint(months) or rules()["someday_review_months"]))
	doc.flags.keep_someday = True
	doc.save()
	return {"review_on": doc.someday_review_on}


@frappe.whitelist(methods=["POST"])
def purge(doctype: str, name: str):
	"""Move a parked item to the trash. An open-ended goal takes the tasks it was parked with."""
	_person()
	_check(doctype)
	from lifeos.library import trash

	doc = permissions.get_doc_checked(doctype, name, "write")
	if doctype == "Life Goal":
		for t in frappe.get_list("Life Task", filters={"someday_with": name, "status": "Someday"}, pluck="name"):
			trash.delete("Life Task", t)
	return trash.delete(doctype, name)


@frappe.whitelist(methods=["POST"])
def create(title: str, space: str | None = None, body_md: str | None = None, area: str | None = None, goal: str | None = None,
		note: str | None = None, as_note: bool | int = 0):
	"""Something new on the Someday list: a task marked Someday with a review date, or (`as_note`) a thought with no action,
	a note marked Someday. From the New menu, a note selection, a chat open item or a digest item."""
	_person()
	space = permissions.resolve_space(space, write=True)
	title = " ".join((title or "").split())[:140]
	if not title:
		frappe.throw(_("Type what to park."), title=_("Nothing to park"))
	fields = {"space": space, "title": title, "area": area or None, "someday_on": today(), "someday_review_on": review_date(), "someday_note": note}
	if cint(as_note):
		doc = frappe.get_doc({"doctype": "Life Note", **fields, "content_md": body_md or "", "is_someday": 1}).insert()
	else:
		doc = frappe.get_doc({"doctype": "Life Task", **fields, "notes_md": body_md, "goal": goal or None, "status": "Someday"}).insert()
	return {"name": doc.name, "title": doc.title, "doctype": doc.doctype, "review_on": doc.someday_review_on}


@frappe.whitelist(methods=["POST"])
def undo(snapshot: str | dict):
	"""Put records back as a snapshot from park or a Reset decision says they were."""
	_person()
	snap = parse(snapshot, {}) or {}
	restore_snapshot(snap)
	return {"ok": True}


def restore_snapshot(snap):
	if not isinstance(snap.get("doctype"), str) or not isinstance(snap.get("name"), str):  # a dict name would act as a filter
		frappe.throw(frappe._("Nothing to undo."), title=_("Nothing to undo"))
	doc = permissions.get_doc_checked(snap["doctype"], snap["name"], "write")
	if doc.get("is_archived") and not cint(snap.get("is_archived")) and snap.get("is_archived") is not None:
		from lifeos.library import archive

		archive.set_archived(doc.doctype, doc.name, False)
		doc.reload()
	if doc.doctype == "Life Note":
		doc.is_someday = cint(snap.get("is_someday"))
	elif doc.doctype == "Life Goal":
		doc.is_someday = cint(snap.get("is_someday"))
		doc.on_hold = cint(snap.get("on_hold"))
		if snap.get("outcome"):
			doc.outcome = snap["outcome"]
	elif snap.get("status"):
		doc.status = snap["status"]
	if "due_date" in snap and doc.doctype == "Life Task":
		doc.due_date = snap.get("due_date") or None
	doc.save()
	if snap.get("is_archived") is not None and doc.meta.has_field("is_archived") and cint(doc.is_archived) != cint(snap["is_archived"]):
		from lifeos.library import archive

		archive.set_archived(doc.doctype, doc.name, bool(cint(snap["is_archived"])))
	for t in snap.get("tasks") or []:
		td = permissions.get_doc_checked("Life Task", t["name"], "write")
		td.status = t["status"]
		td.save()
