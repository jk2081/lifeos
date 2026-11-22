"""When a skill runs: a document event, a schedule, or a button. Always in a background job on the long queue, never in the web request."""
import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

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


UNCLAIMED_MINUTES = 30  # an agent's capture nobody claimed in this long goes to the Brain


def agent_acts(user: str | None = None) -> bool:
	"""True when `user` is an agent other than the Brain itself: what it files is its own."""
	from lifeos import permissions

	user = user or frappe.session.user
	return user != permissions.BRAIN_USER and permissions.is_agent(user)


def capture_created(doc, method=None):
	"""The one rule for who processes a capture (issue 58). What an agent files itself is that agent's: it claims it, or files the
	finished job in one call. Everything else (+ Capture, the phone, email read by Life OS, a retry by a person) is the Brain's, now.
	A capture an agent made and did not claim goes to the Brain after 30 minutes (`route_unclaimed`)."""
	if doc.status != "New" or doc.is_archived:
		return
	if agent_acts():
		return
	route(doc)


def route(doc):
	"""Hand a New capture to the Brain: the skills that wait for a new capture (switched off ones are skipped, and the capture waits
	for an agent). One run for each saved version of the capture, so a reply that brings a Done capture back is processed again."""
	extra = {"at": str(doc.modified)}
	_fire("Capture created", doc, extra)
	if doc.source_type in EMAIL_SOURCES:
		_fire("Email filed", doc, extra)


def route_unclaimed():
	"""Every 5 minutes: captures an agent made or last filed, still New after 30 minutes, are the Brain's."""
	from lifeos import permissions

	cutoff = add_to_date(now_datetime(), minutes=-UNCLAIMED_MINUTES)
	agents = [u for u in frappe.get_all("Has Role", filters={"role": "Life Agent", "parenttype": "User"}, pluck="parent") if u != permissions.BRAIN_USER]
	if not agents:
		return 0
	n = 0
	for name in frappe.get_all("Life Inbox Item", filters={"status": "New", "is_archived": 0, "modified": ("<", cutoff)}, or_filters=[
			["owner", "in", agents], ["modified_by", "in", agents]], pluck="name", limit=50):
		doc = frappe.get_doc("Life Inbox Item", name)
		before = frappe.db.count("Life Skill Run", {"input_name": name})
		route(doc)
		n += frappe.db.count("Life Skill Run", {"input_name": name}) - before
	return n


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
