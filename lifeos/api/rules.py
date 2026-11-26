"""Rules (issue 117): what the Brain does with a capture before it asks a model. Settings > Brain > Rules and a source's Rules tab show the same
rules, in plain words; Change on one is edit, switch off or delete. People only."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.utils import parse
from lifeos.brain import rules as engine

FIELDS = ("sender", "domain", "source", "item_kind", "title_words", "attachment_type", "action", "file_as", "area", "no_area", "never_page", "page_doctype", "page")
CHANGES = ("off", "on", "delete", "edit")


def _people_only(write: bool = False, space: str | None = None) -> str:
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Rules are for people."), frappe.PermissionError, title=_("Only people change rules"))
	return permissions.resolve_space(space, write=write)


def card(rule) -> dict:
	"""A rule as a screen shows it."""
	return {"name": rule.name, "words": engine.words(rule), "when": engine.when_words(rule), "then": engine.then_words(rule), "enabled": int(bool(rule.enabled)),
		"made_by": rule.made_by, "builtin": rule.builtin, "used": int(rule.used_count or 0), "last_used": str(rule.last_used)[:16] if rule.last_used else None,
		"all_sources": int(not rule.source), "source": rule.source, "values": {f: rule.get(f) for f in FIELDS}, "made": str(rule.creation)[:16]}


def _rule(name: str):
	"""A rule in a space the caller writes in."""
	doc = permissions.get_doc_checked("Life Rule", name, "write")
	return doc


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, source: str | None = None):
	"""Every rule of the space, in the order they are tried, in plain words, each with how many times it was used and when. With `source`, only the
	rules that can apply to that source (its own, and the ones for every source)."""
	space = _people_only(space=space)
	rows = engine.rules_of(space, only_on=False)
	if source:
		rows = [r for r in rows if engine.applies_to(r, source)]
	return {"rules": [card(frappe.get_doc("Life Rule", r.name)) for r in rows], "recent": engine.recent(space)}


@frappe.whitelist(methods=["GET"])
def for_source(key: str, space: str | None = None):
	"""A source's page, how it is processed: its rules in the order they are tried, then what the Brain does with the rest, then the last ten items
	from it and what decided each."""
	space = _people_only(space=space)
	return engine.how_processed(space, key)


@frappe.whitelist(methods=["POST"])
def add(space: str | None = None, sender: str | None = None, domain: str | None = None, source: str | None = None, item_kind: str | None = None,
		title_words: str | None = None, attachment_type: str | None = None, action: str = "File", file_as: str | None = None, area: str | None = None,
		no_area: int = 0, never_page: int = 0, page_doctype: str | None = None, page: str | None = None):
	"""Make a rule by hand (the Add a rule form). It is the owner's."""
	space = _people_only(write=True, space=space)
	values = {"sender": sender, "domain": domain, "source": source, "item_kind": item_kind, "title_words": title_words, "attachment_type": attachment_type, "action": action,
		"file_as": file_as, "area": area, "no_area": int(bool(no_area)), "never_page": int(bool(never_page)), "page_doctype": page_doctype, "page": page}
	doc = frappe.get_doc({"doctype": "Life Rule", "space": space, "made_by": "Owner", "enabled": 1, **values}).insert()
	return card(doc)


@frappe.whitelist(methods=["POST"])
def change(rule: str, what: str, values: str | dict | None = None):
	"""The one Change on a rule: `off` stops it being applied, `on` starts it again, `delete` removes it, `edit` saves `values`. A rule changed
	or switched off is a correction like any other: the Brain does not make it again by itself."""
	_people_only(write=True)
	doc = _rule(rule)
	if what not in CHANGES:
		frappe.throw(_("what must be one of: {0}.").format(", ".join(CHANGES)), title=_("Unknown change"))
	if what == "delete":
		if doc.builtin:
			frappe.throw(_("A built-in rule cannot be deleted; switch it off."), title=_("Built-in rule"))
		frappe.delete_doc("Life Rule", doc.name)
		return {"deleted": doc.name}
	if what in ("off", "on"):
		doc.enabled = 1 if what == "on" else 0
	else:
		data = parse(values) or {}
		for field in FIELDS:
			if field in data:
				doc.set(field, data[field] if data[field] not in ("",) else None)
	doc.save()
	return card(doc)


@frappe.whitelist(methods=["POST"])
def always_ask(proposal: str):
	"""Change > "Always ask about this sender": a rule that keeps what comes from this sender (or, with no sender, this source and kind) for the owner."""
	space = _people_only(write=True)
	prop = permissions.get_doc_checked("Life Proposal", proposal, "write")
	item = frappe.get_doc("Life Inbox Item", prop.inbox_item)
	if item.space != space and not permissions.user_spaces().get(item.space):
		frappe.throw(_("There is no such proposal."), frappe.DoesNotExistError, title=_("Proposal not found"))
	doc = engine.always_ask(item, prop)
	return card(doc)
