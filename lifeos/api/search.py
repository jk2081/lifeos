"""Full-text search over Life Index, filtered by space membership."""
import re

import frappe

from lifeos import permissions
from lifeos.api.timeline import decorate
from lifeos.api.utils import area_filter, flag, lens_area

WORD = re.compile(r"[\w][\w'’-]*", re.UNICODE)
FIELDS = "ref_doctype, ref_name, kind, title, record_date, area, goal, is_archived, status, record_owner, also_in_csv, space, search_text"


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
			spaces = frappe.get_all("Life Space", pluck="name")
	words = [w.lower() for w in WORD.findall(text or "")][:8]
	if not words or not spaces:
		return {"text": text, "results": []}
	where = "space in %(spaces)s and kind != 'Task Done'"
	closed = [s for s in spaces if permissions.vault_hidden(s)]  # an agent's spaces whose Vault is closed to it
	if closed:
		where += " and not ((vault_locked = 1 or ref_doctype = 'Life Vault Document') and space in %(closed)s)"
	if not flag(include_archived):
		where += " and is_archived = 0"
	values = {"spaces": spaces, "limit": limit, "closed": closed or [""]}
	area = lens_area(area)
	if area and len(spaces) == 1:
		where += " and " + area_filter(spaces[0], area, "area", values, also_in="index")
	rows = []
	long_words = [w for w in words if len(w) >= 3]
	if long_words:
		clean = [re.sub(r"[^\w]", "", w) for w in long_words]
		values["q"] = " ".join(f"+{w}*" for w in clean if w)
		# nosemgrep: frappe-sql-format-injection -- FIELDS and WHERE are fixed fragments; the search text is the %(q)s parameter
		rows = frappe.db.sql(
			f"""select {FIELDS}, match(title, search_text) against (%(q)s in boolean mode) as score from `tabLife Index`
			where {where} and match(title, search_text) against (%(q)s in boolean mode)
			order by (title like %(starts)s) desc, score desc, record_date desc limit %(limit)s""",
			{**values, "starts": f"%{words[0]}%"}, as_dict=True)
	if not rows and (len(long_words) < len(words) or not long_words or frappe.flags.in_test):
		# short words the full-text index does not hold: fall back to a plain match. When every word is long enough and the
		# full-text index found nothing, a plain match would read every row's text and find nothing more (UX fixes, set 4).
		# Tests search rows of their own open transaction, which InnoDB's full-text index sees only after a commit.
		likes = " and ".join(f"(title like %(w{i})s or search_text like %(w{i})s)" for i in range(len(words)))
		like_values = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
		# nosemgrep: frappe-sql-format-injection -- FIELDS, WHERE and the LIKE placeholders are fixed fragments; each word is a %(wN)s parameter
		rows = frappe.db.sql(
			f"select {FIELDS}, 0 as score from `tabLife Index` where {where} and {likes} order by record_date desc limit %(limit)s",
			{**values, **like_values}, as_dict=True)
	for r in rows:
		r["snippet"] = _snippet(r.pop("search_text"), words)
		r.pop("score", None)
	return {"text": text, "results": decorate(rows)}
