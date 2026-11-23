"""Archive and restore, and the Archive screen."""
import builtins

import frappe

from lifeos.library import archive as rules
from lifeos import permissions
from lifeos.api.timeline import index_rows
from lifeos.api.utils import area_filter, extra_columns, flag, names_map, page, std_clause, std_filters, std_order, summarise, tab_counts
from lifeos.api.utils import order_by as sort_order


@frappe.whitelist(methods=["POST"])
def set(doctype: str, name: str, archived: bool | int = 1):
	"""Archive or restore one record. For a goal, the records filed under it follow (as for a project before set 6)."""
	permissions.require_login()
	return rules.set_archived(doctype, name, flag(archived), "Manual")


@frappe.whitelist(methods=["POST"])
def restore(doctype: str, name: str):
	"""Bring an archived record back. Restoring a goal restores the records archived with it."""
	permissions.require_login()
	return rules.set_archived(doctype, name, False)


TYPES = ("Life Task", "Life Note", "Life Inbox Item", "Life Chat Log", "Life Vault Document")
SORTS = {"title": "title", "kind": "kind", "record_date": "record_date", "area": "area"}


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, area: str | None = None, start: int = 0, page_length: int = 50, doctype: str | None = None,
		reason: str | None = None, archived_from: str | None = None, archived_to: str | None = None, sort: str | None = None,
		dir: str | None = None, filters: str | builtins.list | builtins.dict | None = None, order_by: str | None = None, summary: str | builtins.dict | None = None):
	"""Archived records, grouped by area, plus archived goals.
	Filters: doctype (the record type), area (with its sub-areas, or "none"), reason (Auto, Manual, Project),
	archived_from and archived_to on the day it was archived. `total` is the number of records the filters match.
	`tabs` counts the records of each type (and all) under the same filters."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = "and is_archived = 1 and kind != 'Task Done'", {}
	if area:
		where += " and " + area_filter(space, area, "area", values, also_in="index")
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
	extra, values = std_clause("Life Index", filters, "", values)
	where += extra + permissions.vault_guard(space)
	# the state tabs of the Archive screen: one per record type, counted under every filter but the type itself
	tabs = tab_counts(f"from `tabLife Index` where space=%(space)s {where}", {"space": space, **values},
		{"all": None, **{dt: f"ref_doctype = '{dt}'" for dt in TYPES}})
	if doctype:
		where += " and ref_doctype = %(doctype)s"
		values["doctype"] = doctype
	if summary:
		return {"summary": summarise("Life Index", f"from `tabLife Index` where space=%(space)s {where}", {"space": space, **values}, "", summary, start, page_length),
			"tabs": tabs}
	order = std_order("Life Index", order_by, "", SORTS) or sort_order(sort, dir, SORTS, None)
	rows = index_rows(space, where, values, order=(order + ", modified desc") if order else "area asc, record_date desc, modified desc",
		start=start, page_length=page_length)
	# nosemgrep: frappe-sql-format-injection -- fixed fragments, std_clause columns checked against meta, vault_guard constant; values are parameters
	total = frappe.db.sql(f"select count(*) from `tabLife Index` where space=%(space)s {where}", {"space": space, **values})[0][0]
	reasons = {}
	for dt in {r.ref_doctype for r in rows}:
		names = [r.ref_name for r in rows if r.ref_doctype == dt]
		if frappe.get_meta(dt).has_field("archive_reason"):
			for n, why, on in frappe.get_list(dt, filters={"name": ("in", names)}, fields=["name", "archive_reason", "archived_on"], as_list=True):
				reasons[(dt, n)] = (why, str(on) if on else None)
	groups = {}
	for r in rows:
		r["archive_reason"], r["archived_on"] = reasons.get((r.ref_doctype, r.ref_name), ("", None))
		groups.setdefault((r.area or "", r.area_name or "Unfiled"), []).append(r)
	goals = frappe.get_list("Life Goal", filters={"space": space, "is_archived": 1},
		fields=["name", "title", "area", "horizon", "outcome", "on_hold", "is_someday", "archived_on"], order_by="archived_on desc", limit=100)
	areas = names_map("Life Area", [g.area for g in goals], "area_name")
	from lifeos.api.goals import status_of

	for g in goals:
		g["area_name"] = areas.get(g.area)
		g["archived_on"] = str(g.archived_on) if g.archived_on else None
		g["status"] = status_of(g)
	return {"groups": [{"area": k[0], "area_name": k[1], "records": v} for k, v in groups.items()], "records": rows, "goals": goals,
		"count": len(rows), "total": total, "tabs": tabs, "has_more": start + len(rows) < total}
