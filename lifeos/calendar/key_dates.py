"""Key dates (issue 100): the events that shape the plan, as opposed to routine meetings.

An Event carries `life_key_date` (0 or 1) and `life_key_date_set_by` (Rule, Skill or Owner). The judgement is the `key-date` skill. With no
AI key, or when the skill says nothing, a rule decides: an all-day or multi-day event is a key date, a timed one is not. An important date
(an all-day event repeated every year) is always one. The owner's star in the event's drawer is final: neither a rule nor the skill
changes it afterwards, and it is kept as a skill correction for the skill to learn from.
"""
import frappe
from frappe import _
from frappe.utils import get_datetime

from lifeos import permissions

SKILL = "key-date"


def by_rule(doc) -> int:
	"""1 for an all-day event or one that runs over more than one day (or repeats every year), else 0."""
	if doc.get("all_day"):
		return 1
	starts = get_datetime(doc.starts_on) if doc.get("starts_on") else None
	ends = get_datetime(doc.ends_on) if doc.get("ends_on") else None
	return 1 if starts and ends and ends.date() > starts.date() else 0


def track_change(doc):
	"""Called from the Event's validate. A new event, or one whose title or time changed, gets the rule's answer at once (unless the owner
	decided); the skill is asked after the commit, in a job, so no save waits on a model."""
	if doc.get("life_key_date_set_by") == "Owner":
		return
	changed = doc.is_new() or any(doc.has_value_changed(f) for f in ("subject", "starts_on", "ends_on", "all_day", "description"))
	if not changed:
		return
	doc.life_key_date = by_rule(doc)
	doc.life_key_date_set_by = "Rule"
	if model_possible():
		doc.flags.ask_key_date = True


def backfill():
	"""The events made before key dates existed get the rule's answer (run by the migrate step; it only touches events that were never judged)."""
	for name in frappe.get_all("Event", filters={"life_key_date_set_by": ("in", ["", None])}, pluck="name", limit=100000, ignore_permissions=True):  # system: a migrate step
		doc = frappe.get_doc("Event", name)
		frappe.db.set_value("Event", name, {"life_key_date": by_rule(doc), "life_key_date_set_by": "Rule"}, update_modified=False)


def model_possible() -> bool:
	f = frappe.flags
	if f.in_install or f.in_migrate or f.in_patch or f.in_import:
		return False
	from lifeos.ai import client

	return client.is_set_up()


def after_save(doc):
	"""Called from the Event's on_update: ask the skill after the commit."""
	if doc.flags.pop("ask_key_date", None):
		frappe.enqueue("lifeos.calendar.key_dates.refine", queue="short", enqueue_after_commit=True, event=doc.name)


def refine(event: str):
	"""The job: the skill's answer replaces the rule's, unless the owner decided meanwhile. None when it said nothing."""
	if not frappe.db.exists("Event", event):
		return None
	doc = frappe.get_doc("Event", event)
	if doc.get("life_key_date_set_by") == "Owner":
		return None
	answer = ask_model(doc)
	if answer is None:
		return None
	frappe.db.set_value("Event", event, {"life_key_date": int(answer), "life_key_date_set_by": "Skill"}, update_modified=False)
	return answer


def ask_model(doc):
	"""True or False as the `key-date` skill says it; None with no key, over the cap, or when the call fails."""
	from lifeos.skills import call

	starts = get_datetime(doc.starts_on)
	ends = get_datetime(doc.ends_on) if doc.get("ends_on") else starts
	got = call.ask(SKILL, {"title": doc.subject, "notes": frappe.utils.strip_html(doc.get("description") or "")[:600], "all_day": bool(doc.all_day),
		"starts": str(starts)[:16], "ends": str(ends)[:16], "repeats": doc.get("repeat_on") if doc.get("repeat_this_event") else "",
		"attendees": len(frappe.parse_json(doc.get("life_attendees") or "[]") or [])}, space=doc.get("life_space"), reference=("Event", doc.name))
	if not got or not isinstance(got.get("key"), bool):
		return None
	return got.get("key")


def set_by_owner(doc, key: bool):
	"""The owner's star: set it, and keep the change as a correction of the skill, so it can learn what he counts as a key date."""
	before = bool(doc.get("life_key_date"))
	doc.db_set({"life_key_date": int(key), "life_key_date_set_by": "Owner"}, update_modified=False)
	if before != key and frappe.db.exists("Life Skill", SKILL):
		_correct(doc, key)
	return key


def _correct(doc, key):
	from lifeos.skills import lessons

	if key:
		detail = _("The Brain did not take the event “{0}” for a key date; the owner made it one.").format(doc.subject)
	else:
		detail = _("The Brain took the event “{0}” for a key date; the owner said it is not one.").format(doc.subject)
	frappe.get_doc({"doctype": "Life Skill Correction", "skill": SKILL, "skill_version": frappe.db.get_value("Life Skill", SKILL, "version"),
		"space": doc.get("life_space"), "correction_type": "Key date", "key": f"key-date:{int(key)}", "detail": detail,
		"capture_title": (doc.subject or "")[:140], "capture_excerpt": frappe.utils.strip_html(doc.get("description") or "")[:300]}
		).insert(ignore_permissions=True)  # system: skills are shared system records; only the Brain and admin screens change them
	lessons.ask_for_lesson(SKILL, doc.get("life_space"), f"key-date:{int(key)}")
