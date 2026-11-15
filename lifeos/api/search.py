"""Full-text search over Life Index, filtered by space membership."""
import re

import frappe

from lifeos import permissions
from lifeos.api.timeline import decorate
from lifeos.api.utils import flag

WORD = re.compile(r"[\w][\w'’-]*", re.UNICODE)
FIELDS = "ref_doctype, ref_name, kind, title, record_date, area, project, is_archived, status, record_owner, also_in_csv, space, search_text"


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


@frappe.whitelist()
def query(text, limit=20, space=None, include_archived=0):
	"""Search notes, tasks, inbox items (including transcripts), chat logs, journal pages and vault titles.
	Only records in spaces the user belongs to are returned. Archived records are left out unless asked for."""
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
		where += " and not (ref_doctype = 'Life Vault Document' and space in %(closed)s)"
	if not flag(include_archived):
		where += " and is_archived = 0"
	values = {"spaces": spaces, "limit": limit, "closed": closed or [""]}
	rows = []
	long_words = [w for w in words if len(w) >= 3]
	if long_words:
		clean = [re.sub(r"[^\w]", "", w) for w in long_words]
		values["q"] = " ".join(f"+{w}*" for w in clean if w)
		rows = frappe.db.sql(
			f"""select {FIELDS}, match(title, search_text) against (%(q)s in boolean mode) as score from `tabLife Index`
			where {where} and match(title, search_text) against (%(q)s in boolean mode)
			order by (title like %(starts)s) desc, score desc, record_date desc limit %(limit)s""",
			{**values, "starts": f"%{words[0]}%"}, as_dict=True)
	if not rows:
		# short words, or text the full-text index does not tokenise: fall back to a plain match
		likes = " and ".join(f"(title like %(w{i})s or search_text like %(w{i})s)" for i in range(len(words)))
		like_values = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
		rows = frappe.db.sql(
			f"select {FIELDS}, 0 as score from `tabLife Index` where {where} and {likes} order by record_date desc limit %(limit)s",
			{**values, **like_values}, as_dict=True)
	for r in rows:
		r["snippet"] = _snippet(r.pop("search_text"), words)
		r.pop("score", None)
	return {"text": text, "results": decorate(rows)}
