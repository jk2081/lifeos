"""Issue 10: the item page. What came of one inbox item (the records made from it, with their state) and what is related
to it (wiki pages and chat logs that cite it, the meetings it is linked to). Every record is checked for read access."""
import frappe
from frappe.query_builder import functions as fn

from lifeos.library import links
from lifeos import permissions

ITEM = "Life Inbox Item"
LIMIT = 100
# records that keep the item they came from in their own `inbox_item` field, besides those named by accepted proposals
BACKREF = ("Life Task", "Life Note", "Life Vault Document")
KIND_OF = {"Life Task": "Task", "Life Note": "Note",
	"Life Vault Document": "Document", "Event": "Event", "Life Goal": "Goal", "Life Habit Log": "Habit",
	"Life Action Log": "Week tick"}


def _readable(doctype, name, space):
	if not frappe.db.exists(doctype, name):
		return False
	if doctype == permissions.VAULT and permissions.vault_hidden(space):
		return False
	if doctype in permissions.SENSITIVE_DOCTYPES and permissions.vault_hidden(space) and frappe.db.get_value(doctype, name, "is_sensitive"):
		return False
	return frappe.has_permission(doctype, "read", doc=name)


def _state(doctype, name):
	"""A word or two on where the record stands now, and the date that goes with it (ISO, or empty)."""
	if doctype == "Life Task":
		d = frappe.db.get_value(doctype, name, ["status", "due_date", "is_archived"], as_dict=True)
		return ("Archived" if d.is_archived else d.status or "Open"), str(d.due_date or "")
	if doctype == "Life Note":
		d = frappe.db.get_value(doctype, name, ["collection", "is_archived"], as_dict=True)
		return ("Archived" if d.is_archived else "Wiki page" if d.collection == "Wiki" else "In My notes"), ""
	if doctype == "Event":
		return "Event", str(frappe.db.get_value(doctype, name, "starts_on") or "")[:16]
	if doctype == "Life Goal":
		d = frappe.db.get_value(doctype, name, ["outcome", "is_archived"], as_dict=True)
		return ("Archived" if d.is_archived else d.outcome or "In Progress"), ""
	if doctype == permissions.VAULT:
		return "In the Vault", str(frappe.db.get_value(doctype, name, "expiry_date") or "")
	return "Made", ""


def _entry(kind, doctype, name, title=None):
	state, date = _state(doctype, name)
	own = frappe.db.get_value("Event", name, "subject") if doctype == "Event" else links.title_of(doctype, name)
	return {"kind": kind, "doctype": doctype, "name": name, "title": own or title or name,
		"state": state, "date": date, "route": None if doctype == "Event" else links.route_of(doctype, name), "ref": _ref(doctype, name)}


def _ref(doctype, name):
	"""The pane reference for records whose server route does not carry one (events)."""
	return f"event:{name}" if doctype == "Event" else None


def came_of_it(doc):
	"""The records made from this item: those of accepted proposals, then any other record that names it as its source."""
	out, seen = [], set()
	for p in frappe.get_all("Life Proposal", filters={"inbox_item": doc.name, "status": "Accepted", "created_name": ("is", "set")},
			fields=["kind", "preview", "created_doctype", "created_name"], order_by="sort_order asc, creation asc", limit=LIMIT):
		key = (p.created_doctype, p.created_name)
		if key in seen or not _readable(*key, doc.space):
			continue
		seen.add(key)
		out.append(_entry(KIND_OF.get(p.created_doctype, p.kind), *key, title=p.preview))
	for dt in BACKREF:
		for name in frappe.get_all(dt, filters={"inbox_item": doc.name}, pluck="name", order_by="creation asc", limit=LIMIT):
			if (dt, name) in seen or not _readable(dt, name, doc.space):
				continue
			seen.add((dt, name))
			out.append(_entry(KIND_OF[dt], dt, name))
	return out[:LIMIT]


def related(doc):
	"""Wiki pages (and notes) that cite the item, chat logs that cite it or it was filed with, and the meetings it is linked to."""
	pages = []
	n, s = frappe.qb.DocType("Life Note"), frappe.qb.DocType("Life Note Source")
	cites = (frappe.qb.from_(s).join(n).on(n.name == s.parent).select(n.name, n.collection).distinct().where((s.parenttype == "Life Note") & (s.source_doctype == ITEM) & (s.source_name == doc.name))
		.orderby(n.title).limit(LIMIT).run(as_dict=True))  # system: each page is checked with _readable below
	for n in cites:
		if _readable("Life Note", n.name, doc.space):
			pages.append(_entry("Wiki page" if n.collection == "Wiki" else "Note", "Life Note", n.name))
	chats = []
	names = [doc.job_chat] if doc.get("job_chat") else []
	names += frappe.get_all("Life Chat Log", filters={"inbox_item": doc.name}, pluck="name", limit=LIMIT)
	names += frappe.get_all("Life Link", filters={"from_doctype": "Life Chat Log", "to_doctype": ITEM, "to_name": doc.name}, pluck="from_name", limit=LIMIT)
	for name in dict.fromkeys(names):
		if _readable("Life Chat Log", name, doc.space):
			chats.append({**_entry("Chat", "Life Chat Log", name), "state": frappe.db.get_value("Life Chat Log", name, "assistant") or "Chat",
				"date": str(frappe.db.get_value("Life Chat Log", name, "date") or "")})
	meetings = []
	for event in frappe.get_all("Life Meeting Link", filters={"record_doctype": ITEM, "record_name": doc.name, "removed": 0},
			pluck="event", order_by="creation asc", limit=LIMIT):
		if _readable("Event", event, doc.space):
			meetings.append(_entry("Meeting", "Event", event))
	return {"pages": pages, "chats": chats, "meetings": meetings}
