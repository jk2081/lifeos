"""Link search for the filing DocTypes, used by every picker and filter (`standard_queries` in hooks.py).

Frappe's own link search lists archived areas, finished projects and the areas of every space the person belongs to.
This one keeps to active records, and to one space when the filters name it. The front end (framework/linkScope.js)
adds the current space to every search for these DocTypes. Filters it understands:
  space             only this space
  include_archived  also archived records (and finished projects), labelled "(archived)"; the Archive screen asks for it
  project_status    projects: a list of statuses to allow instead of "not Done or Dropped"
Any other plain filter on a real field is applied as given.
"""
import json

import frappe

SCOPED = {
	"Life Area": "area_name", "Life Tag": "tag_name", "Life Habit": "title", "Life Dimension": "dimension_name",
	"Life Project": "title",
}
CLOSED_PROJECT = ("Done", "Dropped")


@frappe.whitelist(methods=["GET"])
@frappe.validate_and_sanitize_search_inputs
def link_query(doctype: str, txt: str, searchfield: str | None, start: int, page_len: int, filters: str | dict | list | None, **kwargs):
	if doctype not in SCOPED:
		frappe.throw(frappe._("Not a filing DocType"))
	field = SCOPED[doctype]
	if isinstance(filters, str):
		filters = json.loads(filters or "{}")
	if isinstance(filters, list):
		filters = {f[1] if len(f) > 3 else f[0]: (f[-1] if (f[-2] if len(f) > 2 else "=") == "=" else [f[-2], f[-1]]) for f in filters}
	filters = dict(filters or {})
	include_archived = frappe.utils.cint(filters.pop("include_archived", 0))
	statuses = filters.pop("project_status", None)
	meta = frappe.get_meta(doctype)
	where = {k: v for k, v in filters.items() if meta.has_field(k) or k == "name"}
	if doctype == "Life Project" and statuses:
		# a list on a state tab that holds closed projects: exactly those statuses, archived or not
		where["status"] = ["in", statuses]
	elif not include_archived:
		where["is_archived"] = 0
		if doctype == "Life Project":
			where["status"] = ["not in", CLOSED_PROJECT]
	or_filters = {field: ["like", f"%{txt}%"], "name": ["like", f"%{txt}%"]} if txt else None
	extra = ["parent_area"] if doctype == "Life Area" else (["status"] if doctype == "Life Project" else [])
	rows = frappe.get_list(doctype, filters=where, or_filters=or_filters, fields=["name", field, "is_archived", "space", *extra],
		order_by=f"is_archived asc, {'sort_order asc, ' if meta.has_field('sort_order') else ''}{field} asc",
		start=start, page_length=page_len)
	parents = {}
	if doctype == "Life Area":
		ids = [r.parent_area for r in rows if r.parent_area]
		parents = dict(frappe.get_all("Life Area", filters={"name": ["in", ids]}, fields=["name", "area_name"], as_list=True)) if ids else {}
	out = []
	for r in rows:
		label = r.get(field) or r.name
		closed = r.is_archived or (doctype == "Life Project" and r.status in CLOSED_PROJECT)
		if include_archived and closed:
			label += " (archived)" if r.is_archived else f" ({r.status.lower()})"
		desc = parents.get(r.parent_area) or "" if doctype == "Life Area" else ""
		out.append((r.name, label, desc) if desc else (r.name, label))
	return out
