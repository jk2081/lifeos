"""Links between records: backlinks, the [[ picker, and link resolution for rendering."""
import frappe

from lifeos.library import links as rules
from lifeos import permissions
from lifeos.constants import LINKABLE

# (doctype, field, why) pairs: records tied to a record by a field
FIELD_TIES = {
	"Life Inbox Item": [
		("Life Task", "inbox_item", "created from this item"), ("Life Note", "inbox_item", "created from this item"),
		("Life Vault Document", "inbox_item", "created from this item"), ("Life Chat Log", "inbox_item", "created from this item"),
	],
	"Life Goal": [("Life Task", "goal", "task for this goal"), ("Life Goal", "carried_from", "carried into the next cycle"),
		("Life Note", "goal", "filed under this goal"), ("Life Vault Document", "goal", "filed under this goal"),
		("Life Chat Log", "goal", "filed under this goal"), ("Life Goal", "serves", "serves this goal")],
	"Life Note": [("Life Note", "parent_note", "sub-note")],
	"Life Task": [("Life Task", "carried_from", "carried forward from this task")],
	"Life Person": [("Life Vault Document", "holder", "document held")],
}
KIND = {"Life Task": "Task", "Life Note": "Note", "Life Vault Document": "Document", "Life Chat Log": "Chat", "Life Goal": "Goal",
	"Life Person": "Person", "Life Inbox Item": "Inbox item"}


def _title(doctype, name):
	return rules.title_of(doctype, name)


@frappe.whitelist(methods=["GET"])
def backlinks(doctype: str, name: str):
	"""Records that link to this one with [[Title]], plus records tied to it by a field."""
	doc = permissions.get_doc_checked(doctype, name)
	out, seen = [], set()

	def add(dt, n, why):
		if (dt, n) in seen or not frappe.db.exists(dt, n):
			return
		if dt == permissions.VAULT and permissions.vault_hidden(frappe.db.get_value(dt, n, "space")):
			return
		if dt in permissions.SENSITIVE_DOCTYPES:  # a sensitive item is closed to an agent while its space's switch is off (set 6)
			row = frappe.db.get_value(dt, n, ["space", "is_sensitive"], as_dict=True)
			if row.is_sensitive and permissions.vault_hidden(row.space):
				return
		seen.add((dt, n))
		out.append({"doctype": dt, "name": n, "title": _title(dt, n), "kind": KIND.get(dt, dt.replace("Life ", "")),
			"why": why, "route": rules.route_of(dt, n)})

	for r in frappe.get_list("Life Link", filters={"to_doctype": doctype, "to_name": name, "space": doc.space, "origin": ("in", ("Text", ""))}, fields=["from_doctype", "from_name"], limit=100):
		add(r.from_doctype, r.from_name, "links here")
	for dt, field, why in FIELD_TIES.get(doctype, []):
		for n in frappe.get_list(dt, filters={field: name, "space": doc.space}, pluck="name", limit=50, order_by="creation desc"):
			add(dt, n, why)
	for field, why in (("inbox_item", "source"), ("goal", "goal"), ("carried_from", "carried from"), ("parent_note", "parent note")):
		if doc.meta.has_field(field) and doc.get(field):
			add(doc.meta.get_field(field).options, doc.get(field), why)
	return out


@frappe.whitelist(methods=["GET"])
def suggest(space: str | None = None, text: str | None = "", limit: int | None = 12):
	"""Records for the [[ picker: notes, tasks, people, vault documents, chat logs and goals whose title matches."""
	space = permissions.resolve_space(space)
	text = (text or "").strip()
	limit = min(int(limit or 12), 30)
	out = []
	for dt, field in LINKABLE.items():
		if dt == permissions.VAULT and permissions.vault_hidden(space):
			continue
		filters = {"space": space}
		if dt in permissions.SENSITIVE_DOCTYPES and permissions.vault_hidden(space):
			filters["is_sensitive"] = 0  # sensitive items are closed to the agent while the space's switch is off
		if text:
			filters[field] = ("like", f"%{text}%")
		for r in frappe.get_list(dt, filters=filters, fields=["name", f"{field} as title"], order_by="modified desc", limit=limit):
			out.append({"doctype": dt, "name": r.name, "title": r.title, "kind": KIND[dt]})
	out.sort(key=lambda r: (not r["title"].lower().startswith(text.lower()), len(r["title"])))
	out = out[:limit]
	titles = [r["title"].lower() for r in out]
	for r in out:  # two records with one title: the link must carry the id
		r["ambiguous"] = titles.count(r["title"].lower()) > 1 or len(rules.candidates(space, r["title"])) > 1
		r["insert"] = f"[[{r['title']}#{r['name']}]]" if r["ambiguous"] else f"[[{r['title']}]]"
	return out


@frappe.whitelist(methods=["GET"])
def outgoing(doctype: str, name: str):
	"""The stored links of a record, with each target's current title, for rendering."""
	doc = permissions.get_doc_checked(doctype, name)
	return rules.outgoing(doc)
