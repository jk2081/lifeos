"""Brain > Needs you (issue 17): what the Brain asks the owner to decide, and two numbers about what it did on its own.

Nothing here decides anything: Keep, Change and Drop use review.decide and review.decide_all, as the Inbox did.
"""
import math

import frappe
from frappe import _
from frappe.query_builder import Case, Field, Order
from frappe.query_builder import functions as fn
from frappe.utils import add_to_date, now_datetime

from lifeos import permissions
from lifeos.brain import agent_page, proposals, rules
from lifeos.goals import readings
from lifeos.library import wiki_check
from lifeos.api.utils import area_criterion, lens_area, names_map, page
from lifeos.skills import lessons

MAX_ROWS = 7
SECONDS_EACH = 20  # the guess at how long one decision takes: "about 2 minutes" for 7
# the kind as a person says it: a Reading is "Read later" (the mockup's word)
KIND_LABEL = {"Reading": "Read later", "New Subject": "New page", "Same Subject": "Same as?"}


def kind_label(kind):
	return KIND_LABEL.get(kind, kind)


def sees(space, i):
	"""The criterion for the captures the user reads: an agent never reads the source a Vault document was made from, nor a capture
	marked sensitive. None for everyone else."""
	return (fn.IfNull(i.vault_document, "") == "") & (i.is_sensitive == 0) if permissions.vault_hidden(space) else None


def captures(fields, where):
	"""A permission-checked select on the inbox items of a space that the user reads, with the criteria."""
	query = frappe.qb.get_query("Life Inbox Item", fields=fields, ignore_permissions=False)
	for crit in where:
		query = query.where(crit)
	return query


def proposals_of(i, *criteria):
	"""A count of the proposals of the inbox item `i` (correlated), as a select term."""
	q = frappe.qb.DocType("Life Proposal").as_("q")
	query = frappe.qb.from_(q).select(fn.Count("*")).where(q.inbox_item == i.name)
	for crit in criteria:
		query = query.where(crit(q))
	return query


def _open(space):
	return 0 if permissions.vault_hidden(space) else 1


def _day_numbers(space):
	"""Captures of the last 24 hours (not archived): how many, from how many sources, and how many the Brain filed with no
	decision from the owner (Done, and no proposal the owner accepted or rejected), under how many areas and goals."""
	since = add_to_date(now_datetime(), hours=-24)
	i = frappe.qb.DocType("Life Inbox Item")
	where = [i.space == space, i.is_archived == 0, i.received_on >= since, *([g] if (g := sees(space, i)) is not None else [])]
	decided = proposals_of(i, lambda q: q.status != "Pending", lambda q: fn.IfNull(q.filed_by, "") == "").as_("decided")
	rows = captures([i.name, i.source_type, i.status, i.area, i.goal, decided], where).run(as_dict=True)
	own = [r for r in rows if r.status == "Done" and not r.decided]
	return {
		"came_in": {"count": len(rows), "sources": len({r.source_type for r in rows})},
		"filed": {"count": len(own), "areas": len({r.area for r in own if r.area}), "goals": len({r.goal for r in own if r.goal})},
	}


@frappe.whitelist(methods=["GET"])
def needs_you(space: str | None = None, limit: int = MAX_ROWS):
	"""The Needs you screen: `came_in` and `filed` (the last 24 hours), and `rows`, at most `limit` (7) pending proposals, oldest
	capture first, each with the Brain's best guess. `total` is every pending proposal; `waiting` counts captures still with the agent, and `unfiled` lists captures that failed and
	could not be placed. A row with `alt_area` is torn between two areas."""
	space = permissions.resolve_space(space)
	limit = max(1, min(int(limit or MAX_ROWS), 50))
	out = _day_numbers(space)
	i, p = frappe.qb.DocType("Life Inbox Item"), frappe.qb.DocType("Life Proposal")
	guard = sees(space, i)
	where = [p.status == "Pending", i.space == space, i.is_archived == 0, *([guard] if guard is not None else [])]
	query = frappe.qb.get_query("Life Proposal", fields=[fn.Count("*")], ignore_permissions=False).join(i).on(i.name == p.inbox_item)
	for crit in where:
		query = query.where(crit)
	total = query.run()[0][0]
	pending = proposals_of(i, lambda q: q.status == "Pending").as_("item_pending")
	found = frappe.qb.get_query("Life Proposal", fields=[p.name.as_("proposal"), p.kind, p.preview, p.payload, p.confidence, p.reason, p.alt_area],
		ignore_permissions=False).join(i).on(i.name == p.inbox_item)
	# get_query drops fields that are not the DocType's own, so the joined ones are selected on the query
	found = found.select(i.name.as_("item"), i.title.as_("item_title"), i.source_type, i.received_on, i.is_sensitive, pending)
	for crit in where:
		found = found.where(crit)
	found = found.orderby(i.received_on).orderby(i.creation).orderby(p.sort_order).orderby(p.creation).limit(limit).run(as_dict=True)
	areas = names_map("Life Area", [x for r in found for x in (_payload(r).get("area"), r.alt_area) if x], "area_name")
	rows = []
	for r in found:
		data = _payload(r)
		area = data.get("area")
		takes_area = "area" in proposals.SCHEMA[r.kind]["fields"]
		rows.append({
			"proposal": r.proposal, "item": r.item, "source": r.source_type, "received_on": str(r.received_on) if r.received_on else None,
			"title": r.item_title if r.item_pending == 1 else (r.preview or r.item_title), "reason": r.reason, "kind": r.kind,
			"kind_label": kind_label(r.kind), "preview": r.preview, "confidence": r.confidence, "payload": data,
			"area": area, "area_name": areas.get(area), "alt_area": r.alt_area, "alt_area_name": areas.get(r.alt_area),
			"takes_area": takes_area, "unfiled": takes_area and not area, "item_pending": r.item_pending,
			# a Goal with no "Done when" while the setting is on waits for the owner to write one (Change opens the capture)
			"blocked": _(readings.REQUIRED_MESSAGE) if r.kind in ("Goal", "Month Goal") and not readings.has_finish_line(data) and readings.done_when_required() else None,
		})
	waiting = captures([fn.Count("*")], [i.space == space, i.is_archived == 0, i.status.isin(["New", "Processing"]), *([guard] if guard is not None else [])]).run()[0][0]
	from lifeos.tasks import handoff

	looks = handoff.looks_done(space) if not permissions.is_agent() else []  # a reply that seems to answer a waiting task: Confirm or Not yet (issue 130)
	total += len(looks)
	out.update({"looks_done": looks, "agent_requests": agent_page.requests(space) if not permissions.is_agent() else [], "lessons": lessons.proposed(space) if not permissions.is_agent() else [],
		"contradictions": wiki_check.open_findings(space) if not permissions.is_agent() else [], "total": total, "waiting": waiting, "rows": rows, "minutes": minutes(len(rows)), "unfiled": _failed(space), "max_rows": limit,
		"new_rules": rules.recent(space, days=1) if not permissions.is_agent() else []})
	return out


def minutes(n):
	return max(1, math.ceil(n * SECONDS_EACH / 60 - 0.01)) if n else 0


def _payload(r):
	return frappe.parse_json(r.payload) if r.payload else {}


def _failed(space):
	"""Captures the agent could not process: not placed, and never lost. Retry sends them back."""
	i = frappe.qb.DocType("Life Inbox Item")
	guard = sees(space, i)
	where = [i.space == space, i.is_archived == 0, i.status == "Failed", *([guard] if guard is not None else [])]
	fields = [i.name.as_("item"), i.title, i.source_type.as_("source"), i.error.as_("reason"), i.received_on]
	return captures(fields, where).orderby(i.received_on).limit(20).run(as_dict=True)


# Brain > Activity (issue 18): the feed of what came in and what the Brain did with it.
OUTCOMES = ("filed", "waiting", "dropped", "failed")
ASSISTANT = "assistant"  # the filter that shows only what an agent did (issue 125)


def outcome_term(i):
	"""What the Brain did with a capture, as a select term."""
	accepted = proposals_of(i, lambda q: q.status == "Accepted", lambda q: fn.IfNull(q.filed_by, "") == "")
	rejected = proposals_of(i, lambda q: q.status == "Rejected")
	return (Case().when(i.status == "Failed", "failed").when(i.status.isin(["New", "Processing"]), "working").when(i.status == "To Review", "waiting")
		.when(accepted > 0, "decided").when(rejected > 0, "dropped").else_("filed"))


MADE_EACH = 4
SOURCE_TYPES = ("Upload", "Journal Photo", "Voice Note", "Email", "Email Digest", "Chat", "Message", "Web", "Phone")


def _activity_where(space, days, source, area):
	i = frappe.qb.DocType("Life Inbox Item")
	where = [i.space == space, i.is_archived == 0, i.received_on >= add_to_date(now_datetime(), days=-days)]
	guard = sees(space, i)
	if guard is not None:
		where.append(guard)
	if source:
		where.append(i.source_type == source)
	if area:
		where.append(area_criterion(space, area, i))
	return where


@frappe.whitelist(methods=["GET"])
def activity(space: str | None = None, days: int = 14, source: str | None = None, area: str | None = None, outcome: str | None = None,
		start: int = 0, page_length: int = 50):
	"""The Activity feed: captures of the last `days` days, newest first, each with its source, what it was, what the Brain did
	(`outcome`: filed on its own, decided by you, waiting, dropped, failed or working), the area and goal, the error of a failed one,
	and the records made from it. `counts` has every outcome under the other filters; `sources` the source types present;
	`plate` is this week's Outbox piles and flow line, the numbers the Outbox shows. `assistant` is what agents changed for you in the same days
	(who, what, who asked, Undo where there is one); the outcome `assistant` shows only those."""
	permissions.require_login()
	space = permissions.resolve_space(space)
	area = lens_area(area)
	days = max(1, min(int(days or 14), 120))
	start, page_length = page(start, page_length)
	i = frappe.qb.DocType("Life Inbox Item")
	where = _activity_where(space, days, source if source in SOURCE_TYPES else None, area)
	counts = dict(frappe.qb.from_(captures([outcome_term(i).as_("o")], where).as_("t")).select(Field("o"), fn.Count("*")).groupby(Field("o")).run())  # system: wrapped query, permissions applied inside
	total = sum(counts.values())
	counts = {k: int(counts.get(k, 0)) for k in (*OUTCOMES, "decided", "working")}
	assistant = agent_page.feed(space, days) if not permissions.is_agent() and not source and not area else []  # an agent's act has no source or area
	counts[ASSISTANT] = len(assistant)
	fields = [i.name.as_("item"), i.title, i.source_type.as_("source"), i.media_kind, i.received_on, i.status, i.error, i.intent, i.area, i.goal,
		i.is_sensitive, i.processed_by, outcome_term(i).as_("outcome")]
	inner = captures(fields, where).as_("t")
	rows = frappe.qb.from_(inner).select(inner.star)
	if outcome in OUTCOMES:
		rows = rows.where(Field("outcome") == outcome)
	rows = rows.orderby(Field("received_on"), order=Order.desc).orderby(Field("item"), order=Order.desc).limit(page_length).offset(start).run(as_dict=True) if outcome != ASSISTANT else []  # system: wrapped query, permissions applied inside
	areas = names_map("Life Area", [r.area for r in rows if r.area], "area_name")
	goals = names_map("Life Goal", [r.goal for r in rows if r.goal], "title")
	made = _made(space, [r.item for r in rows])
	# "Filed by process-capture v1": the capture's skill, when it accepted something on its own
	own = set(frappe.get_list("Life Proposal", filters={"inbox_item": ("in", [r.item for r in rows] or [""]), "filed_by": ("is", "set")}, pluck="inbox_item"))
	for r in rows:
		r.update(received_on=str(r.received_on)[:19], area_name=areas.get(r.area), goal_title=goals.get(r.goal), made=made.get(r.item, []),
			filed_by=r.processed_by if r.item in own or (r.processed_by or "").startswith("Rule:") else None)
		r.pop("processed_by", None)
	sources = captures([i.source_type], _activity_where(space, days, None, area)).distinct().orderby(i.source_type).run(pluck=True)
	shown = counts[outcome] if outcome in (*OUTCOMES, ASSISTANT) else total
	return {"rows": rows, "total": shown, "all": total, "counts": counts, "assistant": assistant if not outcome or outcome == ASSISTANT else [], "sources": sources, "days": days, "plate": plate(space, area),
		"new_rules": rules.recent(space) if not permissions.is_agent() else []}


def _made(space, items):
	"""The records made from each capture: those of its accepted proposals, at most MADE_EACH, each readable by the caller."""
	from lifeos.library import item_page

	if not items:
		return {}
	out = {}
	for p in frappe.get_list("Life Proposal", filters={"inbox_item": ("in", items), "status": "Accepted", "created_name": ("is", "set")},
			fields=["inbox_item", "kind", "preview", "created_doctype", "created_name"], order_by="decided_on asc, creation asc"):
		bucket = out.setdefault(p.inbox_item, [])
		if len(bucket) >= MADE_EACH or any(e["name"] == p.created_name for e in bucket) or not item_page._readable(p.created_doctype, p.created_name, space):
			continue
		bucket.append(item_page._entry(item_page.KIND_OF.get(p.created_doctype, p.kind), p.created_doctype, p.created_name, title=p.preview))
	# a waiting task the Brain closed because this capture said it was done (issue 118)
	for t in frappe.get_list("Life Task", filters={"closed_by_item": ("in", items)}, fields=["name", "closed_by_item"], order_by="completed_on desc", limit=len(items) * MADE_EACH):
		bucket = out.setdefault(t.closed_by_item, [])
		if len(bucket) < MADE_EACH and item_page._readable("Life Task", t.name, space):
			bucket.append({**item_page._entry("Closed", "Life Task", t.name), "kind": "Closed by itself"})
	return out


def plate(space, area=None):
	"""This week's Outbox piles (Done, Delegated, Parked, Discarded) with what came in, as the Outbox counts them. People only."""
	from lifeos.brain import outbox
	from lifeos.api import outbox as outbox_api

	if permissions.is_agent():
		return None
	start, end, _p = outbox_api.bounds("week")
	piles = outbox_api.out_counts(space, area, start, end)
	return {"piles": piles, "in": outbox_api.in_count(space, area, start, end), "from": str(start)[:10], "order": list(outbox.PILES)}
