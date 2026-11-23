"""Skills (issue 28): list and read them (agents are served them here), run one from a button, and, for the owner, edit them with
versions, test them against their examples and see their runs. Code is plumbing; what a skill decides is in its text."""
import builtins
import json

import frappe
from frappe import _
from frappe.query_builder import functions as fn
from frappe.utils import get_first_day, now_datetime

from lifeos import permissions
from lifeos.brain.proposals import SCHEMA
from lifeos.api.utils import parse
from lifeos.skills import examples, filing, lessons, store, triggers
from lifeos.skills import tools as fixed

LIST = list  # this module defines its own `list` method below


def _people_only():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Skills are edited by people."), frappe.PermissionError, title=_("Only people edit skills"))


def _admin_only():
	_people_only()
	if not permissions.is_admin():
		frappe.throw(_("Only the owner can change skills."), frappe.PermissionError, title=_("Only the owner edits skills"))


def _skill(name):
	"""A skill the caller may see: for all spaces, or for a space they belong to."""
	permissions.require_login()
	if not frappe.db.exists("Life Skill", name):
		frappe.throw(_("There is no skill called {0}.").format(name), frappe.DoesNotExistError, title=_("Skill not found"))
	doc = frappe.get_doc("Life Skill", name)
	if doc.space and doc.space not in permissions.user_spaces() and not permissions.is_admin():
		frappe.throw(_("There is no skill called {0}.").format(name), frappe.DoesNotExistError, title=_("Skill not found"))
	return doc


# ---- served to agents and people ----
@frappe.whitelist(methods=["GET"])
def list(space: str | None = None):
	"""The active skills for the caller's spaces (or one space), with their version, so an agent can cache them and fetch a skill
	again only when its version changed."""
	permissions.require_login()
	if space:
		permissions.require_space(space)
	return [{"name": r.name, "title": r.title, "when_to_use": r.when_to_use, "version": r.version, "space": r.space, "source": r.source,
		"kind": r.trigger_kind} for r in store.visible() if not space or not r.space or r.space == space]


@frappe.whitelist(methods=["GET"])
def get(name: str, space: str | None = None):
	"""One skill: its text and version. A skill for one space is served only to members of that space."""
	doc = _skill(name)
	if not doc.active:
		frappe.throw(_("The skill {0} is switched off.").format(name), frappe.DoesNotExistError, title=_("Skill is switched off"))
	if space and doc.space and doc.space != space:
		frappe.throw(_("There is no skill called {0} for that space.").format(name), frappe.DoesNotExistError, title=_("Skill not found in space"))
	return {"name": doc.name, "title": doc.title, "when_to_use": doc.when_to_use, "version": doc.version, "space": doc.space,
		"source": doc.source, "instructions": doc.instructions}


# ---- a button ----
@frappe.whitelist(methods=["POST"])
def run(skill: str, input: str | dict | None = None):
	"""Start a skill whose trigger is a Button on one record, {doctype, name}. It runs in a background job; the answer names the run.
	The same skill, input and version is run once."""
	_people_only()
	doc = _skill(skill)
	if not doc.active or doc.trigger_kind != "Button":
		frappe.throw(_("{0} is not a skill a button runs, or it is switched off.").format(skill), title=_("Skill cannot run here"))
	data = parse(input) or {}
	if not isinstance(data, dict) or not data.get("doctype") or not data.get("name"):
		frappe.throw(_("input must be {doctype, name}."), title=_("Input is malformed"))
	record = permissions.get_doc_checked(data["doctype"], data["name"])
	name = triggers.queue(doc, {"doctype": record.doctype, "name": record.name, "space": record.get("space")}, "Button")
	return {"run": name, "queued": bool(name)}


# ---- Brain > Skills ----
def _month_rows():
	start = get_first_day(now_datetime())
	run = frappe.qb.DocType("Life Skill Run")
	rows = frappe.qb.get_query("Life Skill Run", fields=[run.skill, fn.Count("*").as_("runs"), fn.Sum(run.cost).as_("cost")], ignore_permissions=False)
	return {r.skill: r for r in rows.where(run.creation >= start).groupby(run.skill).run(as_dict=True)}


def _card(doc, month):
	m = month.get(doc.name)
	edited = store.digest(doc.as_dict()) != doc.built_in_hash if doc.source == "Built-in" else False
	return {"name": doc.name, "title": doc.title, "when_to_use": doc.when_to_use, "trigger": _trigger_text(doc), "trigger_kind": doc.trigger_kind,
		"version": doc.version, "source": doc.source, "edited": edited, "active": bool(doc.active), "space": doc.space,
		"runs": int(m.runs) if m else 0, "cost": round(float(m.cost or 0), 4) if m else 0, "update_available": bool(doc.update_available)}


def _trigger_text(doc):
	if doc.trigger_kind == "Event":
		return _("When: {0}").format(doc.trigger_event.lower()) if doc.trigger_event else _("An event")
	if doc.trigger_kind == "Schedule":
		return _("Schedule: {0}").format(doc.schedule_cron)
	return _("A button") if doc.trigger_kind == "Button" else _("Served to agents")


@frappe.whitelist(methods=["GET"])
def overview():
	"""Brain > Skills: one card for each skill, with runs and cost this month; the fixed lists a new skill picks from; what the Brain may file on its own."""
	_people_only()
	month = _month_rows()
	cards = [_card(frappe.get_doc("Life Skill", n), month) for n in frappe.get_list("Life Skill", pluck="name", order_by="source asc, title asc")
		if _visible(n)]
	return {"skills": cards, "lists": lists(), "auto_file": filing.settings(), "can_edit": permissions.is_admin(),
		"proposal_kinds": sorted(SCHEMA)}


def _visible(name):
	space = frappe.db.get_value("Life Skill", name, "space")
	return not space or space in permissions.user_spaces() or permissions.is_admin()


def lists():
	from lifeos.skills import schemas

	return {"triggers": [t for t in store.TRIGGERS if t != "Served"], "events": LIST(store.EVENTS), "outputs": LIST(store.OUTPUTS), "tiers": LIST(store.TIERS),
		"tools": {"read": fixed.READ, "write": fixed.WRITE}, "shapes": LIST(schemas.SCHEMAS)}


@frappe.whitelist(methods=["GET"])
def detail(name: str):
	"""A skill page: the text and settings, its examples with their last result, its versions, and its recent runs."""
	_people_only()
	doc = _skill(name)
	card = _card(doc, _month_rows())
	versions = frappe.get_list("Life Skill Version", filters={"skill": name}, fields=["version", "instructions", "changed_by", "changed_on", "note", "config"],
		order_by="version desc")
	names = {u.name: u.full_name for u in frappe.get_all("User", filters={"name": ("in", [v.changed_by for v in versions if v.changed_by])}, fields=["name", "full_name"])}  # system: user names, not a space record
	for v in versions:
		v["changed_by_name"] = names.get(v.changed_by) or v.changed_by
		v["changed_on"] = str(v.changed_on)[:19]
	runs = frappe.get_list("Life Skill Run", filters={"skill": name}, fields=["name", "skill_version", "trigger", "input_doctype", "input_name", "status", "cost",
		"duration", "error", "creation", "sensitive"], order_by="creation desc", limit=20)
	for r in runs:
		r["creation"] = str(r.creation)[:19]
	return {**card, "instructions": doc.instructions, "update_text": doc.update_text if doc.update_available else None, "update_version": doc.update_version,
		"config": {k: doc.get(k) for k in store.CONFIG}, "tools": store.tool_list(doc),
		"examples": [{"name": e.name, "title": e.title, "input": e.input, "checks": e.expected, "last_result": e.last_result, "source": e.source,
			"recorded": bool(e.fixture and e.fixture_hash == store.digest(doc.as_dict()))}
			for e in frappe.get_list("Life Skill Example", filters={"skill": name}, fields=["name", "title", "input", "expected", "last_result", "source", "fixture", "fixture_hash"],
				order_by="creation asc")],
		"versions": versions, "runs": runs, "lessons": [x for x in lessons.for_skill(name) if not x["space"] or x["space"] in permissions.user_spaces() or permissions.is_admin()], "can_edit": permissions.is_admin(), "lists": lists()}


@frappe.whitelist(methods=["GET"])
def run_log(run: str):
	"""One run's log: tool calls, output, tokens, cost and error. Nothing of a sensitive input is in it."""
	_people_only()
	doc = frappe.get_doc("Life Skill Run", run)
	if not permissions.is_admin() and (not doc.space or doc.space not in permissions.user_spaces()):
		frappe.throw(_("There is no such run."), frappe.DoesNotExistError, title=_("Run not found"))
	return {"name": doc.name, "skill": doc.skill, "version": doc.skill_version, "trigger": doc.trigger, "status": doc.status,
		"input": f"{doc.input_doctype} {doc.input_name}" if doc.input_name else None, "tool_calls": json.loads(doc.tool_calls or "[]"), "output": doc.output,
		"input_tokens": doc.input_tokens, "output_tokens": doc.output_tokens, "cost": doc.cost, "duration": doc.duration, "error": doc.error,
		"sensitive": bool(doc.sensitive), "created": str(doc.creation)[:19]}


def _values(values):
	data = parse(values) or {}
	if not isinstance(data, dict):
		frappe.throw(_("values must be an object."), title=_("Values must be an object"))
	if isinstance(data.get("tools"), (builtins.list, tuple)):
		data["tools"] = json.dumps(data["tools"])
	allowed = {*store.CONFIG, "instructions", "active", "space"}
	return {k: v for k, v in data.items() if k in allowed}


@frappe.whitelist(methods=["POST"])
def save(name: str, values: str | dict, note: str | None = None):
	"""The owner's edit of a skill. A changed text or setting is a new version (who and when are kept)."""
	_admin_only()
	_skill(name)
	doc = store.save(name, _values(values), note)
	return {"name": doc.name, "version": doc.version}


@frappe.whitelist(methods=["POST"])
def create(slug: str, values: str | dict):
	"""A new skill the owner writes, from the fixed lists of triggers, tools and outputs. It starts switched off."""
	_admin_only()
	slug = frappe.scrub(slug or "").replace("_", "-")
	if not slug or frappe.db.exists("Life Skill", slug):
		frappe.throw(_("Pick a name that no skill has yet."), title=_("Skill name is taken"))
	doc = store.create({"slug": slug, **_values(values)})
	return {"name": doc.name, "version": doc.version}


@frappe.whitelist(methods=["POST"])
def set_active(name: str, active: int = 1):
	"""Switch a skill on or off. Switching never creates a version."""
	_admin_only()
	_skill(name)
	frappe.db.set_value("Life Skill", name, "active", 1 if int(active) else 0)
	return {"name": name, "active": bool(int(active))}


@frappe.whitelist(methods=["POST"])
def rollback(name: str, version: int):
	"""Restore an earlier version's text as a new version."""
	_admin_only()
	_skill(name)
	doc = store.rollback(name, int(version))
	return {"name": doc.name, "version": doc.version, "instructions": doc.instructions}


@frappe.whitelist(methods=["POST"])
def accept_update(name: str):
	"""Take the app's newer text of a built-in skill. The owner's edit stays in the versions."""
	_admin_only()
	_skill(name)
	doc = store.accept_update(name)
	return {"name": doc.name, "version": doc.version}


@frappe.whitelist(methods=["POST"])
def test(name: str, instructions: str | None = None):
	"""Run every example against the text on the screen (not yet saved when `instructions` is given): pass or fail for each, before saving.
	The recorded answer is used when the text is the one it was recorded for, else the model is asked (and the call is counted as cost)."""
	_admin_only()
	_skill(name)
	draft = {"instructions": instructions} if instructions is not None else None
	results = examples.run_all(name, draft)
	return {"results": [{k: v for k, v in r.items() if k in ("title", "passed", "checks", "source", "error", "proposals", "output")} for r in results],
		"passed": sum(1 for r in results if r["passed"]), "total": len(results)}


@frappe.whitelist(methods=["POST"])
def save_auto_file(threshold: float, kinds: str | builtins.list):
	"""What the Brain may file on its own: the confidence above which, and the kinds of proposal. Default: none."""
	_admin_only()
	chosen = [k for k in (parse(kinds) or []) if k in SCHEMA]
	if not 0.5 <= float(threshold) <= 1:
		frappe.throw(_("The confidence must be between 0.5 and 1."), title=_("Confidence is out of range"))
	settings = frappe.get_doc("Life Settings")
	settings.brain_auto_threshold, settings.brain_auto_kinds = float(threshold), json.dumps(chosen)
	settings.flags.ignore_permissions = True  # system: the skill settings are saved by the Life Admin checked above
	settings.save()
	return filing.settings()
