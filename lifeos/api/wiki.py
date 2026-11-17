"""The Wiki (UX fixes, set 4): pages an agent writes and edits directly, after Karpathy's "LLM wiki" pattern. People edit them
like any note. Every create, edit, revert and move, by anyone, writes a Life Wiki Change with the text before and after,
so any change can be undone in one click. My notes pages are people's own: agents can only propose them.

Agents use: rules, index, get_page, search, create_page, update_page, cite. All check space membership, edit access and
the Vault rule. Limits: a page holds at most 200,000 characters; one call changes one page; at most 50 sources per call."""
import re

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from lifeos import links, permissions
from lifeos.api.utils import area_filter, names_map, page, parse, std_filters, std_order, summarise, tab_counts
from lifeos.api.utils import order_by as sort_order
from lifeos.life.doctype.life_note.life_note import MAX_MD, SOURCE_DOCTYPES

MAX_SOURCES = 50
COALESCE_MINUTES = 10  # a person's autosaves within this time are one Edited change
HEALTH_TAG = "health-report"
RULES_TITLE = "Wiki rules"
RULES_SUMMARY = "What this wiki is for and how its pages are written. People edit this page; agents read it."
RULES_TEXT = """# Wiki rules

This wiki holds what we know, written up from our sources: notes, documents, emails, chats and voice notes.
An agent writes and edits it directly; every change is logged and can be undone. People edit it like any note.

## What a page is

- One page per person, organisation, place, project idea, concept and source worth keeping.
- The title is the plain name of the thing: "Mithun Sarkar", "Ghatia estate", "Fair trade premium". No dates or prefixes.
- The summary is one line that says what the page is about.

## How pages are written

- Always cite the sources a page is written from. Add a source with every change that uses one.
- Prefer editing an existing page over creating a near-duplicate. Search first.
- Link related pages with [[Title]].
- Keep to what the sources say. Mark guesses as guesses.
- Never copy secrets, passwords or full account, card or ID numbers. The last four digits at most.

## Health

Pages no other page links to, links to pages that do not exist, pages without sources and near-duplicate titles are listed
under Health. An agent may file a report as a wiki page tagged health-report.
"""


# ---------- helpers ----------

def _norm_title(t):
	return re.sub(r"[^\w]+", "", (t or "").lower())


def version_of(doc):
	return str(doc.modified)


def _page_doc(name, ptype="read"):
	doc = permissions.get_doc_checked("Life Note", name, ptype)
	return doc


def _require_wiki_writer(space):
	permissions.require_space(space, write=True)


def ensure_rules(space):
	"""The one rules page of a space, made with the starter text the first time anyone opens the Wiki or asks for it."""
	name = frappe.db.get_value("Life Note", {"space": space, "is_rules": 1})
	if name:
		return name
	frappe.flags.lifeos_app_write = True  # made by the app, whoever asked first (an agent reading the rules, too)
	try:
		doc = frappe.get_doc({"doctype": "Life Note", "space": space, "title": RULES_TITLE, "collection": "Wiki", "is_rules": 1,
			"summary": RULES_SUMMARY, "content_md": RULES_TEXT}).insert(ignore_permissions=True)
	finally:
		frappe.flags.lifeos_app_write = False
	log_change(doc, "Created", "", doc.content_md, change_note="The starter rules page.", by="Administrator")
	return doc.name


def log_change(doc, change_type, before_md, after_md, change_note=None, source=None, by=None, reverts=None):
	"""Write one Life Wiki Change. `source` is (doctype, name) or a dict, the source that prompted the change."""
	src = None
	if isinstance(source, dict) and source.get("doctype"):
		src = (source["doctype"], source["name"])
	elif isinstance(source, (list, tuple)) and len(source) == 2:
		src = tuple(source)
	ch = frappe.get_doc({"doctype": "Life Wiki Change", "space": doc.space, "note": doc.name, "change_type": change_type,
		"changed_by": by or frappe.session.user, "changed_on": now_datetime(), "change_note": (change_note or "")[:1000] or None,
		"source_doctype": src[0] if src else None, "source_name": src[1] if src else None,
		"before_md": before_md or "", "after_md": after_md or "", "reverts": reverts})
	ch.insert(ignore_permissions=True)
	return ch


def person_edited(doc, before_md):
	"""A person saved a wiki page (library.save): one Edited change, merged with their own edits of the last minutes."""
	if (before_md or "") == (doc.content_md or ""):
		return None
	last = frappe.get_all("Life Wiki Change", filters={"note": doc.name}, fields=["name", "change_type", "changed_by", "changed_on", "reverted"],
		order_by="changed_on desc, creation desc", limit=1)
	if last and last[0].change_type == "Edited" and last[0].changed_by == frappe.session.user and not last[0].reverted \
			and last[0].changed_on > add_to_date(now_datetime(), minutes=-COALESCE_MINUTES):
		frappe.db.set_value("Life Wiki Change", last[0].name, {"after_md": doc.content_md or "", "changed_on": now_datetime()}, update_modified=False)
		return last[0].name
	return log_change(doc, "Edited", before_md, doc.content_md).name


def _sources(rows, space):
	"""Validate a list of sources ({doctype, name}, or "Life Inbox Item:name"). Each must be readable by the caller, which also
	applies the Vault rule."""
	out = []
	for r in parse(rows, []) or []:
		if isinstance(r, str) and ":" in r:
			r = dict(zip(("doctype", "name"), r.split(":", 1)))
		if not isinstance(r, dict) or r.get("doctype") not in SOURCE_DOCTYPES or not r.get("name"):
			frappe.throw(_("A source is {doctype, name} with doctype Life Inbox Item or Life Chat Log."))
		doc = permissions.get_doc_checked(r["doctype"], r["name"])
		if doc.space != space:
			frappe.throw(_("A page can only cite sources from its own space."))
		out.append((r["doctype"], r["name"]))
	if len(out) > MAX_SOURCES:
		frappe.throw(_("At most {0} sources in one call.").format(MAX_SOURCES))
	return out


def _source_arg(source, space):
	if not source:
		return None
	got = _sources([source], space)
	return got[0] if got else None


def _page_out(doc, with_text=True):
	srcs = [{"doctype": r.source_doctype, "name": r.source_name, "title": links.title_of(r.source_doctype, r.source_name)} for r in doc.sources]
	out = {"name": doc.name, "space": doc.space, "title": doc.title, "summary": doc.summary, "collection": doc.collection, "is_rules": doc.is_rules,
		"area": doc.area, "area_name": frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None,
		"project": doc.project, "parent_note": doc.parent_note, "sources": srcs, "links": links.outgoing(doc), "version": version_of(doc),
		"modified": str(doc.modified)[:19]}
	if with_text:
		out["content_md"] = doc.content_md or ""
	return out


def _check_text(content_md):
	if content_md is not None and len(content_md) > MAX_MD:
		frappe.throw(_("A page can hold at most {0} characters.").format(f"{MAX_MD:,}"))


# ---------- reading ----------

PAGE_SORTS = {"title": "n.title", "modified": "n.modified", "creation": "n.creation"}


@frappe.whitelist(methods=["GET"])
def pages(space: str | None = None, area: str | None = None, project: str | None = None, include_archived: bool | int | None = 0, sort: str | None = None, dir: str | None = None, start: int | None = 0, page_length: int | None = 50,
		filters: str | list | dict | None = None, order_by: str | None = None, summary: str | dict | None = None):
	"""The Wiki screen's Pages list: title, summary, area, sources count, updated. Newest first. Filters: area (with its
	sub-areas, or "none"), project, and standard filters on Life Note."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = ["n.space = %(space)s", "n.collection = 'Wiki'"], {"space": space}
	if not int(include_archived or 0):
		where.append("n.is_archived = 0")
	if area:
		where.append(area_filter(space, area, "n.area", values))
	if project:
		where.append("ifnull(n.project, '') = %(project)s")
		values["project"] = "" if project == "none" else project
	conds, values = std_filters("Life Note", filters, "n", values)
	clause = " and ".join(where + conds)
	if summary:
		return {"summary": summarise("Life Note", f"from `tabLife Note` n where {clause}", values, "n", summary, start, page_length)}
	order = std_order("Life Note", order_by, "n", PAGE_SORTS) or sort_order(sort, dir, PAGE_SORTS, "n.modified desc")
	# nosemgrep: frappe-sql-format-injection -- WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters
	rows = frappe.db.sql(f"""select n.name, n.title, n.summary, n.area, n.project, n.is_rules, n.modified, n.is_archived,
		(select count(*) from `tabLife Note Source` s where s.parent = n.name and s.parenttype = 'Life Note') as sources_count
		from `tabLife Note` n where {clause} order by n.is_rules desc, {order}, n.name limit %(start)s, %(len)s""",
		{**values, "start": start, "len": page_length}, as_dict=True)
	# nosemgrep: frappe-sql-format-injection -- WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters
	total = frappe.db.sql(f"select count(*) from `tabLife Note` n where {clause}", values)[0][0]
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	for r in rows:
		r["area_name"] = areas.get(r.area)
		r["modified"] = str(r.modified)[:19]
	return {"space": space, "pages": rows, "total": total}

@frappe.whitelist(methods=["POST"])
def rules(space: str | None = None):
	"""The rules page of the space's wiki: what it is for and how pages are written. Read it before writing."""
	space = permissions.resolve_space(space)
	doc = frappe.get_doc("Life Note", ensure_rules(space))
	return {"name": doc.name, "title": doc.title, "content_md": doc.content_md or "", "version": version_of(doc)}


@frappe.whitelist(methods=["GET"])
def index(space: str | None = None, area: str | None = None, start: int | None = 0, page_length: int | None = 100, order_by: str | None = None):
	"""Wiki pages of a space: name, title, summary, area, sources count, updated. By title. Paginated (at most 500 a call)."""
	space = permissions.resolve_space(space)
	start, page_length = int(start or 0), min(max(int(page_length or 100), 1), 500)
	values = {"space": space}
	where = ["n.space = %(space)s", "n.collection = 'Wiki'", "n.is_archived = 0"]
	if area:
		where.append(area_filter(space, area, "n.area", values))
	order = {"updated": "n.modified desc", "title": "n.title asc"}.get(order_by or "title", "n.title asc")
	# nosemgrep: frappe-sql-format-injection -- WHERE from fixed fragments and area_filter; the order comes from a fixed map; values are parameters
	rows = frappe.db.sql(f"""select n.name, n.title, n.summary, n.area, n.is_rules, n.modified,
		(select count(*) from `tabLife Note Source` s where s.parent = n.name and s.parenttype = 'Life Note') as sources
		from `tabLife Note` n where {' and '.join(where)} order by {order} limit %(start)s, %(len)s""", {**values, "start": start, "len": page_length}, as_dict=True)
	# nosemgrep: frappe-sql-format-injection -- WHERE from fixed fragments and area_filter; values are parameters
	total = frappe.db.sql(f"select count(*) from `tabLife Note` n where {' and '.join(where)}", values)[0][0]
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	for r in rows:
		r["area_name"] = areas.get(r.area)
		r["updated"] = str(r.pop("modified"))[:19]
	return {"space": space, "pages": rows, "total": total, "start": start, "page_length": page_length}


@frappe.whitelist(methods=["GET"])
def get_page(name: str):
	"""One page: title, Markdown, summary, area, sources, links and a `version` token to send back with update_page."""
	return _page_out(_page_doc(name))


@frappe.whitelist(methods=["GET"])
def search(space: str | None = None, query: str | None = None, collection: str | None = None, include_sources: bool | int | None = 0, limit: int | None = 20):
	"""Full-text search over pages (collection Wiki, My notes, or both when not given) and, with include_sources=1, over
	sources too. Each result has doctype, name, title, collection, summary and a snippet."""
	from lifeos.api.search import _snippet, WORD

	space = permissions.resolve_space(space)
	limit = min(max(int(limit or 20), 1), 100)
	words = [w.lower() for w in WORD.findall(query or "")][:8]
	if not words:
		return {"results": []}
	where = ["space = %(space)s", "is_archived = 0"]
	kinds = ["(kind = 'Note'" + (" and collection = %(collection)s)" if collection else ")")]
	if int(include_sources or 0):
		kinds.append("(kind in ('Inbox', 'Chat'))")
	where.append("(" + " or ".join(kinds) + ")")
	where.append("1=1" + permissions.vault_guard(space))
	likes = " and ".join(f"(title like %(w{i})s or search_text like %(w{i})s)" for i in range(len(words)))
	values = {"space": space, "collection": collection, "limit": limit, **{f"w{i}": f"%{w}%" for i, w in enumerate(words)}}
	long_words = [re.sub(r"[^\w]", "", w) for w in words if len(w) >= 3]
	rows = []
	if long_words:
		values["q"] = " ".join(f"+{w}*" for w in long_words if w)
		# nosemgrep: frappe-sql-format-injection -- WHERE from fixed fragments and vault_guard; the search text is the %(q)s parameter
		rows = frappe.db.sql(f"""select ref_doctype, ref_name, title, collection, search_text from `tabLife Index`
			where {' and '.join(where)} and match(title, search_text) against (%(q)s in boolean mode) order by (title like %(w0)s) desc,
			match(title, search_text) against (%(q)s in boolean mode) desc limit %(limit)s""", values, as_dict=True)
	if not rows:
		# nosemgrep: frappe-sql-format-injection -- WHERE and LIKE placeholders are fixed fragments; each word is a %(wN)s parameter
		rows = frappe.db.sql(f"""select ref_doctype, ref_name, title, collection, search_text from `tabLife Index`
			where {' and '.join(where)} and {likes} order by record_date desc limit %(limit)s""", values, as_dict=True)
	summaries = dict(frappe.get_all("Life Note", filters={"name": ["in", [r.ref_name for r in rows if r.ref_doctype == "Life Note"] or [""]]},
		fields=["name", "summary"], as_list=True))
	return {"results": [{"doctype": r.ref_doctype, "name": r.ref_name, "title": r.title, "collection": r.collection or None,
		"summary": summaries.get(r.ref_name), "snippet": _snippet(r.search_text, words)} for r in rows]}


# ---------- writing (agents and people) ----------

@frappe.whitelist(methods=["POST"])
def create_page(space: str | None = None, title: str | None = None, content_md: str | None = None, summary: str | None = None, area: str | None = None, project: str | None = None,
		parent_note: str | None = None, sources: str | list | None = None, change_note: str | None = None, source: str | dict | None = None):
	"""Create a Wiki page and a Created change. Refuses a title that already exists in the space's Wiki (edit that page instead).
	sources: [{doctype, name}] the page cites. source: the one source that prompted this change, if any."""
	space = permissions.resolve_space(space, write=True)
	title = (title or "").strip()
	if not title:
		frappe.throw(_("A page needs a title."))
	_check_text(content_md)
	existing = frappe.db.sql("select name from `tabLife Note` where space=%s and collection='Wiki' and lower(title)=lower(%s) limit 1", (space, title))
	if existing:
		frappe.throw(_("The wiki already has a page called {0} ({1}). Edit it with update_page.").format(title, existing[0][0]), frappe.DuplicateEntryError)
	srcs = _sources(sources, space)
	src = _source_arg(source, space)
	if src and src not in srcs:
		srcs.append(src)
	frappe.flags.lifeos_wiki_api = True
	try:
		doc = frappe.get_doc({"doctype": "Life Note", "space": space, "title": title[:140], "collection": "Wiki", "summary": summary,
			"content_md": content_md or "", "area": area or None, "project": project or None, "parent_note": parent_note or None,
			"sources": [{"source_doctype": d, "source_name": n} for d, n in srcs]})
		doc.insert()
	finally:
		frappe.flags.lifeos_wiki_api = False
	log_change(doc, "Created", "", doc.content_md, change_note, src)
	return _page_out(doc, with_text=False)


@frappe.whitelist(methods=["POST"])
def update_page(name: str, content_md: str | None = None, base_version: str | None = None, summary: str | None = None, sources_add: str | list | None = None,
		change_note: str | None = None, source: str | dict | None = None, title: str | None = None):
	"""Edit a Wiki page if `base_version` (from get_page) is still current. If the page changed since, nothing is written and
	the answer is {"conflict": true, "current": <the page now>}: read it, merge, and send again. Refuses My notes pages and
	the rules page. Writes an Edited change."""
	doc = _page_doc(name, "write")
	if doc.collection != "Wiki":
		frappe.throw(_("This page is in My notes. Only people change My notes; propose a note instead."), frappe.PermissionError)
	if doc.is_rules and permissions.is_agent():
		frappe.throw(_("The rules page is changed by people only."), frappe.PermissionError)
	if not base_version:
		frappe.throw(_("Send base_version, the version you read with get_page."))
	if base_version != version_of(doc):
		return {"conflict": True, "current": _page_out(doc)}
	_check_text(content_md)
	before = doc.content_md or ""
	src = _source_arg(source, doc.space)
	add = _sources(sources_add, doc.space)
	if src and src not in add:
		add.append(src)
	have = {(r.source_doctype, r.source_name) for r in doc.sources}
	for d, n in add:
		if (d, n) not in have:
			doc.append("sources", {"source_doctype": d, "source_name": n})
	if content_md is not None:
		doc.content_md = content_md
	if summary is not None:
		doc.summary = summary
	if title and title.strip() and title.strip() != doc.title:
		doc.title = title.strip()[:140]
	frappe.flags.lifeos_wiki_api = True
	try:
		doc.save()
	finally:
		frappe.flags.lifeos_wiki_api = False
	if (doc.content_md or "") != before or add or summary is not None:
		log_change(doc, "Edited", before, doc.content_md, change_note, src)
	return {"name": doc.name, "version": version_of(doc), "conflict": False}


@frappe.whitelist(methods=["POST"])
def cite(name: str, sources: str | list):
	"""Add sources to a page without changing its text."""
	doc = _page_doc(name, "write")
	if doc.collection != "Wiki" and permissions.is_agent():
		frappe.throw(_("This page is in My notes. Agents cannot change it."), frappe.PermissionError)
	have = {(r.source_doctype, r.source_name) for r in doc.sources}
	added = 0
	for d, n in _sources(sources, doc.space):
		if (d, n) not in have:
			doc.append("sources", {"source_doctype": d, "source_name": n})
			have.add((d, n))
			added += 1
	if added:
		frappe.flags.lifeos_wiki_api = True
		try:
			doc.save()
		finally:
			frappe.flags.lifeos_wiki_api = False
	return {"name": doc.name, "added": added, "version": version_of(doc)}


@frappe.whitelist(methods=["POST"])
def move(name: str, to: str):
	"""Keep in My notes (to="My notes") or Hand to the wiki (to="Wiki"). People only. A page moved to My notes can no longer
	be changed by agents. The rules page stays in the wiki."""
	if permissions.is_agent():
		frappe.throw(_("Only a person can move a page between My notes and the wiki."), frappe.PermissionError)
	if to not in ("My notes", "Wiki"):
		frappe.throw(_("to must be My notes or Wiki."))
	doc = _page_doc(name, "write")
	if doc.is_rules:
		frappe.throw(_("The rules page stays in the wiki."))
	if doc.collection == to:
		return {"name": doc.name, "collection": to}
	doc.collection = to
	if to == "Wiki" and not doc.summary:
		doc.summary = (doc.title or "")[:140]
	doc.save()
	log_change(doc, "Moved to My notes" if to == "My notes" else "Moved to Wiki", doc.content_md, doc.content_md)
	return {"name": doc.name, "collection": to, "version": version_of(doc)}


# ---------- changes and undo ----------

CHANGE_FIELDS = ["name", "note", "change_type", "changed_by", "changed_on", "change_note", "source_doctype", "source_name", "reverted", "reverts"]


def _decorate_changes(rows):
	from lifeos.api.utils import user_names

	notes = {r.name: r for r in frappe.get_all("Life Note", filters={"name": ["in", [x.note for x in rows] or [""]]}, fields=["name", "title", "collection"])}
	users = user_names([r.changed_by for r in rows])
	for r in rows:
		n = notes.get(r.note)
		r["note_title"] = n.title if n else r.note
		r["collection"] = n.collection if n else None
		r["by"] = "Life OS" if r.changed_by == "Administrator" else users.get(r.changed_by) or r.changed_by
		r["by_agent"] = bool(r.changed_by and r.changed_by != "Administrator" and permissions.is_agent(r.changed_by))
		r["changed_on"] = str(r.changed_on)[:19]
		r["source_title"] = links.title_of(r.source_doctype, r.source_name) if r.source_doctype and r.source_name else None
	return rows


@frappe.whitelist(methods=["GET"])
def changes(space: str | None = None, note: str | None = None, by: str | None = None, source: str | None = None, from_date: str | None = None, to_date: str | None = None, start: int | None = 0,
		page_length: int | None = 50, filters: str | list | dict | None = None, order_by: str | None = None, summary: str | dict | None = None):
	"""Every Life Wiki Change of a space, newest first. Filters: note, by (a user), source ("doctype:name" or a name),
	from_date, to_date, and standard filters on Life Wiki Change. Paginated."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = ["c.space = %(space)s"], {"space": space}
	conds, values = std_filters("Life Wiki Change", filters, "c", values)
	where += conds
	if note:
		where.append("c.note = %(note)s")
		values["note"] = note
	if by:
		where.append("c.changed_by = %(by)s")
		values["by"] = by
	if source:
		where.append("c.source_name = %(source)s")
		values["source"] = str(source).split(":", 1)[-1]
	if from_date:
		where.append("date(c.changed_on) >= %(from_date)s")
		values["from_date"] = frappe.utils.getdate(from_date)
	if to_date:
		where.append("date(c.changed_on) <= %(to_date)s")
		values["to_date"] = frappe.utils.getdate(to_date)
	clause = " and ".join(where)
	if summary:
		return {"summary": summarise("Life Wiki Change", f"from `tabLife Wiki Change` c where {clause}", values, "c", summary, start, page_length)}
	order = std_order("Life Wiki Change", order_by, "c", {"changed_on": "c.changed_on"}) or "c.changed_on desc"
	# nosemgrep: frappe-sql-format-injection -- CHANGE_FIELDS is a fixed list; WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters
	rows = frappe.db.sql(f"""select {', '.join('c.' + f for f in CHANGE_FIELDS)} from `tabLife Wiki Change` c where {clause}
		order by {order}, c.creation desc limit %(start)s, %(len)s""", {**values, "start": start, "len": page_length}, as_dict=True)
	# nosemgrep: frappe-sql-format-injection -- WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters
	total = frappe.db.sql(f"select count(*) from `tabLife Wiki Change` c where {clause}", values)[0][0]
	people = frappe.db.sql("select distinct changed_by from `tabLife Wiki Change` where space=%s limit 50", space, pluck=True)
	return {"space": space, "changes": _decorate_changes(rows), "total": total, "people": [{"user": u, "name": n} for u, n in
		[(p, ("Life OS" if p == "Administrator" else None)) for p in people]]}


@frappe.whitelist(methods=["GET"])
def change(name: str):
	"""One change with the text before and after, and whether the page has changed since."""
	ch = frappe.get_doc("Life Wiki Change", name)
	page_doc = _page_doc(ch.note)  # the page's own permission check
	out = _decorate_changes([frappe._dict({f: ch.get(f) for f in CHANGE_FIELDS})])[0]
	out.update({"before_md": ch.before_md or "", "after_md": ch.after_md or "", "current_md": page_doc.content_md or "",
		"changed_since": (page_doc.content_md or "") != (ch.after_md or ""), "space": ch.space})
	return out


@frappe.whitelist(methods=["POST"])
def undo(change: str, force: bool | int | None = 0):
	"""Put back the text from before a change. If the page has changed since that change, nothing is done and the answer is
	{"conflict": true, "current_md": ...} unless force=1 (revert anyway). Writes a Reverted change."""
	ch = frappe.get_doc("Life Wiki Change", change)
	doc = _page_doc(ch.note, "write")
	if doc.collection != "Wiki" and permissions.is_agent():
		frappe.throw(_("This page is in My notes. Agents cannot change it."), frappe.PermissionError)
	if ch.change_type not in ("Created", "Edited", "Reverted"):
		frappe.throw(_("A move between My notes and the wiki is undone by moving the page back."))
	if (doc.content_md or "") != (ch.after_md or "") and not int(force or 0):
		return {"conflict": True, "current_md": doc.content_md or "", "after_md": ch.after_md or ""}
	before = doc.content_md or ""
	doc.content_md = ch.before_md or ""
	frappe.flags.lifeos_wiki_api = True
	try:
		doc.save()
	finally:
		frappe.flags.lifeos_wiki_api = False
	frappe.db.set_value("Life Wiki Change", ch.name, "reverted", 1, update_modified=False)
	new = log_change(doc, "Reverted", before, doc.content_md, change_note=_("Undid the change of {0}.").format(str(ch.changed_on)[:16]), reverts=ch.name)
	return {"name": doc.name, "change": new.name, "version": version_of(doc), "conflict": False}


# ---------- health ----------

def compute_health(space):
	"""Orphans, broken links, pages without sources and near-duplicate titles of a space's wiki, and the health reports."""
	pages = frappe.db.sql("""select name, title, summary, content_md, is_rules from `tabLife Note`
		where space=%s and collection='Wiki' and is_archived=0""", space, as_dict=True)
	names = [p.name for p in pages]
	incoming = set(frappe.db.sql_list("""select distinct to_name from `tabLife Link` where space=%s and to_doctype='Life Note'
		and from_name != to_name""", space)) if names else set()
	cited = set(frappe.db.sql_list("""select distinct parent from `tabLife Note Source` where parenttype='Life Note' and parent in %s""",
		(names,))) if names else set()
	resolved = {}
	for f, text in frappe.db.sql("select from_name, lower(link_text) from `tabLife Link` where space=%s and from_doctype='Life Note'", space):
		resolved.setdefault(f, set()).add(text)
	broken, ambiguous = [], []
	for p in pages:
		for m in links.LINK_RE.finditer(p.content_md or ""):
			text = m.group(1).strip()
			if text.lower() not in resolved.get(p.name, set()):
				broken.append({"page": p.name, "page_title": p.title, "link": text})
			elif not m.group(2) and len(links.candidates(space, text)) > 1:
				wiki = [c for c in links.candidates(space, text) if c["doctype"] == "Life Note"
					and frappe.db.get_value("Life Note", c["name"], "collection") == "Wiki"]
				if len(wiki) > 1:
					ambiguous.append({"page": p.name, "page_title": p.title, "link": text})
	groups = {}
	for p in pages:
		groups.setdefault(_norm_title(p.title), []).append({"name": p.name, "title": p.title})
	report_tag = frappe.db.get_value("Life Tag", {"space": space, "tag_name": HEALTH_TAG})
	reports = []
	if report_tag:
		reports = frappe.db.sql("""select n.name, n.title, n.summary, n.modified from `tabLife Note` n join `tabLife Tag Link` t on t.parent = n.name
			and t.parenttype = 'Life Note' where n.space = %s and n.collection = 'Wiki' and t.tag = %s and n.is_archived = 0
			order by n.modified desc limit 10""", (space, report_tag), as_dict=True)
		for r in reports:
			r["modified"] = str(r.modified)[:19]
	return {
		"computed_on": str(now_datetime())[:19],
		"orphans": [{"name": p.name, "title": p.title} for p in pages if not p.is_rules and p.name not in incoming],
		"broken": broken[:500], "ambiguous": ambiguous[:200],
		"no_sources": [{"name": p.name, "title": p.title} for p in pages if not p.is_rules and p.name not in cited],
		"duplicates": [g for g in groups.values() if len(g) > 1],
		"reports": reports, "pages": len(pages),
	}


def _health_key(space):
	return f"lifeos:wiki_health:{space}"


@frappe.whitelist(methods=["GET"])
def health(space: str | None = None, refresh: bool | int | None = 0):
	"""The wiki's health: orphans (no page links to them; the rules page excepted), broken [[links]], pages without sources,
	near-duplicate titles (same title ignoring case and punctuation), ambiguous links, and reports filed by an agent as wiki
	pages tagged health-report. Computed nightly and when asked (refresh=1)."""
	space = permissions.resolve_space(space)
	data = None if int(refresh or 0) else frappe.cache.get_value(_health_key(space))
	if not data:
		data = compute_health(space)
		frappe.cache.set_value(_health_key(space), data, expires_in_sec=26 * 3600)
	if permissions.vault_hidden(space):
		data = dict(data)
	return data


def refresh_all_health():
	"""The nightly job: health of every space's wiki."""
	for space in frappe.get_all("Life Space", pluck="name"):
		frappe.cache.set_value(_health_key(space), compute_health(space), expires_in_sec=26 * 3600)


# ---------- the screen ----------

@frappe.whitelist(methods=["POST"])
def overview(space: str | None = None):
	"""What the Wiki screen needs to open: the rules page (made on first visit), and the counts of its tabs."""
	space = permissions.resolve_space(space)
	rules_name = ensure_rules(space)
	pages = frappe.db.count("Life Note", {"space": space, "collection": "Wiki", "is_archived": 0})
	changes_n = frappe.db.count("Life Wiki Change", {"space": space})
	h = frappe.cache.get_value(_health_key(space)) or None
	issues = None if not h else len(h["orphans"]) + len(h["broken"]) + len(h["no_sources"]) + len(h["duplicates"])
	return {"space": space, "rules": rules_name, "pages": pages, "changes": changes_n, "health_issues": issues}


@frappe.whitelist(methods=["POST"])
def new_page(space: str | None = None, title: str | None = None, summary: str | None = None, area: str | None = None):
	"""A person creates a wiki page from the Wiki screen."""
	return create_page(space=space, title=title, content_md="", summary=summary or title, area=area)
