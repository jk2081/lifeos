"""Bench commands of Life OS: `bench --site <site> lifeos-update` (the runner's tick) and `lifeos-setup-updater` (issue 103)."""
import shlex
import shutil
import subprocess
from pathlib import Path

import click
import frappe
from frappe.commands import get_site, pass_context


@click.command("lifeos-update")
@pass_context
def lifeos_update(context):
	"""One tick of the updater: write the heartbeat and run the oldest queued update, if any. Run every minute by cron."""
	from lifeos.updater import runner

	site = get_site(context)
	frappe.init(site)
	frappe.connect()
	try:
		click.echo(runner.run_once())
	finally:
		frappe.destroy()


def cron_line(site: str, bench_path: str, bench: str, path: str) -> str:
	log = Path(bench_path, "logs", "lifeos-update.log")
	return (f"* * * * * cd {shlex.quote(bench_path)} && PATH={shlex.quote(path)} {shlex.quote(bench)} --site {shlex.quote(site)} lifeos-update "
		f">> {shlex.quote(str(log))} 2>&1")


@click.command("lifeos-setup-updater")
@pass_context
def lifeos_setup_updater(context):
	"""Install the one crontab line that runs the updater every minute, and check that git can fetch (the deploy key)."""
	import os

	from lifeos.updater import git, status

	site = get_site(context)
	frappe.init(site)
	frappe.connect()
	try:
		bench_path = str(Path(frappe.get_app_path("lifeos")).parents[2])
		bench = shutil.which("bench") or str(Path.home() / ".local" / "bin" / "bench")
		line = cron_line(site, bench_path, bench, os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"))
		click.echo(f"Crontab line for this user:\n{line}")
		have = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False).stdout  # noqa: S603, S607
		if line in have.splitlines():
			click.echo("Already installed.")
		else:
			kept = "\n".join(x for x in have.splitlines() if "lifeos-update" not in x)
			new = (kept + "\n" if kept else "") + line + "\n"
			done = subprocess.run(["crontab", "-"], input=new, text=True, capture_output=True, check=False)  # noqa: S603, S607
			click.echo("Installed." if done.returncode == 0 else "Could not install it: add the line above with `crontab -e`.")
		try:
			git.remote_head(status.repo_path(), status.remote(), status.branch())
			click.echo(f"git can reach {status.remote()}/{status.branch()}.")
		except git.GitError as e:
			click.echo(f"git cannot reach the remote: {e}. Check the deploy key.")
	finally:
		frappe.destroy()


commands = [lifeos_update, lifeos_setup_updater]
