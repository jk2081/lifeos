"""Sources (UX fixes, set 4): the library of every capture, finished or not. A source is an inbox item (a file, voice note,
photo, pasted text, web link, email or email digest) or a chat log, kept unchanged. The Inbox is the queue of sources that
are not finished; Sources lists them all. Reads Life Index, so it needs one query for a page of rows."""
import builtins

import frappe
from frappe import _

from lifeos.library import links
from lifeos import permissions
from frappe.query_builder import Order
from frappe.query_builder import functions as fn

from lifeos.api.timeline import index_where
from lifeos.api.utils import (area_criterion, count_by, count_tabs, count_where, filter_criteria, flag, group_summary, list_query, names_map, order_terms,
	page, parse, sort_terms)

SOURCE_DOCTYPES = ("Life Inbox Item", "Life Chat Log")
# Library > Captures (UX fixes, set 6): every source, with Vault documents (kind Document, always sensitive); Library > All adds the notes
CAPTURE_DOCTYPES = ("Life Inbox Item", "Life Chat Log", "Life Vault Document")
SOURCE_KINDS = ("Inbox", "Chat", "Document")
CAPTURE_REFS = ("Life Inbox Item", "Life Chat Log", "Life Vault Document")


def base_criteria(x, scope="captures"):
	"""The index rows that are sources: every capture, with Vault documents; scope "all" adds the notes."""
	if scope == "all":
		return [x.ref_doctype.isin([*CAPTURE_REFS, "Life Note"]), x.kind.isin([*SOURCE_KINDS, "Note"])]
	return [x.ref_doctype.isin(CAPTURE_REFS), x.kind.isin(SOURCE_KINDS)]


# the kind tabs of Captures and All, each a condition on the index row
TAB_NAMES = ("all", "notes", "chats", "voice", "documents", "photos", "videos", "articles", "email", "text")


def tab_criteria(x):
	return {
		"all": None,
		"notes": x.ref_doctype == "Life Note",
		"chats": x.ref_doctype == "Life Chat Log",
		"voice": x.media_kind == "Voice",
		"documents": (x.media_kind == "Document") | (x.ref_doctype == "Life Vault Document"),
		"photos": x.media_kind == "Photo",
		"videos": x.media_kind == "Video",
		"articles": x.media_kind == "Article",
		"email": x.media_kind.isin(["Email", "Email Digest"]),
		"text": x.media_kind == "Text",
	}


# where a source is: In Inbox (not finished), Done (finished; every chat log), Failed
STATUS_NAMES = ("inbox", "done", "failed")


def status_criteria(x):
	return {
		"inbox": (x.ref_doctype == "Life Inbox Item") & x.status.isin(["New", "Processing", "To Review"]),
		"done": (x.ref_doctype != "Life Inbox Item") | (x.status == "Done"),
		"failed": x.status == "Failed",
	}


SORTS = {k: (lambda x, k=k: [x[k]]) for k in ("record_date", "title", "modified")}
FIELDS = ["ref_doctype", "ref_name", "title", "record_date", "area", "goal", "status", "media_kind", "source_system", "intent",
	"assistant", "thumbnail", "is_archived", "vault_locked", "modified", "collection", "record_owner"]


def status_label(doctype, status):
	if doctype != "Life Inbox Item":
		return "Done"
	return {"New": "In Inbox", "Processing": "In Inbox", "To Review": "In Inbox"}.get(status, status or "In Inbox")


def made_counts(rows):
	"""How many records were made from each source: accepted proposals that created a record, tasks made from a chat's open
	items, and wiki pages citing it."""
	out = {}
	items = [r.ref_name for r in rows if r.ref_doctype == "Life Inbox Item"]
	chats = [r.ref_name for r in rows if r.ref_doctype == "Life Chat Log"]
	if items:
		p = frappe.qb.DocType("Life Proposal")
		made = count_by("Life Proposal", "inbox_item", [p.inbox_item.isin(items), p.status == "Accepted", fn.IfNull(p.created_name, "") != ""])
		out.update({("Life Inbox Item", item): n for item, n in made.items()})
	if chats:
		o = frappe.qb.DocType("Life Chat Open Item")
		made = count_by("Life Chat Open Item", "parent", [o.parenttype == "Life Chat Log", o.parent.isin(chats), fn.IfNull(o.task, "") != ""])
		out.update({("Life Chat Log", chat): n for chat, n in made.items()})
	names = items + chats
	if names:
		s = frappe.qb.DocType("Life Note Source")
		rows = frappe.qb.from_(s).select(s.source_doctype, s.source_name, fn.Count(s.parent).distinct())  # a child table: the sources were read
		for dt, name, n in rows.where((s.parenttype == "Life Note") & s.source_name.isin(names)).groupby(s.source_doctype, s.source_name).run():
			out[(dt, name)] = out.get((dt, name), 0) + n
	return out


def agent_users():
	return frappe.get_all("Has Role", filters={"role": "Life Agent", "parenttype": "User"}, pluck="parent") or ["-"]  # system: role lookup, not a space record


def _where(space, tab=None, area=None, goal=None, from_date=None, to_date=None, status=None, intent=None, system=None, assistant=None,
		include_archived=0, open_items=0, scope="captures", sensitive=0, by=None):
	x = frappe.qb.DocType("Life Index")
	where = base_criteria(x, scope)
	if flag(sensitive):
		where.append(x.vault_locked == 1)
	if by == "me":  # written by me: not by an agent, and not one of the assistant's notes
		where.append(x.record_owner.notin(agent_users()) & (fn.IfNull(x.collection, "") != "Wiki"))
	elif by == "assistant":
		where.append(x.record_owner.isin(agent_users()) | (x.collection == "Wiki"))
	if int(open_items or 0):
		where.append((x.ref_doctype == "Life Chat Log") & (x.status == "Open"))
	if not int(include_archived or 0):
		where.append(x.is_archived == 0)
	if area:
		where.append(area_criterion(space, area, x, also_in="index"))
	if goal:
		where.append(x.goal == ("" if goal == "none" else goal))
	if from_date:
		where.append(x.record_date >= frappe.utils.getdate(from_date))
	if to_date:
		where.append(x.record_date <= frappe.utils.getdate(to_date))
	if status:
		status = str(status).strip().lower().replace("in inbox", "inbox")
		if status not in STATUS_NAMES:
			frappe.throw(_("status must be one of: {0}.").format(", ".join(STATUS_NAMES)), title=_("Unknown source status"))
		where.append(status_criteria(x)[status])
	if intent:
		where.append(x.intent == intent)
	if system:
		where.append(x.source_system == system.lower())
	if assistant:
		where.append(x.assistant == assistant)
	return where


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, tab: str | None = None, area: str | None = None, goal: str | None = None, from_date: str | None = None, to_date: str | None = None, status: str | None = None, intent: str | None = None,
		system: str | None = None, assistant: str | None = None, include_archived: bool | int | None = 0, open_items: bool | int | None = 0, sort: str | None = None, dir: str | None = None, start: int | None = 0,
		page_length: int | None = 50, filters: str | builtins.list | dict | None = None, order_by: str | None = None, summary: str | dict | None = None,
		scope: str | None = "captures", sensitive: bool | int | None = 0, by: str | None = None):
	"""Every capture of a space, newest first: inbox items, chat logs and Vault documents (kind Document, always sensitive)
	(Library > Captures). scope="all" adds the notes (Library > All).
	tab: all (default), notes (scope all), chats, voice, documents (with Vault documents), photos,
	articles, email (emails and email digests), text. sensitive=1 keeps the sensitive items; by=me or assistant keeps
	what a person or an agent wrote (the assistant's notes count as the assistant's).
	Filters: area (with its sub-areas, or "none"), goal, from_date and to_date (received), status (inbox, done, failed),
	intent (Process, Add to wiki, Just keep), system (gmail, claude…), assistant (for chats), open_items=1 (chats with an open item),
	include_archived=1 (archived sources too; they are left out otherwise, as on every list).
	Each row has: doctype, name, title, kind, received, area, status (In Inbox, Done, Failed), made (records made from it), thumbnail.
	`tabs` counts each tab under the same filters."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	tab = tab or "all"
	scope = "all" if scope == "all" else "captures"
	if tab not in TAB_NAMES:
		frappe.throw(_("tab must be one of: {0}.").format(", ".join(TAB_NAMES)), title=_("Unknown source tab"))
	if by not in (None, "", "me", "assistant"):
		frappe.throw(_("by must be me or assistant."), title=_("Unknown actor filter"))
	x = frappe.qb.DocType("Life Index")
	where = _where(space, tab, area, goal, from_date, to_date, status, intent, system, assistant, include_archived, open_items, scope, sensitive, by)
	where += filter_criteria("Life Index", filters, x)
	tabs = count_tabs("Life Index", index_where(space, where), tab_criteria(x))
	if scope != "all":
		tabs.pop("notes", None)
	if tab_criteria(x)[tab] is not None:
		where.append(tab_criteria(x)[tab])
	if permissions.is_agent():  # an agent the owner took off a source's readers does not see what came from it (issue 84)
		from lifeos.brain import source_page

		where += source_page.agent_blocked(space, x)
	where = index_where(space, where)
	if summary:
		return {"summary": group_summary("Life Index", where, summary, start, page_length), "tabs": tabs}
	terms = order_terms("Life Index", order_by, x, SORTS) or sort_terms(sort, dir, SORTS, x, [(x.record_date, Order.desc)])
	rows = list_query("Life Index", FIELDS, where, [*terms, (x.modified, Order.desc)]).limit(page_length).offset(start).run(as_dict=True)
	total = count_where("Life Index", where)
	out = {"space": space, "tab": tab, "sources": decorate(rows), "total": total, "tabs": tabs, "start": start, "page_length": page_length}
	if tab == "chats":  # the Chats tab's door: how many of these chats still have an open item
		out["with_open_items"] = count_where("Life Index", [*where, x.status == "Open"])
	return out


def decorate(rows):
	made = made_counts(rows)
	chats = [r.ref_name for r in rows if r.ref_doctype == "Life Chat Log"]
	o = frappe.qb.DocType("Life Chat Open Item")
	open_items = count_by("Life Chat Open Item", "parent", [o.parenttype == "Life Chat Log", o.parent.isin(chats), o.status == "Open"]) if chats else {}
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	goals = names_map("Life Goal", [r.goal for r in rows], "title")
	vault = _vault_fields([r.ref_name for r in rows if r.ref_doctype == "Life Vault Document"])
	agents = set(agent_users())
	out = []
	for r in rows:
		kind = KIND_OF.get(r.ref_doctype) or (r.media_kind or "Text")
		out.append({
			"doctype": r.ref_doctype, "name": r.ref_name, "title": r.title, "kind": kind, "received": str(r.record_date) if r.record_date else None,
			"area": r.area or None, "area_name": areas.get(r.area), "goal": r.goal or None, "goal_title": goals.get(r.goal),
			"status": status_label(r.ref_doctype, r.status), "intent": r.intent or None, "source_system": r.source_system or None,
			"assistant": r.assistant or None, "thumbnail": r.thumbnail or None, "is_archived": r.is_archived,
			"made": made.get((r.ref_doctype, r.ref_name), 0), "ref": REF_OF.get(r.ref_doctype, "source:") + r.ref_name,
			"open_count": open_items.get(r.ref_name, 0), "sensitive": 1 if r.vault_locked or r.ref_doctype == "Life Vault Document" else 0,
			"by_assistant": 1 if r.collection == "Wiki" or r.record_owner in agents else 0,
			**vault.get(r.ref_name, {}),
		})
	return out


KIND_OF = {"Life Chat Log": "Chat", "Life Vault Document": "Document", "Life Note": "Note"}
REF_OF = {"Life Chat Log": "chat:", "Life Vault Document": "vault:", "Life Note": "note:", "Life Inbox Item": "source:"}


def _vault_fields(names):
	"""What a Vault document keeps as a capture: its holder, last four characters, issue and expiry dates, reminder and badge."""
	if not names:
		return {}
	from lifeos.api.vault import badge

	rows = frappe.get_list("Life Vault Document", filters={"name": ("in", names)},
		fields=["name", "doc_type", "holder", "number_last4", "issue_date", "expiry_date", "remind_days_before"])
	holders = names_map("Life Person", [r.holder for r in rows], "full_name")
	out = {}
	for r in rows:
		out[r.name] = {"doc_type": r.doc_type, "holder": r.holder, "holder_name": holders.get(r.holder), "number_last4": r.number_last4,
			"issue_date": str(r.issue_date) if r.issue_date else None, "expiry_date": str(r.expiry_date) if r.expiry_date else None,
			"remind_days_before": r.remind_days_before, "expiry": badge(r.expiry_date, r.remind_days_before)}
	return out


@frappe.whitelist(methods=["GET"])
def made_from(doctype: str, name: str):
	"""What was made from one source: records created from it, and the wiki pages citing it."""
	if doctype not in SOURCE_DOCTYPES:
		frappe.throw(_("Not a source."), title=_("Not a source"))
	doc = permissions.get_doc_checked(doctype, name)
	out = []
	if doctype == "Life Inbox Item":
		for p in frappe.get_list("Life Proposal", filters={"inbox_item": doc.name, "status": "Accepted", "created_name": ["is", "set"]},
				fields=["kind", "preview", "created_doctype", "created_name"], order_by="sort_order asc, creation asc"):
			if not frappe.db.exists(p.created_doctype, p.created_name):
				continue
			if p.created_doctype == permissions.VAULT and permissions.vault_hidden(doc.space):
				continue
			if (p.created_doctype in permissions.SENSITIVE_DOCTYPES and permissions.vault_hidden(doc.space)
					and frappe.db.get_value(p.created_doctype, p.created_name, "is_sensitive")):
				continue
			out.append({"kind": p.kind, "doctype": p.created_doctype, "name": p.created_name, "title": links.title_of(p.created_doctype, p.created_name) or p.preview,
				"route": links.route_of(p.created_doctype, p.created_name)})
	else:
		for i in doc.open_items:
			if i.task and frappe.db.exists("Life Task", i.task):
				out.append({"kind": "Task", "doctype": "Life Task", "name": i.task, "title": links.title_of("Life Task", i.task),
					"route": links.route_of("Life Task", i.task)})
	n, ns = frappe.qb.DocType("Life Note"), frappe.qb.DocType("Life Note Source")
	where = [ns.parenttype == "Life Note", ns.source_doctype == doctype, ns.source_name == doc.name]
	guard = permissions.sensitive_criterion(doc.space, n)
	if guard is not None:
		where.append(guard)
	notes = frappe.qb.get_query("Life Note", fields=[n.name, n.title, n.collection], ignore_permissions=False).join(ns).on(ns.parent == n.name)  # the pages the user may read
	for crit in where:
		notes = notes.where(crit)
	for n in notes.distinct().orderby(n.title).run(as_dict=True):
		out.append({"kind": "Wiki page" if n.collection == "Wiki" else "Note", "doctype": "Life Note", "name": n.name, "title": n.title,
			"route": links.route_of("Life Note", n.name)})
	return out


@frappe.whitelist(methods=["POST"])
def refile(sources: str | builtins.list, area: str | None = None, goal: str | None = None):
	"""Set the area (and goal) of many sources at once, from the Sources list. `sources` is a list of
	{doctype, name}. People only."""
	if permissions.is_agent():
		frappe.throw(_("Only a person can re-file sources in bulk."), frappe.PermissionError, title=_("Only a person can re-file"))
	rows = parse(sources, []) or []
	if len(rows) > 500:
		frappe.throw(_("At most 500 sources at a time."), title=_("Too many sources at once"))
	done = 0
	for r in rows:
		if r.get("doctype") not in SOURCE_DOCTYPES:
			continue
		doc = permissions.get_doc_checked(r["doctype"], r["name"], "write")
		if area is not None:
			doc.area = area or None
		if goal is not None:
			doc.goal = goal or None
		doc.save()
		done += 1
	return {"updated": done}
