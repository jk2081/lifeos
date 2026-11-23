"""The Timeline: every record by day, newest first. Reads only Life Index."""
import frappe
from frappe.query_builder import functions as fn
from frappe.utils import add_days, getdate, today

from lifeos.library import links
from lifeos import permissions
from frappe.query_builder import Order

from lifeos.api.utils import area_criterion, count_where, filter_criteria, flag, group_summary, list_query, names_map, page, user_names

KIND_DOCTYPES = {
	"Life Inbox Item": ["Inbox"], "Life Task": ["Task", "Task Done"], "Life Note": ["Note"], "Life Vault Document": ["Document"],
	"Life Chat Log": ["Chat"]
}
ROW_FIELDS = ["ref_doctype", "ref_name", "kind", "title", "record_date", "area", "goal", "is_archived", "status", "record_owner", "also_in_csv"]


def decorate(rows):
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	goals = names_map("Life Goal", [r.goal for r in rows], "title")
	users = user_names([r.record_owner for r in rows])
	inbox = [r.ref_name for r in rows if r.ref_doctype == "Life Inbox Item"]
	proposals = {}
	if inbox:
		p = frappe.qb.DocType("Life Proposal")
		for item, st, n in frappe.qb.get_query("Life Proposal", fields=[p.inbox_item, p.status, fn.Count("*")], ignore_permissions=False).where(
				p.inbox_item.isin(inbox)).groupby(p.inbox_item, p.status).run():
			proposals.setdefault(item, {})[st] = n
	for r in rows:
		if r.ref_doctype == "Life Inbox Item":
			c = proposals.get(r.ref_name, {})
			r["proposals"], r["pending"] = sum(c.values()), c.get("Pending", 0)
		r["area_name"], r["goal_title"] = areas.get(r.area), goals.get(r.goal)
		r["route"] = links.route_of(r.ref_doctype, r.ref_name)
		r["filed_by"] = users.get(r.record_owner)
		r["record_date"] = str(r.record_date) if r.record_date else None
		r.pop("also_in_csv", None)
	return rows


def index_where(space, where=()):
	"""The criteria of a read of one space's Life Index rows: the space, `where`, and the Vault guard."""
	x = frappe.qb.DocType("Life Index")
	guard = permissions.vault_criterion(space, x)
	return [x.space == space, *where, *([guard] if guard is not None else [])]


DEFAULT_ORDER = (("record_date", Order.desc), ("modified", Order.desc))


def index_rows(space, where=(), order=None, start=0, page_length=50):
	"""Index rows of a space, decorated. `where` is a list of criteria over `frappe.qb.DocType("Life Index")`, `order` a list of (term, Order)."""
	x = frappe.qb.DocType("Life Index")
	order = order or [(x[f], way) for f, way in DEFAULT_ORDER]
	return decorate(list_query("Life Index", ROW_FIELDS, index_where(space, where), order).limit(page_length).offset(start).run(as_dict=True))


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None, from_date: str | None = None, to_date: str | None = None, area: str | None = None, doctype: str | None = None, include_archived: bool | int = 0, start: int = 0,
		page_length: int = 50, filters: str | list | None = None, summary: str | dict | None = None):
	"""Every record by day, newest first: inbox items, tasks created and completed, notes, documents, chats."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	x = frappe.qb.DocType("Life Index")
	where = []
	if from_date:
		where.append(x.record_date >= getdate(from_date))
	if to_date:
		where.append(x.record_date <= getdate(to_date))
	if area:
		where.append(area_criterion(space, area, x, also_in="index"))  # with its sub-areas, as under the lens
	if doctype:
		where.append(x.ref_doctype == doctype)
	if not flag(include_archived):
		where.append(x.is_archived == 0)
	where += filter_criteria("Life Index", filters, x)
	if summary:
		return {"summary": group_summary("Life Index", index_where(space, where), summary, start, page_length)}
	rows = index_rows(space, where, start=start, page_length=page_length)
	total = count_where("Life Index", index_where(space, where))
	days = []
	for r in rows:
		if not days or days[-1]["date"] != r["record_date"]:
			days.append({"date": r["record_date"], "entries": []})
		days[-1]["entries"].append(r)
	return {"days": days, "count": len(rows), "start": start, "page_length": page_length, "total": total, "has_more": start + len(rows) < total}
