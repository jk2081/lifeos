"""Reset (UX fixes, set 5): clear the backlog. Suggested batches found by rules (and up to three by the AI, see
lifeos/ai/batches.py), the Inventory of counts, one-by-one decisions, and Undo for a minute. People only."""
import re
from datetime import date as Date

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, today

from lifeos import counts, permissions, trash
from lifeos.api import someday
from lifeos.api.utils import names_map, parse

OPEN = ("Open", "Doing", "Waiting")
SAMPLES = 3
MAX_ITEMS = 500
OLD_DAYS = 180


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Agents cannot use Reset."), frappe.PermissionError)


def norm(title):
	return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (title or "").lower())).strip()


def _item(doctype, name, title, extra=None):
	return {"doctype": doctype, "name": name, "title": title, **(extra or {})}


def _batch(key, title, reason, items, action, label, review=None):
	return {"key": key, "title": title, "reason": reason, "count": len(items), "items": items[:MAX_ITEMS],
		"samples": [i["title"] for i in items[:SAMPLES]], "action": action, "action_label": label.format(n=len(items)),
		"review": review, "source": "Rule"}


def rule_batches(space):
	"""The rule batches of section 6, each over the exact items it lists."""
	out = []
	tasks = frappe.db.sql("""select name, title, area, goal, creation, ifnull(last_touched_on, date(creation)) as touched
		from `tabLife Task` where space=%s and status in ('Open', 'Doing', 'Waiting') and is_archived=0 order by creation asc""", space, as_dict=True)
	# 1. exact duplicates: same normalised title, area and goal; the oldest of each group stays
	groups = {}
	for t in tasks:
		groups.setdefault((norm(t.title), t.area or "", t.goal or ""), []).append(t)
	dupes = [_item("Life Task", t.name, t.title) for g in groups.values() if len(g) > 1 and g[0].title for t in g[1:]]
	if dupes:
		out.append(_batch("duplicates", "Duplicate open tasks", "Each has the same title, area and goal as an older open task, which is kept.",
			dupes, "delete", "Delete {n}"))
	# 2. open tasks whose open-ended goal (a project before set 6) is achieved or dropped
	closed = set(frappe.get_all("Life Goal", filters={"space": space, "goal_type": "Open", "outcome": ["not in", ["In Progress", "Carried"]]}, pluck="name"))
	orphans = [_item("Life Task", t.name, t.title) for t in tasks if t.goal in closed]
	if orphans:
		out.append(_batch("closed_project", "Open tasks of finished goals", "Their open-ended goal is achieved or dropped, but they are still open.",
			orphans, "drop", "Drop {n}"))
	# 3. untouched for more than 180 days, by area
	cutoff = getdate(add_days(today(), -OLD_DAYS))
	taken = {i["name"] for i in dupes + orphans}
	by_area = {}
	for t in tasks:
		if t.name not in taken and getdate(t.touched) < cutoff:
			by_area.setdefault(t.area or "", []).append(t)
	areas = names_map("Life Area", list(by_area), "area_name")
	for area, rows in sorted(by_area.items(), key=lambda kv: -len(kv[1])):
		name = areas.get(area) or "Unfiled"
		out.append(_batch(f"old:{area or 'none'}", f"{name} tasks untouched for {OLD_DAYS}+ days",
			f"Nobody has changed them for more than {OLD_DAYS} days. Park them on the Someday list; they come back for review later.",
			[_item("Life Task", t.name, t.title) for t in rows], "someday", "Move {n} to Someday"))
	# 4. inbox items older than a week: accept their note proposals, leave the rest for review
	week = add_days(today(), -7)
	items = frappe.db.sql("""select i.name, i.title, (select count(*) from `tabLife Proposal` p where p.inbox_item = i.name and p.status = 'Pending' and p.kind = 'Note') as notes
		from `tabLife Inbox Item` i where i.space=%s and i.status='To Review' and i.is_archived=0 and i.received_on < %s order by i.received_on""",
		(space, week), as_dict=True)
	if items:
		out.append(_batch("old_inbox", "Inbox items older than a week", "Still waiting for your review. Their note proposals can be accepted at once; tasks and the rest stay for review.",
			[_item("Life Inbox Item", i.name, i.title, {"notes": i.notes}) for i in items], "accept_notes", "Accept notes, review the rest"))
	# 5. notes (My notes) with the same title as a wiki page
	wiki = {norm(t): n for n, t in frappe.db.sql("select name, title from `tabLife Note` where space=%s and collection='Wiki' and is_archived=0", space)}
	twins = [_item("Life Note", n, t, {"wiki": wiki[norm(t)]}) for n, t in frappe.db.sql(
		"select name, title from `tabLife Note` where space=%s and collection='My notes' and is_archived=0", space) if norm(t) in wiki]
	if twins:
		out.append(_batch("wiki_twins", "Notes that repeat wiki pages", "A wiki page has the same title. Merging adds the note's text to the page, keeps both texts in the page's history, and archives the note.",
			twins, "merge", "Merge {n}"))
	# 6. Someday items due for review
	due = someday.list(space=space, tab="due", page_length=100)
	if due["total"]:
		out.append(_batch("someday_due", "Someday items due for review", "Parked long enough to look at again: bring back, keep for longer, or purge.",
			[_item(r.doctype, r.name, f"{r.title} ({r.type.lower()}, parked {r.someday_on})") for r in due["rows"]], "review_someday", "Review {n}",
			review={"path": "/plan/someday", "query": {"tab": "due"}}))
	return out


# POST: with `ai` it calls the model, which records the call's usage and cost
@frappe.whitelist(methods=["POST"])
def get(space: str | None = None, ai: bool | int = 0):
	"""Everything the Reset screen shows: the goal bar, the batches, the inventory and the first one-by-one item."""
	_person()
	space = permissions.resolve_space(space)
	r = counts.rules()
	open_tasks = counts.open_tasks(space)
	stuck = counts.stuck_tasks(space)
	batches = rule_batches(space)
	if cint(ai):
		from lifeos.ai import batches as ai_batches

		batches += ai_batches.suggest(space, batches)
	return {"space": space, "goal": r["open_task_goal"], "open": open_tasks, "stuck": stuck, "rules": r,
		"over_limit": stuck["n"] > r["stuck_limit"], "batches": batches, "batch_items": sum(b["count"] for b in batches),
		"inventory": counts.inventory(space), "next": next_item(space)}


# ---- one by one ----

def _queue(space, skip=(), only=None):
	"""Open tasks and open-ended goals in progress, the oldest untouched first. `only` keeps to the items of one batch."""
	if only is not None:
		only = [n for n in only if n not in skip]
		if not only:
			return None, 0
	rows = frappe.db.sql("""select * from (
		select 'Life Task' as doctype, name, title, area, goal, creation, ifnull(last_touched_on, date(creation)) as touched, inbox_item, status
			from `tabLife Task` where space=%(space)s and status in ('Open', 'Doing', 'Waiting') and is_archived=0
		union all
		select 'Life Goal', name, title, area, '' as goal, creation, ifnull(last_activity_on, date(modified)), '' as inbox_item,
			if(on_hold, 'On Hold', 'Active') from `tabLife Goal` where space=%(space)s and goal_type='Open' and outcome='In Progress' and is_someday=0 and is_archived=0
		) q where name not in %(skip)s {only} order by touched asc, creation asc limit 1""".replace("{only}", "and name in %(only)s" if only else ""),
		{"space": space, "skip": list(skip) or [""], "only": only or [""]}, as_dict=True)
	if only is not None:
		return (rows[0] if rows else None), len(only)
	total = frappe.db.sql("""select (select count(*) from `tabLife Task` where space=%(space)s and status in ('Open', 'Doing', 'Waiting') and is_archived=0)
		+ (select count(*) from `tabLife Goal` where space=%(space)s and goal_type='Open' and outcome='In Progress' and is_someday=0 and is_archived=0)""",
		{"space": space})[0][0]
	return (rows[0] if rows else None), int(total) - len(skip)


@frappe.whitelist(methods=["GET"])
def next_item(space: str | None = None, skip: str | list | None = None, only: str | list | None = None):
	"""The oldest untouched open item, with its type, area, created date, days untouched and where it came from.
	`only`: names to keep to (Review one by one on a batch)."""
	space = permissions.resolve_space(space)
	only = parse(only, None)
	row, left = _queue(space, parse(skip, []) or [], only if isinstance(only, list) else None)
	if not row:
		return {"item": None, "left": 0}
	row["type"] = "Task" if row.doctype == "Life Task" else "Goal"
	row["area_name"] = frappe.db.get_value("Life Area", row.area, "area_name") if row.area else None
	row["goal_title"] = frappe.db.get_value("Life Goal", row.goal, "title") if row.goal else None
	row["days"] = date_diff(today(), row.touched)
	row["created"] = str(row.creation)[:10]
	row["touched"] = str(row.touched)
	row["source"] = _origin(row)
	row["ref"] = ("task:" if row.doctype == "Life Task" else "goal:") + row.name
	row.pop("creation", None)
	return {"item": row, "left": left}


def _origin(row):
	"""Where an item came from: its inbox item (source), or a chat or note that links to it, with a one-line excerpt."""
	def line(text):
		text = re.sub(r"[#*_>`\[\]]", "", text or "").strip()
		return (text.split("\n")[0])[:200]
	if row.get("inbox_item"):
		src = frappe.db.get_value("Life Inbox Item", row.inbox_item, ["name", "title", "summary_md", "received_on", "media_kind"], as_dict=True)
		if src:
			return {"kind": "Source", "ref": "source:" + src.name, "title": src.title, "date": str(src.received_on)[:10], "excerpt": line(src.summary_md)}
	chat = frappe.db.sql("""select c.name, c.title, c.date, c.summary_md from `tabLife Chat Open Item` o join `tabLife Chat Log` c on c.name = o.parent
		where o.task = %s limit 1""", row.name, as_dict=True)
	if chat:
		c = chat[0]
		return {"kind": "Chat", "ref": "chat:" + c.name, "title": c.title, "date": str(c.date), "excerpt": line(c.summary_md)}
	link = frappe.db.get_value("Life Link", {"to_doctype": row.doctype, "to_name": row.name, "from_doctype": ["in", ["Life Note", "Life Chat Log"]]},
		["from_doctype", "from_name"], as_dict=True)
	if link:
		doc = frappe.db.get_value(link.from_doctype, link.from_name, ["title", "modified"], as_dict=True)
		if doc:
			return {"kind": "Note" if link.from_doctype == "Life Note" else "Chat", "ref": ("note:" if link.from_doctype == "Life Note" else "chat:") + link.from_name,
				"title": doc.title, "date": str(doc.modified)[:10], "excerpt": ""}
	return None


DECISIONS = ("do", "waiting", "someday", "archive", "delete")


@frappe.whitelist(methods=["POST"])
def decide(doctype: str, name: str, decision: str, date: str | Date | None = None, waiting_on: str | None = None):
	"""One decision on one item: Do (with a date), Waiting (for whom), Someday, Archive or Delete. Returns what Undo needs."""
	_person()
	if decision not in DECISIONS:
		frappe.throw(_("decision must be one of: {0}.").format(", ".join(DECISIONS)))
	doctype = "Life Goal" if doctype == "Life Project" else doctype  # for one set: a project is the goal it became
	if doctype == "Life Goal" and frappe.db.exists("Life Project", name):
		name = frappe.db.get_value("Life Project", name, "migrated_to") or name
	if doctype not in ("Life Task", "Life Goal"):
		frappe.throw(_("Reset decides on tasks and goals."))
	doc = permissions.get_doc_checked(doctype, name, "delete" if decision == "delete" else "write")
	undo = [_snap(doc)]
	if decision == "do":
		if not date:
			frappe.throw(_("Choose a date."))
		if doctype == "Life Task":
			doc.status = "Open" if doc.status == "Waiting" else doc.status
			doc.due_date = date
		else:
			doc.on_hold, doc.target_date = 0, date
		doc.save()
	elif decision == "waiting":
		if not (waiting_on or "").strip():
			frappe.throw(_("Say who or what it is waiting on."))
		if doctype == "Life Task":
			doc.status, doc.waiting_on = "Waiting", waiting_on.strip()
		else:
			doc.on_hold = 1
			doc.notes_md = ((doc.notes_md or "") + f"\n\nWaiting on {waiting_on.strip()} ({today()})").strip()
		doc.save()
	elif decision == "someday":
		undo = [someday._snapshot(doc)]
		someday.park_doc(doc)
	elif decision == "archive":
		from lifeos import archive

		archive.set_archived(doctype, name, True, "Manual")
	elif decision == "delete":
		trash.delete(doctype, name)
		undo = [{"op": "restore_deleted", "doctype": doctype, "name": name}]
	return {"decision": decision, "undo": undo}


def _snap(doc):
	s = someday._snapshot(doc)
	s.update({"is_archived": doc.get("is_archived"), "waiting_on": doc.get("waiting_on"), "target_date": doc.get("target_date"),
		"notes_md": doc.get("notes_md") if doc.doctype == "Life Goal" else None})
	return s


# ---- batches ----

@frappe.whitelist(methods=["POST"])
def apply_batch(action: str, items: str | list, space: str | None = None):
	"""Apply a batch's action to exactly the items listed. Returns the Undo log."""
	_person()
	space = permissions.resolve_space(space, write=True)
	items = parse(items, []) or []
	if len(items) > MAX_ITEMS:
		frappe.throw(_("At most {0} items at a time.").format(MAX_ITEMS))
	undo, done = [], 0
	for it in items:
		doctype, name = it.get("doctype"), it.get("name")
		if not isinstance(name, str):  # a name sent as a dict would act as a filter
			continue
		if doctype not in ("Life Task", "Life Goal", "Life Idea", "Life Inbox Item", "Life Note"):
			continue
		if not frappe.db.exists(doctype, name) or frappe.db.get_value(doctype, name, "space") != space:
			continue
		if action == "delete":
			trash.delete(doctype, name)
			undo.append({"op": "restore_deleted", "doctype": doctype, "name": name})
		elif action == "drop":
			doc = permissions.get_doc_checked(doctype, name, "write")
			undo.append(_snap(doc))
			if doctype == "Life Goal":  # a goal has an outcome, not a status
				doc.outcome = "Dropped"
			elif doc.meta.has_field("status"):
				doc.status = "Dropped"
			else:
				continue
			doc.save()
		elif action == "someday":
			doc = permissions.get_doc_checked(doctype, name, "write")
			undo.append(someday._snapshot(doc))
			someday.park_doc(doc)
		elif action == "archive":
			from lifeos import archive

			doc = permissions.get_doc_checked(doctype, name, "write")
			undo.append(_snap(doc))
			archive.set_archived(doctype, name, True, "Manual")
		elif action == "accept_notes":
			undo += _accept_notes(name)
		elif action == "merge":
			undo += _merge(name)
		elif action == "keep":
			someday.keep(doctype, name)
		else:
			frappe.throw(_("Unknown batch action."))
		done += 1
	return {"done": done, "undo": undo}


def _accept_notes(item):
	from lifeos.api import review

	out = []
	for p in frappe.get_all("Life Proposal", filters={"inbox_item": item, "status": "Pending", "kind": "Note"}, pluck="name"):
		res = review.decide(p, "accept")
		out.append({"op": "unaccept", "proposal": p, "doctype": res.get("created_doctype"), "name": res.get("created_name"), "item": item})
	return out


def _merge(note):
	"""Add a My notes page's text to the wiki page with the same title, logged as a wiki change, and archive the note."""
	from lifeos import archive
	from lifeos.api import wiki

	doc = permissions.get_doc_checked("Life Note", note, "write")
	target = frappe.db.get_value("Life Note", {"space": doc.space, "collection": "Wiki", "is_archived": 0, "title": doc.title}) or next(
		(n for n, t in frappe.db.sql("select name, title from `tabLife Note` where space=%s and collection='Wiki' and is_archived=0", doc.space) if norm(t) == norm(doc.title)), None)
	if not target:
		return []
	page = frappe.get_doc("Life Note", target)
	before = page.content_md or ""
	merged = (before.rstrip() + f"\n\n## From my note “{doc.title}”\n\n" + (doc.content_md or "").strip()).strip() + "\n"
	res = wiki.update_page(target, content_md=merged, base_version=wiki.version_of(page), change_note=f"Merged from My notes: {doc.title}")
	archive.set_archived("Life Note", note, True, "Manual")
	change = frappe.db.get_value("Life Wiki Change", {"note": target}, "name", order_by="creation desc")
	return [{"op": "unmerge", "change": change, "note": note, "doctype": "Life Note", "name": note}] if res and not res.get("conflict") else []


@frappe.whitelist(methods=["POST"])
def undo(log: str | list):
	"""Put back what a batch or a decision changed, newest first."""
	_person()
	log = parse(log, []) or []
	for op in reversed(log):
		kind = op.get("op")
		if kind == "restore_deleted":
			dd = frappe.db.get_value("Deleted Document", {"deleted_doctype": op["doctype"], "deleted_name": op["name"], "restored": 0}, "name",
				order_by="creation desc")
			if dd:
				trash.restore(dd)
		elif kind == "unaccept":
			_unaccept(op.get("proposal"))
		elif kind == "unmerge":
			from lifeos import archive
			from lifeos.api import wiki

			if op.get("change"):
				wiki.undo(op["change"], force=1)
			archive.set_archived("Life Note", op["note"], False)
		else:
			snap = dict(op)
			someday.restore_snapshot(snap)
			doc = frappe.get_doc(snap["doctype"], snap["name"])
			changed = False
			for f in ("waiting_on", "target_date", "notes_md"):
				if f in snap and snap[f] is not None and doc.meta.has_field(f) and doc.get(f) != snap[f]:
					doc.set(f, snap[f])
					changed = True
			if changed:
				doc.save()
	return {"ok": True}


def _unaccept(proposal):
	"""Undo an accepted note proposal. The undo log comes from the browser, so only the proposal's name is taken from it:
	the item and the record made are read from the proposal, and each is checked for this user."""
	from lifeos import index

	if not isinstance(proposal, str) or not proposal:
		frappe.throw(_("Nothing to undo."))
	prop = permissions.get_doc_checked("Life Proposal", proposal, "write")
	if prop.status != "Accepted":
		return
	item = permissions.get_doc_checked("Life Inbox Item", prop.inbox_item, "write")
	if prop.created_doctype and prop.created_name and frappe.db.exists(prop.created_doctype, prop.created_name):
		permissions.get_doc_checked(prop.created_doctype, prop.created_name, "delete")
		frappe.delete_doc(prop.created_doctype, prop.created_name, ignore_permissions=True, delete_permanently=True)
	frappe.db.set_value("Life Proposal", prop.name, {"status": "Pending", "created_doctype": None, "created_name": None,
		"decided_by": None, "decided_on": None})
	frappe.db.set_value("Life Inbox Item", item.name, {"status": "To Review", "finished_on": None})
	index.update(frappe.get_doc("Life Inbox Item", item.name))


@frappe.whitelist(methods=["GET"])
def short(space: str | None = None):
	"""The weekly review's first step: the stuck count, the batches by title and count, and Someday items due for review."""
	_person()
	space = permissions.resolve_space(space)
	r = counts.rules()
	stuck = counts.stuck_tasks(space)
	return {"stuck": stuck, "over_limit": stuck["n"] > r["stuck_limit"], "rules": r, "open": counts.open_tasks(space),
		"batches": [{"key": b["key"], "title": b["title"], "count": b["count"], "action_label": b["action_label"]} for b in rule_batches(space)],
		"someday_due": counts.someday_due(space)}
