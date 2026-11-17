"""[[Title]] links. Resolved to a record when the source is saved and stored in Life Link."""
import re

import frappe

from lifeos.constants import LINKABLE

LINK_RE = re.compile(r"\[\[([^\[\]#|\n]+?)(?:#([^\[\]\n]+?))?\]\]")
ROUTES = {
	"Life Note": "/library/{0}", "Life Task": "/plan/tasks?open=task:{0}", "Life Person": "/settings?person={0}",
	"Life Vault Document": "/library/captures?open=vault:{0}", "Life Chat Log": "/library/captures?open=chat:{0}", "Life Goal": "/plan/goals/{0}",
	"Life Inbox Item": "/inbox/{0}", "Life Journal Page": "/library/captures?open=page:{0}",
	"Life Check-in": "/plan/month?view=checkins", "Life Month Plan": "/plan/month",
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
			found = frappe.db.sql("""select name from `tabLife Note` where space=%(space)s and title=%(title)s
				and (%(name)s = '' or name=%(name)s) order by (collection = 'Wiki') desc, creation asc limit 1""",
				{"space": space, "title": title, "name": (name or "").strip()})
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
	frappe.db.sql("delete from `tabLife Link` where from_doctype=%s and from_name=%s", (doc.doctype, doc.name))
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
	frappe.db.sql(
		"delete from `tabLife Link` where (from_doctype=%s and from_name=%s) or (to_doctype=%s and to_name=%s)",
		(doctype, name, doctype, name),
	)


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
	rows = frappe.db.sql(
		"select name, from_doctype, from_name from `tabLife Link` where to_doctype=%s and to_name=%s", (doc.doctype, doc.name), as_dict=True
	)
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
			from lifeos import index
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
	rows = frappe.db.sql(
		"select to_doctype, to_name, link_text from `tabLife Link` where from_doctype=%s and from_name=%s",
		(doc.doctype, doc.name), as_dict=True,
	)
	pinned = {m.group(1).strip().lower() for m in LINK_RE.finditer("\n".join(doc.get(f) or "" for f in md_fields(doc))) if m.group(2)}
	out = []
	for r in rows:
		ambiguous = False
		if r.to_doctype == "Life Note" and (r.link_text or "").lower() not in pinned:
			ambiguous = frappe.db.count("Life Note", {"space": doc.space, "collection": "Wiki", "title": r.link_text}) > 1
		out.append({"text": r.link_text, "doctype": r.to_doctype, "name": r.to_name, "ambiguous": ambiguous,
			"title": title_of(r.to_doctype, r.to_name), "route": route_of(r.to_doctype, r.to_name)})
	return out
