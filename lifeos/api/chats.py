"""Chat log: one record per AI chat, and the chats report."""
import builtins
import datetime

import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from lifeos import permissions
from lifeos.proposals import goal_for_project
from lifeos.api.utils import area_filter, extra_columns, flag, names_map, page, parse, std_clause, std_filters, std_order, summarise, tab_counts
from lifeos.api.utils import order_by as sort_order


@frappe.whitelist(methods=["GET"])
def report(space: str | None = None, from_date: str | None = None, to_date: str | None = None, group_by: str = "day", start: int | None = 0, page_length: int | None = 100):
	"""Chat logs between two dates (default: the last seven days), grouped by day, area or goal, with their open items rolled up.
	The same records come back under each group_by."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	group_by = "goal" if group_by == "project" else group_by
	if group_by not in ("day", "area", "goal"):
		frappe.throw(_("group_by must be day, area or goal."))
	end = getdate(to_date or today())
	begin = getdate(from_date) if from_date else add_days(end, -6)
	index = frappe.db.sql(
		"""select ref_name, title, record_date, area, goal from `tabLife Index`
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
	goals = names_map("Life Goal", [r.goal for r in index], "title")
	chats = []
	for r in index:
		d = details.get(r.ref_name) or {}
		chats.append({"name": r.ref_name, "title": r.title, "date": str(r.record_date), "area": r.area or None, "area_name": areas.get(r.area),
			"goal": r.goal or None, "goal_title": goals.get(r.goal), "url": d.get("url"), "assistant": d.get("assistant"),
			"summary_md": d.get("summary_md") or "", "open_items": items.get(r.ref_name, [])})

	def key(c):
		if group_by == "day":
			return c["date"], c["date"]
		if group_by == "area":
			return c["area"] or "", c["area_name"] or "No area"
		return c["goal"] or "", c["goal_title"] or "No goal"

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


OPEN_ITEM = "exists (select 1 from `tabLife Chat Open Item` oi where oi.parent = c.name and oi.parenttype = 'Life Chat Log' and oi.status = 'Open')"
SORTS = {"date": "c.date", "title": "c.title", "assistant": "c.assistant"}
GROUP_ORDER = {
	"day": "c.date desc",
	"area": "(c.area is null or c.area = ''), (select area_name from `tabLife Area` a where a.name = c.area), c.area, c.date desc",
	"goal": "(c.goal is null or c.goal = ''), (select title from `tabLife Goal` p where p.name = c.goal), c.goal, c.date desc",
}


def where_clause(space, area=None, goal=None, open_items=0, from_date=None, to_date=None, include_archived=0):
	where, values = [], {}
	if not flag(include_archived):
		where.append("c.is_archived = 0")
	if area:
		where.append(area_filter(space, area, "c.area", values, also_in="Life Chat Log"))
	if goal:
		where.append("ifnull(c.goal, '') = %(goal)s")
		values["goal"] = "" if goal == "none" else goal
	if flag(open_items):
		where.append(OPEN_ITEM)
	if from_date:
		where.append("c.date >= %(from_date)s")
		values["from_date"] = getdate(from_date)
	if to_date:
		where.append("c.date <= %(to_date)s")
		values["to_date"] = getdate(to_date)
	return "".join(" and " + w for w in where), values


def _chat_rows(rows):
	names = [r.name for r in rows]
	items = {}
	if names:
		for r in frappe.db.sql(
			"select parent, name, text, status, task from `tabLife Chat Open Item` where parenttype='Life Chat Log' and parent in %s order by parent, idx",
			(names,), as_dict=True):
			items.setdefault(r.parent, []).append({"row": r.name, "text": r.text, "status": r.status, "task": r.task})
	areas = names_map("Life Area", [r.area for r in rows], "area_name")
	goals = names_map("Life Goal", [r.goal for r in rows], "title")
	for r in rows:
		r["date"] = str(r.date) if r.date else None
		r["area"], r["goal"] = r.area or None, r.goal or None
		r["area_name"], r["goal_title"] = areas.get(r.area), goals.get(r.goal)
		r["summary_md"] = r.summary_md or ""
		r["open_items"] = items.get(r.name, [])
		r["open_count"] = sum(1 for i in r["open_items"] if i["status"] == "Open")
	return rows


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, area: str | None = None, goal: str | None = None, open_items: bool | int | None = 0, from_date: str | None = None, to_date: str | None = None, include_archived: bool | int | None = 0,
		group_by: str = "day", sort: str | None = None, dir: str | None = None, start: int | None = 0, page_length: int | None = 50, filters: str | builtins.list | dict | None = None,
		order_by: str | None = None, summary: str | dict | None = None, project: str | None = None):
	"""Chat logs of a space as one list, newest first, ordered so that the groups of group_by (day, area, goal) stay together.
	Filters: area (with its sub-areas, or "none"), goal (`project` names the goal a project became), open_items=1 for chats that still have an open item, from_date, to_date.
	`total` is the number of chats the filters match. `with_open_items` and `by_area` count inside the same filters.
	`tabs` counts all chats and those with open items under the same filters, whatever open_items was asked for."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	group_by = "goal" if group_by == "project" else group_by
	if project and not goal:  # for one set after projects became goals (set 6): a project names the goal it became
		goal = project if project == "none" else (goal_for_project(project, space) or project)
	if group_by not in GROUP_ORDER:
		frappe.throw(_("group_by must be day, area or goal."))
	clause, values = where_clause(space, area, goal, open_items, from_date, to_date, include_archived)
	extra, values = std_clause("Life Chat Log", filters, "c", values)
	clause += extra
	values["space"] = space
	# the state tabs of the Chats screen (all, open = with open items), counted under every filter but the open-items switch
	t_clause, t_values = where_clause(space, area, goal, 0, from_date, to_date, include_archived)
	tabs = tab_counts(f"from `tabLife Chat Log` c where c.space=%(space)s {t_clause}{extra}", {**t_values, **values}, {"all": None, "open": OPEN_ITEM})
	if summary:
		return {"summary": summarise("Life Chat Log", f"from `tabLife Chat Log` c where c.space=%(space)s {clause}", values, "c", summary, start, page_length),
			"tabs": tabs}
	order = std_order("Life Chat Log", order_by, "c", SORTS) or sort_order(sort, dir, SORTS, None)
	order = f"{order}, c.creation desc" if order else f"{GROUP_ORDER[group_by]}, c.modified desc"
	# nosemgrep: frappe-sql-format-injection -- WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters
	rows = _chat_rows(frappe.db.sql(
		f"""select c.name, c.title, c.date, c.url, c.assistant, c.summary_md, c.area, c.goal, c.is_archived
		from `tabLife Chat Log` c where c.space=%(space)s {clause} order by {order} limit %(start)s, %(len)s""",
		{**values, "start": start, "len": page_length}, as_dict=True))
	base = f"from `tabLife Chat Log` c where c.space=%(space)s {clause}"
	# nosemgrep: frappe-sql-format-injection -- WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters
	total = frappe.db.sql(f"select count(*) {base}", values)[0][0]
	# nosemgrep: frappe-sql-format-injection -- WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters
	with_open = frappe.db.sql(f"select count(*) {base} and {OPEN_ITEM}", values)[0][0]
	# nosemgrep: frappe-sql-format-injection -- WHERE/ORDER from fixed fragments, area_filter and std_filters/std_order (fields checked against meta); values are parameters
	by_area = frappe.db.sql(f"select ifnull(c.area, ''), count(*) {base} group by ifnull(c.area, '') order by count(*) desc", values)
	area_names = names_map("Life Area", [a for a, n in by_area], "area_name")
	return {"space": space, "chats": rows, "total": total, "with_open_items": with_open, "group_by": group_by, "tabs": tabs,
		"by_area": [{"area": a or "none", "area_name": area_names.get(a) or "No area", "count": n} for a, n in by_area]}


@frappe.whitelist(methods=["GET"])
def get(chat: str):
	"""One chat log with its summary and open items."""
	doc = permissions.get_doc_checked("Life Chat Log", chat)
	row = _chat_rows([frappe._dict({k: doc.get(k) for k in ("name", "title", "date", "url", "assistant", "summary_md", "area", "goal", "is_archived")})])[0]
	row["space"] = doc.space
	row["transcript_md"] = doc.transcript_md or ""
	row["updated_on"] = str(doc.updated_on) if doc.updated_on else None
	row["source_system"] = doc.source_system
	return row


ASSISTANTS = ("Claude", "ChatGPT", "Codex", "Claude Code", "Other")


@frappe.whitelist(methods=["POST"])
def log(space: str | None = None, title: str | None = None, date: str | datetime.date | None = None, url: str | None = None, assistant: str | None = "Claude",
		summary_md: str | None = None, open_items: str | builtins.list | None = None, area: str | None = None, goal: str | None = None, tags: str | builtins.list | None = None,
		also_in: str | builtins.list | None = None, source_system: str | None = None, external_id: str | None = None, transcript_md: str | None = None,
		updated_on: str | datetime.datetime | None = None, project: str | None = None):
	"""Record an AI chat. Agents may call this directly: a chat log is a record of what happened, not a proposal.
	open_items is a list of strings. area, goal and tags take a name or a title; `project` names the goal a project became.

	With source_system (claude, chatgpt…) and external_id (the chat's ID there), a chat already logged is updated instead of
	logged twice: title, updated_on, url, summary and transcript change when given, and open items are merged by their text
	(new ones are added, closed ones stay closed). The connection of that system gives the default area and goal.
	The answer is {name, created}."""
	from lifeos import proposals
	from lifeos.api import connections

	space = permissions.resolve_space(space, write=True)
	if not (title or "").strip():
		frappe.throw(_("A chat log needs a title."))
	if assistant not in ASSISTANTS:
		assistant = "Other"
	system = (source_system or "").strip().lower() or None
	ext = (external_id or "").strip() or None
	items = [str(t).strip()[:500] for t in parse(open_items, []) or [] if str(t).strip()]
	existing = frappe.db.get_value("Life Chat Log", {"space": space, "source_system": system, "external_id": ext}) if system and ext else None
	if existing:
		doc = permissions.get_doc_checked("Life Chat Log", existing, "write")
		fields = ("title", "url", "summary_md", "transcript_md", "updated_on")
		before = {f: doc.get(f) for f in fields}
		doc.title = title.strip()[:140]
		for field, value in (("url", url), ("summary_md", summary_md), ("transcript_md", transcript_md)):
			if value is not None:
				doc.set(field, value)
		if updated_on:
			doc.updated_on = frappe.utils.get_datetime(updated_on).replace(microsecond=0)
		have = {(i.text or "").strip().lower() for i in doc.open_items}
		added = 0
		for t in items:
			if t.lower() not in have:
				doc.append("open_items", {"text": t, "status": "Open"})
				have.add(t.lower())
				added += 1
		same = lambda a, b: (a or "") == (b or "") if not hasattr(a, "year") and not hasattr(b, "year") else \
			(frappe.utils.get_datetime(a) if a else None) == (frappe.utils.get_datetime(b) if b else None)
		changed = added or any(not same(before[f], doc.get(f)) for f in fields)
		if changed:
			doc.save()
		connections.touch(space, system, doc.title)
		return {"name": doc.name, "created": False, "changed": bool(changed)}
	conn = connections.connection(space, system) if system else None
	doc = frappe.get_doc({"doctype": "Life Chat Log", "space": space, "title": title.strip()[:140], "date": getdate(date or today()), "url": url,
		"assistant": assistant, "summary_md": summary_md, "transcript_md": transcript_md, "source_system": system, "external_id": ext,
		"updated_on": frappe.utils.get_datetime(updated_on) if updated_on else None,
		"open_items": [{"text": t, "status": "Open"} for t in items]})
	try:
		if area:
			doc.area = proposals.resolve_link("Life Area", area, space)
		elif conn and conn.default_area:
			doc.area = conn.default_area
		if project and not goal:
			goal = goal_for_project(project, space) or project
		if goal:
			doc.goal = proposals.resolve_link("Life Goal", goal, space)
		elif conn and conn.default_goal and not area:
			doc.goal = conn.default_goal
		for a in parse(also_in, []) or []:
			doc.append("also_in", {"area": proposals.resolve_link("Life Area", a, space)})
		for t in parse(tags, []) or []:
			doc.append("tags", {"tag": proposals.resolve_link("Life Tag", t, space)})  # existing tags only
	except proposals.PayloadError as e:
		frappe.throw(str(e))
	doc.insert()
	if system:
		connections.touch(space, system, doc.title)
	return {"name": doc.name, "created": True}


@frappe.whitelist(methods=["GET"])
def needs_summary(space: str | None = None, start: int | None = 0, page_length: int | None = 50):
	"""Chat logs with no summary yet (imported chats), oldest activity first, for an agent to summarise with
	lifeos.api.chats.save_summary. Each row has name, title, date, updated_on, assistant, url and the transcript's length."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	rows = frappe.db.sql("""select name, title, date, updated_on, assistant, url, char_length(ifnull(transcript_md, '')) as transcript_length
		from `tabLife Chat Log` where space=%(space)s and ifnull(summary_md, '') = '' order by ifnull(updated_on, date) desc
		limit %(start)s, %(len)s""", {"space": space, "start": start, "len": page_length}, as_dict=True)
	total = frappe.db.sql("select count(*) from `tabLife Chat Log` where space=%s and ifnull(summary_md, '') = ''", space)[0][0]
	for r in rows:
		r["date"] = str(r.date) if r.date else None
		r["updated_on"] = str(r.updated_on) if r.updated_on else None
	return {"space": space, "chats": rows, "total": total}


@frappe.whitelist(methods=["GET"])
def transcript(chat: str):
	"""The full transcript of a chat log, for an agent writing its summary."""
	doc = permissions.get_doc_checked("Life Chat Log", chat)
	return {"name": doc.name, "title": doc.title, "transcript_md": doc.transcript_md or ""}


@frappe.whitelist(methods=["POST"])
def save_summary(chat: str, summary_md: str, open_items: str | builtins.list | None = None):
	"""Write the summary of a chat log (and add open items found in it). Agents may call this."""
	doc = permissions.get_doc_checked("Life Chat Log", chat, "write")
	doc.summary_md = summary_md
	have = {(i.text or "").strip().lower() for i in doc.open_items}
	for t in parse(open_items, []) or []:
		t = str(t).strip()[:500]
		if t and t.lower() not in have:
			doc.append("open_items", {"text": t, "status": "Open"})
			have.add(t.lower())
	doc.save()
	return {"name": doc.name}


def _row(chat, row):
	doc = permissions.get_doc_checked("Life Chat Log", chat, "write")
	item = next((i for i in doc.open_items if i.name == row), None)
	if not item:
		frappe.throw(_("Open item not found."), frappe.DoesNotExistError)
	return doc, item


@frappe.whitelist(methods=["POST"])
def make_task(chat: str, row: str):
	"""Turn an open item into a task. People only: an open item becomes a task only when the owner asks."""
	if permissions.is_agent():
		frappe.throw(_("Only a person can turn an open item into a task."), frappe.PermissionError)
	doc, item = _row(chat, row)
	if item.status == "Task Created" and item.task:
		return {"task": item.task}
	task = frappe.get_doc({"doctype": "Life Task", "space": doc.space, "title": item.text[:140], "area": doc.area, "goal": doc.goal,
		"source_url": doc.url, "notes_md": f"From the chat [[{doc.title}#{doc.name}]].", "status": "Open"}).insert()
	item.status, item.task = "Task Created", task.name
	doc.save()
	return {"task": task.name}


@frappe.whitelist(methods=["POST"])
def close_item(chat: str, row: str, reopen: bool | int | None = 0):
	"""Close an open item without making a task, or open it again."""
	doc, item = _row(chat, row)
	item.status = "Open" if int(reopen or 0) else "Closed"
	doc.save()
	return {"row": item.name, "status": item.status}
