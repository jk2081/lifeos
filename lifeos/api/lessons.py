"""Lessons (issue 30): what the owner's corrections teach a skill. The owner accepts, edits, rejects or removes them; a lesson changes
the skill's text only (lifeos/skills/lessons.py)."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.skills import _admin_only, _people_only, _skill
from lifeos.skills import lessons


def _lesson(name):
	"""A lesson in a space the caller belongs to."""
	doc = lessons.get(name)
	if doc.space and doc.space not in permissions.user_spaces() and not permissions.is_admin():
		frappe.throw(_("There is no such lesson."), frappe.DoesNotExistError, title=_("Lesson not found"))
	return doc


@frappe.whitelist(methods=["GET"])
def for_skill(skill: str):
	"""The lessons of a skill that are proposed, accepted, removed or rejected, newest first."""
	_people_only()
	_skill(skill)
	return [x for x in lessons.for_skill(skill) if not x["space"] or x["space"] in permissions.user_spaces() or permissions.is_admin()]


@frappe.whitelist(methods=["POST"])
def accept(lesson: str, text: str | None = None):
	"""Add a proposed lesson (with its words edited when `text` is given) to the skill as a new version. Refused, with the failing examples
	named, when an example of the skill would fail with it."""
	_admin_only()
	_lesson(lesson)
	return lessons.card(lessons.accept(lesson, text))


@frappe.whitelist(methods=["POST"])
def edit(lesson: str, text: str):
	"""Change the words of a proposed lesson, without accepting it."""
	_admin_only()
	_lesson(lesson)
	return lessons.card(lessons.edit(lesson, text))


@frappe.whitelist(methods=["POST"])
def reject(lesson: str):
	_admin_only()
	_lesson(lesson)
	return lessons.card(lessons.reject(lesson))


@frappe.whitelist(methods=["POST"])
def remove(lesson: str):
	"""Take an accepted lesson out of its skill: a new version without it."""
	_admin_only()
	_lesson(lesson)
	return lessons.card(lessons.remove(lesson))
