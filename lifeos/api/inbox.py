"""Inbox pipeline: capture, claim, submit, fail, retry. See section 5 of the spec."""
import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from lifeos import files, links, permissions, proposals
from lifeos.api.utils import area_filter, extra_columns, flag, names_map, page, parse, std_clause, std_filters, std_order, summarise, user_names
from lifeos.api.utils import order_by as sort_order

CLAIM_MINUTES = 30
LIST = list  # this module defines its own `list` method below
SOURCE_TYPES = ["Upload", "Journal Photo", "Voice Note", "Email", "Chat", "Message", "Web"]


def _item_dict(item, with_files=True):
	d = {k: item.get(k) for k in ("name", "space", "title", "source_type", "received_on", "instruction", "raw_text", "transcript_md",
		"summary_md", "source_url", "status", "claimed_by", "claimed_on", "error", "area", "project", "is_archived", "owner", "preview_image")}
	d["received_on"] = str(d["received_on"]) if d["received_on"] else None
	d["claimed_on"] = str(d["claimed_on"]) if d["claimed_on"] else None
	if with_files:
		d["files"] = [{"file_name": f.file_name, "file_url": f.file_url, "file_size": f.file_size} for f in files.attachments("Life Inbox Item", item.name)]
	return d


@frappe.whitelist(methods=["POST"])
def create_item(title=None, source_type="Upload", space=None, raw_text=None, instruction=None, source_url=None):
	"""Create an inbox item. Attach files afterwards with /api/method/upload_file (doctype, docname, is_private=1)."""
	space = permissions.resolve_space(space, write=True)
	if source_type not in SOURCE_TYPES:
		frappe.throw(_("source_type must be one of: {0}.").format(", ".join(SOURCE_TYPES)))
	title = (title or "").strip() or f"{source_type}, {frappe.utils.format_datetime(now_datetime(), 'd MMM HH:mm')}"
	item = frappe.get_doc({"doctype": "Life Inbox Item", "space": space, "title": title[:140], "source_type": source_type,
		"raw_text": raw_text, "instruction": instruction, "source_url": source_url, "status": "New"}).insert()
	return _item_dict(item)


def release_stale_claims():
	"""A claim older than 30 minutes goes back to New. Runs every five minutes and before each claim."""
	cutoff = add_to_date(now_datetime(), minutes=-CLAIM_MINUTES)
	stale = frappe.get_all("Life Inbox Item", filters={"status": "Processing", "claimed_on": ("<", cutoff)}, pluck="name")
	for name in stale:
		frappe.db.set_value("Life Inbox Item", name, {"status": "New", "claimed_by": None, "claimed_on": None})
	return len(stale)


@frappe.whitelist(methods=["POST"])
def claim_next(space=None):
	"""Claim the oldest New item. Returns it with its file URLs and the filing context, or nothing."""
	permissions.require_login()
	release_stale_claims()
	if space:
		spaces = [permissions.require_space(space, write=True)]
	else:
		spaces = [s for s, access in permissions.user_spaces().items() if access == "Write"]
	if not spaces:
		return None
	rows = frappe.db.sql(
		"select name from `tabLife Inbox Item` where status='New' and is_archived=0 and space in %s "
		"order by received_on asc, creation asc limit 1 for update skip locked", (spaces,))
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
	return out


def space_context(space):
	"""What an agent needs to file proposals: the space's areas, projects, tags, people, habits, dimensions and active goals."""
	areas = frappe.get_all("Life Area", filters={"space": space, "is_archived": 0}, fields=["name", "area_name", "parent_area"], order_by="sort_order, area_name", limit=500)
	cycle = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["name", "title", "start_date"], as_dict=True)
	goals = []
	if cycle:
		for g in frappe.get_all("Life Goal", filters={"cycle": cycle.name}, fields=["name", "title", "area"], order_by="sort_order"):
			g["actions"] = frappe.get_all("Life Goal Action", filters={"parent": g.name}, fields=["name", "title", "status", "per_week"], order_by="idx")
			goals.append(g)
	return {
		"space": space,
		"areas": areas,
		"projects": frappe.get_all("Life Project", filters={"space": space, "is_archived": 0, "status": ("in", ["Active", "On Hold"])}, fields=["name", "title", "area"], limit=500),
		"tags": frappe.get_all("Life Tag", filters={"space": space}, fields=["name", "tag_name"], order_by="tag_name", limit=500),
		"people": frappe.get_all("Life Person", filters={"space": space}, fields=["name", "full_name", "relation"], limit=500),
		"habits": frappe.get_all("Life Habit", filters={"space": space}, fields=["name", "title"], limit=200),
		"dimensions": frappe.get_all("Life Dimension", filters={"space": space}, fields=["name", "dimension_name"], order_by="sort_order", limit=50),
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
def submit_result(item, transcript_md=None, summary_md=None, proposals=None):
	"""Store the transcript, summary and proposals, and set the item To Review.

	Each proposal is {kind, preview, payload, confidence}. An invalid proposal is refused with a clear error; the rest are kept.
	"""
	from lifeos import proposals as rules

	doc = _claimed_item(item)
	rows = parse(proposals, []) or []
	if not isinstance(rows, LIST):
		frappe.throw(_("proposals must be a list."))
	created, errors, ctx = [], [], {}
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
			preview = (row.get("preview") or payload.get("title") or payload.get("subject") or kind)[:500]
			p = frappe.get_doc({"doctype": "Life Proposal", "space": doc.space, "inbox_item": doc.name, "kind": kind, "preview": preview,
				"payload": frappe.as_json(payload), "confidence": confidence, "status": "Pending", "sort_order": i}).insert()
			created.append({"index": i, "name": p.name, "kind": kind})
		except (rules.PayloadError, ValueError, TypeError) as e:
			errors.append({"index": i, "kind": row.get("kind") if isinstance(row, dict) else None,
				"preview": row.get("preview") if isinstance(row, dict) else None, "error": str(e)})
	doc.transcript_md = transcript_md if transcript_md is not None else doc.transcript_md
	doc.summary_md = summary_md if summary_md is not None else doc.summary_md
	doc.status = "To Review" if created or not rows or doc.summary_md or doc.transcript_md else "Failed"
	if doc.status == "Failed":
		doc.error = _("Every proposal was invalid.")
	doc.save()
	if doc.status == "To Review" and not created:
		_finish_if_decided(doc)
	return {"item": doc.name, "status": doc.status, "created": created, "errors": errors}


def _finish_if_decided(doc):
	"""An item with no pending proposal is Done."""
	if doc.status != "To Review":
		return doc.status
	if not frappe.db.exists("Life Proposal", {"inbox_item": doc.name, "status": "Pending"}):
		frappe.db.set_value("Life Inbox Item", doc.name, {"status": "Done", "finished_on": frappe.utils.today()})
		doc.reload()
		from lifeos import index
		index.update(doc)
	return doc.status


@frappe.whitelist(methods=["POST"])
def fail_item(item, error=None):
	"""Mark a claimed item Failed, with the reason."""
	doc = _claimed_item(item)
	doc.status = "Failed"
	doc.error = (error or _("Processing failed."))[:1000]
	doc.save()
	return {"item": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def retry(item):
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


@frappe.whitelist()
def list(space=None, status=None, include_archived=0, start=0, page_length=30, source_type=None, area=None,
		from_date=None, to_date=None, sort=None, dir=None, filters=None, order_by=None, summary=None):
	"""Inbox items of a space, newest first, with proposal counts.
	Filters: status (one status or a JSON list), source_type, area (with its sub-areas, or "none"), from_date and to_date on the day received.
	`total` is the number of items the filters match; `pending_total` is the pending proposals of those items."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	where, values = ["i.space = %(space)s"], {"space": space}
	if status:
		statuses = parse(status) if str(status).startswith("[") else [status]
		where.append("i.status in %(statuses)s")
		values["statuses"] = statuses or [""]
	if not flag(include_archived):
		where.append("i.is_archived = 0")
	if source_type:
		where.append("i.source_type = %(source_type)s")
		values["source_type"] = source_type
	if area:
		where.append(area_filter(space, area, "i.area", values))
	if from_date:
		where.append("date(i.received_on) >= %(from_date)s")
		values["from_date"] = frappe.utils.getdate(from_date)
	if to_date:
		where.append("date(i.received_on) <= %(to_date)s")
		values["to_date"] = frappe.utils.getdate(to_date)
	conds, values = std_filters("Life Inbox Item", filters, "i", values)
	clause = " and ".join(where + conds)
	if summary:
		return {"summary": summarise("Life Inbox Item", f"from `tabLife Inbox Item` i where {clause}", values, "i", summary, start, page_length)}
	order = std_order("Life Inbox Item", order_by, "i", SORTS) or sort_order(sort, dir, SORTS, "i.received_on desc")
	rows = frappe.db.sql(
		f"""select i.name, i.title, i.source_type, i.status, i.received_on, i.instruction, i.claimed_by, i.error, i.owner, i.area,
			i.summary_md, i.transcript_md from `tabLife Inbox Item` i where {clause} order by {order}, i.creation desc limit %(start)s, %(len)s""",
		{**values, "start": start, "len": page_length}, as_dict=True)
	total = frappe.db.sql(f"select count(*) from `tabLife Inbox Item` i where {clause}", values)[0][0]
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
	return {"items": rows, "total": total, "pending_total": pending_total, "totals": totals, "start": start, "page_length": page_length}


@frappe.whitelist()
def get(item):
	"""One inbox item with its files, proposals and the choices for the filing chips."""
	doc = permissions.get_doc_checked("Life Inbox Item", item)
	out = _item_dict(doc)
	users = user_names([doc.owner, doc.claimed_by])
	out["filed_by"], out["processed_by"] = users.get(doc.owner), users.get(doc.claimed_by)
	out["area_name"] = frappe.db.get_value("Life Area", doc.area, "area_name") if doc.area else None
	out["project_title"] = frappe.db.get_value("Life Project", doc.project, "title") if doc.project else None
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
def update_transcript(item, transcript_md):
	"""Correct the transcript of an item, for example words marked [?]."""
	doc = permissions.get_doc_checked("Life Inbox Item", item, "write")
	doc.transcript_md = transcript_md
	doc.save()
	return {"item": doc.name}
