"""The Timeline: every record by day, newest first. Reads only Life Index."""
import frappe
from frappe.utils import add_days, getdate, today

from lifeos import links, permissions
from lifeos.api.utils import flag, names_map, page, std_filters, summarise, user_names

KIND_DOCTYPES = {
	"Life Inbox Item": ["Inbox"], "Life Task": ["Task", "Task Done"], "Life Note": ["Note"], "Life Vault Document": ["Document"],
	"Life Chat Log": ["Chat"], "Life Journal Page": ["Journal Page"], "Life Check-in": ["Check-in"], "Life Month Plan": ["Month Plan"],
}
ROW_FIELDS = "ref_doctype, ref_name, kind, title, record_date, area, project, is_archived, status, record_owner, also_in_csv"


def decorate(rows):
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	projects = names_map("Life Project", [r.project for r in rows], "title")
	users = user_names([r.record_owner for r in rows])
	inbox = [r.ref_name for r in rows if r.ref_doctype == "Life Inbox Item"]
	proposals = {}
	if inbox:
		for item, st, n in frappe.db.sql(
			"select inbox_item, status, count(*) from `tabLife Proposal` where inbox_item in %s group by inbox_item, status", (inbox,)):
			proposals.setdefault(item, {})[st] = n
	for r in rows:
		if r.ref_doctype == "Life Inbox Item":
			c = proposals.get(r.ref_name, {})
			r["proposals"], r["pending"] = sum(c.values()), c.get("Pending", 0)
		r["area_name"], r["project_title"] = areas.get(r.area), projects.get(r.project)
		r["route"] = links.route_of(r.ref_doctype, r.ref_name)
		r["filed_by"] = users.get(r.record_owner)
		r["record_date"] = str(r.record_date) if r.record_date else None
		r.pop("also_in_csv", None)
	return rows


def index_rows(space, where="", values=None, order="record_date desc, modified desc", start=0, page_length=50):
	rows = frappe.db.sql(
		f"select {ROW_FIELDS} from `tabLife Index` where space=%(space)s {where}{permissions.vault_guard(space)} order by {order} limit %(start)s, %(len)s",
		{"space": space, "start": start, "len": page_length, **(values or {})}, as_dict=True)
	return decorate(rows)


@frappe.whitelist()
def get(space=None, from_date=None, to_date=None, area=None, doctype=None, include_archived=0, start=0, page_length=50, filters=None, summary=None):
	"""Every record by day, newest first: inbox items, tasks created and completed, notes, documents, chats, journal pages, check-ins."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = [], {}
	if from_date:
		where.append("record_date >= %(from_date)s")
		values["from_date"] = getdate(from_date)
	if to_date:
		where.append("record_date <= %(to_date)s")
		values["to_date"] = getdate(to_date)
	if area:
		from lifeos.index import also_in_sql

		where.append(f"(area = %(area)s or {also_in_sql('area')})")  # this one area only; sub-areas have their own pages
		values.update({"area": area})
	if doctype:
		where.append("ref_doctype = %(doctype)s")
		values["doctype"] = doctype
	if not flag(include_archived):
		where.append("is_archived = 0")
	conds, values = std_filters("Life Index", filters, "", values)
	where += conds
	clause = ((" and " + " and ".join(where)) if where else "") + permissions.vault_guard(space)
	if summary:
		return {"summary": summarise("Life Index", f"from `tabLife Index` where space=%(space)s {clause}", {"space": space, **values}, "", summary, start, page_length)}
	rows = index_rows(space, clause, values, start=start, page_length=page_length)
	total = frappe.db.sql(f"select count(*) from `tabLife Index` where space=%(space)s {clause}", {"space": space, **values})[0][0]
	days = []
	for r in rows:
		if not days or days[-1]["date"] != r["record_date"]:
			days.append({"date": r["record_date"], "entries": []})
		days[-1]["entries"].append(r)
	return {"days": days, "count": len(rows), "start": start, "page_length": page_length, "total": total, "has_more": start + len(rows) < total}
