"""Review: a person accepts or rejects what an agent proposed. Agents are refused."""
import frappe
from frappe import _
from frappe.utils import now_datetime

from lifeos import links, permissions, proposals
from lifeos.api.inbox import _finish_if_decided
from lifeos.api.utils import parse


def _people_only():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Agents cannot accept or reject proposals."), frappe.PermissionError)


def _decide(prop, decision, payload=None):
	if prop.status != "Pending":
		frappe.throw(_("This proposal was already {0}.").format(prop.status.lower()))
	item = frappe.get_doc("Life Inbox Item", prop.inbox_item)
	item.check_permission("write")
	prop.flags.via_review = True
	if decision == "reject":
		prop.status = "Rejected"
	else:
		data = payload if payload is not None else prop.payload_dict()
		try:
			doctype, name = proposals.apply(prop.kind, data, item)
		except proposals.PayloadError as e:
			frappe.throw(str(e), proposals.PayloadError)
		prop.payload = frappe.as_json(proposals.validate(prop.kind, data, item.space, {"allow_new_tags": True}))
		prop.status = "Accepted"
		prop.created_doctype, prop.created_name = doctype, name
	prop.decided_by = frappe.session.user
	prop.decided_on = now_datetime()
	prop.save(ignore_permissions=True)
	return item


@frappe.whitelist(methods=["POST"])
def decide(proposal: str, decision: str, payload: str | dict | None = None):
	"""Accept or reject one proposal. `payload` may carry edited values. People only."""
	_people_only()
	if decision not in ("accept", "reject"):
		frappe.throw(_("decision must be accept or reject."))
	prop = permissions.get_doc_checked("Life Proposal", proposal, "write")
	item = _decide(prop, decision, parse(payload))
	status = _finish_if_decided(item)
	out = {"proposal": prop.name, "status": prop.status, "item": item.name, "item_status": status,
		"created_doctype": prop.created_doctype, "created_name": prop.created_name}
	if prop.created_name:
		out["route"] = links.route_of(prop.created_doctype, prop.created_name)
	return out


@frappe.whitelist(methods=["POST"])
def decide_all(item: str, decision: str):
	"""Accept or reject every pending proposal of an item. A proposal that cannot be accepted stays pending, with its error."""
	_people_only()
	if decision not in ("accept", "reject"):
		frappe.throw(_("decision must be accept or reject."))
	doc = permissions.get_doc_checked("Life Inbox Item", item, "write")
	done, errors = [], []
	for name in frappe.get_all("Life Proposal", filters={"inbox_item": doc.name, "status": "Pending"}, pluck="name", order_by="sort_order asc, creation asc"):
		prop = frappe.get_doc("Life Proposal", name)
		frappe.db.savepoint("lifeos_decide")
		try:
			_decide(prop, decision)
			done.append(name)
		except frappe.ValidationError as e:
			frappe.db.rollback(save_point="lifeos_decide")
			frappe.clear_messages()
			errors.append({"proposal": name, "error": str(e)})
	return {"item": doc.name, "item_status": _finish_if_decided(doc), "decided": done, "errors": errors}


@frappe.whitelist(methods=["POST"])
def update_payload(proposal: str, payload: str | dict):
	"""Save edited values on a pending proposal without deciding it, for example a changed area chip."""
	_people_only()
	prop = permissions.get_doc_checked("Life Proposal", proposal, "write")
	if prop.status != "Pending":
		frappe.throw(_("A decided proposal cannot be changed."))
	try:
		clean = proposals.validate(prop.kind, parse(payload) or {}, prop.space, {"allow_new_tags": True})
	except proposals.PayloadError as e:
		frappe.throw(str(e), proposals.PayloadError)
	prop.payload = frappe.as_json(clean)
	if clean.get("title") and prop.kind in ("Task", "Note", "Vault Document", "Month Goal", "Important Date"):
		prop.preview = clean["title"]
	prop.save()
	return {"proposal": prop.name, "payload": clean, "preview": prop.preview}
