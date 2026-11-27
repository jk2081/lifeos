"""What must work, with no person at a terminal, before an update may change anything (issue 138).

The updater runs from cron. A restart and a restore that need a password would fail halfway through an update, so they are
checked first. `run` gives one dict for each check: {key, label, ok, fix}; the fix is one line a person can follow."""
import getpass
from pathlib import Path


def sudoers_fix() -> str:
	return f"Life OS can't restart the site's services without a password. On the server, as root: `bench setup sudoers {getpass.getuser()}`. Then try again."


RESTORE_FIX = ("Life OS can't load a backup into the site's database with the site's own user. Check `db_name` and `db_password` in the site's "
	"site_config.json and that the `mariadb` client is installed. Then try again.")


def restart_mode(run, bench_path) -> str | None:
	"""'sudo' when `sudo -n supervisorctl restart all` is allowed, 'bench' when the bench is not under Supervisor, else None."""
	if run(["sudo", "-n", "-l", "supervisorctl", "restart", "all"]).returncode == 0:
		return "sudo"
	return None if Path(bench_path, "config", "supervisor.conf").exists() else "bench"


def restart_fix(reason: str = "") -> str:
	return f"bench setup sudoers {getpass.getuser()}" if "sudo" in (reason or "").lower() else "bench restart"


def restore_works(run, bench, site) -> bool:
	"""The site's own database user answers through `bench --site <site> mariadb`: the way a backup is loaded."""
	return run([bench, "--site", site, "mariadb"], text_in="select 1;").returncode == 0


def ready(sh, bench_path, bench, site) -> list[dict]:
	"""`sh(args, text_in=None)` runs a command and answers its returncode; a test passes a fake."""
	return [
		{"key": "restart", "label": "Restart the site's services without a password", "ok": restart_mode(sh, bench_path) is not None, "fix": sudoers_fix()},
		{"key": "restore", "label": "Restore a backup without a password", "ok": restore_works(sh, bench, site), "fix": RESTORE_FIX},
	]
