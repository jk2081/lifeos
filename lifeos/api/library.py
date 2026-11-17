"""Library: notes in a tree under their area and project."""
import builtins

import frappe
from frappe import _

from lifeos import links, permissions
from lifeos.api.utils import area_filter, extra_columns, flag, names_map, page, parse, std_clause, std_filters, std_order, summarise
from lifeos.api.utils import order_by as sort_order


@frappe.whitelist(methods=["GET"])
def tree(space: str | None = None, include_archived: bool | int | None = 0, collection: str | None = "My notes"):
	"""Every note of a space with what the tree needs: title, parent, area and project. At most 100 per call would hide notes,
	so the tree returns light rows only and is capped at 2,000. collection: My notes (default), Wiki, or "all"."""
	space = permissions.resolve_space(space)
	filters = {"space": space}
	if collection and collection != "all":
		filters["collection"] = collection
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


SORTS = {"title": "x.title", "record_date": "x.record_date", "modified": "x.modified"}


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, area: str | None = None, project: str | None = None, tag: str | None = None, include_archived: bool | int | None = 0, sort: str | None = None, dir: str | None = None, start: int | None = 0,
		page_length: int | None = 50, filters: str | builtins.list | dict | None = None, order_by: str | None = None, summary: str | dict | None = None, collection: str | None = "My notes"):
	"""Notes of a space as a flat list, newest first. Reads Life Index.
	Filters: area (with its sub-areas, or "none"), project (a project, or "none" for reference notes), tag,
	collection (My notes, the default; Wiki; or "all").
	`total` is the number of notes the filters match."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = ["x.space = %(space)s", "x.kind = 'Note'"], {"space": space}
	if collection and collection != "all":
		where.append("x.collection = %(collection)s")
		values["collection"] = collection
	if not flag(include_archived):
		where.append("x.is_archived = 0")
	if area:
		where.append(area_filter(space, area, "x.area", values))
	if project:
		where.append("x.project = %(project)s")
		values["project"] = "" if project == "none" else project
	if tag:
		where.append("exists (select 1 from `tabLife Tag Link` tl where tl.parent = x.ref_name and tl.parenttype = 'Life Note' and tl.tag = %(tag)s)")
		values["tag"] = tag
	conds, values = std_filters("Life Index", filters, "x", values)
	clause = " and ".join(where + conds)
	if summary:
		return {"summary": summarise("Life Index", f"from `tabLife Index` x where {clause}", values, "x", summary, start, page_length)}
	order = std_order("Life Index", order_by, "x", SORTS) or sort_order(sort, dir, SORTS, "x.modified desc")
	rows = frappe.db.sql(
		f"""select x.ref_name as name, x.title, x.area, x.project, x.record_date, x.modified, x.is_archived from `tabLife Index` x
		where {clause} order by {order}, x.ref_name limit %(start)s, %(len)s""",
		{**values, "start": start, "len": page_length}, as_dict=True)
	total = frappe.db.sql(f"select count(*) from `tabLife Index` x where {clause}", values)[0][0]
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	projects = names_map("Life Project", [r.project for r in rows], "title")
	tags = {}
	if rows:
		for parent, name in frappe.db.sql(
			"select l.parent, g.tag_name from `tabLife Tag Link` l join `tabLife Tag` g on g.name = l.tag where l.parenttype='Life Note' and l.parent in %s",
			([r.name for r in rows],)):
			tags.setdefault(parent, []).append(name)
	for r in rows:
		r["area_name"], r["project_title"], r["tags"] = areas.get(r.area), projects.get(r.project), tags.get(r.name, [])
		r["record_date"] = str(r.record_date) if r.record_date else None
		r["modified"] = str(r.modified)[:10]
	return {"space": space, "notes": rows, "total": total}


def mark_opened(doc):
	"""Record that a person opened a note: on the note and its index row, without touching `modified`."""
	if permissions.is_agent():
		return
	day = frappe.utils.getdate(frappe.utils.today())
	if doc.get("last_opened_on") and frappe.utils.getdate(doc.last_opened_on) == day:
		return
	frappe.db.set_value("Life Note", doc.name, "last_opened_on", day, update_modified=False)
	frappe.db.sql("update `tabLife Index` set last_opened_on=%s where ref_doctype='Life Note' and ref_name=%s", (day, doc.name))


@frappe.whitelist(methods=["POST"])
def get(note: str):
	"""One note with its links resolved to current titles. A person opening it sets its last_opened_on (UX fixes, set 5)."""
	doc = permissions.get_doc_checked("Life Note", note)
	mark_opened(doc)
	return {
		"name": doc.name, "space": doc.space, "title": doc.title, "content_md": doc.content_md or "", "parent_note": doc.parent_note,
		"parent_title": frappe.db.get_value("Life Note", doc.parent_note, "title") if doc.parent_note else None,
		"area": doc.area, "area_name": frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None,
		"project": doc.project, "project_title": frappe.db.get_value("Life Project", doc.project, "title") if doc.project else None,
		"also_in": [r.area for r in doc.also_in], "tag_ids": [r.tag for r in doc.tags], "is_archived": doc.is_archived,
		"inbox_item": doc.inbox_item, "modified": str(doc.modified)[:19], "owner": doc.owner, "version": version_of(doc),
		"collection": doc.collection or "My notes", "summary": doc.summary, "is_rules": doc.is_rules,
		"sources": [{"doctype": r.source_doctype, "name": r.source_name, "title": links.title_of(r.source_doctype, r.source_name)} for r in doc.sources],
		"links": links.outgoing(doc),
		"children": frappe.get_all("Life Note", filters={"parent_note": doc.name, "is_archived": 0}, fields=["name", "title"], order_by="title", limit=100),
		"versions": frappe.db.count("Version", {"ref_doctype": "Life Note", "docname": doc.name}),
	}


def version_of(doc):
	"""A token that changes with every save: the modified timestamp to the microsecond."""
	return str(doc.modified)


@frappe.whitelist(methods=["POST"])
def save(note: str | None = None, space: str | None = None, title: str | None = None, content_md: str | None = None, area: str | None = None, project: str | None = None, parent_note: str | None = None,
		also_in: str | builtins.list | None = None, tag_ids: str | builtins.list | None = None, base_version: str | None = None, summary: str | None = None, collection: str | None = None):
	"""Create or change a note. On save its [[Title]] links are parsed and stored in Life Link.
	`base_version` is the `version` the editor started from. If the note changed since (an agent's edit, another device),
	nothing is saved and the answer is {"conflict": true, "current": <the note as it is now>}."""
	if note:
		doc = permissions.get_doc_checked("Life Note", note, "write")
		if base_version and base_version != version_of(doc):
			return {"conflict": True, "current": get(doc.name)}
	else:
		space = permissions.resolve_space(space, write=True)
		doc = frappe.get_doc({"doctype": "Life Note", "space": space})
	if title is not None:
		if not title.strip():
			frappe.throw(_("A note needs a title."))
		doc.title = title.strip()
	before_md = doc.content_md or ""
	if content_md is not None:
		doc.content_md = content_md
	if summary is not None:
		doc.summary = summary
	if collection and not note:
		doc.collection = collection  # a new page straight into the wiki; moving an existing page is wiki.move
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
	if doc.collection == "Wiki":
		# every change to a wiki page, by anyone, is logged with the text before and after (UX fixes, set 4)
		from lifeos.api import wiki

		if note:
			wiki.person_edited(doc, before_md)
		else:
			wiki.log_change(doc, "Created", "", doc.content_md)
	return get(doc.name)


@frappe.whitelist(methods=["GET"])
def versions(note: str):
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
