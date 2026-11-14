"""Projects: the list across areas, a project page, completing and reopening."""
import frappe
from frappe import _

from lifeos import archive, permissions
from lifeos.api import tasks as task_api
from lifeos.api.area import chat_open_counts, project_cards
from lifeos.api.timeline import index_rows
from lifeos.api.utils import flag


@frappe.whitelist()
def list(space=None, include_done=0):
	"""Every active project of a space, grouped by area. On hold projects are included; done ones on request."""
	space = permissions.resolve_space(space)
	where = "" if flag(include_done) else "and p.is_archived = 0 and p.status in ('Active', 'On Hold')"
	rows = project_cards(space, where, {})
	groups = {}
	for r in rows:
		groups.setdefault((r.area, r.area_name), []).append(r)
	out = [{"area": k[0], "area_name": k[1], "projects": v} for k, v in groups.items()]
	out.sort(key=lambda g: g["area_name"] or "")
	return {"space": space, "groups": out, "total": len(rows)}


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
	return {
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
