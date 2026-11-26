"""Ask's way to teach the Brain (issue 117): "file Claude's recaps without an area" becomes a rule, saved at once, shown in the answer with Change and Undo.
Owner only: an agent does not make rules."""
import frappe
from frappe import _

from lifeos.brain import rules
from lifeos.tools import actions


def add_rule(space: str | None = None, sender: str | None = None, domain: str | None = None, source: str | None = None, kind: str | None = None, title_words: str | None = None,
		attachment_type: str | None = None, action: str = "File", area: str | None = None, part: str | None = None, no_area: bool = False, file_as: str | None = None,
		never_page: bool = False) -> dict:
	"""Make a rule from what the owner said. When a capture has the `sender`, `domain`, `source`, `kind` (such as Chat), `title_words` or `attachment_type`, then `action`
	File (under an `area` and `part` by name, or `no_area`, optionally `file_as` Chat, Note, Report or Task), Drop, Ask (always ask) or Link; `never_page` stops a page being proposed
	for the sender. Owner only."""
	return actions.write("rules.add", space, {"title": "rule", "sender": sender, "domain": domain, "source": source, "kind": kind, "title_words": title_words,
		"attachment_type": attachment_type, "action": action, "area": area, "part": part, "no_area": no_area, "file_as": file_as, "never_page": never_page})


def _add_rule(space: str, title: str = "", sender=None, domain=None, source=None, kind=None, title_words=None, attachment_type=None, action="File", area=None, part=None,
		no_area=False, file_as=None, never_page=False) -> tuple[str, dict, dict | None]:
	where = actions.area_of(space, area, part) if area or part else None
	doc = frappe.get_doc({"doctype": "Life Rule", "space": space, "made_by": "Owner", "enabled": 1, "sender": sender, "domain": domain, "source": source, "item_kind": kind,
		"title_words": title_words, "attachment_type": attachment_type, "action": action if action in rules.ACTIONS else "File", "area": where, "no_area": 1 if no_area else 0,
		"file_as": file_as if file_as in rules.FILE_AS else None, "never_page": 1 if never_page else 0, "learned_from": "Ask"}).insert()
	return _("New rule: {0}").format(rules.words(doc)), {"rule": doc.name, "title": rules.words(doc)}, {"delete": [["Life Rule", doc.name]]}
