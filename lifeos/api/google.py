"""Google through Life OS (issue 86): the tools an agent acts with. One connection for each person, held by Life OS; every act is logged once on the
agent's page. Read tools are `mail.search`, `mail.get_thread`, `mail.get_attachment` (lifeos.api.mail) and `calendar_list` here. The acts are `email.draft`,
`email.send`, `email.archive`, `email.label`, `calendar.create`, `calendar.move` and `calendar.respond`, all through `act`. There is no delete."""
import frappe
from frappe import _

from lifeos import mail, permissions
from lifeos.agents import acts
from lifeos.api.utils import parse


@frappe.whitelist(methods=["GET"])
def tools():
	"""Every tool an agent has for Google: name, kind (read or act), the switch it follows and what it needs."""
	rows = [{"name": t, "kind": "read", "switch": s} for t, s in acts.READS.items()]
	rows += [{"name": t, "kind": "act", "switch": v[0], "label": v[1], "needs": list(v[2])} for t, v in acts.ACTS.items()]
	return rows


@frappe.whitelist(methods=["POST"])
def act(source_system: str, tool: str, params: str | dict | None = None, asked_by: str = "agent", owner_message: str | None = None, space: str | None = None):
	"""Do something in the owner's Google account. `asked_by` is owner (the owner told the agent to; pass `owner_message`, the owner's own words) or agent (its own
	idea). An owner's request runs at once and is logged. An agent's own idea follows its switch: on its own runs, asks you waits for the owner's OK in Needs you
	(status waiting), off is refused. Returns status (done, waiting or failed), the action to follow and, for a done act, what Google answered."""
	permissions.require_login()
	space = permissions.resolve_space(space, write=True)
	key = (source_system or "").strip().lower()
	if not key:
		frappe.throw(_("An agent names itself with source_system."), title=_("Agent not named"))
	return acts.request(space, key, tool, parse(params, {}), asked_by, owner_message)


@frappe.whitelist(methods=["GET"])
def calendar_list(source_system: str | None = None, time_min: str | None = None, time_max: str | None = None, account: str | None = None, space: str | None = None):
	"""Events from the owner's Google calendar between two times (the next 14 days by default)."""
	permissions.require_login()
	space = permissions.resolve_space(space)
	params = {"time_min": time_min, "time_max": time_max, "account": account}
	if permissions.is_agent():
		key = (source_system or "").strip().lower()
		if not key:
			frappe.throw(_("An agent names itself with source_system."), title=_("Agent not named"))
		return acts.read(space, key, "calendar.list", params)
	return {"events": acts.calendar_list(space, frappe.session.user, params)}
