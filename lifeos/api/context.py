"""Context for agents (issue 54): `get` is the one call an agent makes first; `card` is what Settings → Rules shows the owner;
`decide` settles a wiki contradiction that waits in Brain → Needs you. The rules are in lifeos/context.py and lifeos/wiki_check.py."""
import frappe
from frappe import _

from lifeos import context, permissions, wiki_check


@frappe.whitelist(methods=["GET"])
def get(space: str | None = None, task: str | None = None, budget: int | None = 1500):
	"""The core card and the index; with `task`, the card, the index lines that match it and the summaries of the few pages that matter
	most, trimmed to `budget` words. Sensitive pages are left out unless the space lets agents open sensitive items. Open only the pages
	you need (`wiki.get_page`), and file back with `jobs.file_job` when the job ends."""
	space = permissions.resolve_space(space)
	return context.get(space, task, budget)


@frappe.whitelist(methods=["GET"])
def card(space: str | None = None):
	""""What agents know about you": the core card as Settings → Rules shows it, read only."""
	space = permissions.resolve_space(space)
	text = context.card(space)
	return {"space": space, "card": text, "words": context.words(text)}


@frappe.whitelist(methods=["POST"])
def decide(finding: str, choice: int):
	"""Keep one of a contradiction's facts (`choice`: the position of the option, from 0). The other pages are changed to say it."""
	_people_only()
	return wiki_check.decide(finding, choice)


def _people_only():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Contradictions are decided by people."), frappe.PermissionError)
