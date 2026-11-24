"""Ask's engine (UX fixes, set 5): one question, answered by the model from tool results only, with citations and
suggested actions. Runs as the asking user; see tools.py for what it may read."""
import json
import time

import frappe
from frappe.utils import now_datetime, today

from lifeos.ai import client
from lifeos.ai.cite import cite
from lifeos.ai.tools import Context, NeedsBackground, ask_call, file_actions, run_tool

MAX_TOOL_CALLS = 8
TOKEN_BUDGET = 80000  # input and output tokens for one question, across its turns
MAX_TURNS = 12
HISTORY = 6  # earlier messages of the thread sent with a follow-up


def system_text():
	"""Ask's instructions: the ask skill (lifeos/skills/ask.md), as the owner has it, so they can read and change what it is told."""
	from lifeos.skills import store

	return store.instructions_of("ask")


def _scope_line(scope):
	label = (scope or {}).get("label") or "Everything in this space"
	return f"Scope: {label}"


def history_messages(thread, upto=None):
	rows = frappe.get_all("Life Ask Message", filters={"thread": thread, "status": "Done"}, fields=["name", "role", "text"],
		order_by="creation desc", limit=HISTORY + 2)
	rows = [r for r in reversed(rows) if r.name != upto]
	out = []
	for r in rows[-HISTORY:]:
		if r.text:
			out.append({"role": r.role, "content": r.text})
	while out and out[0]["role"] != "user":
		out.pop(0)
	# the API wants alternating roles
	clean = []
	for m in out:
		if clean and clean[-1]["role"] == m["role"]:
			clean[-1]["content"] += "\n\n" + m["content"]
		else:
			clean.append(m)
	if clean and clean[-1]["role"] == "user":
		clean.pop()
	return clean


def answer(space, question, scope, history=None, on_text=None, background=False, progress=None):
	"""Run the question: {text, cited, actions, done, read, …}. Over 3 pages of mail it raises `NeedsBackground`, unless `background` (then `progress` is told each page)."""
	ctx = Context(space, scope)
	ctx.background, ctx.progress = background, progress
	max_calls, budget, max_turns = (40, 400000, 45) if background else (MAX_TOOL_CALLS, TOKEN_BUDGET, MAX_TURNS)
	messages = list(history or []) + [{"role": "user", "content": f"{_scope_line(scope)}\nToday: {today()}\n\nQuestion: {question}"}]
	parts, tin, tout, cost, limited = [], 0, 0, 0.0, False
	for _turn in range(max_turns):
		allow = ctx.calls < max_calls and tin + tout < budget
		out = ask_call(ctx, system_text(), question, messages, on_text, space)
		tin, tout, cost, ctx.turn_cost = tin + out["usage"]["input_tokens"], tout + out["usage"]["output_tokens"], cost + out["cost"], out["cost"]  # a mail search is logged with its turn's cost
		content = out["content"]
		text = client.text_of(content)
		if text:
			parts.append(text)
		messages.append({"role": "assistant", "content": content})
		if out["stop_reason"] == "refusal":
			parts = ["The model declined to answer this question."]
			break
		uses = [b for b in content if b.get("type") == "tool_use"]
		if not uses:
			break
		results = []
		for u in uses:
			if not allow and u.get("name") != "suggest_actions":
				res = {"error": "Tool limit reached. Answer now with what you found and say what you did not check."}
				limited = True
			else:
				res = run_tool(ctx, u.get("name"), u.get("input") or {})
			results.append({"type": "tool_result", "tool_use_id": u["id"], "content": json.dumps(res, default=str)[:24000]})
		if ctx.choice:  # the question with choices is the end of the turn: the owner's tap comes back as the next message
			break
		if not (ctx.calls < max_calls and tin + tout < budget):
			limited = True
			results.append({"type": "text", "text": "The tool limit for this question is reached. Answer now with what you found, cite it, and say what was not checked. Do not call more tools."})
		messages.append({"role": "user", "content": results})
		if limited and not allow:
			# one last turn to write the answer; if it still calls tools, stop here
			out = ask_call(ctx, system_text(), question, messages, on_text, space)
			tin, tout, cost = tin + out["usage"]["input_tokens"], tout + out["usage"]["output_tokens"], cost + out["cost"]
			text = client.text_of(out["content"])
			if text:
				parts.append(text)
			break
	text, cited = cite("\n\n".join(p.strip() for p in [*(["_This service does not take tools, so this answer uses search results only._"] if ctx.no_tools else []), *parts] if p.strip()), ctx)
	if limited and "not check" not in text.lower():
		text += "\n\n_I stopped at the limit for one question, so some records were not checked._"
	read = [{"ref": r, **{k: ctx.refs[r][k] for k in ("doctype", "name", "title", "kind", "pane")}} for r in ctx.read]
	return {"text": text or (ctx.choice or {}).get("question") or ("Done." if ctx.done else "I could not find that."), "cited": cited, "actions": [*ctx.actions, *file_actions(ctx)],
		"done": ctx.done, "read": read, "input_tokens": tin,
		"output_tokens": tout, "cost": round(cost, 6), "limited": limited}
