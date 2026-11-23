"""Library > Everything (issue 23): notes, documents, people and chats in one list, newest first.

Notes and wiki pages, Vault documents and kept files, and chat logs are read from Life Index; people are Life Person
records (not indexed) and wiki pages about people or organisations (a wiki page whose summary starts with Person,
Organisation, Organization or People). Until the People issue (#25) lands, that is what the People tab holds.
The Vault's rules apply as everywhere: a sensitive item is left out for a user the Vault is closed to."""
import builtins

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder import functions as fn

from lifeos.review import counts
from lifeos import permissions
from lifeos.api.timeline import index_where
from lifeos.api.utils import area_criterion, count_where, flag, list_query, names_map, page
from lifeos.api.sources import agent_users

TABS = ("all", "notes", "documents", "people", "chats")
# the index rows each tab holds (a kept file is an inbox item whose media kind is Document)


def tab_criteria(x):
	"""The index rows each tab holds (a kept file is an inbox item whose media kind is Document), as criteria over the index table."""
	n = frappe.qb.DocType("Life Note")
	about_people = n.summary.like("Person%") | n.summary.like("Organi%") | n.summary.like("People%")
	people = (x.ref_doctype == "Life Note") & (x.collection == "Wiki") & x.ref_name.isin(frappe.qb.from_(n).select(n.name).where(about_people))
	document = (x.ref_doctype == "Life Vault Document") | ((x.ref_doctype == "Life Inbox Item") & (x.media_kind == "Document"))
	chat = x.ref_doctype == "Life Chat Log"
	note = (x.ref_doctype == "Life Note") & ~people
	return {"all": note | document | chat | people, "notes": note, "documents": document, "chats": chat, "people": people}


LETTER = {"note": "N", "person": "P", "document": "D", "chat": "C"}
REF = {"Life Note": "note:", "Life Vault Document": "vault:", "Life Chat Log": "chat:", "Life Inbox Item": "source:", "Life Person": "person:"}
FIELDS = ["ref_doctype", "ref_name", "title", "record_date", "area", "goal", "status", "media_kind", "source_system", "assistant", "intent", "vault_locked", "collection", "record_owner", "modified"]


def _like(text: str) -> str:
	return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _index_rows(space, tab, q, area, goal, source, include_archived, limit, unopened=False):
	x = frappe.qb.DocType("Life Index")
	where = [tab_criteria(x)[tab]]
	if not flag(include_archived):
		where.append(x.is_archived == 0)
	if q:
		where.append(x.title.like(_like(q)) | x.search_text.like(_like(q)))
	if area:
		where.append(area_criterion(space, area, x, also_in="index"))
	if goal:
		where.append(x.goal == ("" if goal == "none" else goal))
	if unopened:  # notes not opened in 90 days (the Library's "Not opened in 90 days" filter)
		un = frappe.qb.DocType("Life Note")
		where.append((x.ref_doctype == "Life Note") & x.ref_name.isin(frappe.qb.from_(un).select(un.name).where(un.last_opened_on <= counts.ago(90))))
	if source in ("me", "brain"):
		by_brain = x.record_owner.isin(agent_users()) | (x.collection == "Wiki")
		where.append(by_brain if source == "brain" else ~by_brain)
	elif source:
		where.append(x.source_system == source.lower())
	where = index_where(space, where)
	rows = list_query("Life Index", FIELDS, where, [(x.record_date, Order.desc), (x.modified, Order.desc)]).limit(limit).run(as_dict=True)
	total = count_where("Life Index", where)
	return rows, total


def _person_rows(space, tab, q, area, goal, source, include_archived, limit):
	"""Life Person records: no area or goal, so a filter on either leaves them out."""
	if tab not in ("all", "people") or area or goal or source not in (None, "", "me", "brain"):
		return [], 0
	filters = {"space": space}
	or_filters = None
	if q:
		or_filters = [["full_name", "like", _like(q)], ["relation", "like", _like(q)], ["notes_md", "like", _like(q)]]
	rows = frappe.get_list("Life Person", filters=filters, or_filters=or_filters, fields=["name", "full_name", "relation", "creation", "owner"],
		order_by="creation desc", limit=limit)
	agents = set(agent_users())
	if source in ("me", "brain"):
		rows = [r for r in rows if (r.owner in agents) == (source == "brain")]
	total = len(rows) if len(rows) < limit else len(frappe.get_list("Life Person", filters=filters, or_filters=or_filters, pluck="name"))
	return rows, total


def _decorate(rows):
	from lifeos.api.sources import decorate

	notes = [r.ref_name for r in rows if r.ref_doctype == "Life Note"]
	details = {n.name: n for n in frappe.get_list("Life Note", filters={"name": ("in", notes)}, fields=["name", "summary", "collection", "inbox_item"])} if notes else {}
	f, ns = frappe.qb.DocType("File"), frappe.qb.DocType("Life Note Source")
	files = dict(frappe.qb.from_(f).select(f.attached_to_name, fn.Count("*")).where((f.attached_to_doctype == "Life Note") & f.attached_to_name.isin(notes)).groupby(f.attached_to_name).run()) if notes else {}  # system: the notes were read above
	sources = {}
	if notes:
		for parent, dt, name in frappe.qb.from_(ns).select(ns.parent, ns.source_doctype, ns.source_name).where((ns.parenttype == "Life Note") & ns.parent.isin(notes)).orderby(ns.idx).run():  # system: the notes were read above
			sources.setdefault(parent, (dt, name))
	for n, d in details.items():
		if d.inbox_item and n not in sources:
			sources[n] = ("Life Inbox Item", d.inbox_item)
	made_from, by_doctype = {}, {}
	for n, (dt, name) in sources.items():
		if dt in ("Life Inbox Item", "Life Chat Log", "Life Note", "Life Vault Document"):
			by_doctype.setdefault(dt, []).append(name)
	titles = {dt: names_map(dt, names, "title") for dt, names in by_doctype.items()}
	for n, (dt, name) in sources.items():
		if dt in titles:
			made_from[n] = titles[dt].get(name)
	base = {(d["doctype"], d["name"]): d for d in decorate(rows)}
	out = []
	for r in rows:
		d = base[(r.ref_doctype, r.ref_name)]
		kind, line = "note", []
		if r.ref_doctype == "Life Note":
			det = details.get(r.ref_name)
			summary = (det.summary or "").strip() if det else ""
			wiki = bool(det and det.collection == "Wiki")
			if summary.lower().startswith(("person", "organi", "people")) and wiki:
				kind = "person"
				line = [summary]
			else:
				line = ["Wiki page" if wiki else "Note"]
				n_files = files.get(r.ref_name, 0)
				if n_files:
					line.append(f"{n_files} file{'' if n_files == 1 else 's'}")
				if made_from.get(r.ref_name):
					line.append(f"made from {made_from[r.ref_name]}")
			if wiki:
				line.append("kept by the Brain")
		elif r.ref_doctype == "Life Chat Log":
			kind = "chat"
			line = ["Chat", d.get("assistant")]
			if d.get("open_count"):
				line.append(f"{d['open_count']} open item{'' if d['open_count'] == 1 else 's'}")
		else:
			kind = "document"
			line = ["Document", d.get("doc_type") if r.ref_doctype == "Life Vault Document" else "kept file"]
			if d["sensitive"]:
				line.append("sensitive")
		out.append({"ref": d["ref"], "doctype": r.ref_doctype, "name": r.ref_name, "kind": kind, "letter": LETTER[kind], "title": d["title"] or "Untitled",
			"line": " · ".join(str(p) for p in line if p), "area": d["area"], "area_name": d["area_name"], "goal": d["goal"], "goal_title": d["goal_title"],
			"date": d["received"], "sensitive": d["sensitive"], "by_brain": d["by_assistant"], "expiry": d.get("expiry")})
	return out


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, tab: str | None = "all", q: str | None = None, area: str | None = None, goal: str | None = None, source: str | None = None,
		include_archived: bool | int | None = 0, start: int | None = 0, page_length: int | None = 50, unopened: bool | int | None = 0):
	"""Everything kept in a space: notes (and wiki pages), documents (Vault documents and kept files), people and chats, newest first.
	tab: all, notes, documents, people (Life Person and wiki pages about people), chats. q: a word in the title or the body.
	area (with its parts, or "none"), goal (or "none"), source: me, brain (kept by an agent or the wiki), or a system such as gmail.
	Each row has: ref, kind (note, person, document, chat), letter (N, P, D, C), title, line, area_name, goal_title, date, sensitive, by_brain.
	unopened=1 keeps notes not opened in 90 days (people are left out). `total` is what the filters match; `sources` lists the systems things came from."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	tab = tab or "all"
	if tab not in TABS:
		frappe.throw(_("tab must be one of: {0}.").format(", ".join(TABS)), title=_("Unknown tab"))
	q = (q or "").strip()[:200]
	limit = start + page_length
	idx, idx_total = _index_rows(space, tab, q, area, goal, source, include_archived, limit, flag(unopened))
	people, people_total = ([], 0) if flag(unopened) else _person_rows(space, tab, q, area, goal, source, include_archived, limit)
	rows = _decorate(idx)
	for row, r in zip(rows, idx):
		row["_at"] = str(r.modified)
	for p in people:
		rows.append({"ref": "person:" + p.name, "doctype": "Life Person", "name": p.name, "kind": "person", "letter": "P", "title": p.full_name,
			"line": " · ".join(x for x in ("Person", p.relation) if x), "area": None, "area_name": None, "goal": None, "goal_title": None,
			"date": str(p.creation.date()), "_at": str(p.creation), "sensitive": 0, "by_brain": 1 if p.owner in set(agent_users()) else 0, "expiry": None})
	rows.sort(key=lambda r: (r["date"] or "", r.pop("_at")), reverse=True)
	x = frappe.qb.DocType("Life Index")
	systems = list_query("Life Index", ["source_system"], [x.space == space, x.source_system != ""]).distinct().orderby(x.source_system).limit(30).run(pluck=True)
	return {"space": space, "tab": tab, "rows": rows[start:start + page_length], "total": idx_total + people_total, "start": start,
		"page_length": page_length, "sources": systems}
