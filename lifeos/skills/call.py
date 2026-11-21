"""Asking a skill about data the caller already has: `ask(slug, data, space)`.

The judgment of Life OS (what to keep, park or drop, what to plan, what to notice) lives in skills. The code around it only gathers
the data, calls this, and uses the answer; with no key, no budget, a switched-off skill or a failed call there is no answer, and the
caller shows nothing (the items wait in Needs you). The call goes through the same runner and gateway as every skill (cost caps,
the shape check) and is logged as a run, so Brain > Skills shows it with its version.
"""
import json
import time

import frappe
from frappe import _

from lifeos.ai import client
from lifeos.skills import examples, runner, store


class Answer:
	"""What a skill said. False when it said nothing; `reason` then says why, and `label` is "plan-week v1" when it answered."""

	def __init__(self, output=None, label=None, reason=None):
		self.output, self.label, self.reason = output, label, reason

	def __bool__(self):
		return self.output is not None

	def get(self, key, default=None):
		return (self.output or {}).get(key, default) if isinstance(self.output, dict) else default


def blocks_of(slug: str, data) -> list:
	"""The request: the caller's data as JSON, with its angle brackets escaped and marked as data, not instructions."""
	return [{"type": "text", "text": f'<input skill="{slug}">\n{runner._data(json.dumps(data, default=str, ensure_ascii=False))}\n</input>'}]


def _skill(slug):
	"""The skill as the owner has it (their edits count), or as shipped when the site has not installed it yet; None when switched off."""
	row = frappe.db.get_value("Life Skill", slug, ["active"], as_dict=True)
	if not row:
		return {**examples.shipped_skill(slug), "card": False, "patient": False}
	if not row.active:
		return None
	return {**runner.skill_values(frappe.get_doc("Life Skill", slug)), "card": False, "patient": False}


def ask(slug: str, data, space: str | None = None, reference: tuple | None = None, replay: list | None = None, user: str | None = None) -> Answer:
	"""Run skill `slug` on `data`. Returns an Answer: its JSON output and the label to show ("Suggested by plan-week v1"), or a false
	Answer saying why not."""
	skill = _skill(slug)
	if not skill:
		return Answer(reason=_("the skill is switched off"))
	try:
		client.check(f"Skill: {slug}")
	except client.NotSetUp:
		return Answer(reason=_("no AI key"))
	except client.CapReached as e:
		return Answer(reason=str(e)[:200])
	skill["user"] = user  # whose cost it is, when a job runs it for someone (the nightly jobs run as Administrator)
	space = space or frappe.db.get_single_value("Life Settings", "default_space")
	started, log = time.monotonic(), {"output": None, "error": None, "input_tokens": 0, "output_tokens": 0, "cost": 0, "retries": 0}
	try:
		state = runner.generate(skill, space, blocks_of(slug, data), reference=reference, replay=replay)
		log.update(output=json.dumps(state["output"], ensure_ascii=False)[:60000], input_tokens=state["tin"], output_tokens=state["tout"],
			cost=state["cost"], retries=state["retries"])
		output = state["output"]
	except runner.SkillError as e:
		log.update(error=e.reason, **{k: v for k, v in e.usage.items() if k in log})
		output = None
	_log(slug, skill["version"], space, log, time.monotonic() - started)
	if output is None:
		return Answer(reason=log["error"])
	return Answer(output, store.label(slug, skill["version"]))


def _log(slug, version, space, log, seconds):
	frappe.get_doc({"doctype": "Life Skill Run", "skill": slug, "skill_version": version, "trigger": "Button", "space": space,
		"run_key": f"call|{slug}|{frappe.generate_hash(length=10)}", "status": "Failed" if log["error"] else "Done",
		"duration": round(seconds, 2), **log}).insert(ignore_permissions=True)
