#!/usr/bin/env python3
"""Generate the DocType JSON files for lifeos from one compact definition.

Run from the repo root:  python3 scripts/gen_doctypes.py
It rewrites every lifeos/life/doctype/*/*.json and creates controller stubs
that do not exist yet. Hand-written controllers are never overwritten.
"""
import json
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lifeos", "life", "doctype")
STAMP = "2026-11-15 00:00:00.000000"


def scrub(name):
	return name.lower().replace(" ", "_").replace("-", "_")


def label(fieldname):
	special = {"notes_md": "Notes", "content_md": "Content", "summary_md": "Summary", "transcript_md": "Transcript",
		"reflection_md": "Reflection", "mindsweep_md": "Mindsweep", "projects_md": "Projects", "url": "URL",
		"source_url": "Source URL", "number_last4": "Number (last 4)", "also_in_csv": "Also In (CSV)", "tags_csv": "Tags (CSV)"}
	return special.get(fieldname) or fieldname.replace("_", " ").title()


def f(fieldname, fieldtype="Data", options=None, **kw):
	d = {"fieldname": fieldname, "fieldtype": fieldtype, "label": kw.pop("label", None) or label(fieldname)}
	if options is not None:
		d["options"] = "\n".join(options) if isinstance(options, (list, tuple)) else options
	for k, v in kw.items():
		d[k] = v
	return d


def link(fieldname, target, **kw):
	return f(fieldname, "Link", target, **kw)


def sel(fieldname, opts, **kw):
	return f(fieldname, "Select", opts, **kw)


def md(fieldname, **kw):
	return f(fieldname, "Long Text", **kw)


SPACE = link("space", "Life Space", reqd=1, search_index=1, in_standard_filter=1)


def org():
	return [
		f("organisation_section", "Section Break", label="Organisation"),
		link("area", "Life Area", search_index=1, in_standard_filter=1, in_list_view=1),
		f("also_in", "Table MultiSelect", "Life Also In"),
		link("project", "Life Project", search_index=1),
		f("tags", "Table MultiSelect", "Life Tag Link"),
		f("is_archived", "Check", default="0", search_index=1),
		f("archived_on", "Date"),
		sel("archive_reason", ["", "Manual", "Auto", "Project"]),
	]



def someday():
	"""UX fixes, set 5: parked on the Someday list. Parking keeps `creation`."""
	return [
		f("someday_section", "Section Break", label="Someday"),
		f("someday_on", "Date", search_index=1, label="Parked On"),
		f("someday_review_on", "Date", search_index=1, label="Review On"),
		f("someday_note", "Small Text", label="Why It Was Parked"),
	]

def perms(admin_only_write=False, agent_write=True):
	full = {"read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1, "print": 1, "email": 1, "share": 1}
	ro = {"read": 1, "report": 1}
	out = [{"role": "Life Admin", **full}]
	if admin_only_write:
		out += [{"role": "Life User", **ro}, {"role": "Life Agent", **ro}]
	else:
		out.append({"role": "Life User", **full})
		agent = {"read": 1, "report": 1}
		if agent_write:
			agent.update({"write": 1, "create": 1})
		out.append({"role": "Life Agent", **agent})
	return out


DOCTYPES = {}


def dt(name, fields, **kw):
	DOCTYPES[name] = (fields, kw)


PRIORITY = ["", "I", "II", "III", "IV"]
INTENTS = ["Process", "Add to wiki", "Just keep"]
MEDIA_KINDS = ["", "Voice", "Document", "Photo", "Article", "Email", "Email Digest", "Text"]

# ---- child tables ----
dt("Life Space Member", [link("user", "User", reqd=1, in_list_view=1), sel("access", ["Read", "Write"], default="Write", reqd=1, in_list_view=1)], istable=1)
dt("Life Also In", [link("area", "Life Area", reqd=1, in_list_view=1)], istable=1)
dt("Life Tag Link", [link("tag", "Life Tag", reqd=1, in_list_view=1)], istable=1)
dt("Life Goal Action", [
	f("title", reqd=1, in_list_view=1),
	f("per_week", "Int", default="1", in_list_view=1),
	sel("status", ["Open", "Done", "Dropped"], default="Open", in_list_view=1),
	f("done_on", "Date"),
	f("ticks", read_only=1, in_list_view=1, description="Summary computed from Life Action Log"),
], istable=1)
dt("Life Month Plan Goal", [
	f("title", reqd=1, in_list_view=1),
	sel("priority", PRIORITY, in_list_view=1),
	sel("status", ["Open", "Done", "Carried", "Dropped"], default="Open", in_list_view=1),
	link("area", "Life Area", in_list_view=1),
	link("task", "Life Task"),
	f("carried_from", read_only=1, description="Row this goal was carried from"),
], istable=1)
dt("Life Month Plan Habit", [
	link("habit", "Life Habit", reqd=1, in_list_view=1),
	f("days_per_week", "Int", default="7", in_list_view=1),
	f("sort_order", "Int"),
	f("tracked_from", "Date", in_list_view=1),
	f("tracked_until", "Date", in_list_view=1),
], istable=1)
dt("Life Check-in Score", [
	link("dimension", "Life Dimension", reqd=1, in_list_view=1),
	f("habits_low", "Float", in_list_view=1), f("habits_high", "Float", in_list_view=1),
	f("situation_low", "Float", in_list_view=1), f("situation_high", "Float", in_list_view=1),
	f("note", "Small Text"),
], istable=1)
dt("Life Note Source", [
	link("source_doctype", "DocType", reqd=1, in_list_view=1),
	f("source_name", "Dynamic Link", "source_doctype", reqd=1, in_list_view=1),
], istable=1)
dt("Life AI Price", [
	f("model", reqd=1, in_list_view=1), f("input_per_mtok", "Float", in_list_view=1, label="Input, $ per million tokens"),
	f("output_per_mtok", "Float", in_list_view=1, label="Output, $ per million tokens"),
], istable=1)
dt("Life Insight Evidence", [
	link("ref_doctype", "DocType", reqd=1, in_list_view=1), f("ref_name", "Dynamic Link", "ref_doctype", reqd=1, in_list_view=1),
	f("label", in_list_view=1),
], istable=1)
dt("Life Chat Open Item", [
	f("text", "Small Text", reqd=1, in_list_view=1),
	sel("status", ["Open", "Task Created", "Closed"], default="Open", in_list_view=1),
	link("task", "Life Task"),
], istable=1)

# ---- core ----
dt("Life Space", [
	f("space_name", reqd=1, unique=1, in_list_view=1),
	link("owner_user", "User", in_list_view=1),
	f("members", "Table", "Life Space Member"),
	f("agents_can_read_vault", "Check", default="0", label="Agents Can Read Vault",
		description="Let agents open documents in this space's Vault. Off by default."),
	f("ask_enabled", "Check", default="1", label="Ask Is On", description="People in this space can use Ask (UX fixes, set 5)."),
	f("ask_can_read_vault", "Check", default="0", label="Ask May Read Vault Documents",
		description="Let Ask send this space's Vault documents to the AI model. Off by default; separate from the agent switch."),
], autoname="field:space_name", permissions=perms(admin_only_write=True), title_field="space_name")
dt("Life Area", [
	SPACE, f("area_name", reqd=1, in_list_view=1), link("parent_area", "Life Area"),
	f("sort_order", "Int"), f("is_archived", "Check", default="0"), f("archived_on", "Date"),
], title_field="area_name", show_title=1, search_fields="area_name")
dt("Life Project", [
	SPACE, f("title", reqd=1, in_list_view=1), link("area", "Life Area", reqd=1, in_list_view=1, search_index=1),
	sel("status", ["Active", "On Hold", "Done", "Dropped", "Someday"], default="Active", in_list_view=1, search_index=1),
	f("outcome", "Small Text"), f("target_date", "Date", in_list_view=1), f("completed_on", "Date"), md("notes_md"),
	f("is_archived", "Check", default="0", search_index=1), f("archived_on", "Date"),
	f("last_activity_on", "Date", search_index=1, description="The last day the project or one of its tasks changed"),
	*someday(),
], title_field="title", show_title=1, search_fields="title")
dt("Life Tag", [SPACE, f("tag_name", reqd=1, in_list_view=1), f("is_archived", "Check", default="0"), f("archived_on", "Date")], title_field="tag_name", show_title=1, search_fields="tag_name")
dt("Life Dimension", [SPACE, f("dimension_name", reqd=1, in_list_view=1), f("sort_order", "Int"),
	f("is_archived", "Check", default="0"), f("archived_on", "Date")], title_field="dimension_name", show_title=1)
dt("Life Person", [
	SPACE, f("full_name", reqd=1, in_list_view=1), f("relation", in_list_view=1), link("user", "User"), md("notes_md"),
], title_field="full_name", show_title=1, search_fields="full_name")
dt("Life Settings", [
	link("default_space", "Life Space"),
	sel("weekly_review_day", ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], default="Sunday"),
	f("weekly_review_time", "Time", default="18:00:00"),
	f("score_target", "Int", default="85"),
	f("archive_after_days", "Int", default="90"),
	f("stale_task_days", "Int", default="90"),
	# UX fixes, set 5: Reset rules
	f("stuck_after_days", "Int", default="30", label="Stuck After (Days)"),
	f("stuck_limit", "Int", default="50"),
	f("open_task_goal", "Int", default="100"),
	f("someday_review_months", "Int", default="3", label="Someday Review After (Months)"),
	# UX fixes, set 5: the AI model behind Ask and the insights
	f("ai_section", "Section Break", label="AI"),
	f("anthropic_api_key", "Password", label="Anthropic API Key"),
	f("ask_model", default="claude-sonnet-5-5"), f("short_model", default="claude-haiku-5-5", label="Short-task Model"),
	f("monthly_cap_usd", "Float", default="30", label="Monthly Cap (USD)"),
	f("ai_prices", "Table", "Life AI Price", label="Prices per Model"),
	f("insights_run_on", "Datetime", read_only=1, label="Insights Last Run"),
], issingle=1, permissions=[
	{"role": "Life Admin", "read": 1, "write": 1, "create": 1},
	{"role": "Life User", "read": 1}, {"role": "Life Agent", "read": 1}])

# ---- capture ----
dt("Life Inbox Item", [
	SPACE, f("title", reqd=1, in_list_view=1),
	sel("source_type", ["Upload", "Journal Photo", "Voice Note", "Email", "Email Digest", "Chat", "Message", "Web"], default="Upload"),
	f("received_on", "Datetime", search_index=1, in_list_view=1),
	sel("intent", INTENTS, default="Process", search_index=1),
	sel("media_kind", MEDIA_KINDS, search_index=1, read_only=1, description="Set on save from the file or the source type"),
	f("source_system", length=40, search_index=1), f("external_id", length=255),
	f("instruction", "Small Text"), md("raw_text"), md("transcript_md"), md("summary_md"),
	f("source_url", length=500),
	sel("status", ["New", "Processing", "To Review", "Done", "Failed"], default="New", in_list_view=1, search_index=1),
	link("claimed_by", "User"), f("claimed_on", "Datetime"), f("error", "Small Text"), f("finished_on", "Date"),
	f("preview_image", "Attach Image"), f("thumbnail", "Attach Image", description="About 480 px wide, made on upload"),
	link("vault_document", "Life Vault Document", read_only=1, description="Set when a Vault document is made from this item"),
	*org(),
], title_field="title", show_title=1)
dt("Life Proposal", [
	SPACE, link("inbox_item", "Life Inbox Item", reqd=1, search_index=1, in_list_view=1),
	sel("kind", ["Task", "Event", "Important Date", "Note", "Vault Document", "Month Goal", "Habit Log", "Check-in", "Week Tick", "Journal Page", "Someday"], reqd=1, in_list_view=1),
	f("preview", "Small Text", in_list_view=1), f("payload", "JSON"), f("confidence", "Float"),
	sel("status", ["Pending", "Accepted", "Rejected"], default="Pending", in_list_view=1, search_index=1),
	link("created_doctype", "DocType"), f("created_name", "Dynamic Link", "created_doctype"),
	link("decided_by", "User"), f("decided_on", "Datetime"), f("sort_order", "Int"),
], title_field="preview")

# ---- tasks and dates ----
dt("Life Task", [
	SPACE, f("title", reqd=1, in_list_view=1),
	sel("status", ["Open", "Doing", "Waiting", "Done", "Dropped", "Carried", "Someday"], default="Open", in_list_view=1, search_index=1),
	sel("priority", PRIORITY, in_list_view=1),
	f("due_date", "Date", in_list_view=1, search_index=1),
	link("goal", "Life Goal"), link("month_plan", "Life Month Plan"), link("inbox_item", "Life Inbox Item", search_index=1),
	f("source_url", length=500), md("notes_md"), f("waiting_on"), f("completed_on", "Date"),
	link("carried_from", "Life Task"), f("last_touched_on", "Date", search_index=1),
	*org(), *someday(),
	link("someday_with", "Life Project", description="Parked together with this project"),
], title_field="title", show_title=1, search_fields="title")
dt("Life Important Date", [
	SPACE, f("title", reqd=1, in_list_view=1), link("person", "Life Person"),
	f("day", "Int", reqd=1, in_list_view=1), f("month", "Int", reqd=1, in_list_view=1), f("year", "Int"),
	sel("kind", ["Birthday", "Anniversary", "Other"], default="Birthday", in_list_view=1),
	link("inbox_item", "Life Inbox Item"),
], title_field="title", show_title=1)

# ---- journal ----
dt("Life Cycle", [
	SPACE, f("title", reqd=1, in_list_view=1), f("start_date", "Date", reqd=1, in_list_view=1),
	f("end_date", "Date", read_only=1, in_list_view=1),
	sel("status", ["Planned", "Active", "Closed"], default="Planned", in_list_view=1, search_index=1),
	f("final_score", "Float", read_only=1), f("closed_on", "Date", read_only=1),
], title_field="title", show_title=1)
dt("Life Goal", [
	SPACE, link("cycle", "Life Cycle", search_index=1), f("title", reqd=1, in_list_view=1),
	sel("goal_type", ["12 Week Year", "Annual", "Open"], reqd=1, default="12 Week Year", in_list_view=1, search_index=1, label="Type"),
	f("target_date", "Date"), f("closed_on", "Date"),
	link("area", "Life Area", in_list_view=1, search_index=1), link("project", "Life Project"), f("sort_order", "Int"),
	f("actions", "Table", "Life Goal Action"),
	sel("outcome", ["In Progress", "Achieved", "Partly Achieved", "Not Achieved", "Carried", "Dropped"], default="In Progress"),
	f("result_note", "Small Text"), link("carried_from", "Life Goal", search_index=1), f("final_score", "Float", read_only=1),
	f("is_someday", "Check", default="0", search_index=1, label="On the Someday List",
		description="Parked, whatever its outcome; the 12 Week Year history is not changed"),
	*someday(),
], title_field="title", show_title=1, search_fields="title")
dt("Life Month Plan", [
	SPACE, f("year", "Int", reqd=1, in_list_view=1), f("month", "Int", reqd=1, in_list_view=1),
	f("goals", "Table", "Life Month Plan Goal"), f("habits", "Table", "Life Month Plan Habit"),
	md("mindsweep_md"), md("projects_md"),
], autoname="prompt")
dt("Life Habit", [SPACE, f("title", reqd=1, in_list_view=1), link("area", "Life Area"),
	f("is_archived", "Check", default="0"), f("archived_on", "Date")], title_field="title", show_title=1, search_fields="title")
dt("Life Habit Log", [
	SPACE, link("habit", "Life Habit", reqd=1, in_list_view=1, search_index=1),
	f("date", "Date", reqd=1, in_list_view=1, search_index=1), f("done", "Check", default="1", in_list_view=1),
	link("inbox_item", "Life Inbox Item"),
], autoname="prompt")
dt("Life Check-in", [
	SPACE, f("date", "Date", reqd=1, in_list_view=1, search_index=1), f("scores", "Table", "Life Check-in Score"), md("reflection_md"),
	link("inbox_item", "Life Inbox Item"),
])
dt("Life Journal Page", [
	SPACE, f("page_date", "Date", reqd=1, in_list_view=1, search_index=1), f("page_number", in_list_view=1),
	f("image", "Attach Image"), md("transcript_md"), link("inbox_item", "Life Inbox Item", search_index=1),
	*org(),
])

# ---- library ----
dt("Life Note", [
	SPACE, f("title", reqd=1, in_list_view=1), link("parent_note", "Life Note", search_index=1), md("content_md"),
	link("inbox_item", "Life Inbox Item", search_index=1),
	sel("collection", ["My notes", "Wiki"], default="My notes", search_index=1),
	f("summary", "Small Text", description="One line. Required for wiki pages"),
	f("sources", "Table", "Life Note Source"),
	f("is_rules", "Check", default="0", description="The wiki's rules page; one per space"),
	f("last_opened_on", "Date", search_index=1, description="The last day a person opened it (its creation counts)"),
	*org(),
], title_field="title", show_title=1, search_fields="title")
dt("Life Wiki Change", [
	SPACE, link("note", "Life Note", reqd=1, search_index=1, in_list_view=1, label="Page"),
	sel("change_type", ["Created", "Edited", "Reverted", "Moved to My notes", "Moved to Wiki"], reqd=1, in_list_view=1),
	link("changed_by", "User", in_list_view=1, label="By"), f("changed_on", "Datetime", search_index=1, in_list_view=1, label="On"),
	f("change_note", "Small Text"),
	link("source_doctype", "DocType"), f("source_name", "Dynamic Link", "source_doctype"),
	md("before_md"), md("after_md"), f("reverted", "Check", default="0"),
	link("reverts", "Life Wiki Change", description="The change this one undid"),
], permissions=[{"role": r, "read": 1, "report": 1} for r in ("Life Admin", "Life User", "Life Agent")], in_create=1, title_field="note")
dt("Life Connection", [
	SPACE, f("system", reqd=1, in_list_view=1, length=40), f("label", in_list_view=1),
	link("default_area", "Life Area"), link("default_project", "Life Project"),
	sel("default_intent", INTENTS, default="Process"), f("active", "Check", default="1", in_list_view=1),
	f("last_received_on", "Datetime", read_only=1, in_list_view=1), f("last_received_what", read_only=1),
], permissions=perms(agent_write=False), title_field="label")
dt("Life Vault Document", [
	SPACE, f("title", reqd=1, in_list_view=1),
	sel("doc_type", ["ID", "Travel", "Insurance", "Property", "Tax", "Medical", "Other"], default="Other", in_list_view=1),
	link("holder", "Life Person", in_list_view=1), f("file", "Attach"),
	f("number_last4", length=4), f("issue_date", "Date"), f("expiry_date", "Date", in_list_view=1, search_index=1),
	f("remind_days_before", "Int", default="60"), md("notes_md"), link("inbox_item", "Life Inbox Item", search_index=1),
	*org(),
], title_field="title", show_title=1, search_fields="title")
dt("Life Chat Log", [
	SPACE, f("date", "Date", reqd=1, in_list_view=1, search_index=1), f("title", reqd=1, in_list_view=1),
	f("url", length=500), sel("assistant", ["Claude", "ChatGPT", "Codex", "Claude Code", "Other"], default="Claude", in_list_view=1),
	f("updated_on", "Datetime", search_index=1, description="The chat's last activity"),
	md("summary_md"), md("transcript_md"), f("open_items", "Table", "Life Chat Open Item"), link("inbox_item", "Life Inbox Item"),
	f("source_system", length=40, search_index=1), f("external_id", length=255),
	*org(),
], title_field="title", show_title=1, search_fields="title")
dt("Life Link", [
	SPACE, f("from_doctype", reqd=1, in_list_view=1), f("from_name", reqd=1, in_list_view=1),
	f("to_doctype", reqd=1, in_list_view=1), f("to_name", reqd=1, in_list_view=1), f("link_text"),
], permissions=perms(agent_write=False), in_create=1)
dt("Life Index", [
	SPACE, f("ref_doctype", reqd=1, label="Record Type"), f("ref_name", reqd=1, label="Record"),
	f("area", in_list_view=1), f("also_in_csv", "Small Text"), f("project", in_list_view=1), f("tags_csv", "Small Text"),
	f("record_date", "Date", in_list_view=1, label="Date"), f("title", length=255, in_list_view=1), f("search_text", "Long Text"),
	f("is_archived", "Check", default="0"), f("kind", in_list_view=1), f("status"), f("record_owner"),
	# UX fixes, set 4: what the Sources and Wiki screens filter on, so they need no second query
	sel("media_kind", ["", "Voice", "Document", "Photo", "Article", "Email", "Email Digest", "Text", "Chat"], label="Kind of source"),
	f("source_system", length=40), sel("intent", ["", *INTENTS]), f("assistant", length=40),
	sel("collection", ["", "My notes", "Wiki"]), f("thumbnail", length=255),
	f("vault_locked", "Check", default="0", description="A Vault document, or a source a Vault document was made from"),
	f("last_opened_on", "Date", description="Notes: the last day a person opened it (UX fixes, set 5)"),
], permissions=perms(agent_write=False), in_create=1, title_field="title")
dt("Life Action Log", [
	SPACE, link("goal", "Life Goal", reqd=1, search_index=1), f("action_id", reqd=1, search_index=1),
	link("cycle", "Life Cycle", reqd=1, search_index=1), f("week", "Int", reqd=1), f("date", "Date", reqd=1, search_index=1),
	f("count", "Int", default="1"), link("inbox_item", "Life Inbox Item"),
], autoname="prompt")

# ---- UX fixes, set 5: Someday ideas, insights, Ask, AI usage ----
dt("Life Idea", [
	SPACE, f("title", reqd=1, in_list_view=1), md("body_md", label="Body"),
	link("area", "Life Area", in_list_view=1, search_index=1), link("project", "Life Project"),
	link("source_doctype", "DocType"), f("source_name", "Dynamic Link", "source_doctype"),
	sel("status", ["Someday", "Brought Back"], default="Someday", in_list_view=1, search_index=1),
	link("brought_to_doctype", "DocType"), f("brought_to_name", "Dynamic Link", "brought_to_doctype"),
	*someday(),
], permissions=perms(agent_write=False), title_field="title", show_title=1, search_fields="title")
NO_AGENT = [{"role": "Life Admin", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1},
	{"role": "Life User", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1}]
dt("Life Insight", [
	SPACE, sel("kind", ["Stuck", "Waiting on you", "Promise", "12 Week Year", "Habit", "Check-in", "Theme", "Someday"], reqd=1,
		in_list_view=1, search_index=1),
	f("title", reqd=1, in_list_view=1, length=255), f("body", "Small Text"),
	f("evidence", "Table", "Life Insight Evidence"), f("actions", "JSON", label="Suggested Actions"),
	sel("status", ["New", "Snoozed", "Acted", "Dismissed"], default="New", in_list_view=1, search_index=1),
	f("snooze_until", "Date"), f("fingerprint", length=140, search_index=1),
	sel("source", ["Rule", "AI"], default="Rule", in_list_view=1), link("area", "Life Area"),
	f("found_on", "Date", search_index=1), f("rank", "Int"),
	sel("dismiss_reason", ["", "Not relevant", "Already done", "Wrong"]), f("acted_note", "Small Text"),
], permissions=NO_AGENT, title_field="title")
dt("Life Ask Thread", [
	SPACE, link("user", "User", reqd=1, search_index=1), f("title", in_list_view=1, length=255),
	link("scope_doctype", "DocType"), f("scope_name", "Dynamic Link", "scope_doctype"), f("scope_label"),
	f("scope_kind", description="space, area, project, goal, goals, journal, items, record, notes"),
	f("last_message_on", "Datetime", search_index=1, in_list_view=1),
], permissions=NO_AGENT, title_field="title")
dt("Life Ask Message", [
	link("thread", "Life Ask Thread", reqd=1, search_index=1), sel("role", ["user", "assistant"], reqd=1, in_list_view=1),
	md("text"), f("cited", "JSON"), f("actions", "JSON", label="Suggested Actions"), f("records_read", "JSON"),
	sel("status", ["Done", "Working", "Error"], default="Done"), f("error", "Small Text"),
	f("input_tokens", "Int"), f("output_tokens", "Int"), f("cost", "Float"),
], permissions=NO_AGENT)
dt("Life AI Usage", [
	link("user", "User", search_index=1, in_list_view=1), f("month", search_index=1, in_list_view=1, length=7),
	f("model", in_list_view=1), f("input_tokens", "Int"), f("output_tokens", "Int"), f("cost", "Float", in_list_view=1),
	sel("purpose", ["Ask", "Insights", "Batches", "Wording", "Test"], in_list_view=1), link("space", "Life Space"),
], permissions=[{"role": "Life Admin", "read": 1, "report": 1}], in_create=1)

# ---- per-user screen state (UX fixes, set 2): one row per user, screen and space ----
OWN_ROWS = {"read": 1, "write": 1, "create": 1, "delete": 1}
dt("Life View State", [
	link("user", "User", reqd=1, search_index=1, in_list_view=1), f("screen", reqd=1, in_list_view=1, length=60),
	link("space", "Life Space", in_list_view=1), f("state", "JSON"),
], permissions=[{"role": "Life Admin", **OWN_ROWS}, {"role": "Life User", **OWN_ROWS}], in_create=1)

TRACK = {"Life Note", "Life Task", "Life Vault Document", "Life Project", "Life Goal", "Life Month Plan", "Life Journal Page", "Life Inbox Item"}


def build(name, fields, kw):
	doc = {
		"actions": [], "creation": STAMP, "doctype": "DocType", "engine": "InnoDB",
		"field_order": [x["fieldname"] for x in fields], "fields": fields,
		"links": [], "modified": STAMP, "modified_by": "Administrator", "module": "Life", "name": name,
		"owner": "Administrator", "sort_field": "creation", "sort_order": "DESC", "states": [],
	}
	if kw.get("istable"):
		doc["istable"] = 1
		doc["editable_grid"] = 1
		doc["permissions"] = []
	elif kw.get("issingle"):
		doc["issingle"] = 1
		doc["permissions"] = kw["permissions"]
	else:
		doc["permissions"] = kw.get("permissions") or perms()
		doc["autoname"] = kw.get("autoname", "hash")
		doc["naming_rule"] = {"hash": "Random", "prompt": "Set by user"}.get(doc["autoname"], "By fieldname")
		if name in TRACK:
			doc["track_changes"] = 1
	for k in ("title_field", "search_fields", "in_create"):
		if k in kw:
			doc[k] = kw[k]
	if kw.get("show_title"):
		doc["show_title_field_in_link"] = 1  # link pickers show the title, not the random id
	return dict(sorted(doc.items()))


def main():
	for name, (fields, kw) in DOCTYPES.items():
		folder = os.path.join(ROOT, scrub(name))
		os.makedirs(folder, exist_ok=True)
		with open(os.path.join(folder, scrub(name) + ".json"), "w") as fh:
			json.dump(build(name, [dict(x) for x in fields], kw), fh, indent=1, sort_keys=False)
			fh.write("\n")
		init = os.path.join(folder, "__init__.py")
		if not os.path.exists(init):
			open(init, "w").close()
		py = os.path.join(folder, scrub(name) + ".py")
		if not os.path.exists(py):
			cls = re.sub(r"[ \-]", "", name)
			with open(py, "w") as fh:
				fh.write(f"from frappe.model.document import Document\n\n\nclass {cls}(Document):\n\tpass\n")
	open(os.path.join(ROOT, "__init__.py"), "a").close()
	print(f"{len(DOCTYPES)} doctypes written")


if __name__ == "__main__":
	main()
