"""Someday (UX fixes, set 5): park tasks, projects (with their open tasks), goals and ideas out of the way, and bring
them back, keep them for longer, or purge them. Parking keeps `creation`. Agents may only propose parking."""
import builtins
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_months, cint, getdate, today

from lifeos import permissions
from lifeos.api.utils import names_map, page, parse, std_filters
from lifeos.counts import rules

PARKABLE = ("Life Task", "Life Project", "Life Goal", "Life Idea")
TYPE_OF = {"Life Task": "Task", "Life Project": "Project", "Life Goal": "Goal", "Life Idea": "Idea"}
TAB_TYPE = {"tasks": "Life Task", "projects": "Life Project", "goals": "Life Goal", "ideas": "Life Idea"}
TABS = ("all", "due", "tasks", "projects", "goals", "ideas")
# the SQL that says "parked" for each kind
PARKED = {"Life Task": "x.status = 'Someday' and x.is_archived = 0", "Life Project": "x.status = 'Someday'",
	"Life Goal": "x.is_someday = 1", "Life Idea": "x.status = 'Someday'"}


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Agents cannot park, bring back or purge. They may propose moving something to Someday."), frappe.PermissionError)


def review_date(on=None):
	return str(add_months(getdate(on or today()), rules()["someday_review_months"]))


def _sub(doctype, space, filters, values, i, area=None):
	"""One branch of the union: the parked rows of one DocType with the common columns."""
	where = [f"x.space = %(space)s", PARKED[doctype]]
	conds, values = std_filters(doctype, filters, "x", values, prefix=f"s{i}_")
	if area:
		from lifeos.api.utils import area_filter

		where.append(area_filter(space, area, "x.area", values))
	extra = "''"
	if doctype == "Life Project":
		extra = "(select count(*) from `tabLife Task` t where t.someday_with = x.name and t.status = 'Someday')"
	elif doctype == "Life Idea":
		extra = "ifnull(x.source_doctype, '')"
	elif doctype == "Life Task":
		extra = "ifnull(x.project, '')"
	return (f"select '{doctype}' as doctype, x.name, x.title, x.area, x.creation, x.someday_on, x.someday_review_on, "
		f"x.someday_note, {extra} as extra from `tab{doctype}` x where {' and '.join(where + conds)}"), values


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, tab: str | None = "all", area: str | None = None, filters: str | builtins.list | dict | None = None,
		order_by: str | None = None, start: int | str | None = 0, page_length: int | str | None = 50):
	"""Parked items of a space, oldest review first. tab: all, due (review date reached), tasks, projects, goals, ideas.
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
	tabs = {"all": sum(by.values()), "due": due, **{k: by.get(dt, 0) for k, dt in TAB_TYPE.items()}}
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
	parents = {r.area: frappe.db.get_value("Life Area", r.area, "parent_area") for r in rows if r.area}
	parent_names = names_map("Life Area", [p for p in parents.values() if p], "area_name")
	now = getdate(today())
	for r in rows:
		r["type"] = TYPE_OF[r.doctype]
		r["area_name"] = areas.get(r.area)
		r["area_path"] = " · ".join(x for x in (parent_names.get(parents.get(r.area)), areas.get(r.area)) if x)
		r["due"] = bool(r.someday_review_on and getdate(r.someday_review_on) <= now)
		r["tasks"] = cint(r.extra) if r.doctype == "Life Project" else None
		r["from_source"] = r.extra if r.doctype == "Life Idea" and r.extra else None
		r["ref"] = {"Life Task": "task", "Life Project": "project", "Life Goal": "goal", "Life Idea": "idea"}[r.doctype] + ":" + r.name
		for k in ("creation", "someday_on", "someday_review_on"):
			r[k] = str(r[k])[:10] if r.get(k) else None
		r.pop("extra", None)
	return {"rows": rows, "total": total, "tabs": tabs, "review_months": rules()["someday_review_months"], "today": str(now)}


def count(space):
	return list(space=space, page_length=1)["tabs"]


def _check(doctype):
	if doctype not in PARKABLE:
		frappe.throw(_("Only tasks, projects, goals and ideas can go on the Someday list."))


def park_doc(doc, note=None):
	"""Park one record. Its creation is untouched; a project takes its open tasks with it."""
	day = today()
	rev = review_date(day)
	if doc.doctype == "Life Task":
		if doc.status not in ("Open", "Doing", "Waiting", "Someday"):
			frappe.throw(_("Only an open task can go on the Someday list."))
		doc.status = "Someday"
	elif doc.doctype == "Life Project":
		if doc.status not in ("Active", "On Hold", "Someday"):
			frappe.throw(_("Only an active or on-hold project can go on the Someday list."))
		doc.status = "Someday"
		doc.flags.keep_someday = True
	elif doc.doctype == "Life Goal":
		if (doc.outcome or "In Progress") != "In Progress":
			frappe.throw(_("Only a goal in progress can go on the Someday list."))
		doc.is_someday = 1
	doc.someday_on, doc.someday_review_on = day, rev
	if note is not None:
		doc.someday_note = note
	doc.save()
	if doc.doctype == "Life Project":
		for name in frappe.get_all("Life Task", filters={"project": doc.name, "status": ["in", ["Open", "Doing", "Waiting"]], "is_archived": 0}, pluck="name"):
			t = frappe.get_doc("Life Task", name)
			t.check_permission("write")
			t.status, t.someday_on, t.someday_review_on, t.someday_with = "Someday", day, rev, doc.name
			t.save()
	return doc


@frappe.whitelist(methods=["POST"])
def park(doctype: str, name: str, note: str | None = None):
	"""Move a task, project (with its open tasks) or goal to Someday. Returns what changed, for Undo."""
	_person()
	_check(doctype)
	doc = permissions.get_doc_checked(doctype, name, "write")
	before = _snapshot(doc)
	park_doc(doc, note)
	return {"doctype": doctype, "name": name, "title": doc.title, "review_on": doc.someday_review_on, "undo": before}


def _snapshot(doc):
	"""What Undo needs to put a record back: its status fields, and for a project the open tasks it took."""
	out = {"doctype": doc.doctype, "name": doc.name, "status": doc.get("status"), "is_someday": doc.get("is_someday"),
		"due_date": doc.get("due_date")}
	if doc.doctype == "Life Project":
		out["tasks"] = frappe.get_all("Life Task", filters={"project": doc.name, "status": ["in", ["Open", "Doing", "Waiting"]], "is_archived": 0},
			fields=["name", "status"])
	return out


@frappe.whitelist(methods=["POST"])
def bring_back(doctype: str, name: str, due_date: str | date | None = None, status: str | None = None, cycle: str | None = None,
		target_date: str | date | None = None, make: str | None = None, area: str | None = None):
	"""Make a parked item live again. A task: an optional due date. A project: a status (Active or On Hold); the tasks
	it took come back as Open. A goal: a cycle (12 Week Year goals) or a target date. An idea: make a task, project or note."""
	_person()
	_check(doctype)
	doc = permissions.get_doc_checked(doctype, name, "write")
	out = {"doctype": doctype, "name": name}
	if doctype == "Life Task":
		doc.status = "Open"
		doc.due_date = due_date or None
		doc.save()
	elif doctype == "Life Project":
		doc.status = status if status in ("Active", "On Hold") else "Active"
		doc.someday_on = doc.someday_review_on = None
		doc.save()
		for t in frappe.get_all("Life Task", filters={"someday_with": doc.name, "status": "Someday"}, pluck="name"):
			td = frappe.get_doc("Life Task", t)
			td.status = "Open"
			td.save()
	elif doctype == "Life Goal":
		doc.is_someday = 0
		if cycle and doc.goal_type == "12 Week Year":
			doc.cycle = cycle
		if target_date:
			doc.target_date = target_date
		doc.save()
	else:
		if make not in ("task", "project", "note"):
			frappe.throw(_("Choose what the idea becomes: a task, a project or a note."))
		target_area = area or doc.area
		if make == "task":
			new = frappe.get_doc({"doctype": "Life Task", "space": doc.space, "title": doc.title[:140], "area": target_area,
				"project": doc.project if doc.project and target_area == doc.area else None, "notes_md": doc.body_md, "due_date": due_date or None,
				"status": "Open"}).insert()
		elif make == "project":
			if not target_area:
				frappe.throw(_("A project needs an area."))
			new = frappe.get_doc({"doctype": "Life Project", "space": doc.space, "title": doc.title, "area": target_area,
				"notes_md": doc.body_md, "status": "Active"}).insert()
		else:
			new = frappe.get_doc({"doctype": "Life Note", "space": doc.space, "title": doc.title, "area": target_area,
				"content_md": doc.body_md or ""}).insert()
		doc.status = "Brought Back"
		doc.brought_to_doctype, doc.brought_to_name = new.doctype, new.name
		doc.save()
		out["made"] = {"doctype": new.doctype, "name": new.name}
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
	"""Move a parked item to the trash. A project takes the tasks it was parked with."""
	_person()
	_check(doctype)
	from lifeos import trash

	doc = permissions.get_doc_checked(doctype, name, "write")
	if doctype == "Life Project":
		for t in frappe.get_all("Life Task", filters={"someday_with": name, "status": "Someday"}, pluck="name"):
			trash.delete("Life Task", t)
	return trash.delete(doctype, name)


@frappe.whitelist(methods=["POST"])
def create_idea(title: str, space: str | None = None, body_md: str | None = None, area: str | None = None, project: str | None = None,
		source_doctype: str | None = None, source_name: str | None = None, note: str | None = None):
	"""A new idea on the Someday list, from the New menu, a note selection, a chat open item or a digest item."""
	_person()
	space = permissions.resolve_space(space, write=True)
	title = " ".join((title or "").split())[:140]
	if not title:
		frappe.throw(_("Type the idea."))
	if source_doctype and source_name:
		src = permissions.get_doc_checked(source_doctype, source_name)
		if src.get("space") != space:
			frappe.throw(_("The source belongs to another space."))
	doc = frappe.get_doc({"doctype": "Life Idea", "space": space, "title": title, "body_md": body_md, "area": area or None,
		"project": project or None, "source_doctype": source_doctype if source_name else None, "source_name": source_name or None,
		"status": "Someday", "someday_on": today(), "someday_review_on": review_date(), "someday_note": note}).insert()
	return {"name": doc.name, "title": doc.title, "review_on": doc.someday_review_on}


@frappe.whitelist(methods=["GET"])
def get_idea(idea: str):
	doc = permissions.get_doc_checked("Life Idea", idea)
	out = doc.as_dict()
	out["area_name"] = frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None
	if doc.source_doctype and doc.source_name:
		from lifeos import links

		out["source_title"] = links.title_of(doc.source_doctype, doc.source_name)
	return {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in out.items() if not k.startswith("_")}


@frappe.whitelist(methods=["POST"])
def undo(snapshot: str | dict):
	"""Put records back as a snapshot from park or a Reset decision says they were."""
	_person()
	snap = parse(snapshot, {}) or {}
	restore_snapshot(snap)
	return {"ok": True}


def restore_snapshot(snap):
	if not isinstance(snap.get("doctype"), str) or not isinstance(snap.get("name"), str):  # a dict name would act as a filter
		frappe.throw(frappe._("Nothing to undo."))
	doc = permissions.get_doc_checked(snap["doctype"], snap["name"], "write")
	if doc.get("is_archived") and not cint(snap.get("is_archived")) and snap.get("is_archived") is not None:
		from lifeos import archive

		archive.set_archived(doc.doctype, doc.name, False)
		doc.reload()
	if doc.doctype == "Life Goal":
		doc.is_someday = cint(snap.get("is_someday"))
	elif snap.get("status"):
		doc.status = snap["status"]
	if "due_date" in snap and doc.doctype == "Life Task":
		doc.due_date = snap.get("due_date") or None
	doc.save()
	if snap.get("is_archived") is not None and doc.meta.has_field("is_archived") and cint(doc.is_archived) != cint(snap["is_archived"]):
		from lifeos import archive

		archive.set_archived(doc.doctype, doc.name, bool(cint(snap["is_archived"])))
	for t in snap.get("tasks") or []:
		td = permissions.get_doc_checked("Life Task", t["name"], "write")
		td.status = t["status"]
		td.save()
