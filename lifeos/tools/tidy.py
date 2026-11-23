"""Issue 9: tidy what was filed before issues 6, 7 and 8. Run by the owner on his own site:

	bench --site SITE execute lifeos.tools.tidy.run                          # dry run: reports, changes nothing
	bench --site SITE execute lifeos.tools.tidy.run --kwargs "{'apply': True}"

It finds duplicate stored files, jobs filed as one item with their inputs beside their outputs, and items Failed by the intent
refusal. With apply it first takes a backup with files (and stops if that fails), then merges the duplicates, moves the inputs
to reusable assets and puts the Failed items back to New. Every change is written to the site's `logs/lifeos_tidy.log` and as a
comment on the record it changed. Nothing a record uses is deleted, and no note, task or proposal is deleted at all."""
import logging
import os

import frappe
from frappe import _

from lifeos.tools.tidy_files import DuplicateFiles
from lifeos.tools.tidy_jobs import FailedIntents, MixedJobs


class TidyRefused(frappe.ValidationError):
	pass


def run(apply: bool = False, space: str | None = None):
	"""The bench entry point: prints the report (and with apply, what was done). `space` limits it to one space.
	Not whitelisted: only bench runs it."""
	tidy = Tidy(apply=bool(apply), commit=True, spaces=[space] if space else None)
	report = tidy.run()
	print(tidy.text(report))
	return report["summary"]


def take_backup():
	"""What `bench backup --with-files` does. Raises when any part of the backup is missing."""
	from frappe.utils.backups import new_backup

	odb = new_backup(ignore_files=False, force=True)
	paths = [odb.backup_path_db, odb.backup_path_files, odb.backup_path_private_files]
	missing = [p for p in paths if not p or not os.path.isfile(_site_relative(p)) or not os.path.getsize(_site_relative(p))]
	if missing:
		raise OSError(f"backup files missing or empty: {', '.join(str(p) for p in missing)}")
	return paths


class Tidy:
	def __init__(self, apply=False, commit=False, backup=take_backup, spaces=None):
		self.apply, self.commit, self.backup = apply, commit, backup
		self.actions = []
		self.logger = frappe.logger("lifeos_tidy", allow_site=True, file_count=20)
		self.logger.setLevel(logging.INFO)  # the site's level is WARNING; every change belongs in this log
		spaces = spaces or frappe.get_all("Life Space", pluck="name")
		self.duplicates = DuplicateFiles(self.log, spaces)
		self.jobs = MixedJobs(self.log, spaces)
		self.failed = FailedIntents(self.log, spaces)

	def run(self):
		frappe.only_for("System Manager")
		report = {"duplicates": self.duplicates.find(), "jobs": self.jobs.find(), "failed": self.failed.find(),
			"applied": False, "backup": None, "removed": []}
		if self.apply and self._has_work(report):
			report["backup"] = self._backup()
			report["removed"] = self._apply(report)
			report["applied"] = True
		report["actions"] = self.actions
		report["summary"] = _summary(report)
		return report

	def log(self, doctype, name, text):
		"""One change: to the action log file, and as a comment on the record it changed."""
		line = f"{doctype} {name}: {text}" if doctype else text
		self.actions.append(line)
		self.logger.info(line)
		if doctype and frappe.db.exists(doctype, name):
			frappe.get_doc(doctype, name).add_comment("Info", f"Tidy: {text}")

	def text(self, report):
		lines = [("Applied" if report["applied"] else "Dry run: nothing was changed") + "."]
		lines.append(f"Duplicate files: {len(report['duplicates'])}")
		for g in report["duplicates"]:
			lines.append(f"  {g['file_name']} in {g['space']}: keep {g['keep']['file_url']}")
			for c in g["copies"]:
				used = f" (named in the text of {', '.join(c['used_in_text'])}: left as it is)" if c["used_in_text"] else ""
				records = ", ".join(f"{r['doctype']} {r['name']}" for r in c["records"])
				lines.append(f"    copy {c['file_url']} used by {records}{used}")
			for t in g["twins"]:
				lines.append(f"    {t['doctype']} {t['name']} holds it twice: {t['drop']} goes, {t['keep']} stays")
		lines.append(f"Jobs with inputs beside outputs: {len(report['jobs'])}")
		for j in report["jobs"]:
			lines.append(f"  {j['item']} {j['title']}")
			lines += [f"    input  {f['file_name']} ({f['file']})" for f in j["inputs"]]
			lines += [f"    output {f['file_name']} ({f['file']})" for f in j["outputs"]]
		lines.append(f"Failed by the intent refusal: {len(report['failed'])}")
		lines += [f"  {r['name']} {r['title']}: {r['error']}" for r in report["failed"]]
		if report["backup"]:
			lines.append("Backup: " + ", ".join(report["backup"]))
		if report["applied"]:
			lines.append(f"Changes ({len(report['actions'])}), also in logs/lifeos_tidy.log:")
			lines += [f"  {a}" for a in report["actions"]]
		elif report["summary"]["to_do"]:
			lines.append("To apply: bench --site SITE execute lifeos.tools.tidy.run --kwargs \"{'apply': True}\"")
		return "\n".join(lines)

	# ---------- applying ----------

	def _has_work(self, report):
		return any(report[k] for k in ("duplicates", "jobs", "failed"))

	def _backup(self):
		try:
			paths = self.backup()
		except Exception as e:
			frappe.throw(_("The backup failed, so nothing was changed: {0}").format(str(e)), TidyRefused, title=_("Backup failed"))
		self.log(None, None, "Backup taken: " + ", ".join(str(p) for p in paths))
		return [str(p) for p in paths]

	def _apply(self, report):
		unused = []
		for group in report["duplicates"]:
			unused += self.duplicates.merge(group)
		for job in report["jobs"]:
			self.jobs.refile(job)
		for row in report["failed"]:
			self.failed.reset(row)
		if self.commit:  # the rows are saved before any stored copy leaves the disk
			frappe.db.commit()  # nosemgrep: frappe-manual-commit -- bench execute run: the copies are removed only after the rows that used them are saved
		return self.duplicates.remove_unused(unused)


def _summary(report):
	to_do = sum(len(report[k]) for k in ("duplicates", "jobs", "failed"))
	return {"applied": report["applied"], "to_do": to_do, "duplicates": len(report["duplicates"]), "jobs": len(report["jobs"]),
		"failed": len(report["failed"]), "changes": len(report["actions"]), "removed": len(report["removed"])}


def _site_relative(path):
	return path if os.path.isabs(path) else frappe.get_site_path("..", path)
