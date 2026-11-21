"""Fake models for tests and the acceptance site (UX fixes, set 5). No test calls the real API.

- ScriptedFake: replays scripted responses in order and records every request it was sent (unit tests).
- SiteFake: a small deterministic "model" for the acceptance site (site config lifeos_fake_ai = 1). It searches with the
  question, lists records when the search finds nothing, answers citing what it found, and suggests a Make task. Every
  request it receives is kept in the cache (last 200), so a check can assert what was sent.
"""
import html
import json
import re
from datetime import datetime

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


def asked(params):
	"""(skill, data) of a request made by lifeos.skills.call: the skill's name and the data it was given; ("", {}) for any other request."""
	first = params["messages"][0]["content"]
	first = first if isinstance(first, str) else "".join(b.get("text", "") for b in first if b.get("type") == "text")
	m = re.search(r'<input skill="([\w-]+)">\n(.*)\n</input>', first, re.S)
	try:
		data = json.loads(html.unescape(m.group(2))) if m else {}
	except ValueError:
		data = {}
	return (m.group(1) if m else ""), (data if isinstance(data, dict) else {})


def tool_use(name, args, id=None):
	return {"type": "tool_use", "id": id or f"toolu_{name}_{frappe.generate_hash(length=6)}", "name": name, "input": args}


class SiteFake:
	"""Deterministic answers on the acceptance site, from what the tools return."""

	def run(self, params, on_text=None):
		_record(params)
		if any(t["name"] == "propose" for t in params.get("tools") or []):
			return self._capture(params)
		if (params.get("output_config") or {}).get("format"):
			return self._structured(params)
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

	def _capture(self, params):
		"""process-capture (issue 28): one task named after the capture's title in Career, then a summary."""
		first = params["messages"][0]["content"]
		first = first if isinstance(first, str) else "".join(b.get("text", "") for b in first if b.get("type") == "text")
		title = (re.search(r"<title>(.*?)</title>", first, re.S) or [None, "A capture"])[1].strip()[:100] or "A capture"
		called = any(b.get("type") == "tool_use" for m in params["messages"] if m["role"] == "assistant" for b in m["content"])
		if not called:
			return self._out(params, None, "", [tool_use("propose", {"kind": "Task", "preview": title, "confidence": 0.6, "reason": "The acceptance site's stand-in model files everything under Career.",
				"payload": {"title": title, "area": "Career"}})], "tool_use")
		return self._done(params, None, json.dumps({"transcript_md": "", "summary_md": f"{title}. Read by the acceptance site's stand-in model."}))

	def _structured(self, params):
		"""A skill asked about data (lifeos/skills/call.py): the answer the skill's rules would give, from the data in the request."""
		slug, data = asked(params)
		out = SKILLS.get(slug, lambda d: {})(data)
		text = json.dumps(out)
		return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "model": params["model"], "usage": _usage(params, text)}

	def _out(self, params, on_text, text, tools, stop):
		_stream(on_text, text)
		content = ([{"type": "text", "text": text}] if text else []) + tools
		return {"content": content, "stop_reason": stop, "model": params["model"], "usage": _usage(params, text)}

	def _done(self, params, on_text, text):
		_stream(on_text, text)
		return {"content": [{"type": "text", "text": text}] if text else [], "stop_reason": "end_turn", "model": params["model"],
			"usage": _usage(params, text)}


# ---- the skills that are asked about data, answered by simple rules, so the acceptance site exercises the path deterministically ----

def _words(text):
	return set(re.findall(r"[a-z]{4,}", (text or "").lower()))


def _tidy(data):
	"""Inbox items and tasks: an item with proposals is kept, only notes parked, nothing found dropped; a task untouched 120 days is
	dropped, 60 parked, a waiting one kept. Reset's request gets its three oldest tasks as one group."""
	out = []
	if str(data.get("request", "")).startswith("Reset"):  # the three oldest tasks, as one group
		return {"decisions": [{"item": it["item"], "decision": "park", "reason": "They have waited longest and nothing links them to this week's plan.",
			"group": "Oldest tasks nobody has touched"} for it in (data.get("items") or [])[:3]]}
	for it in data.get("items") or []:
		kinds = it.get("proposals")
		age = it.get("age_days") or 0
		if it.get("kind") in ("Inbox",):
			decision = "drop" if not kinds else "park" if set(kinds) <= {"Note"} else "keep"
		elif it.get("kind") == "Waiting":
			decision = "keep"
		else:
			decision = "drop" if age > 120 else "park" if age > 60 else "keep"
		row = {"item": it["item"], "decision": decision, "reason": f"Sorted by the stand-in model: {decision}.",
			"chase": it.get("kind") == "Waiting" and age > 7}
		out.append(row)
	return {"decisions": out}


def _plan(data):
	"""The next action given, or "Plan the next step for <goal>", 60 minutes (30 for a call); the three goals furthest behind."""
	goals = data.get("goals") or []
	plans = []
	for g in goals:
		action = g.get("next_action") or f"Plan the next step for {g.get('title')}"[:140]
		plans.append({"goal": g["goal"], "next_action": action, "minutes": 30 if "call" in action.lower() else 60})
	stars = [g["goal"] for g in sorted(goals, key=lambda g: g.get("percent") or 0)[:3]]
	return {"plans": plans if data.get("request") == "plans" else [], "stars": stars if data.get("request") == "stars" else []}


def _notice(data):
	"""Insights: a Promise over the first record. Follow-ups: "I will ..." in a linked record. Readings: "<measure> ... <number>"."""
	out = {"insights": [], "follow_ups": [], "readings": []}
	request = data.get("request")
	if request == "insights":
		recs = [r for r in data.get("records") or [] if r.get("ref")]
		if recs:
			out["insights"] = [{"kind": "Promise", "title": f"You said you would follow up on {recs[0]['title'][:80]}. No task covers it.",
				"evidence": [recs[0]["ref"]], "task_title": f"Follow up on {recs[0]['title'][:80]}"}]
	elif request == "follow_ups":
		for m in data.get("meetings") or []:
			for r in m.get("records") or []:
				for said in re.findall(r"\b(?:I will|I'll|I shall)\s+([^.\n]{5,120})", r.get("text") or "", re.I)[:2]:
					out["follow_ups"].append({"meeting": m["meeting"], "kind": "Promise", "title": f"You said you would {said.strip()}.",
						"task_title": said.strip()[:1].upper() + said.strip()[1:], "record": r["record"], "excerpt": said.strip()})
				for day, month in re.findall(r"\b(?:on|by)\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b", r.get("text") or "", re.I)[:1]:
					when = datetime.strptime(f"{int(day)} {month.title()} {frappe.utils.getdate().year}", "%d %B %Y").date()
					out["follow_ups"].append({"meeting": m["meeting"], "kind": "Date", "title": f"{m['title']}: next on {int(day)} {month.title()}.",
						"task_title": f"{m['title']} ({int(day)} {month.title()})", "date": str(when), "record": r["record"], "excerpt": f"{day} {month}"})
	else:
		for g in data.get("goals") or []:
			if not g.get("measure"):
				continue
			pat = re.escape(g["measure"]) + r"[^0-9\n]{0,60}?(\d+(?:\.\d+)?)"
			for r in data.get("records") or []:
				if m := re.search(pat, r.get("text") or "", re.I):
					out["readings"].append({"goal": g["goal"], "value": float(m.group(1)), "record": r.get("ref"), "excerpt": m.group(0)[:200]})
	return out


def _define(data):
	"""A finish line "<title> is done"; a number when the title holds a number and a unit ("Lose 6 kg"); a title from the word most tasks share."""
	if data.get("request") == "title":
		titles = data.get("titles") or []
		seen = {}
		for t in titles:
			for w in _words(t):
				seen[w] = seen.get(w, 0) + 1
		best = max(seen.items(), key=lambda kv: (kv[1], len(kv[0]), kv[0]), default=None)
		return {"kind": "Title", "title": f"Get {best[0].capitalize()} done" if best and best[1] >= 3 else (titles[0] if titles else "New goal")}
	title = (data.get("title") or "").strip()
	m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|km|%|books|hours|days)\b", title, re.I)
	if m:
		return {"kind": "Number", "measure": re.sub(r"\s+", " ", title.replace(m.group(0), "")).strip(" :-,.") or m.group(2), "unit": m.group(2), "target_value": float(m.group(1))}
	return {"kind": "Milestone", "done_when": f"{title} is done"}


def _reflect(data):
	"""A weekday named in the line is counted in the calendar."""
	line = (data.get("line") or "").lower()
	for day, rows in (data.get("events_by_weekday") or {}).items():
		if day.lower() in line:
			calls = sum(1 for t in rows if "call" in t.lower())
			return {"sentence": f"This week {day} had {calls} call{'s' if calls != 1 else ''}."}
	return {"sentence": ""}


def _area(data):
	"""The first part that shares a word with the title or notes, else the first area given, 40% sure."""
	text = _words(f"{data.get('title') or ''} {data.get('notes') or ''}")
	listed = data.get("areas") or []
	pick = next((a for a in listed if a.get("part_of") and text & _words(f"{a['name']} {a.get('description') or ''}")), None) or (listed[0] if listed else {})
	return {"area": pick.get("id") or "", "confidence": 40}


SKILLS = {"tidy-backlog": _tidy, "plan-week": _plan, "notice": _notice, "define-goal": _define, "reflect": _reflect, "guess-area": _area}
