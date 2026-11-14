"""Vault: documents by holder and type, with expiry badges."""
import frappe
from frappe import _
from frappe.utils import getdate, today

from lifeos import permissions
from lifeos.api.utils import flag, names_map, page, parse

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


@frappe.whitelist()
def list(space=None, include_archived=0, start=0, page_length=100):
	"""Vault documents of a space, grouped by holder, soonest expiry first."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	filters = {"space": space}
	if not flag(include_archived):
		filters["is_archived"] = 0
	rows = _decorate(frappe.get_all("Life Vault Document", filters=filters, fields=FIELDS,
		order_by="expiry_date asc, title asc", limit_start=start, limit=page_length))
	rows.sort(key=lambda r: (r["expiry_date"] is None, r["expiry_date"] or "", r["title"]))
	groups = {}
	for r in rows:
		groups.setdefault(r["holder_name"] or "No holder", []).append(r)
	people = frappe.get_all("Life Person", filters={"space": space}, fields=["name", "full_name", "relation"], order_by="full_name", limit=500)
	return {"space": space, "groups": [{"holder": k, "documents": v} for k, v in sorted(groups.items(), key=lambda kv: (kv[0] == "No holder", kv[0]))],
		"total": len(rows), "people": people, "expiring": sum(1 for r in rows if r["badge"])}


@frappe.whitelist()
def get(document):
	"""One vault document with its holder, file and expiry badge."""
	doc = permissions.get_doc_checked("Life Vault Document", document)
	row = _decorate([frappe._dict({f: doc.get(f) for f in FIELDS})])[0]
	row.update({"space": doc.space, "notes_md": doc.notes_md or "", "also_in": [r.area for r in doc.also_in]})
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
