"""Library > People (issue 25): one row per person or organisation, and a page for each with who they are and where they are mentioned.

A person or organisation is a Life Person. Who they are is the text of the wiki page linked to them. "Mentioned in" is read from
Life Index (captures, notes, tasks, chats) and from meetings by the person's name or another name they go by, plus the tasks that
are waiting on them or delegated to them by link. The Vault's rules apply: a sensitive item is left out for a user the Vault is closed to."""
import re

import frappe
from frappe import _
from frappe.query_builder import Order

from lifeos.api import pages
from lifeos.library import briefs, people as rules, subjects
from lifeos import permissions
from lifeos.api.timeline import index_where
from lifeos.api.utils import count_by, descendants, list_query, names_map, page
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


def _mentions(space, person, limit=MENTION_CAP, linked=()):
	"""Where a person is mentioned, newest first: [{ref, doctype, name, kind, title, date, how}], and how many there are in all. `linked` is what the
	Brain or the owner linked to them (`subjects.timeline`): those count as mentions too."""
	found = {}
	for e in linked:
		found[(e["doctype"], e["name"])] = {"doctype": e["doctype"], "name": e["name"], "kind": e["kind"], "title": e["title"] or "Untitled", "date": e["date"], "at": e["date"],
			"how": None, "ref": e["ref"]}
	terms = _terms(person)
	if terms:
		pat = _pattern(terms)
		x = frappe.qb.DocType("Life Index")
		where = index_where(space, [x.is_archived == 0, x.kind.isin(INDEX_KINDS), x.ref_name != (person.get("wiki_page") or ""), x.title.regexp(pat) | x.search_text.regexp(pat)])
		query = list_query("Life Index", ["ref_doctype", "ref_name", "kind", "title", "record_date", "modified"], where, [(x.record_date, Order.desc), (x.modified, Order.desc)])
		for r in query.limit(limit).run(as_dict=True):
			found[(r.ref_doctype, r.ref_name)] = {"doctype": r.ref_doctype, "name": r.ref_name, "kind": LABEL[r.kind], "title": r.title or "Untitled",
				"date": str(r.record_date), "at": str(r.modified), "how": None, "ref": REF[r.kind] + r.ref_name}
		e = frappe.qb.DocType("Event")
		events = frappe.qb.from_(e).select(e.name, e.subject, e.starts_on).where((e.life_space == space) & (e.subject.regexp(pat) | e.description.regexp(pat)))  # system: the person's mentions in the space, as the Timeline reads them
		for ev in events.orderby(e.starts_on, order=Order.desc).limit(limit).run(as_dict=True):
			found[("Event", ev.name)] = {"doctype": "Event", "name": ev.name, "kind": "Meeting", "title": ev.subject or "Meeting", "date": str(ev.starts_on)[:10],
				"at": str(ev.starts_on), "how": None, "ref": "event:" + ev.name}
	for field, how in (("waiting_on_person", "Waiting on them"), ("delegated_to", "Delegated to them")):
		for t in frappe.get_list("Life Task", filters={"space": space, field: person["name"], "is_archived": 0}, fields=["name", "title", "creation", "modified"], limit=limit):
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
		frappe.throw(_("kind must be Person or Organisation."), title=_("Unknown kind of contact"))
	filters = {"space": space}
	if kind:
		filters["kind"] = kind
	if area:
		filters["area"] = ("in", descendants(space, area))
	or_filters = None
	q = (q or "").strip()[:200]
	if q:
		orgs = frappe.get_list("Life Person", filters={"space": space, "kind": "Organisation", "full_name": ("like", _like(q))}, pluck="name")
		or_filters = [["full_name", "like", _like(q)], ["aliases", "like", _like(q)], ["role", "like", _like(q)], ["relation", "like", _like(q)]]
		if orgs:
			or_filters.append(["organisation", "in", orgs])
	fields = ["name", "full_name", "kind", "relation", "role", "organisation", "area", "wiki_page"]
	rows = frappe.get_list("Life Person", filters=filters, or_filters=or_filters, fields=fields, order_by="full_name asc", limit_start=start, limit_page_length=page_length)
	total = len(frappe.get_list("Life Person", filters=filters, or_filters=or_filters, pluck="name", limit=100000))
	counts = {k: frappe.db.count("Life Person", {"space": space, "kind": k}) for k in KINDS}
	org_names = names_map("Life Person", [r.organisation for r in rows], "full_name")
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	summaries = names_map("Life Note", [r.wiki_page for r in rows], "summary")
	p = frappe.qb.DocType("Life Person")
	members = count_by("Life Person", "organisation", [p.space == space, p.organisation.isin([r.name for r in rows] or [""])])
	aliases = names_map("Life Person", [r.name for r in rows], "aliases")
	out = []
	for r in rows:
		got, n = _mentions(space, {**r, "aliases": aliases.get(r.name)}, limit=1)
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
	notes, tasks (also those waiting on them or delegated to them), meetings and chats, newest first (at most 100; `mentioned_total` is all).
	The Library's page and the Drawer's layer both read this: the Drawer also shows `brief` (the Brain's, or null), `open` (linked open tasks and
	upcoming events), `related` (the organisation, its people, or people often with them, each with `why`), `email`, `phone` and `path`."""
	doc = permissions.get_doc_checked("Life Person", name, "read")
	p = doc.as_dict()
	who = _text(p)
	mentioned, total = _mentions(doc.space, p, linked=[e for e in subjects.timeline("Life Person", doc.name)[0] if e.get("ref")])
	org = frappe.db.get_value("Life Person", doc.organisation, ["name", "full_name"], as_dict=True) if doc.organisation else None
	members = frappe.get_list("Life Person", filters={"space": doc.space, "organisation": doc.name}, fields=["name", "full_name", "role", "relation"], order_by="full_name asc", limit=500)
	linked = pages.linked_items("Life Person", doc.name)
	brief = briefs.read("Life Person", doc.name)
	return {"name": doc.name, "space": doc.space, "kind": doc.kind or "Person", "title": doc.full_name, "role": doc.role or doc.relation,
		"email": doc.email, "phone": doc.phone, "path": pages.area_path(doc.area), "brief": brief["md"] if brief else None,
		"open": pages.open_work("Life Person", doc, linked), "related": pages.related_people("Life Person", doc, linked),
		"aliases": split_aliases(doc.aliases), "area": doc.area, "area_name": frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None,
		"organisation": org, "people": [{"name": m.name, "title": m.full_name, "role": m.role or m.relation} for m in members],
		"wiki": who["page"], "text": who["text"], "mentioned": [{k: v for k, v in r.items() if k != "at"} for r in mentioned], "mentioned_total": total}


OPTIONS_CAP = 50


def _recent_people(space: str) -> list[str]:
	"""People used on tasks (delegated to, waiting on, handed off), most recently used first."""
	last: dict[str, object] = {}
	for field in ("delegated_to", "waiting_on_person"):
		for r in frappe.get_list("Life Task", filters={"space": space, field: ("is", "set")}, fields=[field + " as person", "modified"], order_by="modified desc", limit=500):
			if r.person not in last or r.modified > last[r.person]:
				last[r.person] = r.modified
	return sorted(last, key=lambda n: last[n], reverse=True)


@frappe.whitelist(methods=["GET"])
def options(space: str | None = None, q: str | None = None, kind: str | None = None, include: str | None = None):
	"""People to pick from, for a task's "waiting on" and "delegated to" and for Hand off: {rows: [{value, label, kind, organisation, email}], more}.
	`kind` is Person unless Organisation is asked for. Without `q`: the 50 most recently used on tasks first, then by name, and `more` says there are others.
	With `q`: the best 50 matches, name, other names and email first, then people at an organisation whose name matches. `include` adds that person (the one already picked)."""
	space = permissions.resolve_space(space)
	kind = kind if kind in KINDS else "Person"
	filters = {"space": space, "kind": kind}
	fields = ["name", "full_name", "kind", "organisation", "email"]
	q = (q or "").strip()[:200]
	if q:
		own = frappe.get_list("Life Person", filters=filters, or_filters=[["full_name", "like", _like(q)], ["aliases", "like", _like(q)], ["email", "like", _like(q)]],
			fields=fields, order_by="full_name asc", limit=OPTIONS_CAP + 1)
		rows = own[:OPTIONS_CAP]
		orgs = frappe.get_list("Life Person", filters={"space": space, "kind": "Organisation", "full_name": ("like", _like(q))}, pluck="name", limit=200)
		if orgs and len(rows) < OPTIONS_CAP:
			seen = {r.name for r in rows}
			rest = frappe.get_list("Life Person", filters={**filters, "organisation": ("in", orgs)}, fields=fields, order_by="full_name asc", limit=OPTIONS_CAP + 1)
			rows += [r for r in rest if r.name not in seen][:OPTIONS_CAP - len(rows)]
		more = len(own) > OPTIONS_CAP
	else:
		recent = [n for n in _recent_people(space)][:200]
		by_name = {r.name: r for r in frappe.get_list("Life Person", filters={**filters, "name": ("in", recent)}, fields=fields, limit=200)} if recent else {}
		rows = [by_name[n] for n in recent if n in by_name][:OPTIONS_CAP]
		if len(rows) < OPTIONS_CAP:
			taken = [r.name for r in rows]
			rows += frappe.get_list("Life Person", filters={**filters, **({"name": ("not in", taken)} if taken else {})}, fields=fields, order_by="full_name asc", limit=OPTIONS_CAP - len(rows))
		more = frappe.db.count("Life Person", filters) > len(rows)
	if include and include not in {r.name for r in rows}:
		rows += frappe.get_list("Life Person", filters={**filters, "name": include}, fields=fields, limit=1)
	org_names = names_map("Life Person", [r.organisation for r in rows], "full_name")
	return {"rows": [{"value": r.name, "label": r.full_name, "kind": r.kind or "Person", "organisation": org_names.get(r.organisation), "email": r.email or None} for r in rows], "more": more}
