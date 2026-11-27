"""Tests for the updater (Settings > Advanced > Updates): who may ask, the check, the runner's steps, rollback and restart, the checks
before anything changes, the restore through the site's own user, and the installed commit."""
import frappe

from lifeos.updater.shell import StepError
from lifeos.tests.base import FAMILY, LifeTestCase, OWNER


class TestUpdater(LifeTestCase):
	"""Settings > Advanced > Updates (issue 103): who may ask, the check against a temporary repository, the runner's steps and its
	rollback, a target that is not on the remote, and one runner at a time."""

	def setUp(self):
		super().setUp()
		import shutil
		import tempfile

		self.tmp = tempfile.mkdtemp(prefix="lifeos-upd-")
		self.addCleanup(shutil.rmtree, self.tmp, True)
		self.addCleanup(self.clean)

	def clean(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Life Update", pluck="name"):  # system: the test's own requests
			frappe.db.delete("Notification Log", {"document_type": "Life Update", "document_name": name})
			frappe.delete_doc("Life Update", name, force=True, ignore_permissions=True)  # system: the test's own requests
		frappe.db.set_single_value("Life Settings", "updater_heartbeat", None)
		frappe.db.set_single_value("Life Settings", "update_state", None)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the runner under test commits, so the test cleans up with a commit

	def git(self, repo, *args):
		import subprocess

		return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.t", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()

	def repos(self):
		"""A remote with one commit, and a clone of it; then a second commit on the remote. Returns (remote, clone, second sha)."""
		import os

		remote, clone = os.path.join(self.tmp, "remote"), os.path.join(self.tmp, "clone")
		os.makedirs(remote)
		self.git(remote, "init", "-q", "-b", "main")
		with open(os.path.join(remote, "a.txt"), "w") as f:
			f.write("one")
		self.git(remote, "add", ".")
		self.git(remote, "commit", "-q", "-m", "First")
		self.git(self.tmp, "clone", "-q", remote, clone)
		os.makedirs(os.path.join(remote, "lifeos", "patches"))
		with open(os.path.join(remote, "lifeos", "patches", "p.py"), "w") as f:
			f.write("x = 1")
		self.git(remote, "add", ".")
		self.git(remote, "commit", "-q", "-m", "Merge pull request #5 from jk2081/batch-9", "-m", "Goals get a result bar")
		return remote, clone, self.git(remote, "rev-parse", "HEAD")

	def request(self, commit="b" * 40):
		return frappe.get_doc({"doctype": "Life Update", "to_commit": commit, "summary": "One\nTwo"}).insert()

	def steps(self, fail=None, refuse=False, message=None):
		calls = []

		class Fake:
			def __getattr__(me, name):
				def step(*args):
					calls.append(name if not args else (name, *args))
					if (refuse and name == "verify") or name == fail:
						raise StepError(message) if message else RuntimeError("it broke | token=abc123")  # a real step's own message is already safe
					return {"backup": "BK", "record": "a" * 40}.get(name)
				return step

		return Fake(), calls

	def test_1_only_the_owner_can_ask_for_an_update(self):
		from lifeos.api import updates

		self.as_user(FAMILY)
		with self.assertRaises(frappe.PermissionError):
			self.request()
		with self.assertRaises(frappe.PermissionError):
			updates.get()
		self.as_user(OWNER)
		doc = self.request("C" * 40)
		self.assertEqual((doc.status, doc.to_commit, doc.requested_by), ("Queued", "c" * 40, OWNER))
		with self.assertRaises(frappe.ValidationError):
			self.request("not a commit; rm -rf /")

	def test_2_the_check_finds_the_newer_commit_and_its_title(self):
		from lifeos.updater import status

		remote, clone, second = self.repos()
		out = status.check(repo=clone, remote_name="origin", branch_name="main")
		self.assertIsNone(out["error"])
		self.assertEqual(out["available"]["commit"], second)
		self.assertEqual([c["title"] for c in out["available"]["changes"]], ["Goals get a result bar"])
		self.assertTrue(out["available"]["migrations"])
		self.assertEqual(out["installed"]["title"], "First")
		self.assertEqual(status.state()["available"]["commit"], second)
		self.git(clone, "pull", "-q", "origin", "main")  # up to date: nothing is offered
		self.assertIsNone(status.check(repo=clone, remote_name="origin", branch_name="main")["available"])

	def test_3_the_runner_goes_through_the_steps_then_rolls_back_a_failed_migrate(self):
		from lifeos.updater import runner

		fake, calls = self.steps()
		doc = self.request()
		self.assertEqual(runner.execute(doc, fake), "Done")
		self.assertEqual([c if isinstance(c, str) else c[0] for c in calls],
			["verify", "backup", "record", "maintenance_on", "checkout", "requirements", "migrate", "build", "restart", "health", "maintenance_off"])
		self.assertIn(("checkout", doc.to_commit), calls)  # the live site failed here: checkout was called without the commit
		self.assertEqual(frappe.db.get_value("Life Update", doc.name, "status"), "Done")
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": OWNER, "document_name": doc.name}))

		fake, calls = self.steps(fail="migrate")
		doc = self.request()
		self.assertEqual(runner.execute(doc, fake), "Rolled back")
		tail = [c if isinstance(c, str) else c[0] for c in calls][6:]
		self.assertEqual(tail, ["migrate", "rollback_checkout", "restore", "build", "restart", "maintenance_off"])
		self.assertIn(("rollback_checkout", "a" * 40), calls)
		log = frappe.db.get_value("Life Update", doc.name, "log")
		self.assertIn("migrate: failed", log)
		self.assertNotIn("abc123", log)  # a line that looks like a secret never reaches the log

		fake, calls = self.steps(fail="requirements")  # before migrate started: the checkout is undone, the database is not restored
		doc = self.request()
		self.assertEqual(runner.execute(doc, fake), "Rolled back")
		self.assertNotIn("restore", [c if isinstance(c, str) else c[0] for c in calls])

	def test_4_a_commit_that_is_not_on_the_remote_is_refused_before_any_step(self):
		from lifeos.updater import runner

		fake, calls = self.steps(refuse=True)
		doc = self.request()
		self.assertEqual(runner.execute(doc, fake), "Failed")
		self.assertEqual(calls, [("verify", doc.to_commit)])
		# the real check: a commit of the remote's history passes, one that is not there is refused
		remote, clone, second = self.repos()
		real = self.real_steps(clone)
		real.verify(second)
		with self.assertRaises(RuntimeError):
			real.verify("d" * 40)

	def test_5_a_second_runner_leaves_when_the_lock_is_held(self):
		from lifeos.updater import runner, status

		self.assertFalse(status.runner_alive())
		doc = self.request()
		fake, calls = self.steps()
		with runner.lock() as mine:
			self.assertTrue(mine)
			self.assertEqual(runner.run_once(fake), "locked")
		self.assertEqual(calls, [])
		self.assertEqual(frappe.db.get_value("Life Update", doc.name, "status"), "Queued")
		self.assertTrue(status.runner_alive())  # the heartbeat is written either way
		self.assertEqual(runner.run_once(fake), "Done")

	def test_6_update_now_needs_a_runner_and_something_newer(self):
		from lifeos.api import updates
		from lifeos.updater import status

		with self.assertRaises(frappe.ValidationError):
			updates.request_update()
		status.save_state({"installed": {"commit": "a" * 40}, "available": {"commit": "e" * 40, "changes": [{"title": "Thing"}]}})
		with self.assertRaises(frappe.ValidationError):  # no heartbeat
			updates.request_update()
		status.heartbeat()
		out = updates.request_update()
		self.assertEqual((out["history"][0]["status"], out["history"][0]["to_commit"], out["busy"]), ("Queued", "e" * 40, True))
		with self.assertRaises(frappe.ValidationError):  # one at a time
			updates.request_update()

	# --- issue 138: check before changing, no rollback of a good migrate, a restore without root, a failure that says why, the truth on the page

	def real_steps(self, clone=None, supervised=True, sudo_ok=True, mariadb_ok=True):
		"""The real BenchSteps with a fake shell: it records every command, and `sudo -n -l` and `bench ... mariadb` answer as asked."""
		import os
		from types import SimpleNamespace

		from lifeos.updater import runner

		bench_path = os.path.join(self.tmp, "bench")
		os.makedirs(os.path.join(bench_path, "config"), exist_ok=True)
		conf = os.path.join(bench_path, "config", "supervisor.conf")
		if supervised:
			open(conf, "w").close()
		elif os.path.exists(conf):
			os.remove(conf)
		real = runner.BenchSteps.__new__(runner.BenchSteps)
		real.repo, real.remote, real.branch, real.site, real.bench, real.bench_path = clone, "origin", "main", frappe.local.site, "bench", bench_path
		real.commands = []

		def run(args, cwd=None, timeout=3600, text_in=None):
			real.commands.append(list(args))
			bad = (args[0] == "sudo" and not sudo_ok) or (args[-1] == "mariadb" and not mariadb_ok)
			return SimpleNamespace(returncode=1 if bad else 0, stdout="", stderr="")

		real.run = run
		return real

	def test_7_a_restart_that_needs_a_password_refuses_before_anything_changes(self):
		from lifeos.updater import runner

		remote, clone, second = self.repos()
		before = self.git(clone, "rev-parse", "HEAD")
		real = self.real_steps(clone, sudo_ok=False)
		doc = self.request(second)
		self.assertEqual(runner.execute(doc, real), "Failed")
		self.assertEqual(self.git(clone, "rev-parse", "HEAD"), before)  # nothing was checked out
		self.assertEqual([c[0] for c in real.commands], ["sudo", "bench"])  # only the checks ran: no backup, no migrate
		log = frappe.db.get_value("Life Update", doc.name, "log")
		self.assertIn("bench setup sudoers", log)
		self.assertIn("Refused: nothing was changed.", log)
		self.assertFalse(frappe.conf.get("maintenance_mode"))
		# a bench not under Supervisor needs no sudo for `bench restart`
		self.assertTrue(all(c["ok"] for c in self.real_steps(clone, supervised=False, sudo_ok=False).ready()))
		# a restore that cannot run is refused too, with its own fix
		doc = self.request(second)
		self.assertEqual(runner.execute(doc, self.real_steps(clone, mariadb_ok=False)), "Failed")
		self.assertIn("site_config.json", frappe.db.get_value("Life Update", doc.name, "log"))

	def test_8_only_the_restart_failed_so_nothing_is_rolled_back(self):
		from lifeos.api import updates
		from lifeos.updater import runner, status

		message = "Life OS can't restart the site's services without a password. On the server, as root: `bench setup sudoers frappe`. Then try again."
		fake, calls = self.steps(fail="restart", message=message)
		doc = self.request()
		self.assertEqual(runner.execute(doc, fake), "Needs restart")
		names = [c if isinstance(c, str) else c[0] for c in calls]
		self.assertEqual(names[-3:], ["build", "restart", "maintenance_off"])
		self.assertNotIn("rollback_checkout", names)
		self.assertNotIn("restore", names)
		row = frappe.db.get_value("Life Update", doc.name, ["status", "reason", "fix"], as_dict=True)
		self.assertEqual(row.status, "Needs restart")
		self.assertIn("without a password", row.reason)
		self.assertIn("bench setup sudoers", row.fix)
		self.as_user(OWNER)
		status.heartbeat()
		self.assertEqual(updates.get()["history"][0]["status"], "Needs restart")
		updates.restart_now()
		self.assertEqual(frappe.db.get_value("Life Update", doc.name, "status"), "Queued")
		fake, calls = self.steps()  # the services restart this time
		self.assertEqual(runner.run_once(fake), "Done")
		self.assertEqual(calls, ["restart", "health"])
		self.assertEqual(frappe.db.get_value("Life Update", doc.name, ["status", "reason"]), ("Done", ""))
		with self.assertRaises(frappe.ValidationError):  # nothing is waiting for a restart any more
			updates.restart_now()

	def test_9_a_failed_migrate_still_rolls_back_with_the_restore(self):
		from lifeos.updater import runner

		fake, calls = self.steps(fail="migrate")
		doc = self.request()
		self.assertEqual(runner.execute(doc, fake), "Rolled back")
		names = [c if isinstance(c, str) else c[0] for c in calls]
		self.assertEqual(names[names.index("migrate"):], ["migrate", "rollback_checkout", "restore", "build", "restart", "maintenance_off"])

	def test_10_a_failed_step_says_what_ran_what_it_returned_and_what_it_printed(self):
		import os

		from lifeos.updater import runner, shell

		real = runner.BenchSteps.__new__(runner.BenchSteps)
		real.bench_path = self.tmp
		with self.assertRaises(shell.StepError) as quiet:
			real.sh("false")
		self.assertEqual(str(quiet.exception), "`false` exit 1, no output")
		script = "for i in $(seq 1 15); do echo out$i; done; echo err1 >&2; echo password=hunter2; echo token=abc >&2; exit 3"
		with self.assertRaises(shell.StepError) as loud:
			real.sh("sh", "-c", script, "api_key=zzz")
		said = str(loud.exception)
		self.assertIn("exit 3", said)
		self.assertIn("stdout", said)
		self.assertIn("stderr", said)
		self.assertIn("out15", said)
		self.assertNotIn("out5\n", said)  # only the last lines
		self.assertIn("err1", said)
		for secret in ("hunter2", "token=abc", "api_key=zzz"):
			self.assertNotIn(secret, said)
		# git says why too, and the log keeps the lines
		remote, clone, second = self.repos()
		with self.assertRaises(shell.StepError) as git_says:
			from lifeos.updater import git

			git.run(clone, "checkout", "no-such-branch")
		self.assertIn("exit 1", str(git_says.exception))
		self.assertIn("no-such-branch", str(git_says.exception))
		self.assertTrue(os.path.isdir(clone))

	def test_11_the_restore_through_the_sites_own_user_loads_a_real_backup(self):
		import os

		from frappe.utils.backups import new_backup

		from lifeos.updater import runner

		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the backup reads what is committed, and the restore replaces the tables
		# only this table: the whole test database (100,000 index rows) is more than the Docker MariaDB's memory takes to load back
		odb = new_backup(ignore_files=True, force=True, include_doctypes="Life Update")
		backup = {"db": odb.backup_path_db}
		self.addCleanup(lambda: os.path.exists(backup["db"]) and os.remove(backup["db"]))
		doc = self.request()
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- written after the backup, so the restore must take it away
		self.assertTrue(frappe.db.exists("Life Update", doc.name))
		real = runner.BenchSteps()
		self.assertTrue(real.ready()[1]["ok"], "the site's own user cannot reach the database through bench mariadb")
		real.restore(backup)
		self.assertFalse(frappe.db.exists("Life Update", doc.name))  # the dump put the database back as it was
		self.assertEqual(frappe.db.sql("select 1")[0][0], 1)  # the site answers afterwards
		self.assertTrue(frappe.db.get_single_value("System Settings", "enable_scheduler") is not None)
		self.assertTrue(frappe.db.exists("DocType", "Life Update"))

	def test_12_installed_is_what_git_says_and_an_update_to_it_is_refused(self):
		from unittest.mock import patch

		from lifeos.api import updates
		from lifeos.updater import status

		remote, clone, second = self.repos()
		first = self.git(clone, "rev-parse", "HEAD")
		self.as_user(OWNER)
		status.heartbeat()
		status.save_state({"installed": {"commit": "a" * 40, "short": "aaaaaaa"}, "available": {"commit": second, "short": second[:7], "changes": [{"title": "Thing"}]}})
		with patch.object(status, "repo_path", return_value=clone):
			out = updates.get()
			self.assertEqual(out["installed"]["commit"], first)  # not the saved value
			self.assertEqual(out["available"]["commit"], second)
			self.git(clone, "pull", "-q", "origin", "main")  # the folder moves on: the saved "available" is already installed
			out = updates.get()
			self.assertEqual(out["installed"]["commit"], second)
			self.assertIsNone(out["available"])
			with self.assertRaises(frappe.ValidationError) as refused:
				updates.request_update()
			self.assertIn("up to date", str(refused.exception))
		self.assertFalse(frappe.db.exists("Life Update", {"to_commit": second}))

	def test_13_update_now_is_refused_while_a_check_has_a_cross(self):
		from lifeos.api import updates
		from lifeos.updater import status

		self.as_user(OWNER)
		status.heartbeat()
		fix = "Life OS can't restart the site's services without a password. On the server, as root: `bench setup sudoers frappe`. Then try again."
		state = {"installed": {"commit": "a" * 40}, "available": {"commit": "e" * 40, "changes": [{"title": "Thing"}]},
			"ready": [{"key": "restart", "label": "Restart", "ok": False, "fix": fix}, {"key": "restore", "label": "Restore", "ok": True, "fix": ""}]}
		status.save_state(state)
		with self.assertRaises(frappe.ValidationError) as refused:
			updates.request_update()
		self.assertIn("bench setup sudoers", str(refused.exception))
		self.assertEqual(len(updates.get()["ready"]), 2)
		state["ready"][0]["ok"] = True
		status.save_state(state)
		self.assertEqual(updates.request_update()["history"][0]["status"], "Queued")
