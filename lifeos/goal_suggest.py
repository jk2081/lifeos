"""Goals > No goal (issue 22): when several tasks of one area point the same way, suggest one goal for them, and make it
on a click. Nothing here runs without the click that asks for it, except `cluster`, which only reads titles."""
import frappe
from frappe import _

from lifeos.area_guess import words

MIN_TASKS = 3
TITLE_SYSTEM = (
	"You name a goal for the owner. You get the titles of several open tasks that belong together. Answer with one short goal "
	"title (at most eight words) that says the result they are working towards, in the owner's own plain words."
)
TITLE_SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"], "additionalProperties": False}


def cluster(tasks):
	"""The largest set of at least three tasks (rows with `name` and `title`) whose titles share a word, as
	{word, title, tasks: [names]}, or None. The title is the word, capitalised: a name to show, not a final goal title."""
	seen = {}
	for t in tasks:
		for w in set(words(t["title"])):
			if len(w) >= 4:
				seen.setdefault(w, []).append(t["name"])
	best = max(seen.items(), key=lambda kv: (len(kv[1]), len(kv[0]), kv[0]), default=None)
	if not best or len(best[1]) < MIN_TASKS:
		return None
	return {"word": best[0], "title": best[0].capitalize(), "tasks": best[1]}


def fake_title(data):
	"""What the fake assistant answers: the rule's title, so tests and the acceptance site are deterministic."""
	return {"title": rule_title(data.get("titles") or [])}


def rule_title(titles):
	"""A goal title from the task titles alone: the word most of them share, else the first title."""
	found = cluster([{"name": str(i), "title": t} for i, t in enumerate(titles)])
	if found:
		return f"Get {found['title']} done"[:140]
	return (titles[0] if titles else _("New goal"))[:140]


def title_for(titles, space=None):
	"""The goal title for these task titles. With a key set and within the spend cap, the assistant's short model names it;
	otherwise, or if the call fails, the titles do."""
	import json

	from lifeos.ai import client

	base = rule_title(titles)
	if not client.is_set_up():
		return base
	try:
		out = client.call("Goal from tasks", TITLE_SYSTEM, [{"role": "user", "content": json.dumps({"task": "goal_title", "titles": titles[:20]})}],
			kind="short", space=space, schema=TITLE_SCHEMA, max_tokens=200)
	except client.AIError:
		return base
	return ((client.json_of(out["content"]) or {}).get("title") or "").strip()[:140] or base
