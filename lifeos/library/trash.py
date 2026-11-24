"""The trash (UX fixes, set 5): Delete and Purge move a Life OS record to Frappe's Deleted Document, the Archive's Trash
tab restores it, and a daily job removes Life OS deleted documents older than 30 days. Agents never delete."""
import json

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from lifeos import permissions

DAYS = 30
# what the trash lists and restores; areas and habits stay archive-only (set 3)
TRASHABLE = ("Life Task", "Life Goal", "Life Note", "Life Inbox Item", "Life Chat Log",
	"Life Vault Document", "Life Person")
LABELS = {"Life Task": "Task", "Life Goal": "Goal", "Life Note": "Note",
	"Life Inbox Item": "Source", "Life Chat Log": "Chat", "Life Vault Document": "Vault document",
	"Life Person": "Person"}


def delete(doctype, name):
	"""Move one record to the trash, with the caller's own delete permission. Records that other records still point
	to are refused with a plain message."""
	if doctype not in TRASHABLE:
		frappe.throw(_("{0} cannot be deleted here.").format(doctype), title=_("Record cannot be deleted"))
	if permissions.is_agent():
		frappe.throw(_("Agents cannot delete records."), frappe.PermissionError, title=_("Agents cannot delete"))
	doc = permissions.get_doc_checked(doctype, name, "delete")
	try:
		frappe.delete_doc(doctype, name)
	except frappe.LinkExistsError:
		frappe.throw(_("{0} is still used by other records, so it cannot be deleted. Archive it instead.").format(frappe.bold(_title(doc))), title=_("Record is still in use"))
	return {"deleted": name, "doctype": doctype}


def _title(doc):
	meta = frappe.get_meta(doc.doctype)
	return doc.get(meta.title_field or "title") or doc.get("title") or doc.name


def _rows(space=None):
	"""Deleted Life OS records of the last 30 days that the user may see, newest first."""
	spaces = permissions.user_spaces()
	if space:
		spaces = {space: spaces.get(space)} if space in spaces else {}
	rows = frappe.get_all("Deleted Document", filters={"restored": 0, "deleted_doctype": ("in", TRASHABLE), "creation": (">=", add_days(now_datetime(), -DAYS))},  # system: the trash is filtered to the user's spaces below
		fields=["name", "deleted_doctype", "deleted_name", "data", "creation", "owner"], order_by="creation desc", limit=1000)
	out = []
	for r in rows:
		try:
			data = json.loads(r.data)
		except ValueError:
			continue
		if data.get("space") not in spaces and frappe.session.user != "Administrator":
			continue
		if space and data.get("space") != space:
			continue
		if data.get("space") and permissions.vault_hidden(data["space"]) and (
				r.deleted_doctype == permissions.VAULT or data.get("vault_document")):
			continue  # a closed Vault stays closed to agents in the trash too (pre-step 6 audit)
		meta = frappe.get_meta(r.deleted_doctype)
		out.append({"name": r.name, "doctype": r.deleted_doctype, "kind": LABELS.get(r.deleted_doctype, r.deleted_doctype),
			"record": r.deleted_name, "title": data.get(meta.title_field or "title") or data.get("title") or r.deleted_name,
			"area": data.get("area"), "deleted_on": str(r.creation)[:19], "deleted_by": r.owner,
			"days_left": max(DAYS - (now_datetime() - r.creation).days, 0), "space": data.get("space")})
	return out


def list(space=None, start=0, page_length=50, kind=None):
	"""The Archive's Trash tab: Life OS records deleted in the last 30 days, in spaces the user belongs to."""
	space = permissions.resolve_space(space)
	rows = _rows(space)
	if kind:
		rows = [r for r in rows if r["doctype"] == kind]
	from lifeos.api.utils import names_map, page

	start, page_length = page(start, page_length)
	part = rows[start:start + page_length]
	areas = names_map("Life Area", [r["area"] for r in part], "area_name")
	for r in part:
		r["area_name"] = areas.get(r["area"])
	return {"rows": part, "total": len(rows)}


def restore(name):
	"""Put a deleted record back as it was, with its original name and creation date. Needs Write access to its space."""
	if permissions.is_agent():
		frappe.throw(_("Agents cannot restore records."), frappe.PermissionError, title=_("Agents cannot restore"))
	deleted = frappe.db.get_value("Deleted Document", name, ["deleted_doctype", "deleted_name", "data", "restored"], as_dict=True)
	if not deleted or deleted.deleted_doctype not in TRASHABLE:
		frappe.throw(_("Not found in the trash."), frappe.DoesNotExistError, title=_("Not found in trash"))
	if deleted.restored:
		frappe.throw(_("This record was already restored."), title=_("Already restored"))
	data = json.loads(deleted.data)
	permissions.require_space(data.get("space"), write=True)
	doc = frappe.get_doc(data)
	doc.flags.from_restore = True
	doc.flags.name_set = True  # back under its own name, so links written before the delete still find it
	keep = {k: data.get(k) for k in ("owner", "creation", "modified", "modified_by")}
	doc.insert()
	frappe.db.set_value(doc.doctype, doc.name, keep, update_modified=False)
	frappe.db.set_value("Deleted Document", name, {"restored": 1, "new_name": doc.name}, update_modified=False)
	doc.reload()
	from lifeos.library import index
	from lifeos.constants import INDEXED_DOCTYPES

	if doc.doctype in INDEXED_DOCTYPES:
		index.update(doc)
	return {"doctype": doc.doctype, "name": doc.name, "title": _title(doc)}


def purge_old():
	"""Daily: remove Life OS deleted documents older than 30 days for good."""
	frappe.db.delete("Deleted Document", {"deleted_doctype": ("like", "Life %"), "creation": ("<", add_days(now_datetime(), -DAYS))})
