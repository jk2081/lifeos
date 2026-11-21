"""Named output shapes a skill can ask for, and a small checker for them. A skill's `output_schema` is either a name from SCHEMAS
or a JSON schema written out; the checker understands type, required, properties, items and enum, which is all they use."""
import json

import frappe
from frappe import _

SCHEMAS = {
	"capture-result": {
		"title": "capture-result", "type": "object", "additionalProperties": False, "required": ["transcript_md", "summary_md"],
		"properties": {
			"transcript_md": {"type": "string", "description": "The text of the capture, cleaned up; empty when the capture is already text."},
			"summary_md": {"type": "string", "description": "A short summary in Markdown, in the owner's words. Mention anything odd in the capture."},
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
		frappe.throw(_("The output shape must be the name of a shape or valid JSON."))


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
