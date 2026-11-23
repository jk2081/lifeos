"""Archive and restore, and the Archive screen."""
import builtins

import frappe

from lifeos.library import archive as rules
from lifeos import permissions
from frappe.query_builder import Order

from lifeos.api.timeline import index_rows, index_where
from lifeos.api.utils import area_criterion, count_tabs, count_where, filter_criteria, flag, group_summary, names_map, order_terms, page, sort_terms


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
SORTS = {k: (lambda x, k=k: [x[k]]) for k in ("title", "kind", "record_date", "area")}


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
	x = frappe.qb.DocType("Life Index")
	where = [x.is_archived == 1, x.kind != "Task Done"]
	if area:
		where.append(area_criterion(space, area, x, also_in="index"))
	if reason or archived_from or archived_to:
		# the reason and the day live on the records themselves, so each type is checked in its own table
		parts = []
		for dt in rules.AUTO_DOCTYPES + tuple(t for t in TYPES if t not in rules.AUTO_DOCTYPES):
			if not frappe.get_meta(dt).has_field("archive_reason"):
				continue
			r = frappe.qb.DocType(dt)
			conds = []
			if reason:
				conds.append(r.archive_reason == reason)
			if archived_from:
				conds.append(r.archived_on >= archived_from)
			if archived_to:
				conds.append(r.archived_on <= archived_to)
			names = frappe.qb.from_(r).select(r.name)
			for c in conds:
				names = names.where(c)
			parts.append((x.ref_doctype == dt) & x.ref_name.isin(names))
		crit = parts[0] if parts else x.name.isnull()  # no type to look in: nothing matches
		for p in parts[1:]:
			crit = crit | p
		where.append(crit)
	where += filter_criteria("Life Index", filters, x)
	# the state tabs of the Archive screen: one per record type, counted under every filter but the type itself
	tabs = count_tabs("Life Index", index_where(space, where), {"all": None, **{dt: x.ref_doctype == dt for dt in TYPES}})
	if doctype:
		where.append(x.ref_doctype == doctype)
	if summary:
		return {"summary": group_summary("Life Index", index_where(space, where), summary, start, page_length), "tabs": tabs}
	terms = order_terms("Life Index", order_by, x, SORTS) or sort_terms(sort, dir, SORTS, x)
	terms = [*terms, (x.modified, Order.desc)] if terms else [(x.area, Order.asc), (x.record_date, Order.desc), (x.modified, Order.desc)]
	rows = index_rows(space, where, terms, start=start, page_length=page_length)
	total = count_where("Life Index", index_where(space, where))
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
