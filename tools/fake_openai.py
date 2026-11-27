"""A fake OpenAI-compatible model for the Flow trial (issue 108): no key, no network.

    python3 tools/fake_openai.py 8765

Chat completions only, streamed or not. With tools offered, the first turn calls the tool whose name ends in
`__list_records` (kind: tasks) or, if the user's message starts with `make task:`, `__make_task`, or, if the question is `add a note: …` with a record open, `__add_note`, or, if it is `mark it done` with a task open, `__finish_task`, or, if it starts "Vivek owes me", "Ask Vivek for" or "Email Vivek for", `__hand_off` (track, draft, send); once a tool result is
in the conversation it answers in words, quoting the result. Used by `docs/FLOW_TRIAL.md`; not part of the app.
"""
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SEEN = []


def reply(body):
	msgs = body.get("messages", [])
	tools = {t["function"]["name"] for t in body.get("tools") or []}
	if msgs and msgs[-1].get("role") == "tool":
		return {"content": "From the tool: " + str(msgs[-1].get("content"))[:600], "tool_calls": None}
	last = next((m for m in reversed(msgs) if m.get("role") == "user"), {})
	text = last.get("content") if isinstance(last.get("content"), str) else json.dumps(last.get("content"))
	pick = lambda suffix: next((t for t in sorted(tools) if t.endswith(suffix)), None)
	question = text.split("Question:", 1)[-1].strip()
	opened = re.search(r"\((Event|Life [A-Za-z]+) ([^)\s]+)\)", text)
	if question.lower().startswith("add a note:") and opened and pick("__add_note"):  # issue 120: a note on the record the owner has open
		call = (pick("__add_note"), {"text": question.split(":", 1)[1].strip(), "doctype": opened.group(1), "name": opened.group(2)})
	elif question.lower().startswith("mark it done") and opened and opened.group(1) == "Life Task" and pick("__finish_task"):  # issue 149: Done on the task the owner has open
		call = (pick("__finish_task"), {"task": opened.group(2)})
	elif re.match(r"(vivek owes me|ask vivek for|email vivek for) ", question.lower()) and pick("__hand_off"):  # issue 130: the three ways to hand off
		how = "track" if question.lower().startswith("vivek owes") else "send" if "send it" in question.lower() else "draft"
		call = (pick("__hand_off"), {"person": "Vivek I130", "what": "the ITR draft", "check_by": "friday", "how": how, "channel": "email"})
	elif text.lower().startswith("make task:") and pick("__make_task"):
		call = (pick("__make_task"), {"title": text.split(":", 1)[1].strip()})
	elif pick("__list_records"):
		call = (pick("__list_records"), {"kind": "tasks"})
	else:
		return {"content": "I have no tools. You said: " + (text or "")[:200], "tool_calls": None}
	return {"content": None, "tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": call[0], "arguments": json.dumps(call[1])}}]}


class Handler(BaseHTTPRequestHandler):
	def log_message(self, *a):
		pass

	def do_GET(self):
		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(json.dumps({"data": [{"id": "fake-1", "object": "model"}]}).encode())

	def do_POST(self):
		body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
		SEEN.append({"messages": body.get("messages"), "tools": [t["function"]["name"] for t in body.get("tools") or []]})
		r = reply(body)
		usage = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
		msg = {"role": "assistant", "content": r["content"]}
		if r["tool_calls"]:
			msg["tool_calls"] = [{k: v for k, v in c.items() if k != "index"} for c in r["tool_calls"]]
		finish = "tool_calls" if r["tool_calls"] else "stop"
		base = {"id": "chatcmpl-fake", "object": "chat.completion", "created": int(time.time()), "model": body.get("model", "fake-1")}
		if not body.get("stream"):
			out = json.dumps({**base, "choices": [{"index": 0, "message": msg, "finish_reason": finish}], "usage": usage}).encode()
			self.send_response(200)
			self.send_header("Content-Type", "application/json")
			self.send_header("Content-Length", str(len(out)))
			self.end_headers()
			self.wfile.write(out)
			return
		self.send_response(200)
		self.send_header("Content-Type", "text/event-stream")
		self.end_headers()
		delta = {"role": "assistant"}
		if r["content"] is not None:
			delta["content"] = r["content"]
		if r["tool_calls"]:
			delta["tool_calls"] = r["tool_calls"]
		chunks = [{**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
			{**base, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
			{**base, "object": "chat.completion.chunk", "choices": [], "usage": usage}]
		for c in chunks:
			self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
		self.wfile.write(b"data: [DONE]\n\n")


if __name__ == "__main__":
	ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), Handler).serve_forever()
