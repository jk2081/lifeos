"""The agent connector (issue 85): the three calls the small script on the agent's server makes. `report` sends the agent's memory, skills, jobs,
settings and actions; `pull` returns what the owner changed in Life OS; `confirm` says what it applied or could not. No change to the agent's own code."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.agents import connector
from lifeos.api.utils import parse
from lifeos.brain import source_page


def _system(space: str, source_system: str) -> str:
	key = (source_system or "").strip().lower()
	if not key or source_page.is_kind(key) or key in (c[0] for c in source_page.CHANNELS):
		frappe.throw(_("Name the agent with its own source_system, not one of Life OS's own sources."), title=_("Agent not named"))
	return key


@frappe.whitelist(methods=["POST"])
def report(source_system: str, facts: str | list | None = None, jobs: str | list | None = None, skills: str | list | None = None, settings: str | dict | None = None,
		actions: str | list | None = None, space: str | None = None):
	"""Send everything the agent holds, when it changes and once a day. `facts`: [{id, text, origin, learned_on}], `jobs`: [{id, name, schedule, next_run, paused, last_status, last_run, last_error}],
	`skills`: [{name, description}], `settings`: {abilities: {action: on its own, asks you or off}}, `actions`: [{id, action, title, draft, status (Done or Waiting), cost, when}].
	Each list is the whole of it: what is left out is dropped from Life OS. A repeated report changes nothing. A list left out is not touched."""
	permissions.require_login()
	space = permissions.resolve_space(space, write=True)
	return connector.report(space, _system(space, source_system), frappe.session.user, parse(facts) if facts is not None else None, parse(jobs) if jobs is not None else None,
		parse(skills) if skills is not None else None, parse(settings) if settings is not None else None, parse(actions) if actions is not None else None)


@frappe.whitelist(methods=["GET"])
def pull(source_system: str, space: str | None = None):
	"""What to do now: `abilities` (the owner's switch for each action), `changes` waiting (edit or delete a fact, pause or resume a job, a setting) and
	`decisions` on what the agent asked to do, and `assistant_name`, what the owner calls the agent (write it into the agent's settings). Apply them, then call `confirm`."""
	permissions.require_login()
	space = permissions.resolve_space(space)
	return connector.pull(space, _system(space, source_system))


@frappe.whitelist(methods=["POST"])
def confirm(source_system: str, changes: str | list | None = None, delivered: str | list | None = None, space: str | None = None):
	"""Say what was done: `changes` [{id, status: applied or failed, reason}] and `delivered` [the ids of the decisions picked up]."""
	permissions.require_login()
	space = permissions.resolve_space(space, write=True)
	return connector.confirm(space, _system(space, source_system), parse(changes) if changes is not None else None, parse(delivered) if delivered is not None else None)
