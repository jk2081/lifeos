"""Projects: the list across areas, a project page, completing and reopening."""
import frappe
from frappe import _

from lifeos import archive, permissions
from lifeos.api import tasks as task_api
from lifeos.api.area import chat_open_counts, project_cards
from lifeos.api.timeline import index_rows
from lifeos.api.utils import area_filter, extra_columns, flag, page, std_clause, std_filters, std_order, summarise
from lifeos.api.utils import order_by as sort_order


SORTS = {"title": "p.title", "status": "field(p.status, 'Active', 'On Hold', 'Done', 'Dropped')", "target_date": "p.target_date is null, p.target_date",
	"area": "p.area", "creation": "p.creation"}


def where_clause(space, status=None, area=None, include_done=0):
	"""The WHERE of the project list. With no status: active and on hold projects that are not archived."""
	where, values = [], {}
	if status:
		where.append("p.status = %(status)s")
		values["status"] = status
		if status in ("Active", "On Hold"):
			where.append("p.is_archived = 0")
	elif not flag(include_done):
		where.append("p.is_archived = 0 and p.status in ('Active', 'On Hold')")
	if area:
		where.append(area_filter(space, area, "p.area", values))
	return "".join(" and " + w for w in where), values


def count(space, **filters):
	clause, values = where_clause(space, **filters)
	return frappe.db.sql(f"select count(*) from `tabLife Project` p where p.space=%(space)s {clause}", {"space": space, **values})[0][0]


@frappe.whitelist()
def list(space=None, include_done=0, status=None, area=None, sort=None, dir=None, start=0, page_length=100, filters=None, order_by=None, summary=None):
	"""Projects of a space, as a flat list and grouped by area. With no status: active and on hold ones; include_done=1 for every status.
	Filters: status (Active, On Hold, Done, Dropped), area (with its sub-areas). `total` is the number the filters match."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	if status and status not in ("Active", "On Hold", "Done", "Dropped"):
		frappe.throw(_("Unknown status."))
	where, values = where_clause(space, status, area, include_done)
	extra, values = std_clause("Life Project", filters, "p", values)
	where += extra
	if summary:
		return {"summary": summarise("Life Project", f"from `tabLife Project` p where p.space=%(space)s {where}", {"space": space, **values},
			"p", summary, start, page_length)}
	order = std_order("Life Project", order_by, "p", SORTS) or sort_order(sort, dir, SORTS, None)
	rows = project_cards(space, where, values, order, start, page_length)
	groups = {}
	for r in rows:
		groups.setdefault((r.area, r.area_name), []).append(r)
	out = [{"area": k[0], "area_name": k[1], "projects": v} for k, v in groups.items()]
	out.sort(key=lambda g: g["area_name"] or "")
	return {"space": space, "groups": out, "projects": rows, "total": frappe.db.sql(f"select count(*) from `tabLife Project` p where p.space=%(space)s {where}", {"space": space, **values})[0][0]}


@frappe.whitelist()
def get(project):
	"""A project page: its tasks, notes, documents and chats."""
	doc = permissions.get_doc_checked("Life Project", project)
	space = doc.space
	card = project_cards(space, "and p.name = %(name)s", {"name": doc.name})[0]
	card["notes_md"] = doc.notes_md
	arch = "" if doc.is_archived else "and is_archived = 0"
	t_arch = "" if doc.is_archived else "and t.is_archived = 0"
	v = {"project": doc.name}
	open_tasks = task_api.query(space, f"and t.project = %(project)s and t.status in ('Open', 'Doing', 'Waiting') {t_arch}", v, None, 0, 100)
	done_tasks = task_api.query(space, f"and t.project = %(project)s and t.status in ('Done', 'Dropped') {t_arch}", v, "t.completed_on desc", 0, 50)
	chats = index_rows(space, f"and project = %(project)s and kind = 'Chat' {arch}", v, page_length=30)
	counts = chat_open_counts([c.ref_name for c in chats])
	for c in chats:
		c["open_items"] = counts.get(c.ref_name, 0)
	inc = 1 if doc.is_archived else 0
	idx = lambda kind: frappe.db.sql(  # noqa: E731
		f"select count(*) from `tabLife Index` where space=%(space)s and project=%(project)s and kind=%(kind)s {arch}",
		{"space": space, "kind": kind, **v})[0][0]
	return {
		"counts": {"open_tasks": task_api.count(space, project=doc.name, include_archived=inc), "notes": idx("Note"),
			"documents": idx("Document"), "chats": idx("Chat")},
		"project": card, "space": space,
		"tasks": open_tasks, "done_tasks": done_tasks,
		"notes": index_rows(space, f"and project = %(project)s and kind = 'Note' {arch}", v, page_length=50),
		"documents": index_rows(space, f"and project = %(project)s and kind = 'Document' {arch}", v, page_length=50),
		"chats": chats,
		"goals": frappe.get_all("Life Goal", filters={"project": doc.name}, fields=["name", "title", "cycle", "outcome"], limit=20),
		"record_count": archive.project_record_count(doc.name),
	}


@frappe.whitelist()
def completion_info(project):
	"""How many records will move to the Archive when the project is completed. Shown in the confirm dialog."""
	doc = permissions.get_doc_checked("Life Project", project)
	return {"project": doc.name, "title": doc.title, "records": archive.project_record_count(doc.name)}


@frappe.whitelist(methods=["POST"])
def set_status(project, status):
	"""Change a project's status. Done or Dropped archives it at once with every record whose project points to it."""
	doc = permissions.get_doc_checked("Life Project", project, "write")
	if status not in ("Active", "On Hold", "Done", "Dropped"):
		frappe.throw(_("Unknown status."))
	records = archive.project_record_count(doc.name) if status in ("Done", "Dropped") else 0
	if status in ("Active", "On Hold") and doc.is_archived:
		archive.restore_project(doc)
		doc.reload()
	doc.status = status
	doc.save()
	return {"project": doc.name, "status": doc.status, "is_archived": frappe.db.get_value("Life Project", doc.name, "is_archived"), "archived_records": records}
