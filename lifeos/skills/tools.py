"""The tools a skill may use: a fixed list in code. An owner skill picks among them and can never add one. Every tool is a normal
Life OS function, run as the "Life Brain" user (a Life Agent), so every permission and sensitive-item rule applies.

There is no tool to accept, delete, send or change settings: the runner refuses any name that is not in this list, and the
code behind a name never does those things.
"""
import frappe
from frappe import _

from lifeos import permissions, proposals
from lifeos.ai import tools as ask_tools

READ = ["search", "context.get", "get_record", "list_goals", "list_areas"]
WRITE = ["propose", "update_wiki_page", "suggest_lesson"]
NAMES = [*READ, *WRITE]
# context.get reads the core card, which does not exist yet (#54): the name is reserved and answers that it is not there
NOT_YET = {"context.get"}

SPECS = {
	"search": ask_tools.TOOLS[0],
	"get_record": ask_tools.TOOLS[1],
	"context.get": {"name": "context_get", "description": "The owner's core card: who they are and what matters most. Not available yet.",
		"input_schema": {"type": "object", "properties": {}}},
	"list_goals": {"name": "list_goals", "description": "The goals in progress in the space, with their area and the cycle's actions.",
		"input_schema": {"type": "object", "properties": {}}},
	"list_areas": {"name": "list_areas", "description": "The areas of life that are on in the space, each followed by its parts, with a one-line description.",
		"input_schema": {"type": "object", "properties": {}}},
	"propose": {"name": "propose", "description": "Propose one record for the owner to accept: a task, event, note and so on. It waits for the owner "
		"(or is filed by Life OS only when the owner allowed it for that kind and your confidence is high). Use the payload fields of the kind.",
		"input_schema": {"type": "object", "required": ["kind", "payload", "confidence"], "properties": {
			"kind": {"type": "string", "enum": sorted(proposals.SCHEMA)},
			"preview": {"type": "string", "description": "One line the owner reads."},
			"payload": {"type": "object", "description": "The fields of the kind (title, area, due_date …). Never invent a date."},
			"confidence": {"type": "number", "description": "0 to 1: how sure you are this is right and in the right area."},
			"reason": {"type": "string", "description": "One short line on why this area and goal."},
			"alt_area": {"type": "string", "description": "When torn between two areas, the other one."}}}},
	"update_wiki_page": {"name": "update_wiki_page", "description": "Create or update a wiki page, citing the capture. Only when the capture's intent is Add to wiki.",
		"input_schema": {"type": "object", "required": ["title", "content_md"], "properties": {
			"title": {"type": "string"}, "content_md": {"type": "string"}, "summary": {"type": "string", "description": "What changed, one line."}}}},
	"suggest_lesson": {"name": "suggest_lesson", "description": "Note something the owner's correction could teach this skill. It is kept for the owner to read; it changes nothing.",
		"input_schema": {"type": "object", "required": ["lesson"], "properties": {"lesson": {"type": "string"}}}},
}
# the name the model sees (a dot is not allowed in a tool name) back to the name in the list
MODEL_NAME = {name: spec["name"] for name, spec in SPECS.items()}
FROM_MODEL = {v: k for k, v in MODEL_NAME.items()}


class Refused(Exception):
	"""A tool name the skill may not use."""


def specs_for(names: list) -> list:
	return [SPECS[n] for n in names if n in SPECS]


class Run:
	"""What one skill run may do: the space, the input record and what the tools collected."""

	def __init__(self, skill, space, item=None, intent="Process", lenient=False):
		self.skill, self.space, self.item, self.intent = skill, space, item, intent
		self.lenient = lenient  # an example run: the proposals are judged by the example's checks, not by this space's areas
		self.allowed = set(skill["tools"])
		self.proposals, self.lessons, self.pages, self.calls = [], [], [], []
		self.ctx = ask_tools.Context(space, {"kind": "space"}, user=frappe.session.user)
		# the Brain reads a sensitive item only where the space's switch lets agents open them
		self.ctx.vault_ok = not permissions.vault_hidden(space)
		self.validation = {}

	def call(self, model_name: str, args: dict) -> dict:
		name = FROM_MODEL.get(model_name, model_name)
		if name not in NAMES:
			self.calls.append({"tool": str(model_name)[:60], "refused": True})
			raise Refused(_("{0} is not a Life OS tool.").format(model_name))
		if name not in self.allowed:
			self.calls.append({"tool": name, "refused": True})
			raise Refused(_("This skill may not use {0}.").format(name))
		self.calls.append({"tool": name})
		return globals()[f"tool_{name.replace('.', '_')}"](self, **(args if isinstance(args, dict) else {}))


def tool_search(run, **args):
	return ask_tools.run_tool(run.ctx, "search", args)


def tool_get_record(run, **args):
	return ask_tools.run_tool(run.ctx, "get_record", args)


def tool_context_get(run, **_args):
	return {"error": _("The core card does not exist yet.")}


def tool_list_goals(run, **_args):
	from lifeos.api.inbox import space_context

	return {"goals": [{"name": g["name"], "title": g["title"], "area": g["area"], "type": g["horizon"]} for g in space_context(run.space)["goals"]]}


def tool_list_areas(run, **_args):
	from lifeos.api.inbox import space_context

	ctx = space_context(run.space)
	return {"areas": [{"name": a["name"], "title": a["area_name"], "part_of": a.get("parent_area"), "description": a.get("description")} for a in ctx["areas"]],
		"areas_off": ctx["areas_off"]}


def tool_propose(run, kind=None, payload=None, preview=None, confidence=None, reason=None, alt_area=None, **_ignored):
	"""Check the proposal now, so the model can fix it, and hold it: the runner files all of them with `submit_result` at the end."""
	if run.intent == "Just keep":
		return {"error": _("This capture is to be kept only. Propose nothing.")}
	if run.intent == "Add to wiki" and kind == "Note":
		return {"error": _("This capture is for the wiki. Use update_wiki_page, not a note.")}
	try:
		if kind not in proposals.SCHEMA:
			raise proposals.PayloadError(_("{0} is not a kind of proposal.").format(kind))
		if not run.lenient:
			clean = proposals.validate(kind, payload or {}, run.space, run.validation)
			proposals.extras({"reason": reason, "alt_area": alt_area}, clean, run.space)
		conf = 0.5 if confidence is None else float(confidence)
		if not 0 <= conf <= 1:
			raise proposals.PayloadError(_("confidence must be between 0 and 1."))
	except (proposals.PayloadError, ValueError, TypeError) as e:
		return {"error": str(e)}
	run.proposals.append({"kind": kind, "preview": preview, "payload": payload or {}, "confidence": conf, "reason": reason, "alt_area": alt_area})
	return {"ok": True, "proposals_so_far": len(run.proposals)}


def tool_update_wiki_page(run, title=None, content_md=None, summary=None, **_ignored):
	from lifeos.api import wiki

	if run.intent != "Add to wiki":
		return {"error": _("Wiki pages are written only for captures whose intent is Add to wiki.")}
	source = [{"doctype": "Life Inbox Item", "name": run.item}] if run.item else None
	existing = frappe.db.get_value("Life Note", {"space": run.space, "collection": "Wiki", "title": title})
	try:
		if existing:
			out = wiki.update_page(existing, content_md=content_md, base_version=wiki.version_of(frappe.get_doc("Life Note", existing)),
				summary=summary, sources_add=source)
		else:
			out = wiki.create_page(space=run.space, title=title, content_md=content_md, summary=summary, sources=source)
	except frappe.ValidationError as e:
		return {"error": str(e)}
	run.pages.append(existing or (out.get("name") if isinstance(out, dict) else None))
	return {"ok": True, "page": run.pages[-1]}


def tool_suggest_lesson(run, lesson=None, **_ignored):
	run.lessons.append(str(lesson or "")[:500])
	return {"ok": True}
