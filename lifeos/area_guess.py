"""Every task has an area (issue 13). When a task is saved without one, the Brain guesses it, in this order:

1. the area of the task's goal;
2. the area of the capture (inbox item) it came from;
3. a rule match: the words of the title against the names and descriptions of the areas and parts that are on;
4. with an AI key set and within the spend cap, one short model call with the title, notes and the areas that are on;
5. otherwise Career, if it is on, with a low confidence.

A guessed area carries `area_guessed` and `area_confidence` until a person confirms or changes it. A change is kept as a
`Life Action Log` row of kind "Area correction" (the guessed area and the new one), for later issues to learn from.
"""
import json
import re

import frappe

from lifeos import areas

# confidence, in percent, of each step
GOAL_CONFIDENCE = 95
CAPTURE_CONFIDENCE = 85
NAME_CONFIDENCE = 70
WORD_CONFIDENCE = 50
TIE_PENALTY = 15
FALLBACK_CONFIDENCE = 20
FALLBACK_AREA = "Career"

STOP_WORDS = set("""
a an and are as at be but by can could did do does for from get got has have he her his how i if in into is it its me my
need needs new no not now of on one or our out please re she so some than that the their them then there these they this
to too up us was we were what when where which who why will with would you your yours about after again all also am any
back before call check do done email find follow just let like look make more much next off only over put reply say see
send set should still take tell thing things think today tomorrow two week via want way well yet
""".split())

SYSTEM = (
	"You file a task into one of the owner's areas of life. You get the task's title and notes, and the areas that are on: "
	"each has an id, a name, a short description, and for a part, the area of life it belongs to. Pick the one area the task "
	"belongs to, preferring a part when the task is clearly about it. Answer with its id and how sure you are, from 0 to 100."
)
SCHEMA = {
	"type": "object",
	"properties": {"area": {"type": "string"}, "confidence": {"type": "integer"}},
	"required": ["area", "confidence"],
	"additionalProperties": False,
}


def apply(doc, use_ai=True):
	"""Fill `doc.area` with a guess when it has none. Returns the guess {area, confidence, source} or None."""
	if doc.area:
		return None
	found = guess(doc, use_ai=use_ai)
	if found:
		doc.area = found["area"]
		doc.area_guessed = 1
		doc.area_confidence = found["confidence"]
	return found


def guess(doc, use_ai=True):
	"""The area a task most likely belongs to, as {area, confidence, source}, or None when no area of its space is on."""
	if doc.goal:
		area = frappe.db.get_value("Life Goal", doc.goal, "area")
		if area:
			return _found(area, GOAL_CONFIDENCE, "goal")
	candidates = areas.ordered(doc.space, fields=["name", "area_name", "parent_area", "is_life_area", "description"])
	on = {a.name for a in candidates}
	if doc.inbox_item:
		area = frappe.db.get_value("Life Inbox Item", doc.inbox_item, "area")
		if area in on:
			return _found(area, CAPTURE_CONFIDENCE, "capture")
	found = rule_match(doc.title, candidates)
	if found:
		return found
	if use_ai and ai_allowed():
		found = ask_model(doc, candidates)
		if found:
			return found
	return fallback(candidates)


def _found(area, confidence, source):
	return {"area": area, "confidence": max(0, min(100, int(confidence))), "source": source}


def words(text):
	"""The meaningful words of a text, lower case and with a plain plural made singular."""
	out = set()
	for w in re.findall(r"[^\W_]+", (text or "").lower()):
		if len(w) < 3 or w in STOP_WORDS or w.isdigit():
			continue
		if len(w) > 4 and w.endswith("ies"):
			w = w[:-3] + "y"
		elif len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
			w = w[:-1]
		out.add(w)
	return out


def rule_match(title, candidates):
	"""The area whose name or description shares the most words with the title. A word of the name counts three, a word
	of the description one. A part wins a tie with an area of life (it is the more exact place); a tie between two
	different areas lowers the confidence."""
	title_words = words(title)
	if not title_words:
		return None
	scored = []
	for i, a in enumerate(candidates):
		name_words, desc_words = words(a.area_name), words(a.description)
		score = 3 * len(title_words & name_words) + len(title_words & (desc_words - name_words))
		if score:
			scored.append((score, 1 if a.parent_area else 0, -i, a, bool(title_words & name_words)))
	if not scored:
		return None
	scored.sort(key=lambda s: s[:3], reverse=True)
	score, _part, _i, best, by_name = scored[0]
	confidence = NAME_CONFIDENCE if by_name else min(WORD_CONFIDENCE + 5 * (score - 1), NAME_CONFIDENCE - 5)
	if len(scored) > 1 and scored[1][0] == score:
		confidence -= TIE_PENALTY
	return _found(best.name, confidence, "rule")


def fallback(candidates):
	"""Career if it is on; else the first area of life that is on; None when every area of the space is off."""
	life = [a for a in candidates if a.is_life_area]
	pick = next((a for a in life if a.area_name == FALLBACK_AREA), None) or (life[0] if life else None)
	return _found(pick.name, FALLBACK_CONFIDENCE, "fallback") if pick else None


def ai_allowed():
	"""A model call is made only from a normal request or job, never during install, migrate, a patch or an import."""
	f = frappe.flags
	return not (f.in_install or f.in_migrate or f.in_patch or f.in_import or f.lifeos_no_area_ai)


def ask_model(doc, candidates):
	"""Step 4: one short model call, within the spend cap. None when there is no key, the cap is reached, the call fails,
	or the answer names no area that is on."""
	from lifeos.ai import client

	if not candidates or not client.is_set_up():
		return None
	ids = {f"A{i + 1}": a for i, a in enumerate(candidates[:80])}
	names = {a.name: a.area_name for a in candidates}
	prompt = json.dumps({"task": "task_area", "title": doc.title, "notes": (doc.notes_md or "")[:1500],
		"areas": [{"id": k, "name": a.area_name, "part_of": names.get(a.parent_area), "description": a.description or ""}
			for k, a in ids.items()]})
	try:
		out = client.call("Area guess", SYSTEM, [{"role": "user", "content": prompt}], kind="short", space=doc.space,
			schema=SCHEMA, max_tokens=200)
	except client.AIError:
		return None
	data = client.json_of(out["content"]) or {}
	key = str(data.get("area") or "").strip()
	pick = ids.get(key) or next((a for a in ids.values() if a.area_name.lower() == key.lower()), None)
	if not pick:
		return None
	try:
		confidence = int(data.get("confidence"))
	except (TypeError, ValueError):
		confidence = WORD_CONFIDENCE
	return _found(pick.name, confidence, "model")


def fake_area(data):
	"""The acceptance site's model: the first part that shares a word with the title or notes, else the first area given,
	40% sure."""
	text = words(f"{data.get('title') or ''} {data.get('notes') or ''}")
	listed = data.get("areas") or []
	pick = next((a for a in listed if a.get("part_of") and text & words(f"{a['name']} {a.get('description') or ''}")), None)
	pick = pick or (listed[0] if listed else {})
	return {"area": pick.get("id") or "", "confidence": 40}


def track_change(doc):
	"""Called from the task's validate. Guess an area when the task has none; when a person or agent changes a guessed
	area, clear the mark and remember the correction (written in on_update). Moving the open work of an archived part
	(areas.move_work) is not a correction."""
	if not doc.area:
		apply(doc, use_ai=not doc.flags.no_area_ai)
		return
	if doc.is_new() or not doc.has_value_changed("area") or doc.flags.area_moved:
		return
	before = doc.get_doc_before_save()
	if before and before.area_guessed and before.area:
		doc.flags.area_correction = (before.area, doc.area)
	doc.area_guessed = 0
	doc.area_confidence = 0


def log_correction(doc):
	"""Called from the task's on_update: keep the owner's correction of a guessed area."""
	change = doc.flags.pop("area_correction", None)
	if not change:
		return
	frappe.get_doc({"doctype": "Life Action Log", "kind": "Area correction", "space": doc.space, "task": doc.name,
		"old_area": change[0], "new_area": change[1], "date": frappe.utils.today()}).insert(ignore_permissions=True)


def confirm(doc, area=None):
	"""Confirm the guessed area of a task (clear the mark), or move it to `area`, which clears the mark and logs the
	correction."""
	if area and area != doc.area:
		doc.area = area
	else:
		doc.area_guessed = 0
		doc.area_confidence = 0
	doc.save()
	return doc


def fill_missing(use_ai=False):
	"""The patch's work: give every task without an area a guessed one, by steps 1 to 3 and 5 (no model call). Writes the
	fields directly (no `modified` change) and refreshes each task's index row. Returns how many were filled."""
	from lifeos import index

	filled = 0
	for name in frappe.get_all("Life Task", filters={"area": ("is", "not set")}, pluck="name", limit=0):
		doc = frappe.get_doc("Life Task", name)
		found = apply(doc, use_ai=use_ai)
		if not found:
			continue
		frappe.db.set_value("Life Task", name, {"area": doc.area, "area_guessed": 1, "area_confidence": doc.area_confidence},
			update_modified=False)
		index.update(doc)
		filled += 1
	return filled
