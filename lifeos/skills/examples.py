"""A skill's examples are its tests: a sample input and checks on what the skill makes of it.

Built-in examples live in `lifeos/skills/examples/<skill>/*.json`, each with the recorded model answer (the fixture) CI replays: fast,
free and repeatable. A fixture belongs to one text of the skill: a changed skill without re-recorded fixtures fails CI, with a message
saying how to record them. `eval` runs the examples against the real model with the owner's key, on demand; `record` writes the fixtures.
"""
import json
from pathlib import Path

import frappe
from frappe import _

from lifeos.ai import client
from lifeos.skills import runner, store

DIR = Path(__file__).parent / "examples"


def files_of(slug) -> list:
	return sorted((DIR / slug).glob("*.json"))


def install(slug):
	"""Load a built-in skill's example files as Life Skill Example records (the owner's own examples are left alone)."""
	for path in files_of(slug):
		data = json.loads(path.read_text())
		row = frappe.db.get_value("Life Skill Example", {"skill": slug, "title": data["title"], "source": "Built-in"})
		doc = frappe.get_doc("Life Skill Example", row) if row else frappe.get_doc({"doctype": "Life Skill Example", "skill": slug, "source": "Built-in"})
		doc.update({"title": data["title"], "input": json.dumps(data["input"], ensure_ascii=False), "expected": json.dumps(data["checks"]),
			"fixture": json.dumps(data.get("fixture") or []), "fixture_hash": data.get("skill_hash")})
		doc.save(ignore_permissions=True) if row else doc.insert(ignore_permissions=True)


def evaluate(checks, output, proposals) -> list:
	"""[(check, passed, detail)]: each check is one of summary_contains, has_proposal {kind, area, title_contains, min_confidence},
	no_proposal {kind}, proposal_count {min, max}, waits (every proposal is below the auto-file threshold)."""
	results = []
	summary = (output or {}).get("summary_md", "") if isinstance(output, dict) else ""
	for check in checks:
		(name, arg), = check.items()
		ok, detail = False, ""
		if name == "summary_contains":
			ok = str(arg).lower() in summary.lower()
		elif name == "has_proposal":
			ok = any(_matches(p, arg) for p in proposals)
		elif name == "no_proposal":
			ok = not any(p["kind"] == arg.get("kind") for p in proposals) if arg.get("kind") else not proposals
		elif name == "proposal_count":
			ok = arg.get("min", 0) <= len(proposals) <= arg.get("max", 999)
			detail = f"{len(proposals)} proposals"
		results.append({"check": check, "passed": bool(ok), "detail": detail})
	return results


def _matches(p, want) -> bool:
	pay = p.get("payload") or {}
	if want.get("kind") and p["kind"] != want["kind"]:
		return False
	if want.get("area") and str(pay.get("area", "")).lower() != want["area"].lower():
		return False
	if want.get("title_contains") and want["title_contains"].lower() not in str(pay.get("title", p.get("preview", ""))).lower():
		return False
	return not want.get("min_confidence") or float(p.get("confidence") or 0) >= want["min_confidence"]


def run_example(skill, example, text_hash, live=None, space=None):
	"""Run one example against `skill` (a dict, so a draft text can be tried before it is saved). Uses the recorded answer when the
	text is the one it was recorded for, else the real model. Returns {title, passed, checks, source}."""
	sample = json.loads(example.input) if isinstance(example.input, str) else example.input
	checks = json.loads(example.expected) if isinstance(example.expected, str) else example.expected
	fixture = json.loads(example.fixture) if example.fixture else []
	replay = fixture if (fixture and example.fixture_hash == text_hash and live is not True) else None
	if replay is None and not client.is_set_up():
		return {"title": example.title, "passed": False, "source": "none", "checks": [],
			"error": _("This text has no recorded answers yet, and no AI key is set to try it with.")}
	space = space or frappe.db.get_single_value("Life Settings", "default_space")
	source = "recorded" if replay is not None else "model"
	try:
		state = runner.generate(skill, space, runner.blocks_of_sample(sample), intent=sample.get("intent") or "Process", replay=replay, lenient=True)
	except runner.SkillError as e:
		return {"title": example.title, "passed": False, "source": source, "error": e.reason, "checks": []}
	results = evaluate(checks, state["output"], state["proposals"])
	return {"title": example.title, "passed": all(r["passed"] for r in results), "checks": results, "source": source,
		"output": state["output"], "proposals": state["proposals"], "cost": state["cost"]}


def run_all(slug, draft: dict | None = None, live=None, space=None) -> list:
	"""Every example of a skill against its text, or against `draft` (the unsaved text and settings) when given."""
	doc = frappe.get_doc("Life Skill", slug)
	skill = {**runner.skill_values(doc), **({k: v for k, v in draft.items() if k in ("instructions", "output_schema", "cost_limit")} if draft else {})}
	if draft and draft.get("tools") is not None:
		skill["tools"] = draft["tools"] if isinstance(draft["tools"], list) else json.loads(draft["tools"])
	text_hash = store.digest({**doc.as_dict(), **(draft or {}), "tools": json.dumps(skill["tools"])})
	out = []
	for name in frappe.get_all("Life Skill Example", filters={"skill": slug}, pluck="name", order_by="creation asc"):
		res = run_example(skill, frappe.get_doc("Life Skill Example", name), text_hash, live, space)
		out.append(res)
		if not draft:
			frappe.db.set_value("Life Skill Example", name, "last_result", "Pass" if res["passed"] else "Fail")
	return out


def shipped_skill(slug) -> dict:
	"""A built-in skill as shipped (its file), as the runner takes it."""
	shipped = store.builtin(slug)
	return {"name": slug, "version": shipped["version"], "instructions": shipped["instructions"], "tools": json.loads(shipped["tools"]),
		"output_schema": shipped.get("output_schema"), "model_tier": shipped.get("model_tier") or "Fast", "cost_limit": float(shipped.get("cost_limit") or 0)}


def record(slug):
	"""Run each example of a built-in skill against the real model and write the answers into the example files."""
	skill, text_hash = shipped_skill(slug), store.digest(store.builtin(slug))
	space = frappe.db.get_single_value("Life Settings", "default_space")
	for path in files_of(slug):
		data = json.loads(path.read_text())
		state = runner.generate(skill, space, runner.blocks_of_sample(data["input"]), intent=data["input"].get("intent") or "Process", lenient=True)
		results = evaluate(data["checks"], state["output"], state["proposals"])
		data["fixture"], data["skill_hash"] = state["responses"], text_hash
		path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
		print(("PASS " if all(r["passed"] for r in results) else "FAIL ") + data["title"])
