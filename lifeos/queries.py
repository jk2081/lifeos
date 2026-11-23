"""Link search for the filing DocTypes, used by every picker and filter (`standard_queries` in hooks.py).

Frappe's own link search lists archived areas, finished goals and the areas of every space the person belongs to.
This one keeps to active records, and to one space when the filters name it. The front end (framework/linkScope.js)
adds the current space to every search for these DocTypes. Filters it understands:
  space             only this space
  include_archived  also archived records (and finished goals), labelled "(archived)" or with their outcome
  goal_outcome      goals: a list of outcomes to allow instead of "In Progress"
Any other plain filter on a real field is applied as given.
"""
import json

import frappe

SCOPED = {
	"Life Area": "area_name", "Life Habit": "title",
	"Life Goal": "title",
}


@frappe.whitelist(methods=["GET"])
@frappe.validate_and_sanitize_search_inputs
def link_query(doctype: str, txt: str, searchfield: str | None, start: int, page_len: int, filters: str | dict | list | None, **kwargs):
	if doctype not in SCOPED:
		frappe.throw(frappe._("Not a filing DocType"), title=frappe._("Not a filing DocType"))
	field = SCOPED[doctype]
	if isinstance(filters, str):
		filters = json.loads(filters or "{}")
	if isinstance(filters, list):
		filters = {f[1] if len(f) > 3 else f[0]: (f[-1] if (f[-2] if len(f) > 2 else "=") == "=" else [f[-2], f[-1]]) for f in filters}
	filters = dict(filters or {})
	include_archived = frappe.utils.cint(filters.pop("include_archived", 0))
	outcomes = filters.pop("goal_outcome", None)
	meta = frappe.get_meta(doctype)
	where = {k: v for k, v in filters.items() if meta.has_field(k) or k == "name"}
	if doctype == "Life Goal" and outcomes:
		# a list on a state tab that holds closed goals: exactly those outcomes, archived or not
		where["outcome"] = ["in", outcomes]
	elif not include_archived:
		where["is_archived"] = 0
		if doctype == "Life Goal":
			where["outcome"] = "In Progress"
	if doctype in ("Life Area", "Life Goal"):  # areas switched off, with their parts and goals, are not offered (issue 11)
		from lifeos import areas, permissions

		spaces = [where["space"]] if isinstance(where.get("space"), str) else list(permissions.user_spaces())
		off = [n for s in spaces for n in areas.off(s)]
		if off:
			where["name" if doctype == "Life Area" else "area"] = ["not in", off]
	or_filters = {field: ["like", f"%{txt}%"], "name": ["like", f"%{txt}%"]} if txt else None
	extra = ["parent_area"] if doctype == "Life Area" else (["outcome", "horizon"] if doctype == "Life Goal" else [])
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
		closed = r.is_archived or (doctype == "Life Goal" and r.outcome != "In Progress")
		if include_archived and closed:
			label += " (archived)" if r.is_archived else f" ({(r.outcome or '').lower()})"
		desc = (parents.get(r.parent_area) or "") if doctype == "Life Area" else (r.horizon or "") if doctype == "Life Goal" else ""
		out.append((r.name, label, desc) if desc else (r.name, label))
	return out
