"""Every task has an area (issue 13). When a task is saved without one, the Brain guesses it, in this order:

1. the area of the task's goal;
2. the area of the capture (inbox item) it came from;
3. a rule match: the words of the title against the names and descriptions of the areas and parts that are on;
4. with an AI key set and within the spend cap, the guess-area skill, given the title, notes and the areas that are on;
5. otherwise Career, if it is on, with a low confidence.

Steps 1, 2, 3 and 5 run as the task is saved, so it always has an area. Step 4 runs in a background job after the save,
only when the task got the Career fallback, and replaces that guess with the model's.

A guessed area carries `area_guessed` and `area_confidence` until a person confirms or changes it. A change is kept as a
`Life Action Log` row of kind "Area correction" (the guessed area and the new one), for later issues to learn from.
"""
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

def apply(doc):
	"""Fill `doc.area` with a guess by steps 1, 2, 3 and 5 when it has none. Returns {area, confidence, source} or None."""
	if doc.area:
		return None
	found = guess(doc)
	if found:
		doc.area = found["area"]
		doc.area_guessed = 1
		doc.area_confidence = found["confidence"]
	return found


def guess(doc):
	"""The area a task most likely belongs to without asking a model, as {area, confidence, source}, or None when no area
	of its space is on."""
	if doc.goal:
		area = frappe.db.get_value("Life Goal", doc.goal, "area")
		if area:
			return _found(area, GOAL_CONFIDENCE, "goal")
	candidates = candidates_of(doc.space)
	if doc.inbox_item:
		area = frappe.db.get_value("Life Inbox Item", doc.inbox_item, "area")
		if area in {a.name for a in candidates}:
			return _found(area, CAPTURE_CONFIDENCE, "capture")
	return rule_match(doc.title, candidates) or fallback(candidates)


def candidates_of(space):
	"""The areas a task may be filed into: those that are on and not archived, in picker order."""
	return areas.ordered(space, fields=["name", "area_name", "parent_area", "is_life_area", "description"])


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


def model_possible():
	"""Step 4 runs only with an AI key set, and never for a task saved during install, migrate, a patch or an import."""
	from lifeos.ai import client

	f = frappe.flags
	if f.in_install or f.in_migrate or f.in_patch or f.in_import:
		return False
	return client.is_set_up()


def refine(task, area):
	"""Step 4, in a background job after the task is saved, so no request waits on the model or holds its transaction
	open: when the task still has the Career fallback, unconfirmed, ask the model and take its answer."""
	if not frappe.db.exists("Life Task", task):
		return None  # deleted before the job ran
	doc = frappe.get_doc("Life Task", task)
	if not (doc.area_guessed and doc.area == area and doc.area_confidence == FALLBACK_CONFIDENCE):
		return None  # confirmed, changed or guessed better meanwhile
	found = ask_model(doc, candidates_of(doc.space))
	if not found:
		return None
	doc.area, doc.area_confidence = found["area"], found["confidence"]
	doc.flags.area_guess = True  # still a guess: keep the mark, log no correction
	doc.flags.keep_touched = True
	doc.save(ignore_permissions=True)  # the job runs as the user who saved the task; only the guess changes
	return found


def ask_model(doc, candidates):
	"""Step 4: the guess-area skill, within the spend cap. None when there is no key, the cap is reached, the call fails, or the answer
	names no area that is on."""
	from lifeos.skills import call

	if not candidates:
		return None
	ids = {f"A{i + 1}": a for i, a in enumerate(candidates[:80])}
	names = {a.name: a.area_name for a in candidates}
	got = call.ask("guess-area", {"title": doc.title, "notes": (doc.notes_md or "")[:1500], "areas": [{"id": k, "name": a.area_name,
		"part_of": names.get(a.parent_area), "description": a.description or ""} for k, a in ids.items()]}, space=doc.space, reference=(doc.doctype, doc.name))
	key = str(got.get("area") or "").strip()
	pick = ids.get(key) or next((a for a in ids.values() if a.area_name.lower() == key.lower()), None)
	if not pick:
		return None
	try:
		confidence = int(got.get("confidence"))
	except (TypeError, ValueError):
		confidence = WORD_CONFIDENCE
	return _found(pick.name, confidence, "model")


def track_change(doc):
	"""Called from the task's validate. Guess an area when the task has none; when a person or agent changes a guessed
	area, clear the mark and remember the correction (written in on_update). Moving the open work of an archived part
	(areas.move_work) is not a correction."""
	if not doc.area:
		found = apply(doc)
		if found and found["source"] == "fallback" and model_possible():
			doc.flags.refine_area = True
		return
	if doc.is_new() or not doc.has_value_changed("area") or doc.flags.area_moved or doc.flags.area_guess:
		return
	before = doc.get_doc_before_save()
	if before and before.area_guessed and before.area:
		doc.flags.area_correction = (before.area, doc.area)
	doc.area_guessed = 0
	doc.area_confidence = 0


def after_save(doc):
	"""Called from the task's on_update: ask the model about a fallback guess after the commit (step 4), and keep the
	owner's correction of a guessed area."""
	if doc.flags.pop("refine_area", None):
		frappe.enqueue("lifeos.area_guess.refine", queue="short", enqueue_after_commit=True, task=doc.name,
			area=doc.area)
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


def fill_missing():
	"""The patch's work: give every task without an area a guessed one, by steps 1 to 3 and 5 (no model call). Writes the
	fields directly (no `modified` change) and refreshes each task's index row. Returns how many were filled."""
	from lifeos import index

	filled = 0
	for name in frappe.get_all("Life Task", filters={"area": ("is", "not set")}, pluck="name", limit=0):
		doc = frappe.get_doc("Life Task", name)
		found = apply(doc)
		if not found:
			continue
		frappe.db.set_value("Life Task", name, {"area": doc.area, "area_guessed": 1, "area_confidence": doc.area_confidence},
			update_modified=False)
		index.update(doc)
		filled += 1
	return filled
