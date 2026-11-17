"""Inbox items left too long (set 7): the suggested decisions to confirm, Confirm selected, Undo, and Today's Undo of what the
rule parked or discarded on its own. People only: agents never accept, park or discard."""
import builtins

import frappe
from frappe import _

from lifeos import old_inbox, permissions
from lifeos.api.utils import lens_area, page, parse


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Only a person decides what happens to Inbox items."), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def suggested(space: str | None = None, area: str | None = None, start: int = 0, page_length: int = 100):
	"""Items older than the rule's days that have a suggested decision and are still waiting: each with its decision, reason,
	proposals and when it came in. `total` is what the Inbox's banner counts."""
	_person()
	space = permissions.resolve_space(space)
	area = lens_area(area)
	r = old_inbox.rule()
	items = [i for i in old_inbox.candidates(space, r["days"], limit=1000) if i.suggested_decision]
	if area:
		from lifeos.api.utils import in_area

		keep = in_area(space, area, "Life Inbox Item", [i.name for i in items])
		items = [i for i in items if i.name in keep]
	start, page_length = page(start, page_length)
	part = items[start:start + page_length]
	pending = old_inbox._pending(part)
	sensitive = dict(frappe.get_all("Life Inbox Item", filters={"name": ("in", [i.name for i in part] or ["-"])}, fields=["name", "is_sensitive"], as_list=True))
	rows = [{"name": i.name, "title": i.title, "status": i.status, "received_on": str(i.received_on)[:19] if i.received_on else None,
		"decision": i.suggested_decision, "reason": i.suggested_reason, "suggested_on": str(i.suggested_on) if i.suggested_on else None,
		"proposals": [p.kind for p in pending.get(i.name, [])], "sensitive": bool(sensitive.get(i.name))} for i in part]
	return {"rows": rows, "total": len(items), "days": r["days"], "mode": r["mode"]}


@frappe.whitelist(methods=["POST"])
def apply(items: str | builtins.list):
	"""Confirm decisions: [{item, decision}] with decision Accept, Park or Discard. Returns the Undo log."""
	_person()
	return old_inbox.apply(parse(items, []) or [])


@frappe.whitelist(methods=["POST"])
def undo(log: str | builtins.list):
	"""Put back what Confirm selected did."""
	_person()
	old_inbox.undo(parse(log, []) or [])
	return {"undone": True}


@frappe.whitelist(methods=["POST"])
def undo_auto(space: str | None = None):
	"""Today's Undo: bring back what the rule parked or discarded on its own in the last seven days."""
	_person()
	space = permissions.resolve_space(space, write=True)
	return old_inbox.undo_auto(space)
