"""The email digest (issue 86): how email enters Life OS. Nothing is copied. Each morning one Brain item lists the mail from real people since the day
before, grouped by inbox, each with the sender, the subject, one line and a File it button; on Sundays a second item rolls up the week. Newsletters and
notifications are left out. Anything else is found by live search (`lifeos.mail.search`) and filed only when the owner says so.

Plumbing: the cheap header rules (`GmailAdapter.recent`), the always-include and always-skip lists of each connection, and one item for each person and day.
Who counts as a real person beyond that is the `ingest-email` skill's judgment (the Gmail channel's rules, `channel-gmail`).
"""
import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from lifeos import mail
from lifeos.mail.gmail import scrub

LINE_CHARS = 140
PER_INBOX = 40  # lines of one inbox in one digest


def run_daily():
	"""Scheduled each morning: a digest for each person who has an inbox on, and the week's roll-up on Sundays."""
	today = getdate(nowdate())
	pairs = {(r.user, r.space) for r in frappe.get_all("Life Mail Account", filters={"active": 1}, fields=["user", "space"])}  # system: the scheduled job reads every person's accounts to make their own digest
	for user, space in sorted(pairs):
		for days, weekly in ((1, False), *(((7, True),) if today.weekday() == 6 else ())):
			try:
				make(user, space, days, weekly, today)
				frappe.db.commit()
			except Exception as e:  # noqa: BLE001 - one person's failing inbox never stops the others
				frappe.db.rollback()
				frappe.log_error(title="Life OS mail digest failed", message=f"{type(e).__name__}: {scrub(e)[:200]}")


def _one_line(hit: dict, space: str) -> str | None:
	"""One line about a thread: the skill's own words when it gave them, else the start of the message."""
	from lifeos.skills import call

	answer = call.ask("ingest-email", {"from": hit["from"], "to": hit.get("to", ""), "subject": hit["subject"], "snippet": hit["snippet"][:600], "mailbox": "",
		"messages_in_thread": hit["messages"]}, space)
	if answer and answer.get("keep") is False:
		return None
	return " ".join(str(hit["snippet"]).split())[:LINE_CHARS]


def make(user: str, space: str, days: int = 1, weekly: bool = False, today=None) -> str | None:
	"""The digest of one person's inboxes for the last `days` days; the item's name, or None when nothing from a person came in. Run again for the same day it updates the same item."""
	today = getdate(today or nowdate())
	since = str(add_days(today, -days))
	sections, lines, sensitive, systems = [], 0, False, set()
	for row in mail.accounts_for(user, space):
		doc = frappe._dict(row)
		conn = frappe.db.get_value("Life Connection", doc.connection, ["label_name", "always_include", "always_skip", "always_sensitive"], as_dict=True) if doc.connection else None
		conn = conn or frappe._dict()
		try:
			hits = mail.adapter(doc).recent(since, conn.label_name or "", conn.always_include or "", conn.always_skip or "")
		except Exception as e:  # noqa: BLE001 - an inbox that fails is said in the digest, the others still count
			sections.append(f"## {mail.label_of(doc)}\n\n_This inbox could not be read: {scrub(e)[:120]}_")
			continue
		for h in hits:  # issue 111: every email seen is linked to the subjects it is about (the Brain's pages)
			_seen(space, h)
		items = []
		for h in sorted((h for h in hits if h["person"]), key=lambda h: h["at"], reverse=True)[:PER_INBOX]:
			line = _one_line(h, space)
			if line is None:
				continue
			if conn.always_sensitive and _listed(h["sender"], conn.always_sensitive):
				sensitive = True
			subject = h["subject"].replace("[", "(").replace("]", ")")
			items.append(f"- **{h['from']}**: {subject}. {line} [Open in {mail.PROVIDER_NAMES.get(doc.provider, 'mail')}]({h['link']}) [File it](lifeos-file:{doc.name}:{h['thread_id']})")
		if items:
			systems.add(doc.provider)
			sections.append(f"## {mail.label_of(doc)}\n\n" + "\n".join(items))
			lines += len(items)
	if not lines:
		return None
	from lifeos.api import inbox

	title = _("Email this week, to {0}").format(today.strftime("%-d %b")) if weekly else _("Email, {0}").format(today.strftime("%-d %b"))
	text = "\n\n".join(sections)
	done = inbox.create_item(space=space, source_type="Email Digest", source_system="gmail" if "gmail" in systems or not systems else sorted(systems)[0], external_id=f"digest:{user}:{'week' if weekly else 'day'}:{today}",
		title=title, raw_text=text, intent="Just keep")  # made by the scheduled job; the item belongs to the person's space
	if sensitive:
		frappe.db.set_value("Life Inbox Item", done["name"], "is_sensitive", 1, update_modified=False)
	return done["name"]


def _seen(space: str, hit: dict):
	"""Link an email the digest saw to the subjects it is about; a failure here never stops the digest."""
	from lifeos.library import subjects

	try:
		subjects.see_email(space, subjects.mail_of_hit(hit))
	except Exception:  # noqa: BLE001 - the digest is what the owner reads; a page that could not be linked waits for the next one
		frappe.log_error(title="Life OS: could not link an email to its pages")


def _listed(sender: str, text: str) -> bool:
	from lifeos.mail import gmail

	return gmail.listed(sender, gmail._lines(text))
