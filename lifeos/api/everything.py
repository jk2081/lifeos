"""Library > Everything (issue 23): notes, documents, people and chats in one list, newest first.

Notes and wiki pages, Vault documents and kept files, and chat logs are read from Life Index; people are Life Person
records (not indexed) and wiki pages about people or organisations (a wiki page whose summary starts with Person,
Organisation, Organization or People). Until the People issue (#25) lands, that is what the People tab holds.
The Vault's rules apply as everywhere: a sensitive item is left out for a user the Vault is closed to."""
import builtins

import frappe
from frappe import _

from lifeos import counts, permissions
from lifeos.api.utils import area_filter, flag, names_map, page
from lifeos.api.sources import agent_users

TABS = ("all", "notes", "documents", "people", "chats")
# the index rows each tab holds (a kept file is an inbox item whose media kind is Document)
PEOPLE_NOTE = ("(x.ref_doctype = 'Life Note' and x.collection = 'Wiki' and exists (select 1 from `tabLife Note` n where n.name = x.ref_name "
	"and (n.summary like 'Person%%' or n.summary like 'Organi%%' or n.summary like 'People%%')))")
DOCUMENT = "(x.ref_doctype = 'Life Vault Document' or (x.ref_doctype = 'Life Inbox Item' and x.media_kind = 'Document'))"
CHAT = "x.ref_doctype = 'Life Chat Log'"
NOTE = f"(x.ref_doctype = 'Life Note' and not {PEOPLE_NOTE})"
TAB_SQL = {"all": f"({NOTE} or {DOCUMENT} or {CHAT} or {PEOPLE_NOTE})", "notes": NOTE, "documents": DOCUMENT, "chats": CHAT, "people": PEOPLE_NOTE}
LETTER = {"note": "N", "person": "P", "document": "D", "chat": "C"}
REF = {"Life Note": "note:", "Life Vault Document": "vault:", "Life Chat Log": "chat:", "Life Inbox Item": "source:", "Life Person": "person:"}
FIELDS = "x.ref_doctype, x.ref_name, x.title, x.record_date, x.area, x.goal, x.status, x.media_kind, x.source_system, x.assistant, x.intent, x.vault_locked, x.collection, x.record_owner, x.modified"


def _like(text: str) -> str:
	return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _index_rows(space, tab, q, area, goal, source, include_archived, limit, unopened=False):
	where, values = ["x.space = %(space)s", TAB_SQL[tab]], {"space": space}
	where.append("1=1" + permissions.vault_guard(space, "x."))
	if not flag(include_archived):
		where.append("x.is_archived = 0")
	if q:
		where.append("(x.title like %(q)s or x.search_text like %(q)s)")
		values["q"] = _like(q)
	if area:
		where.append(area_filter(space, area, "x.area", values, also_in="index"))
	if goal:
		where.append("x.goal = %(goal)s")
		values["goal"] = "" if goal == "none" else goal
	if unopened:  # notes not opened in 90 days (the Library's "Not opened in 90 days" filter)
		where.append("(x.ref_doctype = 'Life Note' and exists (select 1 from `tabLife Note` un where un.name = x.ref_name and un.last_opened_on <= %(unopened_cut)s))")
		values["unopened_cut"] = counts.ago(90)
	if source in ("me", "brain"):
		where.append(("" if source == "brain" else "not ") + "(x.record_owner in %(agents)s or x.collection = 'Wiki')")
		values["agents"] = agent_users()
	elif source:
		where.append("x.source_system = %(source)s")
		values["source"] = source.lower()
	clause = " and ".join(where)
	# nosemgrep: frappe-sql-format-injection -- WHERE from fixed fragments (TAB_SQL) and area_filter; every value is a parameter
	rows = frappe.db.sql(f"select {FIELDS} from `tabLife Index` x where {clause} order by x.record_date desc, x.modified desc limit %(n)s", {**values, "n": limit}, as_dict=True)
	# nosemgrep: frappe-sql-format-injection -- WHERE from fixed fragments (TAB_SQL) and area_filter; every value is a parameter
	total = frappe.db.sql(f"select count(*) from `tabLife Index` x where {clause}", values)[0][0]
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
	files = dict(frappe.db.sql("select attached_to_name, count(*) from `tabFile` where attached_to_doctype = 'Life Note' and attached_to_name in %s group by attached_to_name", (notes,))) if notes else {}
	sources = {}
	if notes:
		for parent, dt, name in frappe.db.sql("select parent, source_doctype, source_name from `tabLife Note Source` where parenttype = 'Life Note' and parent in %s order by idx", (notes,)):
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
		frappe.throw(_("tab must be one of: {0}.").format(", ".join(TABS)))
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
	systems = frappe.db.sql("select distinct source_system from `tabLife Index` where space = %s and source_system != '' order by source_system limit 30", space, pluck=True)
	return {"space": space, "tab": tab, "rows": rows[start:start + page_length], "total": idx_total + people_total, "start": start,
		"page_length": page_length, "sources": systems}
