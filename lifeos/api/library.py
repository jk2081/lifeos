"""Library: notes in a tree under their area and project."""
import frappe
from frappe import _

from lifeos import links, permissions
from lifeos.api.utils import flag, names_map, parse


@frappe.whitelist()
def tree(space=None, include_archived=0):
	"""Every note of a space with what the tree needs: title, parent, area and project. At most 100 per call would hide notes,
	so the tree returns light rows only and is capped at 2,000."""
	space = permissions.resolve_space(space)
	filters = {"space": space}
	if not flag(include_archived):
		filters["is_archived"] = 0
	notes = frappe.get_all("Life Note", filters=filters, fields=["name", "title", "parent_note", "area", "project", "modified", "is_archived"],
		order_by="title asc", limit=2000)
	areas = frappe.get_all("Life Area", filters={"space": space}, fields=["name", "area_name", "parent_area"], order_by="sort_order, area_name", limit=1000)
	projects = names_map("Life Project", [n.project for n in notes], "title")
	for n in notes:
		n["project_title"] = projects.get(n.project)
		n["modified"] = str(n.modified)[:10]
	return {"space": space, "notes": notes, "areas": areas}


@frappe.whitelist()
def get(note):
	"""One note with its links resolved to current titles."""
	doc = permissions.get_doc_checked("Life Note", note)
	return {
		"name": doc.name, "space": doc.space, "title": doc.title, "content_md": doc.content_md or "", "parent_note": doc.parent_note,
		"parent_title": frappe.db.get_value("Life Note", doc.parent_note, "title") if doc.parent_note else None,
		"area": doc.area, "area_name": frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None,
		"project": doc.project, "project_title": frappe.db.get_value("Life Project", doc.project, "title") if doc.project else None,
		"also_in": [r.area for r in doc.also_in], "tag_ids": [r.tag for r in doc.tags], "is_archived": doc.is_archived,
		"inbox_item": doc.inbox_item, "modified": str(doc.modified)[:19], "owner": doc.owner,
		"links": links.outgoing(doc),
		"children": frappe.get_all("Life Note", filters={"parent_note": doc.name, "is_archived": 0}, fields=["name", "title"], order_by="title", limit=100),
		"versions": frappe.db.count("Version", {"ref_doctype": "Life Note", "docname": doc.name}),
	}


@frappe.whitelist(methods=["POST"])
def save(note=None, space=None, title=None, content_md=None, area=None, project=None, parent_note=None, also_in=None, tag_ids=None):
	"""Create or change a note. On save its [[Title]] links are parsed and stored in Life Link."""
	if note:
		doc = permissions.get_doc_checked("Life Note", note, "write")
	else:
		space = permissions.resolve_space(space, write=True)
		doc = frappe.get_doc({"doctype": "Life Note", "space": space})
	if title is not None:
		if not title.strip():
			frappe.throw(_("A note needs a title."))
		doc.title = title.strip()
	if content_md is not None:
		doc.content_md = content_md
	for field, value in (("area", area), ("project", project), ("parent_note", parent_note)):
		if value is not None:
			doc.set(field, value or None)
	if also_in is not None:
		doc.set("also_in", [{"area": a} for a in parse(also_in, [])])
	if tag_ids is not None:
		doc.set("tags", [{"tag": t} for t in parse(tag_ids, [])])
	if doc.parent_note and doc.parent_note == doc.name:
		frappe.throw(_("A note cannot be its own parent."))
	doc.save() if note else doc.insert()
	return get(doc.name)


@frappe.whitelist()
def versions(note):
	"""Saved versions of a note, from Frappe's document versioning."""
	doc = permissions.get_doc_checked("Life Note", note)
	rows = frappe.get_all("Version", filters={"ref_doctype": "Life Note", "docname": doc.name}, fields=["name", "owner", "creation", "data"],
		order_by="creation desc", limit=30)
	out = []
	for r in rows:
		data = frappe.parse_json(r.data) or {}
		changed = [c[0] for c in data.get("changed", [])]
		old = next((c[1] for c in data.get("changed", []) if c[0] == "content_md"), None)
		out.append({"name": r.name, "by": r.owner, "on": str(r.creation)[:16], "changed": changed, "previous_content": old})
	return out
