"""Chat log: one record per AI chat, and the chats report."""
import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos import permissions
from lifeos.api.utils import names_map, page, parse


@frappe.whitelist()
def report(space=None, from_date=None, to_date=None, group_by="day", start=0, page_length=100):
	"""Chat logs between two dates (default: the last seven days), grouped by day, area or project, with their open items rolled up.
	The same records come back under each group_by."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	if group_by not in ("day", "area", "project"):
		frappe.throw(_("group_by must be day, area or project."))
	end = getdate(to_date or today())
	begin = getdate(from_date) if from_date else add_days(end, -6)
	index = frappe.db.sql(
		"""select ref_name, title, record_date, area, project from `tabLife Index`
		where space=%s and kind='Chat' and is_archived=0 and record_date between %s and %s
		order by record_date desc, modified desc limit %s, %s""", (space, begin, end, start, page_length), as_dict=True)
	names = [r.ref_name for r in index]
	details, items = {}, {}
	if names:
		for r in frappe.get_all("Life Chat Log", filters={"name": ("in", names)}, fields=["name", "url", "assistant", "summary_md"]):
			details[r.name] = r
		for r in frappe.db.sql(
			"select parent, name, text, status, task from `tabLife Chat Open Item` where parenttype='Life Chat Log' and parent in %s order by parent, idx",
			(names,), as_dict=True):
			items.setdefault(r.parent, []).append({"row": r.name, "text": r.text, "status": r.status, "task": r.task})
	areas = names_map("Life Area", [r.area for r in index], "area_name")
	projects = names_map("Life Project", [r.project for r in index], "title")
	chats = []
	for r in index:
		d = details.get(r.ref_name) or {}
		chats.append({"name": r.ref_name, "title": r.title, "date": str(r.record_date), "area": r.area or None, "area_name": areas.get(r.area),
			"project": r.project or None, "project_title": projects.get(r.project), "url": d.get("url"), "assistant": d.get("assistant"),
			"summary_md": d.get("summary_md") or "", "open_items": items.get(r.ref_name, [])})

	def key(c):
		if group_by == "day":
			return c["date"], c["date"]
		if group_by == "area":
			return c["area"] or "", c["area_name"] or "No area"
		return c["project"] or "", c["project_title"] or "No project"

	groups = {}
	for c in chats:
		groups.setdefault(key(c), []).append(c)
	out = [{"key": k[0], "label": k[1], "chats": v, "open_items": sum(1 for c in v for i in c["open_items"] if i["status"] == "Open")} for k, v in groups.items()]
	if group_by != "day":
		out.sort(key=lambda g: (g["key"] == "", g["label"]))
	counts = {}
	for c in chats:
		counts[c["area_name"] or "No area"] = counts.get(c["area_name"] or "No area", 0) + 1
	open_items = [{**i, "chat": c["name"], "chat_title": c["title"], "area_name": c["area_name"]} for c in chats for i in c["open_items"] if i["status"] == "Open"]
	return {"space": space, "from_date": str(begin), "to_date": str(end), "group_by": group_by, "groups": out, "total": len(chats),
		"counts_by_area": [{"area_name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])], "open_items": open_items}


@frappe.whitelist(methods=["POST"])
def log(space=None, title=None, date=None, url=None, assistant="Claude", summary_md=None, open_items=None, area=None, project=None, tags=None, also_in=None):
	"""Record an AI chat. Agents may call this directly: a chat log is a record of what happened, not a proposal.
	open_items is a list of strings. area, project and tags take a name or a title."""
	from lifeos import proposals

	space = permissions.resolve_space(space, write=True)
	if not (title or "").strip():
		frappe.throw(_("A chat log needs a title."))
	if assistant not in ("Claude", "ChatGPT", "Other"):
		assistant = "Other"
	doc = frappe.get_doc({"doctype": "Life Chat Log", "space": space, "title": title.strip()[:140], "date": getdate(date or today()), "url": url,
		"assistant": assistant, "summary_md": summary_md,
		"open_items": [{"text": str(t)[:500], "status": "Open"} for t in parse(open_items, []) if str(t).strip()]})
	try:
		if area:
			doc.area = proposals.resolve_link("Life Area", area, space)
		if project:
			doc.project = proposals.resolve_link("Life Project", project, space)
		for a in parse(also_in, []) or []:
			doc.append("also_in", {"area": proposals.resolve_link("Life Area", a, space)})
		for t in parse(tags, []) or []:
			doc.append("tags", {"tag": proposals.resolve_link("Life Tag", t, space)})  # existing tags only
	except proposals.PayloadError as e:
		frappe.throw(str(e))
	doc.insert()
	return {"name": doc.name}


def _row(chat, row):
	doc = permissions.get_doc_checked("Life Chat Log", chat, "write")
	item = next((i for i in doc.open_items if i.name == row), None)
	if not item:
		frappe.throw(_("Open item not found."), frappe.DoesNotExistError)
	return doc, item


@frappe.whitelist(methods=["POST"])
def make_task(chat, row):
	"""Turn an open item into a task. People only: an open item becomes a task only when the owner asks."""
	if permissions.is_agent():
		frappe.throw(_("Only a person can turn an open item into a task."), frappe.PermissionError)
	doc, item = _row(chat, row)
	if item.status == "Task Created" and item.task:
		return {"task": item.task}
	task = frappe.get_doc({"doctype": "Life Task", "space": doc.space, "title": item.text[:140], "area": doc.area, "project": doc.project,
		"source_url": doc.url, "notes_md": f"From the chat [[{doc.title}#{doc.name}]].", "status": "Open"}).insert()
	item.status, item.task = "Task Created", task.name
	doc.save()
	return {"task": task.name}


@frappe.whitelist(methods=["POST"])
def close_item(chat, row, reopen=0):
	"""Close an open item without making a task, or open it again."""
	doc, item = _row(chat, row)
	item.status = "Open" if int(reopen or 0) else "Closed"
	doc.save()
	return {"row": item.name, "status": item.status}
