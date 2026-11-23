"""Context for agents (issue 54): a core card, an index and the one call that returns them (`lifeos.api.context.get`).

Plumbing only. The core card is generated from the owner's records (never written by hand), the index has one line for every person,
organisation and wiki page, and a task is matched to index lines by the words it shares with them. Both are cached for a space and
dropped when a record they are made from changes (`changed`, from hooks.py). What the check-wiki skill decides is in `wiki_check.py`.
"""
import re

import frappe
from frappe import _
from frappe.utils import getdate, today

from lifeos import permissions

CARD_WORDS = 1500  # the card stays under this many words
SUMMARY_WORDS = 15  # an index line's summary
PAGE_WORDS = 60  # how much of a page comes with its summary for a task
TOP_PAGES = 3
RULES_WORDS = 250
DEFAULT_BUDGET = 1500
STOP = set("a an and the of to for in on at with by from or is are was be do make get my our your this that it its as about into".split())
CACHE = "lifeos_context"
WATCHED = ("Life Note", "Life Person", "Life Goal", "Life Area", "Life Cycle", "Life Settings", "Life Space")


def words(text) -> int:
	return len((text or "").split())


def clip(text, n) -> str:
	"""At most n words of text, with an ellipsis when it was cut."""
	parts = (text or "").split()
	return " ".join(parts) if len(parts) <= n else " ".join(parts[:n]) + "…"


# ---- cache ----
def changed(doc=None, method=None):
	"""Hook: a record the card or the index is made from changed; both are rebuilt the next time they are asked for."""
	space = doc.get("space") if doc else None
	prefix = f"{CACHE}|{space}|" if space else f"{CACHE}|"
	keys = frappe.cache.get_keys(prefix, shared=True)
	frappe.cache.delete_value([k.decode() if isinstance(k, bytes) else k for k in keys], shared=True)  # str keys, so this request's copy goes too


def _cached(key, build):
	key = f"{CACHE}|{key}"
	got = frappe.cache.get_value(key, shared=True)
	if got is None:
		got = build()
		frappe.cache.set_value(key, got, shared=True)
	return got


# ---- the core card ----
def card(space, hidden=None) -> str:
	"""The summary of the owner that agents read first, in Markdown. `hidden`: leave out what is sensitive (default: as for the caller)."""
	hidden = permissions.vault_hidden(space) if hidden is None else hidden
	return _cached(f"{space}|card|{int(bool(hidden))}|{today()}", lambda: _build_card(space, hidden))


def _owner(space):
	user = frappe.db.get_value("Life Space", space, "owner_user")
	name = frappe.db.get_value("User", user, "full_name") if user else None
	role = frappe.db.get_value("Life Person", {"space": space, "user": user, "role": ("is", "set")}, "role") if user else None
	zone = frappe.db.get_single_value("System Settings", "time_zone")
	return name, role, zone


def _areas_lines(space):
	rows = frappe.get_all("Life Area", filters={"space": space, "is_on": 1, "is_archived": 0, "is_focus": 0}, fields=["name", "area_name", "parent_area", "description"],
		order_by="sort_order asc, creation asc", limit=200)
	parts = {}
	for r in rows:
		if r.parent_area:
			parts.setdefault(r.parent_area, []).append(r)
	lines = []
	for r in rows:
		if r.parent_area:
			continue
		sub = ", ".join(p.area_name for p in parts.get(r.name, []))
		lines.append(f"- **{r.area_name}**" + (f" ({sub})" if sub else "") + (f": {clip(r.description, 18)}" if r.description else ""))
	return lines


def _focus_lines(space):
	"""Each active focus with its standard and principles (issue 57), so agents work within them; none while "Use focuses" is off."""
	from lifeos.goals import areas

	if not areas.use_focuses():
		return []
	hidden = set(areas.off(space))
	lines = []
	for f in frappe.get_all("Life Area", filters={"space": space, "is_on": 1, "is_archived": 0, "is_focus": 1}, fields=["name", "area_name", "parent_area", "standard"],
			order_by="sort_order asc, creation asc", limit=100):
		if f.name in hidden:
			continue
		part = frappe.db.get_value("Life Area", f.parent_area, "area_name")
		bits = [f"- **{f.area_name}** ({part})"]
		if f.standard:
			bits.append(f"Standard: {clip(f.standard, 30)}")
		rules = frappe.get_all("Life Area Principle", filters={"parent": f.name, "parenttype": "Life Area"}, pluck="line", order_by="idx")
		if rules:
			bits.append("Principles: " + " ".join(f"{i}. {clip(r, 20)}" for i, r in enumerate(rules, 1)))
		lines.append(" ".join(bits))
	return lines


def _goal_lines(space):
	from lifeos.api import goals

	rows = goals.list(space=space, state="in_progress", page_length=100)["goals"]
	lines = []
	for g in rows:
		bits = [f"- **{g.title}** ({g.horizon}{', ' + g.area_name if g.area_name else ''})"]
		if g.done_when:
			bits.append(f"Done when: {clip(g.done_when, 25)}.")
		if g.progress and g.progress.get("label"):
			bits.append(f"Progress: {g.progress['label']}.")
		lines.append(" ".join(bits))
	return lines


def _cycle_line(space):
	from lifeos.goals import cycles

	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["title", "start_date", "end_date"], as_dict=True, order_by="start_date desc")
	if not cycle:
		return None
	week = cycles.week_of(cycle)
	where = f"week {min(max(week, 1), cycles.WEEKS)} of {cycles.WEEKS}" if week <= cycles.WEEKS else "past its last week"
	return f"{cycle.title}: {where} ({getdate(cycle.start_date):%-d %b} to {getdate(cycle.end_date):%-d %b %Y})."


def _preferences(space):
	s = frappe.get_cached_doc("Life Settings")
	bits = []
	if s.get("weekly_review_day"):
		bits.append(f"Weekly review on {s.weekly_review_day}" + (f" at {str(s.weekly_review_time)[:5]}" if s.get("weekly_review_time") else ""))
	if s.get("work_days"):
		bits.append(f"Work days {s.work_days}" + (f", {str(s.work_start)[:5]} to {str(s.work_end)[:5]}" if s.get("work_start") and s.get("work_end") else ""))
	if s.get("week_starts_on"):
		bits.append(f"Week starts on {s.week_starts_on}")
	if s.get("planning_period"):
		bits.append(f"Plans in {s.planning_period}")
	if s.get("score_target"):
		bits.append(f"Weekly score target {s.score_target}%")
	return [f"- {b}." for b in bits]


def _rules_text(space, hidden):
	row = frappe.db.get_value("Life Note", {"space": space, "is_rules": 1}, ["content_md", "is_sensitive"], as_dict=True)
	if not row or (hidden and row.is_sensitive):
		return ""
	text = re.sub(r"^#+\s.*$", "", row.content_md or "", flags=re.M)  # the headings; the rules are the lines
	return clip(re.sub(r"\n{2,}", "\n", text).strip(), RULES_WORDS)


def _build_card(space, hidden):
	name, role, zone = _owner(space)
	out = [f"# {name or _('The owner')}", ""]
	out.append(" · ".join(b for b in [role, f"Time zone {zone}" if zone else None, f"Today is {today()}"] if b))
	out += ["", "## Areas that are on", *(_areas_lines(space) or [_("- None yet.")]), "", "## Active goals", *(_goal_lines(space) or [_("- None yet.")])]
	focuses = _focus_lines(space)
	if focuses:
		out += ["", "## Focuses (ongoing work: work within these)", *focuses]
	cycle = _cycle_line(space)
	if cycle:
		out += ["", "## The 12 Week Year", cycle]
	prefs = _preferences(space)
	if prefs:
		out += ["", "## Standing preferences", *prefs]
	rules = _rules_text(space, hidden)
	if rules:
		out += ["", "## How notes are written", rules]
	text = "\n".join(out)
	while words(text) >= CARD_WORDS and out:  # never over the limit: the longest lists give way first
		longest = max(range(len(out)), key=lambda i: words(out[i]) if out[i].startswith("- ") else 0)
		if not out[longest].startswith("- "):
			break
		out.pop(longest)
		text = "\n".join(out)
	return text


# ---- the index ----
def index_lines(space, hidden=None) -> list:
	"""One line for every person, organisation and wiki page of the space (people and organisations once, from Life Person, never also as
	the wiki page that describes them): {name, doctype, title, kind, area, summary (15 words at most), updated}. Newest change first."""
	hidden = permissions.vault_hidden(space) if hidden is None else hidden
	return _cached(f"{space}|index|{int(bool(hidden))}", lambda: _build_index(space, hidden))


def _build_index(space, hidden):
	areas = {r.name: r.area_name for r in frappe.get_all("Life Area", filters={"space": space}, fields=["name", "area_name"], limit=1000)}
	notes = frappe.get_all("Life Note", filters={"space": space, "collection": "Wiki", "is_rules": 0, "is_archived": 0},
		fields=["name", "title", "summary", "area", "modified", "person", "is_sensitive"], order_by="modified desc", limit=5000)
	by_name = {n.name: n for n in notes}
	lines = []
	for p in frappe.get_all("Life Person", filters={"space": space}, fields=["name", "full_name", "kind", "role", "relation", "area", "wiki_page", "modified"], limit=5000):
		page = by_name.get(p.wiki_page)
		if hidden and page and page.is_sensitive:
			continue
		summary = (page.summary if page else None) or p.role or p.relation or p.kind
		lines.append({"name": p.name, "doctype": "Life Person", "title": p.full_name, "kind": (p.kind or "Person").lower(), "area": areas.get(p.area or (page.area if page else None)),
			"summary": clip(summary, SUMMARY_WORDS), "updated": str(max(p.modified, page.modified) if page else p.modified)[:10]})
	for n in notes:
		if n.person or (hidden and n.is_sensitive):
			continue
		lines.append({"name": n.name, "doctype": "Life Note", "title": n.title, "kind": "wiki", "area": areas.get(n.area), "summary": clip(n.summary, SUMMARY_WORDS),
			"updated": str(n.modified)[:10]})
	lines.sort(key=lambda r: (r["updated"], r["title"].lower()), reverse=True)
	return lines


def line_text(line) -> str:
	return f"- {line['title']} ({line['kind']}{', ' + line['area'] if line['area'] else ''}): {line['summary']} [{line['updated']}]"


# ---- one call ----
def _tokens(text) -> set:
	return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2 and t not in STOP}


def score(task, line) -> int:
	"""How well an index line fits a task: the whole title inside the task counts most, then the words they share."""
	title = " ".join(re.findall(r"[a-z0-9]+", line["title"].lower()))
	phrase = " ".join(re.findall(r"[a-z0-9]+", task.lower()))
	got = 10 if title and f" {title} " in f" {phrase} " else 0
	wanted = _tokens(task)
	return got + 3 * len(wanted & _tokens(line["title"])) + len(wanted & _tokens(line["summary"])) + len(wanted & _tokens(line["area"]))


def _excerpt(line, hidden) -> str:
	name = line["name"]
	if line["doctype"] == "Life Person":
		name = frappe.db.get_value("Life Person", name, "wiki_page")
	text = frappe.db.get_value("Life Note", name, "content_md") if name else ""
	return clip(re.sub(r"[#>*`]+|\[\[|\]\]", "", text or ""), PAGE_WORDS)


def get(space, task=None, budget=None) -> dict:
	"""The card and the index; with a task, the card, the index lines that match it and the summaries of the few pages that matter most,
	trimmed to `budget` words (the card always comes whole). Sensitive pages are left out for an agent whose space keeps them closed."""
	hidden = permissions.vault_hidden(space)
	text, lines = card(space, hidden), index_lines(space, hidden)
	task = " ".join((task or "").split())
	if not task:
		return {"space": space, "task": None, "card": text, "index": lines, "pages": [], "words": words(text) + sum(words(line_text(x)) for x in lines)}
	budget = max(int(budget or DEFAULT_BUDGET), 0)
	left = budget - words(text)
	scored = sorted(((score(task, x), x) for x in lines), key=lambda p: -p[0])
	matches = [x for s, x in scored if s > 0]
	kept = []
	for x in matches:
		cost = words(line_text(x))
		if cost > left:
			break
		kept.append(x)
		left -= cost
	pages = []
	for x in kept[:TOP_PAGES]:
		body = _excerpt(x, hidden)
		cost = words(x["summary"]) + words(body)
		if cost > left:
			body = clip(body, max(left - words(x["summary"]), 0))
			cost = words(x["summary"]) + words(body)
		if cost > left:
			break
		pages.append({"name": x["name"], "doctype": x["doctype"], "title": x["title"], "summary": x["summary"], "excerpt": body})
		left -= cost
	return {"space": space, "task": task, "budget": budget, "card": text, "index": kept, "pages": pages, "words": budget - left}
