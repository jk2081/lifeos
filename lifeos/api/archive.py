"""Archive and restore, and the Archive screen."""
import frappe

from lifeos import archive as rules
from lifeos import permissions
from lifeos.api.timeline import index_rows
from lifeos.api.utils import area_filter, flag, names_map, order_by, page


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


TYPES = ("Life Task", "Life Note", "Life Inbox Item", "Life Chat Log", "Life Vault Document", "Life Journal Page")
SORTS = {"title": "title", "kind": "kind", "record_date": "record_date", "area": "area"}


@frappe.whitelist()
def list(space=None, area=None, start=0, page_length=50, doctype=None, reason=None, archived_from=None, archived_to=None, sort=None, dir=None):
	"""Archived records, grouped by area, plus archived projects.
	Filters: doctype (the record type), area (with its sub-areas, or "none"), reason (Auto, Manual, Project),
	archived_from and archived_to on the day it was archived. `total` is the number of records the filters match."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = "and is_archived = 1 and kind != 'Task Done'", {}
	if area:
		where += " and " + area_filter(space, area, "area", values)
	if doctype:
		where += " and ref_doctype = %(doctype)s"
		values["doctype"] = doctype
	if reason or archived_from or archived_to:
		# the reason and the day live on the records themselves, so each type is checked in its own table
		parts = []
		for dt in rules.AUTO_DOCTYPES + tuple(t for t in TYPES if t not in rules.AUTO_DOCTYPES):
			if not frappe.get_meta(dt).has_field("archive_reason"):
				continue
			cond = "x.name = ref_name"
			if reason:
				cond += " and x.archive_reason = %(reason)s"
			if archived_from:
				cond += " and x.archived_on >= %(archived_from)s"
			if archived_to:
				cond += " and x.archived_on <= %(archived_to)s"
			parts.append(f"(ref_doctype = '{dt}' and exists (select 1 from `tab{dt}` x where {cond}))")
		where += " and (" + (" or ".join(parts) or "1=0") + ")"
		values.update({"reason": reason, "archived_from": archived_from, "archived_to": archived_to})
	order = order_by(sort, dir, SORTS, None)
	rows = index_rows(space, where, values, order=(order + ", modified desc") if order else "area asc, record_date desc, modified desc",
		start=start, page_length=page_length)
	total = frappe.db.sql(f"select count(*) from `tabLife Index` where space=%(space)s {where}", {"space": space, **values})[0][0]
	reasons = {}
	for dt in {r.ref_doctype for r in rows}:
		names = [r.ref_name for r in rows if r.ref_doctype == dt]
		if frappe.get_meta(dt).has_field("archive_reason"):
			for n, why, on in frappe.get_all(dt, filters={"name": ("in", names)}, fields=["name", "archive_reason", "archived_on"], as_list=True):
				reasons[(dt, n)] = (why, str(on) if on else None)
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
	return {"groups": [{"area": k[0], "area_name": k[1], "records": v} for k, v in groups.items()], "records": rows, "projects": projects,
		"count": len(rows), "total": total, "has_more": start + len(rows) < total}
