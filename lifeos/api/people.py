"""Library > People (issue 25): one row per person or organisation, and a page for each with who they are and where they are mentioned.

A person or organisation is a Life Person. Who they are is the text of the wiki page linked to them. "Mentioned in" is read from
Life Index (captures, notes, tasks, chats) and from meetings by the person's name or another name they go by, plus the tasks that
are waiting on them or delegated to them by link. The Vault's rules apply: a sensitive item is left out for a user the Vault is closed to."""
import re

import frappe
from frappe import _

from lifeos import people as rules
from lifeos import permissions
from lifeos.api.utils import descendants, names_map, page
from lifeos.life.doctype.life_person.life_person import split_aliases

KINDS = rules.KINDS
INDEX_KINDS = ("Inbox", "Note", "Task", "Chat")
LABEL = {"Inbox": "Capture", "Note": "Note", "Task": "Task", "Chat": "Chat", "Event": "Meeting"}
REF = {"Inbox": "source:", "Note": "note:", "Task": "task:", "Chat": "chat:", "Event": "event:"}
MENTION_CAP = 100


def _like(text: str) -> str:
	return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _pattern(names):
	"""A word-bounded match for any of the names, for MariaDB's REGEXP (so 'Rao' does not match 'Karaoke')."""
	return "(^|[^[:alnum:]_])(" + "|".join(re.escape(n) for n in names) + ")($|[^[:alnum:]_])"


def _terms(person) -> list[str]:
	"""The name, and the other names that are long enough not to match by accident."""
	names = rules.names_of(person)
	return [n for i, n in enumerate(names) if i == 0 or len(n) >= 3]


def _mentions(space, person, limit=MENTION_CAP):
	"""Where a person is mentioned, newest first: [{ref, doctype, name, kind, title, date, how}], and how many there are in all."""
	found = {}
	terms = _terms(person)
	if terms:
		values = {"space": space, "kinds": INDEX_KINDS, "pat": _pattern(terms), "wiki": person.get("wiki_page") or ""}
		guard = permissions.vault_guard(space, "x.")
		where = (f"x.space = %(space)s and x.is_archived = 0 and x.kind in %(kinds)s and x.ref_name != %(wiki)s{guard} "
			"and (x.title regexp %(pat)s or x.search_text regexp %(pat)s)")
		# nosemgrep: frappe-sql-format-injection -- the only formatted part is vault_guard's fixed SQL; every value is a parameter
		for r in frappe.db.sql(f"select x.ref_doctype, x.ref_name, x.kind, x.title, x.record_date, x.modified from `tabLife Index` x where {where} "
				"order by x.record_date desc, x.modified desc limit %(n)s", {**values, "n": limit}, as_dict=True):
			found[(r.ref_doctype, r.ref_name)] = {"doctype": r.ref_doctype, "name": r.ref_name, "kind": LABEL[r.kind], "title": r.title or "Untitled",
				"date": str(r.record_date), "at": str(r.modified), "how": None, "ref": REF[r.kind] + r.ref_name}
		for ev in frappe.db.sql("select name, subject, starts_on from `tabEvent` where life_space = %(space)s and (subject regexp %(pat)s or description regexp %(pat)s) "
				"order by starts_on desc limit %(n)s", {**values, "n": limit}, as_dict=True):
			found[("Event", ev.name)] = {"doctype": "Event", "name": ev.name, "kind": "Meeting", "title": ev.subject or "Meeting", "date": str(ev.starts_on)[:10],
				"at": str(ev.starts_on), "how": None, "ref": "event:" + ev.name}
	for field, how in (("waiting_on_person", "Waiting on them"), ("delegated_to", "Delegated to them")):
		for t in frappe.get_all("Life Task", filters={"space": space, field: person["name"], "is_archived": 0}, fields=["name", "title", "creation", "modified"], limit=limit):
			key = ("Life Task", t.name)
			row = found.setdefault(key, {"doctype": "Life Task", "name": t.name, "kind": "Task", "title": t.title, "date": str(t.creation.date()), "at": str(t.modified),
				"how": None, "ref": "task:" + t.name})
			row["how"] = how if not row["how"] else f"{row['how']}, {how.lower()}"
	rows = sorted(found.values(), key=lambda r: (r["date"], r["at"]), reverse=True)
	return rows[:limit], len(rows)


def _person_row(p, last, people_count, org_names, areas, summaries):
	line = summaries.get(p.wiki_page) or " · ".join(x for x in (p.role or p.relation, org_names.get(p.organisation)) if x)
	return {"name": p.name, "kind": p.kind or "Person", "letter": "O" if p.kind == "Organisation" else "P", "title": p.full_name, "line": line,
		"role": p.role or p.relation, "organisation": p.organisation, "organisation_name": org_names.get(p.organisation), "people_count": people_count.get(p.name, 0),
		"area": p.area, "area_name": areas.get(p.area), "wiki_page": p.wiki_page, "last": last}


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, kind: str | None = None, q: str | None = None, area: str | None = None, start: int | None = 0, page_length: int | None = 50):
	"""People and organisations of a space, by name. kind: Person or Organisation. q: a word in the name, another name, the role or the
	organisation. area (with its parts). Each row: name, kind, letter (P, O), title, line (one line about them), role, organisation_name,
	people_count (for an organisation), area_name, last (the newest thing that mentions them: ref, kind, title, date, or null).
	`total` is what the filters match; `counts` has Person and Organisation totals for the space."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	if kind and kind not in KINDS:
		frappe.throw(_("kind must be Person or Organisation."))
	filters = {"space": space}
	if kind:
		filters["kind"] = kind
	if area:
		filters["area"] = ("in", descendants(space, area))
	or_filters = None
	q = (q or "").strip()[:200]
	if q:
		orgs = frappe.get_all("Life Person", filters={"space": space, "kind": "Organisation", "full_name": ("like", _like(q))}, pluck="name")
		or_filters = [["full_name", "like", _like(q)], ["aliases", "like", _like(q)], ["role", "like", _like(q)], ["relation", "like", _like(q)]]
		if orgs:
			or_filters.append(["organisation", "in", orgs])
	fields = ["name", "full_name", "kind", "relation", "role", "organisation", "area", "wiki_page"]
	rows = frappe.get_all("Life Person", filters=filters, or_filters=or_filters, fields=fields, order_by="full_name asc", limit_start=start, limit_page_length=page_length)
	total = len(frappe.get_all("Life Person", filters=filters, or_filters=or_filters, pluck="name", limit=100000))
	counts = {k: frappe.db.count("Life Person", {"space": space, "kind": k}) for k in KINDS}
	org_names = names_map("Life Person", [r.organisation for r in rows], "full_name")
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	summaries = names_map("Life Note", [r.wiki_page for r in rows], "summary")
	members = dict(frappe.db.sql("select organisation, count(*) from `tabLife Person` where space = %s and organisation in %s group by organisation",
		(space, [r.name for r in rows] or [""])))
	out = []
	for r in rows:
		got, n = _mentions(space, {**r, "aliases": frappe.db.get_value("Life Person", r.name, "aliases")}, limit=1)
		last = {k: got[0][k] for k in ("ref", "kind", "title", "date")} if got else None
		out.append(_person_row(r, last, members, org_names, areas, summaries))
	return {"space": space, "rows": out, "total": total, "start": start, "page_length": page_length, "counts": counts}


def _text(person):
	"""Who they are: the linked wiki page's text, else the person's own notes."""
	if person.wiki_page and frappe.has_permission("Life Note", "read", person.wiki_page):
		note = frappe.db.get_value("Life Note", person.wiki_page, ["title", "summary", "content_md", "is_sensitive"], as_dict=True)
		if note and not (note.is_sensitive and permissions.vault_hidden(person.space)):
			return {"page": {"name": person.wiki_page, "title": note.title, "summary": note.summary}, "text": note.content_md or ""}
	return {"page": None, "text": person.notes_md or ""}


@frappe.whitelist(methods=["GET"])
def get(name: str):
	"""One person or organisation: who they are (the wiki page's text), their organisation or its people, and Mentioned in: captures,
	notes, tasks (also those waiting on them or delegated to them), meetings and chats, newest first (at most 100; `mentioned_total` is all)."""
	doc = permissions.get_doc_checked("Life Person", name, "read")
	p = doc.as_dict()
	who = _text(p)
	mentioned, total = _mentions(doc.space, p)
	org = frappe.db.get_value("Life Person", doc.organisation, ["name", "full_name"], as_dict=True) if doc.organisation else None
	members = frappe.get_all("Life Person", filters={"space": doc.space, "organisation": doc.name}, fields=["name", "full_name", "role", "relation"], order_by="full_name asc", limit=500)
	return {"name": doc.name, "space": doc.space, "kind": doc.kind or "Person", "title": doc.full_name, "role": doc.role or doc.relation,
		"aliases": split_aliases(doc.aliases), "area": doc.area, "area_name": frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None,
		"organisation": org, "people": [{"name": m.name, "title": m.full_name, "role": m.role or m.relation} for m in members],
		"wiki": who["page"], "text": who["text"], "mentioned": [{k: v for k, v in r.items() if k != "at"} for r in mentioned], "mentioned_total": total}


@frappe.whitelist(methods=["GET"])
def options(space: str | None = None, q: str | None = None, kind: str | None = None):
	"""People and organisations to pick from, for a task's "waiting on" and "delegated to": [{value, label, kind}], at most 50."""
	space = permissions.resolve_space(space)
	filters = {"space": space}
	if kind in KINDS:
		filters["kind"] = kind
	q = (q or "").strip()[:200]
	rows = frappe.get_all("Life Person", filters=filters, or_filters=[["full_name", "like", _like(q)], ["aliases", "like", _like(q)]] if q else None,
		fields=["name", "full_name", "kind"], order_by="full_name asc", limit=50)
	return [{"value": r.name, "label": r.full_name, "kind": r.kind or "Person"} for r in rows]
