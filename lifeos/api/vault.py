"""Vault: documents by holder and type, with expiry badges."""
import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos import permissions
from lifeos.api.utils import area_filter, extra_columns, flag, names_map, page, parse, std_clause, std_filters, std_order, summarise, tab_counts
from lifeos.api.utils import order_by as sort_order

FIELDS = ["name", "title", "doc_type", "holder", "file", "number_last4", "issue_date", "expiry_date", "remind_days_before", "area", "project", "is_archived", "inbox_item"]
EDITABLE = {"title", "doc_type", "holder", "number_last4", "issue_date", "expiry_date", "remind_days_before", "notes_md", "area", "project"}


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
EXPIRY = {
	"expired": "d.expiry_date < %(today)s",
	"soon": "d.expiry_date between %(today)s and %(soon)s",
	"later": "d.expiry_date > %(soon)s",
	"none": "d.expiry_date is null",
}
SORTS = {"title": "d.title", "doc_type": "d.doc_type", "expiry_date": "d.expiry_date is null, d.expiry_date",
	"holder": "(select full_name from `tabLife Person` h where h.name = d.holder)"}


def where_clause(space, holder=None, doc_type=None, expiry=None, area=None, project=None, include_archived=0):
	where, values = [], {"today": getdate(today()), "soon": add_days(getdate(today()), SOON_DAYS)}
	if not flag(include_archived):
		where.append("d.is_archived = 0")
	if holder:
		where.append("ifnull(d.holder, '') = %(holder)s")
		values["holder"] = "" if holder == "none" else holder
	if doc_type:
		where.append("d.doc_type = %(doc_type)s")
		values["doc_type"] = doc_type
	if expiry:
		if expiry not in EXPIRY:
			frappe.throw(_("expiry must be one of: {0}.").format(", ".join(EXPIRY)))
		where.append(EXPIRY[expiry])
	if area:
		where.append(area_filter(space, area, "d.area", values))
	if project:
		where.append("d.project = %(project)s")
		values["project"] = project
	return "".join(" and " + w for w in where), values


def count(space, **filters):
	clause, values = where_clause(space, **filters)
	return frappe.db.sql(f"select count(*) from `tabLife Vault Document` d where d.space=%(space)s {clause}", {"space": space, **values})[0][0]


def expiry_counts(space):
	"""How many documents have expired and how many expire within 60 days, counted as the Expiry filter counts them."""
	if permissions.vault_hidden(space):
		return {"expired": 0, "soon": 0}
	return {"expired": count(space, expiry="expired"), "soon": count(space, expiry="soon")}


@frappe.whitelist()
def list(space=None, include_archived=0, start=0, page_length=100, holder=None, doc_type=None, expiry=None, area=None, project=None,
		sort=None, dir=None, filters=None, order_by=None, fields=None, summary=None):
	"""Vault documents of a space, soonest expiry first, as a flat list and grouped by holder.
	Filters: holder (a person, or "none"), doc_type, expiry (expired, soon = within 60 days, later, none), area, project.
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
	clause, values = where_clause(space, holder, doc_type, expiry, area, project, include_archived)
	extra, values = std_clause("Life Vault Document", filters, "d", values)
	clause += extra
	# the state tabs of the Vault screen (all, soon = within 60 days, expired), counted under every filter but the expiry itself
	t_clause, t_values = where_clause(space, holder, doc_type, None, area, project, include_archived)
	tabs = tab_counts(f"from `tabLife Vault Document` d where d.space=%(space)s {t_clause}{extra}", {**t_values, **values, "space": space},
		{"all": None, "soon": EXPIRY["soon"], "expired": EXPIRY["expired"]})
	if summary:
		return {"summary": summarise("Life Vault Document", f"from `tabLife Vault Document` d where d.space=%(space)s {clause}",
			{"space": space, **values}, "d", summary, start, page_length), **expiry_counts(space), "tabs": tabs}
	cols = ", ".join([f"d.`{f}`" for f in FIELDS] + extra_columns("Life Vault Document", fields, "d", FIELDS))
	order = std_order("Life Vault Document", order_by, "d", SORTS) or sort_order(sort, dir, SORTS, "d.expiry_date is null, d.expiry_date asc")
	rows = _decorate(frappe.db.sql(
		f"select {cols} from `tabLife Vault Document` d where d.space=%(space)s {clause} order by {order}, d.title asc limit %(start)s, %(len)s",
		{"space": space, "start": start, "len": page_length, **values}, as_dict=True))
	total = frappe.db.sql(f"select count(*) from `tabLife Vault Document` d where d.space=%(space)s {clause}", {"space": space, **values})[0][0]
	groups = {}
	for r in rows:
		groups.setdefault(r["holder_name"] or "No holder", []).append(r)
	people = frappe.get_all("Life Person", filters={"space": space}, fields=["name", "full_name", "relation"], order_by="full_name", limit=500)
	counts = expiry_counts(space)
	return {"space": space, "documents": rows,
		"groups": [{"holder": k, "documents": v} for k, v in sorted(groups.items(), key=lambda kv: (kv[0] == "No holder", kv[0]))],
		"total": total, "tabs": tabs, "people": people, "expiring": sum(1 for r in rows if r["badge"]), "expired": counts["expired"], "soon": counts["soon"]}


@frappe.whitelist()
def get(document):
	"""One vault document with its holder, file and expiry badge."""
	doc = permissions.get_doc_checked("Life Vault Document", document)
	row = _decorate([frappe._dict({f: doc.get(f) for f in FIELDS})])[0]
	row.update({"space": doc.space, "notes_md": doc.notes_md or "", "also_in": [r.area for r in doc.also_in],
		"project_title": frappe.db.get_value("Life Project", doc.project, "title") if doc.project else None})
	if doc.file:
		f = frappe.db.get_value("File", {"file_url": doc.file, "attached_to_name": doc.name}, ["file_name", "file_size"], as_dict=True)
		row["file_name"], row["file_size"] = (f.file_name, f.file_size) if f else (doc.file.split("/")[-1], None)
	return row


@frappe.whitelist(methods=["POST"])
def save(document=None, space=None, values=None):
	"""Create or change a vault document. Only the last four characters of a number are ever stored."""
	values = parse(values, {}) or {}
	unknown = set(values) - EDITABLE
	if unknown:
		frappe.throw(_("Field {0} cannot be set here.").format(", ".join(sorted(unknown))))
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
def set_file(document, file_url):
	"""Point the document at a file already uploaded to it with upload_file."""
	doc = permissions.get_doc_checked("Life Vault Document", document, "write")
	if not frappe.db.exists("File", {"file_url": file_url, "attached_to_doctype": "Life Vault Document", "attached_to_name": doc.name}):
		frappe.throw(_("Upload the file to this document first."))
	doc.file = file_url
	doc.save()
	return get(doc.name)


@frappe.whitelist(methods=["POST"])
def add_person(space=None, full_name=None, relation=None):
	"""Add a person, for example a document holder."""
	space = permissions.resolve_space(space, write=True)
	doc = frappe.get_doc({"doctype": "Life Person", "space": space, "full_name": full_name, "relation": relation}).insert()
	return {"name": doc.name, "full_name": doc.full_name}
