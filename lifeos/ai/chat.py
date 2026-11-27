"""Chat on Flow (issue 119): Life OS's own chat screen over Flow's engine.

`start` checks the monthly cap, creates or continues the thread's Flow Session, puts the space, scope and current record in front of the
question and starts a run of the "Life OS" agent. The agent's tools are `lifeos.ai.flow` (Life OS's own tools, with the space, Vault and
scope checks). The screen polls `progress`, which reads the run from the Flow Run and its transcript. `run_done` writes `Life AI Usage`
when a run ends. Nothing here calls a model or writes a prompt: the loop, the model and the key are Flow's.
"""
import json
import re

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from lifeos.ai import client
from lifeos.ai.cite import cite

AGENT = "lifeos/Life OS"
PURPOSE = "Chat"
QUESTION = "\n\nQuestion: "
WORKING = ("Running", "Paused")


def ready() -> bool:
	"""Chat has an agent to run: a model is set up in Flow (Settings › Advanced › AI links there)."""
	from lifeos.ai import flow

	return bool(flow.agents())


def ensure_agent():
	"""The "Life OS" agent exists and uses a model that is still there (it is written after migrate, so a model added since needs it written again)."""
	from lifeos.ai import flow

	want = flow.agents()
	if not want:
		return None
	have = frappe.db.get_value("Flow Agent", AGENT, ["model", "enabled"], as_dict=True)
	if not have or not have.enabled or have.model != want[0].model:
		from frappe.flow.doctype.flow_skill.flow_skill import sync_skills
		from frappe.flow.lib.agent import sync_agents, sync_tools

		sync_skills()
		sync_tools()
		sync_agents()
	return AGENT


def give_flow_role(user: str):
	"""Flow lets only a Flow User chat. The role comes with the first chat."""
	if "Flow User" in frappe.get_roles(user):
		return
	doc = frappe.get_doc("User", user)
	doc.flags.ignore_permissions = True  # system: the first chat gives the person the role Flow needs; they may not edit users
	doc.add_roles("Flow User")
	frappe.clear_cache(user=user)


def context_text(space: str, scope: dict | None, record: dict | None) -> str:
	"""What the model is told before the question: today, the scope, and the record the owner has open."""
	lines = [f"Today: {today()}", f"Scope: {(scope or {}).get('label') or 'Everything in this space'}"]
	if record and record.get("doctype") and record.get("name"):
		dt, name = record["doctype"], record["name"]
		title = frappe.db.get_value(dt, name, "subject" if dt == "Event" else (frappe.get_meta(dt).title_field or "name")) or name
		lines.append(f"The owner has this open: {dt.replace('Life ', '')} “{title}” ({dt} {name}). When they say “this” or “it”, they mean this record. "
			+ ("Its time is " + str(frappe.db.get_value(dt, name, "starts_on"))[:16] + ". " if dt == "Event" else "Read it with get_record before answering about it. ")
			+ "To add a note to it, call add_note with this doctype and name.")
	return "\n".join(lines)


def start(thread, text: str, scope: dict | None, record: dict | None = None, filed: dict | None = None):
	"""Send `text` in the thread's Flow Session (made on the first message). Returns the Flow Run. `filed` is what was done with the files that came with it
	(`lifeos.ai.chat_files.process`): the model is told in `block`, and the answer lists `lines` and asks `pending`."""
	from frappe.flow.lib.session import new_session

	give_flow_role(thread.user)
	agent = ensure_agent()
	if not thread.flow_session:
		session = new_session(agent, title=thread.title)
		thread.db_set("flow_session", session.name)
	session = frappe.get_doc("Flow Session", thread.flow_session)
	body = context_text(thread.space, scope, record) + (f"\n\n{filed['block']}" if filed and filed.get("block") else "") + QUESTION + text
	run = session.chat(body, on_complete="lifeos.ai.chat.run_done", reference_doctype="Life Ask Thread", reference_name=thread.name)
	if filed and (filed.get("lines") or filed.get("pending")):
		save_filed(thread, run.name, {"lines": filed["lines"], "pending": filed["pending"]})
	thread.db_set("last_message_on", now_datetime())
	return run


def asked_text(run_input: str) -> str:
	"""The owner's own words in a run's input."""
	return (run_input or "").split(QUESTION, 1)[-1].strip()


def filed_of(thread) -> dict:
	return frappe.parse_json(thread.filed) if thread.get("filed") else {}


def save_filed(thread, run: str, data: dict):
	all_ = filed_of(thread)
	all_[run] = data
	thread.db_set("filed", json.dumps(all_, default=str), update_modified=False)


def run_done(run):
	"""A run ended (Flow calls this, and `progress` does once it sees it ended): its usage goes to Life AI Usage, once."""
	if frappe.db.exists("Life AI Usage", {"reference_doctype": "Flow Run", "reference_name": run.name}):
		return
	usage = frappe.parse_json(run.usage) if run.usage else {}
	if not usage:
		return
	thread = frappe.db.get_value("Life Ask Thread", {"flow_session": run.session}, ["name", "space", "user"], as_dict=True)
	model = frappe.db.get_value("Flow Session", run.session, "model") or frappe.db.get_value("Flow Agent", AGENT, "model")
	inp, out = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
	cached, wrote = int(usage.get("cache_read_tokens") or 0), int(usage.get("cache_write_tokens") or 0)
	cost = flt(usage.get("cost")) or client.cost_of(model, inp, out, cached, wrote)
	frappe.get_doc({"doctype": "Life AI Usage", "user": (thread or {}).get("user") or frappe.db.get_value("Flow Session", run.session, "owner"), "month": client.month(),
		"model": model, "input_tokens": inp, "output_tokens": out, "cached_tokens": cached, "cache_write_tokens": wrote, "cost": cost, "purpose": PURPOSE,
		"space": (thread or {}).get("space"), "reference_doctype": "Flow Run", "reference_name": run.name}).insert(ignore_permissions=True)  # system: the cost log is written for whoever chatted, who may not write Life AI Usage


# ---- the thread as the screen shows it ----

def refs_of(thread) -> dict:
	return frappe.parse_json(thread.refs) if thread.refs else {}


def _tool_results(run: str, session: str):
	"""The result of every tool call in the run, in order."""
	rows = frappe.get_all("Flow Session Message", filters={"parent": session, "parenttype": "Flow Session", "run": run, "role": "tool"}, fields=["content"], order_by="idx asc")
	for r in rows:
		try:
			out = json.loads(r.content or "")
		except ValueError:
			continue
		if isinstance(out, dict):
			yield out


def _done_lines(run: str, session: str) -> list[dict]:
	"""What the answer did: the `done_list` of every tool result in the run, in order."""
	return [dict(d) for out in _tool_results(run, session) for d in out.get("done_list") or []]


def _drafts(run: str, session: str) -> list[dict]:
	"""The messages the answer drafted, as they are now (issue 150): each once, with its status; a dropped draft is gone."""
	from lifeos.tools import messages

	names = list(dict.fromkeys(n for out in _tool_results(run, session) for n in out.get("draft_list") or []))
	cards = []
	for n in names:
		try:
			cards.append(messages.card(n))
		except (frappe.ValidationError, frappe.DoesNotExistError):
			frappe.clear_messages()  # dropped, or not this user's
	return cards


def _status(run) -> str:
	return "Working" if run.status in WORKING else ("Done" if run.status == "Completed" else "Error")


# What an answer never shows (issue 140): a link is kept as it is; a bracketed note `[word: …]` and a bare record ID (10 lowercase letters and digits, with both) are removed.
INTERNAL = re.compile(r"(?P<link>\[[^\]]*\]\([^)]*\))|(?P<note>\s*\[[A-Za-z_]+:[^\]]*\])|(?P<id>(?<![\w/#=.-])(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{10}(?![\w/-]))")
NOTE_TITLE = "Chat answer had an internal note"


def strip_internal(text: str, run: str | None = None) -> str:
	"""The answer without internal notes or record IDs. This is a safety net; the skill is the fix. Logs once per run."""
	found = []

	def sub(m):
		if m.group("link"):
			return m.group(0)
		found.append(m.group(0).strip())
		return ""

	out = INTERNAL.sub(sub, text or "")
	if not found:
		return text
	out = re.sub(r"[ \t]{2,}", " ", out)
	out = re.sub(r"[ \t]+([.,;:!?])", r"\1", out)
	if run and not frappe.db.exists("Error Log", {"reference_doctype": "Flow Run", "reference_name": run, "method": NOTE_TITLE}):
		frappe.log_error(title=NOTE_TITLE, message="\n".join(found), reference_doctype="Flow Run", reference_name=run)
	return out.strip()


def answer_of(thread, run) -> dict:
	"""One run as an answer message: {name, role, text, status, error, cited, done, …}."""
	text, cited = cite(strip_internal(run.output or "", run.name), frappe._dict(refs=refs_of(thread)))
	undone = frappe.parse_json(thread.undone) if thread.undone else {}
	done = _done_lines(run.name, run.session)
	for i, d in enumerate(done):
		d["undone"] = int(bool(undone.get(f"{run.name}:{i}")))
	drafts = _drafts(run.name, run.session)
	filed = filed_of(thread).get(run.name) or {}
	done += [{**d, "undone": 0} for d in filed.get("lines") or []]  # after the tools' own lines, so the numbers Undo uses do not move
	status = _status(run)
	error = run.error if status == "Error" else None
	if status == "Error":
		error = _("The answer could not be written. {0}").format(frappe.utils.strip_html(run.error or "")[:200]).strip()
	if status == "Done" and not text:
		text = _("Done.") if done or filed.get("pending") else _("I could not find that.")
	usage = frappe.parse_json(run.usage) if run.usage else {}
	return {"name": run.name, "thread": thread.name, "role": "assistant", "text": text, "status": status, "error": error, "cited": cited, "actions": [], "done": done, "read": [], "drafts": drafts,
		"questions": [{"index": i, "text": q["text"], "file_name": q["file_name"], "options": q["options"]} for i, q in enumerate(filed.get("pending") or []) if q],
		"cost": flt(usage.get("cost")), "created": str(run.creation)[:19]}


def messages_of(thread) -> list[dict]:
	"""The thread's messages: what was said before Chat ran on Flow (read only), then each run's question and answer."""
	out = []
	for m in frappe.parse_json(thread.transcript) if thread.transcript else []:
		out.append({"name": m.get("id"), "thread": thread.name, "role": m.get("role"), "text": m.get("text") or "", "status": "Done", "error": None, "cited": [], "actions": [], "done": [],
			"read": [], "cost": 0, "created": m.get("at") or ""})
	if thread.flow_session:
		for run in frappe.get_all("Flow Run", filters={"session": thread.flow_session}, fields=["name", "session", "input", "output", "status", "error", "usage", "creation"], order_by="creation asc"):
			out.append({"name": run.name + ":q", "thread": thread.name, "role": "user", "text": asked_text(run.input), "status": "Done", "error": None, "cited": [], "actions": [], "done": [],
				"read": [], "cost": 0, "created": str(run.creation)[:19]})
			out.append(answer_of(thread, run))
	return out


def latest_answer(thread, run_name: str | None = None) -> dict | None:
	"""The answer of a run (the last, by default), fresh from Flow: a run still going is brought up to date first."""
	if not thread.flow_session:
		return None
	run_name = run_name or frappe.db.get_value("Flow Run", {"session": thread.flow_session}, "name", order_by="creation desc")
	if not run_name:
		return None
	if frappe.db.get_value("Flow Run", run_name, "session") != thread.flow_session:
		raise frappe.DoesNotExistError(_("Answer not found."))
	run = frappe.get_doc("Flow Run", run_name)
	if run.status in WORKING:
		from frappe.flow.lib.session import sync_with_retry

		sync_with_retry(frappe.get_doc("Flow Session", thread.flow_session))
		run.reload()
	if run.status not in WORKING:
		run_done(run)
	return answer_of(thread, run)
