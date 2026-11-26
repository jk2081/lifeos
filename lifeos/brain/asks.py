"""The summary of a capture, as data, and what comes of its "To act on" lines (issue 118).

The summarising skill answers in one shape (`SHAPE` below); `clean` keeps it tidy and drops anything sensitive, `render_md`
writes the Markdown copy that search and the older screens read, and `route_lines` makes a task for each line the Brain found:
on the owner's plate when only he can do it, in the waiting pile (status Waiting, a person, a check-by date) when someone else
is on it or when it is not sure. The owner changes a line with `change`; moving a line between plate and pile twice for one
sender makes a Route rule (issue 117's rules), so the Brain gets it right the next time. A reply that says it is done closes
a waiting task (`close_waiting`). The Brain never sends anything.
"""
import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime, today

from lifeos import permissions
from lifeos.brain import rules

WORDS = 20  # the most words in one line
FACTS = 5
ROUTES = ("plate", "waiting")
MOVES = ("plate", "waiting", "calendar", "not_needed")
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _words(text, n=WORDS) -> str:
	parts = str(text or "").split()
	return " ".join(parts[:n]) + ("…" if len(parts) > n else "")


def _date(value):
	try:
		return str(getdate(value)) if value else None
	except Exception:
		return None


def clean(summary) -> dict:
	"""The model's summary in its fixed shape: lines of at most 20 words, a sensitive line only counted, never kept."""
	s = summary if isinstance(summary, dict) else {}
	sensitive = cint(s.get("sensitive"))
	out = {"line": _words(s.get("line"), 30), "to_act_on": [], "updates": [], "reports": [], "facts": []}
	for r in s.get("to_act_on") or []:
		if not isinstance(r, dict) or not (r.get("what") or "").strip():
			continue
		if r.get("sensitive"):
			sensitive += 1
			continue
		out["to_act_on"].append({"who": _words(r.get("who"), 12), "what": _words(r.get("what")), "source": str(r.get("source") or "")[:500],
			"route": r.get("route") if r.get("route") in ROUTES else None, "waiting_on": _words(r.get("waiting_on"), 8) or None,
			"due": _date(r.get("due")), "check_by": _date(r.get("check_by"))})
	for r in s.get("updates") or []:
		if isinstance(r, dict) and (r.get("what") or "").strip() and not r.get("sensitive"):
			out["updates"].append({"what": _words(r["what"]), "source": str(r.get("source") or "")[:500]})
		elif isinstance(r, dict) and r.get("sensitive"):
			sensitive += 1
	for r in s.get("reports") or []:
		if isinstance(r, dict) and (r.get("title") or "").strip() and not r.get("sensitive"):
			out["reports"].append({"title": _words(r["title"], 8), "source": str(r.get("source") or "")[:500]})
		elif isinstance(r, dict) and r.get("sensitive"):
			sensitive += 1
	out["facts"] = [_words(f) for f in (s.get("facts") or [])[:FACTS] if str(f or "").strip()]
	out["sensitive"] = sensitive
	return out


def render_md(s: dict) -> str:
	"""The summary as plain Markdown: for search, the Today card and anything that reads summary_md."""
	lines = [s.get("line") or ""]
	if s.get("to_act_on"):
		lines += ["", f"**To act on · {len(s['to_act_on'])}**"] + [f"- **{r['who']}** {r['what']}" if r.get("who") else f"- {r['what']}" for r in s["to_act_on"]]
	if s.get("updates"):
		lines += ["", f"**Updates · {len(s['updates'])}**"] + [f"- {r['what']}" for r in s["updates"]]
	if s.get("reports"):
		lines += ["", f"**Reports · {len(s['reports'])}**", " · ".join(r["title"] for r in s["reports"])]
	if s.get("facts"):
		lines += ["", "**Key facts**"] + [f"- {f}" for f in s["facts"]]
	if s.get("sensitive"):
		lines += ["", _("{0} sensitive item").format(s["sensitive"]) if s["sensitive"] == 1 else _("{0} sensitive items").format(s["sensitive"])]
	return "\n".join(lines).strip()


def stored(item) -> dict | None:
	raw = item.get("summary_json")
	try:
		return json.loads(raw) if raw else None
	except ValueError:
		return None


def _save(item_name, summary):
	frappe.db.set_value("Life Inbox Item", item_name, {"summary_json": json.dumps(summary, ensure_ascii=False), "summary_md": render_md(summary)}, update_modified=False)


# ---- where the review is, and who the line is waiting on ----
def next_review_date() -> str:
	"""The next weekly review day after today."""
	day = frappe.db.get_single_value("Life Settings", "weekly_review_day") or "Sunday"
	now = getdate(today())
	return str(add_days(now, (DAYS.index(day) - now.weekday()) % 7 or 7))


def _person(name):
	if not name:
		return None
	rows = frappe.get_all("Life Person", filters={"full_name": name}, pluck="name", limit=1)  # system: names the owner's own people, to link a waiting task
	return rows[0] if rows else None


def route_rule(item):
	"""A Route rule for this capture's sender: "Plate" or "Waiting", or None. Rules come before the model."""
	f = rules.facts(item)
	for rule in rules.rules_of(item.space):
		if rule.action == "Route" and rule.asks_to in ("Plate", "Waiting") and rules.matches(rule, f):
			return rule
	return None


def _default_route(item, line) -> str:
	rule = route_rule(item)
	if rule:
		rules.used(rule)
		return rule.asks_to.lower()
	return line.get("route") or "waiting"  # when unsure, the pile


def _make_task(item, line, route) -> str:
	values = {"doctype": "Life Task", "space": item.space, "title": (f"{line['who']}: {line['what']}" if line.get("who") else line["what"])[:140], "inbox_item": item.name,
		"area": item.get("area"), "goal": item.get("goal"), "notes_md": _("From “{0}”.").format(item.title)}
	if str(line.get("source") or "").startswith("http"):
		values["source_url"] = line["source"][:140]
	if route == "plate":
		values.update(status="Open", due_date=line.get("due") or today())
	else:
		who = line.get("waiting_on") or line.get("who") or _("someone")
		values.update(status="Waiting", waiting_on=who, waiting_on_person=_person(who), check_by=line.get("check_by") or next_review_date(), due_date=line.get("due"))
	return frappe.get_doc(values).insert(ignore_permissions=True).name  # system: the Brain files the asks of a capture on the owner's plate or in his waiting pile


def route_lines(item, summary: dict) -> dict:
	"""Make a task for each To act on line that has none; the line keeps its task and where it went. Nothing needs a click."""
	for line in summary.get("to_act_on", []):
		if line.get("task") and frappe.db.exists("Life Task", line["task"]):
			continue
		line["route"] = _default_route(item, line)
		line["task"] = _make_task(item, line, line["route"])
	return summary


def apply(item, raw) -> dict:
	"""Clean the model's summary, make the tasks of its To act on lines, and store both the data and its Markdown."""
	summary = route_lines(item, clean(raw))
	_save(item.name, summary)
	return summary


# ---- the owner changes a line ----
def _line(item_name, index):
	doc = permissions.get_doc_checked("Life Inbox Item", item_name, "write")
	summary = stored(doc)
	lines = (summary or {}).get("to_act_on") or []
	if not 0 <= cint(index) < len(lines):
		frappe.throw(_("There is no such line."), title=_("Line not found"))
	return doc, summary, lines[cint(index)]


def change(item: str, index: int, to: str, waiting_on: str | None = None) -> dict:
	"""Move one To act on line: to the plate, the waiting pile (with who), the calendar, or not needed."""
	if to not in MOVES:
		frappe.throw(_("Choose Your plate, Waiting on, Add to calendar or Not needed."), title=_("Choice is not valid"))
	doc, summary, line = _line(item, index)
	task = permissions.get_doc_checked("Life Task", line["task"], "write") if line.get("task") and frappe.db.exists("Life Task", line["task"]) else None
	before = line.get("route")
	if to == "plate":
		if task:
			task.update({"status": "Open", "waiting_on": None, "waiting_on_person": None, "check_by": None, "due_date": task.due_date or today()})
			task.save()
		line["route"] = "plate"
	elif to == "waiting":
		who = (waiting_on or line.get("waiting_on") or line.get("who") or _("someone")).strip()
		if task:
			task.update({"status": "Waiting", "waiting_on": who, "waiting_on_person": _person(who), "check_by": task.check_by or next_review_date()})
			task.save()
		line.update(route="waiting", waiting_on=who)
	elif to == "calendar":
		start = line.get("due") or add_days(today(), 1)
		frappe.get_attr("lifeos.api.calendar.add_event")(space=doc.space, subject=(task.title if task else line["what"]), starts_on=f"{start} 09:00:00", all_day=1)
		if task:
			task.status = "Dropped"
			task.save()
		line["route"] = "calendar"
	else:
		if task:
			task.status = "Dropped"
			task.save()
		line["route"] = "not_needed"
	if to in ROUTES and before in ROUTES and before != to:
		line.update(moved=to, moved_on=str(now_datetime()))
		_save(doc.name, summary)
		learn_route(doc, to)
	else:
		_save(doc.name, summary)
	return {"summary": summary, "task": line.get("task")}


def _moves(space, sender, to, since=None) -> int:
	n = 0
	for raw in frappe.get_all("Life Inbox Item", filters={"space": space, "sender": sender, "is_sensitive": 0, "summary_json": ("like", f'%"moved": "{to}"%')},  # system: the owner's own moves, counted for a rule
			pluck="summary_json", limit=30):
		for line in (json.loads(raw) or {}).get("to_act_on", []):
			if line.get("moved") == to and (not since or str(line.get("moved_on") or "") >= str(since)):
				n += 1
	return n


def learn_route(item, to):
	"""The same move twice for one sender makes a Route rule: this sender's asks go to the plate (or the pile). A rule that is there is
	flipped only by two moves the other way made after it. Nothing of a sensitive capture is learnt."""
	sender = (item.get("sender") or "").strip().lower()
	if not sender or item.get("is_sensitive") or item.get("vault_document") or frappe.session.user == permissions.BRAIN_USER:
		return None
	existing = frappe.get_all("Life Rule", filters={"space": item.space, "action": "Route", "sender": sender}, fields=["name", "asks_to", "creation"], limit=1)  # system: the owner's space rules
	since = existing[0].creation if existing else None
	if _moves(item.space, sender, to, since) < rules.SAME_CORRECTION:
		return None
	asks = to.capitalize()
	if existing:
		if existing[0].asks_to == asks:
			return None
		frappe.db.set_value("Life Rule", existing[0].name, {"asks_to": asks, "creation": now_datetime()}, update_modified=False)
		return existing[0].name
	return frappe.get_doc({"doctype": "Life Rule", "space": item.space, "made_by": "Brain", "enabled": 1, "action": "Route", "asks_to": asks, "sender": sender,
		"learned_from": item.name}).insert(ignore_permissions=True).name  # system: the Brain makes the rule from the owner's own moves


# ---- the waiting pile ----
def waiting_rows(space) -> list:
	"""Open waiting tasks, grouped by person by the caller, oldest first, each with since, source and whether it is past its check-by."""
	rows = frappe.get_list("Life Task", filters={"space": space, "status": "Waiting", "is_archived": 0},
		fields=["name", "title", "waiting_on", "waiting_on_person", "check_by", "creation", "inbox_item"], order_by="creation asc", limit=200)
	titles = {r.name: r.title for r in frappe.get_all("Life Inbox Item", filters={"name": ("in", [r.inbox_item for r in rows if r.inbox_item] or [""])}, fields=["name", "title"])}  # system: titles of items the tasks came from
	now = getdate(today())
	return [{"name": r.name, "title": r.title, "who": r.waiting_on or _("Someone"), "since": str(r.creation)[:10], "from": titles.get(r.inbox_item),
		"item": r.inbox_item, "check_by": str(r.check_by) if r.check_by else None, "past": bool(r.check_by and getdate(r.check_by) < now)} for r in rows]


def past_check(space) -> dict:
	"""The one line Today may show about the waiting pile: how many are past their check-by date, and whose."""
	rows = [r for r in waiting_rows(space) if r["past"]]
	names = list(dict.fromkeys(r["who"] for r in rows))
	return {"count": len(rows), "names": names[:4]}


def waiting_change(task: str, to: str) -> dict:
	"""Weekly review › Waiting on others: Done, Move to my plate, Still waiting (check-by a week on) or Not needed."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	if doc.status != "Waiting":
		frappe.throw(_("{0} is not waiting any more.").format(doc.title), title=_("Task is not waiting"))
	item = frappe.get_doc("Life Inbox Item", doc.inbox_item) if doc.inbox_item and frappe.db.exists("Life Inbox Item", doc.inbox_item) else None
	if to == "done":
		doc.status = "Done"
	elif to == "plate":
		doc.update({"status": "Open", "waiting_on": None, "waiting_on_person": None, "check_by": None, "due_date": doc.due_date or today()})
	elif to == "still":
		doc.check_by = add_days(max(getdate(doc.check_by or today()), getdate(today())), 7)
	elif to == "not_needed":
		doc.status = "Dropped"
	else:
		frappe.throw(_("Choose Done, Move to my plate, Still waiting or Not needed."), title=_("Choice is not valid"))
	doc.save()
	if to in ("plate", "not_needed") and item:
		_mark_line(item, doc.name, "plate" if to == "plate" else "not_needed")
	return {"task": doc.name, "status": doc.status, "check_by": str(doc.check_by) if doc.check_by else None}


def _mark_line(item, task, to):
	"""Keep the item's summary in step when its task is moved elsewhere, and learn from a move to the plate."""
	summary = stored(item)
	for line in (summary or {}).get("to_act_on", []):
		if line.get("task") == task:
			line["route"] = to
			if to == "plate":
				line.update(moved="plate", moved_on=str(now_datetime()))
			_save(item.name, summary)
			if to == "plate":
				learn_route(item, "plate")
			return


def nudge(task: str) -> dict:
	"""The two-line follow-up the owner may send himself. It is a draft: Life OS never sends on its own."""
	doc = permissions.get_doc_checked("Life Task", task, "read")
	who = (doc.waiting_on or "").split(" (")[0] or "there"
	since = str(doc.creation)[:10]
	text = _("Hi {0}, a quick nudge on this: {1}. It has been open since {2}. Could you let me know where it stands?").format(who.split(" ")[0], doc.title, since)
	return {"text": text, "to": who}


# ---- a reply that says it is done ----
def waiting_for(item) -> list:
	"""The open waiting tasks the Brain may close from this capture: those of the same sender or the same thread. They are given to the model."""
	sender = (item.get("sender") or "").strip().lower()
	thread = item.get("external_id")
	rows = []
	for t in frappe.get_all("Life Task", filters={"space": item.space, "status": "Waiting", "is_archived": 0}, fields=["name", "title", "waiting_on", "inbox_item"], limit=50):  # system: the owner's own waiting pile
		origin = frappe.db.get_value("Life Inbox Item", t.inbox_item, ["sender", "external_id"], as_dict=True) if t.inbox_item else None
		if origin and t.inbox_item != item.name and ((thread and origin.external_id == thread) or (sender and (origin.sender or "").lower() == sender)):
			rows.append({"task": t.name, "title": t.title, "waiting_on": t.waiting_on})
	return rows


def close_waiting(item, closes) -> list:
	"""Mark Done the waiting tasks the model says this capture settles. Only tasks it was offered count. Each says which item closed it, so
	Activity lists it and the weekly review shows it under "Closed by itself" with Change."""
	offered = {r["task"] for r in waiting_for(item)}
	done = []
	for c in closes or []:
		name = c.get("task") if isinstance(c, dict) else None
		if name in offered and frappe.db.get_value("Life Task", name, "status") == "Waiting":
			frappe.db.set_value("Life Task", name, {"status": "Done", "completed_on": today(), "closed_by_brain": 1, "closed_by_item": item.name})
			done.append(name)
	return done


def closed_by_itself(space, since) -> list:
	rows = frappe.get_all("Life Task", filters={"space": space, "closed_by_brain": 1, "completed_on": (">=", since)},  # system: the owner's own tasks the Brain closed
		fields=["name", "title", "waiting_on", "completed_on", "closed_by_item", "status"], order_by="completed_on desc", limit=50)
	return [{**r, "completed_on": str(r.completed_on)} for r in rows]


def reopen(task: str) -> dict:
	"""Change on a task the Brain closed by itself: it goes back to the waiting pile."""
	doc = permissions.get_doc_checked("Life Task", task, "write")
	doc.update({"status": "Waiting", "completed_on": None, "closed_by_brain": 0, "closed_by_item": None, "check_by": next_review_date()})
	doc.save()
	return {"task": doc.name, "status": doc.status}
