"""The tools Ask's model reads the owner's records with (UX fixes, set 5). Every tool runs on the server as the asking
user, inside the thread's space, with the space rules, the Vault rules and the question's scope applied. Records are
named to the model as short references (R1, R2, …) that the answer cites; the server maps them back."""
import json
import re

import frappe
from frappe import _
from frappe.query_builder import Case, Order
from frappe.utils import add_days, cint, getdate, today

from lifeos import permissions
from lifeos.api.utils import area_criterion, count_where, descendants, list_query
from lifeos.web.pane_refs import ref_of

TEXT_CAP = 6000  # characters of a record's text sent to the model
MAX_ROWS = 50
WORD = re.compile(r"[\w']+", re.UNICODE)
STOP = set("""a an and are as at be but by can could did do does for from had has have how i in into is it its me my of on or our
show so than that the their them then there these they this to up was we were what when where which who why will with would you your
still open here stuck tell give list find about any all""".split())

KIND_DOCTYPE = {"task": "Life Task", "note": "Life Note", "source": "Life Inbox Item", "chat": "Life Chat Log", "document": "Life Vault Document",
	"goal": "Life Goal", "insight": "Life Insight"}
INDEX_KIND = {"task": "Task", "note": "Note", "source": "Inbox", "chat": "Chat", "document": "Document"}

TOOLS = [
	{"name": "search", "description": "Search the owner's records (notes, wiki pages, tasks, sources and their transcripts, chats) by words. Returns matching records with a snippet and a reference such as R3 to cite.",
		"input_schema": {"type": "object", "properties": {
			"query": {"type": "string", "description": "A few key words, not a sentence."},
			"kinds": {"type": "array", "items": {"type": "string", "enum": sorted(INDEX_KIND)}, "description": "Only these kinds."},
			"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string", "description": "YYYY-MM-DD"}},
			"required": ["query"]}},
	{"name": "get_record", "description": "One record's fields and text (truncated), by its reference (R3) or doctype and name.",
		"input_schema": {"type": "object", "properties": {"ref": {"type": "string"}, "doctype": {"type": "string"}, "name": {"type": "string"}}}},
	{"name": "list_records", "description": "Rows of one kind, at most 50: tasks, goals, notes, sources, chats, someday (parked tasks, goals and notes), insights.",
		"input_schema": {"type": "object", "properties": {
			"kind": {"type": "string", "enum": ["tasks", "goals", "notes", "sources", "chats", "someday", "insights"]},
			"filters": {"type": "object", "description": "For tasks: status (open, waiting, done, someday, overdue, due_today, stuck), area, goal. For goals: state (in_progress, achieved, closed, someday), type (12 Week Year, Annual, Open), area. Others: area."},
			"order": {"type": "string", "enum": ["oldest", "newest", "due"]}, "limit": {"type": "integer"}},
			"required": ["kind"]}},
	{"name": "counts", "description": "A count with the list it opens: open_tasks, stuck_tasks, overdue_tasks, due_today_tasks, open_goals, idle_goals, goals_in_progress, inbox_to_review, inbox_old, someday, someday_due.",
		"input_schema": {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}},
	{"name": "cycle_state", "description": "The active 12 Week Year: week, scores, goals with their actions and this week's ticks, and this month's habits.",
		"input_schema": {"type": "object", "properties": {}}},
	{"name": "timeline", "description": "What happened in a period: records by day (created, completed, captured).",
		"input_schema": {"type": "object", "properties": {"date_from": {"type": "string"}, "date_to": {"type": "string"}}, "required": ["date_from"]}},
	{"name": "suggest_actions", "description": "Offer the owner buttons under the answer. Nothing changes until the owner clicks one. Use only records you cited.",
		"input_schema": {"type": "object", "properties": {"actions": {"type": "array", "items": {"type": "object", "properties": {
			"kind": {"type": "string", "enum": ["make_task", "move_someday", "open_reset", "open_list", "snooze_insight", "dismiss_insight", "file_mail"]},
			"label": {"type": "string", "description": "Button text, short: 'Make task: reply to Kunal', 'Move 11 to Someday'."},
			"title": {"type": "string", "description": "make_task: the task title"}, "area_ref": {"type": "string", "description": "make_task: a cited record whose area the task takes"},
			"due_date": {"type": "string"}, "refs": {"type": "array", "items": {"type": "string"}, "description": "move_someday, open_reset: the cited records"},
			"list": {"type": "string", "description": "open_list: one of the counts kinds"}, "insight_ref": {"type": "string"},
			"thread_id": {"type": "string", "description": "file_mail: a thread you read with mail_thread. The label names the email by who sent it and what it is: 'File Ashmeet's leave email'."}},
			"required": ["kind", "label"]}}}, "required": ["actions"]}},
]
# issue 107: what Ask does when the owner asks. Each runs the plain function in lifeos/tools, as the asking person, and the answer lists what it did, each with Undo.
WRITE_TOOLS = [
	{"name": "create_page", "description": "Create a wiki page under an area (and a part of it), by their names, when the owner asks for one. kind: Prospect, Client, Project, Person or Note. The body is Markdown and may link people and pages as [[Name]]. Refuses a title the wiki already has: use update_page on that page.",
		"input_schema": {"type": "object", "properties": {
			"title": {"type": "string"}, "area": {"type": "string", "description": "An area's name, e.g. Career."}, "part": {"type": "string", "description": "A part of the area, e.g. BTW."},
			"kind": {"type": "string", "enum": ["Prospect", "Client", "Project", "Person", "Note"]}, "body": {"type": "string"}, "summary": {"type": "string", "description": "One line on what the page is about."},
			"sources": {"type": "array", "items": {"type": "string"}, "description": "Emails or captures it is written from, as 'Life Inbox Item:<name>' (an email saved with save_attachment says its item)."}},
			"required": ["title", "area"]}},
	{"name": "update_page", "description": "Change a wiki page found with search or made with create_page: replace its text (send the whole new text), and/or add links to other pages or people.",
		"input_schema": {"type": "object", "properties": {"page": {"type": "string", "description": "The page's name, or the reference R3 of a record you found."}, "body": {"type": "string"},
			"add_links": {"type": "array", "items": {"type": "string"}, "description": "Titles of pages or people to link under Links."}}, "required": ["page"]}},
	{"name": "add_person", "description": "Add a person (with their email and company) when the owner asks; a person already there is reused. link_to is a page's name: the page lists them under People.",
		"input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "email": {"type": "string"}, "company": {"type": "string"}, "link_to": {"type": "string"}}, "required": ["name"]}},
	{"name": "save_note", "description": "Save text you wrote, such as a summary the owner asked you to file, as a note under an area (and a part), by their names.",
		"input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}, "area": {"type": "string"}, "part": {"type": "string"}}, "required": ["title", "body", "area"]}},
	{"name": "make_task", "description": "Make a task now, only when the owner asked for it. For a task you think of yourself, offer a button with suggest_actions instead.",
		"input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "area": {"type": "string"}, "part": {"type": "string"}, "due_date": {"type": "string", "description": "YYYY-MM-DD"}}, "required": ["title"]}},
	{"name": "add_event", "description": "Put an event on the calendar now, only when the owner asked for it.",
		"input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "start": {"type": "string", "description": "YYYY-MM-DD or YYYY-MM-DD HH:MM"}, "end": {"type": "string"},
			"all_day": {"type": "boolean"}, "description": {"type": "string"}}, "required": ["title", "start"]}},
	{"name": "ask_one_question", "description": "When two records could be the one meant (for example two similar company names), ask the owner one question with each as a choice, then stop. The owner's choice comes back as their next message, and then you do the work. Do not hand the work back.",
		"input_schema": {"type": "object", "properties": {"question": {"type": "string"}, "choices": {"type": "array", "items": {"type": "string"}, "description": "Two to four short choices."}}, "required": ["question", "choices"]}},
]
TOOL_NAMES = [t["name"] for t in TOOLS]
# issue 86: offered only to a person who has connected an inbox; the search is live, nothing is copied into Life OS
MAIL_TOOLS = [
	{"name": "mail_search", "description": "Search the person's own inbox live, with plain fields (not Gmail's syntax). Returns up to 10 threads, newest first: subject, sender, date, a snippet, the thread_id and which inbox. Try two or three different searches before giving up.",
		"input_schema": {"type": "object", "properties": {
			"text": {"type": "string", "description": "Words to find, a few key words."}, "from": {"type": "string"}, "to": {"type": "string"}, "subject": {"type": "string"},
			"has_attachment": {"type": "boolean"}, "filename": {"type": "string", "description": "Part of an attachment's file name."},
			"after": {"type": "string", "description": "YYYY-MM-DD"}, "before": {"type": "string", "description": "YYYY-MM-DD"},
			"account": {"type": "string", "description": "One inbox, by its label or address. Leave out to search every inbox."}, "raw": {"type": "string", "description": "The provider's own query, only if the plain fields cannot say it."}}}},
	{"name": "mail_thread", "description": "Read one thread found by mail_search: each message's text and its attachments.",
		"input_schema": {"type": "object", "properties": {"thread_id": {"type": "string"}, "account": {"type": "string", "description": "The inbox the search said."}}, "required": ["thread_id"]}},
	{"name": "mail_list_threads", "description": "Every email thread of a period, 25 a page, newest first: use it for any question about a period, never mail_search (which stops at 10). When the answer has next_page_token, call again with it until it is empty. `pages` says how many pages the period holds.",
		"input_schema": {"type": "object", "properties": {"after": {"type": "string", "description": "YYYY-MM-DD, the first day"}, "before": {"type": "string", "description": "YYYY-MM-DD, the last day, included"},
			"query": {"type": "string"}, "page_token": {"type": "string"}, "account": {"type": "string"}}, "required": ["after", "before"]}},
	{"name": "digests_read", "description": "The daily email digests Life OS already wrote for a period, and the days that have none. For a summary of a period, read these first and search the inbox only for the missing days.",
		"input_schema": {"type": "object", "properties": {"start": {"type": "string", "description": "YYYY-MM-DD"}, "end": {"type": "string", "description": "YYYY-MM-DD"}}, "required": ["start", "end"]}},
	{"name": "save_attachment", "description": "Save one attachment of an email (from mail_thread) in Life OS when the owner asks: under an area or part, attached to a page when one is given. The email it came from is kept with it. vault_type (ID, Travel, Insurance, Property, Tax, Medical, Other) only for an ID card, a statement or another private document: it goes to the Vault.",
		"input_schema": {"type": "object", "properties": {"thread_id": {"type": "string"}, "attachment_id": {"type": "string"}, "area": {"type": "string"}, "part": {"type": "string"}, "page": {"type": "string", "description": "A page's name from create_page."},
			"vault_type": {"type": "string"}, "account": {"type": "string"}}, "required": ["thread_id", "attachment_id"]}},
]


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
		self.mails = []  # threads a search found: {thread_id, account, subject, from, date, link}
		self.mails_read = []  # of those, the ones read in full
		self.no_tools = False  # the service takes no tools (issue 102): Ask answers from one search of the question
		self.turn_cost = 0.0  # the AI cost of the model turn that is calling a tool; a search is logged with it
		self._has_mail = None
		self.done = []  # what the answer did (issue 107): {text, undo, kind, doctype, name}; each with Undo
		self.choice = None  # a question with choices the owner answers by tapping one
		self.background = False  # a long read of mail runs as a background job
		self.progress = None  # called with what is being read, for the screen
		self.mail_pages = {}  # (after, before, query) -> pages read

	def has_mail(self):
		if self._has_mail is None:
			from lifeos import mail

			self._has_mail = bool(mail.accounts_for(self.user, self.space))
		return self._has_mail

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

	# ---- the space, the Vault rule and the scope as criteria on Life Index rows ----
	def scope_criteria(self, x):
		"""The question's scope as a list of criteria over `frappe.qb.DocType("Life Index")`."""
		s = self.scope
		k = s.get("kind")
		if k == "area" and s.get("name"):
			return [area_criterion(self.space, s["name"], x, also_in="index")]
		if k in ("goal",) and s.get("name"):  # a goal: what is filed under it, and what links to it
			return [(x.goal == s["name"]) | x.ref_name.isin(self.scope_names() or [""])]
		if k in ("record", "items") and self.scope_names():
			return [x.ref_name.isin(self.scope_names())]
		if k == "notes":
			return [x.kind == "Note"]
		return []

	def index_criteria(self, x):
		"""The criteria every read of Life Index rows starts with: the space, the Vault rule (`vault_criteria`) and the scope."""
		return [x.space == self.space, *self.vault_criteria(x), *self.scope_criteria(x)]

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
			lk = frappe.qb.DocType("Life Link")
			mine = (lk.from_doctype == s["doctype"]) & (lk.from_name == s["name"]) | (lk.to_doctype == s["doctype"]) & (lk.to_name == s["name"])
			for a, b in frappe.qb.from_(lk).select(lk.to_name, lk.from_name).where((lk.space == self.space) & mine).run():  # system: the links of the record in the question's own space
				names += [a, b]
			if s["doctype"] == "Life Goal":
				names += frappe.get_all("Life Task", filters={"goal": s["name"]}, pluck="name", limit=200)
			for f in ("inbox_item", "goal", "serves", "parent_note"):
				if frappe.get_meta(s["doctype"]).has_field(f):
					v = frappe.db.get_value(s["doctype"], s["name"], f)
					if v:
						names.append(v)
		self._scope_names = sorted({n for n in names if n})
		return self._scope_names

	def vault_criteria(self, x):
		"""Leaves Vault rows, and sources of Vault documents, out unless the space lets Ask read the Vault."""
		return [] if self.vault_ok else [(x.vault_locked == 0) & (x.ref_doctype != "Life Vault Document")]


def run_tool(ctx, name, args):
	"""Run one tool as the asking user. Returns a JSON-serialisable result; a refusal is a result too."""
	ctx.calls += 1
	args = args or {}
	try:
		fn = {"search": t_search, "get_record": t_get_record, "list_records": t_list, "counts": t_counts,
			"cycle_state": t_cycle, "timeline": t_timeline, "suggest_actions": t_suggest, "mail_search": t_mail_search, "mail_thread": t_mail_thread,
			"mail_list_threads": t_mail_list_threads, "digests_read": t_digests_read, "save_attachment": t_save_attachment, "create_page": t_create_page,
			"update_page": t_update_page, "add_person": t_add_person, "save_note": t_save_note, "make_task": t_make_task, "add_event": t_add_event,
			"ask_one_question": t_ask_one_question}[name]
	except KeyError:
		return {"error": f"Unknown tool {name}."}
	try:
		return fn(ctx, **{k: v for k, v in args.items() if v not in (None, "")})
	except frappe.PermissionError:
		return {"error": "Not allowed: this record is outside what you may read or change."}
	except frappe.DoesNotExistError:
		return {"error": "Not found."}
	except (frappe.DuplicateEntryError, frappe.ValidationError) as e:
		frappe.clear_messages()  # the model is told; the owner is not given a second pop-up
		return {"error": frappe.utils.strip_html(str(e))[:300]}
	except TypeError as e:
		return {"error": f"Bad arguments: {e}"}


def _words(q):
	return [w.lower() for w in WORD.findall(q or "") if w.lower() not in STOP][:10]


def t_search(ctx, query, kinds=None, date_from=None, date_to=None, limit=15):
	words = _words(query)
	if not words:
		return {"results": [], "note": "No search words."}
	x = frappe.qb.DocType("Life Index")
	where = [*ctx.index_criteria(x), x.kind != "Task Done", x.is_archived == 0]
	if kinds:
		where.append(x.kind.isin([INDEX_KIND[k] for k in kinds if k in INDEX_KIND] or [""]))
	if date_from:
		where.append(x.record_date >= getdate(date_from))
	if date_to:
		where.append(x.record_date <= getdate(date_to))
	# any of the words, best match first; a plain match for short words and for rows the full-text index has not seen yet
	likes = [x.title.like(f"%{w}%") | x.search_text.like(f"%{w}%") for w in words]
	any_word = likes[0]
	for like in likes[1:]:
		any_word = any_word | like
	score = Case().when(x.title.like(f"%{words[0]}%"), 3).else_(0) + Case().when(x.search_text.like(f"%{words[0]}%"), 1).else_(0)
	for w in words[1:]:
		score = score + Case().when(x.title.like(f"%{w}%"), 3).else_(0) + Case().when(x.search_text.like(f"%{w}%"), 1).else_(0)
	fields = ["ref_doctype", "ref_name", "title", "kind", "record_date", "area", "status", "search_text"]
	rows = list_query("Life Index", fields, [*where, any_word], [(score, Order.desc), (x.record_date, Order.desc)]).select(score.as_("score")).limit(min(cint(limit) or 15, 25)).run(as_dict=True)
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
	"Life Chat Log": ["summary_md", "transcript_md"],
	"Life Goal": ["done_when", "notes_md", "result_note"], "Life Vault Document": ["notes_md"], "Life Insight": ["body"]}
FIELDS = {"Life Task": ["status", "due_date", "priority", "goal", "completed_on", "last_touched_on", "someday_review_on"],
	"Life Goal": ["horizon", "outcome", "on_hold", "target_date", "cycle", "serves", "is_someday", "last_activity_on"],
	"Life Inbox Item": ["status", "received_on", "source_type", "intent"], "Life Chat Log": ["date", "assistant", "url"],
	"Life Note": ["collection", "last_opened_on", "page_date"], "Life Vault Document": ["doc_type", "expiry_date", "number_last4"],
	"Life Insight": ["kind", "status"]}


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
	doc = permissions.get_doc_checked(doctype, name, user=ctx.user)
	if doc.get("space") != ctx.space:
		return {"error": "That record is in another space."}
	if doctype == "Life Inbox Item" and doc.get("vault_document") and not ctx.vault_ok:
		return {"error": "This source belongs to a Vault document, which Ask may not read in this space."}
	if doc.get("is_sensitive") and not ctx.vault_ok:
		return {"error": "This item is marked sensitive, and Ask may not read sensitive items in this space."}
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
	from lifeos.review import counts
	from lifeos.api import goals, someday, tasks

	filters = filters if isinstance(filters, dict) else (json.loads(filters) if isinstance(filters, str) and filters else {})
	limit = min(cint(limit) or 20, MAX_ROWS)
	area = filters.get("area")
	if area and not frappe.db.exists("Life Area", {"name": area, "space": ctx.space}):
		area = frappe.db.get_value("Life Area", {"area_name": area, "space": ctx.space})
	scope = ctx.scope
	if scope.get("kind") == "area" and not area:
		area = scope.get("name")
	goal = filters.get("goal") or (scope.get("name") if scope.get("kind") in ("goal",) else None)
	if kind == "tasks":
		st = str(filters.get("status") or "open").lower()
		args = {"space": ctx.space, "area": area, "goal": goal, "page_length": limit}
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
		return {"total": res["total"], "rows": _rows_out(ctx, "Life Task", res["tasks"], extra=("status", "due_date", "goal_title", "last_touched_on", "waiting_on"))}
	if kind == "goals":
		horizon = filters.get("type")
		res = goals.list(space=ctx.space, state=filters.get("state") or "in_progress", horizon=horizon if horizon in goals.TYPES else None,
			area=area, page_length=limit)
		return {"total": res["total"], "rows": _rows_out(ctx, "Life Goal", res["goals"], extra=("horizon", "outcome", "tasks_done", "tasks_counted", "score"))}
	if kind == "someday":
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
	x = frappe.qb.DocType("Life Index")
	where = [*ctx.index_criteria(x), x.kind == index_kind, x.is_archived == 0]
	if area and ctx.scope.get("kind") != "area":
		where.append(x.area.isin(descendants(ctx.space, area)))
	fields = ["ref_doctype", "ref_name", "title", "record_date", "area", "status"]
	rows = list_query("Life Index", fields, where, [(x.record_date, Order.asc if order == "oldest" else Order.desc)]).limit(limit).run(as_dict=True)
	total = count_where("Life Index", where)
	return {"total": total, "rows": [{"ref": ctx.ref(r.ref_doctype, r.ref_name, r.title, index_kind, r.record_date, r.area), "title": r.title,
		"date": str(r.record_date), "area": _area(r.area), "status": r.status or None} for r in rows]}


COUNT_KINDS = {"open_tasks", "stuck_tasks", "overdue_tasks", "due_today_tasks", "open_goals", "idle_goals", "goals_in_progress",
	"inbox_to_review", "inbox_old", "someday", "someday_due"}


def t_counts(ctx, kind):
	from lifeos.review import counts

	if kind not in COUNT_KINDS:
		return {"error": f"kind must be one of {', '.join(sorted(COUNT_KINDS))}."}
	fn = {"open_goals": counts.active_open_goals, "idle_goals": counts.idle_open_goals}.get(kind) or getattr(counts, kind)
	area = ctx.scope.get("name") if ctx.scope.get("kind") == "area" else None  # the lens's area, when the question has one
	c = fn(ctx.space, area)
	return {"kind": kind, "n": c["n"], "label": c["label"], "list": c["to"]}


def t_cycle(ctx):
	from lifeos.api import today as today_api

	t = today_api.get(space=ctx.space)
	cycle = t.get("cycle") or {}
	out = {"week": cycle.get("week"), "weeks": 12, "cycle": cycle.get("title"), "week_score": cycle.get("score"), "target": t.get("target"),
		"this_week_actions": [{"title": a["title"], "goal": a["goal_title"], "ticks": a["count"], "per_week": a["per_week"]} for a in cycle.get("actions") or []],
		"habits_today": [{"habit": h["title"], "done": h["done"]} for h in t.get("habits") or []]}
	if cycle.get("name"):
		from lifeos.goals import cycles

		g = cycles.grid(cycle["name"])
		out["goals"] = [{"ref": ctx.ref("Life Goal", x["name"], x["title"], "Goal"), "title": x["title"], "percent": x.get("percent"),
			"actions": [a.get("title") for a in x.get("actions") or []]} for x in g.get("goals", [])]
		out["week_scores"] = [w.get("percent") for w in g.get("weeks", [])] if isinstance(g.get("weeks"), list) else None
	now = getdate(today())
	month = habits_this_month(ctx.space, now)
	out["habits_this_month"] = month
	return out


def habits_this_month(space, now):
	from lifeos.goals import habits

	m = habits.habits_month(space, now.year, now.month)
	return [{"habit": h["title"], "done": h["done"], "target": h["target"], "percent": h["percent"]} for h in m["habits"]]


def t_timeline(ctx, date_from, date_to=None):
	date_to = date_to or today()
	x = frappe.qb.DocType("Life Index")
	a, b = getdate(date_from), getdate(date_to)
	where = [*ctx.index_criteria(x), x.record_date.between(a, b)]
	rows = list_query("Life Index", ["ref_doctype", "ref_name", "title", "kind", "record_date", "area"], where, [(x.record_date, Order.desc)]).limit(60).run(as_dict=True)
	return {"from": str(a), "to": str(b), "rows": [{"ref": ctx.ref(r.ref_doctype, r.ref_name, r.title, r.kind, r.record_date, r.area),
		"kind": r.kind, "title": r.title, "date": str(r.record_date)} for r in rows]}


def t_suggest(ctx, actions):
	"""Record the buttons to show. Records are named by the references the answer cited."""
	from lifeos.review import counts

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
			item["items"] = [{"doctype": r["doctype"], "name": r["name"]} for r in recs if r["doctype"] in ("Life Task", "Life Goal")]
			if not item["items"]:
				continue
		elif kind == "open_list":
			k = a.get("list")
			if k not in COUNT_KINDS:
				continue
			item["to"] = getattr(counts, k)(ctx.space)["to"]
		elif kind == "file_mail":
			m = next((m for m in [*ctx.mails_read, *ctx.mails] if m["thread_id"] == a.get("thread_id")), None)
			if not m:
				continue
			item.update({"thread_id": m["thread_id"], "account": m["account"], "title": m["subject"], "link": m["link"]})
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


def tools_for(ctx):
	return None if ctx.no_tools else [*TOOLS, *WRITE_TOOLS, *(MAIL_TOOLS if ctx.has_mail() else [])]


def ask_call(ctx, system, question, messages, on_text, space):
	"""One model turn of Ask. A service that refuses tools gets one search of the question as data instead, and the turn is repeated."""
	from lifeos.ai import client

	try:
		return client.call("Ask", system, messages, tools=tools_for(ctx), on_text=on_text, space=space)
	except client.ToolsRefused:
		ctx.no_tools = True
		found = run_tool(ctx, "search", {"query": question})
		messages[-1] = {"role": "user", "content": f"{messages[-1]['content']}\n\nSearch results (the only records you can use):\n{json.dumps(found, default=str)[:24000]}"}
		return client.call("Ask", system, messages, on_text=on_text, space=space)


def t_mail_search(ctx, text=None, has_attachment=None, account=None, **fields):
	"""A live search of the asking person's inboxes. One log record; the AI cost of this turn goes on it."""
	from lifeos import mail
	from lifeos.mail.gmail import GmailError, scrub

	cost, ctx.turn_cost = ctx.turn_cost, 0.0
	try:
		found = mail.search(ctx.user, ctx.space, {"text": text, "has_attachment": has_attachment, **{k: v for k, v in fields.items() if k in mail.FIELDS}}, account, 10, cost=cost)
	except GmailError as e:
		return {"error": scrub(e)}
	except frappe.ValidationError as e:
		return {"error": str(e)}
	rows = []
	for h in found["hits"]:
		if h["thread_id"] not in {m["thread_id"] for m in ctx.mails}:
			ctx.mails.append({"thread_id": h["thread_id"], "account": h["account"], "subject": h["subject"], "from": h["from"], "date": h["date"], "link": h["link"]})
		rows.append({k: h[k] for k in ("thread_id", "subject", "from", "date", "snippet", "inbox")})
	return {"results": rows, "searched": found["searched"], "errors": found["errors"], "note": "These are not records in Life OS: say who, when and what, not a reference."}


def t_mail_thread(ctx, thread_id, account=None):
	from lifeos import mail
	from lifeos.mail.gmail import GmailError, scrub

	try:
		got = mail.get_thread(ctx.user, ctx.space, thread_id, account)
	except GmailError as e:
		return {"error": scrub(e)}
	known = next((m for m in ctx.mails if m["thread_id"] == thread_id), None)
	if known and known not in ctx.mails_read:
		ctx.mails_read.append(known)
	elif not known:
		known = {"thread_id": thread_id, "account": got["account"], "subject": got["subject"], "from": got["messages"][0]["from"] if got["messages"] else "", "date": "", "link": got["link"]}
		ctx.mails.append(known)
		ctx.mails_read.append(known)
	return {"subject": got["subject"], "inbox": got["inbox"], "messages": [{"from": m["from"], "date": m["date"], "text": m["text"][:TEXT_CAP], "attachments": m["attachments"]}
		for m in got["messages"][:6]]}


# ---- issue 107: reading a period of mail, and what Ask does when the owner asks (each write lists itself under "Done" with Undo) ----

class NeedsBackground(Exception):
	"""A question that needs more than 3 pages of mail: it is run again as a background job, which reports each page."""


BACKGROUND_PAGES = 3


def _label_period(after, before):
	a, b = getdate(after), getdate(before)
	return f"{a.day}–{b.day} {b.strftime('%b')}" if (a.year, a.month) == (b.year, b.month) else f"{a.day} {a.strftime('%b')}–{b.day} {b.strftime('%b')}"


def t_mail_list_threads(ctx, after, before, query=None, page_token=None, account=None):
	from lifeos.tools import mail as mail_tools

	got = mail_tools.list_threads(after, before, query, page_token, ctx.space, account)
	key = (after, before, query or "")
	ctx.mail_pages[key] = n = ctx.mail_pages.get(key, 0) + 1
	if got["pages"] > BACKGROUND_PAGES and not ctx.background:
		raise NeedsBackground
	if ctx.progress:
		ctx.progress(f"Reading {_label_period(after, before)}… (page {n} of {max(got['pages'], n)})")
	rows = [{k: t[k] for k in ("thread_id", "subject", "from", "date", "snippet", "inbox")} for t in got["threads"]]
	return {"threads": rows, "next_page_token": got["next_page_token"], "page": n, "pages": got["pages"], "note": "These are not records in Life OS: say who, when and what, not a reference."}


def t_digests_read(ctx, start, end):
	from lifeos.tools import digests

	return digests.read(start, end, ctx.space)


def _did(ctx, out, kind, doctype=None, name=None):
	"""Remember a write for the "Done" list under the answer; the model gets the same line back."""
	ctx.done.append({"text": out["done"], "undo": out.get("undo"), "kind": kind, "doctype": doctype, "name": name, "pane": ref_of(doctype, name) if doctype and name else None})
	return {"done": out["done"], **{k: v for k, v in out.items() if k in ("page", "person", "note", "task", "event", "item", "file", "file_name", "title", "organisation", "vault_document")}}


def _page_arg(ctx, page):
	r = ctx.refs.get(str(page).strip()) if page else None
	if r:
		if r["doctype"] != "Life Note":
			frappe.throw(_("That record is not a page."), title=_("Not a page"))
		return r["name"]
	return page


def t_create_page(ctx, title, area, part=None, kind=None, body=None, summary=None, sources=None):
	from lifeos.tools import pages

	out = pages.create(title, area, part, kind, body, sources, summary, space=ctx.space)
	return _did(ctx, out, "page", "Life Note", out["page"])


def t_update_page(ctx, page, body=None, add_links=None):
	from lifeos.tools import pages

	out = pages.update(_page_arg(ctx, page), body, add_links, space=ctx.space)
	return _did(ctx, out, "page", "Life Note", out["page"])


def t_add_person(ctx, name, email=None, company=None, link_to=None):
	from lifeos.tools import people

	out = people.add(name, email, company, _page_arg(ctx, link_to), space=ctx.space)
	return _did(ctx, out, "person", "Life Person", out["person"])


def t_save_note(ctx, title, body, area, part=None):
	from lifeos.tools import notes

	out = notes.save(title, body, area, part, space=ctx.space)
	return _did(ctx, out, "note", "Life Note", out["note"])


def t_save_attachment(ctx, thread_id, attachment_id, area=None, part=None, page=None, vault_type=None, account=None):
	from lifeos.tools import mail as mail_tools

	out = mail_tools.save_attachment(thread_id, attachment_id, area, part, _page_arg(ctx, page), vault_type, account, ctx.space)
	return _did(ctx, out, "file", "Life Note" if out.get("page") else "Life Inbox Item", out.get("page") or out["item"])


def t_make_task(ctx, title, area=None, part=None, due_date=None):
	from lifeos.tools import work

	out = work.add_task(title, area, part, due_date, ctx.space)
	return _did(ctx, out, "task", "Life Task", out["task"])


def t_add_event(ctx, title, start, end=None, all_day=False, description=None):
	from lifeos.tools import work

	out = work.add_event(title, start, end, bool(all_day), description, ctx.space)
	return _did(ctx, out, "event")


def t_ask_one_question(ctx, question, choices):
	"""The question is the end of the turn: the owner taps a choice, which comes back as the next message."""
	picks = [str(c)[:80] for c in (choices or [])[:4] if str(c).strip()]
	if len(picks) < 2:
		return {"error": "Give two to four choices."}
	ctx.choice = {"question": str(question)[:300], "choices": picks}
	return {"ok": True, "note": "Write the question as your answer and stop. Do not call more tools."}


def file_actions(ctx):
	"""A button to file each thread the answer read (or, if none was read, the best three found), named for what it files: "File the email “LEAVE” from
	Ashmeet". The owner's click files it; nothing is filed before. A thread the model already named in suggest_actions, or one already filed, gets none."""
	if ctx.choice:  # a question with choices: the choices are the buttons, and nothing is offered to file
		return [{"kind": "choose", "label": c, "question": ctx.choice["question"]} for c in ctx.choice["choices"]]
	named = {a.get("thread_id") for a in ctx.actions if a.get("kind") == "file_mail"}
	chosen = [m for m in (ctx.mails_read or ctx.mails)[:3] if m["thread_id"] not in named
		and not frappe.db.exists("Life Inbox Item", {"space": ctx.space, "source_system": ["in", ["gmail", "microsoft"]], "external_id": m["thread_id"]})]
	return [{"kind": "file_mail", "label": file_label(m), "thread_id": m["thread_id"], "account": m["account"], "title": m["subject"], "link": m["link"]} for m in chosen]


def file_label(m):
	""""File the email “Leave request” from Ashmeet Singh": the whole subject (the button wraps), and who sent it."""
	who = re.sub(r"\s*[(<].*$", "", m.get("from") or "").strip().strip('"')
	return f"File the email “{m['subject'][:100]}”" + (f" from {who}" if who else "")
