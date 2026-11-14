"""Archive and restore, and the Archive screen."""
import frappe

from lifeos import archive as rules
from lifeos import permissions
from lifeos.api.timeline import index_rows
from lifeos.api.utils import flag, names_map, page


@frappe.whitelist(methods=["POST"])
def set(doctype, name, archived=1):
	"""Archive or restore one record. For a project, its records follow."""
	permissions.require_login()
	return rules.set_archived(doctype, name, flag(archived), "Manual")


@frappe.whitelist(methods=["POST"])
def restore(doctype, name):
	"""Bring an archived record back. Restoring a project restores the records archived with it."""
	permissions.require_login()
	return rules.set_archived(doctype, name, False)


@frappe.whitelist()
def list(space=None, area=None, start=0, page_length=50):
	"""Archived records by area, newest first, plus archived projects."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = "and is_archived = 1 and kind != 'Task Done'", {}
	if area:
		where += " and area = %(area)s"
		values["area"] = area
	rows = index_rows(space, where, values, order="area asc, record_date desc", start=start, page_length=page_length)
	reasons = {}
	for dt in {r.ref_doctype for r in rows}:
		names = [r.ref_name for r in rows if r.ref_doctype == dt]
		if frappe.get_meta(dt).has_field("archive_reason"):
			for n, reason, on in frappe.get_all(dt, filters={"name": ("in", names)}, fields=["name", "archive_reason", "archived_on"], as_list=True):
				reasons[(dt, n)] = (reason, str(on) if on else None)
	groups = {}
	for r in rows:
		r["archive_reason"], r["archived_on"] = reasons.get((r.ref_doctype, r.ref_name), ("", None))
		groups.setdefault((r.area or "", r.area_name or "Unfiled"), []).append(r)
	projects = frappe.get_all("Life Project", filters={"space": space, "is_archived": 1},
		fields=["name", "title", "area", "status", "archived_on"], order_by="archived_on desc", limit=100)
	areas = names_map("Life Area", [p.area for p in projects], "area_name")
	for p in projects:
		p["area_name"] = areas.get(p.area)
		p["archived_on"] = str(p.archived_on) if p.archived_on else None
	return {"groups": [{"area": k[0], "area_name": k[1], "records": v} for k, v in groups.items()], "projects": projects,
		"count": len(rows), "has_more": len(rows) == page_length}
