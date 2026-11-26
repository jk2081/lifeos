"""Pages that build themselves (issue 111): subjects, and what is linked to them.

A **subject** is a person or an organisation (`Life Person`) or a part (`Life Area` under an area of life). Things that come in (an email, a
capture, a note, a task, a meeting) are linked to the subjects they are about with `Life Link` rows (`origin` Brain or Owner), and each subject's
page reads them back as its timeline. Plumbing only: finding the subjects an email is about, the counts and rules of the table in the issue,
making and merging subjects, and Undo. Who someone is, and whether a stranger deserves a page, is the `link-subjects` skill's judgment.
"""
import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime, nowdate

from lifeos.life.doctype.life_person.life_person import split_aliases

SUBJECTS = ("Life Person", "Life Area")
SKILL = "link-subjects"
BRAIN = "brain"  # the `agent` of a log row the Brain wrote on its own
PUBLIC_DOMAINS = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com", "live.com", "icloud.com", "rediffmail.com", "proton.me", "protonmail.com"}
KIND_OF = {"Life Inbox Item": "Capture", "Life Sender Sighting": "Email", "Life Task": "Task", "Life Note": "Note", "Event": "Meeting", "Life Chat Log": "Chat"}
TIMELINE_CAP = 100


def settings() -> tuple[int, int]:
	"""(how many sightings, within how many days) make a new sender worth proposing: defaults from Settings."""
	s = frappe.get_cached_doc("Life Settings")
	return cint(s.get("subject_seen_count")) or 3, cint(s.get("subject_seen_days")) or 30


def is_part(area) -> bool:
	return bool(area.parent_area) and not area.is_life_area and not area.is_focus


def kind_of_subject(doctype: str, name: str) -> str:
	"""company, person or part: the kind icon of a page."""
	if doctype == "Life Area":
		return "part"
	return "company" if frappe.db.get_value("Life Person", name, "kind") == "Organisation" else "person"


def title_of(doctype: str, name: str) -> str:
	field = {"Life Person": "full_name", "Life Area": "area_name", "Life Note": "title"}[doctype]
	return frappe.db.get_value(doctype, name, field) or name


# ---------------------------------------------------------------- links

def _key(from_dt, from_name, to_dt, to_name) -> str:
	return f"{from_dt}:{from_name}>{to_dt}:{to_name}"


def removed(from_dt, from_name, to_dt, to_name) -> bool:
	"""The owner took this link off once; the Brain does not put it back."""
	return bool(frappe.db.exists("Life Skill Correction", {"skill": SKILL, "correction_type": "Link", "key": _key(from_dt, from_name, to_dt, to_name)}))


def link(space: str, from_dt: str, from_name: str, to_dt: str, to_name: str, origin: str = "Brain", made: bool = False) -> bool:
	"""Link a record to the subject it is about. True when a link was made (not when it was there, or the owner removed it before)."""
	if to_dt not in SUBJECTS or (from_dt, from_name) == (to_dt, to_name):
		return False
	if frappe.db.exists("Life Link", {"from_doctype": from_dt, "from_name": from_name, "to_doctype": to_dt, "to_name": to_name, "origin": ("in", ("Brain", "Owner"))}):
		return False
	if origin == "Brain" and removed(from_dt, from_name, to_dt, to_name):
		return False
	doc = frappe.new_doc("Life Link")
	doc.update({"space": space, "from_doctype": from_dt, "from_name": from_name, "to_doctype": to_dt, "to_name": to_name, "origin": origin, "made_subject": 1 if made else 0,
		"link_text": title_of(to_dt, to_name)[:140]})
	doc.insert(ignore_permissions=True)  # system: the Brain links what it files; the space is the record's own
	return True


def link_all(space: str, from_dt: str, from_name: str, subjects: list, origin: str = "Brain") -> list:
	"""Link a record to each subject (and, for a person, their organisation). Returns the subjects linked, as (doctype, name)."""
	done = []
	for dt, name in _with_organisations(subjects):
		if link(space, from_dt, from_name, dt, name, origin):
			done.append((dt, name))
	return done


def _with_organisations(subjects) -> list:
	out = []
	for dt, name in subjects:
		if (dt, name) not in out:
			out.append((dt, name))
		org = frappe.db.get_value("Life Person", name, "organisation") if dt == "Life Person" else None
		if org and ("Life Person", org) not in out:
			out.append(("Life Person", org))
	return out


def unlink(from_dt: str, from_name: str, to_dt: str, to_name: str, user_action: bool = True) -> bool:
	"""Take a wrong link off a page. It is kept as a correction for the skill, and the Brain does not make it again."""
	rows = frappe.get_all("Life Link", filters={"from_doctype": from_dt, "from_name": from_name, "to_doctype": to_dt, "to_name": to_name, "origin": ("in", ("Brain", "Owner"))},
		fields=["name", "space"])
	if not rows:
		return False
	space = rows[0].space
	for r in rows:
		frappe.delete_doc("Life Link", r.name, ignore_permissions=True, force=True)  # system: the caller checked the owner may write on the subject's space
	if user_action:
		_correction(space, from_dt, from_name, to_dt, to_name)
	return True


def _correction(space, from_dt, from_name, to_dt, to_name):
	title = frappe.db.get_value(from_dt, from_name, {"Life Sender Sighting": "subject", "Life Task": "title", "Life Note": "title", "Life Inbox Item": "title",
		"Life Chat Log": "title", "Event": "subject"}.get(from_dt, "name")) or from_name
	if not frappe.db.exists("Life Skill", SKILL):
		return
	frappe.get_doc({"doctype": "Life Skill Correction", "skill": SKILL, "skill_version": frappe.db.get_value("Life Skill", SKILL, "version") or 1, "space": space,
		"correction_type": "Link", "key": _key(from_dt, from_name, to_dt, to_name), "detail": f"Not about {title_of(to_dt, to_name)}",
		"capture_title": str(title)[:140]}).insert(ignore_permissions=True)  # system: a correction is a record of the owner's decision for the skill


def links_to(doctype: str, name: str) -> list:
	"""The rows linking records to this subject (origin Brain or Owner), newest first."""
	return frappe.get_all("Life Link", filters={"to_doctype": doctype, "to_name": name, "origin": ("in", ("Brain", "Owner"))},
		fields=["name", "from_doctype", "from_name", "origin", "creation"], order_by="creation desc", limit=2000)


def last_linked(doctype: str, name: str):
	"""When something was last linked to a subject, or None."""
	return frappe.db.get_value("Life Link", {"to_doctype": doctype, "to_name": name, "origin": ("in", ("Brain", "Owner"))}, "creation", order_by="creation desc")


# ---------------------------------------------------------------- what a link points at

def entry(from_dt: str, from_name: str) -> dict | None:
	"""A linked record as a timeline line: {doctype, name, kind, title, date, text, sensitive, url, ref}; None when the record is gone."""
	if from_dt == "Life Sender Sighting":
		r = frappe.db.get_value(from_dt, from_name, ["subject", "seen_on", "snippet", "url", "item", "address"], as_dict=True)
		if not r:
			return None
		if r.item and frappe.db.exists("Life Inbox Item", r.item):  # an email that was filed is its item
			e = entry("Life Inbox Item", r.item)
			if e:
				e["kind"] = "Email"
				e["url"] = r.url
				return e
		return {"doctype": from_dt, "name": from_name, "kind": "Email", "title": r.subject or r.address, "date": str(r.seen_on or ""), "text": r.snippet or "", "sensitive": False,
			"url": r.url, "ref": None}
	if from_dt == "Life Inbox Item":
		r = frappe.db.get_value(from_dt, from_name, ["title", "received_on", "source_type", "summary_md", "transcript_md", "raw_text", "is_sensitive", "vault_document", "source_url"], as_dict=True)
		if not r:
			return None
		text = r.summary_md or r.transcript_md or r.raw_text or ""
		return {"doctype": from_dt, "name": from_name, "kind": "Email" if (r.source_type or "").startswith("Email") else "Capture", "title": r.title or "Capture",
			"date": str(r.received_on or "")[:10], "text": text, "sensitive": bool(r.is_sensitive or r.vault_document), "url": None, "ref": f"source:{from_name}"}
	if from_dt == "Life Task":
		r = frappe.db.get_value(from_dt, from_name, ["title", "status", "due_date", "completed_on", "notes_md", "modified"], as_dict=True)
		if not r:
			return None
		done = r.status == "Done"
		return {"doctype": from_dt, "name": from_name, "kind": "Task", "title": r.title, "date": str(r.completed_on or r.modified)[:10], "done": done,
			"text": f"{r.status}" + (f", due {r.due_date}" if r.due_date and not done else "") + (f". {r.notes_md}" if r.notes_md else ""), "sensitive": False, "url": None, "ref": f"task:{from_name}"}
	if from_dt == "Life Note":
		r = frappe.db.get_value(from_dt, from_name, ["title", "summary", "content_md", "modified", "is_sensitive"], as_dict=True)
		if not r:
			return None
		return {"doctype": from_dt, "name": from_name, "kind": "Note", "title": r.title, "date": str(r.modified)[:10], "text": r.summary or r.content_md or "", "sensitive": bool(r.is_sensitive),
			"url": None, "ref": f"note:{from_name}"}
	if from_dt == "Event":
		r = frappe.db.get_value(from_dt, from_name, ["subject", "starts_on", "description"], as_dict=True)
		if not r:
			return None
		return {"doctype": from_dt, "name": from_name, "kind": "Meeting", "title": r.subject, "date": str(r.starts_on)[:10], "text": r.description or "", "sensitive": False, "url": None,
			"ref": f"event:{from_name}", "starts_on": str(r.starts_on)}
	if from_dt == "Life Chat Log":
		r = frappe.db.get_value(from_dt, from_name, ["title", "modified"], as_dict=True)
		if not r:
			return None
		return {"doctype": from_dt, "name": from_name, "kind": "Chat", "title": r.title, "date": str(r.modified)[:10], "text": "", "sensitive": False, "url": None, "ref": f"chat:{from_name}"}
	return None


def timeline(doctype: str, name: str, limit: int = TIMELINE_CAP) -> tuple[list, int]:
	"""Everything linked to a subject, newest first: [entry + id of the link]; and how many there are. A record that is sensitive is listed
	without its text; one the person may not read is left out."""
	out, seen = [], set()
	for row in links_to(doctype, name):
		e = entry(row.from_doctype, row.from_name)
		if not e or (e["doctype"], e["name"]) in seen:
			continue
		seen.add((e["doctype"], e["name"]))
		if e["doctype"] not in ("Life Sender Sighting",) and not frappe.has_permission(e["doctype"], "read", e["name"]):
			continue
		if e["sensitive"]:
			e["text"] = ""
		e.update(link=row.name, linked_on=str(row.creation), origin=row.origin)
		out.append(e)
	out.sort(key=lambda e: (e["date"], e["linked_on"]), reverse=True)
	return out[:limit], len(out)


# ---------------------------------------------------------------- finding the subjects an email is about

def _pattern(names):
	return re.compile(r"(^|[^A-Za-z0-9_])(" + "|".join(re.escape(n) for n in names) + r")($|[^A-Za-z0-9_])", re.I)


def known_subjects(space: str) -> list:
	"""Every person and organisation of a space with the names they go by."""
	return frappe.get_all("Life Person", filters={"space": space, "is_archived": 0}, fields=["name", "full_name", "kind", "email", "aliases", "organisation", "wiki_page"],
		order_by="creation asc", limit=5000)


def names_of(p) -> list:
	return [n for n in [p.get("full_name"), *split_aliases(p.get("aliases"))] if n]


def match_known(space: str, address: str = "", sender_name: str = "", text: str = "") -> list:
	"""The people and organisations an email is about, as (doctype, name): the sender's address, the sender's name, and the names (and aliases)
	of anyone known that the subject and the text mention. A known person brings their organisation."""
	address = (address or "").strip().lower()
	people = known_subjects(space)
	found = []

	def add(p):
		if ("Life Person", p.name) not in found:
			found.append(("Life Person", p.name))

	for p in people:
		if address and (p.email or "").strip().lower() == address:
			add(p)
	hay = f"{sender_name}\n{text}"
	for p in people:
		names = [n for i, n in enumerate(names_of(p)) if i == 0 or len(n) >= 3]
		if names and len(names[0]) >= 3 and _pattern(names).search(hay):
			add(p)
	return _with_organisations(found)


def find_by_name(space: str, name: str):
	"""The person or organisation a name (or an alias of it) belongs to, as a row, or None."""
	t = " ".join((name or "").split()).lower()
	if not t:
		return None
	for p in known_subjects(space):
		if t in [n.lower() for n in names_of(p)]:
			return p
	return None


# ---------------------------------------------------------------- making and merging subjects

def make_person(space: str, name: str, kind: str = "Person", email: str | None = None, organisation: str | None = None, role: str | None = None) -> tuple[str, bool]:
	"""A person or organisation by name: the one that is there, or a new one. Returns (name, made)."""
	found = find_by_name(space, name)
	if found:
		if email and not found.email and found.kind == "Person":
			frappe.db.set_value("Life Person", found.name, "email", email)
		if organisation and found.kind == "Person" and not found.organisation:
			frappe.db.set_value("Life Person", found.name, "organisation", organisation)
		return found.name, False
	doc = frappe.get_doc({"doctype": "Life Person", "space": space, "full_name": " ".join(name.split())[:140], "kind": kind, "email": email or None,
		"organisation": organisation if kind == "Person" else None, "role": role or None})
	doc.insert(ignore_permissions=True)  # system: the Brain makes the page of someone who wrote to the owner
	return doc.name, True


def make_for_email(space: str, sender: str, address: str, organisation: str | None, role: str | None = None) -> list:
	"""A person and (when named) their organisation. Returns [(doctype, name, made)], the organisation first."""
	made = []
	org = None
	if organisation and organisation.strip():
		org, was = make_person(space, organisation, "Organisation")
		made.append(("Life Person", org, was))
	person, was = make_person(space, sender, "Person", address, org, role)
	made.append(("Life Person", person, was))
	return made


def log_made(space: str, made: list, title: str, reason: str = "") -> str | None:
	"""Record in Activity (a `Life Agent Action` of the Brain) that pages were made on its own, with what Undo takes back."""
	new = [(dt, n) for dt, n, was in made if was]
	if not new:
		return None
	order = sorted(new, key=lambda x: 0 if frappe.db.get_value("Life Person", x[1], "kind") == "Person" else 1)  # people go before the organisation they belong to
	row = frappe.get_doc({"doctype": "Life Agent Action", "space": space, "agent": BRAIN, "action": "subjects.make", "title": title[:200], "status": "Done", "asked_by": "agent",
		"draft": reason[:5000] or None, "undo": json.dumps({"delete": [list(x) for x in order]}), "result": json.dumps({"line": title})[:900], "happened_on": now_datetime(), "delivered": 1})
	row.insert(ignore_permissions=True)  # system: the Brain's own log of what it did, with its undo
	return row.name


def add_alias(doctype: str, name: str, alias: str):
	if doctype != "Life Person" or not alias:
		return
	doc = frappe.get_doc("Life Person", name)
	names = [n.lower() for n in names_of(doc)]
	if alias.lower() not in names:
		doc.aliases = "\n".join([*split_aliases(doc.aliases), alias])
		doc.save(ignore_permissions=True)  # system: the owner said these are the same


def merge(space: str, keep: str, drop: str) -> str:
	"""Join two subjects (people or organisations): links, aliases, notes and people move to `keep`; `drop` goes. Returns `keep`."""
	if keep == drop:
		return keep
	a, b = frappe.get_doc("Life Person", keep), frappe.get_doc("Life Person", drop)
	if a.space != b.space or a.kind != b.kind:
		frappe.throw(_("Only two people, or two organisations, of one space can be joined."), title=_("Cannot merge"))
	for row in frappe.get_all("Life Link", filters={"to_doctype": "Life Person", "to_name": drop}, fields=["name", "from_doctype", "from_name", "origin"]):
		if frappe.db.exists("Life Link", {"from_doctype": row.from_doctype, "from_name": row.from_name, "to_doctype": "Life Person", "to_name": keep, "origin": row.origin}):
			frappe.delete_doc("Life Link", row.name, ignore_permissions=True, force=True)  # system: a duplicate of a link the kept subject has
		else:
			frappe.db.set_value("Life Link", row.name, {"to_name": keep, "link_text": a.full_name[:140]}, update_modified=False)
	frappe.db.delete("Life Link", {"from_doctype": "Life Person", "from_name": drop})
	a.aliases = "\n".join(dict.fromkeys([*split_aliases(a.aliases), *[n for n in names_of(b)]]).keys() - {a.full_name}) or None
	for f in ("email", "role", "relation", "area", "wiki_page", "status", "notes_md"):
		if not a.get(f) and b.get(f):
			a.set(f, b.get(f))
	b_org = b.organisation
	if not a.organisation and b_org and a.kind == "Person":
		a.organisation = b_org
	a.save(ignore_permissions=True)  # system: the owner chose to join them
	for dt, field in (("Life Person", "organisation"), ("Life Task", "waiting_on_person"), ("Life Task", "delegated_to"), ("Life Note", "person")):
		for n in frappe.get_all(dt, filters={field: drop}, pluck="name"):
			frappe.db.set_value(dt, n, field, keep, update_modified=False)
	for pin in frappe.get_all("Life Pin", filters={"ref_doctype": "Life Person", "ref_name": drop}, fields=["name", "user"]):
		if frappe.db.exists("Life Pin", {"user": pin.user, "ref_doctype": "Life Person", "ref_name": keep}):
			frappe.delete_doc("Life Pin", pin.name, ignore_permissions=True, force=True)  # system: the person already pins the kept page
		else:
			frappe.db.set_value("Life Pin", pin.name, "ref_name", keep)
	for dt in ("Life Page Visit",):
		frappe.db.set_value(dt, {"ref_doctype": "Life Person", "ref_name": drop}, "ref_name", keep)
	frappe.delete_doc("Life Person", drop, ignore_permissions=True, force=True)  # system: nothing points at it now
	return keep


# ---------------------------------------------------------------- an email is seen (filed, or listed by the digest)

def _sighting(space: str, mail: dict, item: str | None):
	"""The record of one email thread in a space (one per thread): what the subjects' timelines list when the email was seen but not filed."""
	name = frappe.db.get_value("Life Sender Sighting", {"space": space, "thread_id": mail["thread_id"]})
	if name:
		doc = frappe.get_doc("Life Sender Sighting", name)
		changed = False
		if item and doc.item != item:
			doc.item, changed = item, True
		if mail.get("replied") and not doc.replied:
			doc.replied, changed = 1, True
		if changed:
			doc.save(ignore_permissions=True)  # system: the Brain's own record of an email it saw
		return doc
	doc = frappe.get_doc({"doctype": "Life Sender Sighting", "space": space, "address": (mail.get("address") or "").lower(), "sender_name": mail.get("sender_name"), "thread_id": mail["thread_id"],
		"subject": (mail.get("subject") or "")[:140], "seen_on": mail.get("seen_on") or nowdate(), "replied": 1 if mail.get("replied") else 0, "item": item,
		"snippet": (mail.get("text") or "")[:600], "url": mail.get("url")})
	return doc.insert(ignore_permissions=True)  # system: the Brain's own record of an email it saw


def _count(space: str, address: str) -> int:
	n, days = settings()
	return len(frappe.get_all("Life Sender Sighting", filters={"space": space, "address": address, "seen_on": (">=", add_days(nowdate(), -days))}, pluck="thread_id"))


def _skill_answer(space, mail, known):
	from lifeos.skills import call

	return call.ask(SKILL, {"from": f"{mail.get('sender_name') or ''} <{mail['address']}>".strip(), "subject": mail.get("subject") or "", "text": (mail.get("text") or "")[:800],
		"signature": (mail.get("signature") or "")[-500:], "owner_replied": bool(mail.get("replied")), "existing_subjects": [p.full_name for p in known][:80]}, space)


def see_email(space: str, mail: dict, item: str | None = None) -> dict:
	"""An email thread was filed, or the digest listed it. `mail`: thread_id, address, sender_name, subject, text, signature, replied (the owner wrote in
	the thread), bulk (a promotion, a list, a notification), url. Links it to the subjects it is about and, by the issue's table, makes a page for a
	new sender, proposes one, or asks which existing subject it is. Returns {linked: [(doctype, name)], made: [...], proposed: <proposal>|None, asked: <proposal>|None}."""
	out = {"linked": [], "made": [], "proposed": None, "asked": None}
	if not mail.get("thread_id") or not mail.get("address"):
		return out
	address = mail["address"].strip().lower()
	mail = {**mail, "address": address}
	known = match_known(space, address, mail.get("sender_name") or "", f"{mail.get('subject') or ''}\n{mail.get('text') or ''}\n{mail.get('signature') or ''}")
	bulk = bool(mail.get("bulk")) and not mail.get("replied")
	if bulk and not known:  # promotions, newsletters, notifications, receipts: no page, no record of the sender
		return out
	sighting = _sighting(space, mail, item)
	targets = [("Life Sender Sighting", sighting.name)] + ([("Life Inbox Item", item)] if item else [])
	senders = [s for s in known if s[0] == "Life Person" and frappe.db.get_value("Life Person", s[1], "email") == address]
	if known and senders:  # the sender is someone already there: nothing to decide
		for t in targets:
			out["linked"] += link_all(space, *t, known)
		_refresh(known)
		return out
	if bulk:  # a promotion that names a known subject is linked, never made into one
		for t in targets:
			out["linked"] += link_all(space, *t, known)
		return out
	from lifeos.brain import rules

	if rules.never_page(space, address):  # a rule says this sender never gets a page: the owner's own company, by the built-in rule (issue 117)
		for t in targets:
			out["linked"] += link_all(space, *t, known)
		return out
	# the sender is new (a known subject may be mentioned in the text); the table decides
	count = _count(space, address)
	need, _days = settings()
	asked_before = frappe.db.exists("Life Sender Sighting", {"space": space, "address": address, "proposal": ("is", "set")})  # a sender is proposed once
	if not (mail.get("replied") or count >= need) or sighting.proposal or asked_before:
		for t in targets:
			out["linked"] += link_all(space, *t, known)
		return out
	people = known_subjects(space)
	answer = _skill_answer(space, mail, people)
	name = (answer.get("person") if answer else None) or mail.get("sender_name") or address.split("@")[0]
	org = (answer.get("organisation") if answer else None) or None
	context = answer.get("context") if answer else None
	same = find_by_name(space, answer.get("same_as")) if answer and answer.get("same_as") else None
	unsure = find_by_name(space, answer.get("unsure_of")) if answer and answer.get("unsure_of") else None
	if org and not same and not find_by_name(space, org) and unsure:  # might be a company the owner already has: ask once
		out["asked"] = _ask_same(space, sighting, item, org, unsure, mail)
		for t in targets:
			out["linked"] += link_all(space, *t, known)
		return out
	if same:
		org = same.full_name
	role = answer.get("role") if answer else None
	if mail.get("replied") and context in ("business", "family"):  # a real two-way exchange with someone new: a page straight away
		made = make_for_email(space, name, address, org, role)
		fresh = {n for _dt, n, was in made if was}
		for t in targets:
			for dt, n, _was in made:
				if link(space, t[0], t[1], dt, n, "Brain", made=n in fresh):
					out["linked"].append((dt, n))
		out["made"] = [("Life Person", n) for n in fresh]
		if fresh:
			log_made(space, made, _("Made a page for {0}").format(name) + (f" ({org})" if org else ""), mail.get("subject") or "")
	elif not mail.get("replied") or context is None:  # seen often, importance unclear (or no answer from the model): the owner decides
		out["proposed"] = _propose_new(space, sighting, item, name, address, org, role, count, mail)
	for t in targets:
		out["linked"] += link_all(space, *t, known)
	return out


def mail_of_hit(hit: dict) -> dict:
	"""A digest hit (`GmailAdapter.recent`) as the facts `see_email` takes."""
	name = re.sub(r"\s*\(.*\)\s*$", "", hit.get("from") or "").strip()
	return {"thread_id": hit["thread_id"], "address": hit.get("sender") or "", "sender_name": name, "subject": hit.get("subject"), "text": hit.get("text") or hit.get("snippet"),
		"signature": hit.get("signature"), "replied": hit.get("replied"), "bulk": not hit.get("person") or hit.get("list_mail"), "url": hit.get("link")}


def mail_of_thread(thread: dict, thread_id: str, mailbox: str) -> dict:
	"""A thread read with `get_thread` as the facts `see_email` takes: the first person who is not the mailbox's owner is the sender."""
	mailbox = (mailbox or "").lower()
	theirs = [m for m in thread.get("messages") or [] if mailbox not in (m.get("from") or "").lower()]
	mine = [m for m in thread.get("messages") or [] if mailbox in (m.get("from") or "").lower()]
	first = theirs[0] if theirs else {}
	m = re.match(r"^(.*?)\s*\(([^()]*@[^()]*)\)\s*$", first.get("from") or "")
	name, address = (m.group(1), m.group(2)) if m else ("", first.get("from") or "")
	body = first.get("text") or ""
	return {"thread_id": thread_id, "address": address, "sender_name": name.strip(), "subject": thread.get("subject"), "text": body[:1500], "signature": body[-500:], "replied": bool(mine),
		"bulk": False, "url": thread.get("link")}


def _refresh(subjects):
	"""Nothing to do: a brief is marked to refresh because a newer link exists than `brief_on`."""
	return None


def _holder(space, sighting, item, mail):
	"""The Brain item a question waits under in Needs you: the filed email, or a short item standing for the thread."""
	if item:
		return item
	from lifeos.api import inbox

	made = inbox.create_item(space=space, source_type="Email", source_system="gmail", external_id=f"subject:{mail['thread_id']}", title=(mail.get("subject") or "Email")[:140],
		raw_text=(mail.get("text") or "")[:4000], source_url=mail.get("url"), intent="Just keep")
	frappe.db.set_value("Life Sender Sighting", sighting.name, "item", made["name"], update_modified=False)
	return made["name"]


def _make_proposal(space, item, kind, payload, preview, reason):
	return frappe.get_doc({"doctype": "Life Proposal", "space": space, "inbox_item": item, "kind": kind, "payload": frappe.as_json(payload), "preview": preview[:140],
		"confidence": 0.6, "reason": reason[:200], "status": "Pending"}).insert(ignore_permissions=True).name  # system: the Brain proposes; only the owner's Accept makes the page


def _propose_new(space, sighting, item, name, address, org, role, count, mail) -> str:
	holder = _holder(space, sighting, item, mail)
	title = org or name
	kind = "Organisation" if org else "Person"
	proposal = _make_proposal(space, holder, "New Subject", {"name": title if org else name, "kind": kind, "person": name, "email": address, "role": role or "", "address": address},
		_("New {0}: {1}. Make a page?").format(_("company") if org else _("person"), title), _("{0} emails from {1} in {2} days").format(count, address, settings()[1]))
	frappe.db.set_value("Life Sender Sighting", sighting.name, "proposal", proposal, update_modified=False)
	return proposal


def _ask_same(space, sighting, item, name, unsure, mail) -> str:
	holder = _holder(space, sighting, item, mail)
	proposal = _make_proposal(space, holder, "Same Subject", {"name": name, "same_as": unsure.name, "address": mail["address"], "kind": unsure.kind},
		_("Is {0} the same as {1}?").format(name, unsure.full_name), _("Asked once; the answer becomes an alias"))
	frappe.db.set_value("Life Sender Sighting", sighting.name, "proposal", proposal, update_modified=False)
	return proposal


# ---------------------------------------------------------------- what Accept does for the two proposals

def accept_new(space: str, payload: dict, item) -> tuple[str, str]:
	"""Accept 'New company/person: make a page': the subject is made, and everything seen from that address (and the item) is linked to it."""
	name, kind, address = payload["name"], payload.get("kind") or "Person", (payload.get("address") or payload.get("email") or "").lower()
	org = None
	if kind == "Organisation":
		org, _was = make_person(space, name, "Organisation")
		person, _was = make_person(space, payload.get("person") or name, "Person", address, org, payload.get("role"))
		main = ("Life Person", org)
	else:
		person, _was = make_person(space, name, "Person", address, None, payload.get("role"))
		main = ("Life Person", person)
	subjects = [("Life Person", person), *([("Life Person", org)] if org else [])]
	holders = [("Life Inbox Item", item.name)]
	for s in frappe.get_all("Life Sender Sighting", filters={"space": space, "address": address}, fields=["name", "item"]):
		holders.append(("Life Sender Sighting", s.name))
		if s.item:
			holders.append(("Life Inbox Item", s.item))
	for dt, n in dict.fromkeys(holders):
		for sdt, sn in subjects:
			link(space, dt, n, sdt, sn, "Brain")
	return main


def accept_same(space: str, payload: dict, item) -> tuple[str, str]:
	"""Accept 'Is X the same as Y?': X becomes another name of Y (a subject already made for X is joined into Y), and mail by that name is linked to Y from now on."""
	keep = payload["same_as"]
	other = find_by_name(space, payload["name"])
	if other and other.name != keep:
		merge(space, keep, other.name)
	add_alias("Life Person", keep, payload["name"])
	address = (payload.get("address") or "").lower()
	for dt, n in [("Life Inbox Item", item.name), *[("Life Sender Sighting", s) for s in frappe.get_all("Life Sender Sighting", filters={"space": space, "address": address}, pluck="name")]]:
		link(space, dt, n, "Life Person", keep, "Brain")
	return "Life Person", keep


def on_trash(doc, method=None):
	"""A subject that is deleted takes the links to it and the pins of it with it."""
	frappe.db.delete("Life Link", {"to_doctype": doc.doctype, "to_name": doc.name, "origin": ("in", ("Brain", "Owner"))})
	frappe.db.delete("Life Pin", {"ref_doctype": doc.doctype, "ref_name": doc.name})
	frappe.db.delete("Life Page Visit", {"ref_doctype": doc.doctype, "ref_name": doc.name})
