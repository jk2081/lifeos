"""Life Index: one row per filed record, read by the Timeline, area pages, Archive, chats report and search."""
import hashlib

import frappe
from frappe.utils import getdate, now

from lifeos.constants import INDEXED_DOCTYPES

KINDS = {
	"Life Inbox Item": "Inbox", "Life Task": "Task", "Life Note": "Note", "Life Vault Document": "Document",
	"Life Chat Log": "Chat",
}
COLUMNS = ["name", "creation", "modified", "modified_by", "owner", "docstatus", "idx", "ref_doctype", "ref_name", "space",
	"area", "also_in_csv", "goal", "record_date", "title", "search_text", "is_archived", "kind", "status", "record_owner",
	"media_kind", "source_system", "intent", "assistant", "collection", "thumbnail", "vault_locked", "last_opened_on"]
NULLABLE = ("last_opened_on",)
# Characters of a record's text kept for search: transcripts, extracted text, summaries and page Markdown (UX fixes, set 4)
SEARCH_CAP = 60000


def row_name(doctype, name, kind):
	return hashlib.sha1(f"{doctype}|{name}|{kind}".encode()).hexdigest()[:20]


def _csv(values):
	values = [v for v in values if v]
	return "," + ",".join(values) + "," if values else ""


def _text(*parts):
	return "\n".join(p for p in parts if p)[:SEARCH_CAP]


def build_rows(doc) -> list[dict]:
	"""Return the index rows for one record."""
	dt = doc.doctype
	base = {
		"ref_doctype": dt, "ref_name": doc.name, "space": doc.space, "kind": KINDS[dt],
		"area": doc.get("area") or "", "goal": doc.get("goal") or "",
		"also_in_csv": _csv([r.area for r in doc.get("also_in") or []]),
		"is_archived": 1 if doc.get("is_archived") else 0,
		"status": doc.get("status") or "", "record_owner": doc.owner,
		"record_date": getdate(doc.creation), "title": (doc.get("title") or "")[:255], "search_text": "",
		"media_kind": "", "source_system": "", "intent": "", "assistant": "", "collection": "", "thumbnail": "",
		"vault_locked": 1 if dt == "Life Vault Document" or doc.get("is_sensitive") else 0,
	}
	rows = [base]
	if dt == "Life Inbox Item":
		base["record_date"] = getdate(doc.received_on or doc.creation)
		base["search_text"] = _text(doc.title, doc.instruction, doc.summary_md, doc.transcript_md, doc.raw_text)
		base.update({"media_kind": doc.media_kind or "", "source_system": doc.source_system or "", "intent": doc.intent or "",
			"thumbnail": doc.thumbnail or "", "vault_locked": 1 if doc.vault_document or doc.get("is_sensitive") else 0})
	elif dt == "Life Task":
		base["search_text"] = _text(doc.notes_md, doc.waiting_on)
		if doc.status == "Done" and doc.completed_on:
			rows.append({**base, "kind": "Task Done", "record_date": getdate(doc.completed_on), "search_text": ""})
	elif dt == "Life Note":
		base["search_text"] = _text(doc.summary, doc.content_md)
		base["collection"] = doc.collection or "My notes"
		base["last_opened_on"] = doc.get("last_opened_on") or getdate(doc.creation)
		if doc.page_date:  # a photographed journal page is dated the day it was written
			base["record_date"] = getdate(doc.page_date)
	elif dt == "Life Vault Document":
		base["search_text"] = _text(doc.doc_type, doc.notes_md)
	elif dt == "Life Chat Log":
		base["record_date"] = getdate(doc.date)
		base["search_text"] = _text(doc.summary_md, *[r.text for r in doc.open_items or []], doc.transcript_md)
		base.update({"media_kind": "Chat", "source_system": doc.source_system or "", "assistant": doc.assistant or ""})
		base["status"] = "Open" if any(r.status == "Open" for r in doc.open_items or []) else ""
	return rows


def _write(rows):
	if not rows:
		return
	ts = now()
	values = []
	for r in rows:
		head = (row_name(r["ref_doctype"], r["ref_name"], r["kind"]), ts, ts, frappe.session.user, r["record_owner"] or frappe.session.user, 0, 0)
		values.append(head + tuple(r.get(c) if r.get(c) is not None or c in NULLABLE else "" for c in COLUMNS[7:]))
	cols = ", ".join(f"`{c}`" for c in COLUMNS)
	updates = ", ".join(f"`{c}`=values(`{c}`)" for c in COLUMNS if c not in ("name", "creation", "owner"))
	placeholders = ", ".join(["(" + ", ".join(["%s"] * len(COLUMNS)) + ")"] * len(values))
	flat = [v for row in values for v in row]
	# nosemgrep: frappe-sql-format-injection -- column names come from the fixed COLUMNS list; every value is a %s parameter
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
	return total


def also_in_sql(param="area", alias=""):
	"""SQL for "this index row's record is also filed in the area(s) named by %(param)s" (one name, or a tuple with `in`).
	It reads the indexed child table Life Also In, so it never scans the rows' text."""
	op = "in" if param.endswith("ids") else "="
	return (f"({alias}ref_doctype, {alias}ref_name) in (select ai.parenttype, ai.parent from `tabLife Also In` ai "
		f"where ai.area {op} %({param})s)")


def ensure_indexes():
	"""Composite and FULLTEXT indexes that DocType JSON cannot describe."""
	frappe.db.add_index("Life Index", ["space", "record_date"], "life_index_space_date")
	frappe.db.add_index("Life Index", ["space", "area", "is_archived"], "life_index_space_area")
	frappe.db.add_index("Life Index", ["space", "goal"], "life_index_space_goal")
	frappe.db.add_index("Life Index", ["ref_doctype", "ref_name"], "life_index_ref")
	frappe.db.add_index("Life Link", ["from_doctype", "from_name"], "life_link_from")
	frappe.db.add_index("Life Link", ["to_doctype", "to_name"], "life_link_to")
	frappe.db.add_index("Life Habit Log", ["space", "date"], "life_habit_log_space_date")
	frappe.db.add_index("Life Task", ["space", "status", "due_date"], "life_task_space_status_due")
	frappe.db.add_unique("Life Action Log", ["action_id", "date"], "life_action_log_unique")
	frappe.db.add_unique("Life Habit Log", ["habit", "date"], "life_habit_log_unique")
	# UX fixes, set 4: original IDs are unique per space and system; one connection per space and system
	frappe.db.add_unique("Life Inbox Item", ["space", "source_system", "external_id"], "life_inbox_external_id")
	frappe.db.add_unique("Life Chat Log", ["space", "source_system", "external_id"], "life_chat_external_id")
	# issue 58: several Gmail mailboxes share the system "gmail", so the mailbox is part of the key (empty for every other system; the
	# document's own check keeps one connection for each of those)
	if frappe.db.has_index("tabLife Connection", "life_connection_system"):
		frappe.db.sql_ddl("alter table `tabLife Connection` drop index life_connection_system")
	frappe.db.add_unique("Life Connection", ["space", "system", "mailbox"], "life_connection_mailbox")
	frappe.db.add_index("Life Index", ["space", "ref_doctype", "is_archived", "record_date"], "life_index_space_type_date")
	# covering indexes for the counts (tab counts, totals, the timeline's and an area's counts): with text of up to 60,000
	# characters a row, a count must not read the rows themselves
	# the Outbox (set 7): what came in by creation, and exits by period
	for dt in ("Life Task", "Life Goal", "Life Inbox Item"):
		frappe.db.add_index(dt, ["space", "creation", "area"], f"{dt.lower().replace(' ', '_')}_space_creation")
	if frappe.db.table_exists("Life Exit"):
		frappe.db.add_index("Life Exit", ["space", "reversed", "exited_on", "pile", "area"], "life_exit_period_area")
		frappe.db.add_index("Life Exit", ["record_doctype", "record_name", "reversed"], "life_exit_record")
	frappe.db.add_index("Life Index", ["space", "kind", "is_archived", "ref_doctype", "media_kind", "status", "vault_locked"], "life_index_counts")
	frappe.db.add_index("Life Index", ["space", "area", "is_archived", "kind", "ref_doctype", "vault_locked"], "life_index_area_counts")
	frappe.db.add_index("Life Index", ["space", "is_archived", "record_date", "modified"], "life_index_timeline")
	frappe.db.add_index("Life Index", ["space", "is_archived", "area", "ref_doctype", "ref_name", "kind", "vault_locked"], "life_index_area_refs")
	# "also filed in" is matched through the records' own child rows, not by scanning also_in_csv (see also_in_sql)
	frappe.db.add_index("Life Also In", ["area", "parenttype", "parent"], "life_also_in_area")
	frappe.db.add_index("Life Wiki Change", ["space", "changed_on"], "life_wiki_change_space_on")
	# pre-step 6: the Notes list and its "not opened in 90 days" count on Today; the Inbox's state tabs and totals
	frappe.db.add_index("Life Index", ["space", "kind", "collection", "is_archived", "last_opened_on", "modified"], "life_index_notes")
	frappe.db.add_index("Life Inbox Item", ["space", "is_archived", "status", "received_on"], "life_inbox_space_state")
	# goals with no tasks (Today), and when each agent last filed something (Settings)
	frappe.db.add_index("Life Task", ["goal", "status"], "life_task_goal_status")
	frappe.db.add_index("Life Proposal", ["owner", "creation"], "life_proposal_owner_creation")
	frappe.db.add_index("Life Chat Log", ["owner", "creation"], "life_chat_owner_creation")
	if not frappe.db.sql("show index from `tabLife Index` where Key_name='life_index_fulltext'"):
		frappe.db.sql_ddl("alter table `tabLife Index` add fulltext index `life_index_fulltext` (`title`, `search_text`)")
