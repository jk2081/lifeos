#!/usr/bin/env python3
"""Set 7: add fields and DocTypes to the JSON definitions. Run from the repo root. Safe to run again."""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lifeos", "life", "doctype")
STAMP = "2026-11-18 09:00:00.000000"


def path(dt):
	s = dt.lower().replace(" ", "_").replace("-", "_")
	return os.path.join(ROOT, s, s + ".json")


def add_fields(dt, after, fields):
	p = path(dt)
	d = json.load(open(p))
	have = {f["fieldname"] for f in d["fields"]}
	new = [f for f in fields if f["fieldname"] not in have]
	if not new:
		return
	i = next(i for i, f in enumerate(d["fields"]) if f["fieldname"] == after) + 1
	d["fields"][i:i] = new
	d["field_order"] = [f["fieldname"] for f in d["fields"]]
	d["modified"] = STAMP
	json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)
	open(p, "a").write("\n")


PERMS = [
	{"role": "Life Admin", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "print": 1, "email": 1, "share": 1},
	{"role": "Life User", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "print": 1, "email": 1, "share": 1},
	{"role": "Life Agent", "read": 1, "report": 1},
]


def new_doctype(name, fields, title_field="title", sort_field="creation", perms=PERMS):
	p = path(name)
	os.makedirs(os.path.dirname(p), exist_ok=True)
	d = {"actions": [], "autoname": "hash", "creation": STAMP, "doctype": "DocType", "engine": "InnoDB",
		"field_order": [f["fieldname"] for f in fields], "fields": fields, "links": [], "modified": STAMP,
		"modified_by": "Administrator", "module": "Life", "name": name, "naming_rule": "Random", "owner": "Administrator",
		"permissions": perms, "search_fields": title_field, "show_title_field_in_link": 1, "sort_field": sort_field,
		"sort_order": "DESC", "states": [], "title_field": title_field}
	json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)
	open(p, "a").write("\n")
	init = os.path.join(os.path.dirname(p), "__init__.py")
	if not os.path.exists(init):
		open(init, "w").close()


SPACE = {"fieldname": "space", "fieldtype": "Link", "label": "Space", "options": "Life Space", "reqd": 1, "search_index": 1, "in_standard_filter": 1}


def step1():
	add_fields("Life Goal", "done_when", [
		{"fieldname": "measure_kind", "fieldtype": "Select", "label": "Measure Kind", "options": "\nMilestone\nNumber",
			"description": "How you will know it is done: a finish line (Milestone) or a number against a target (Number)."},
		{"fieldname": "measure", "fieldtype": "Data", "label": "Measure", "description": "What is measured, for example Ghillidary yield."},
		{"fieldname": "unit", "fieldtype": "Data", "label": "Unit", "description": "For example kg/ha."},
		{"fieldname": "start_value", "fieldtype": "Float", "label": "Start Value"},
		{"fieldname": "target_value", "fieldtype": "Float", "label": "Target Value"},
		{"fieldname": "current_value", "fieldtype": "Float", "label": "Current Value", "read_only": 1,
			"description": "The latest confirmed reading."},
		{"fieldname": "current_on", "fieldtype": "Date", "label": "Current On", "read_only": 1},
	])
	new_doctype("Life Goal Reading", [
		SPACE,
		{"fieldname": "goal", "fieldtype": "Link", "label": "Goal", "options": "Life Goal", "reqd": 1, "search_index": 1, "in_list_view": 1},
		{"fieldname": "date", "fieldtype": "Date", "label": "Date", "reqd": 1, "in_list_view": 1},
		{"fieldname": "value", "fieldtype": "Float", "label": "Value", "in_list_view": 1},
		{"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Suggested\nConfirmed\nRejected", "default": "Suggested",
			"in_list_view": 1, "search_index": 1},
		{"fieldname": "source_doctype", "fieldtype": "Link", "label": "Source Type", "options": "DocType"},
		{"fieldname": "source_name", "fieldtype": "Dynamic Link", "label": "Source", "options": "source_doctype"},
		{"fieldname": "excerpt", "fieldtype": "Small Text", "label": "Excerpt", "description": "The words the value was read from."},
		{"fieldname": "suggested_by", "fieldtype": "Select", "label": "Suggested By", "options": "\nAgent\nAssistant\nOwner"},
		{"fieldname": "confirmed_by", "fieldtype": "Link", "label": "Confirmed By", "options": "User"},
		{"fieldname": "confirmed_on", "fieldtype": "Datetime", "label": "Confirmed On"},
		{"fieldname": "title", "fieldtype": "Data", "label": "Title", "read_only": 1},
	], sort_field="date")


if __name__ == "__main__":
	for s in sys.argv[1:] or ["step1"]:
		globals()[s]()
