"""Vault: documents by holder and type, with expiry badges."""
import builtins

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder import functions as fn
from frappe.utils import add_days, getdate, today

from lifeos import permissions
from lifeos.api.utils import (area_criterion, count_tabs, count_where, extra_fields, filter_criteria, flag, group_summary, list_query, names_map, null_last, order_terms,
	page, parse, sort_terms)

FIELDS = ["name", "title", "doc_type", "holder", "file", "number_last4", "issue_date", "expiry_date", "remind_days_before", "area", "goal", "is_archived", "inbox_item"]
EDITABLE = {"title", "doc_type", "holder", "number_last4", "issue_date", "expiry_date", "remind_days_before", "notes_md", "area", "goal"}


def badge(expiry, remind, on=None):
	"""The expiry badge of a document: None, or {state, days}. A document inside its reminder window gets one."""
	if not expiry:
		return None
	days = (getdate(expiry) - getdate(on or today())).days
	remind = 60 if remind is None else int(remind)
	if days < 0:
		return {"state": "expired", "days": days}
	if days <= remind:
		return {"state": "expiring", "days": days}
	return None


def _decorate(rows):
	holders = names_map("Life Person", [r.holder for r in rows], "full_name")
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	for r in rows:
		r["holder_name"], r["area_name"] = holders.get(r.holder), areas.get(r.area)
		r["badge"] = badge(r.expiry_date, r.remind_days_before)
		for k in ("issue_date", "expiry_date"):
			r[k] = str(r[k]) if r.get(k) else None
	return rows


SOON_DAYS = 60


def expiry_criteria(d):
	"""The Expiry filter as criteria over the document table."""
	now = getdate(today())
	return {"expired": d.expiry_date < now, "soon": d.expiry_date.between(now, add_days(now, SOON_DAYS)), "later": d.expiry_date > add_days(now, SOON_DAYS),
		"none": d.expiry_date.isnull()}


def holder_name(d):
	h = frappe.qb.DocType("Life Person")
	return frappe.qb.from_(h).select(h.full_name).where(h.name == d.holder)


SORTS = {"title": lambda d: [d.title], "doc_type": lambda d: [d.doc_type], "expiry_date": lambda d: null_last(d.expiry_date),
	"holder": lambda d: [fn.IfNull(holder_name(d), "")]}


def where_criteria(space, holder=None, doc_type=None, expiry=None, area=None, goal=None, include_archived=0):
	d = frappe.qb.DocType("Life Vault Document")
	where = [d.space == space]
	if not flag(include_archived):
		where.append(d.is_archived == 0)
	if holder:
		where.append(fn.IfNull(d.holder, "") == ("" if holder == "none" else holder))
	if doc_type:
		where.append(d.doc_type == doc_type)
	if expiry:
		if expiry not in expiry_criteria(d):
			frappe.throw(_("expiry must be one of: {0}.").format(", ".join(expiry_criteria(d))), title=_("Unknown expiry filter"))
		where.append(expiry_criteria(d)[expiry])
	if area:
		where.append(area_criterion(space, area, d, also_in="Life Vault Document"))
	if goal:
		where.append(fn.IfNull(d.goal, "") == ("" if goal == "none" else goal))
	return where


def count(space, **filters):
	return count_where("Life Vault Document", where_criteria(space, **filters))


def expiry_counts(space):
	"""How many documents have expired and how many expire within 60 days, counted as the Expiry filter counts them."""
	if permissions.vault_hidden(space):
		return {"expired": 0, "soon": 0}
	return {"expired": count(space, expiry="expired"), "soon": count(space, expiry="soon")}


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, include_archived: bool | int = 0, start: int = 0, page_length: int = 100, holder: str | None = None,
		doc_type: str | None = None, expiry: str | None = None, area: str | None = None, goal: str | None = None, sort: str | None = None,
		dir: str | None = None, filters: str | builtins.list | builtins.dict | None = None, order_by: str | None = None, fields: str | builtins.list | None = None,
		summary: str | builtins.dict | None = None):
	"""Vault documents of a space, soonest expiry first, as a flat list and grouped by holder.
	Filters: holder (a person, or "none"), doc_type, expiry (expired, soon = within 60 days, later, none), area, goal.
	`total` is the number of documents the filters match.
	`tabs` counts all documents, those expiring within 60 days and the expired ones, under the same filters."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	if permissions.vault_hidden(space):
		# an agent, and this space's Vault is closed to agents: the same answer as an empty Vault
		empty = {"tabs": {"all": 0, "soon": 0, "expired": 0}, "expired": 0, "soon": 0}
		if summary:
			return {"summary": {"rows": [], "totals": None}, **empty}
		return {"space": space, "documents": [], "groups": [], "total": 0, **empty}
	d = frappe.qb.DocType("Life Vault Document")
	extra = filter_criteria("Life Vault Document", filters, d)
	where = where_criteria(space, holder, doc_type, expiry, area, goal, include_archived) + extra
	# the state tabs of the Vault screen (all, soon = within 60 days, expired), counted under every filter but the expiry itself
	known = expiry_criteria(d)
	tabs = count_tabs("Life Vault Document", where_criteria(space, holder, doc_type, None, area, goal, include_archived) + extra,
		{"all": None, "soon": known["soon"], "expired": known["expired"]})
	if summary:
		return {"summary": group_summary("Life Vault Document", where, summary, start, page_length), **expiry_counts(space), "tabs": tabs}
	terms = order_terms("Life Vault Document", order_by, d, SORTS) or sort_terms(sort, dir, SORTS, d, [(d.expiry_date.isnull(), Order.asc), (d.expiry_date, Order.asc)])
	cols = [*FIELDS, *extra_fields("Life Vault Document", fields, d, FIELDS)]
	rows = _decorate(list_query("Life Vault Document", cols, where, [*terms, (d.title, Order.asc)]).limit(page_length).offset(start).run(as_dict=True))
	total = count_where("Life Vault Document", where)
	groups = {}
	for r in rows:
		groups.setdefault(r["holder_name"] or "No holder", []).append(r)
	people = frappe.get_list("Life Person", filters={"space": space}, fields=["name", "full_name", "relation"], order_by="full_name", limit=500)
	counts = expiry_counts(space)
	return {"space": space, "documents": rows,
		"groups": [{"holder": k, "documents": v} for k, v in sorted(groups.items(), key=lambda kv: (kv[0] == "No holder", kv[0]))],
		"total": total, "tabs": tabs, "people": people, "expiring": sum(1 for r in rows if r["badge"]), "expired": counts["expired"], "soon": counts["soon"]}


@frappe.whitelist(methods=["GET"])
def get(document: str):
	"""One vault document with its holder, file and expiry badge."""
	doc = permissions.get_doc_checked("Life Vault Document", document)
	row = _decorate([frappe._dict({f: doc.get(f) for f in FIELDS})])[0]
	row.update({"space": doc.space, "notes_md": doc.notes_md or "", "also_in": [r.area for r in doc.also_in],
		"goal_title": frappe.db.get_value("Life Goal", doc.goal, "title") if doc.goal else None})
	if doc.file:
		f = frappe.db.get_value("File", {"file_url": doc.file, "attached_to_name": doc.name}, ["file_name", "file_size"], as_dict=True)
		row["file_name"], row["file_size"] = (f.file_name, f.file_size) if f else (doc.file.split("/")[-1], None)
	return row


@frappe.whitelist(methods=["POST"])
def save(document: str | None = None, space: str | None = None, values: str | builtins.dict | None = None):
	"""Create or change a vault document. Only the last four characters of a number are ever stored."""
	values = parse(values, {}) or {}
	unknown = set(values) - EDITABLE
	if unknown:
		frappe.throw(_("Field {0} cannot be set here.").format(", ".join(sorted(unknown))), title=_("Field cannot be set"))
	if document:
		doc = permissions.get_doc_checked("Life Vault Document", document, "write")
	else:
		space = permissions.resolve_space(space, write=True)
		doc = frappe.get_doc({"doctype": "Life Vault Document", "space": space})
	for k, v in values.items():
		doc.set(k, v if v not in ("", None) else None)
	doc.save() if document else doc.insert()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def set_file(document: str, file_url: str):
	"""Point the document at a file already uploaded to it with upload_file."""
	doc = permissions.get_doc_checked("Life Vault Document", document, "write")
	if not frappe.db.exists("File", {"file_url": file_url, "attached_to_doctype": "Life Vault Document", "attached_to_name": doc.name}):
		frappe.throw(_("Upload the file to this document first."), title=_("Upload the file first"))
	doc.file = file_url
	doc.save()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def add_person(space: str | None = None, full_name: str | None = None, relation: str | None = None):
	"""Add a person, for example a document holder."""
	space = permissions.resolve_space(space, write=True)
	doc = frappe.get_doc({"doctype": "Life Person", "space": space, "full_name": full_name, "relation": relation}).insert()
	return {"name": doc.name, "full_name": doc.full_name}
