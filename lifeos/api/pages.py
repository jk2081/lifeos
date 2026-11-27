"""Pages that build themselves (issue 111): a page for every person, company and part, and for a free-form note.

`get` is one page, laid out top to bottom: header, the Brain's brief, Open, People, Files, Timeline and Your notes. `list` is Library > Pages. The pins
(`pins`, `pin`, `unpin`, `reorder`, `visit`) are the person's own, shown in the sidebar. The owner's own notes are Frappe Comments on the page, which
the Brain and agents never write. Plumbing only: reading what is linked, the checks, the counts; the brief's words are the `write-brief` skill's."""
import frappe
from frappe import _
from frappe.utils import nowdate, strip_html_tags

from lifeos import permissions
from lifeos.api.utils import page as clamp
from lifeos.library import briefs, pins, subjects

STATUSES = ("Prospect", "Client", "Partner", "Past")
KINDS = {"company": "Companies", "person": "People", "part": "Parts and projects", "note": "Notes"}
OPEN_TASKS = ("Open", "Doing", "Waiting")
NOTE_CAP = 100


def _people_only():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Only a person changes a page. The Brain writes the brief, and an agent files what it finds."), frappe.PermissionError, title=_("People only"))


def _check(doctype: str, name: str, ptype: str = "read"):
	if doctype not in pins.PAGE_DOCTYPES:
		frappe.throw(_("{0} has no page.").format(doctype), title=_("No page here"))
	return permissions.get_doc_checked(doctype, name, ptype)


def _area_path(area: str | None) -> str | None:
	"""Career › BTW"""
	names = []
	while area and len(names) < 4:
		row = frappe.db.get_value("Life Area", area, ["area_name", "parent_area"], as_dict=True)
		if not row:
			break
		names.insert(0, row.area_name)
		area = row.parent_area
	return " › ".join(names) or None


def _kind(doctype: str, doc) -> str:
	return "note" if doctype == "Life Note" else subjects.kind_of_subject(doctype, doc.name)


def _header(doctype: str, doc) -> dict:
	kind = _kind(doctype, doc)
	h = {"doctype": doctype, "name": doc.name, "space": doc.space, "kind": kind, "kind_label": {"company": "Company", "person": "Person", "part": "Part", "note": "Page"}[kind]}
	if doctype == "Life Person":
		h.update(title=doc.full_name, status=doc.status if doc.kind == "Organisation" else None, role=doc.role or doc.relation, email=doc.email, phone=doc.phone, aliases=subjects.split_aliases(doc.aliases),
			area=doc.area, path=_area_path(doc.area), organisation={"name": doc.organisation, "title": frappe.db.get_value("Life Person", doc.organisation, "full_name")} if doc.organisation else None,
			is_archived=bool(doc.is_archived))
	elif doctype == "Life Area":
		h.update(title=doc.area_name, status=None, aliases=[], area=doc.name, path=_area_path(doc.name), is_archived=bool(doc.is_archived))
	else:
		h.update(title=doc.title, status=None, aliases=[], area=doc.area, path=_area_path(doc.area), is_archived=bool(doc.is_archived))
	return h


def _linked_items(doctype: str, name: str) -> list:
	"""(doctype, name) of every record linked to the page."""
	return [(r.from_doctype, r.from_name) for r in subjects.links_to(doctype, name)]


def _open(doctype: str, doc, linked: list) -> dict:
	"""What is open: linked open tasks (and those of an email linked to it, waiting on or delegated to the person, or in the part), upcoming events and Needs you."""
	task_names, item_names = set(), set()
	for dt, n in linked:
		if dt == "Life Task":
			task_names.add(n)
		elif dt == "Life Inbox Item":
			item_names.add(n)
		elif dt == "Life Sender Sighting":
			it = frappe.db.get_value(dt, n, "item")
			if it:
				item_names.add(it)
	filters_or = []
	if task_names:
		filters_or.append(["name", "in", list(task_names)])
	if item_names:
		filters_or.append(["inbox_item", "in", list(item_names)])
	if doctype == "Life Person":
		filters_or += [["waiting_on_person", "=", doc.name], ["delegated_to", "=", doc.name]]
	if doctype == "Life Area":
		filters_or.append(["area", "=", doc.name])
	tasks = []
	if filters_or:
		tasks = frappe.get_list("Life Task", filters={"space": doc.space, "status": ("in", OPEN_TASKS), "is_archived": 0}, or_filters=filters_or,
			fields=["name", "title", "status", "due_date", "priority"], order_by="due_date asc, modified desc", limit=20)
	events = []
	event_names = [n for dt, n in linked if dt == "Event"]
	if event_names:
		events = frappe.get_list("Event", filters={"name": ("in", event_names), "starts_on": (">=", nowdate())}, fields=["name", "subject", "starts_on"], order_by="starts_on asc", limit=10)
	needs = []
	if item_names:
		needs = frappe.get_list("Life Proposal", filters={"inbox_item": ("in", list(item_names)), "status": "Pending"}, fields=["name", "inbox_item", "kind", "preview"], limit=10)
	return {"tasks": [{"name": t.name, "title": t.title, "status": t.status, "due_date": str(t.due_date or ""), "ref": f"task:{t.name}"} for t in tasks],
		"events": [{"name": e.name, "title": e.subject, "starts_on": str(e.starts_on), "ref": f"event:{e.name}"} for e in events],
		"needs_you": [{"name": p.name, "item": p.inbox_item, "title": p.preview or p.kind, "kind": p.kind} for p in needs]}


def _people(doctype: str, doc, linked: list) -> list:
	rows = []
	if doctype == "Life Person" and doc.kind == "Organisation":
		rows = frappe.get_list("Life Person", filters={"space": doc.space, "organisation": doc.name, "is_archived": 0}, fields=["name", "full_name", "role", "relation", "email"], order_by="full_name asc", limit=50)
		return [{"name": r.name, "title": r.full_name, "role": r.role or r.relation, "email": r.email, "why": "works there"} for r in rows]
	if doctype == "Life Person":
		out = []
		if doc.organisation:
			o = frappe.db.get_value("Life Person", doc.organisation, ["full_name", "status"], as_dict=True)
			out.append({"name": doc.organisation, "title": o.full_name, "role": None, "email": None, "why": "their organisation", "company": True})
		with_ = {}
		for dt, n in linked:  # the people on the same emails and notes
			for r in frappe.get_all("Life Link", filters={"from_doctype": dt, "from_name": n, "to_doctype": "Life Person", "origin": ("in", ("Brain", "Owner")), "to_name": ("!=", doc.name)}, pluck="to_name", limit=20):  # system: the links of items this person may see, to find who is often with them
				with_[r] = with_.get(r, 0) + 1
		for name, c in sorted(with_.items(), key=lambda x: -x[1])[:6]:
			r = frappe.db.get_value("Life Person", name, ["full_name", "role", "kind", "email"], as_dict=True)
			if r and r.kind == "Person" and name != doc.organisation:
				out.append({"name": name, "title": r.full_name, "role": r.role, "email": r.email, "why": "often with them"})
		return out
	if doctype == "Life Area":
		rows = frappe.get_list("Life Person", filters={"space": doc.space, "area": doc.name, "is_archived": 0}, fields=["name", "full_name", "role", "kind", "email"], order_by="full_name asc", limit=50)
		return [{"name": r.name, "title": r.full_name, "role": r.role, "email": r.email, "why": "in this part", "company": r.kind == "Organisation"} for r in rows]
	return []


def _files(linked: list, doctype: str, name: str) -> list:
	"""Files attached to the page, or to anything linked to it."""
	holders = {(doctype, name), *linked}
	for dt, n in list(holders):
		if dt == "Life Sender Sighting":
			it = frappe.db.get_value(dt, n, "item")
			if it:
				holders.add(("Life Inbox Item", it))
	out, seen = [], set()
	for dt in {h[0] for h in holders}:
		names = [n for d, n in holders if d == dt]
		for f in frappe.get_all("File", filters={"attached_to_doctype": dt, "attached_to_name": ("in", names), "is_folder": 0}, fields=["name", "file_name", "file_url", "file_size", "creation", "attached_to_name"],  # system: files of the page and what is linked to it; each is checked for read below
				order_by="creation desc", limit=50):
			if f.file_url in seen or not frappe.has_permission("File", "read", f.name):
				continue
			seen.add(f.file_url)
			out.append({"name": f.name, "title": f.file_name, "url": f.file_url, "size": f.file_size, "date": str(f.creation)[:10], "from": f"{dt}:{f.attached_to_name}"})
	out.sort(key=lambda f: f["date"], reverse=True)
	return out[:50]


def _notes(doctype: str, name: str) -> list:
	rows = frappe.get_all("Comment", filters={"reference_doctype": doctype, "reference_name": name, "comment_type": "Comment"}, fields=["name", "content", "creation", "comment_by"],  # system: the Comments on a page this person was checked to read
		order_by="creation desc", limit=NOTE_CAP)
	return [{"name": r.name, "text": strip_html_tags(r.content or ""), "on": str(r.creation), "by": r.comment_by} for r in rows]


@frappe.whitelist(methods=["GET"])
def get(doctype: str, name: str):
	"""One page. Subjects (a person, a company, a part): `header`, `brief` (text with [n] source numbers, its sources, `as_of`, `stale`), `open`, `people`, `files`, `timeline`
	(newest first, each with the id of its link so a wrong one can be taken off) and `notes` (the owner's own, Comments). A free-form page (a note) has the header and its
	`note` text. `pin` says whether the person pinned it, and `offer_pin` whether to ask "Pin it?"."""
	doc = _check(doctype, name)
	head = _header(doctype, doc)
	pinned = bool(frappe.db.exists("Life Pin", {"user": frappe.session.user, "ref_doctype": doctype, "ref_name": name}))
	out = {"header": head, "pinned": pinned, "pins": len(frappe.get_all("Life Pin", filters={"user": frappe.session.user}, pluck="name")), "pin_limit": pins.LIMIT}  # system: the person's own pins
	if doctype == "Life Note":
		out["note"] = {"text": doc.content_md or "", "collection": doc.collection, "summary": doc.summary}
		return out
	linked = _linked_items(doctype, name)
	line, total = subjects.timeline(doctype, name)
	brief = briefs.read(doctype, name)
	out.update(brief=({**brief, "n_sources": len(brief["sources"])} if brief else None), open=_open(doctype, doc, linked), people=_people(doctype, doc, linked),
		files=_files(linked, doctype, name), timeline=line, timeline_total=total, notes=_notes(doctype, name), can_rewrite=bool(line))
	return out


@frappe.whitelist(methods=["GET"])
def index(space: str | None = None, kind: str | None = None, status: str | None = None, q: str | None = None, start: int = 0, page_length: int = 50):
	"""Library > Pages: people, companies, parts and free-form pages, most recently updated first. kind: company, person, part or note. status: Prospect, Client, Partner or Past
	(companies). Each row: doctype, name, title, kind, status, path, updated, new (linked since the person last opened it), and `counts` per kind."""
	space = permissions.resolve_space(space)
	start, page_length = clamp(start, page_length)
	q = (q or "").strip().lower()
	rows = []
	for p in frappe.get_list("Life Person", filters={"space": space, "is_archived": 0}, fields=["name", "full_name", "kind", "status", "area", "modified", "organisation"], limit=2000):
		rows.append({"doctype": "Life Person", "name": p.name, "title": p.full_name, "kind": "company" if p.kind == "Organisation" else "person", "status": p.status if p.kind == "Organisation" else None,
			"path": _area_path(p.area), "updated": str(p.modified)})
	for a in frappe.get_list("Life Area", filters={"space": space, "is_archived": 0, "is_focus": 0, "is_life_area": 0, "parent_area": ("is", "set")}, fields=["name", "area_name", "parent_area", "modified"], limit=2000):
		rows.append({"doctype": "Life Area", "name": a.name, "title": a.area_name, "kind": "part", "status": None, "path": _area_path(a.parent_area), "updated": str(a.modified)})
	linked_notes = set(frappe.get_all("Life Person", filters={"space": space, "wiki_page": ("is", "set")}, pluck="wiki_page", limit=5000))  # system: the space's linked wiki pages, only to leave them out of the list; the list itself is read with permissions
	for n in frappe.get_list("Life Note", filters={"space": space, "is_archived": 0, "collection": "Wiki", "person": ("is", "not set")}, fields=["name", "title", "area", "modified"], limit=2000):
		if n.name not in linked_notes:
			rows.append({"doctype": "Life Note", "name": n.name, "title": n.title, "kind": "note", "status": None, "path": _area_path(n.area), "updated": str(n.modified)})
	counts = {k: sum(1 for r in rows if r["kind"] == k) for k in KINDS}
	if kind in KINDS:
		rows = [r for r in rows if r["kind"] == kind]
	if status in STATUSES:
		rows = [r for r in rows if r["status"] == status]
	if q:
		rows = [r for r in rows if q in (r["title"] or "").lower()]
	for r in rows:  # a subject's page is also "updated" when something was linked to it
		last = subjects.last_linked(r["doctype"], r["name"]) if r["doctype"] != "Life Note" else None
		if last and str(last) > r["updated"]:
			r["updated"] = str(last)
	rows.sort(key=lambda r: r["updated"], reverse=True)
	total = len(rows)
	rows = rows[start:start + page_length]
	seen = {(v.ref_doctype, v.ref_name): v.opened_on for v in frappe.get_all("Life Page Visit", filters={"user": frappe.session.user}, fields=["ref_doctype", "ref_name", "opened_on"], order_by="opened_on asc", limit=5000)}  # system: the person's own openings
	for p in frappe.get_all("Life Pin", filters={"user": frappe.session.user}, fields=["ref_doctype", "ref_name", "seen_on"]):  # system: the person's own pins
		key = (p.ref_doctype, p.ref_name)
		if p.seen_on and (not seen.get(key) or p.seen_on > seen[key]):
			seen[key] = p.seen_on
	for r in rows:
		r["new"] = pins.new_since(r["doctype"], r["name"], seen.get((r["doctype"], r["name"])))
	return {"space": space, "rows": rows, "total": total, "counts": counts, "statuses": [*STATUSES], "start": start, "page_length": page_length}


# ---------------------------------------------------------------- the person's pins

@frappe.whitelist(methods=["GET"])
def pinned():
	"""The person's pinned pages, in their order: [{doctype, name, title, kind, new}], and the suggestions: `unpin` (pins not opened for 30 days, for the weekly review)."""
	permissions.require_login()
	return {"pins": pins.mine(), "limit": pins.LIMIT}


@frappe.whitelist(methods=["POST"])
def pin(doctype: str, name: str, replace: str | None = None):
	"""Pin a page. With seven pinned already it answers `refused` with `choose_to_unpin`; call again with `replace` ("Doctype:name") to swap."""
	permissions.require_login()
	_check(doctype, name)
	return pins.pin(doctype, name, replace)


@frappe.whitelist(methods=["POST"])
def unpin(doctype: str, name: str):
	permissions.require_login()
	return pins.unpin(doctype, name)


@frappe.whitelist(methods=["POST"])
def reorder(order: list):
	"""The pins in the order the person dragged them to: a list of "Doctype:name"."""
	permissions.require_login()
	return pins.reorder(order)


@frappe.whitelist(methods=["POST"])
def visit(doctype: str, name: str):
	"""The person opened a page: its pin's count clears. Answers `offer_pin` once, when it was opened 5 times in 7 days."""
	permissions.require_login()
	_check(doctype, name)
	return pins.visit(doctype, name)


# ---------------------------------------------------------------- changing a page

@frappe.whitelist(methods=["POST"])
def rewrite(doctype: str, name: str):
	"""Rewrite the brief now (the Rewrite button). People only. Says why when it could not: no AI key, or the month's cap is reached."""
	_people_only()
	_check(doctype, name, "write")
	res = briefs.rewrite(doctype, name, force=True)
	return {**res, "brief": briefs.read(doctype, name)}


@frappe.whitelist(methods=["POST"])
def set_status(name: str, status: str | None = None):
	"""A company's status: Prospect, Client, Partner, Past, or none."""
	_people_only()
	doc = _check("Life Person", name, "write")
	if doc.kind != "Organisation":
		frappe.throw(_("Only a company has a status."), title=_("Not a company"))
	if status and status not in STATUSES:
		frappe.throw(_("Status is one of {0}.").format(", ".join(STATUSES)), title=_("Unknown status"))
	doc.status = status or None
	doc.save()
	return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def rename(doctype: str, name: str, title: str):
	_people_only()
	doc = _check(doctype, name, "write")
	title = " ".join((title or "").split())[:140]
	if not title:
		frappe.throw(_("A page needs a name."), title=_("Name needed"))
	doc.set({"Life Person": "full_name", "Life Area": "area_name", "Life Note": "title"}[doctype], title)
	doc.save()
	return {"title": title}


@frappe.whitelist(methods=["POST"])
def merge(name: str, into: str):
	"""Join two people, or two companies: `name` goes into `into`, with its links, other names and notes."""
	_people_only()
	_check("Life Person", name, "delete")
	keep = _check("Life Person", into, "write")
	subjects.merge(keep.space, keep.name, name)
	return {"name": keep.name}


@frappe.whitelist(methods=["POST"])
def archive(doctype: str, name: str, archived: bool | int = 1):
	"""Archive a page (or bring it back). A person or company is hidden from Library > Pages and its pin goes."""
	_people_only()
	doc = _check(doctype, name, "write")
	flag = 1 if archived in (1, True, "1", "true", "True") else 0
	if doctype == "Life Person":
		doc.is_archived = flag
		doc.save()
	else:
		from lifeos.api import archive as archive_api

		archive_api.set(doctype, name, flag)
	if flag:
		frappe.db.delete("Life Pin", {"ref_doctype": doctype, "ref_name": name})
	return {"is_archived": bool(flag)}


@frappe.whitelist(methods=["POST"])
def remove_link(link: str):
	"""Take a wrong item off a page's timeline. The Brain does not make that link again, and it is kept as a correction for the skill."""
	_people_only()
	row = frappe.db.get_value("Life Link", link, ["from_doctype", "from_name", "to_doctype", "to_name", "origin"], as_dict=True)
	if not row or row.origin == "Text" or row.to_doctype not in subjects.SUBJECTS:
		frappe.throw(_("That is not an item on a page."), frappe.DoesNotExistError, title=_("Link not found"))
	_check(row.to_doctype, row.to_name, "write")
	subjects.unlink(row.from_doctype, row.from_name, row.to_doctype, row.to_name)
	return {"removed": True}


@frappe.whitelist(methods=["POST"])
def add_note(doctype: str, name: str, text: str):
	"""Add to Your notes: the owner's own text, a Comment on the page. The Brain and agents never write or change it."""
	_people_only()
	doc = _check(doctype, name, "write")
	text = strip_html_tags(text or "").strip()
	if not text:
		frappe.throw(_("Write something first."), title=_("Nothing to save"))
	doc.add_comment("Comment", text[:5000])
	return {"notes": _notes(doctype, name)}


@frappe.whitelist(methods=["POST"])
def delete_note(doctype: str, name: str, note: str):
	_people_only()
	_check(doctype, name, "write")
	row = frappe.db.get_value("Comment", note, ["reference_doctype", "reference_name", "owner"], as_dict=True)
	if not row or (row.reference_doctype, row.reference_name) != (doctype, name):
		frappe.throw(_("That note is not on this page."), frappe.DoesNotExistError, title=_("Note not found"))
	frappe.delete_doc("Comment", note, ignore_permissions=True, force=True)  # system: the page's write check is above
	return {"notes": _notes(doctype, name)}
