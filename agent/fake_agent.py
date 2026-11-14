#!/usr/bin/env python3
"""A test agent for Life OS. It uses the same API methods a real agent would and returns canned results,
so the inbox pipeline can be tested with no model.

    export LIFEOS_URL=http://localhost:18000
    export LIFEOS_API_KEY=...  LIFEOS_API_SECRET=...
    python3 agent/fake_agent.py            # claim and process every New item, then stop
    python3 agent/fake_agent.py --loop     # keep polling every 5 minutes
    python3 agent/fake_agent.py --fail     # report a failure for the next item instead

Only the Python standard library is needed. Credentials are read from the environment and never printed.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic")
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac")


class HttpClient:
	"""Calls whitelisted methods over HTTP with an API key."""

	def __init__(self, url, key, secret):
		self.url = url.rstrip("/")
		self.auth = f"token {key}:{secret}"

	def call(self, method, **args):
		req = urllib.request.Request(
			f"{self.url}/api/method/lifeos.api.{method}", data=json.dumps(args).encode(),
			headers={"Authorization": self.auth, "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
		try:
			with urllib.request.urlopen(req, timeout=60) as res:
				return json.loads(res.read().decode()).get("message")
		except urllib.error.HTTPError as e:
			body = e.read().decode(errors="replace")[:400]
			raise RuntimeError(f"{method} failed with HTTP {e.code}: {body}") from None

	def download(self, file_url):
		"""Fetch a private file with the agent's own credentials. Returns its bytes."""
		req = urllib.request.Request(self.url + urllib.parse.quote(file_url), headers={"Authorization": self.auth})
		with urllib.request.urlopen(req, timeout=120) as res:
			return res.read()


def _area(context, *names):
	"""Reuse an existing area. Returns the first of `names` the space has, else None."""
	have = {a["area_name"] for a in context.get("areas", [])}
	return next((n for n in names if n in have), None)


def _goal(context, title):
	return next((g for g in context.get("goals", []) if g["title"] == title), None)


def _with(d, **optional):
	d.update({k: v for k, v in optional.items() if v})
	return d


def canned_journal(item, context, today):
	transcript = (
		"**Goal Oct to Dec** · Actions · Week 1 to 12\n\n"
		"**Money.** Meet Arjun Singh for PMS. Complete usable MoneyOS.\n\n"
		"**RMT, GHL turnaround.** Discuss going with Nowrojee. Make detailed plan for poor sections. Visit leased gardens. Start internal audit.\n\n"
		"**Close open loops.** Ruchi ITR. Driver's licence. ~~Anya passport~~. Generic promotion [?]\n"
	)
	summary = ("The 12 Week Year plan for October to December. Seven goals with their actions. "
		"One action, Anya passport, is struck through as done.")
	money, loops = _goal(context, "Money"), _goal(context, "Close open loops")
	proposals = [
		{"kind": "Task", "preview": "Meet Arjun Singh for PMS", "confidence": 0.92,
			"payload": _with({"title": "Meet Arjun Singh for PMS"}, area=_area(context, "Money & Legal", "Money"), goal=money and money["name"])},
		{"kind": "Task", "preview": "Visit leased gardens", "confidence": 0.88,
			"payload": _with({"title": "Visit leased gardens"}, area=_area(context, "Tea & Coffee", "Tea", "Work"))},
	]
	if loops and any(a["title"] == "Anya passport" for a in loops["actions"]):
		proposals.append({"kind": "Week Tick", "preview": 'Mark "Anya passport" as done in the 12 Week Year', "confidence": 0.95,
			"payload": {"goal": loops["name"], "action": "Anya passport", "mark_done": True}})
	else:
		proposals.append({"kind": "Task", "preview": "Ruchi ITR", "confidence": 0.9,
			"payload": _with({"title": "Ruchi ITR"}, area=_area(context, "Money & Legal", "Money"))})
	proposals += [
		{"kind": "Task", "preview": "Generic promotion [?]", "confidence": 0.41,
			"payload": _with({"title": "Generic promotion [?]", "notes_md": "The agent could not read this line. Edit the title or reject it."},
				area=_area(context, "Personal", "Personal & Health"))},
		{"kind": "Journal Page", "preview": "Save pages 187 to 188 with this transcript", "confidence": 0.97,
			"payload": {"page_date": today, "page_number": "187-188", "transcript_md": transcript}},
	]
	return transcript, summary, proposals


def canned_document(item, context, today):
	summary = (f"**{item['title']}** summarised. The document lists three follow-ups, extracted below as to-dos. "
		"No dates were stated, so none were set.")
	area = _area(context, "Tea & Coffee", "Business That Works", "Work", "Tea")
	titles = ["Review the production figures with Mithun", "Send six questions on the blend sheets", "Confirm the despatch schedule"]
	proposals = [{"kind": "Task", "preview": t, "confidence": c, "payload": _with({"title": t}, area=area)}
		for t, c in zip(titles, (0.9, 0.84, 0.77))]
	return None, summary, proposals


def canned_voice(item, context, today):
	transcript = ("Note to self. Call Vivek about the ITR papers this week. Also the estate training programme needs an outline, "
		"start with supervisors and field staff [?].")
	summary = "A voice note with one to-do and one idea for the training programme."
	proposals = [
		{"kind": "Task", "preview": "Call Vivek about the ITR papers", "confidence": 0.9,
			"payload": _with({"title": "Call Vivek about the ITR papers"}, area=_area(context, "Money & Legal", "Money"))},
		{"kind": "Note", "preview": "Estate training programme: first outline", "confidence": 0.7,
			"payload": _with({"title": "Estate training programme: first outline",
				"content_md": "Start with supervisors and field staff [?].\n\nFrom a voice note."}, area=_area(context, "Tea & Coffee", "Tea", "Work"))},
	]
	return transcript, summary, proposals


def canned_text(item, context, today):
	text = (item.get("raw_text") or "").strip()
	summary = "Summary: " + (text[:280] + ("…" if len(text) > 280 else "") if text else f"{item['title']} was received with no text.")
	proposals = [{"kind": "Note", "preview": item["title"], "confidence": 0.6,
		"payload": _with({"title": item["title"], "content_md": text or summary}, area=_area(context, "Personal", "Personal & Health", "Work"))}]
	return None, summary, proposals


def canned_result(item, context, today):
	names = [f["file_name"].lower() for f in item.get("files", [])]
	instruction = (item.get("instruction") or "").lower()
	if item.get("source_type") == "Journal Photo" or "journal" in instruction or (names and all(n.endswith(IMAGE_EXT) for n in names)):
		return canned_journal(item, context, today)
	if item.get("source_type") == "Voice Note" or any(n.endswith(AUDIO_EXT) for n in names):
		return canned_voice(item, context, today)
	if any(n.endswith(".pdf") for n in names) or "to-do" in instruction or "todo" in instruction:
		return canned_document(item, context, today)
	return canned_text(item, context, today)


def process_one(client, fail=False, today=None, log=print):
	"""Claim one item, 'process' it and submit. Returns the submit result, or None when the inbox is empty."""
	item = client.call("inbox.claim_next")
	if not item:
		return None
	log(f"claimed {item['name']}: {item['title']} ({item['source_type']}, {len(item.get('files', []))} files)")
	if fail:
		return client.call("inbox.fail_item", item=item["name"], error="The fake agent was asked to fail.")
	try:
		for f in item.get("files", []):
			data = client.download(f["file_url"])  # a real agent would transcribe this; the copy is dropped at once
			log(f"  downloaded {f['file_name']} ({len(data)} bytes)")
			del data
		transcript, summary, proposals = canned_result(item, item.get("context") or {}, today or time.strftime("%Y-%m-%d"))
		result = client.call("inbox.submit_result", item=item["name"], transcript_md=transcript, summary_md=summary, proposals=proposals)
	except Exception as e:  # report the failure so the owner sees a Retry button
		client.call("inbox.fail_item", item=item["name"], error=str(e)[:500])
		raise
	log(f"  submitted: {len(result['created'])} proposals, {len(result['errors'])} refused, item is {result['status']}")
	for err in result["errors"]:
		log(f"  refused #{err['index']}: {err['error']}")
	return result


def main():
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument("--url", default=os.environ.get("LIFEOS_URL", "http://localhost:18000"))
	ap.add_argument("--loop", action="store_true", help="poll every five minutes")
	ap.add_argument("--fail", action="store_true", help="fail the next item instead of processing it")
	args = ap.parse_args()
	key, secret = os.environ.get("LIFEOS_API_KEY"), os.environ.get("LIFEOS_API_SECRET")
	if not key or not secret:
		sys.exit("Set LIFEOS_API_KEY and LIFEOS_API_SECRET in the environment.")
	client = HttpClient(args.url, key, secret)
	schema = client.call("meta.proposal_schema")
	print(f"schema loaded: {', '.join(schema)}")
	while True:
		done = 0
		while process_one(client, fail=args.fail) is not None:
			done += 1
			if args.fail:
				break
		print(f"{done} item(s) processed")
		if not args.loop:
			break
		time.sleep(300)


if __name__ == "__main__":
	main()
