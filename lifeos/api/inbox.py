"""Inbox pipeline: capture, claim, submit, fail, retry. See section 5 of the spec."""
import builtins

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from lifeos import files, links, permissions, proposals
from lifeos.proposals import goal_for_project
from lifeos.api.utils import area_filter, extra_columns, flag, names_map, page, parse, std_clause, std_filters, std_order, summarise, tab_counts, user_names
from lifeos.api.utils import order_by as sort_order

CLAIM_MINUTES = 30
LIST = list  # this module defines its own `list` method below
SOURCE_TYPES = ["Upload", "Journal Photo", "Voice Note", "Email", "Email Digest", "Chat", "Message", "Web"]


def _item_dict(item, with_files=True):
	d = {k: item.get(k) for k in ("name", "space", "title", "source_type", "received_on", "instruction", "raw_text", "transcript_md",
		"summary_md", "source_url", "status", "claimed_by", "claimed_on", "error", "area", "goal", "is_archived", "owner", "preview_image",
		"intent", "media_kind", "source_system", "external_id", "thumbnail", "is_sensitive")}
	d["received_on"] = str(d["received_on"]) if d["received_on"] else None
	d["claimed_on"] = str(d["claimed_on"]) if d["claimed_on"] else None
	if with_files:
		d["files"] = [{"file_name": f.file_name, "file_url": f.file_url, "file_size": f.file_size} for f in files.attachments("Life Inbox Item", item.name)]
	return d


INTENTS = ("Process", "Add to wiki", "Just keep")


@frappe.whitelist(methods=["POST"])
def create_item(title: str | None = None, source_type: str = "Upload", space: str | None = None, raw_text: str | None = None,
		instruction: str | None = None, source_url: str | None = None, intent: str | None = None, source_system: str | None = None,
		external_id: str | None = None, area: str | None = None, goal: str | None = None, project: str | None = None):
	"""Create an inbox item. Attach files afterwards with /api/method/upload_file (doctype, docname, is_private=1).

	intent: Process (the default), Add to wiki or Just keep. With source_system (gmail, claude, upload…) the space's connection for
	that system gives the default intent, area and goal (`project` names the goal a project became). With source_system and external_id (the original's ID in that system)
	an item that already exists is updated instead of created: its text changes, and a Done item whose content changed goes back
	to New so the agent processes the change. The answer carries `created` (true or false)."""
	from lifeos.api import connections

	space = permissions.resolve_space(space, write=True)
	if source_type not in SOURCE_TYPES:
		frappe.throw(_("source_type must be one of: {0}.").format(", ".join(SOURCE_TYPES)))
	if intent and intent not in INTENTS:
		frappe.throw(_("intent must be one of: {0}.").format(", ".join(INTENTS)))
	system = (source_system or "").strip().lower() or None
	conn = connections.connection(space, system) if system else None
	title = (title or "").strip() or f"{source_type}, {frappe.utils.format_datetime(now_datetime(), 'd MMM HH:mm')}"
	existing = frappe.db.get_value("Life Inbox Item", {"space": space, "source_system": system, "external_id": external_id.strip()}) \
		if system and (external_id or "").strip() else None
	if existing:
		item = permissions.get_doc_checked("Life Inbox Item", existing, "write")
		before = (item.title, item.raw_text or "", item.source_url or "", item.instruction or "")
		item.title, item.source_type = title[:140], source_type
		for field, value in (("raw_text", raw_text), ("source_url", source_url), ("instruction", instruction)):
			if value is not None:
				item.set(field, value)
		changed = before != (item.title, item.raw_text or "", item.source_url or "", item.instruction or "")
		if changed and item.status == "Done":
			item.status = "New"
			item.add_comment("Info", _("Updated from {0}: the content changed, so it went back to the agent.").format(system))
		elif changed:
			item.add_comment("Info", _("Updated from {0}.").format(system))
		item.save()
		connections.touch(space, system, item.title)
		return {**_item_dict(item), "created": False, "changed": changed}
	item = frappe.get_doc({"doctype": "Life Inbox Item", "space": space, "title": title[:140], "source_type": source_type,
		"raw_text": raw_text, "instruction": instruction, "source_url": source_url, "status": "New",
		"intent": intent or (conn.default_intent if conn and conn.active else None) or "Process",
		"source_system": system, "external_id": (external_id or "").strip() or None,
		"area": area or (conn.default_area if conn else None),
		"goal": goal or (project and goal_for_project(project, space)) or (conn.default_goal if conn else None)})
	if item.goal and not item.area:
		item.area = frappe.db.get_value("Life Goal", item.goal, "area")
	item.insert()
	if system:
		connections.touch(space, system, item.title)
	return {**_item_dict(item), "created": True}


def release_stale_claims():
	"""A claim older than 30 minutes goes back to New. Runs every five minutes and before each claim."""
	cutoff = add_to_date(now_datetime(), minutes=-CLAIM_MINUTES)
	stale = frappe.get_all("Life Inbox Item", filters={"status": "Processing", "claimed_on": ("<", cutoff)}, pluck="name")
	for name in stale:
		frappe.db.set_value("Life Inbox Item", name, {"status": "New", "claimed_by": None, "claimed_on": None})
	return len(stale)


@frappe.whitelist(methods=["POST"])
def claim_next(space: str | None = None):
	"""Claim the oldest New item. Returns it with its file URLs and the filing context, or nothing."""
	permissions.require_login()
	release_stale_claims()
	if space:
		spaces = [permissions.require_space(space, write=True)]
	else:
		spaces = [s for s, access in permissions.user_spaces().items() if access == "Write"]
	if not spaces:
		return None
	# a source a Vault document was made from is hidden from an agent while that Vault is closed to it
	closed = [sp for sp in spaces if permissions.vault_hidden(sp)] or [""]
	rows = frappe.db.sql(
		"select name from `tabLife Inbox Item` where status='New' and is_archived=0 and space in %s "
		"and not ((ifnull(vault_document, '') != '' or is_sensitive = 1) and space in %s) "
		"order by received_on asc, creation asc limit 1 for update skip locked", (spaces, closed))
	if not rows:
		return None
	item = frappe.get_doc("Life Inbox Item", rows[0][0])
	item.status = "Processing"
	item.claimed_by = frappe.session.user
	item.claimed_on = now_datetime()
	item.error = None
	item.save()
	out = _item_dict(item)
	out["context"] = space_context(item.space)
	# what the agent must respect: the intent, and the filing defaults of the system it came from
	from lifeos.api import connections

	out["connection"] = connections.defaults(item.space, item.source_system) if item.source_system else None
	out["rules"] = {
		"Process": "Extract text, summarise and propose records for review.",
		"Add to wiki": "Extract text, then create or edit wiki pages directly with lifeos.api.wiki (cite this item). Propose tasks or events "
			"for review as usual; do not propose notes.",
		"Just keep": "Extract text (transcript, OCR, PDF text) so it is searchable. Propose nothing.",
	}[item.intent or "Process"]
	return out


def space_context(space):
	"""What an agent needs to file proposals: the space's areas, tags, people, habits, dimensions and goals in progress (projects
	became open-ended goals in set 6)."""
	areas = frappe.get_all("Life Area", filters={"space": space, "is_archived": 0}, fields=["name", "area_name", "parent_area", "colour", "is_pinned"],
		order_by="sort_order, area_name", limit=500)
	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "title", "start_date"], as_dict=True)
	# every goal in progress, of every type, for filing a task under it; 12 Week Year goals of the active cycle carry their actions
	goals = []
	for g in frappe.db.sql("""select g.name, g.title, g.area, g.goal_type, g.cycle, g.measure_kind, g.measure, g.unit, g.start_value,
			g.target_value, g.current_value, g.current_on from `tabLife Goal` g left join `tabLife Cycle` c on c.name = g.cycle
			where g.space=%s and g.outcome='In Progress' and (ifnull(g.cycle, '') = '' or c.status in ('Active', 'Planned'))
			order by field(g.goal_type, '12 Week Year', 'Annual', 'Open'), g.sort_order, g.title""", space, as_dict=True):
		g["actions"] = frappe.get_all("Life Goal Action", filters={"parent": g.name}, fields=["name", "title", "status", "per_week"], order_by="idx") if g.cycle else []
		if g.measure_kind == "Number":  # a number goal: what a Reading proposal reports (set 7)
			g["measure"] = {"measure": g.measure, "unit": g.unit, "start": g.start_value, "target": g.target_value, "current": g.current_value if g.current_on else None}
		g.pop("unit", None), g.pop("start_value", None), g.pop("target_value", None), g.pop("current_value", None), g.pop("current_on", None)
		goals.append(g)
	return {
		"space": space,
		"areas": areas,
		"tags": frappe.get_all("Life Tag", filters={"space": space, "is_archived": 0}, fields=["name", "tag_name"], order_by="tag_name", limit=500),
		"people": frappe.get_all("Life Person", filters={"space": space}, fields=["name", "full_name", "relation"], limit=500),
		"habits": frappe.get_all("Life Habit", filters={"space": space, "is_archived": 0}, fields=["name", "title"], limit=200),
		"dimensions": frappe.get_all("Life Dimension", filters={"space": space, "is_archived": 0}, fields=["name", "dimension_name"], order_by="sort_order", limit=50),
		"cycle": ({"name": cycle.name, "title": cycle.title, "start_date": str(cycle.start_date)} if cycle else None),
		"goals": goals,
	}


def _claimed_item(item_name):
	item = permissions.get_doc_checked("Life Inbox Item", item_name, "write")
	if item.status != "Processing":
		frappe.throw(_("This item is not being processed. Claim it first."))
	if item.claimed_by != frappe.session.user and not permissions.is_admin():
		frappe.throw(_("This item is claimed by someone else."), frappe.PermissionError)
	return item


@frappe.whitelist(methods=["POST"])
def submit_result(item: str, transcript_md: str | None = None, summary_md: str | None = None, proposals: str | builtins.list | None = None):
	"""Store the transcript, summary and proposals, and set the item To Review.

	Each proposal is {kind, preview, payload, confidence}. An invalid proposal is refused with a clear error; the rest are kept.
	"""
	from lifeos import proposals as rules

	doc = _claimed_item(item)
	rows = parse(proposals, []) or []
	if not isinstance(rows, LIST):
		frappe.throw(_("proposals must be a list."))
	if rows and doc.intent == "Just keep":
		frappe.throw(_("This item is to be kept only (intent Just keep). Send its text with no proposals."))
	if doc.intent == "Add to wiki" and any(isinstance(r, dict) and r.get("kind") == "Note" for r in rows):
		frappe.throw(_("This item is for the wiki (intent Add to wiki). Write wiki pages with lifeos.api.wiki instead of proposing notes."))
	created, errors, ctx, readings_made = [], [], {}, []
	for i, row in enumerate(rows):
		try:
			if not isinstance(row, dict):
				raise rules.PayloadError(_("Each proposal must be an object."))
			kind = row.get("kind")
			payload = rules.validate(kind, row.get("payload") or {}, doc.space, ctx)
			confidence = row.get("confidence")
			confidence = 0.5 if confidence is None else float(confidence)
			if not 0 <= confidence <= 1:
				raise rules.PayloadError(_("confidence must be between 0 and 1."))
			if kind in rules.DIRECT:  # a Reading is stored at once as a Suggested reading for the weekly review (set 7)
				r = rules.store_reading(payload, doc)
				readings_made.append({"index": i, "name": r.name, "kind": kind})
				continue
			preview = (row.get("preview") or payload.get("title") or payload.get("subject") or kind)[:500]
			p = frappe.get_doc({"doctype": "Life Proposal", "space": doc.space, "inbox_item": doc.name, "kind": kind, "preview": preview,
				"payload": frappe.as_json(payload), "confidence": confidence, "status": "Pending", "sort_order": i}).insert()
			created.append({"index": i, "name": p.name, "kind": kind})
		except (rules.PayloadError, ValueError, TypeError) as e:
			errors.append({"index": i, "kind": row.get("kind") if isinstance(row, dict) else None,
				"preview": row.get("preview") if isinstance(row, dict) else None, "error": str(e)})
	doc.transcript_md = transcript_md if transcript_md is not None else doc.transcript_md
	doc.summary_md = summary_md if summary_md is not None else doc.summary_md
	doc.status = "To Review" if created or readings_made or not rows or doc.summary_md or doc.transcript_md else "Failed"
	if doc.status == "Failed":
		doc.error = _("Every proposal was invalid.")
	doc.save()
	if doc.status == "To Review" and not created:
		_finish_if_decided(doc)
	return {"item": doc.name, "status": doc.status, "created": created, "errors": errors, "readings": readings_made}


def _finish_if_decided(doc):
	"""An item with no pending proposal is Done."""
	if doc.status != "To Review":
		return doc.status
	if not frappe.db.exists("Life Proposal", {"inbox_item": doc.name, "status": "Pending"}):
		# saved, not set: the Outbox hooks record the item leaving the Inbox (set 7)
		doc.reload()
		doc.status, doc.finished_on = "Done", frappe.utils.today()
		doc.save(ignore_permissions=True)
	return doc.status


@frappe.whitelist(methods=["POST"])
def fail_item(item: str, error: str | None = None):
	"""Mark a claimed item Failed, with the reason."""
	doc = _claimed_item(item)
	doc.status = "Failed"
	doc.error = (error or _("Processing failed."))[:1000]
	doc.save()
	return {"item": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def retry(item: str):
	"""Send a Failed item back to New so an agent picks it up again. Pending proposals of the old attempt are removed."""
	doc = permissions.get_doc_checked("Life Inbox Item", item, "write")
	if permissions.is_agent():
		frappe.throw(_("Only a person can retry an item."), frappe.PermissionError)
	if doc.status not in ("Failed", "To Review", "Processing"):
		frappe.throw(_("Only a failed item can be retried."))
	for name in frappe.get_all("Life Proposal", filters={"inbox_item": doc.name, "status": "Pending"}, pluck="name"):
		frappe.delete_doc("Life Proposal", name, ignore_permissions=True, force=True)
	doc.status = "New"
	doc.error = None
	doc.save()
	return {"item": doc.name, "status": doc.status}


SORTS = {"received_on": "i.received_on", "title": "i.title", "status": "i.status", "source_type": "i.source_type"}


# the Inbox is a queue (UX fixes, set 4): its tabs are what is not finished. Done items are in Sources; `Done` and `all` stay
# here for agents and old links.
TABS = {"To Review": "i.status = 'To Review'", "Waiting": "i.status in ('New', 'Processing')", "Failed": "i.status = 'Failed'",
	"Done": "i.status = 'Done'", "all": None}


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, status: str | builtins.list | None = None, include_archived: bool | int = 0, start: int = 0,
		page_length: int = 30, source_type: str | None = None, area: str | None = None, from_date: str | None = None,
		to_date: str | None = None, sort: str | None = None, dir: str | None = None, filters: str | builtins.list | builtins.dict | None = None,
		order_by: str | None = None, summary: str | builtins.dict | None = None):
	"""Inbox items of a space, newest first, with proposal counts.
	Filters: status (one status or a JSON list), source_type, area (with its sub-areas, or "none"), from_date and to_date on the day received.
	`total` is the number of items the filters match; `pending_total` is the pending proposals of those items.
	`tabs` counts the items on each state tab of the Inbox screen (To Review, Waiting = New and Processing, Failed, Done, all)
	under the same filters, whatever status was asked for."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = ["i.space = %(space)s"], {"space": space}
	if permissions.vault_hidden(space):  # an agent never lists the source a Vault document was made from (pre-step 6 audit)
		where.append("ifnull(i.vault_document, '') = '' and i.is_sensitive = 0")
	if not flag(include_archived):
		where.append("i.is_archived = 0")
	if source_type:
		where.append("i.source_type = %(source_type)s")
		values["source_type"] = source_type
	if area:
		where.append(area_filter(space, area, "i.area", values, also_in="Life Inbox Item"))
	if from_date:
		where.append("date(i.received_on) >= %(from_date)s")
		values["from_date"] = frappe.utils.getdate(from_date)
	if to_date:
		where.append("date(i.received_on) <= %(to_date)s")
		values["to_date"] = frappe.utils.getdate(to_date)
	conds, values = std_filters("Life Inbox Item", filters, "i", values)
	# the state tabs of the Inbox screen, counted under every filter but the status itself
	tabs = tab_counts(f"from `tabLife Inbox Item` i where {' and '.join(where + conds)}", values, TABS)
	if status:
		statuses = parse(status) if str(status).startswith("[") else [status]
		where.append("i.status in %(statuses)s")
		values["statuses"] = statuses or [""]
	clause = " and ".join(where + conds)
	if summary:
		return {"summary": summarise("Life Inbox Item", f"from `tabLife Inbox Item` i where {clause}", values, "i", summary, start, page_length), "tabs": tabs}
	order = std_order("Life Inbox Item", order_by, "i", SORTS) or sort_order(sort, dir, SORTS, "i.received_on desc")
	# nosemgrep: frappe-sql-format-injection -- clause from fixed fragments and std_filters (columns checked against meta, values as parameters); order from std_order or the SORTS allowlist
	rows = frappe.db.sql(
		f"""select i.name, i.title, i.source_type, i.status, i.received_on, i.instruction, i.claimed_by, i.error, i.owner, i.area,
			i.summary_md, i.transcript_md from `tabLife Inbox Item` i where {clause} order by {order}, i.creation desc limit %(start)s, %(len)s""",
		{**values, "start": start, "len": page_length}, as_dict=True)
	# nosemgrep: frappe-sql-format-injection -- clause from fixed fragments and std_filters (columns checked against meta, values as parameters)
	total = frappe.db.sql(f"select count(*) from `tabLife Inbox Item` i where {clause}", values)[0][0]
	# nosemgrep: frappe-sql-format-injection -- clause from fixed fragments and std_filters (columns checked against meta, values as parameters)
	pending_total = frappe.db.sql(
		f"select count(*) from `tabLife Proposal` p join `tabLife Inbox Item` i on i.name = p.inbox_item where p.status = 'Pending' and {clause}", values)[0][0]
	counts = {}
	if rows:
		for item, st, n in frappe.db.sql(
			"select inbox_item, status, count(*) from `tabLife Proposal` where inbox_item in %s group by inbox_item, status", ([r.name for r in rows],)):
			counts.setdefault(item, {})[st] = n
	users = user_names([r.owner for r in rows] + [r.claimed_by for r in rows])
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	for r in rows:
		c = counts.get(r.name, {})
		r["proposals"] = sum(c.values())
		r["pending"] = c.get("Pending", 0)
		r["has_transcript"] = bool(r.pop("transcript_md"))
		r["has_summary"] = bool(r.pop("summary_md"))
		r["received_on"] = str(r.received_on) if r.received_on else None
		r["filed_by"] = users.get(r.owner)
		r["processed_by"] = users.get(r.claimed_by)
		r["area_name"] = areas.get(r.area)
	totals = dict(frappe.db.sql("select status, count(*) from `tabLife Inbox Item` where space=%s and is_archived=0 group by status", space))
	return {"items": rows, "total": total, "pending_total": pending_total, "totals": totals, "tabs": tabs, "start": start, "page_length": page_length}


@frappe.whitelist(methods=["GET"])
def get(item: str):
	"""One inbox item with its files, proposals and the choices for the filing chips."""
	doc = permissions.get_doc_checked("Life Inbox Item", item)
	out = _item_dict(doc)
	users = user_names([doc.owner, doc.claimed_by])
	out["filed_by"], out["processed_by"] = users.get(doc.owner), users.get(doc.claimed_by)
	out["area_name"] = frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None
	out["goal_title"] = frappe.db.get_value("Life Goal", doc.goal, "title") if doc.goal else None
	props = frappe.get_all("Life Proposal", filters={"inbox_item": doc.name},
		fields=["name", "kind", "preview", "payload", "confidence", "status", "created_doctype", "created_name", "decided_on"],
		order_by="sort_order asc, creation asc", limit=100)
	for p in props:
		p["payload"] = frappe.parse_json(p.payload) if p.payload else {}
		p["filed"] = proposals.SCHEMA[p.kind]["filed"]
		if p.created_doctype and p.created_name:
			p["route"] = links.route_of(p.created_doctype, p.created_name)
			p["exists"] = bool(frappe.db.exists(p.created_doctype, p.created_name))
	out["proposals"] = props
	out["context"] = space_context(doc.space)
	return out


@frappe.whitelist(methods=["POST"])
def update_transcript(item: str, transcript_md: str | None):
	"""Correct the transcript of an item, for example words marked [?]."""
	doc = permissions.get_doc_checked("Life Inbox Item", item, "write")
	doc.transcript_md = transcript_md
	doc.save()
	return {"item": doc.name}
