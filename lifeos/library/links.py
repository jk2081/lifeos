"""[[Title]] links. Resolved to a record when the source is saved and stored in Life Link."""
import re

import frappe
from frappe.query_builder import Order

from lifeos.constants import LINKABLE

LINK_RE = re.compile(r"\[\[([^\[\]#|\n]+?)(?:#([^\[\]\n]+?))?\]\]")
ROUTES = {
	"Life Note": "/library/{0}", "Life Task": "/goals/tasks?open=task:{0}", "Life Person": "/settings?person={0}",
	"Life Vault Document": "/library/documents?open=vault:{0}", "Life Chat Log": "/library/chats?open=chat:{0}", "Life Goal": "/goals/{0}",
	"Life Inbox Item": "/item/{0}",
}


NO_LINKS = {"Life Wiki Change"}  # the before and after copies of a page are history, not links


def md_fields(doc):
	if doc.doctype in NO_LINKS:
		return []
	return [df.fieldname for df in doc.meta.fields if df.fieldtype == "Long Text" and df.fieldname.endswith("_md")]


def find_target(space, title, name=None):
	"""Return (doctype, name) for a link, or None. `name` pins one record when titles clash."""
	title = (title or "").strip()
	for dt, field in LINKABLE.items():
		filters = {"space": space, field: title}
		if name:
			filters["name"] = name.strip()
		if dt == "Life Note":  # a Wiki page first, then a My notes page (UX fixes, set 4)
			n = frappe.qb.DocType("Life Note")
			query = frappe.qb.from_(n).select(n.name).where((n.space == space) & (n.title == title))  # system: a link is resolved inside the record's own space
			if (name or "").strip():
				query = query.where(n.name == name.strip())
			found = query.orderby(n.collection == "Wiki", order=Order.desc).orderby(n.creation).limit(1).run()
			found = found[0][0] if found else None
		else:
			found = frappe.db.get_value(dt, filters, "name", order_by="creation asc")
		if found:
			return dt, found
	if name:  # the title changed since the link was written; the name still pins it
		for dt in LINKABLE:
			if frappe.db.get_value(dt, {"space": space, "name": name.strip()}, "name"):
				return dt, name.strip()
	return None


def candidates(space, title):
	"""Every record in the space with this exact title, for the picker."""
	out = []
	for dt, field in LINKABLE.items():
		for name in frappe.get_all(dt, filters={"space": space, field: title}, pluck="name"):
			out.append({"doctype": dt, "name": name})
	return out


def rebuild(doc):
	"""Parse the record's Markdown and rewrite its Life Link rows."""
	fields = md_fields(doc)
	if not fields:
		return
	frappe.db.delete("Life Link", {"from_doctype": doc.doctype, "from_name": doc.name, "origin": ("in", ("Text", ""))})  # the links to subjects (issue 111) are not written in the text
	seen = set()
	for field in fields:
		for m in LINK_RE.finditer(doc.get(field) or ""):
			target = find_target(doc.space, m.group(1), m.group(2))
			if not target or target == (doc.doctype, doc.name) or target in seen:
				continue
			seen.add(target)
			link = frappe.new_doc("Life Link")
			link.update({"space": doc.space, "from_doctype": doc.doctype, "from_name": doc.name,
				"to_doctype": target[0], "to_name": target[1], "link_text": m.group(1).strip()[:140]})
			link.db_insert()


def remove(doctype, name):
	lk = frappe.qb.DocType("Life Link")
	frappe.qb.from_(lk).delete().where(((lk.from_doctype == doctype) & (lk.from_name == name)) | ((lk.to_doctype == doctype) & (lk.to_name == name))).run()


def on_rename(doc):
	"""When a linkable record's title changes, update the link text in the records that point to it."""
	field = LINKABLE[doc.doctype]
	before = doc.get_doc_before_save()
	if not before or before.get(field) == doc.get(field):
		# a new record may make older, unresolved [[Title]] links valid
		if before is None:
			_adopt_unresolved(doc, field)
		return
	old, new = before.get(field), doc.get(field)
	rows = frappe.get_all("Life Link", filters={"to_doctype": doc.doctype, "to_name": doc.name}, fields=["name", "from_doctype", "from_name"], limit=0)
	pattern = re.compile(r"\[\[\s*" + re.escape(old) + r"\s*(#[^\[\]\n]+?)?\]\]")
	for row in rows:
		if not frappe.db.exists(row.from_doctype, row.from_name):
			continue
		src = frappe.get_doc(row.from_doctype, row.from_name)
		changed = {}
		for f in md_fields(src):
			text = src.get(f) or ""
			updated = pattern.sub(lambda m: f"[[{new}{m.group(1) or ''}]]", text)
			if updated != text:
				changed[f] = updated
		if changed:
			frappe.db.set_value(row.from_doctype, row.from_name, changed, update_modified=False)
			from lifeos.library import index
			from lifeos.constants import INDEXED_DOCTYPES
			if row.from_doctype in INDEXED_DOCTYPES:
				index.update(frappe.get_doc(row.from_doctype, row.from_name))
		frappe.db.set_value("Life Link", row.name, "link_text", new[:140], update_modified=False)


def _adopt_unresolved(doc, field):
	title = doc.get(field)
	if not title:
		return
	needle = f"%[[{title}%"
	for dt in ("Life Note",):
		for name in frappe.get_all(dt, filters={"space": doc.space, "content_md": ("like", needle), "name": ("!=", doc.name)}, pluck="name", limit=50):
			rebuild(frappe.get_doc(dt, name))


def title_of(doctype, name):
	field = LINKABLE.get(doctype) or "title"
	if frappe.get_meta(doctype).has_field(field):
		return frappe.db.get_value(doctype, name, field)
	return name


def route_of(doctype, name):
	return ROUTES.get(doctype, "/").format(name)


def outgoing(doc):
	"""Links stored for this record: link text, target and the target's current title. `ambiguous` is set when more than one
	wiki page has the link's title (the link resolves to the oldest; the screen shows a warning)."""
	rows = frappe.get_all("Life Link", filters={"from_doctype": doc.doctype, "from_name": doc.name, "origin": ("in", ("Text", ""))}, fields=["to_doctype", "to_name", "link_text"], limit=0)
	pinned = {m.group(1).strip().lower() for m in LINK_RE.finditer("\n".join(doc.get(f) or "" for f in md_fields(doc))) if m.group(2)}
	out = []
	for r in rows:
		ambiguous = False
		if r.to_doctype == "Life Note" and (r.link_text or "").lower() not in pinned:
			ambiguous = frappe.db.count("Life Note", {"space": doc.space, "collection": "Wiki", "title": r.link_text}) > 1
		out.append({"text": r.link_text, "doctype": r.to_doctype, "name": r.to_name, "ambiguous": ambiguous,
			"title": title_of(r.to_doctype, r.to_name), "route": route_of(r.to_doctype, r.to_name)})
	return out
