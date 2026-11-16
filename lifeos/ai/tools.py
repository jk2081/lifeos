"""The tools Ask's model reads the owner's records with (UX fixes, set 5). Every tool runs on the server as the asking
user, inside the thread's space, with the space rules, the Vault rules and the question's scope applied. Records are
named to the model as short references (R1, R2, …) that the answer cites; the server maps them back."""
import json
import re

import frappe
from frappe.utils import add_days, cint, getdate, today

from lifeos import permissions
from lifeos.api.utils import descendants
from lifeos.pane_refs import ref_of

TEXT_CAP = 6000  # characters of a record's text sent to the model
MAX_ROWS = 50
WORD = re.compile(r"[\w']+", re.UNICODE)
STOP = set("""a an and are as at be but by can could did do does for from had has have how i in into is it its me my of on or our
show so than that the their them then there these they this to up was we were what when where which who why will with would you your
still open here stuck tell give list find about any all""".split())

KIND_DOCTYPE = {"task": "Life Task", "note": "Life Note", "source": "Life Inbox Item", "chat": "Life Chat Log", "document": "Life Vault Document",
	"journal page": "Life Journal Page", "project": "Life Project", "goal": "Life Goal", "idea": "Life Idea", "insight": "Life Insight"}
INDEX_KIND = {"task": "Task", "note": "Note", "source": "Inbox", "chat": "Chat", "document": "Document", "journal page": "Journal Page",
	"check-in": "Check-in", "month plan": "Month Plan"}

TOOLS = [
	{"name": "search", "description": "Search the owner's records (notes, wiki pages, tasks, sources and their transcripts, chats, journal pages, check-ins) by words. Returns matching records with a snippet and a reference such as R3 to cite.",
		"input_schema": {"type": "object", "properties": {
			"query": {"type": "string", "description": "A few key words, not a sentence."},
			"kinds": {"type": "array", "items": {"type": "string", "enum": sorted(INDEX_KIND)}, "description": "Only these kinds."},
			"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string", "description": "YYYY-MM-DD"}},
			"required": ["query"]}},
	{"name": "get_record", "description": "One record's fields and text (truncated), by its reference (R3) or doctype and name.",
		"input_schema": {"type": "object", "properties": {"ref": {"type": "string"}, "doctype": {"type": "string"}, "name": {"type": "string"}}}},
	{"name": "list_records", "description": "Rows of one kind, at most 50: tasks, projects, goals, notes, sources, chats, ideas (Someday), insights.",
		"input_schema": {"type": "object", "properties": {
			"kind": {"type": "string", "enum": ["tasks", "projects", "goals", "notes", "sources", "chats", "ideas", "insights"]},
			"filters": {"type": "object", "description": "For tasks: status (open, waiting, done, someday, overdue, due_today, stuck), area, project, goal. For projects: status (Active, On Hold, Done, Someday), area. For goals: state (in_progress, achieved, closed, someday). Others: area."},
			"order": {"type": "string", "enum": ["oldest", "newest", "due"]}, "limit": {"type": "integer"}},
			"required": ["kind"]}},
	{"name": "counts", "description": "A count with the list it opens: open_tasks, stuck_tasks, overdue_tasks, due_today_tasks, active_projects, idle_projects, goals_in_progress, inbox_to_review, inbox_old, someday, someday_due.",
		"input_schema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
	{"name": "journal_state", "description": "The active 12 Week Year: week, scores, goals with their actions and this week's ticks, and this month's habits.",
		"input_schema": {"type": "object", "properties": {}}},
	{"name": "timeline", "description": "What happened in a period: records by day (created, completed, captured).",
		"input_schema": {"type": "object", "properties": {"date_from": {"type": "string"}, "date_to": {"type": "string"}}, "required": ["date_from"]}},
	{"name": "suggest_actions", "description": "Offer the owner buttons under the answer. Nothing changes until the owner clicks one. Use only records you cited.",
		"input_schema": {"type": "object", "properties": {"actions": {"type": "array", "items": {"type": "object", "properties": {
			"kind": {"type": "string", "enum": ["make_task", "move_someday", "open_reset", "open_list", "snooze_insight", "dismiss_insight"]},
			"label": {"type": "string", "description": "Button text, short: 'Make task: reply to Kunal', 'Move 11 to Someday'."},
			"title": {"type": "string", "description": "make_task: the task title"}, "area_ref": {"type": "string", "description": "make_task: a cited record whose area the task takes"},
			"due_date": {"type": "string"}, "refs": {"type": "array", "items": {"type": "string"}, "description": "move_someday, open_reset: the cited records"},
			"list": {"type": "string", "description": "open_list: one of the counts kinds"}, "insight_ref": {"type": "string"}},
			"required": ["kind", "label"]}}}, "required": ["actions"]}},
]
TOOL_NAMES = [t["name"] for t in TOOLS]


class Context:
	"""What one question may read: the space, the scope, the Vault switch; and what it did read."""

	def __init__(self, space, scope=None, user=None):
		self.space = space
		self.scope = scope or {"kind": "space"}
		self.user = user or frappe.session.user
		self.vault_ok = bool(frappe.db.get_value("Life Space", space, "ask_can_read_vault"))
		self.refs = {}  # R1 -> {doctype, name, title, kind, date}
		self.by_key = {}
		self.read = []  # records whose text was sent
		self.actions = []
		self.calls = 0
		self._scope_names = None

	def ref(self, doctype, name, title="", kind="", date=None, area=None):
		key = (doctype, name)
		if key not in self.by_key:
			r = f"R{len(self.refs) + 1}"
			self.refs[r] = {"doctype": doctype, "name": name, "title": title or name, "kind": kind or doctype.replace("Life ", ""),
				"date": str(date)[:10] if date else None, "pane": ref_of(doctype, name), "area": area}
			self.by_key[key] = r
		return self.by_key[key]

	def mark_read(self, r):
		if r in self.refs and r not in self.read:
			self.read.append(r)

	# ---- the scope as SQL on Life Index rows ----
	def scope_sql(self, alias="x."):
		s, values = self.scope, {}
		k = s.get("kind")
		if k == "area" and s.get("name"):
			values["scope_ids"] = descendants(self.space, s["name"])
			from lifeos.index import also_in_sql

			return f" and ({alias}area in %(scope_ids)s or {also_in_sql('scope_ids', alias)})", values
		if k == "project" and s.get("name"):
			return f" and ({alias}project = %(scope_project)s or ({alias}ref_doctype = 'Life Project' and {alias}ref_name = %(scope_project)s))", {"scope_project": s["name"]}
		if k in ("record", "items", "goal") and self.scope_names():
			return f" and {alias}ref_name in %(scope_names)s", {"scope_names": self.scope_names()}
		if k == "notes":
			return f" and {alias}kind = 'Note'", {}
		return "", {}

	def scope_names(self):
		"""For a record scope: the record and the records linked to it, either way. For items: the items on screen."""
		if self._scope_names is not None:
			return self._scope_names
		s = self.scope
		names = []
		if s.get("kind") == "items":
			names = [i.get("name") for i in s.get("items") or [] if i.get("name")]
		elif s.get("doctype") and s.get("name"):
			names = [s["name"]]
			for a, b in frappe.db.sql("""select to_name, from_name from `tabLife Link` where space=%s and
				((from_doctype=%s and from_name=%s) or (to_doctype=%s and to_name=%s))""", (self.space, s["doctype"], s["name"], s["doctype"], s["name"])):
				names += [a, b]
			if s["doctype"] == "Life Project":
				names += frappe.get_all("Life Task", filters={"project": s["name"]}, pluck="name", limit=200)
			if s["doctype"] == "Life Goal":
				names += frappe.get_all("Life Task", filters={"goal": s["name"]}, pluck="name", limit=200)
			for f in ("inbox_item", "project", "goal", "parent_note"):
				if frappe.get_meta(s["doctype"]).has_field(f):
					v = frappe.db.get_value(s["doctype"], s["name"], f)
					if v:
						names.append(v)
		self._scope_names = sorted({n for n in names if n})
		return self._scope_names

	def vault_sql(self, alias="x."):
		return "" if self.vault_ok else f" and {alias}vault_locked = 0 and {alias}ref_doctype != 'Life Vault Document'"


def run_tool(ctx, name, args):
	"""Run one tool as the asking user. Returns a JSON-serialisable result; a refusal is a result too."""
	ctx.calls += 1
	args = args or {}
	try:
		fn = {"search": t_search, "get_record": t_get_record, "list_records": t_list, "counts": t_counts,
			"journal_state": t_journal, "timeline": t_timeline, "suggest_actions": t_suggest}[name]
	except KeyError:
		return {"error": f"Unknown tool {name}."}
	try:
		return fn(ctx, **{k: v for k, v in args.items() if v not in (None, "")})
	except frappe.PermissionError:
		return {"error": "Not allowed: this record is outside what you may read."}
	except frappe.DoesNotExistError:
		return {"error": "Not found."}
	except TypeError as e:
		return {"error": f"Bad arguments: {e}"}


def _words(q):
	return [w.lower() for w in WORD.findall(q or "") if w.lower() not in STOP][:10]


def t_search(ctx, query, kinds=None, date_from=None, date_to=None, limit=15):
	words = _words(query)
	if not words:
		return {"results": [], "note": "No search words."}
	where = f"x.space = %(space)s and x.kind != 'Task Done' and x.is_archived = 0{ctx.vault_sql()}"
	values = {"space": ctx.space, "limit": min(cint(limit) or 15, 25)}
	sql, v = ctx.scope_sql()
	where += sql
	values.update(v)
	if kinds:
		values["kinds"] = [INDEX_KIND[k] for k in kinds if k in INDEX_KIND] or [""]
		where += " and x.kind in %(kinds)s"
	if date_from:
		where += " and x.record_date >= %(df)s"
		values["df"] = getdate(date_from)
	if date_to:
		where += " and x.record_date <= %(dt)s"
		values["dt"] = getdate(date_to)
	# any of the words, best match first; a plain match for short words and for rows the full-text index has not seen yet
	likes = " or ".join(f"x.title like %(w{i})s or x.search_text like %(w{i})s" for i in range(len(words)))
	values.update({f"w{i}": f"%{w}%" for i, w in enumerate(words)})
	score = " + ".join(f"(x.title like %(w{i})s) * 3 + (x.search_text like %(w{i})s)" for i in range(len(words)))
	rows = frappe.db.sql(f"""select x.ref_doctype, x.ref_name, x.title, x.kind, x.record_date, x.area, x.status, x.search_text, ({score}) as score
		from `tabLife Index` x where {where} and ({likes}) order by score desc, x.record_date desc limit %(limit)s""", values, as_dict=True)
	from lifeos.api.search import _snippet

	out = []
	for r in rows:
		rid = ctx.ref(r.ref_doctype, r.ref_name, r.title, r.kind, r.record_date, r.area)
		ctx.mark_read(rid)
		out.append({"ref": rid, "kind": r.kind, "title": r.title, "date": str(r.record_date), "status": r.status or None,
			"area": _area(r.area), "snippet": _snippet(r.search_text or "", words, 300)})
	return {"results": out, "scope": ctx.scope.get("label") or ctx.scope.get("kind")}


def _area(area):
	return frappe.db.get_value("Life Area", area, "area_name") if area else None


TEXT_FIELDS = {"Life Note": ["summary", "content_md"], "Life Task": ["notes_md", "waiting_on"], "Life Inbox Item": ["instruction", "summary_md", "transcript_md", "raw_text"],
	"Life Chat Log": ["summary_md", "transcript_md"], "Life Journal Page": ["transcript_md"], "Life Project": ["outcome", "notes_md"],
	"Life Goal": ["result_note"], "Life Vault Document": ["notes_md"], "Life Idea": ["body_md", "someday_note"], "Life Insight": ["body"]}
FIELDS = {"Life Task": ["status", "due_date", "priority", "project", "goal", "completed_on", "last_touched_on", "someday_review_on"],
	"Life Project": ["status", "target_date", "last_activity_on"], "Life Goal": ["goal_type", "outcome", "target_date", "cycle", "is_someday"],
	"Life Inbox Item": ["status", "received_on", "source_type", "intent"], "Life Chat Log": ["date", "assistant", "url"],
	"Life Note": ["collection", "last_opened_on"], "Life Vault Document": ["doc_type", "expiry_date", "number_last4"],
	"Life Idea": ["status", "someday_review_on"], "Life Journal Page": ["page_date", "page_number"], "Life Insight": ["kind", "status"]}


def t_get_record(ctx, ref=None, doctype=None, name=None):
	if ref:
		r = ctx.refs.get(ref.strip())
		if not r:
			return {"error": f"Unknown reference {ref}."}
		doctype, name = r["doctype"], r["name"]
	if not doctype or not name:
		return {"error": "Give a reference, or a doctype and a name."}
	if doctype not in TEXT_FIELDS:
		return {"error": "That kind of record cannot be read here."}
	if doctype == "Life Vault Document" and not ctx.vault_ok:
		return {"error": "Vault documents are not available to Ask in this space."}
	doc = permissions.get_doc_checked(doctype, name)
	if doc.get("space") != ctx.space:
		return {"error": "That record is in another space."}
	if doctype == "Life Inbox Item" and doc.get("vault_document") and not ctx.vault_ok:
		return {"error": "This source belongs to a Vault document, which Ask may not read in this space."}
	title = doc.get(frappe.get_meta(doctype).title_field or "title") or doc.name
	rid = ctx.ref(doctype, name, title, doctype.replace("Life ", ""), doc.get("creation"), doc.get("area"))
	ctx.mark_read(rid)
	text = "\n\n".join(f"{f}: {doc.get(f)}" for f in TEXT_FIELDS[doctype] if doc.get(f))
	out = {"ref": rid, "doctype": doctype, "title": title, "created": str(doc.creation)[:10], "area": _area(doc.get("area")),
		"text": text[:TEXT_CAP], "truncated": len(text) > TEXT_CAP}
	for f in FIELDS.get(doctype, []):
		v = doc.get(f)
		if v not in (None, ""):
			out[f] = str(v)
	if doctype == "Life Chat Log":
		out["open_items"] = [{"text": r.text, "status": r.status} for r in doc.open_items]
	if doctype == "Life Insight":
		out["evidence"] = [ctx.ref(e.ref_doctype, e.ref_name, e.label) for e in doc.evidence]
	return out


def _rows_out(ctx, doctype, rows, title="title", extra=()):
	out = []
	for r in rows[:MAX_ROWS]:
		rid = ctx.ref(doctype, r["name"], r.get(title), doctype.replace("Life ", ""), r.get("creation"), r.get("area"))
		item = {"ref": rid, "title": r.get(title), "area": r.get("area_name") or _area(r.get("area"))}
		for f in extra:
			if r.get(f) not in (None, ""):
				item[f] = str(r.get(f))
		out.append(item)
	return out


def t_list(ctx, kind, filters=None, order=None, limit=20):
	from lifeos import counts
	from lifeos.api import goals, projects, someday, tasks

	filters = filters if isinstance(filters, dict) else (json.loads(filters) if isinstance(filters, str) and filters else {})
	limit = min(cint(limit) or 20, MAX_ROWS)
	area = filters.get("area")
	if area and not frappe.db.exists("Life Area", {"name": area, "space": ctx.space}):
		area = frappe.db.get_value("Life Area", {"area_name": area, "space": ctx.space})
	scope = ctx.scope
	if scope.get("kind") == "area" and not area:
		area = scope.get("name")
	project = filters.get("project") or (scope.get("name") if scope.get("kind") == "project" else None)
	if kind == "tasks":
		st = str(filters.get("status") or "open").lower()
		args = {"space": ctx.space, "area": area, "project": project, "goal": filters.get("goal"), "page_length": limit}
		wire = []
		if st == "open":
			args["status"] = "open"
		elif st == "waiting":
			args["status"] = "Waiting"
		elif st == "done":
			args["status"] = "Done"
		elif st == "someday":
			args["status"] = "Someday"
		elif st in ("overdue", "due_today"):
			args.update({"status": "open", "due": "overdue" if st == "overdue" else "today"})
		elif st == "stuck":
			args["status"] = "open"
			wire = counts.untouched(counts.rules()["stuck_after_days"])
		if order == "oldest":
			args["order_by"] = "creation asc"
		elif order == "newest":
			args["order_by"] = "creation desc"
		if wire:
			args["filters"] = json.dumps([list(w) for w in wire])
		if ctx.scope.get("kind") in ("items", "record") and ctx.scope_names():
			args["filters"] = json.dumps([*(json.loads(args.get("filters") or "[]")), ["name", "in", ctx.scope_names()]])
		res = tasks.list(**args)
		return {"total": res["total"], "rows": _rows_out(ctx, "Life Task", res["tasks"], extra=("status", "due_date", "project_title", "last_touched_on", "waiting_on"))}
	if kind == "projects":
		status = filters.get("status")
		res = projects.list(space=ctx.space, status=status if status in ("Active", "On Hold", "Done", "Dropped", "Someday") else None, area=area, page_length=limit)
		return {"total": res["total"], "rows": _rows_out(ctx, "Life Project", res["projects"], extra=("status", "target_date", "last_activity_on"))}
	if kind == "goals":
		res = goals.list(space=ctx.space, state=filters.get("state") or "in_progress", area=area, page_length=limit)
		return {"total": res["total"], "rows": _rows_out(ctx, "Life Goal", res["goals"], extra=("goal_type", "outcome", "tasks_done", "tasks_counted", "score"))}
	if kind == "ideas":
		res = someday.list(space=ctx.space, area=area, page_length=limit)
		return {"total": res["total"], "rows": [{"ref": ctx.ref(r.doctype, r.name, r.title, r.type, r.creation, r.area), "title": r.title, "type": r.type,
			"parked": r.someday_on, "review": r.someday_review_on} for r in res["rows"]]}
	if kind == "insights":
		from lifeos.api import insights

		res = insights.list(space=ctx.space, page_length=limit)
		return {"total": res["total"], "rows": [{"ref": ctx.ref("Life Insight", r.name, r.title, "Insight", r.creation), "title": r.title, "kind": r.kind,
			"status": r.status} for r in res["rows"]]}
	index_kind = {"notes": "Note", "sources": "Inbox", "chats": "Chat"}.get(kind)
	if not index_kind:
		return {"error": "Unknown kind."}
	where = f"x.space=%(space)s and x.kind=%(kind)s and x.is_archived=0{ctx.vault_sql()}"
	values = {"space": ctx.space, "kind": index_kind, "limit": limit}
	sql, v = ctx.scope_sql()
	where += sql
	values.update(v)
	if area and ctx.scope.get("kind") != "area":
		values["areas"] = descendants(ctx.space, area)
		where += " and x.area in %(areas)s"
	rows = frappe.db.sql(f"""select x.ref_doctype, x.ref_name, x.title, x.record_date, x.area, x.status from `tabLife Index` x where {where}
		order by x.record_date {'asc' if order == 'oldest' else 'desc'} limit %(limit)s""", values, as_dict=True)
	total = frappe.db.sql(f"select count(*) from `tabLife Index` x where {where}", values)[0][0]
	return {"total": total, "rows": [{"ref": ctx.ref(r.ref_doctype, r.ref_name, r.title, index_kind, r.record_date, r.area), "title": r.title,
		"date": str(r.record_date), "area": _area(r.area), "status": r.status or None} for r in rows]}


COUNT_KINDS = {"open_tasks", "stuck_tasks", "overdue_tasks", "due_today_tasks", "active_projects", "idle_projects", "goals_in_progress",
	"inbox_to_review", "inbox_old", "someday", "someday_due"}


def t_counts(ctx, kind):
	from lifeos import counts

	if kind not in COUNT_KINDS:
		return {"error": f"kind must be one of {', '.join(sorted(COUNT_KINDS))}."}
	c = getattr(counts, kind)(ctx.space)
	return {"kind": kind, "n": c["n"], "label": c["label"], "list": c["to"]}


def t_journal(ctx):
	from lifeos.api import today as today_api

	t = today_api.get(space=ctx.space)
	cycle = t.get("cycle") or {}
	out = {"week": cycle.get("week"), "weeks": 12, "cycle": cycle.get("title"), "week_score": cycle.get("score"), "target": t.get("target"),
		"this_week_actions": [{"title": a["title"], "goal": a["goal_title"], "ticks": a["count"], "per_week": a["per_week"]} for a in cycle.get("actions") or []],
		"habits_today": [{"habit": h["title"], "done": h["done"]} for h in t.get("habits") or []]}
	if cycle.get("name"):
		from lifeos import journal

		g = journal.grid(cycle["name"])
		out["goals"] = [{"ref": ctx.ref("Life Goal", x["name"], x["title"], "Goal"), "title": x["title"], "percent": x.get("percent"),
			"actions": [a.get("title") for a in x.get("actions") or []]} for x in g.get("goals", [])]
		out["week_scores"] = [w.get("percent") for w in g.get("weeks", [])] if isinstance(g.get("weeks"), list) else None
	now = getdate(today())
	month = journal_month(ctx.space, now)
	out["habits_this_month"] = month
	return out


def journal_month(space, now):
	from lifeos import journal

	m = journal.habits_month(space, now.year, now.month)
	return [{"habit": h["title"], "done": h["done"], "target": h["target"], "percent": h["percent"]} for h in m["habits"]]


def t_timeline(ctx, date_from, date_to=None):
	date_to = date_to or today()
	where = f"x.space=%(space)s and x.record_date between %(a)s and %(b)s{ctx.vault_sql()}"
	values = {"space": ctx.space, "a": getdate(date_from), "b": getdate(date_to)}
	sql, v = ctx.scope_sql()
	where += sql
	values.update(v)
	rows = frappe.db.sql(f"""select x.ref_doctype, x.ref_name, x.title, x.kind, x.record_date, x.area from `tabLife Index` x where {where}
		order by x.record_date desc limit 60""", values, as_dict=True)
	return {"from": str(values["a"]), "to": str(values["b"]), "rows": [{"ref": ctx.ref(r.ref_doctype, r.ref_name, r.title, r.kind, r.record_date, r.area),
		"kind": r.kind, "title": r.title, "date": str(r.record_date)} for r in rows]}


def t_suggest(ctx, actions):
	"""Record the buttons to show. Records are named by the references the answer cited."""
	from lifeos import counts

	kept = []
	for a in (actions or [])[:4]:
		kind = a.get("kind")
		item = {"kind": kind, "label": str(a.get("label") or kind)[:80]}
		if kind == "make_task":
			item["title"] = str(a.get("title") or a.get("label") or "")[:140]
			src = ctx.refs.get(a.get("area_ref") or "")
			item["area"] = src.get("area") if src else None
			item["due_date"] = a.get("due_date")
		elif kind in ("move_someday", "open_reset"):
			recs = [ctx.refs[r] for r in a.get("refs") or [] if r in ctx.refs]
			item["items"] = [{"doctype": r["doctype"], "name": r["name"]} for r in recs if r["doctype"] in ("Life Task", "Life Project", "Life Goal")]
			if not item["items"]:
				continue
		elif kind == "open_list":
			k = a.get("list")
			if k not in COUNT_KINDS:
				continue
			item["to"] = getattr(counts, k)(ctx.space)["to"]
		elif kind in ("snooze_insight", "dismiss_insight"):
			r = ctx.refs.get(a.get("insight_ref") or "")
			if not r or r["doctype"] != "Life Insight":
				continue
			item["insight"] = r["name"]
		else:
			continue
		kept.append(item)
	ctx.actions = kept
	return {"ok": True, "shown": len(kept)}
