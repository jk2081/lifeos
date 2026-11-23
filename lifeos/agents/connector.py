"""The agent connector's side in Life OS (issue 85): what an agent reports, what waits for it, and what it confirms.

An agent runs a small script (`agent/connector/`) that sends its memory (facts), skills, jobs and settings when they change and once a day
(`report`), and picks up what the owner changed here (`pull`), applies it and says so (`confirm`). Plumbing only: records, a queue and
statuses. A change the owner makes is a `Life Agent Change`, *Waiting* until the connector confirms it (*Applied*) or says why it could not
(*Failed*, with the reason).
"""
import json

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime

from lifeos.agents import limits

FACT_EDIT, FACT_DELETE, JOB_PAUSE, JOB_RESUME, SETTING = "Fact edit", "Fact delete", "Job pause", "Job resume", "Setting"
FACT_KINDS, JOB_KINDS = (FACT_EDIT, FACT_DELETE), (JOB_PAUSE, JOB_RESUME)
DONE_STATES = ("Done", "Approved")
MAX_ROWS = 2000  # facts or jobs one report may carry


def _text(value, n) -> str:
	return " ".join(str(value or "").split())[:n]


def _same(doc, values) -> bool:
	return all((doc.get(k) or None) == (v or None) for k, v in values.items())


def _upsert(doctype: str, space: str, agent: str, external_id: str, values: dict) -> bool:
	"""Make the row for this external id say `values`; True when anything was written (a repeated report writes nothing)."""
	name = frappe.db.get_value(doctype, {"space": space, "agent": agent, "external_id": external_id})
	if name:
		doc = frappe.get_doc(doctype, name)
		if _same(doc, values):
			return False
		doc.update(values)
		doc.save(ignore_permissions=True)  # system: the agent's report; the space write check is in the API
		return True
	frappe.get_doc({"doctype": doctype, "space": space, "agent": agent, "external_id": external_id, **values}).insert(ignore_permissions=True)  # system: as above
	return True


def _waiting_targets(space: str, agent: str, kinds) -> set:
	return set(frappe.get_all("Life Agent Change", filters={"space": space, "agent": agent, "status": "Waiting", "kind": ("in", list(kinds))}, pluck="target"))  # system: the connector's own queue


def _check_rows(rows, what: str) -> list:
	if rows is None:
		return []
	if not isinstance(rows, list) or len(rows) > MAX_ROWS:
		frappe.throw(_("{0} must be a list of at most {1}.").format(what, MAX_ROWS), title=_("Report not understood"))
	return [r for r in rows if isinstance(r, dict) and _text(r.get("id"), 140)]


def _sync_facts(space, agent, facts) -> int:
	keep, wrote = set(), 0
	held = _waiting_targets(space, agent, FACT_KINDS)  # what the owner changed and the agent has not applied yet is not written over
	for r in _check_rows(facts, "facts"):
		ext = _text(r["id"], 140)
		keep.add(ext)
		if ext in held or not _text(r.get("text"), 500):
			continue
		learned = None
		try:
			learned = getdate(r["learned_on"]) if r.get("learned_on") else None
		except Exception:  # noqa: BLE001 - a date the agent could not format is left out, not an error
			learned = None
		wrote += _upsert("Life Agent Fact", space, agent, ext, {"fact": _text(r.get("text"), 500), "origin": _text(r.get("origin"), 140), "learned_on": learned})
	for name in frappe.get_all("Life Agent Fact", filters={"space": space, "agent": agent, "external_id": ("not in", list(keep) or [""])}, pluck="name"):  # system: the agent forgot it
		if frappe.db.get_value("Life Agent Fact", name, "external_id") not in held:
			frappe.delete_doc("Life Agent Fact", name, ignore_permissions=True, force=True)
			wrote += 1
	return wrote


def _sync_jobs(space, agent, jobs) -> int:
	keep, wrote = set(), 0
	held = _waiting_targets(space, agent, JOB_KINDS)
	for r in _check_rows(jobs, "jobs"):
		ext = _text(r["id"], 140)
		keep.add(ext)
		values = {"job_name": _text(r.get("name"), 140) or ext, "schedule": _text(r.get("schedule"), 140), "next_run": _text(r.get("next_run"), 60)}
		if ext not in held:
			values["paused"] = cint(bool(r.get("paused")))
		wrote += _upsert("Life Agent Job", space, agent, ext, values)
	for name in frappe.get_all("Life Agent Job", filters={"space": space, "agent": agent, "external_id": ("not in", list(keep) or [""])}, pluck="name"):  # system: the agent dropped it
		frappe.delete_doc("Life Agent Job", name, ignore_permissions=True, force=True)
		wrote += 1
	return wrote


def _sync_actions(space, agent, actions) -> int:
	"""What the agent did, or wants approval for. A decision the owner made is never written over by the report."""
	wrote = 0
	for r in _check_rows(actions, "actions"):
		ext = _text(r["id"], 140)
		status = "Waiting" if r.get("status") == "Waiting" else "Done"
		name = frappe.db.get_value("Life Agent Action", {"space": space, "agent": agent, "external_id": ext})
		when = None
		try:
			when = get_datetime(r["when"]) if r.get("when") else None
		except Exception:  # noqa: BLE001 - as for a fact's date
			when = None
		values = {"action": _text(r.get("action"), 60) or "other", "title": _text(r.get("title"), 200) or ext, "draft": str(r.get("draft") or "")[:5000], "cost": flt(r.get("cost")),
			"happened_on": when or now_datetime()}
		if name:
			doc = frappe.get_doc("Life Agent Action", name)
			if doc.status != "Waiting" and status == "Waiting":
				continue  # already decided
			values = {**values, "status": status} if status == "Done" else values
			values.pop("happened_on")  # the first time it was seen stands
			if not _same(doc, values):
				doc.update(values)
				doc.save(ignore_permissions=True)  # system: as above
				wrote += 1
		else:
			frappe.get_doc({"doctype": "Life Agent Action", "space": space, "agent": agent, "external_id": ext, "status": status, **values}).insert(ignore_permissions=True)  # system: as above
			wrote += 1
	return wrote


def _settle_settings(space, agent, settings):
	"""An agent that reports its own switches settles the waiting Setting changes it already matches."""
	if not isinstance(settings, dict) or not isinstance(settings.get("abilities"), dict):
		return
	for ch in frappe.get_all("Life Agent Change", filters={"space": space, "agent": agent, "status": "Waiting", "kind": SETTING}, fields=["name", "target", "payload"]):  # system: the connector's queue
		if settings["abilities"].get(ch.target) == (json.loads(ch.payload or "{}")).get("mode"):
			frappe.db.set_value("Life Agent Change", ch.name, {"status": "Applied", "applied_on": now_datetime()})


def report(space: str, system: str, user: str, facts=None, jobs=None, skills=None, settings=None, actions=None) -> dict:
	"""Take the agent's report: every list is the whole of it, so what it left out is gone from here. Says how many rows it wrote."""
	from lifeos.api import connections

	system = _text(system, 60).lower()
	if not system:
		frappe.throw(_("Say which agent is reporting (source_system)."), title=_("Agent not named"))
	connections.touch(space, system, "Report from the connector")
	cfg = limits.config(space, system, create=True)
	changed = {"facts": _sync_facts(space, system, facts) if facts is not None else 0, "jobs": _sync_jobs(space, system, jobs) if jobs is not None else 0,
		"actions": _sync_actions(space, system, actions) if actions is not None else 0}
	if skills is not None:
		clean = [{"name": _text(s.get("name"), 80), "description": _text(s.get("description"), 200)} for s in skills[:200] if isinstance(s, dict) and _text(s.get("name"), 80)] if isinstance(skills, list) else []
		text = json.dumps(clean)
		if cfg.skills != text:
			cfg.skills = text
			changed["skills"] = 1
	if cfg.agent_user != user:
		cfg.agent_user = user
		changed["agent_user"] = 1
	_settle_settings(space, system, settings)
	cfg.last_report = now_datetime()  # the agent was heard from; not a change of what it holds
	cfg.flags.ignore_permissions = True
	cfg.save()
	return {"changed": changed, "waiting": waiting_count(space, system)}


def waiting_count(space: str, agent: str) -> int:
	return frappe.db.count("Life Agent Change", {"space": space, "agent": agent, "status": "Waiting"})


def pull(space: str, system: str) -> dict:
	"""What the connector has to do: the owner's switches, the changes waiting, and the decisions on what it asked to do."""
	system = _text(system, 60).lower()
	cfg = limits.config(space, system)
	changes = [{"id": c.name, "kind": c.kind, "target": c.target, "payload": json.loads(c.payload or "{}")} for c in frappe.get_all("Life Agent Change",
		filters={"space": space, "agent": system, "status": "Waiting"}, fields=["name", "kind", "target", "payload"], order_by="creation asc", limit=500)]  # system: the connector's queue
	decisions = [{"id": a.external_id, "decision": "approved" if a.status == "Approved" else "declined"} for a in frappe.get_all("Life Agent Action",
		filters={"space": space, "agent": system, "status": ("in", ["Approved", "Declined"]), "delivered": 0, "external_id": ("is", "set")}, fields=["external_id", "status"], limit=500)]  # system: as above
	return {"abilities": limits.abilities(cfg), "changes": changes, "decisions": decisions}


def confirm(space: str, system: str, changes=None, delivered=None) -> dict:
	"""The connector says which changes it applied or could not, and which decisions it has picked up."""
	system = _text(system, 60).lower()
	applied = failed = 0
	for row in changes if isinstance(changes, list) else []:
		if not isinstance(row, dict):
			continue
		name = row.get("id")
		ch = frappe.db.get_value("Life Agent Change", {"name": name, "space": space, "agent": system}, ["name", "kind", "target", "payload", "status"], as_dict=True) if name else None
		if not ch or ch.status != "Waiting":
			continue  # unknown, or already settled: confirming twice changes nothing
		if row.get("status") == "failed":
			frappe.db.set_value("Life Agent Change", ch.name, {"status": "Failed", "reason": _text(row.get("reason"), 500) or _("The agent gave no reason."), "applied_on": now_datetime()})
			failed += 1
		else:
			_apply(space, system, ch)
			frappe.db.set_value("Life Agent Change", ch.name, {"status": "Applied", "applied_on": now_datetime()})
			applied += 1
	for ext in delivered if isinstance(delivered, list) else []:
		name = frappe.db.get_value("Life Agent Action", {"space": space, "agent": system, "external_id": _text(ext, 140)})
		if name:
			frappe.db.set_value("Life Agent Action", name, "delivered", 1)
	return {"applied": applied, "failed": failed}


def _apply(space, agent, ch):
	"""The change is done on the agent's side: make the copy here say so."""
	fact = frappe.db.get_value("Life Agent Fact", {"space": space, "agent": agent, "external_id": ch.target}) if ch.kind in FACT_KINDS else None
	job = frappe.db.get_value("Life Agent Job", {"space": space, "agent": agent, "external_id": ch.target}) if ch.kind in JOB_KINDS else None
	if ch.kind == FACT_EDIT and fact:
		frappe.db.set_value("Life Agent Fact", fact, {"fact": json.loads(ch.payload or "{}").get("text", ""), "is_stale": 0, "stale_reason": None})
	elif ch.kind == FACT_DELETE and fact:
		frappe.delete_doc("Life Agent Fact", fact, ignore_permissions=True, force=True)
	elif ch.kind in JOB_KINDS and job:
		frappe.db.set_value("Life Agent Job", job, "paused", int(ch.kind == JOB_PAUSE))


# ---- the owner's side: queue a change ----
def queue(space: str, agent: str, kind: str, target: str, payload: dict | None = None) -> str:
	"""Ask the agent to change something. A newer change to the same thing replaces one still waiting."""
	for old in frappe.get_all("Life Agent Change", filters={"space": space, "agent": agent, "status": "Waiting", "target": target, "kind": ("in", FACT_KINDS if kind in FACT_KINDS else JOB_KINDS if kind in JOB_KINDS else (kind,))}, pluck="name"):  # system: the connector's queue
		frappe.delete_doc("Life Agent Change", old, ignore_permissions=True, force=True)
	doc = frappe.get_doc({"doctype": "Life Agent Change", "space": space, "agent": agent, "kind": kind, "target": target, "payload": json.dumps(payload or {}), "status": "Waiting"})
	doc.insert(ignore_permissions=True)  # system: only the owner reaches this, in the API
	return doc.name
