"""When a skill runs: a document event, a schedule, or a button. Always in a background job on the long queue, never in the web request."""
import frappe
from frappe.utils import get_datetime, now_datetime

from lifeos.skills import runner

# the fixed list of events a skill can wait for: (event name) -> what the hook checks
EVENTS = {"Capture created": "capture", "Email filed": "email", "Record changed": "record"}
EMAIL_SOURCES = ("Email", "Email Digest")


def queue(skill, input, trigger):
	"""Make the Queued run (once per skill, input and version) and put it on the long queue. Returns its name, or None when the same run exists."""
	log = runner.new_run(skill, input, trigger)
	if not log:
		return None
	frappe.enqueue("lifeos.skills.runner.execute", queue="long", timeout=1800, enqueue_after_commit=True, run_name=log.name)
	return log.name


def _skills_for(event, space):
	return [s for s in frappe.get_all("Life Skill", filters={"active": 1, "trigger_kind": "Event", "trigger_event": event}, fields=["name", "space"])
		if not s.space or s.space == space]


def _fire(event, doc, extra=None):
	for row in _skills_for(event, doc.get("space")):
		queue(frappe.get_doc("Life Skill", row.name), {"doctype": doc.doctype, "name": doc.name, "space": doc.get("space"), **(extra or {})}, event)


def capture_created(doc, method=None):
	"""A capture is created that no agent has claimed (it is New). #58 will refine which captures are the Brain's."""
	if doc.status != "New" or doc.is_archived:
		return
	_fire("Capture created", doc)
	if doc.source_type in EMAIL_SOURCES:
		_fire("Email filed", doc)


def record_changed(doc, method=None):
	"""A task, goal or note changed. One run for each saved version of the record."""
	if frappe.flags.in_import or frappe.flags.in_migrate:
		return
	_fire("Record changed", doc, {"at": str(doc.modified)})


def run_due():
	"""Every 5 minutes: start the scheduled skills that are due, one run for each space they cover."""
	from croniter import croniter

	now = now_datetime()
	for row in frappe.get_all("Life Skill", filters={"active": 1, "trigger_kind": "Schedule"}, fields=["name", "schedule_cron", "space", "modified"]):
		if not row.schedule_cron or not croniter.is_valid(row.schedule_cron):
			continue
		last = frappe.db.get_value("Life Skill Run", {"skill": row.name, "trigger": "Schedule"}, "creation", order_by="creation desc") or row.modified
		due = croniter(row.schedule_cron, get_datetime(last)).get_next(type(now))
		if due > now:
			continue
		skill = frappe.get_doc("Life Skill", row.name)
		for space in [row.space] if row.space else frappe.get_all("Life Space", pluck="name"):
			queue(skill, {"space": space, "at": str(due)}, "Schedule")
