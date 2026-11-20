"""Brain > Needs you (issue 17): what the Brain asks the owner to decide, and two numbers about what it did on its own.

Nothing here decides anything: Keep, Change and Drop use review.decide and review.decide_all, as the Inbox did.
"""
import math

import frappe
from frappe.utils import add_to_date, now_datetime

from lifeos import permissions, proposals
from lifeos.api.utils import names_map

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
			(select count(*) from `tabLife Proposal` p where p.inbox_item = i.name and p.status != 'Pending') as decided
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
		})
	waiting = frappe.db.sql("""select count(*) from `tabLife Inbox Item` i where i.space = %(space)s and i.is_archived = 0
		and i.status in ('New', 'Processing') and """ + SEES, args)[0][0]
	out.update({"total": total, "waiting": waiting, "rows": rows, "minutes": minutes(len(rows)), "unfiled": _failed(space), "max_rows": limit})
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
