"""Fake models for tests and the acceptance site (UX fixes, set 5). No test calls the real API.

- ScriptedFake: replays scripted responses in order and records every request it was sent (unit tests).
- SiteFake: a small deterministic "model" for the acceptance site (site config lifeos_fake_ai = 1). It searches with the
  question, lists records when the search finds nothing, answers citing what it found, and suggests a Make task. Every
  request it receives is kept in the cache (last 200), so a check can assert what was sent.
"""
import json
import re

import frappe

CACHE_KEY = "lifeos_fake_ai_received"


def _record(params):
	try:
		frappe.cache.rpush(CACHE_KEY, json.dumps({"model": params.get("model"), "system": params.get("system"),
			"messages": params.get("messages"), "tools": [t["name"] for t in params.get("tools") or []]}, default=str))
		frappe.cache.ltrim(CACHE_KEY, -200, -1)
	except Exception:
		pass


def received():
	return [json.loads(x) for x in (frappe.cache.lrange(CACHE_KEY, 0, -1) or [])]


def clear_received():
	frappe.cache.delete(CACHE_KEY)


def _usage(params, text):
	return {"input_tokens": max(len(json.dumps(params.get("messages"), default=str)) // 4, 1), "output_tokens": max(len(text) // 4, 1)}


def _stream(on_text, text):
	if on_text:
		for part in re.findall(r"\S+\s*", text):
			on_text(part)


class ScriptedFake:
	"""responses: a list of dicts {content: [blocks], stop_reason}, or of callables (params) -> dict."""

	def __init__(self, responses):
		self.responses = list(responses)
		self.received = []

	def run(self, params, on_text=None):
		self.received.append(json.loads(json.dumps(params, default=str)))
		_record(params)
		r = self.responses.pop(0) if self.responses else {"content": [{"type": "text", "text": "I could not find that."}], "stop_reason": "end_turn"}
		if callable(r):
			r = r(params)
		text = "".join(b.get("text", "") for b in r["content"] if b.get("type") == "text")
		_stream(on_text, text)
		return {"content": r["content"], "stop_reason": r.get("stop_reason", "end_turn"), "model": params["model"],
			"usage": r.get("usage") or _usage(params, text)}


def tool_use(name, args, id=None):
	return {"type": "tool_use", "id": id or f"toolu_{name}_{frappe.generate_hash(length=6)}", "name": name, "input": args}


class SiteFake:
	"""Deterministic answers on the acceptance site, from what the tools return."""

	def run(self, params, on_text=None):
		_record(params)
		msgs = params["messages"]
		last = msgs[-1]
		results = []  # every tool result since the question
		for m in reversed(msgs):
			if m["role"] == "user" and isinstance(m["content"], str):
				question = m["content"]
				break
			if m["role"] == "user":
				for b in m["content"]:
					if b.get("type") == "tool_result":
						try:
							results.append(json.loads(b.get("content") or "{}"))
						except ValueError:
							pass
		else:
			question = ""
		q = question.split("Question:", 1)[-1].strip()
		called = sum(1 for m in msgs if m["role"] == "assistant" for b in (m["content"] if isinstance(m["content"], list) else []) if b.get("type") == "tool_use")
		refs = []
		for res in reversed(results):
			for row in (res.get("results") or res.get("rows") or []):
				if row.get("ref") and row["ref"] not in [r[0] for r in refs]:
					refs.append((row["ref"], row.get("title") or ""))
			if res.get("ref") and res["ref"] not in [r[0] for r in refs]:
				refs.append((res["ref"], res.get("title") or ""))
		suggested = any(b.get("type") == "tool_use" and b.get("name") == "suggest_actions" for m in msgs if m["role"] == "assistant"
			for b in (m["content"] if isinstance(m["content"], list) else []))
		if not params.get("tools") or suggested:
			return self._done(params, on_text, "" if suggested else "I could not check more than this.")
		if called == 0:
			return self._out(params, on_text, "", [tool_use("search", {"query": q})], "tool_use")
		if called == 1 and not refs:
			return self._out(params, on_text, "", [tool_use("list_records", {"kind": "tasks", "filters": {"status": "open"}, "limit": 10})], "tool_use")
		if not refs:
			return self._done(params, on_text, "I could not find that in your records.")
		lines = [f"- {title} [{r}]" for r, title in refs[:3]]
		text = "Here is what I found in your records.\n\n" + "\n".join(lines) + "\n"
		first = refs[0]
		act = tool_use("suggest_actions", {"actions": [{"kind": "make_task", "label": f"Make task: follow up {first[1][:40]}",
			"title": f"Follow up: {first[1][:100]}", "area_ref": first[0]}]})
		return self._out(params, on_text, text, [act], "tool_use")

	def _out(self, params, on_text, text, tools, stop):
		_stream(on_text, text)
		content = ([{"type": "text", "text": text}] if text else []) + tools
		return {"content": content, "stop_reason": stop, "model": params["model"], "usage": _usage(params, text)}

	def _done(self, params, on_text, text):
		_stream(on_text, text)
		return {"content": [{"type": "text", "text": text}] if text else [], "stop_reason": "end_turn", "model": params["model"],
			"usage": _usage(params, text)}
