"""Shared rules for every lifeos DocType that carries a `space`: same-space links, organisation fields, index, links."""
import frappe
from frappe import _

from lifeos import index, links
from lifeos.constants import INDEXED_DOCTYPES, LINKABLE, ORG_DOCTYPES, SPACE_DOCTYPES

SKIP = {"Life Index", "Life Link"}


def _space_of(doctype, name):
	return frappe.db.get_value(doctype, name, "space")


def _check_links(doc, parent_space, label_prefix=""):
	for df in doc.meta.get_link_fields():
		value = doc.get(df.fieldname)
		if not value or df.options not in SPACE_DOCTYPES:
			continue
		other = _space_of(df.options, value)
		if other is None:
			frappe.throw(_("{0}{1}: {2} {3} does not exist.").format(label_prefix, df.label, df.options, value), frappe.ValidationError)
		if other != parent_space:
			frappe.throw(
				_("{0}{1} belongs to another space. A record can only use records from its own space.").format(label_prefix, df.label),
				frappe.ValidationError,
			)


def validate_common(doc, method=None):
	if doc.doctype in SKIP:
		return
	if not doc.space:
		frappe.throw(_("Space is required."))
	if not doc.is_new() and doc.has_value_changed("space") and not frappe.flags.lifeos_allow_space_change:
		frappe.throw(_("A record cannot be moved to another space."))
	_check_links(doc, doc.space)
	for tf in doc.meta.get_table_fields():
		for row in doc.get(tf.fieldname) or []:
			_check_links(row, doc.space, label_prefix=f"{tf.label} row {row.idx}: ")
	if doc.doctype in ORG_DOCTYPES:
		validate_org(doc)


def validate_org(doc):
	also = [r.area for r in doc.get("also_in") or [] if r.area]
	if doc.area:
		# an area is never also its own reference
		doc.set("also_in", [r for r in doc.get("also_in") or [] if r.area and r.area != doc.area])
		also = [a for a in also if a != doc.area]
	seen, rows = set(), []
	for r in doc.get("also_in") or []:
		if r.area not in seen:
			seen.add(r.area)
			rows.append(r)
	doc.set("also_in", rows)
	if doc.project:
		project_area = frappe.db.get_value("Life Project", doc.project, "area")
		if project_area not in [doc.area, *also]:
			frappe.throw(_("The project must belong to the record's area or to one of its other areas."), frappe.ValidationError)
	if doc.is_archived and not doc.archived_on:
		doc.archived_on = frappe.utils.today()
	if not doc.is_archived:
		doc.archived_on = None
		doc.archive_reason = ""


def on_update(doc, method=None):
	if doc.doctype in SKIP:
		return
	if doc.doctype in INDEXED_DOCTYPES:
		index.update(doc)
	links.rebuild(doc)
	if doc.doctype in LINKABLE:
		links.on_rename(doc)


def on_trash(doc, method=None):
	if doc.doctype in SKIP:
		return
	if doc.doctype in INDEXED_DOCTYPES:
		index.remove(doc.doctype, doc.name)
	links.remove(doc.doctype, doc.name)
	forget_bookkeeping(doc.doctype, doc.name)


# Rows that only record history and point at another record by a Dynamic Link: they must not stop that record's delete
# (pre-step 6 audit, Q-B26), so their pointer is cleared when it goes. Frappe runs on_trash before its link check, and the
# clearing is part of the delete's transaction. Real filing links (an idea's area or project, a wiki change's page) still
# stop a delete, and so does a wiki page's cited source (Life Note Source).
BOOKKEEPING = (
	("Life Proposal", "created_doctype", "created_name"),
	("Life Ask Thread", "scope_doctype", "scope_name"),
	("Life Idea", "source_doctype", "source_name"),
	("Life Idea", "brought_to_doctype", "brought_to_name"),
	("Life Wiki Change", "source_doctype", "source_name"),
)


def forget_bookkeeping(doctype, name):
	for table, type_field, name_field in BOOKKEEPING:
		frappe.db.set_value(table, {type_field: doctype, name_field: name}, {type_field: None, name_field: None}, update_modified=False)
	frappe.db.delete("Life Insight Evidence", {"ref_doctype": doctype, "ref_name": name})
