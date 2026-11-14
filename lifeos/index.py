"""Life Index: one row per filed record, read by the Timeline, area pages, Archive, chats report and search."""
import hashlib

import frappe
from frappe.utils import getdate, now

from lifeos.constants import INDEXED_DOCTYPES

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
KINDS = {
	"Life Inbox Item": "Inbox", "Life Task": "Task", "Life Note": "Note", "Life Vault Document": "Document",
	"Life Chat Log": "Chat", "Life Journal Page": "Journal Page", "Life Check-in": "Check-in", "Life Month Plan": "Month Plan",
}
COLUMNS = ["name", "creation", "modified", "modified_by", "owner", "docstatus", "idx", "ref_doctype", "ref_name", "space",
	"area", "also_in_csv", "project", "tags_csv", "record_date", "title", "search_text", "is_archived", "kind", "status", "record_owner"]


def row_name(doctype, name, kind):
	return hashlib.sha1(f"{doctype}|{name}|{kind}".encode()).hexdigest()[:20]


def _csv(values):
	values = [v for v in values if v]
	return "," + ",".join(values) + "," if values else ""


def _text(*parts):
	return "\n".join(p for p in parts if p)[:20000]


def build_rows(doc) -> list[dict]:
	"""Return the index rows for one record."""
	dt = doc.doctype
	base = {
		"ref_doctype": dt, "ref_name": doc.name, "space": doc.space, "kind": KINDS[dt],
		"area": doc.get("area") or "", "project": doc.get("project") or "",
		"also_in_csv": _csv([r.area for r in doc.get("also_in") or []]),
		"tags_csv": _csv([r.tag for r in doc.get("tags") or []]),
		"is_archived": 1 if doc.get("is_archived") else 0,
		"status": doc.get("status") or "", "record_owner": doc.owner,
		"record_date": getdate(doc.creation), "title": (doc.get("title") or "")[:255], "search_text": "",
	}
	rows = [base]
	if dt == "Life Inbox Item":
		base["record_date"] = getdate(doc.received_on or doc.creation)
		base["search_text"] = _text(doc.instruction, doc.summary_md, doc.transcript_md, doc.raw_text)
	elif dt == "Life Task":
		base["search_text"] = _text(doc.notes_md, doc.waiting_on)
		if doc.status == "Done" and doc.completed_on:
			rows.append({**base, "kind": "Task Done", "record_date": getdate(doc.completed_on), "search_text": ""})
	elif dt == "Life Note":
		base["search_text"] = _text(doc.content_md)
	elif dt == "Life Vault Document":
		base["search_text"] = _text(doc.doc_type, doc.notes_md)
	elif dt == "Life Chat Log":
		base["record_date"] = getdate(doc.date)
		base["search_text"] = _text(doc.summary_md, *[r.text for r in doc.open_items or []])
		base["status"] = "Open" if any(r.status == "Open" for r in doc.open_items or []) else ""
	elif dt == "Life Journal Page":
		base["record_date"] = getdate(doc.page_date)
		base["title"] = f"Journal page {doc.page_number}" if doc.page_number else "Journal page"
		base["search_text"] = _text(doc.transcript_md)
	elif dt == "Life Check-in":
		base["record_date"] = getdate(doc.date)
		base["title"] = "Check-in"
		base["search_text"] = _text(doc.reflection_md, *[r.note for r in doc.scores or []])
	elif dt == "Life Month Plan":
		base["record_date"] = getdate(f"{doc.year}-{int(doc.month):02d}-01")
		base["title"] = f"Month plan, {MONTHS[int(doc.month) - 1]} {doc.year}"
		base["search_text"] = _text(doc.mindsweep_md, doc.projects_md, *[r.title for r in doc.goals or []])
	return rows


def _write(rows):
	if not rows:
		return
	ts = now()
	values = []
	for r in rows:
		values.append((
			row_name(r["ref_doctype"], r["ref_name"], r["kind"]), ts, ts, frappe.session.user, r["record_owner"] or frappe.session.user, 0, 0,
			r["ref_doctype"], r["ref_name"], r["space"], r["area"], r["also_in_csv"], r["project"], r["tags_csv"],
			r["record_date"], r["title"], r["search_text"], r["is_archived"], r["kind"], r["status"], r["record_owner"],
		))
	cols = ", ".join(f"`{c}`" for c in COLUMNS)
	updates = ", ".join(f"`{c}`=values(`{c}`)" for c in COLUMNS if c not in ("name", "creation", "owner"))
	placeholders = ", ".join(["(" + ", ".join(["%s"] * len(COLUMNS)) + ")"] * len(values))
	flat = [v for row in values for v in row]
	frappe.db.sql(f"insert into `tabLife Index` ({cols}) values {placeholders} on duplicate key update {updates}", flat)


def update(doc):
	rows = build_rows(doc)
	keep = [row_name(r["ref_doctype"], r["ref_name"], r["kind"]) for r in rows]
	frappe.db.sql(
		"delete from `tabLife Index` where ref_doctype=%s and ref_name=%s and name not in %s", (doc.doctype, doc.name, keep)
	)
	_write(rows)


def remove(doctype, name):
	frappe.db.sql("delete from `tabLife Index` where ref_doctype=%s and ref_name=%s", (doctype, name))


def rebuild():
	"""Rebuild the whole index from the records. Run: bench --site SITE execute lifeos.index.rebuild"""
	frappe.db.sql("delete from `tabLife Index`")
	total = 0
	for dt in INDEXED_DOCTYPES:
		start = 0
		while True:
			names = frappe.get_all(dt, pluck="name", order_by="creation asc", limit_start=start, limit=500)
			if not names:
				break
			rows = []
			for name in names:
				rows.extend(build_rows(frappe.get_doc(dt, name)))
			for i in range(0, len(rows), 200):
				_write(rows[i : i + 200])
			total += len(rows)
			start += 500
	frappe.db.commit()
	return total


def ensure_indexes():
	"""Composite and FULLTEXT indexes that DocType JSON cannot describe."""
	frappe.db.add_index("Life Index", ["space", "record_date"], "life_index_space_date")
	frappe.db.add_index("Life Index", ["space", "area", "is_archived"], "life_index_space_area")
	frappe.db.add_index("Life Index", ["space", "project"], "life_index_space_project")
	frappe.db.add_index("Life Index", ["ref_doctype", "ref_name"], "life_index_ref")
	frappe.db.add_index("Life Link", ["from_doctype", "from_name"], "life_link_from")
	frappe.db.add_index("Life Link", ["to_doctype", "to_name"], "life_link_to")
	frappe.db.add_index("Life Habit Log", ["space", "date"], "life_habit_log_space_date")
	frappe.db.add_index("Life Task", ["space", "status", "due_date"], "life_task_space_status_due")
	frappe.db.add_unique("Life Action Log", ["action_id", "date"], "life_action_log_unique")
	frappe.db.add_unique("Life Habit Log", ["habit", "date"], "life_habit_log_unique")
	if not frappe.db.sql("show index from `tabLife Index` where Key_name='life_index_fulltext'"):
		frappe.db.sql_ddl("alter table `tabLife Index` add fulltext index `life_index_fulltext` (`title`, `search_text`)")
