"""Brain > Needs you (issue 17): what the Brain asks the owner to decide, and two numbers about what it did on its own.

Nothing here decides anything: Keep, Change and Drop use review.decide and review.decide_all, as the Inbox did.
"""
import math

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from lifeos import permissions, proposals, readings, wiki_check
from lifeos.api.utils import area_filter, lens_area, names_map, page
from lifeos.skills import lessons

MAX_ROWS = 7
SECONDS_EACH = 20  # the guess at how long one decision takes: "about 2 minutes" for 7
# the kind as a person says it: a Reading is "Read later" (the mockup's word)
KIND_LABEL = {"Reading": "Read later"}


def kind_label(kind):
	return KIND_LABEL.get(kind, kind)


# an agent never reads the source a Vault document was made from, nor a capture marked sensitive: `%(open)s` is 1 for everyone else
SEES = "(%(open)s = 1 or (ifnull(i.vault_document, '') = '' and i.is_sensitive = 0))"


def _open(space):
	return 0 if permissions.vault_hidden(space) else 1


def _day_numbers(space):
	"""Captures of the last 24 hours (not archived): how many, from how many sources, and how many the Brain filed with no
	decision from the owner (Done, and no proposal the owner accepted or rejected), under how many areas and goals."""
	since = add_to_date(now_datetime(), hours=-24)
	rows = frappe.db.sql(
		"""select i.name, i.source_type, i.status, i.area, i.goal,
			(select count(*) from `tabLife Proposal` p where p.inbox_item = i.name and p.status != 'Pending' and ifnull(p.filed_by, '') = '') as decided
		from `tabLife Inbox Item` i where i.space = %(space)s and i.is_archived = 0 and i.received_on >= %(since)s and """ + SEES,
		{"space": space, "since": since, "open": _open(space)}, as_dict=True)
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
	args = {"space": space, "limit": limit, "open": _open(space)}
	total = frappe.db.sql("""select count(*) from `tabLife Proposal` p join `tabLife Inbox Item` i on i.name = p.inbox_item
		where p.status = 'Pending' and i.space = %(space)s and i.is_archived = 0 and """ + SEES, args)[0][0]
	found = frappe.db.sql(
		"""select p.name as proposal, p.kind, p.preview, p.payload, p.confidence, p.reason, p.alt_area, i.name as item, i.title as item_title,
			i.source_type, i.received_on, i.is_sensitive,
			(select count(*) from `tabLife Proposal` q where q.inbox_item = i.name and q.status = 'Pending') as item_pending
		from `tabLife Proposal` p join `tabLife Inbox Item` i on i.name = p.inbox_item
		where p.status = 'Pending' and i.space = %(space)s and i.is_archived = 0 and """ + SEES + """
		order by i.received_on asc, i.creation asc, p.sort_order asc, p.creation asc limit %(limit)s""", args, as_dict=True)
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
	waiting = frappe.db.sql("""select count(*) from `tabLife Inbox Item` i where i.space = %(space)s and i.is_archived = 0
		and i.status in ('New', 'Processing') and """ + SEES, args)[0][0]
	out.update({"lessons": lessons.proposed(space) if not permissions.is_agent() else [],
		"contradictions": wiki_check.open_findings(space) if not permissions.is_agent() else [], "total": total, "waiting": waiting, "rows": rows, "minutes": minutes(len(rows)), "unfiled": _failed(space), "max_rows": limit})
	return out


def minutes(n):
	return max(1, math.ceil(n * SECONDS_EACH / 60 - 0.01)) if n else 0


def _payload(r):
	return frappe.parse_json(r.payload) if r.payload else {}


def _failed(space):
	"""Captures the agent could not process: not placed, and never lost. Retry sends them back."""
	return frappe.db.sql(
		"""select i.name as item, i.title, i.source_type as source, i.error as reason, i.received_on from `tabLife Inbox Item` i
		where i.space = %(space)s and i.is_archived = 0 and i.status = 'Failed' and """ + SEES + " order by i.received_on asc limit 20",
		{"space": space, "open": _open(space)}, as_dict=True)


# Brain > Activity (issue 18): the feed of what came in and what the Brain did with it.
OUTCOMES = ("filed", "waiting", "dropped", "failed")
OUTCOME_SQL = """case when i.status = 'Failed' then 'failed' when i.status in ('New', 'Processing') then 'working'
	when i.status = 'To Review' then 'waiting'
	when (select count(*) from `tabLife Proposal` p where p.inbox_item = i.name and p.status = 'Accepted' and ifnull(p.filed_by, '') = '') > 0 then 'decided'
	when (select count(*) from `tabLife Proposal` p where p.inbox_item = i.name and p.status = 'Rejected') > 0 then 'dropped'
	else 'filed' end"""
MADE_EACH = 4
SOURCE_TYPES = ("Upload", "Journal Photo", "Voice Note", "Email", "Email Digest", "Chat", "Message", "Web", "Phone")


def _activity_where(space, days, source, area):
	where = "i.space = %(space)s and i.is_archived = 0 and i.received_on >= %(since)s and " + SEES
	values = {"space": space, "open": _open(space), "since": add_to_date(now_datetime(), days=-days)}
	if source:
		where += " and i.source_type = %(source)s"
		values["source"] = source
	if area:
		where += " and " + area_filter(space, area, "i.area", values)
	return where, values


@frappe.whitelist(methods=["GET"])
def activity(space: str | None = None, days: int = 14, source: str | None = None, area: str | None = None, outcome: str | None = None,
		start: int = 0, page_length: int = 50):
	"""The Activity feed: captures of the last `days` days, newest first, each with its source, what it was, what the Brain did
	(`outcome`: filed on its own, decided by you, waiting, dropped, failed or working), the area and goal, the error of a failed one,
	and the records made from it. `counts` has every outcome under the other filters; `sources` the source types present;
	`plate` is this week's Outbox piles and flow line, the numbers the Outbox shows."""
	permissions.require_login()
	space = permissions.resolve_space(space)
	area = lens_area(area)
	days = max(1, min(int(days or 14), 120))
	start, page_length = page(start, page_length)
	where, values = _activity_where(space, days, source if source in SOURCE_TYPES else None, area)
	# nosemgrep: frappe-sql-format-injection -- WHERE is constant SQL plus area_filter; values are parameters
	counts = dict(frappe.db.sql(f"select o, count(*) from (select {OUTCOME_SQL} as o from `tabLife Inbox Item` i where {where}) t group by o", values))
	total = sum(counts.values())
	counts = {k: int(counts.get(k, 0)) for k in (*OUTCOMES, "decided", "working")}
	if outcome in OUTCOMES:
		values["outcome"] = outcome
	# nosemgrep: frappe-sql-format-injection -- WHERE is constant SQL plus area_filter; values are parameters
	rows = frappe.db.sql(f"""select * from (select i.name as item, i.title, i.source_type as source, i.media_kind, i.received_on, i.status, i.error,
			i.intent, i.area, i.goal, i.is_sensitive, i.processed_by, {OUTCOME_SQL} as outcome from `tabLife Inbox Item` i where {where}) t
		{'where outcome = %(outcome)s' if outcome in OUTCOMES else ''} order by received_on desc, item desc limit %(s)s, %(n)s""",
		{**values, "s": start, "n": page_length}, as_dict=True)
	areas = names_map("Life Area", [r.area for r in rows if r.area], "area_name")
	goals = names_map("Life Goal", [r.goal for r in rows if r.goal], "title")
	made = _made(space, [r.item for r in rows])
	# "Filed by process-capture v1": the capture's skill, when it accepted something on its own
	own = set(frappe.get_list("Life Proposal", filters={"inbox_item": ("in", [r.item for r in rows] or [""]), "filed_by": ("is", "set")}, pluck="inbox_item"))
	for r in rows:
		r.update(received_on=str(r.received_on)[:19], area_name=areas.get(r.area), goal_title=goals.get(r.goal), made=made.get(r.item, []),
			filed_by=r.processed_by if r.item in own else None)
		r.pop("processed_by", None)
	every, every_values = _activity_where(space, days, None, area)
	# nosemgrep: frappe-sql-format-injection -- WHERE is constant SQL plus area_filter; values are parameters
	sources = [x[0] for x in frappe.db.sql(f"select distinct i.source_type from `tabLife Inbox Item` i where {every} order by 1", every_values)]
	shown = counts[outcome] if outcome in OUTCOMES else total
	return {"rows": rows, "total": shown, "all": total, "counts": counts, "sources": sources, "days": days, "plate": plate(space, area)}


def _made(space, items):
	"""The records made from each capture: those of its accepted proposals, at most MADE_EACH, each readable by the caller."""
	from lifeos import item_page

	if not items:
		return {}
	out = {}
	for p in frappe.get_list("Life Proposal", filters={"inbox_item": ("in", items), "status": "Accepted", "created_name": ("is", "set")},
			fields=["inbox_item", "kind", "preview", "created_doctype", "created_name"], order_by="decided_on asc, creation asc"):
		bucket = out.setdefault(p.inbox_item, [])
		if len(bucket) >= MADE_EACH or any(e["name"] == p.created_name for e in bucket) or not item_page._readable(p.created_doctype, p.created_name, space):
			continue
		bucket.append(item_page._entry(item_page.KIND_OF.get(p.created_doctype, p.kind), p.created_doctype, p.created_name, title=p.preview))
	return out


def plate(space, area=None):
	"""This week's Outbox piles (Done, Delegated, Parked, Discarded) with what came in, as the Outbox counts them. People only."""
	from lifeos import outbox
	from lifeos.api import outbox as outbox_api

	if permissions.is_agent():
		return None
	start, end, _p = outbox_api.bounds("week")
	piles = outbox_api.out_counts(space, area, start, end)
	return {"piles": piles, "in": outbox_api.in_count(space, area, start, end), "from": str(start)[:10], "order": list(outbox.PILES)}
