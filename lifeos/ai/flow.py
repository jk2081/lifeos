"""Life OS's tools and agent for Frappe Flow (issue 108): the Ask tools of `lifeos.ai.tools`, one-line wrappers.

Flow runs each as the asking user. `_run` builds Ask's own `Context` for that user's default space and calls `run_tool`,
so the space, Vault and scope rules are the ones Ask has, and a second user without the space is refused by the same checks.
Writes need no confirmation because the answer lists them with Undo; nothing here sends or deletes.
Ask's own screens are unchanged; this is for trying at /flow.
"""
import frappe
from frappe.flow import Agent, ToolContext, tool

from lifeos.ai.tools import Context, run_tool

TOOL_NAMES = ['search', 'read_page', 'get_record', 'list_records', 'counts', 'cycle_state', 'timeline', 'catch_up', 'mail_search', 'mail_thread', 'mail_list_threads', 'digests_read', 'save_attachment', 'create_page', 'update_page', 'add_person', 'save_note', 'make_task', 'add_event', 'make_rule']


def _run(name: str, ctx: ToolContext, **args) -> dict:
	"""Run Ask's tool `name` as the user Flow runs for, in their default space."""
	from lifeos.permissions import default_space, require_space

	if frappe.session.user != ctx.user:
		frappe.set_user(ctx.user)  # nosemgrep: frappe-setuser -- Flow names the asking user in ctx; a call made without that session runs as that user, never wider
	space = default_space(ctx.user)
	if not space:
		return {"error": "Not allowed: you are not in any space."}
	try:
		require_space(space)
	except frappe.PermissionError:
		frappe.clear_messages()
		return {"error": "Not allowed: you are not in this space."}
	c = Context(space, user=ctx.user)
	c.background = True  # a long read of mail runs on, not as a background job
	out = run_tool(c, name, args)
	if c.done and isinstance(out, dict):
		out["done_list"] = c.done
	return out

@tool
def search(query: str, kinds: list[str] | None = None, date_from: str | None = None, date_to: str | None = None, *, ctx: ToolContext) -> dict:
	"""Search the owner's records (notes, wiki pages, tasks, sources and their transcripts, chats) by words. Returns matching records with a snippet and a reference."""
	return _run("search", ctx, query=query, kinds=kinds, date_from=date_from, date_to=date_to)


@tool
def read_page(name: str, *, ctx: ToolContext) -> dict:
	"""A person's, company's or part's page: the Brain's brief with its sources and the newest things linked to it. Read it first for any question about a person, company or part."""
	return _run("read_page", ctx, name=name)


@tool
def get_record(ref: str | None = None, doctype: str | None = None, name: str | None = None, *, ctx: ToolContext) -> dict:
	"""One record's fields and text (truncated), by its reference or doctype and name."""
	return _run("get_record", ctx, ref=ref, doctype=doctype, name=name)


@tool
def list_records(kind: str, filters: dict | None = None, order: str | None = None, limit: int | None = None, *, ctx: ToolContext) -> dict:
	"""Rows of one kind, at most 50: tasks, goals, notes, sources, chats, someday, insights."""
	return _run("list_records", ctx, kind=kind, filters=filters, order=order, limit=limit)


@tool
def counts(kind: str, *, ctx: ToolContext) -> dict:
	"""A count with the list it opens: open_tasks, stuck_tasks, overdue_tasks, due_today_tasks, open_goals, idle_goals, goals_in_progress, inbox_to_review, inbox_old, someday, someday_due."""
	return _run("counts", ctx, kind=kind)


@tool
def cycle_state(*, ctx: ToolContext) -> dict:
	"""The active 12 Week Year: week, scores, goals with their actions and this week's ticks, and this month's habits."""
	return _run("cycle_state", ctx)


@tool
def timeline(date_from: str, date_to: str | None = None, *, ctx: ToolContext) -> dict:
	"""What happened in a period: records by day (created, completed, captured)."""
	return _run("timeline", ctx, date_from=date_from, date_to=date_to)


@tool
def catch_up(days: int | None = None, *, ctx: ToolContext) -> dict:
	"""For a broad question ('what's going on', 'catch me up'): what needs the owner, what waits on others, the email digests, what came in and was done, and the next 7 days."""
	return _run("catch_up", ctx, days=days)


@tool
def mail_search(text: str | None = None, has_attachment: bool | None = None, account: str | None = None, subject: str | None = None, filename: str | None = None, after: str | None = None, before: str | None = None, *, ctx: ToolContext) -> dict:
	"""Search the person's own inbox live, with plain fields. Up to 10 threads, newest first."""
	return _run("mail_search", ctx, text=text, has_attachment=has_attachment, account=account, subject=subject, filename=filename, after=after, before=before)


@tool
def mail_thread(thread_id: str, account: str | None = None, *, ctx: ToolContext) -> dict:
	"""Read one thread found by mail_search: each message's text and its attachments."""
	return _run("mail_thread", ctx, thread_id=thread_id, account=account)


@tool
def mail_list_threads(after: str, before: str, query: str | None = None, page_token: str | None = None, account: str | None = None, *, ctx: ToolContext) -> dict:
	"""Every email thread of a period, 25 a page, newest first. Use next_page_token until it is empty."""
	return _run("mail_list_threads", ctx, after=after, before=before, query=query, page_token=page_token, account=account)


@tool
def digests_read(start: str, end: str, *, ctx: ToolContext) -> dict:
	"""The daily email digests Life OS already wrote for a period, and the days that have none."""
	return _run("digests_read", ctx, start=start, end=end)


@tool
def save_attachment(thread_id: str, attachment_id: str, area: str | None = None, part: str | None = None, page: str | None = None, vault_type: str | None = None, account: str | None = None, *, ctx: ToolContext) -> dict:
	"""Save one attachment of an email in Life OS when the owner asks, under an area or part; vault_type sends it to the Vault."""
	return _run("save_attachment", ctx, thread_id=thread_id, attachment_id=attachment_id, area=area, part=part, page=page, vault_type=vault_type, account=account)


@tool
def create_page(title: str, area: str, part: str | None = None, kind: str | None = None, body: str | None = None, summary: str | None = None, sources: list[str] | None = None, *, ctx: ToolContext) -> dict:
	"""Create a wiki page under an area (and a part), when the owner asks for one. kind: Prospect, Client, Project, Person or Note."""
	return _run("create_page", ctx, title=title, area=area, part=part, kind=kind, body=body, summary=summary, sources=sources)


@tool
def update_page(page: str, body: str | None = None, add_links: list[str] | None = None, *, ctx: ToolContext) -> dict:
	"""Change a wiki page: replace its text and/or add links to other pages or people."""
	return _run("update_page", ctx, page=page, body=body, add_links=add_links)


@tool
def add_person(name: str, email: str | None = None, company: str | None = None, link_to: str | None = None, *, ctx: ToolContext) -> dict:
	"""Add a person (with email and company) when the owner asks; one already there is reused."""
	return _run("add_person", ctx, name=name, email=email, company=company, link_to=link_to)


@tool
def save_note(title: str, body: str, area: str, part: str | None = None, *, ctx: ToolContext) -> dict:
	"""Save text you wrote as a note under an area (and a part)."""
	return _run("save_note", ctx, title=title, body=body, area=area, part=part)


@tool
def make_task(title: str, area: str | None = None, part: str | None = None, due_date: str | None = None, *, ctx: ToolContext) -> dict:
	"""Make a task now, only when the owner asked for it."""
	return _run("make_task", ctx, title=title, area=area, part=part, due_date=due_date)


@tool
def add_event(title: str, start: str, end: str | None = None, all_day: bool = False, description: str | None = None, *, ctx: ToolContext) -> dict:
	"""Put an event on the calendar now, only when the owner asked for it."""
	return _run("add_event", ctx, title=title, start=start, end=end, all_day=all_day, description=description)


@tool
def make_rule(action: str = "File", sender: str | None = None, domain: str | None = None, source: str | None = None, kind: str | None = None, title_words: str | None = None,
		area: str | None = None, part: str | None = None, no_area: bool = False, file_as: str | None = None, never_page: bool = False, *, ctx: ToolContext) -> dict:
	"""Teach the Brain, only when the owner said how to treat things from now on: when a capture has the sender, domain, source, kind or title words, file it under an area (or no area), drop it, always ask, or never make a page."""
	return _run("make_rule", ctx, action=action, sender=sender, domain=domain, source=source, kind=kind, title_words=title_words, area=area, part=part, no_area=no_area,
		file_as=file_as, never_page=never_page)


TOOLS = [globals()[n] for n in TOOL_NAMES]


NOTE = """
In this chat there are no suggest_actions and ask_one_question tools: offer a next step in a sentence, and ask a question in plain text and stop.
Writes you make are listed in the answer with Undo by Life OS; say what you did.
"""


def agents() -> list[Agent]:
	"""The "Life OS" agent: Ask's instructions, the same tools, and the site's first enabled model.
	None until a model is set up in Flow; the model can be switched in the desk afterwards."""
	from lifeos.skills import store

	model = frappe.db.get_value("Flow Model", {"enabled": 1, "embedding": 0}, "name", order_by="creation asc")
	if not model:
		return []
	return [
		Agent(
			name="Life OS",
			model=model,
			description="Answers from the owner's Life OS records and files what is asked, each write with Undo.",
			instructions=store.instructions_of("ask") + NOTE,
			tools=TOOLS,
			skills=["ask"],
		)
	]
