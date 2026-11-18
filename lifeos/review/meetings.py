"""Meetings that matter, and what was captured around them (set 8).

A meeting matters when at least one attendee's email domain is not one of the owner's domains (Settings > Me), it lasts 30
minutes or more, and it is not a recurring event whose attendees are all from those domains. Events with no attendees do not
matter. The owner can mark any event by hand, which overrides the rule (`life_matters_set_by` Owner).

A capture, voice note, email, chat log or note is linked to a meeting that matters when it was made during the meeting or within
two hours after it and names an attendee (Both). Time alone links only voice notes and captures made during the meeting or
within 30 minutes after its end (Time). An email from or naming an attendee within two days after links by People. The owner
links and unlinks by hand (Owner); an unlinked record is kept as removed so the rule does not link it again.
"""
import json
import re
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate

MIN_MINUTES = 30
AFTER_H = 2
TIME_ONLY_MIN = 30
EMAIL_AFTER_H = 48
CAPTURES = ("Voice Note", "Upload", "Journal Photo", "Message", "Web")
EMAILS = ("Email", "Email Digest")
KIND_LABEL = {"Life Chat Log": "Chat", "Life Note": "Note"}


# ---- the rule ----

def own_domains():
	"""The owner's domains: the setting, one per line; when empty, the domains of the space owners' own addresses."""
	text = frappe.db.get_single_value("Life Settings", "own_domains") or ""
	got = [d.strip().lstrip("@").lower() for d in re.split(r"[\s,;]+", text) if d.strip()]
	if got:
		return got
	owners = frappe.get_all("Life Space", pluck="owner_user")
	return sorted({u.split("@")[-1].lower() for u in owners if u and "@" in u})


def attendees(doc):
	try:
		rows = json.loads(doc.get("life_attendees") or "[]")
	except ValueError:
		rows = []
	return [r for r in rows if isinstance(r, dict) and r.get("email")]


def minutes(doc):
	if doc.get("all_day") or not doc.get("ends_on"):
		return 0
	return int((get_datetime(doc.ends_on) - get_datetime(doc.starts_on)).total_seconds() // 60)


def matters_by_rule(doc, domains=None):
	people = attendees(doc)
	if not people or minutes(doc) < MIN_MINUTES:
		return False
	domains = own_domains() if domains is None else domains
	outside = [p for p in people if p["email"].split("@")[-1].lower() not in domains]
	if doc.get("life_recurring") and not outside:
		return False
	return bool(outside)


def apply_rule(doc, domains=None):
	"""Set `life_matters` from the rule unless the owner set it."""
	if doc.get("life_matters_set_by") == "Owner":
		return
	doc.life_matters = 1 if matters_by_rule(doc, domains) else 0
	doc.life_matters_set_by = "Rule"


def mark(event, matters):
	"""The owner's override: True or False, or None to go back to the rule."""
	doc = frappe.get_doc("Event", event)
	doc.check_permission("write")
	if matters is None:
		doc.life_matters_set_by = "Rule"
		apply_rule(doc)
	else:
		doc.life_matters, doc.life_matters_set_by = 1 if matters else 0, "Owner"
	doc.save()
	return doc


# ---- meetings in a period ----

def in_period(space, start, end, only_matter=False):
	"""Timed and all-day events of the space between two dates (repeats as Google sent them), in order."""
	filters = {"life_space": space, "starts_on": ("between", [f"{getdate(start)} 00:00:00", f"{getdate(end)} 23:59:59"]), "status": ("!=", "Cancelled")}
	if only_matter:
		filters["life_matters"] = 1
	return frappe.get_all("Event", filters=filters, fields=["name", "subject", "starts_on", "ends_on", "all_day", "life_attendees", "life_matters",
		"life_matters_set_by", "life_recurring", "life_followups_on"], order_by="starts_on asc", limit=500)


def link_period(space, start, end):
	"""Link the period's records to its meetings that matter by the rule. Returns the number of new links."""
	meets = in_period(space, start, end, only_matter=True)
	if not meets:
		return 0
	lo = min(get_datetime(m.starts_on) for m in meets)
	hi = max(get_datetime(m.ends_on or m.starts_on) for m in meets) + timedelta(hours=EMAIL_AFTER_H)
	records = _records(space, lo, hi)
	have = {(r.event, r.record_doctype, r.record_name) for r in frappe.get_all("Life Meeting Link", filters={"event": ("in", [m.name for m in meets])},
		fields=["event", "record_doctype", "record_name"], limit=20000)}
	people = _people(space)
	n = 0
	for m in meets:
		names = _names(m, people)
		for r in records:
			how = _how(m, r, names)
			if how and (m.name, r.doctype, r.name) not in have:
				_add(space, m.name, r.doctype, r.name, r.title, how)
				have.add((m.name, r.doctype, r.name))
				n += 1
	return n


def _how(m, r, names):
	start, end = get_datetime(m.starts_on), get_datetime(m.ends_on or m.starts_on)
	t = get_datetime(r.at)
	named = _names_in(r.text, names)
	if start <= t <= end + timedelta(hours=AFTER_H) and named:
		return "Both"
	if r.kind == "capture" and start <= t <= end + timedelta(minutes=TIME_ONLY_MIN):
		return "Time"
	if r.kind == "email" and named and end <= t <= end + timedelta(hours=EMAIL_AFTER_H):
		return "People"
	return None


def _records(space, lo, hi):
	out = []
	for i in frappe.db.sql("""select name, title, source_type, ifnull(received_on, creation) as at, concat_ws(' ', title, raw_text, transcript_md, summary_md) as text
		from `tabLife Inbox Item` where space = %s and ifnull(received_on, creation) between %s and %s""", (space, lo, hi), as_dict=True):
		kind = "email" if i.source_type in EMAILS else "capture" if i.source_type in CAPTURES else "chat"
		out.append(frappe._dict(doctype="Life Inbox Item", name=i.name, title=i.title, at=i.at, text=i.text or "", kind=kind))
	for c in frappe.db.sql("""select name, title, ifnull(updated_on, creation) as at, concat_ws(' ', title, summary_md, left(transcript_md, 20000)) as text
		from `tabLife Chat Log` where space = %s and ifnull(updated_on, creation) between %s and %s""", (space, lo, hi), as_dict=True):
		out.append(frappe._dict(doctype="Life Chat Log", name=c.name, title=c.title, at=c.at, text=c.text or "", kind="chat"))
	for n in frappe.db.sql("""select name, title, creation as at, concat_ws(' ', title, content_md) as text from `tabLife Note`
		where space = %s and creation between %s and %s and title not like 'Weekly review, %%'""", (space, lo, hi), as_dict=True):
		out.append(frappe._dict(doctype="Life Note", name=n.name, title=n.title, at=n.at, text=n.text or "", kind="note"))
	return out


def _people(space):
	return frappe.get_all("Life Person", filters={"space": space}, fields=["full_name", "user"], limit=2000)


def _names(m, people):
	"""What naming an attendee looks like: the email, the name Google gives, and a Life Person matched by name or email."""
	out = set()
	for a in attendees(m):
		out.add(a["email"].lower())
		name = (a.get("name") or "").strip()
		if len(name) >= 3:
			out.add(name.lower())
		for p in people:
			full = (p.full_name or "").strip()
			if (p.user and p.user.lower() == a["email"].lower()) or (full and name and (full.lower() == name.lower() or full.split()[0].lower() == name.lower())):
				out.add(full.lower())
	return out


def _names_in(text, names):
	low = (text or "").lower()
	return any(re.search(r"(?<![\w@.])" + re.escape(n) + r"(?![\w@])", low) for n in names)


def _add(space, event, doctype, name, title, how):
	return frappe.get_doc({"doctype": "Life Meeting Link", "space": space, "event": event, "record_doctype": doctype, "record_name": name,
		"title": (title or name)[:140], "how": how}).insert(ignore_permissions=True)


def link(event, doctype, name):
	"""The owner links a record by hand."""
	from lifeos import permissions

	ev = frappe.get_doc("Event", event)
	ev.check_permission("write")
	doc = permissions.get_doc_checked(doctype, name, "read")
	if doc.get("space") != ev.life_space:
		frappe.throw(_("That record is in another space."))
	got = frappe.db.get_value("Life Meeting Link", {"event": event, "record_doctype": doctype, "record_name": name})
	if got:
		frappe.db.set_value("Life Meeting Link", got, {"removed": 0, "how": "Owner"})
		return got
	return _add(ev.life_space, event, doctype, name, doc.get("title") or name, "Owner").name


def unlink(link_name):
	"""The owner unlinks: kept as removed, so the rule does not link it again."""
	from lifeos import permissions

	permissions.get_doc_checked("Life Meeting Link", link_name, "write")
	frappe.db.set_value("Life Meeting Link", link_name, "removed", 1)


def linked(event):
	rows = frappe.get_all("Life Meeting Link", filters={"event": event, "removed": 0}, fields=["name", "record_doctype", "record_name", "title", "how"],
		order_by="creation asc", limit=200)
	return [r for r in rows if frappe.db.exists(r.record_doctype, r.record_name)]


def label_of(doctype, name):
	if doctype == "Life Inbox Item":
		kind = frappe.db.get_value("Life Inbox Item", name, "source_type") or "Capture"
		return {"Voice Note": "Voice note", "Email Digest": "Email", "Email": "Email"}.get(kind, "Capture")
	return KIND_LABEL.get(doctype, doctype.replace("Life ", ""))
