"""Skills as records: the built-in ones installed from `lifeos/skills/*.md`, the owner's edits as versions, and what agents are served.

A skill file is a Markdown file with a small header (name, title, when_to_use, trigger, event, schedule, tools, output, model,
cost_limit, version) and the instructions below it. The header and the instructions together are "the shipped text". An app
update that changes a built-in skill never overwrites the owner's edit: it shows "update available" with a diff instead.
"""
import hashlib
import json
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import now_datetime

DIR = Path(__file__).parent
TRIGGERS = ("Event", "Schedule", "Button", "Served")
EVENTS = ("Capture created", "Email filed", "Record changed")  # the fixed list in code (triggers.py)
OUTPUTS = ("Proposals", "Note", "Insight", "Page update", "Answer", "JSON")
TIERS = ("Fast", "Smart")
# the settings of a skill that are part of its text and so of its versions
CONFIG = ("title", "when_to_use", "trigger_kind", "trigger_event", "schedule_cron", "tools", "output_kind", "output_schema", "model_tier", "cost_limit")
HEADER = {"name": "slug", "title": "title", "when_to_use": "when_to_use", "trigger": "trigger_kind", "event": "trigger_event",
	"schedule": "schedule_cron", "tools": "tools", "output": "output_kind", "schema": "output_schema", "model": "model_tier",
	"cost_limit": "cost_limit"}


def parse_file(path: Path) -> dict:
	"""{slug, title, …, instructions, version} from a skill file."""
	text = path.read_text()
	head, _sep, body = text.removeprefix("---\n").partition("\n---\n")
	out = {"instructions": body.strip() + "\n", "version": 1, "cost_limit": "0.25"}
	for line in head.splitlines():
		key, _colon, value = line.partition(":")
		key, value = key.strip(), value.strip()
		if key == "version":
			out["version"] = int(value or 1)
		elif key in HEADER:
			out[HEADER[key]] = value
	out["tools"] = json.dumps([t.strip() for t in out.get("tools", "").strip("[]").split(",") if t.strip()])
	return out


def builtin_files() -> list:
	return sorted(DIR.glob("*.md"))


def builtin(slug: str) -> dict | None:
	path = DIR / f"{slug}.md"
	return parse_file(path) if path.exists() else None


def instructions_of(slug: str) -> str:
	"""A skill's instructions as the owner has them, or as shipped when the site has none yet."""
	return frappe.db.get_value("Life Skill", slug, "instructions") or builtin(slug)["instructions"]


def digest(values: dict) -> str:
	"""A hash of a skill's text and settings, to tell whether the owner changed it."""
	data = {k: str(values.get(k) if values.get(k) is not None else "") for k in ("instructions", *CONFIG)}
	data["cost_limit"] = str(float(values.get("cost_limit") or 0))
	return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def config_of(doc) -> dict:
	return {k: doc.get(k) for k in CONFIG}


def snapshot(doc, note: str, user: str | None = None):
	frappe.get_doc({"doctype": "Life Skill Version", "skill": doc.name, "version": doc.version, "instructions": doc.instructions,
		"config": json.dumps(config_of(doc), default=str), "changed_by": user or frappe.session.user, "changed_on": now_datetime(),
		"note": note[:140]}).insert(ignore_permissions=True)


def _apply(doc, values: dict):
	for k in ("instructions", *CONFIG):
		if k in values:
			doc.set(k, values[k])


def install():
	"""Install or update every built-in skill and its examples. Runs on migrate. An edit by the owner is kept."""
	for path in builtin_files():
		shipped = parse_file(path)
		slug = shipped["slug"]
		doc = frappe.db.get_value("Life Skill", slug)
		if not doc:
			values = {"doctype": "Life Skill", "source": "Built-in", "version": shipped["version"], "built_in_version": shipped["version"],
				"built_in_hash": digest(shipped), "active": 0 if shipped.get("trigger_kind") == "Event" else 1,
				**{k: v for k, v in shipped.items() if k not in ("version",)}}
			doc = frappe.get_doc(values).insert(ignore_permissions=True)
			snapshot(doc, "Installed with the app", "Administrator")
		else:
			_update_builtin(frappe.get_doc("Life Skill", slug), shipped)
		from lifeos.skills import examples

		examples.install(slug)


def _update_builtin(doc, shipped: dict):
	new_hash = digest(shipped)
	if doc.built_in_hash == new_hash and doc.built_in_version == shipped["version"]:
		return
	if digest(doc.as_dict()) == doc.built_in_hash:  # the owner never edited it: take the new text
		_apply(doc, shipped)
		doc.version += 1
		doc.update_available = 0
		doc.update_text = doc.update_version = None
		doc.built_in_version, doc.built_in_hash = shipped["version"], new_hash
		doc.save(ignore_permissions=True)
		snapshot(doc, f"Built-in update (shipped v{shipped['version']})", "Administrator")
	else:  # an edited skill keeps the edit and shows the update
		doc.update_available = 1
		doc.update_text, doc.update_version = shipped["instructions"], shipped["version"]
		doc.save(ignore_permissions=True)


def save(slug: str, values: dict, note: str | None = None):
	"""The owner's edit: a changed text or setting is a new version, with who and when."""
	doc = frappe.get_doc("Life Skill", slug)
	before = digest(doc.as_dict())
	_apply(doc, values)
	for k in ("active", "space"):
		if k in values:
			doc.set(k, values[k])
	validate(doc)
	if digest(doc.as_dict()) != before:
		doc.version += 1
		doc.save(ignore_permissions=True)
		snapshot(doc, note or _("Edited"))
	else:
		doc.save(ignore_permissions=True)
	return doc


def create(values: dict):
	doc = frappe.get_doc({"doctype": "Life Skill", "source": "Owner", "version": 1, "active": 0, "trigger_kind": "Button", "output_kind": "Answer",
		"model_tier": "Fast", "cost_limit": 0.25, "tools": "[]", **values})
	validate(doc)
	doc.insert(ignore_permissions=True)
	snapshot(doc, _("Created"))
	return doc


def validate(doc):
	"""The fixed lists: a skill picks a trigger, tools and an output from these, and can never add one."""
	from lifeos.skills import tools as fixed

	if doc.trigger_kind not in TRIGGERS:
		frappe.throw(_("The trigger must be one of: {0}.").format(", ".join(TRIGGERS)))
	if doc.trigger_kind == "Event" and doc.trigger_event not in EVENTS:
		frappe.throw(_("Pick an event: {0}.").format(", ".join(EVENTS)))
	if doc.trigger_kind == "Schedule":
		from croniter import croniter

		if not doc.schedule_cron or not croniter.is_valid(doc.schedule_cron):
			frappe.throw(_("A schedule needs a valid cron expression, such as 0 7 * * *."))
	if doc.output_kind not in OUTPUTS:
		frappe.throw(_("The output must be one of: {0}.").format(", ".join(OUTPUTS)))
	if doc.model_tier not in TIERS:
		frappe.throw(_("The model tier is Fast or Smart."))
	chosen = tool_list(doc)
	bad = [t for t in chosen if t not in fixed.NAMES]
	if bad:
		frappe.throw(_("{0} is not one of the tools Life OS offers. The tools are: {1}.").format(", ".join(bad), ", ".join(fixed.NAMES)))
	if doc.output_kind == "JSON" and doc.output_schema:
		from lifeos.skills import schemas

		schemas.resolve(doc.output_schema)  # a name from the list, or valid JSON


def tool_list(doc) -> list:
	try:
		out = json.loads(doc.get("tools") or "[]")
	except ValueError:
		return []
	return [str(t) for t in out] if isinstance(out, list) else []


def rollback(slug: str, version: int):
	"""Restore an earlier version's text and settings as a new version."""
	row = frappe.db.get_value("Life Skill Version", {"skill": slug, "version": int(version)}, ["instructions", "config"], as_dict=True)
	if not row:
		frappe.throw(_("There is no version {0} of this skill.").format(version))
	config = json.loads(row.config or "{}")
	return save(slug, {"instructions": row.instructions, **{k: v for k, v in config.items() if k in CONFIG}}, _("Rolled back to version {0}").format(version))


def accept_update(slug: str):
	"""Take the app's newer text of a built-in skill, as a new version (the edit stays in the history)."""
	doc = frappe.get_doc("Life Skill", slug)
	shipped = builtin(slug)
	if not shipped:
		frappe.throw(_("This skill is not built in."))
	_apply(doc, shipped)
	doc.version += 1
	doc.update_available, doc.update_text, doc.update_version = 0, None, None
	doc.built_in_version, doc.built_in_hash = shipped["version"], digest(shipped)
	doc.save(ignore_permissions=True)
	snapshot(doc, _("Built-in update (shipped v{0})").format(shipped["version"]))
	return doc


def label(doc_or_slug, version=None) -> str:
	"""How a skill and its version read in Activity: "process-capture v1"."""
	if isinstance(doc_or_slug, str):
		return f"{doc_or_slug} v{version}"
	return f"{doc_or_slug.name} v{doc_or_slug.version}"


# ---- served to agents and people ----
def visible(user: str | None = None) -> list:
	"""Active skills a person or agent may be served: those of every space they belong to, and those for all spaces."""
	from lifeos import permissions

	spaces = list(permissions.user_spaces(user))
	rows = frappe.get_all("Life Skill", filters={"active": 1}, fields=["name", "title", "when_to_use", "version", "space", "source", "trigger_kind"],
		order_by="title")
	return [r for r in rows if not r.space or r.space in spaces]
