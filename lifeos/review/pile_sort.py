"""Which items go in the piles, and the first sort (set 8).

Library: Inbox items waiting for review. Tasks: open tasks stuck (untouched past the stuck threshold, as Reset defines it) and
tasks waiting on someone else; items that came in during the review period were handled in Library and are left out.

Without a key, or for what the tidy-backlog skill leaves out, everything waits under Needs you, except waiting items, which are kept
(and chased when asked more than 7 days ago).
"""
import frappe
from frappe.utils import add_days, getdate, now_datetime, today

from lifeos import counts
from lifeos.api.utils import names_map
from lifeos.review.piles import CHASE_AFTER, NEEDS

MAX_ITEMS = 300
UNCLAIMED_DAYS = 2
AI_MAX = 60


def candidates(space, key, period_start):
	rows = _inbox(space) if key == "inbox" else _tasks(space, period_start)
	areas = names_map("Life Area", list({r["area"] for r in rows if r.get("area")}), "area_name")
	for r in rows:
		r["area_name"] = areas.get(r.get("area"))
	return rows


def _days(d):
	return (getdate(today()) - getdate(d)).days if d else 0


def _inbox(space):
	# waiting for review, and captures no agent has picked up for two days (as set 7's old-Inbox rule takes them)
	rows = frappe.db.sql("""select name, title, area, is_sensitive, vault_document, ifnull(received_on, creation) as received
		from `tabLife Inbox Item` where space = %(space)s and is_archived = 0 and (status = 'To Review'
		or (status = 'New' and ifnull(claimed_by, '') = '' and ifnull(received_on, creation) < %(unclaimed)s))
		order by ifnull(received_on, creation) asc limit %(limit)s""", {"space": space, "limit": MAX_ITEMS,
		"unclaimed": add_days(now_datetime(), -UNCLAIMED_DAYS)}, as_dict=True)
	return [{"ref": f"Life Inbox Item:{r.name}", "doctype": "Life Inbox Item", "name": r.name, "title": r.title or "Capture",
		"source": "Inbox", "area": r.area, "age": _days(r.received), "sensitive": bool(r.is_sensitive or r.vault_document)} for r in rows]


def _tasks(space, period_start):
	from lifeos.outbox import _owner_names

	stuck_days = counts.rules()["stuck_after_days"]
	cutoff = add_days(today(), -stuck_days)
	owner = _owner_names(space)
	cycle_goals = set(frappe.db.sql_list("""select g.name from `tabLife Goal` g join `tabLife Cycle` c on c.name = g.cycle
		where g.space = %s and c.status = 'Active' and g.outcome = 'In Progress'""", space))
	rows = frappe.db.sql("""select name, title, area, goal, status, waiting_on, ifnull(last_touched_on, date(creation)) as touched, creation
		from `tabLife Task` where space = %(space)s and is_archived = 0 and date(creation) < %(start)s
		and (status = 'Waiting' or (status in ('Open', 'Doing') and ifnull(last_touched_on, date(creation)) <= %(cutoff)s))
		order by touched asc limit %(limit)s""", {"space": space, "start": getdate(period_start), "cutoff": cutoff, "limit": MAX_ITEMS},
		as_dict=True)
	out = []
	for r in rows:
		waiting = r.status == "Waiting" and (r.waiting_on or "").strip().lower() not in owner
		if r.status == "Waiting" and not waiting and getdate(r.touched) > getdate(cutoff):
			continue  # waiting on the owner, and not stuck
		out.append({"ref": f"Life Task:{r.name}", "doctype": "Life Task", "name": r.name, "title": r.title, "area": r.area,
			"source": "Waiting" if waiting else "Stuck", "age": _days(r.touched), "waiting_on": r.waiting_on if waiting else None,
			"cycle_goal": r.goal in cycle_goals, "sensitive": False})
	return out


# ---- sorting ----

def sort(space, items, ai=False):
	"""Give each item its pile and reason, in place. The tidy-backlog skill decides what it can (keep, park or drop); what it leaves out,
	and everything with no key, goes under Needs you, except the two certain rules of counts: a waiting item is kept, and chased when it
	was asked more than a week ago. Returns the skill's label ("tidy-backlog v1") when it sorted, else None."""
	for it in items:
		pile, reason, chase = _count_rule(it)
		it.update({"pile": pile, "orig": pile, "reason": reason, "chase": chase, "by": None})
	if ai and _ask_allowed(space):
		return _tidy(space, items)
	return None


def _count_rule(it):
	"""(pile, reason, chase): waiting items by how long ago they were asked; everything else waits for the owner."""
	age = it.get("age") or 0
	if it["source"] == "Waiting":
		if age > CHASE_AFTER:
			return "keep", f"Asked {age} days ago; chase {it.get('waiting_on') or 'them'}.", True
		return "keep", f"Asked {age} days ago; keep waiting.", False
	return NEEDS, f"Untouched for {age} days." if it["doctype"] == "Life Task" else "Waiting for review.", False


def _ask_allowed(space):
	return bool(frappe.db.get_value("Life Space", space, "ask_enabled"))


PILE_OF = {"keep": "keep", "park": "park", "drop": "letgo"}


def _tidy(space, items):
	from lifeos.skills import call

	readable = frappe.db.get_value("Life Space", space, "ask_can_read_vault")
	ids = {f"I{n + 1}": it for n, it in enumerate([i for i in items if readable or not i.get("sensitive")][:AI_MAX])}
	if not ids:
		return None
	got = call.ask("tidy-backlog", {"request": "the weekly review's piles", "items": [{"item": k, "kind": it["source"], "title": it["title"],
		"age_days": it.get("age"), "waiting_on": it.get("waiting_on"), "serves_cycle_goal": bool(it.get("cycle_goal"))} for k, it in ids.items()]}, space=space)
	for d in got.get("decisions") or []:
		it = ids.get(d.get("item"))
		if it and d.get("decision") in PILE_OF:
			pile = PILE_OF[d["decision"]]
			it.update({"pile": pile, "orig": pile, "reason": (d.get("reason") or "").strip()[:200] or it["reason"], "by": got.label,
				"chase": bool(d.get("chase")) and it["source"] == "Waiting"})
	return got.label if got else None
