"""What is installed, what is on the remote, and whether the runner is alive (Settings > Advanced > Updates).

The state is kept in Life Settings, written by the hourly job, by Check now and by the runner. The web page only reads it."""
import json
from pathlib import Path

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from lifeos.updater import git

REMOTE = "origin"
BRANCH = "main"
ALIVE_MINUTES = 5


def repo_path() -> str:
	return str(Path(frappe.get_app_path("lifeos")).parent)


def remote() -> str:
	return frappe.conf.get("lifeos_update_remote") or REMOTE


def branch() -> str:
	return frappe.conf.get("lifeos_update_branch") or BRANCH


def state() -> dict:
	raw = frappe.db.get_single_value("Life Settings", "update_state")
	try:
		return json.loads(raw) if raw else {}
	except ValueError:
		return {}


def save_state(value: dict):
	frappe.db.set_single_value("Life Settings", "update_state", json.dumps(value))


def heartbeat():
	frappe.db.set_single_value("Life Settings", "updater_heartbeat", now_datetime())


def last_seen():
	return frappe.db.get_single_value("Life Settings", "updater_heartbeat")


def runner_alive() -> bool:
	seen = last_seen()
	return bool(seen) and get_datetime(seen) > add_to_date(now_datetime(), minutes=-ALIVE_MINUTES)


def check(repo=None, remote_name=None, branch_name=None) -> dict:
	"""Read the installed commit, ask the remote for its newest, and list what a fetch brings. Never changes the checkout."""
	repo = repo or repo_path()
	remote_name = remote_name or remote()
	branch_name = branch_name or branch()
	out = {"checked_at": str(now_datetime()), "branch": branch_name, "error": None, "available": None}
	try:
		out["installed"] = git.describe(repo, "HEAD")
	except git.GitError as e:
		out["installed"] = None
		out["error"] = str(e)
		save_state(out)
		return out
	try:
		head = git.remote_head(repo, remote_name, branch_name)
		if head != out["installed"]["commit"]:
			git.fetch(repo, remote_name, branch_name)
			tip = f"refs/remotes/{remote_name}/{branch_name}"
			changes = git.changes_between(repo, "HEAD", tip)
			# a remote that is only behind the installed commit offers nothing
			if changes:
				out["available"] = {"commit": head, "short": head[:7], "date": changes[0]["date"], "changes": changes,
					"migrations": git.has_migrations(repo, "HEAD", tip)}
	except git.GitError as e:
		out["error"] = f"Could not reach the remote: {e}"
	save_state(out)
	return out


def check_hourly():
	"""The hourly job. Never raises: a failed check is kept in the state and shown on the page."""
	try:
		check()
	except Exception:
		frappe.log_error(title="Life OS update check")


def check_in_background():
	"""Check now: the web worker queues it, a background worker runs git."""
	frappe.enqueue("lifeos.updater.status.check_hourly", queue="short", enqueue_after_commit=True)
