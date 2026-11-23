"""Library: notes in a tree under their area and goal."""
import builtins

import frappe
from frappe import _
from frappe.query_builder import Order

from lifeos.library import links
from lifeos import permissions
from lifeos.api.timeline import index_where
from lifeos.api.utils import area_criterion, count_where, filter_criteria, flag, group_summary, in_area, lens_area, list_query, names_map, order_terms, page, parse, sort_terms


@frappe.whitelist(methods=["GET"])
def tree(space: str | None = None, include_archived: bool | int | None = 0, collection: str | None = "My notes", area: str | None = None):
	"""Every note of a space with what the tree needs: title, parent, area and goal. At most 100 per call would hide notes,
	so the tree returns light rows only and is capped at 2,000. collection: My notes (default), Wiki, or "all".
	`area` is the lens: notes of the area, its sub-areas or listing one in "also in"."""
	space = permissions.resolve_space(space)
	filters = {"space": space}
	if collection and collection != "all":
		filters["collection"] = collection
	if not flag(include_archived):
		filters["is_archived"] = 0
	if permissions.vault_hidden(space):
		filters["is_sensitive"] = 0
	notes = frappe.get_list("Life Note", filters=filters, fields=["name", "title", "parent_note", "area", "goal", "modified", "is_archived"],
		order_by="title asc", limit=2000)
	area = lens_area(area)
	if area:
		keep = in_area(space, area, "Life Note", [n.name for n in notes])
		notes = [n for n in notes if n.name in keep]
	areas = frappe.get_list("Life Area", filters={"space": space}, fields=["name", "area_name", "parent_area"], order_by="sort_order, area_name", limit=1000)
	goals = names_map("Life Goal", [n.goal for n in notes], "title")
	for n in notes:
		n["goal_title"] = goals.get(n.goal)
		n["modified"] = str(n.modified)[:10]
	return {"space": space, "notes": notes, "areas": areas}


SORTS = {k: (lambda x, k=k: [x[k]]) for k in ("title", "record_date", "modified")}


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, area: str | None = None, goal: str | None = None, include_archived: bool | int | None = 0, sort: str | None = None, dir: str | None = None, start: int | None = 0,
		page_length: int | None = 50, filters: str | builtins.list | dict | None = None, order_by: str | None = None, summary: str | dict | None = None, collection: str | None = "My notes"):
	"""Notes of a space as a flat list, newest first. Reads Life Index. A photographed journal page is a note too.
	Filters: area (with its sub-areas, or "none"), goal (a goal, or "none" for reference notes),
	collection (My notes, the default; Wiki; or "all").
	`total` is the number of notes the filters match."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	x = frappe.qb.DocType("Life Index")
	where = [x.kind == "Note"]
	if collection and collection != "all":
		where.append(x.collection == collection)
	if not flag(include_archived):
		where.append(x.is_archived == 0)
	if area:
		where.append(area_criterion(space, area, x, also_in="index"))
	if goal:
		where.append(x.goal == ("" if goal == "none" else goal))
	where = index_where(space, where + filter_criteria("Life Index", filters, x))
	if summary:
		return {"summary": group_summary("Life Index", where, summary, start, page_length)}
	terms = order_terms("Life Index", order_by, x, SORTS) or sort_terms(sort, dir, SORTS, x, [(x.modified, Order.desc)])
	fields = ["area", "goal", "record_date", "modified", "is_archived", "collection", "vault_locked"]
	rows = list_query("Life Index", ["title", *fields], where, [*terms, (x.ref_name, Order.asc)])
	rows = rows.select(x.ref_name.as_("name"), x.kind.as_("kind")).limit(page_length).offset(start).run(as_dict=True)
	total = count_where("Life Index", where)
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	goals = names_map("Life Goal", [r.goal for r in rows], "title")
	for r in rows:
		r["area_name"], r["goal_title"] = areas.get(r.area), goals.get(r.goal)
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
	frappe.db.set_value("Life Index", {"ref_doctype": "Life Note", "ref_name": doc.name}, "last_opened_on", day, update_modified=False)


def _visible_title(note, space):
	"""A related note's title, unless it is sensitive and the user is kept from sensitive items."""
	row = frappe.db.get_value("Life Note", note, ["title", "is_sensitive"], as_dict=True)
	if not row or (row.is_sensitive and permissions.vault_hidden(space)):
		return None
	return row.title


@frappe.whitelist(methods=["POST"])
def get(note: str):
	"""One note with its links resolved to current titles. A person opening it sets its last_opened_on (UX fixes, set 5)."""
	doc = permissions.get_doc_checked("Life Note", note)
	mark_opened(doc)
	return {
		"name": doc.name, "space": doc.space, "title": doc.title, "content_md": doc.content_md or "", "parent_note": doc.parent_note,
		"is_sensitive": doc.is_sensitive, "image": doc.image, "page_date": str(doc.page_date) if doc.page_date else None,
		"parent_title": _visible_title(doc.parent_note, doc.space) if doc.parent_note else None,
		"area": doc.area, "area_name": frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None,
		"goal": doc.goal, "goal_title": frappe.db.get_value("Life Goal", doc.goal, "title") if doc.goal else None,
		"also_in": [r.area for r in doc.also_in], "is_archived": doc.is_archived,
		"inbox_item": doc.inbox_item, "modified": str(doc.modified)[:19], "owner": doc.owner, "version": version_of(doc),
		"collection": doc.collection or "My notes", "summary": doc.summary, "is_rules": doc.is_rules,
		"sources": [{"doctype": r.source_doctype, "name": r.source_name, "title": links.title_of(r.source_doctype, r.source_name),
			"added_on": str(r.added_on) if r.get("added_on") else None} for r in doc.sources],
		"links": links.outgoing(doc),
		"children": frappe.get_list("Life Note", filters={"parent_note": doc.name, "is_archived": 0,
			**({"is_sensitive": 0} if permissions.vault_hidden(doc.space) else {})}, fields=["name", "title"], order_by="title", limit=100),
		"versions": frappe.db.count("Version", {"ref_doctype": "Life Note", "docname": doc.name}),
	}


def version_of(doc):
	"""A token that changes with every save: the modified timestamp to the microsecond."""
	return str(doc.modified)


@frappe.whitelist(methods=["POST"])
def save(note: str | None = None, space: str | None = None, title: str | None = None, content_md: str | None = None, area: str | None = None, goal: str | None = None, parent_note: str | None = None,
		also_in: str | builtins.list | None = None, base_version: str | None = None, summary: str | None = None, collection: str | None = None):
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
			frappe.throw(_("A note needs a title."), title=_("Note needs a title"))
		doc.title = title.strip()
	before_md = doc.content_md or ""
	if content_md is not None:
		doc.content_md = content_md
	if summary is not None:
		doc.summary = summary
	if collection and not note:
		doc.collection = collection  # a new page straight into the wiki; moving an existing page is wiki.move
	for field, value in (("area", area), ("goal", goal), ("parent_note", parent_note)):
		if value is not None:
			doc.set(field, value or None)
	if also_in is not None:
		doc.set("also_in", [{"area": a} for a in parse(also_in, [])])
	if doc.parent_note and doc.parent_note == doc.name:
		frappe.throw(_("A note cannot be its own parent."), title=_("Note cannot be its own parent"))
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
	rows = frappe.get_all("Version", filters={"ref_doctype": "Life Note", "docname": doc.name}, fields=["name", "owner", "creation", "data"],  # system: the note's own permission is checked above
		order_by="creation desc", limit=30)
	out = []
	for r in rows:
		data = frappe.parse_json(r.data) or {}
		changed = [c[0] for c in data.get("changed", [])]
		old = next((c[1] for c in data.get("changed", []) if c[0] == "content_md"), None)
		out.append({"name": r.name, "by": r.owner, "on": str(r.creation)[:16], "changed": changed, "previous_content": old})
	return out


@frappe.whitelist(methods=["POST"])
def set_sensitive(doctype: str, name: str, sensitive: bool | int = 1):
	"""Mark a capture or note sensitive, or unmark it (UX fixes, set 6). Anyone who may edit it may mark it; only the space's
	owner may unmark it. A sensitive item follows the Vault rules. People only: an agent cannot change who sees what."""
	if permissions.is_agent():
		frappe.throw(_("Agents cannot mark or unmark sensitive items."), frappe.PermissionError, title=_("Agents cannot mark sensitive"))
	if doctype not in permissions.SENSITIVE_DOCTYPES:
		frappe.throw(_("Only captures and notes can be marked sensitive."), title=_("Cannot be marked sensitive"))
	doc = permissions.get_doc_checked(doctype, name, "write")
	doc.is_sensitive = 1 if flag(sensitive) else 0
	doc.flags.keep_touched = True
	doc.save()
	return {"doctype": doctype, "name": doc.name, "is_sensitive": doc.is_sensitive}
