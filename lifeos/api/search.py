"""Full-text search over Life Index, filtered by space membership."""
import re

import frappe
from frappe.query_builder import Order
from pypika.terms import Criterion, ValueWrapper

from lifeos import permissions
from lifeos.api.timeline import decorate
from lifeos.api.utils import FullText, area_criterion, flag, lens_area

WORD = re.compile(r"[\w][\w'’-]*", re.UNICODE)
FIELDS = ["ref_doctype", "ref_name", "kind", "title", "record_date", "area", "goal", "is_archived", "status", "record_owner", "also_in_csv", "space", "search_text"]


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


def find(x, where, order, score, limit):
	"""The index rows of one search. The spaces in `where` are the user's own (`require_space`, `user_spaces`), so the query builder runs without the
	permission query: it would add a membership test to every row of the full-text match, which took the common word from 45 to 750 ms."""
	query = frappe.qb.from_(x).select(*[x[f] for f in FIELDS], score).where(Criterion.all(where))  # system: the spaces were chosen from the user's own
	for term, way in order:
		query = query.orderby(term, order=way)
	return query.limit(limit).run(as_dict=True)


@frappe.whitelist(methods=["GET"])
def query(text: str, limit: int | None = 20, space: str | None = None, include_archived: bool | int | None = 0, area: str | None = None):
	"""Search notes, tasks, inbox items (including transcripts), chat logs, journal pages and vault titles.
	Only records in spaces the user belongs to are returned. Archived records are left out unless asked for.
	`area` (the lens, with `space`) keeps records filed under the area, a sub-area, or listing one in "also in"."""
	permissions.require_login()
	limit = min(max(int(limit or 20), 1), 100)
	if space:
		spaces = [permissions.require_space(space)]
	else:
		spaces = list(permissions.user_spaces())
		if frappe.session.user == "Administrator" and not spaces:
			spaces = frappe.get_all("Life Space", pluck="name")  # system: the admin's space list
	words = [w.lower() for w in WORD.findall(text or "")][:8]
	if not words or not spaces:
		return {"text": text, "results": []}
	x = frappe.qb.DocType("Life Index")
	where = [x.space.isin(spaces), x.kind != "Task Done"]
	closed = [s for s in spaces if permissions.vault_hidden(s)]  # an agent's spaces whose Vault is closed to it
	if closed:
		where.append(~(((x.vault_locked == 1) | (x.ref_doctype == "Life Vault Document")) & x.space.isin(closed)))
	if not flag(include_archived):
		where.append(x.is_archived == 0)
	area = lens_area(area)
	if area and len(spaces) == 1:
		where.append(area_criterion(spaces[0], area, x, also_in="index"))
	rows = []
	long_words = [w for w in words if len(w) >= 3]
	if long_words:
		match = FullText([x.title, x.search_text], " ".join(f"+{re.sub(r'[^\w]', '', w)}*" for w in long_words if re.sub(r"[^\w]", "", w)))
		rows = find(x, [*where, match], [(x.title.like(f"%{words[0]}%"), Order.desc), (match, Order.desc), (x.record_date, Order.desc)], match.as_("score"), limit)
	if not rows and (len(long_words) < len(words) or not long_words or frappe.flags.in_test):
		# short words the full-text index does not hold: fall back to a plain match. When every word is long enough and the
		# full-text index found nothing, a plain match would read every row's text and find nothing more (UX fixes, set 4).
		# Tests search rows of their own open transaction, which InnoDB's full-text index sees only after a commit.
		likes = [x.title.like(f"%{w}%") | x.search_text.like(f"%{w}%") for w in words]
		rows = find(x, [*where, *likes], [(x.record_date, Order.desc)], ValueWrapper(0).as_("score"), limit)
	for r in rows:
		r["snippet"] = _snippet(r.pop("search_text"), words)
		r.pop("score", None)
	return {"text": text, "results": decorate(rows)}
