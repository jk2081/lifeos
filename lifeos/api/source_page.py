"""Brain > Sources > one source (issue 84): its strip, Rules, settings and Try it. People only; only the owner changes the rules."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.utils import parse
from lifeos.brain import source_page as pages
from lifeos.skills import store, template


def _people_only(write: bool = False, space: str | None = None) -> str:
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Sources are for people."), frappe.PermissionError, title=_("Only people open sources"))
	return permissions.resolve_space(space, write=write)


def _known(space: str, key: str) -> str:
	key = (key or "").strip().lower()
	if not pages.known(space, key):
		frappe.throw(_("There is no source called {0}.").format(key), frappe.DoesNotExistError, title=_("Source not found"))
	return key


def _owner_only():
	if not permissions.is_admin():
		frappe.throw(_("Only the owner can change a source's rules."), frappe.PermissionError, title=_("Only the owner changes rules"))


@frappe.whitelist(methods=["GET"])
def get(key: str, space: str | None = None):
	"""One source's page: the strip (on or off, where it arrives from, this week's count, the share filed without you, the AI cost of the week,
	the skill and its version), its Rules, its settings, its versions, examples, lessons and recent captures."""
	space = _people_only(space=space)
	return {**pages.page(space, _known(space, key)), "can_edit": permissions.is_admin()}


@frappe.whitelist(methods=["POST"])
def save_rules(key: str, sections: str | dict, anything_else: str | None = None, space: str | None = None):
	"""Save the Rules tab: each section's chips, rows or text, and the free box. A changed text is a new version of the source's skill."""
	space = _people_only(write=True, space=space)
	_owner_only()
	data = parse(sections) or {}
	if not isinstance(data, dict):
		frappe.throw(_("sections must be an object."), title=_("Sections must be an object"))
	return pages.save_rules(_known(space, key), data, anything_else)


@frappe.whitelist(methods=["POST"])
def go_back(key: str, version: int, space: str | None = None):
	"""Version history: restore an earlier version of the source's rules as a new version."""
	space = _people_only(write=True, space=space)
	_owner_only()
	doc = store.rollback(pages.skill_of(_known(space, key)), int(version))
	return {"skill": doc.name, "version": doc.version, "rules": template.rules_of(doc.name, doc.instructions)}


@frappe.whitelist(methods=["POST"])
def save_settings(key: str, auto_file_confidence: int | None = None, readers: str | list | None = None, space: str | None = None):
	"""The side panel: the confidence above which what it brings is filed without you (0 to 100), and which agents may read it."""
	space = _people_only(write=True, space=space)
	_owner_only()
	if auto_file_confidence is not None and not 0 <= int(auto_file_confidence) <= 100:
		frappe.throw(_("The confidence is a percentage from 0 to 100."), title=_("Confidence out of range"))
	return pages.save_settings(space, _known(space, key), auto_file_confidence, parse(readers) if readers is not None else None)


@frappe.whitelist(methods=["POST"])
def try_it(key: str, title: str | None = None, text: str | None = None, url: str | None = None, file_url: str | None = None, space: str | None = None):
	"""What the source's rules would do with a sample (a file, text or a link): summary, filing, proposals, what it skipped and the lessons
	used. Nothing is filed."""
	space = _people_only(write=True, space=space)
	return pages.try_it(space, _known(space, key), title, text, url, file_url)


@frappe.whitelist(methods=["POST"])
def file_it(key: str, title: str | None = None, text: str | None = None, url: str | None = None, file_url: str | None = None, space: str | None = None):
	"""File Try it's sample for real, as a capture the Brain reads like any other."""
	space = _people_only(write=True, space=space)
	return pages.file_for_real(space, _known(space, key), title, text, url, file_url)


@frappe.whitelist(methods=["GET"])
def groups(space: str | None = None):
	"""Brain > Sources in two groups: channels (where it comes from) and kinds (what it is), each row with its count this week, whether it is
	on, and its skill and version."""
	space = _people_only(space=space)
	return pages.groups(space)


@frappe.whitelist(methods=["POST"])
def teach(key: str, lesson: str, space: str | None = None):
	"""Try it's "That's wrong… teach it": a correction in a sentence or two becomes a lesson in the source's skill, as a new version."""
	space = _people_only(write=True, space=space)
	_owner_only()
	return pages.teach(_known(space, key), lesson)
