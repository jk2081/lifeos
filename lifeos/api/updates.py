"""Settings > Advanced > Updates: what is installed, what is on the repository, and one click to update (issue 103).
The web app only reads state and records a request; the runner (lifeos/updater/runner.py) does the work outside the web workers."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.updater import status

HISTORY = 20


def _owner_only():
	permissions.require_login()
	if not (permissions.is_admin() or "System Manager" in frappe.get_roles()):
		frappe.throw(_("Only the owner can update Life OS."), frappe.PermissionError, title=_("Only the owner can update"))


def _history():
	return frappe.get_list("Life Update", fields=["name", "from_commit", "to_commit", "requested_by", "requested_on", "status", "reason", "fix", "summary", "started", "finished", "log"],
		order_by="creation desc", limit=HISTORY)


@frappe.whitelist(methods=["GET"])
def get():
	"""The Updates page: installed, available, whether the runner is alive (or the command that sets it up), and the history."""
	_owner_only()
	s = status.state()
	busy = frappe.db.exists("Life Update", {"status": ["in", ["Queued", "Running"]]})
	# the installed commit is read from the app's folder now; a saved value can be older than the folder
	return {"installed": status.installed() or s.get("installed"), "available": status.available_now(s), "checked_at": s.get("checked_at"), "error": s.get("error"),
		"ready": s.get("ready") or [],
		"branch": s.get("branch") or status.branch(),
		"runner": {"alive": status.runner_alive(), "last_seen": status.last_seen(), "setup_command": f"bench --site {frappe.local.site} lifeos-setup-updater"},
		"busy": bool(busy), "history": _history()}


@frappe.whitelist(methods=["POST"])
def check_now():
	"""Ask a background worker to look at the repository again. The page reads the new state when `checked_at` changes."""
	_owner_only()
	status.check_in_background()
	return {"queued": True}


@frappe.whitelist(methods=["POST"])
def request_update():
	"""Queue an update to the newest commit found by the last check. Only a commit hash is stored; the runner checks it is on the remote branch."""
	_owner_only()
	state = status.state()
	available = status.available_now(state)
	if not available:
		if state.get("available"):
			frappe.throw(_("You're up to date."), title=_("You're up to date"))
		frappe.throw(_("There is nothing newer to install. Check again first."), title=_("Nothing to install"))
	for check in state.get("ready") or []:
		if not check.get("ok"):
			frappe.throw(check.get("fix") or _("A check failed."), title=_("Not ready to update"))
	if not status.runner_alive():
		frappe.throw(_("The updater is not running on this server. Set it up first."), title=_("The updater is not running"))
	if frappe.db.exists("Life Update", {"status": ["in", ["Queued", "Running"]]}):
		frappe.throw(_("An update is already waiting or running."), title=_("An update is in progress"))
	doc = frappe.get_doc({"doctype": "Life Update", "to_commit": available["commit"],
		"summary": "\n".join(c["title"] for c in available.get("changes", []))})
	doc.insert()
	return get()


@frappe.whitelist(methods=["POST"])
def restart_now():
	"""Run the restart step again for the update that Needs restart. The runner does it; the page only records the request."""
	_owner_only()
	name = frappe.db.get_value("Life Update", {"status": "Needs restart"}, "name", order_by="creation desc")
	if not name:
		frappe.throw(_("Nothing is waiting for a restart."), title=_("No restart needed"))
	if not status.runner_alive():
		frappe.throw(_("The updater is not running on this server. Set it up first."), title=_("The updater is not running"))
	if frappe.db.exists("Life Update", {"status": ["in", ["Queued", "Running"]]}):
		frappe.throw(_("An update is already waiting or running."), title=_("An update is in progress"))
	frappe.db.set_value("Life Update", name, {"status": "Queued", "restart_only": 1})
	return get()
