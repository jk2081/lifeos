"""Goals > No goal (issue 22): when several tasks of one area point the same way, suggest one goal for them, and make it
on a click. Nothing here runs without the click that asks for it, except `cluster`, which only reads titles."""
from frappe import _

from lifeos.brain.area_guess import words

MIN_TASKS = 3


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


def rule_title(titles):
	"""A goal title from the task titles alone: the word most of them share, else the first title."""
	found = cluster([{"name": str(i), "title": t} for i, t in enumerate(titles)])
	if found:
		return f"Get {found['title']} done"[:140]
	return (titles[0] if titles else _("New goal"))[:140]


def title_for(titles, space=None):
	"""The goal title for these task titles: the define-goal skill names it; with no key, or when it says nothing, the titles do."""
	from lifeos.skills import call

	got = call.ask("define-goal", {"request": "title", "titles": titles[:20]}, space=space)
	return (got.get("title") or "").strip()[:140] or rule_title(titles)
