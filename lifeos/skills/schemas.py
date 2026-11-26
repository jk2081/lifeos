"""Named output shapes a skill can ask for, and a small checker for them. A skill's `output_schema` is either a name from SCHEMAS
or a JSON schema written out; the checker understands type, required, properties, items and enum, which is all they use."""
import json

import frappe
from frappe import _

SCHEMAS = {
	"capture-result": {
		"title": "capture-result", "type": "object", "additionalProperties": False, "required": ["transcript_md", "summary"],
		"properties": {
			"transcript_md": {"type": "string", "description": "The text of the capture, cleaned up; empty when the capture is already text."},
			"summary": {
				"type": "object", "additionalProperties": False, "required": ["line"],
				"description": "The summary as data: one line on top, then what to act on, what is moving and what was only filed.",
				"properties": {
					"line": {"type": "string", "description": "One line: what it is, for example '9 emails, 26 Nov'."},
					"to_act_on": {"type": "array", "description": "One line per thing that asks something. Under 15 words each.", "items": {
						"type": "object", "additionalProperties": False, "required": ["who", "what"], "properties": {
							"who": {"type": "string", "description": "The person or organisation."},
							"what": {"type": "string", "description": "What they want, under 15 words."},
							"source": {"type": "string", "description": "Where the line comes from: the email's link, or 'Email 3'."},
							"route": {"type": "string", "enum": ["plate", "waiting"], "description": "plate: only the owner can do it. waiting: someone else is on it, or you are not sure."},
							"waiting_on": {"type": "string", "description": "For waiting: the person who is on it."},
							"due": {"type": "string", "description": "A date the text names, YYYY-MM-DD."},
							"check_by": {"type": "string", "description": "For waiting: a date the text names to look again, YYYY-MM-DD."},
							"sensitive": {"type": "boolean"}}}},
					"updates": {"type": "array", "description": "Things moving that need nothing now; several items on one subject make one line.", "items": {
						"type": "object", "additionalProperties": False, "required": ["what"], "properties": {"what": {"type": "string"}, "source": {"type": "string"}, "sensitive": {"type": "boolean"}}}},
					"reports": {"type": "array", "description": "Filed, nothing to do: a short title each.", "items": {
						"type": "object", "additionalProperties": False, "required": ["title"], "properties": {"title": {"type": "string"}, "source": {"type": "string"}, "sensitive": {"type": "boolean"}}}},
					"facts": {"type": "array", "items": {"type": "string"}, "description": "For a single item: up to 5 key facts."},
				},
			},
			"closes": {"type": "array", "description": "Waiting tasks this capture settles (a reply that says it is done): only ids from waiting_tasks_on_this_thread.", "items": {
				"type": "object", "additionalProperties": False, "required": ["task"], "properties": {"task": {"type": "string"}, "reason": {"type": "string"}}}},
			"moves": {"type": "array", "description": "Waiting tasks this capture gives a new date for (\"will send Monday\"): only ids from waiting_tasks_on_this_thread.", "items": {
				"type": "object", "additionalProperties": False, "required": ["task", "check_by"], "properties": {"task": {"type": "string"}, "check_by": {"type": "string", "description": "YYYY-MM-DD"}, "reason": {"type": "string"}}}},
			"skipped": {"type": "array", "items": {"type": "string"}, "description": "What was left out on purpose, one short line each."},
		},
	},
	"lesson-result": {
		"title": "lesson-result", "type": "object", "additionalProperties": False, "required": ["lesson", "summary"],
		"properties": {
			"lesson": {"type": "string", "description": "One or two plain sentences to add to the skill's instructions."},
			"summary": {"type": "string", "description": "A few words naming what the lesson teaches."},
		},
	},
}

def _obj(required, properties):
	return {"type": "object", "additionalProperties": False, "required": required, "properties": properties}


def _list(item):
	return {"type": "array", "items": item}


_S, _N = {"type": "string"}, {"type": "number"}
_REFS = _list(_S)

SCHEMAS.update({
	"backlog-decisions": _obj(["decisions"], {"decisions": _list(_obj(["item", "decision", "reason"], {
		"item": _S, "decision": {"type": "string", "enum": ["keep", "park", "drop"]}, "reason": _S, "chase": {"type": "boolean"}, "group": _S}))}),
	"week-plan": _obj(["plans", "stars"], {"plans": _list(_obj(["goal", "minutes"], {
		"goal": _S, "next_action": _S, "minutes": {"type": "integer", "enum": [30, 60, 90]}})), "stars": _REFS}),
	"notice-result": _obj(["insights", "follow_ups", "readings"], {
		"insights": _list(_obj(["kind", "title", "evidence"], {"kind": {"type": "string", "enum": ["Waiting on you", "Promise", "Theme"]},
			"title": _S, "body": _S, "evidence": _REFS, "task_title": _S})),
		"follow_ups": _list(_obj(["meeting", "kind", "title", "record"], {"meeting": _S, "kind": {"type": "string", "enum": ["Promise", "Date"]},
			"title": _S, "task_title": _S, "date": _S, "record": _S, "excerpt": _S})),
		"readings": _list(_obj(["goal", "value", "record", "excerpt"], {"goal": _S, "value": _N, "date": _S, "record": _S, "excerpt": _S}))}),
	"goal-definition": _obj(["kind"], {"kind": {"type": "string", "enum": ["Milestone", "Number", "Title"]}, "done_when": _S, "measure": _S,
		"unit": _S, "target_value": _N, "start_value": _N, "title": _S}),
	"email-triage": _obj(["keep", "reason"], {"keep": {"type": "boolean"}, "reason": _S}),
	"link-subjects": _obj(["context", "person"], {"context": {"type": "string", "enum": ["business", "family", "other"]}, "person": _S, "role": _S,
		"organisation": _S, "same_as": _S, "unsure_of": _S, "reason": _S}),
	"brief-result": _obj(["sentences"], {"sentences": _list(_obj(["text", "sources"], {"text": _S, "sources": _list({"type": "integer"})}))}),
	"reflect-result": _obj(["sentence"], {"sentence": _S}),
	"key-date": _obj(["key", "reason"], {"key": {"type": "boolean"}, "reason": _S}),
	"hand-off-message": _obj(["subject", "body"], {"subject": _S, "body": _S}),
	"area-guess": _obj(["area", "confidence"], {"area": _S, "confidence": {"type": "integer"}}),
	"wiki-check": _obj(["orphans", "missing", "stale", "contradictions"], {
		"orphans": _list(_obj(["page", "action"], {"page": _S, "action": {"type": "string", "enum": ["link", "archive"]}, "link_to": _S, "reason": _S})),
		"missing": _list(_obj(["name", "summary"], {"name": _S, "summary": _S})),
		"stale": _list(_obj(["page", "summary"], {"page": _S, "summary": _S})),
		"contradictions": _list(_obj(["topic", "question", "options"], {"topic": _S, "question": _S,
			"options": _list(_obj(["page", "fact"], {"page": _S, "fact": _S}))}))}),
})


def resolve(value: str | None):
	"""The schema a skill asks for, or None when it asks for none."""
	value = (value or "").strip()
	if not value:
		return None
	if value in SCHEMAS:
		return SCHEMAS[value]
	try:
		return json.loads(value)
	except ValueError:
		frappe.throw(_("The output shape must be the name of a shape or valid JSON."), title=_("Output shape not valid"))


TYPES = {"object": dict, "array": list, "string": str, "number": (int, float), "integer": int, "boolean": bool}


def check(value, schema: dict, where: str = "the answer") -> str | None:
	"""None when `value` fits `schema`, else one line saying what does not."""
	kind = schema.get("type")
	if kind in TYPES:
		ok = isinstance(value, TYPES[kind]) and not (kind in ("number", "integer") and isinstance(value, bool))
		if not ok:
			return _("{0} should be {1}").format(where, kind)
	if "enum" in schema and value not in schema["enum"]:
		return _("{0} should be one of {1}").format(where, ", ".join(str(v) for v in schema["enum"]))
	if kind == "object":
		for key in schema.get("required") or []:
			if key not in value:
				return _("{0} is missing {1}").format(where, key)
		for key, sub in (schema.get("properties") or {}).items():
			if key in value and (problem := check(value[key], sub, f"{where}.{key}")):
				return problem
	if kind == "array" and schema.get("items"):
		for i, v in enumerate(value):
			if problem := check(v, schema["items"], f"{where}[{i}]"):
				return problem
	return None
