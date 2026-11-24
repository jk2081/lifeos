"""Search the whole app (issue 98), on Frappe's Global Search table.

Global Search checks the record type, not our spaces, so every hit is opened and passes `frappe.has_permission` (our space
rules) before it is returned; more rows than shown are asked for to make up for the ones dropped.
"""
import re

import frappe
from frappe.query_builder import Order
from pypika.terms import Criterion, ValueWrapper

from lifeos import permissions
from lifeos.api.utils import FullText, descendants, flag, lens_area
from lifeos.library import globalsearch, links

WORD = re.compile(r"[\w][\w'’-]*", re.UNICODE)
LABEL = re.compile(r"^.*? : ", re.DOTALL)  # Global Search stores "Label : value" for each field
ASK_MORE = 4  # rows asked for per row shown
GROUPS = {
	"Task": "Tasks", "Capture": "Captures", "Note": "Notes", "Wiki page": "Wiki pages", "Chat": "Chats", "Event": "Events", "Goal": "Goals",
	"Cycle": "Cycles", "Focus": "Focuses", "Area": "Areas", "Person": "People", "Habit": "Habits", "Weekly review": "Weekly reviews",
	"Insight": "Insights", "Ask thread": "Ask threads", "Vault document": "Vault documents", "Needs you": "Needs you", "Skill": "Skills",
	"Source": "Sources",
}
# where a record opens when links.route_of has no page of its own for it
ROUTES = {
	"Event": "/today?open=event:{0}", "Life Area": "/settings?tab=areas", "Life Cycle": "/goals/cycles", "Life Person": "/library/people/{0}",
	"Life Habit": "/settings?tab=habits", "Life Review": "/review", "Life Insight": "/ask?tab=insights", "Life Ask Thread": "/ask?thread={0}",
	"Life Proposal": "/brain", "Life Skill": "/brain/skills/{0}", "Life Source Setting": "/brain/sources",
}
DATE_FIELD = {"Event": "starts_on", "Life Task": "due_date", "Life Chat Log": "date", "Life Goal": "target_date", "Life Cycle": "start_date"}


def _text(content):
	"""What a hit says, without the field labels Global Search adds."""
	return " ".join(LABEL.sub("", part, count=1) for part in (content or "").split(" ||| "))


def _matches(text, words):
	"""A word of three letters or more matches the start of any word; a shorter one matches anywhere."""
	low = text.lower()
	tokens = WORD.findall(low)
	return all(any(t.startswith(w) for t in tokens) if len(w) >= 3 else w in low for w in words)


def _snippet(text, words, width=140):
	text = " ".join((text or "").split())
	if not text:
		return ""
	low = text.lower()
	at = min((low.find(w) for w in words if low.find(w) >= 0), default=-1)
	if at < 0:
		return text[:width] + ("…" if len(text) > width else "")
	start = max(0, at - width // 3)
	end = min(len(text), start + width)
	return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


FULLTEXT_FROM = 4  # the database's full-text index holds words of four letters or more; shorter ones are matched on the text itself


def _comments():
	"""The comments a person wrote on a record. Frappe also writes one for every attachment, edit and assignment; those are not searched,
	and thousands of them would otherwise fill the rows asked for before the records are reached."""
	c = frappe.qb.DocType("Comment")
	on = [dt for dt in globalsearch.FIELDS if dt != "Comment"]
	return frappe.qb.from_(c).select(c.name).where((c.comment_type == "Comment") & c.reference_doctype.isin(on))  # system: Global Search holds every comment; the parent record's permission decides


def _hits(words, rows):
	"""Global Search rows (doctype, name, content, rank) for the words: the full-text index narrows by the long words (as a prefix), a
	pattern on the text finds the start of the short ones. A test reads the text only: the index sees an open transaction after a commit."""
	gs = frappe.qb.Table("__global_search")
	where = [gs.doctype.isin(list(globalsearch.FIELDS)), (gs.doctype != "Comment") | gs.name.isin(_comments())]
	indexed = [] if frappe.flags.in_test else [re.sub(r"[^\w]", "", w) for w in words if len(w) >= FULLTEXT_FROM]
	indexed = [w for w in indexed if w]
	for w in words:
		if len(w) < FULLTEXT_FROM or frappe.flags.in_test:
			where.append(gs.content.regexp(r"\b" + re.escape(w)))
	rank = FullText([gs.content], " ".join(f"+{w}*" for w in indexed)) if indexed else None
	if rank is not None:
		where.append(rank)
	query = frappe.qb.from_(gs).select(gs.doctype, gs.name, gs.content, (rank if rank is not None else ValueWrapper(0)).as_("rank")).where(Criterion.all(where))
	if rank is not None:
		query = query.orderby(rank, order=Order.desc)
	return query.limit(rows).run(as_dict=True)  # system: Global Search holds every record; each hit is permission-checked by the caller


class Finder:
	"""Opens Global Search hits as the signed-in user and keeps those they may see."""

	def __init__(self, words, space, include_archived, area):
		self.words, self.space, self.archived = words, space, include_archived
		self.area_ids = set(descendants(space, area)) if space and area and area != "none" else None
		self.area_none = area == "none"
		self.names = {}

	def area_name(self, area):
		if area and area not in self.names:
			self.names[area] = frappe.db.get_value("Life Area", area, "area_name")
		return self.names.get(area)

	def doc_of(self, doctype, name):
		"""The record, when the signed-in user may read it and it is wanted; else None."""
		if not frappe.db.exists(doctype, name):
			return None
		doc = frappe.get_doc(doctype, name)
		if not frappe.has_permission(doctype, "read", doc=doc):
			return None
		if doc.get("is_archived") and not self.archived:
			return None
		space = doc.get("space") or doc.get("life_space")
		if self.space and space and space != self.space:
			return None
		if self.area_ids is not None or self.area_none:
			area = doc.get("area") or ""
			also = {r.area for r in doc.get("also_in") or []}
			if self.area_none and area:
				return None
			if self.area_ids is not None and area not in self.area_ids and not (also & self.area_ids):
				return None
		return doc

	def result(self, hit):
		"""One result row for a Global Search hit, or None. A comment stands for the record it is on."""
		text = _text(hit.content)
		if not _matches(text, self.words):
			return None
		doctype, name = hit.doctype, hit.name
		if doctype == "Comment":
			comment = frappe.db.get_value("Comment", name, ["comment_type", "reference_doctype", "reference_name"], as_dict=True)
			if not comment or comment.comment_type != "Comment" or comment.reference_doctype not in globalsearch.FIELDS or not comment.reference_name:
				return None
			doctype, name = comment.reference_doctype, comment.reference_name
		doc = self.doc_of(doctype, name)
		if doc is None:
			return None
		kind = globalsearch.KIND[doctype]
		if doctype == "Life Note" and doc.collection == "Wiki":
			kind = "Wiki page"
		elif doctype == "Life Area" and doc.is_focus:
			kind = "Focus"
		date = doc.get(DATE_FIELD.get(doctype, "creation")) or doc.creation
		area = doc.parent_area if doctype == "Life Area" else doc.get("area")
		return frappe._dict({
			"ref_doctype": doctype, "ref_name": name, "kind": kind, "group": GROUPS[kind], "title": doc.get_title() or "",
			"record_date": str(date)[:10] if date else None, "area": area or "", "area_name": self.area_name(area),
			"space": doc.get("space") or doc.get("life_space") or "", "is_archived": 1 if doc.get("is_archived") else 0,
			"snippet": "" if doctype == "Life Vault Document" else _snippet(text, self.words), "rank": hit.rank,
			"route": ROUTES.get(doctype, "").format(name) or links.route_of(doctype, name),
		})


@frappe.whitelist(methods=["GET"])
def query(text: str, limit: int | None = 20, space: str | None = None, include_archived: bool | int | None = 0, area: str | None = None):
	"""Search everything the person can open: tasks, captures, notes, chats, events, goals, areas, people, habits, reviews, insights,
	Ask threads, Vault document titles, items in Needs you, skills, sources and comments on them. Results are grouped by kind, best
	match first. Archived records are left out unless asked for. `area` (the lens, with `space`) keeps records filed under it."""
	permissions.require_login()
	limit = min(max(int(limit or 20), 1), 100)
	if space:
		space = permissions.require_space(space)
	words = [w.lower() for w in WORD.findall(text or "")][:8]
	if not words:
		return {"text": text, "results": []}
	finder = Finder(words, space, flag(include_archived), lens_area(area) if space else None)
	seen, results = set(), []
	for hit in _hits(words, min(limit * ASK_MORE, 400)):
		row = finder.result(hit)
		if row and (row["ref_doctype"], row["ref_name"]) not in seen:
			seen.add((row["ref_doctype"], row["ref_name"]))
			results.append(row)
	results = results[:limit]
	order = list(dict.fromkeys(r["group"] for r in results))  # groups by their best match; rows keep their rank inside
	results.sort(key=lambda r: order.index(r["group"]))
	for r in results:
		r.pop("rank")
	return {"text": text, "results": results}
