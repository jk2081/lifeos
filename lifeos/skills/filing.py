"""What the Brain files on its own: a proposal above the confidence threshold, of a kind the owner turned on (default: none), is
accepted with the same call a person's Keep makes, and shows in Activity as "Filed by process-capture v1". Everything else waits."""
import json

import frappe
from frappe.utils import flt

DEFAULT_THRESHOLD = 0.85


def settings():
	"""{threshold, kinds}: the owner's choice in Settings."""
	s = frappe.get_cached_doc("Life Settings")
	try:
		kinds = json.loads(s.get("brain_auto_kinds") or "[]")
	except ValueError:
		kinds = []
	return {"threshold": flt(s.get("brain_auto_threshold")) or DEFAULT_THRESHOLD, "kinds": [k for k in kinds if isinstance(k, str)]}


def file_confident(item, proposals, label):
	"""Accept each pending proposal of `item` (the names in `proposals`) that is sure enough and of a kind that may be filed on its own."""
	from lifeos.api import review
	from lifeos.api.inbox import _finish_if_decided

	from lifeos.brain import source_page

	rule = settings()
	if not rule["kinds"]:
		return []
	own = source_page.threshold_for(frappe.get_doc("Life Inbox Item", item))  # a source's own confidence (issue 84) beats the setting
	threshold = rule["threshold"] if own is None else own
	filed = []
	for name in proposals:
		prop = frappe.get_doc("Life Proposal", name)
		if prop.status != "Pending" or prop.kind not in rule["kinds"] or flt(prop.confidence) < threshold:
			continue
		frappe.db.savepoint("lifeos_autofile")
		try:
			review._decide(prop, "accept")
		except frappe.ValidationError:
			frappe.db.rollback(save_point="lifeos_autofile")
			frappe.clear_messages()
			continue
		frappe.db.set_value("Life Proposal", prop.name, "filed_by", label)
		filed.append(prop.name)
	if filed:
		_finish_if_decided(frappe.get_doc("Life Inbox Item", item))
	return filed
