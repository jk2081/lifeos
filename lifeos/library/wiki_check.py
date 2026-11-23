"""The light weekly wiki check (issue 54), the day before the weekly review.

The built-in skill `check-wiki` decides: which orphan page to link or archive, which names deserve a page, which summaries no longer match
their page, and which two facts contradict each other. This file is plumbing: it gathers the pages and captures, checks what the skill
says against the records (a fact must be in its page, a name must be in three captures), writes the change as the Life Brain with a
Life Wiki Change each (so it can be undone) and turns a contradiction into a Life Wiki Finding that waits in Brain > Needs you.
"""
import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, today

from lifeos.library import archive
from lifeos import permissions
from lifeos.skills import call

SLUG = "check-wiki"
MAX_PAGES = 60  # pages sent to the skill in one check, the least recently changed first
PAGE_WORDS = 160
CAPTURE_DAYS = 90
MAX_CAPTURES = 150
CAPTURE_WORDS = 60
MIN_MENTIONS = 3  # captures that name something before it gets a page
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _norm(text) -> str:
	return " ".join((text or "").lower().split())


def _excerpt(text, n=PAGE_WORDS) -> str:
	return " ".join((text or "").split()[:n])


# ---- what the skill is shown ----
def _link_counts(space) -> dict:
	rows = frappe.db.sql("""select name, sum(out_n) as out_n, sum(in_n) as in_n from (
		select from_name as name, count(*) as out_n, 0 as in_n from `tabLife Link` where space = %(s)s and from_doctype = 'Life Note' and to_name != from_name group by from_name
		union all
		select to_name, 0, count(*) from `tabLife Link` where space = %(s)s and to_doctype = 'Life Note' and to_name != from_name group by to_name) x group by name""",
		{"s": space}, as_dict=True)
	return {r.name: (int(r.in_n or 0), int(r.out_n or 0)) for r in rows}


def pages_for(space) -> list:
	"""The wiki pages the check looks at (not the rules page, not a person's or organisation's page, nothing sensitive or archived)."""
	rows = frappe.get_all("Life Note", filters={"space": space, "collection": "Wiki", "is_rules": 0, "is_archived": 0, "is_sensitive": 0, "person": ("is", "not set")},
		fields=["name", "title", "summary", "content_md", "modified"], order_by="modified asc", limit=MAX_PAGES)
	counts = _link_counts(space)
	out = []
	for i, r in enumerate(rows, 1):
		got_in, got_out = counts.get(r.name, (0, 0))
		out.append({"id": f"P{i}", "name": r.name, "title": r.title, "summary": r.summary, "text": _excerpt(r.content_md), "text_full": r.content_md or "",
			"linked_from": got_in, "links_to": got_out, "orphan": not got_in and not got_out})
	return out


def captures_for(space) -> list:
	rows = frappe.get_all("Life Inbox Item", filters={"space": space, "is_sensitive": 0, "is_archived": 0, "received_on": (">=", add_days(today(), -CAPTURE_DAYS))},
		fields=["name", "title", "raw_text", "summary_md"], order_by="received_on desc", limit=MAX_CAPTURES)
	return [{"id": f"C{i}", "name": r.name, "title": r.title, "text": _excerpt(r.summary_md or r.raw_text, CAPTURE_WORDS),
		"haystack": _norm(" ".join([r.title or "", r.raw_text or "", r.summary_md or ""]))} for i, r in enumerate(rows, 1)]


def _known_names(space) -> list:
	names = frappe.get_all("Life Note", filters={"space": space, "collection": "Wiki"}, pluck="title", limit=5000)
	for p in frappe.get_all("Life Person", filters={"space": space}, fields=["full_name", "aliases"], limit=5000):
		names += [p.full_name, *[a.strip() for a in (p.aliases or "").replace("\n", ",").split(",")]]
	return sorted({n for n in names if n})


# ---- the check ----
def run(space) -> dict:
	"""Check one space. Returns what was done; {"skipped": reason} when the skill gave no answer (no key, over the cap, switched off)."""
	pages, captures = pages_for(space), captures_for(space)
	known = _known_names(space)
	if not pages and not captures:
		return {"linked": [], "archived": [], "created": [], "summaries": [], "findings": []}
	data = {"pages": [{k: v for k, v in p.items() if k not in ("name", "text_full")} for p in pages],
		"captures": [{k: v for k, v in c.items() if k not in ("name", "haystack")} for c in captures], "known_names": known}
	answer = call.ask(SLUG, data, space)
	if not answer:
		return {"skipped": answer.reason}
	by_id = {p["id"]: p for p in pages}
	out = {"linked": [], "archived": [], "created": [], "summaries": [], "findings": []}
	for o in answer.get("orphans") or []:
		_orphan(space, by_id, o, out)
	for m in answer.get("missing") or []:
		_missing(space, captures, known, m, out)
	for s in answer.get("stale") or []:
		_stale(by_id, s, out)
	for c in answer.get("contradictions") or []:
		_contradiction(space, by_id, c, out)
	return out


def _save(doc, before, note):
	"""Save a page as the Life Brain, with one Life Wiki Change."""
	from lifeos.api import wiki

	frappe.flags.lifeos_wiki_api = True
	try:
		doc.save(ignore_permissions=True)
	finally:
		frappe.flags.lifeos_wiki_api = False
	wiki.log_change(doc, "Edited", before, doc.content_md, note, by=permissions.BRAIN_USER)


def _orphan(space, by_id, o, out):
	page = by_id.get(o.get("page"))
	if not page or not page["orphan"]:
		return
	if o.get("action") == "archive":
		archive.set_archived("Life Note", page["name"], True, "Auto")
		out["archived"].append(page["name"])
		return
	target = by_id.get(o.get("link_to"))
	if not target or target["name"] == page["name"]:
		return
	doc = frappe.get_doc("Life Note", target["name"])
	line = f"See also: [[{page['title']}]]"
	if line in (doc.content_md or ""):
		return
	before = doc.content_md or ""
	doc.content_md = before.rstrip() + "\n\n" + line + "\n"
	_save(doc, before, _("Weekly wiki check: linked the page {0}, which nothing linked to.").format(page["title"]))
	out["linked"].append(page["name"])


def _missing(space, captures, known, m, out):
	"""A name the skill says deserves a page: made only when it is in MIN_MENTIONS captures and has no page, person or other name yet."""
	name = " ".join((m.get("name") or "").split())
	if not name or _norm(name) in {_norm(k) for k in known}:
		return
	found = [c for c in captures if _norm(name) in c["haystack"]]
	if len(found) < MIN_MENTIONS:
		return
	from lifeos.api import wiki

	summary = " ".join((m.get("summary") or "").split()) or name
	body = "\n".join([f"# {name}", "", summary, "", "Seen in:", *[f"- {c['title']}" for c in found[:8]]])
	sources = [{"doctype": "Life Inbox Item", "name": c["name"]} for c in found[:wiki.MAX_SOURCES]]
	frappe.flags.lifeos_wiki_api = True
	try:
		doc = frappe.get_doc({"doctype": "Life Note", "space": space, "title": name[:140], "collection": "Wiki", "summary": summary[:500], "content_md": body,
			"sources": [{"source_doctype": s["doctype"], "source_name": s["name"]} for s in sources]})
		doc.insert(ignore_permissions=True)
	finally:
		frappe.flags.lifeos_wiki_api = False
	wiki.log_change(doc, "Created", "", doc.content_md, _("Weekly wiki check: {0} came up in {1} captures and had no page.").format(name, len(found)), by=permissions.BRAIN_USER)
	known.append(name)
	out["created"].append(doc.name)


def _stale(by_id, s, out):
	page = by_id.get(s.get("page"))
	summary = " ".join((s.get("summary") or "").split())
	if not page or not summary or summary == page["summary"]:
		return
	doc = frappe.get_doc("Life Note", page["name"])
	doc.summary = summary[:500]
	_save(doc, doc.content_md, _("Weekly wiki check: the summary no longer matched the page."))
	out["summaries"].append(page["name"])


def _contradiction(space, by_id, c, out):
	"""Two facts that cannot both be true, each found word for word in its page; one Life Wiki Finding, once."""
	options = []
	for o in c.get("options") or []:
		page, fact = by_id.get(o.get("page")), " ".join((o.get("fact") or "").split())
		if page and fact and _norm(fact) in _norm(page["text_full"]) and fact not in [x["fact"] for x in options]:
			src = frappe.db.get_value("Life Note Source", {"parent": page["name"], "parenttype": "Life Note"}, ["source_doctype", "source_name"], order_by="added_on desc, creation desc", as_dict=True)
			options.append({"page": page["name"], "title": page["title"], "fact": fact, "source_doctype": src.source_doctype if src else None,
				"source_name": src.source_name if src else None})
	if len(options) < 2:
		return
	topic = " ".join((c.get("topic") or "").split())[:140] or options[0]["title"]
	key = _norm(topic) + "|" + "|".join(sorted(_norm(o["fact"]) for o in options))
	for f in frappe.get_all("Life Wiki Finding", filters={"space": space}, fields=["name", "topic", "options"], limit=2000):
		have = "|".join(sorted(_norm(o["fact"]) for o in json.loads(f.options or "[]")))
		if _norm(f.topic) + "|" + have == key:
			return
	question = " ".join((c.get("question") or "").split()) or _("The pages disagree about {0}: keep which?").format(topic)
	doc = frappe.get_doc({"doctype": "Life Wiki Finding", "space": space, "topic": topic, "question": question[:500], "options": json.dumps(options), "status": "Open"})
	doc.insert(ignore_permissions=True)
	out["findings"].append(doc.name)


# ---- Needs you ----
def open_findings(space) -> list:
	rows = frappe.get_all("Life Wiki Finding", filters={"space": space, "status": "Open"}, fields=["name", "topic", "question", "options", "creation"], order_by="creation asc", limit=50)
	for r in rows:
		r["options"] = json.loads(r.options or "[]")
		for o in r["options"]:
			o["source_title"] = _source_title(o)
	return rows


def _source_title(o):
	from lifeos.library import links

	return links.title_of(o["source_doctype"], o["source_name"]) if o.get("source_doctype") and o.get("source_name") else None


def decide(finding, choice) -> dict:
	"""The owner keeps one fact. Every page that holds another reading of it now says the chosen one, and each page that changed cites the
	chosen fact's source, with the day. The finding is closed."""
	doc = frappe.get_doc("Life Wiki Finding", finding)
	permissions.require_space(doc.space, write=True)
	if doc.status != "Open":
		frappe.throw(_("This has been decided already."), title=_("Already decided"))
	options = json.loads(doc.options or "[]")
	choice = int(choice)
	if not 0 <= choice < len(options):
		frappe.throw(_("Choose one of the options."), title=_("Option is not valid"))
	keep = options[choice]
	changed = []
	for i, o in enumerate(options):
		if i == choice or o["fact"] == keep["fact"]:
			continue
		page = frappe.get_doc("Life Note", o["page"])
		before = page.content_md or ""
		text = re.sub(re.escape(o["fact"]), lambda _m: keep["fact"], before, count=1) if o["fact"] in before else None
		if text is None:
			text = before.rstrip() + "\n\n" + keep["fact"] + "\n"
		page.content_md = text
		have = {(r.source_doctype, r.source_name) for r in page.sources}
		if keep.get("source_doctype") and (keep["source_doctype"], keep["source_name"]) not in have and frappe.db.exists(keep["source_doctype"], keep["source_name"]):
			page.append("sources", {"source_doctype": keep["source_doctype"], "source_name": keep["source_name"]})
		_save_as_owner(page, before, _("Decided in Needs you: {0}").format(keep["fact"][:200]), keep)
		changed.append(page.name)
	frappe.db.set_value("Life Wiki Finding", doc.name, {"status": "Decided", "chosen": choice, "decided_on": now_datetime(), "decided_by": frappe.session.user})
	return {"finding": doc.name, "changed": changed, "kept": keep["fact"]}


def _save_as_owner(page, before, note, keep):
	from lifeos.api import wiki

	frappe.flags.lifeos_wiki_api = True
	try:
		page.save()
	finally:
		frappe.flags.lifeos_wiki_api = False
	src = {"doctype": keep["source_doctype"], "name": keep["source_name"]} if keep.get("source_doctype") else None
	wiki.log_change(page, "Edited", before, page.content_md, note, src)


# ---- the schedule ----
def run_weekly():
	"""The daily job: on the day before the weekly review, check each space's wiki (the skill decides; nothing happens without a key)."""
	review = frappe.db.get_single_value("Life Settings", "weekly_review_day") or "Sunday"
	if review not in DAYS or DAYS[(DAYS.index(review) - 1) % 7] != DAYS[getdate(today()).weekday()]:
		return
	for space in frappe.get_all("Life Space", pluck="name"):
		try:
			run(space)
		except Exception:
			frappe.log_error(title=f"check-wiki {space}")
