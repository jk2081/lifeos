"""Inbox items left too long (set 7). A rule in Settings > Your life > Reset rules says what happens to items To Review (and
New items no agent has claimed) older than N days: Suggest a decision for each (the default, after 7 days), Park them as ideas
in Someday, or Discard them to the trash (after 14 days). A nightly job applies it. Items an agent is processing, and Failed
items, are never acted on. Parking and discarding record their Outbox exits with `auto_rule`, which Today's line and its Undo
(for seven days) read."""
import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime, today

from lifeos import permissions

MODES = ("Suggest", "Park", "Discard")
DEFAULT_DAYS = {"Suggest": 7, "Park": 14, "Discard": 14}
DECISIONS = ("Accept", "Park", "Discard")
RULE = "old_inbox"
UNDO_DAYS = 7
MAX_PER_RUN = 200


def rule():
	s = frappe.get_cached_doc("Life Settings")
	mode = s.get("old_inbox_mode") if s.get("old_inbox_mode") in MODES else "Suggest"
	return {"mode": mode, "days": max(cint(s.get("old_inbox_days")) or DEFAULT_DAYS[mode], 1)}


def candidates(space, days, limit=MAX_PER_RUN):
	"""Items To Review, and New items no agent has claimed, received more than `days` days ago."""
	cutoff = add_days(getdate(today()), -int(days))
	return frappe.db.sql("""select name, title, status, area, summary_md, raw_text, suggested_decision, suggested_reason, suggested_by, suggested_on, received_on
		from `tabLife Inbox Item`
		where space = %(space)s and is_archived = 0 and date(ifnull(received_on, creation)) < %(cutoff)s
		and (status = 'To Review' or (status = 'New' and ifnull(claimed_by, '') = ''))
		order by ifnull(received_on, creation) asc limit %(limit)s""", {"space": space, "cutoff": cutoff, "limit": limit}, as_dict=True)


def _pending(items):
	rows = frappe.get_all("Life Proposal", filters={"inbox_item": ("in", [i.name for i in items] or ["-"]), "status": "Pending"},
		fields=["inbox_item", "kind", "preview"], limit=5000)
	out = {}
	for r in rows:
		out.setdefault(r.inbox_item, []).append(r)
	return out


DECIDED = {"keep": "Accept", "park": "Park", "drop": "Discard"}  # tidy-backlog's words, in the words of the Inbox's decisions


def suggest(space, items):
	"""{item: (decision, reason)} from the tidy-backlog skill, and the label to show: only for the items it could decide. With no key, or
	when it says nothing, {} and None: the items wait in Needs you."""
	from lifeos.skills import call

	pending = _pending(items)
	ids = {f"I{n + 1}": i for n, i in enumerate(items[:60])}
	if not ids:
		return {}, None
	got = call.ask("tidy-backlog", {"request": "old Inbox items", "items": [{"item": k, "kind": "Inbox", "title": i.title,
		"age_days": (getdate(today()) - getdate(i.received_on)).days if i.received_on else None, "summary": (i.summary_md or i.raw_text or "")[:600],
		"proposals": [p.kind for p in pending.get(i.name, [])], "previews": [p.preview for p in pending.get(i.name, [])][:8]} for k, i in ids.items()]},
		space=space)
	out = {}
	for d in got.get("decisions") or []:
		if (i := ids.get(d.get("item"))) and d.get("decision") in DECIDED:
			out[i.name] = (DECIDED[d["decision"]], (d.get("reason") or "").strip()[:300])
	return out, got.label if got else None


# ---- the nightly job ----

def run_nightly():
	"""Daily: each space, as its owner. A space that fails is undone alone."""
	for s in frappe.get_all("Life Space", fields=["name", "owner_user", "ask_enabled"]):
		if not s.owner_user:
			continue
		frappe.db.savepoint("lifeos_old_inbox")
		try:
			run_for_space(s.name, ai=bool(s.ask_enabled))
		except Exception:
			frappe.db.rollback(save_point="lifeos_old_inbox")
			frappe.log_error(title=f"Life OS old Inbox items for {s.name}")


def run_for_space(space, ai=True):
	"""Apply the rule to one space. Returns what it did: {"mode", "suggested" | "parked" | "discarded": n}."""
	r = rule()
	items = candidates(space, r["days"])
	if r["mode"] == "Suggest":
		fresh = [i for i in items if not i.suggested_on]
		got, label = suggest(space, fresh) if ai else ({}, None)
		for i in fresh if label else []:  # asked once: an item the skill left out waits in Needs you, and is not asked about again
			decision, reason = got.get(i.name, (None, None))
			frappe.db.set_value("Life Inbox Item", i.name, {"suggested_decision": decision, "suggested_reason": reason, "suggested_by": label if decision else None,
				"suggested_on": today()}, update_modified=False)
		return {"mode": "Suggest", "suggested": len(got)}
	# the job runs as the scheduler (Administrator), which may act in every space; exits are marked with the rule
	done = 0
	for i in items:
		doc = frappe.get_doc("Life Inbox Item", i.name)
		park(doc, auto=True) if r["mode"] == "Park" else discard(doc, auto=True)
		done += 1
	return {"mode": r["mode"], "parked" if r["mode"] == "Park" else "discarded": done}


# ---- the three decisions ----

def accept(doc):
	"""Accept the proposals as they are. An item with none is kept as it is and leaves the Inbox."""
	from lifeos.api import review

	if frappe.db.exists("Life Proposal", {"inbox_item": doc.name, "status": "Pending"}):
		res = review.decide_all(doc.name, "accept")
		return {"op": "unaccept_all", "item": doc.name, "proposals": frappe.get_all("Life Proposal",
			filters={"inbox_item": doc.name, "status": "Accepted"}, pluck="name"), "errors": len(res.get("errors") or [])}
	before = doc.status
	doc.status, doc.finished_on = "Done", today()
	doc.save()
	return {"op": "reopen", "item": doc.name, "status": before}


def park(doc, auto=False):
	"""Park as an idea in Someday: an idea with the item's title and summary, citing it; pending proposals are rejected and the
	item leaves the Inbox (the Outbox records it as Parked)."""
	from lifeos.api import review, someday

	before = doc.status
	idea = frappe.get_doc({"doctype": "Life Idea", "space": doc.space, "title": (doc.title or "Parked capture")[:140], "area": doc.area or None,
		"body_md": doc.summary_md or (doc.raw_text or "")[:4000] or None, "source_doctype": "Life Inbox Item", "source_name": doc.name, "status": "Someday",
		"someday_on": today(), "someday_review_on": someday.review_date(), "someday_note": "Parked from the Inbox after it waited too long." if auto else None})
	idea.insert()
	pending = frappe.get_all("Life Proposal", filters={"inbox_item": doc.name, "status": "Pending"}, pluck="name")
	doc.flags.auto_rule = RULE if auto else None
	if pending and doc.status == "To Review":
		for p in pending:
			prop = frappe.get_doc("Life Proposal", p)
			prop.flags.auto_rule = doc.flags.auto_rule
			review._decide(prop, "reject", None)
		doc.reload()
		doc.flags.auto_rule = RULE if auto else None
	doc.status, doc.finished_on = "Done", today()
	doc.save()
	return {"op": "unpark", "item": doc.name, "idea": idea.name, "status": before, "proposals": pending}


def discard(doc, auto=False):
	"""Move the item to the trash (restorable for 30 days); the Outbox records it as Discarded."""
	from lifeos import trash

	doc.flags.auto_rule = RULE if auto else None
	permissions.get_doc_checked("Life Inbox Item", doc.name, "delete")
	frappe.local.lifeos_auto_rule = doc.flags.auto_rule
	try:
		trash.delete("Life Inbox Item", doc.name)
	finally:
		frappe.local.lifeos_auto_rule = None
	return {"op": "restore", "item": doc.name}


def apply(items):
	"""Confirm decisions: a list of {item, decision}. Returns the Undo log and how many were done."""
	log, done = [], 0
	for it in items:
		name, decision = it.get("item"), it.get("decision")
		if not isinstance(name, str) or decision not in DECISIONS:
			continue
		doc = permissions.get_doc_checked("Life Inbox Item", name, "write")
		if doc.status not in ("To Review", "New") or (doc.status == "New" and doc.claimed_by):
			continue
		log.append({"Accept": accept, "Park": park, "Discard": discard}[decision](doc))
		done += 1
	return {"done": done, "undo": log}


def undo(log):
	"""Put back what `apply` or the nightly job did, newest first."""
	from lifeos import trash
	from lifeos.api import reset

	for op in reversed(log or []):
		kind, item = op.get("op"), op.get("item")
		if not isinstance(item, str):
			continue
		if kind == "restore":
			dd = frappe.db.get_value("Deleted Document", {"deleted_doctype": "Life Inbox Item", "deleted_name": item, "restored": 0}, "name",
				order_by="creation desc")
			if dd:
				trash.restore(dd)
		elif kind == "unpark":
			idea = op.get("idea")
			if isinstance(idea, str) and frappe.db.exists("Life Idea", idea):
				permissions.get_doc_checked("Life Idea", idea, "delete")
				frappe.local.lifeos_no_exit = True  # the idea was only the item's parking place: no Discarded exit for it
				try:
					frappe.delete_doc("Life Idea", idea, ignore_permissions=True, delete_permanently=True)
				finally:
					frappe.local.lifeos_no_exit = False
			doc = _reopen(item, op.get("status") or "To Review")
			# only the item's own rejected proposals go back to Pending (the item's write access is checked in _reopen)
			for p in op.get("proposals") or []:
				if isinstance(p, str) and frappe.db.get_value("Life Proposal", p, ["inbox_item", "status"]) == (doc.name, "Rejected"):
					frappe.db.set_value("Life Proposal", p, {"status": "Pending", "decided_by": None, "decided_on": None})
			if doc.status == "New" and frappe.db.exists("Life Proposal", {"inbox_item": doc.name, "status": "Pending"}):
				doc.status = "To Review"
				doc.save()
		elif kind == "reopen":
			_reopen(item, op.get("status") or "To Review")
		elif kind == "unaccept_all":
			for p in op.get("proposals") or []:
				if isinstance(p, str):
					reset._unaccept(p)


def _reopen(item, status):
	doc = permissions.get_doc_checked("Life Inbox Item", item, "write")
	doc.status, doc.finished_on = status if status in ("To Review", "New") else "To Review", None
	doc.save()  # saved: the Outbox reverses the item's exit
	return doc


def recent_auto(space, area=None):
	"""What the rule parked or discarded on its own in the last seven days and is not undone, for Today's line."""
	from lifeos.api.utils import area_filter

	values = {"space": space, "since": add_days(now_datetime(), -UNDO_DAYS), "rule": RULE}
	where = "e.space = %(space)s and e.auto_rule = %(rule)s and e.reversed = 0 and e.exited_on >= %(since)s"
	if area:
		where += " and " + area_filter(space, area, "e.area", values)
	# nosemgrep: frappe-sql-format-injection -- WHERE is constant SQL plus area_filter's fixed fragment; values are parameters
	rows = frappe.db.sql(f"select e.record_name, e.pile, e.exited_on from `tabLife Exit` e where {where} order by e.exited_on desc", values, as_dict=True)
	if not rows:
		return None
	parked = [r.record_name for r in rows if r.pile == "Parked"]
	discarded = [r.record_name for r in rows if r.pile == "Discarded"]
	return {"parked": len(parked), "discarded": len(discarded), "days": rule()["days"], "items": [r.record_name for r in rows],
		"undo_until": str(add_days(getdate(rows[-1].exited_on), UNDO_DAYS))}


def undo_auto(space):
	"""Today's Undo: bring back everything the rule parked or discarded on its own in the last seven days."""
	got = recent_auto(space)
	if not got:
		return {"restored": 0}
	log = []
	for name in got["items"]:
		if frappe.db.exists("Life Inbox Item", name):
			idea = frappe.db.get_value("Life Idea", {"source_doctype": "Life Inbox Item", "source_name": name, "status": "Someday"})
			props = frappe.get_all("Life Proposal", filters={"inbox_item": name, "status": "Rejected"}, pluck="name")
			log.append({"op": "unpark", "item": name, "idea": idea, "status": "To Review" if props else "New", "proposals": props})
		else:
			log.append({"op": "restore", "item": name})
	undo(log)
	return {"restored": len(log)}
