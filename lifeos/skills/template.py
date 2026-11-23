"""The one template of a source skill (issue 84), and how its sections are read, edited and put together with the base skill.

A source is a *channel* (where a thing comes from: Gmail, an agent, the phone) or a *kind* (what it is: a PDF, a photo). Each has one
skill written in the same sections. Something that arrives is read with the base skill's shared rules (`process-capture`), then its
channel's rules, then its kind's. Only the sections below are put into a run; anything else a skill file says (how it answers when it
is run alone) is not. The Rules tab shows these sections as fields and saves them back into the skill's text, so each save is a version.
"""
import re

import frappe

BASE = "process-capture"
LESSONS = "Lessons"
LESSONS_HEADING = "## Lessons from the owner's corrections"  # lessons.py appends under this heading
ANYTHING = "Anything else"
KIND_SECTIONS = ("What arrives", "Keep", "Skip", "How to read it", "Where it goes", "What to propose", "Never", "Examples", LESSONS)
CHANNEL_SECTIONS = ("What arrives", "Let in", "Check every", "Who may send", "Where it goes", "What to propose", "Never", "Examples", LESSONS)
# how the Rules tab shows a section: chips (one short line each), rows (one line each), or plain text
CHIPS = ("Keep", "Skip", "Let in", "Who may send")
ROWS = ("Where it goes", "What to propose", "Check every")
# kind key -> (skill, label, the media kind of an inbox item)
KINDS = {"document": ("ingest-document", "Documents (PDF)", "Document"), "photo": ("ingest-photo", "Photos", "Photo"),
	"video": ("ingest-video", "Videos", "Video"), "link": ("ingest-link", "Links and articles", "Article"),
	"voice": ("ingest-voice", "Voice notes", "Voice"), "email": ("ingest-email", "Email", "Email")}
CHANNEL_SKILLS = {"upload": "channel-upload", "phone": "channel-phone", "gmail": "channel-gmail", "microsoft": "channel-microsoft", "google-calendar": "channel-calendar",
	"email": "channel-email-in"}
AGENT_SKILL = "channel-agent"
MEDIA_TO_KIND = {"Document": "document", "Photo": "photo", "Video": "video", "Article": "link", "Voice": "voice", "Email": "email", "Email Digest": "email"}


def source_skills() -> list:
	return [*(v[0] for v in KINDS.values()), *CHANNEL_SKILLS.values(), AGENT_SKILL]


def channel_skill(system: str | None) -> str:
	"""The skill of the channel something came in by. Phone and upload have their own; an empty system is an upload; every other is an agent."""
	return CHANNEL_SKILLS.get((system or "").strip().lower() or "upload") or AGENT_SKILL


def kind_skill(media_kind: str | None) -> str | None:
	key = MEDIA_TO_KIND.get(media_kind or "")
	return KINDS[key][0] if key else None


def normal(title: str) -> str:
	title = title.strip().rstrip(":").strip()
	return LESSONS if title.lower().startswith("lessons") else title


def parse(text: str) -> tuple:
	"""(intro, [(title, body)]) from a skill's instructions: the words before the first "## " heading, then each section in order."""
	parts = re.split(r"^## +(.+?)\s*$", text or "", flags=re.M)
	return parts[0].strip(), [(normal(parts[i]), parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]


def sections_of(text: str) -> dict:
	return dict(parse(text)[1])


def assemble(intro: str, sections: list) -> str:
	out = [intro.strip()] if intro.strip() else []
	for title, body in sections:
		heading = LESSONS_HEADING if title == LESSONS else f"## {title}"
		out.append(f"{heading}\n\n{body.strip()}" if body.strip() else heading)
	return "\n\n".join(out).strip() + "\n"


def expected(slug: str) -> tuple:
	return KIND_SECTIONS if slug in (v[0] for v in KINDS.values()) else CHANNEL_SECTIONS


def missing(slug: str, text: str) -> list:
	"""The sections of the template this skill's text lacks (the schema test)."""
	have = sections_of(text)
	return [s for s in expected(slug) if s not in have]


def items_of(body: str) -> list:
	"""The lines of a bulleted section, each without its bullet."""
	return [re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line).strip() for line in (body or "").splitlines() if line.strip()]


def body_of(items: list) -> str:
	return "\n".join(f"- {str(i).strip()}" for i in items if str(i).strip())


def rules_of(slug: str, text: str) -> dict:
	"""What the Rules tab shows: the template's sections with how to show each, and the free "Anything else" text."""
	have = sections_of(text)
	out = []
	for title in expected(slug):
		if title == LESSONS:
			continue  # lessons are the owner's accepted corrections; they have their own tab
		body = have.get(title, "")
		mode = "chips" if title in CHIPS else "rows" if title in ROWS else "text"
		out.append({"title": title, "mode": mode, "items": items_of(body) if mode != "text" else [], "text": body if mode == "text" else ""})
	return {"sections": out, "anything_else": have.get(ANYTHING, "")}


def with_rules(slug: str, text: str, sections: dict, anything_else: str | None) -> str:
	"""`text` with the sections the owner edited put back: `sections` is {title: list of lines | text}. Other sections stay as they were."""
	intro, parts = parse(text)
	known = dict(parts)
	for title, value in (sections or {}).items():
		if title in expected(slug) and title != LESSONS:
			known[title] = body_of(value) if isinstance(value, (list, tuple)) else str(value or "").strip()
	if anything_else is not None:
		known[ANYTHING] = str(anything_else).strip()
	order = [t for t, _body in parts]
	order += [t for t in (*expected(slug), ANYTHING) if t not in order and (known.get(t) or t in expected(slug))]
	return assemble(intro, [(t, known.get(t, "")) for t in order if t != ANYTHING or known.get(t)])


def rule_text(slug: str) -> str:
	"""A source skill's template sections as one text, as the owner has them (an edit counts); empty when the skill is switched off."""
	from lifeos.skills import store

	if frappe.db.exists("Life Skill", slug) and not frappe.db.get_value("Life Skill", slug, "active"):
		return ""
	if not (store.builtin(slug) or frappe.db.exists("Life Skill", slug)):
		return ""
	have = sections_of(store.instructions_of(slug))
	return "\n\n".join(f"## {t}\n\n{have[t]}" for t in (*expected(slug), ANYTHING) if have.get(t))


def put_together(base: str, channel: str | None, kind: str | None) -> tuple:
	"""(the instructions of one run, the skills it used): the base's, then the channel's template sections, then the kind's."""
	text, used = base, []
	for label, slug in (("channel", channel), ("kind", kind)):
		body = rule_text(slug) if slug else ""
		if body:
			used.append(slug)
			text += (f"\n\n# Rules of the {label}: {slug}\nThese come after the shared rules above and add to them. Where they differ, "
				f"the {label}'s rules win, except the Never of the shared rules.\n\n{body}")
	return text, used
