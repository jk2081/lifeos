"""An agent's page (issue 85): what it waits for, knows, can do, may read, has scheduled and did, and what the owner changed that it has not
yet applied. The agent is shown under the name the owner gives it; the product never names the agent's maker.
"""
import json

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, getdate, now_datetime, nowdate

from lifeos.agents import connector, limits

DECISIONS = {"approve": "Approved", "no": "Declined"}


def is_agent_key(space: str, key: str) -> bool:
	"""A source that is an agent: a connection that is neither a kind nor one of the channels Life OS reads itself."""
	from lifeos.brain import source_page

	return not source_page.is_kind(key) and key not in (c[0] for c in source_page.CHANNELS) and bool(frappe.db.exists("Life Connection", {"space": space, "system": key}))


def _week_start():
	d = getdate(nowdate())
	return add_to_date(d, days=-d.weekday())


def _waiting_by_target(space: str, agent: str) -> dict:
	"""{(kind group, target): change} for what the owner changed and the agent has not confirmed; a failed one shows until it is replaced."""
	out = {}
	for c in frappe.get_all("Life Agent Change", filters={"space": space, "agent": agent, "status": ("in", ["Waiting", "Failed"])},
			fields=["name", "kind", "target", "status", "reason", "payload", "creation"], order_by="creation asc"):  # system: this agent's queue, read by the owner
		out[("fact" if c.kind in connector.FACT_KINDS else "job" if c.kind in connector.JOB_KINDS else "setting", c.target)] = c
	return out


def _change_out(c) -> dict | None:
	return {"name": c.name, "kind": c.kind, "status": c.status.lower(), "reason": c.reason} if c else None


def requests(space: str, agent: str | None = None) -> list:
	"""What agents want to do that needs the owner's OK, oldest first: the same rows on an agent's page and in Needs you."""
	filters = {"space": space, "status": "Waiting", **({"agent": agent} if agent else {})}
	rows = frappe.get_all("Life Agent Action", filters=filters, fields=["name", "agent", "action", "title", "draft", "happened_on"], order_by="happened_on asc, creation asc", limit=100)  # system: the owner's list; the space check is in the API
	names = {c.agent: limits.display_name(limits.config(space, c.agent)) for c in rows}
	labels = dict(limits.ACTIONS)
	return [{"name": r.name, "agent": r.agent, "agent_name": names[r.agent], "action": r.action, "action_label": labels.get(r.action, r.action), "title": r.title, "draft": r.draft,
		"when": str(r.happened_on)[:16]} for r in rows]


def sections(space: str, key: str) -> dict:
	cfg = limits.config(space, key)
	held = _waiting_by_target(space, key)
	facts = [{"name": f.name, "id": f.external_id, "text": f.fact, "origin": f.origin, "learned_on": str(f.learned_on) if f.learned_on else None, "stale": int(f.is_stale or 0),
		"stale_reason": f.stale_reason, "change": _change_out(held.get(("fact", f.external_id)))} for f in frappe.get_all("Life Agent Fact", filters={"space": space, "agent": key},
		fields=["name", "external_id", "fact", "origin", "learned_on", "is_stale", "stale_reason"], order_by="learned_on desc, creation desc", limit=500)]  # system: this agent's memory, read by the owner
	for f in facts:  # a waiting edit shows what the owner wrote
		if f["change"] and f["change"]["kind"] == connector.FACT_EDIT:
			f["text"] = json.loads(frappe.db.get_value("Life Agent Change", f["change"]["name"], "payload") or "{}").get("text", f["text"])
	jobs = [{"name": j.name, "id": j.external_id, "title": j.job_name, "schedule": j.schedule, "next_run": j.next_run, "paused": int(j.paused or 0),
		"change": _change_out(held.get(("job", j.external_id)))} for j in frappe.get_all("Life Agent Job", filters={"space": space, "agent": key},
		fields=["name", "external_id", "job_name", "schedule", "next_run", "paused"], order_by="job_name asc", limit=200)]  # system: as above
	for j in jobs:  # a waiting pause or resume shows the state the owner asked for
		if j["change"] and j["change"]["status"] == "waiting":
			j["paused"] = int(j["change"]["kind"] == connector.JOB_PAUSE)
	modes = limits.abilities(cfg)
	can = [{"key": k, "label": label, "mode": modes[k], "fixed": int(k == "pay"), "change": _change_out(held.get(("setting", k)))} for k, label in limits.ACTIONS]
	off = set(limits._below(space, set(limits.areas_off(cfg))))
	areas = [{"name": a.name, "title": a.area_name, "on": int(a.name not in off)} for a in frappe.get_all("Life Area", filters={"space": space, "is_on": 1, "is_archived": 0, "is_life_area": 1},
		fields=["name", "area_name"], order_by="sort_order asc, creation asc", limit=50)]  # system: the owner's own areas
	rows = frappe.get_all("Life Agent Action", filters={"space": space, "agent": key, "status": ("in", list(connector.DONE_STATES)), "happened_on": (">=", _week_start())},
		fields=["name", "action", "title", "status", "cost", "happened_on"], order_by="happened_on desc, creation desc", limit=200)  # system: as above
	did = [{"name": r.name, "action": r.action, "title": r.title, "status": r.status, "cost": flt(r.cost), "when": str(r.happened_on)[:16]} for r in rows]
	return {"name": limits.display_name(cfg), "has_name": int(bool(cfg and cfg.display_name)), "reported": str(cfg.last_report)[:16] if cfg and cfg.last_report else None,
		"waiting": requests(space, key), "facts": facts, "can": can, "areas": areas, "vault": "off", "jobs": jobs, "did": did,
		"cost_week": round(sum(d["cost"] for d in did), 4), "skills": json.loads(cfg.skills) if cfg and cfg.skills else [],
		"changes": {"waiting": sum(1 for c in held.values() if c.status == "Waiting"), "failed": sum(1 for c in held.values() if c.status == "Failed")}}


def _fact(space: str, key: str, name: str):
	doc = frappe.get_doc("Life Agent Fact", name) if frappe.db.exists("Life Agent Fact", {"name": name, "space": space, "agent": key}) else None
	if not doc:
		frappe.throw(_("That fact is not in this agent's memory."), frappe.DoesNotExistError, title=_("Fact not found"))
	return doc


def edit_fact(space: str, key: str, name: str, text: str) -> dict:
	text = " ".join((text or "").split())
	if not text:
		frappe.throw(_("A fact cannot be empty. Delete it instead."), title=_("Fact is empty"))
	doc = _fact(space, key, name)
	connector.queue(space, key, connector.FACT_EDIT, doc.external_id, {"text": text[:500]})
	return sections(space, key)


def delete_fact(space: str, key: str, name: str) -> dict:
	doc = _fact(space, key, name)
	connector.queue(space, key, connector.FACT_DELETE, doc.external_id)
	return sections(space, key)


def pause_job(space: str, key: str, name: str, paused: bool) -> dict:
	row = frappe.db.get_value("Life Agent Job", {"name": name, "space": space, "agent": key}, ["external_id", "paused"], as_dict=True)
	if not row:
		frappe.throw(_("That job is not in this agent's schedule."), frappe.DoesNotExistError, title=_("Job not found"))
	connector.queue(space, key, connector.JOB_PAUSE if paused else connector.JOB_RESUME, row.external_id)
	return sections(space, key)


def set_ability(space: str, key: str, action: str, mode: str) -> dict:
	cfg = limits.config(space, key, create=True)
	if limits.abilities(cfg).get(action) != mode:
		limits.set_ability(cfg, action, mode)
		connector.queue(space, key, connector.SETTING, action, {"mode": mode})
	return sections(space, key)


def set_area(space: str, key: str, area: str, on: bool) -> dict:
	limits.set_area(limits.config(space, key, create=True), area, on)  # Life OS enforces it itself: nothing for the connector to apply
	return sections(space, key)


def rename(space: str, key: str, name: str) -> dict:
	cfg = limits.config(space, key, create=True)
	cfg.display_name = " ".join((name or "").split())[:80] or None
	cfg.save(ignore_permissions=True)  # system: only the owner reaches this, in the API
	return sections(space, key)


def decide(space: str, name: str, decision: str, user: str) -> dict:
	"""Approve or say no to something an agent waits to do. The agent picks the decision up on its next pull."""
	status = DECISIONS.get(decision)
	row = frappe.db.get_value("Life Agent Action", {"name": name, "space": space}, ["name", "agent", "status"], as_dict=True)
	if not status or not row:
		frappe.throw(_("Choose approve or no, for a request in this space."), frappe.DoesNotExistError, title=_("Request not found"))
	if row.status != "Waiting":
		frappe.throw(_("That was already decided."), title=_("Already decided"))
	frappe.db.set_value("Life Agent Action", row.name, {"status": status, "decided_by": user, "decided_on": now_datetime(), "delivered": 0,
		**({"happened_on": now_datetime()} if status == "Approved" else {})})
	return {"name": row.name, "agent": row.agent, "status": status}


def flag_stale(space: str, key: str, name: str, reason: str | None) -> None:
	"""The Brain thinks a fact is out of date (or no longer thinks so, with no reason): the page flags it for the owner to keep or change."""
	doc = _fact(space, key, name)
	frappe.db.set_value("Life Agent Fact", doc.name, {"is_stale": int(bool(reason)), "stale_reason": (reason or "")[:140] or None})
