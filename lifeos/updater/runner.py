"""The update runner (issue 103). It runs outside the web workers, as the bench's own user, with fixed steps only.

`run_once` is what the minute's cron line calls (`bench --site <site> lifeos-update`): it writes a heartbeat, takes a lock so
one update runs at a time, and works the oldest Queued Life Update through `execute`. The steps themselves are the methods of a
steps object (`BenchSteps` for real, a fake in the tests). A request carries only a commit; nothing a person typed reaches a shell."""
import fcntl
import os
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import frappe
from frappe.utils import now_datetime

from lifeos.updater import git, status

# the steps, in order; maintenance mode is switched off by the last
ORDER = ("backup", "record", "maintenance_on", "checkout", "requirements", "migrate", "build", "restart", "health", "maintenance_off")
SECRET = re.compile(r"(secret|token|password|passwd|api[_-]?key|authorization|bearer)", re.I)
# the only untracked path a checkout may remove: the link `bench build` makes to the app's node_modules
BUILD_LINKS = ("lifeos/public/node_modules",)
TAIL = 4


class StepFailed(Exception):
	pass


@contextmanager
def lock():
	"""Yield True when this process holds the update lock, False when another runner has it. The lock goes when the process ends."""
	path = Path(frappe.get_site_path("locks", "lifeos_update.lock"))
	path.parent.mkdir(parents=True, exist_ok=True)
	handle = path.open("w")
	try:
		fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
	except OSError:
		handle.close()
		yield False
		return
	try:
		yield True
	finally:
		fcntl.flock(handle, fcntl.LOCK_UN)
		handle.close()


def run_once(steps=None) -> str:
	"""One tick of the cron line: 'idle', 'locked', or the status the request ended with."""
	status.heartbeat()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the runner is a background process: each step's outcome is saved at once
	with lock() as held:
		if not held:
			return "locked"
		_stop_crashed()
		name = frappe.db.get_value("Life Update", {"status": "Queued"}, "name", order_by="creation asc")
		if not name:
			return "idle"
		return execute(frappe.get_doc("Life Update", name), steps or BenchSteps())


def _stop_crashed():
	"""A request still Running while this process holds the lock belongs to a runner that died: say so, touch nothing else."""
	for name in frappe.get_all("Life Update", filters={"status": "Running"}, pluck="name"):  # system: the runner works for no one user
		log = frappe.db.get_value("Life Update", name, "log") or ""
		frappe.db.set_value("Life Update", name, {"status": "Failed", "finished": now_datetime(),
			"log": log + "\nThe runner stopped during this update. Nothing was undone: check the site, and restore the backup if it is broken."})
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the runner is a background process: each step's outcome is saved at once


class Log:
	"""The request's log, kept in memory and written whole after every line (a restore can replace the database under it)."""

	def __init__(self, doc):
		self.doc = doc
		self.lines = []

	def add(self, text):
		self.lines.append(f"{now_datetime().strftime('%H:%M:%S')}  {text}")
		self.save()

	def save(self, **fields):
		values = {"log": "\n".join(self.lines), **fields}
		if frappe.db.exists("Life Update", self.doc.name):
			frappe.db.set_value("Life Update", self.doc.name, values, update_modified=False)
		else:  # the database was restored to a point before this request's row
			self.doc.update(values)
			self.doc.db_insert()
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the runner is a background process: each step's outcome is saved at once

	def step(self, name, fn, *args):
		try:
			result = fn(*args)
		except Exception as e:
			self.add(f"{name}: failed. {scrub(str(e))}")
			raise StepFailed(name) from e
		self.add(f"{name}: ok")
		return result


def scrub(text: str) -> str:
	"""A failure's last lines, without any line that looks like it holds a secret."""
	lines = [x.strip() for x in str(text).splitlines() if x.strip() and not SECRET.search(x)]
	return " | ".join(lines[-TAIL:])[:600]


def execute(doc, steps) -> str:
	"""Work one request through the steps. Returns the status it ended with."""
	log = Log(doc)
	log.save(status="Running", started=now_datetime())
	try:
		log.step("verify target", steps.verify, doc.to_commit)
	except StepFailed:
		log.add("Refused: nothing was changed.")
		return _finish(doc, log, "Failed")
	old = backup = None
	switched = changed = migrating = False
	try:
		backup = log.step("backup", steps.backup)
		old = log.step("record commit", steps.record)
		log.add(f"was at {str(old)[:7]}, going to {doc.to_commit[:7]}")
		for name in ORDER[2:]:
			if name == "maintenance_on":
				switched = True
			elif name == "checkout":
				changed = True
			elif name == "migrate":
				migrating = True
			args = (doc.to_commit,) if name == "checkout" else ()  # the one step that needs the target
			log.step(name, getattr(steps, name), *args)
		return _finish(doc, log, "Done")
	except StepFailed:
		return _finish(doc, log, _roll_back(log, steps, old, backup, switched, changed, migrating))


def _roll_back(log, steps, old, backup, switched, changed, migrating) -> str:
	"""Put the site back as it was. Each part is tried even when an earlier one failed; the restore only when migrate had started."""
	if not changed:
		if switched:
			_try(log, "maintenance_off", steps.maintenance_off)
		log.add("Nothing had changed.")
		return "Failed"
	log.add("Rolling back.")
	if old:
		_try(log, "check out the old commit", steps.rollback_checkout, old)
	if migrating and backup:
		_try(log, "restore the backup", steps.restore, backup)
	_try(log, "build", steps.build)
	_try(log, "restart", steps.restart)
	_try(log, "maintenance_off", steps.maintenance_off)
	return "Rolled back"


def _try(log, name, fn, *args):
	try:
		log.step(name, fn, *args)
	except StepFailed:
		pass


def _finish(doc, log, result) -> str:
	log.save(status=result, finished=now_datetime())
	try:
		_notify(doc, result)
	except Exception:
		frappe.log_error(title="Life OS update notice")
	return result


def _notify(doc, result):
	if not doc.requested_by:
		return
	if result == "Done":
		n = len([x for x in (doc.summary or "").splitlines() if x.strip()])
		subject = f"Life OS updated to {doc.to_commit[:7]}: {n} change{'s' if n != 1 else ''}"
	elif result == "Rolled back":
		subject = "Update failed and was rolled back"
	else:
		subject = "Update failed; nothing was changed"
	frappe.get_doc({"doctype": "Notification Log", "for_user": doc.requested_by, "from_user": doc.requested_by, "type": "Alert", "subject": subject,
		"document_type": "Life Update", "document_name": doc.name}).insert(ignore_permissions=True)  # system: the runner tells the person who asked
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the runner is a background process: each step's outcome is saved at once


class BenchSteps:
	"""The real steps. Every command is a fixed list run without a shell; the log gets each step's name and outcome only."""

	def __init__(self):
		self.site = frappe.local.site
		self.repo = status.repo_path()
		self.remote = status.remote()
		self.branch = status.branch()
		self.bench_path = str(Path(frappe.get_app_path("lifeos")).parents[2])
		self.bench = shutil.which("bench") or str(Path.home() / ".local" / "bin" / "bench")
		self.started = None

	def sh(self, *args, cwd=None, timeout=3600):
		try:
			out = subprocess.run(list(args), cwd=cwd or self.bench_path, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, check=False)  # noqa: S603 -- fixed arguments
		except (OSError, subprocess.TimeoutExpired) as e:
			raise RuntimeError(f"{Path(args[0]).name} did not run: {type(e).__name__}") from e
		if out.returncode:
			raise RuntimeError(f"{Path(args[0]).name} {args[1] if len(args) > 1 else ''} exited {out.returncode}: {scrub(out.stderr or out.stdout)}")
		return out.stdout

	def verify(self, commit):
		git.fetch(self.repo, self.remote, self.branch)
		if not git.on_remote_branch(self.repo, self.remote, self.branch, commit):
			raise RuntimeError(f"{commit[:7]} is not on {self.remote}/{self.branch}")

	def backup(self):
		from frappe.utils.backups import new_backup

		odb = new_backup(ignore_files=False, force=True)
		return {"db": odb.backup_path_db, "public": odb.backup_path_files, "private": odb.backup_path_private_files}

	def record(self):
		return git.run(self.repo, "rev-parse", "HEAD")

	def maintenance_on(self):
		from frappe.installer import update_site_config

		update_site_config("maintenance_mode", 1)

	def maintenance_off(self):
		from frappe.installer import update_site_config

		update_site_config("maintenance_mode", 0)
		self.wait_for_ping(want_pong=True, seconds=60)

	def checkout(self, commit):
		for link in BUILD_LINKS:
			path = Path(self.repo, link)
			if path.is_symlink():
				path.unlink()
		git.fetch(self.repo, self.remote, self.branch)
		git.run(self.repo, "checkout", "-B", self.branch, commit)

	def rollback_checkout(self, commit):
		for link in BUILD_LINKS:
			path = Path(self.repo, link)
			if path.is_symlink():
				path.unlink()
		git.run(self.repo, "checkout", "-B", self.branch, commit)

	def requirements(self):
		self.sh(self.bench, "setup", "requirements", "--python", "lifeos")
		self.sh(self.bench, "setup", "requirements", "--node", "lifeos")

	def migrate(self):
		self.sh(self.bench, "--site", self.site, "migrate")

	def build(self):
		self.sh(self.bench, "build", "--app", "lifeos")

	def restart(self):
		self.started = now_datetime()
		if subprocess.run(["sudo", "-n", "-l", "supervisorctl", "restart", "all"], capture_output=True, check=False).returncode == 0:  # noqa: S603, S607
			self.sh("sudo", "-n", "supervisorctl", "restart", "all")
		else:
			self.sh(self.bench, "restart")

	def restore(self, backup):
		args = [self.bench, "--site", self.site, "--force", "restore", backup["db"]]
		for flag, key in (("--with-public-files", "public"), ("--with-private-files", "private")):
			if backup.get(key):
				args += [flag, backup[key]]
		self.sh(*args)
		frappe.db.close()
		frappe.connect()

	def wait_for_ping(self, want_pong=False, seconds=120):
		"""The site answers /api/method/ping. In maintenance mode Frappe answers SessionStopped, which also shows the app is up."""
		import requests

		port = frappe.conf.get("webserver_port") or 8000
		deadline = time.time() + seconds
		while time.time() < deadline:
			try:
				r = requests.get(f"http://127.0.0.1:{port}/api/method/ping", headers={"Host": self.site}, timeout=5)
				if (r.status_code == 200 and "pong" in r.text) or (not want_pong and "SessionStopped" in r.text):
					return
			except requests.RequestException:
				pass
			time.sleep(3)
		raise RuntimeError("the site does not answer /api/method/ping")

	def health(self):
		self.wait_for_ping()
		time.sleep(int(frappe.conf.get("lifeos_update_settle") or 30))
		conf = frappe.get_site_config()
		if conf.get("disable_scheduler") or not frappe.db.get_single_value("System Settings", "enable_scheduler"):
			raise RuntimeError("the scheduler is not enabled")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the runner is a background process: a fresh view of the table
		since = self.started or now_datetime()
		fresh = frappe.db.count("Error Log", {"creation": [">", since]})
		if fresh:
			raise RuntimeError(f"{fresh} new Error Log row(s) after the restart")
