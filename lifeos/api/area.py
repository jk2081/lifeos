"""Area pages and the area tree."""
import frappe
from frappe import _

from lifeos import journal, permissions
from lifeos.api import tasks as task_api
from lifeos.api.timeline import index_rows
from lifeos.api.utils import descendants, flag, names_map


def project_cards(space, where, values, order=None, start=0, page_length=100):
	rows = frappe.db.sql(
		f"""select p.name, p.title, p.status, p.outcome, p.target_date, p.area, p.is_archived, p.completed_on,
			(select count(*) from `tabLife Task` t where t.project = p.name and t.status != 'Carried') as tasks_total,
			(select count(*) from `tabLife Task` t where t.project = p.name and t.status in ('Done', 'Dropped')) as tasks_done,
			(select t.waiting_on from `tabLife Task` t where t.project = p.name and t.status = 'Waiting' and t.is_archived = 0 limit 1) as waiting_on
		from `tabLife Project` p where p.space = %(space)s {where}
		order by field(p.status, 'Active', 'On Hold', 'Done', 'Dropped'), p.creation asc limit 100""",
		{"space": space, **values}, as_dict=True)
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	for r in rows:
		r["area_name"] = areas.get(r.area)
		r["target_date"] = str(r.target_date) if r.target_date else None
	return rows


def chat_open_counts(names):
	if not names:
		return {}
	return dict(frappe.db.sql(
		"select parent, count(*) from `tabLife Chat Open Item` where parenttype='Life Chat Log' and status='Open' and parent in %s group by parent",
		(names,)))


@frappe.whitelist()
def get(area, include_archived=0):
	"""An area page: sub-areas, active projects, open tasks, reference notes, documents, recent chats with their open items,
	the last 20 timeline entries, the goals of the active cycle, and records from other areas that are also filed here."""
	doc = permissions.get_doc_checked("Life Area", area)
	space = doc.space
	ids = descendants(space, doc.name)
	v = {"ids": ids}
	arch = "" if flag(include_archived) else "and is_archived = 0"

	subs = frappe.get_all("Life Area", filters={"space": space, "parent_area": doc.name, "is_archived": 0}, fields=["name", "area_name"], order_by="sort_order, area_name")
	projects = project_cards(space, "and p.area in %(ids)s and p.is_archived = 0 and p.status in ('Active', 'On Hold')", v)
	# the same filter as the Tasks screen, so the count here equals the list it links to
	t_clause, t_values = task_api.where_clause(space, area=doc.name)
	tasks = task_api.query(space, t_clause, t_values, None, 0, 8)
	open_tasks = task_api.count(space, area=doc.name)

	counts = dict(frappe.db.sql(
		f"select kind, count(*) from `tabLife Index` where space=%(space)s and area in %(ids)s {arch} group by kind", {"space": space, **v}))
	notes = index_rows(space, f"and area in %(ids)s and kind = 'Note' and project = '' {arch}", v, page_length=6)
	reference_notes = frappe.db.sql(
		f"select count(*) from `tabLife Index` where space=%(space)s and area in %(ids)s and kind='Note' and project = '' {arch}", {"space": space, **v})[0][0]
	documents = index_rows(space, f"and area in %(ids)s and kind = 'Document' {arch}", v, page_length=6)
	chats = index_rows(space, f"and area in %(ids)s and kind = 'Chat' {arch}", v, page_length=5)
	open_items = chat_open_counts([c.ref_name for c in chats])
	for c in chats:
		c["open_items"] = open_items.get(c.ref_name, 0)
	timeline = index_rows(space, f"and area in %(ids)s {arch}", v, page_length=20)

	like = " or ".join(f"also_in_csv like %(like{i})s" for i in range(len(ids)))
	like_values = {f"like{i}": f"%,{a},%" for i, a in enumerate(ids)}
	references = index_rows(space, f"and also_in_csv != '' and ({like}) and area not in %(ids)s and kind != 'Task Done' {arch}", {**v, **like_values}, page_length=20)

	goals = []
	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, "name")
	if cycle:
		grid = journal.grid(cycle)
		goals = [{"name": g["name"], "title": g["title"], "percent": g["percent"], "actions": len(g["actions"])} for g in grid["goals"] if g["area"] in ids]

	parent = None
	if doc.parent_area:
		parent = {"name": doc.parent_area, "area_name": frappe.db.get_value("Life Area", doc.parent_area, "area_name")}
	return {
		"area": {"name": doc.name, "area_name": doc.area_name, "space": space, "parent": parent, "is_archived": doc.is_archived},
		"sub_areas": subs, "projects": projects, "tasks": tasks, "notes": notes, "documents": documents, "chats": chats,
		"timeline": timeline, "references": references, "goals": goals,
		"counts": {"projects": sum(1 for p in projects if p.status == "Active"), "open_tasks": open_tasks, "notes": counts.get("Note", 0),
			"all_projects": len(projects), "reference_notes": reference_notes, "documents": counts.get("Document", 0), "chats": counts.get("Chat", 0)},
	}


@frappe.whitelist()
def tree(space=None, include_archived=0):
	"""Every area of a space with its parent and small counts, for the Areas screen and for pickers."""
	space = permissions.resolve_space(space)
	filters = {"space": space}
	if not flag(include_archived):
		filters["is_archived"] = 0
	areas = frappe.get_all("Life Area", filters=filters, fields=["name", "area_name", "parent_area", "sort_order", "is_archived"],
		order_by="sort_order asc, area_name asc", limit=1000)
	# each number is counted the way the list it links to is filtered: the area with its sub-areas
	kids = {}
	for a in areas:
		kids.setdefault(a.parent_area, []).append(a.name)

	def below(name):
		out = [name]
		for k in kids.get(name, []):
			out.extend(below(k))
		return out

	direct_projects = dict(frappe.db.sql(
		"select area, count(*) from `tabLife Project` where space=%s and status='Active' and is_archived=0 group by area", space))
	direct_notes = dict(frappe.db.sql("select area, count(*) from `tabLife Index` where space=%s and kind='Note' and is_archived=0 group by area", space))
	for a in areas:
		ids = below(a.name)
		a["open_tasks"] = task_api.count(space, area=a.name)
		a["projects"] = sum(direct_projects.get(i, 0) for i in ids)
		a["notes"] = sum(direct_notes.get(i, 0) for i in ids)
	return {"space": space, "areas": areas,
		"tags": frappe.get_all("Life Tag", filters={"space": space}, fields=["name", "tag_name"], order_by="tag_name", limit=500),
		"unfiled_tasks": task_api.count(space, area="none")}
