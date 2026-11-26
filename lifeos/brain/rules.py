"""Rules (issue 117): what the owner has already decided, applied before any model is asked.

A `Life Rule` says "when a capture is like this, do that". The first enabled rule that matches, most specific first (a sender before a
domain before a source), decides: the capture is filed with the reason "Rule: ...", no model is called and nothing is spent. Rules come from
the owner (by hand, in Ask), from the Brain (the same correction twice) and from Life OS (the built-in two). A rule is plumbing, a field
test and an outcome; judgment stays in the filing skill.
"""
import re

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from lifeos import permissions

ACTIONS = ("File", "Link", "Drop", "Ask")  # a Route rule (asks to the plate or the pile) is made only by lifeos/brain/asks.py
FILE_AS = ("Chat", "Note", "Report", "Task")
SAME_CORRECTION = 2  # the same correction this many times (the one just made included) makes a rule
EXAMPLES = 8  # recent decisions shown to the Brain with each capture
PUBLIC = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "outlook.com", "hotmail.com", "live.com", "icloud.com", "rediffmail.com", "proton.me", "protonmail.com"}
CONTEXT_KINDS = "Chat, Email Digest, Journal Photo"
BUILTIN = {
	"own-domains": {"action": "Link", "never_page": 1},
	"context-items": {"item_kind": CONTEXT_KINDS, "action": "File", "file_as": "Chat", "no_area": 1},
}


# ---- the words ----
def area_name(area) -> str:
	return frappe.db.get_value("Life Area", area, "area_name") or area if area else ""


def _list(text) -> list:
	return [w.strip() for w in re.split(r"[,\n;]", text or "") if w.strip()]


def when_words(rule) -> str:
	parts = []
	if rule.sender:
		parts.append(_("mail is from {0}").format(rule.sender))
	if rule.builtin == "own-domains":
		parts.append(_("mail is from your own company's address ({0})").format(", ".join([*_list(rule.domain), *own_domains()])))
	elif rule.domain:
		parts.append(_("mail is from anyone at {0}").format(rule.domain))
	if rule.source:
		parts.append(_("it comes from {0}").format(source_title(rule.space, rule.source)))
	if rule.item_kind:
		parts.append(_("it is a {0}").format(" or ".join(_list(rule.item_kind)).lower()))
	if rule.title_words:
		parts.append(_("the title has {0}").format(" or ".join(f"“{w}”" for w in _list(rule.title_words))))
	if rule.attachment_type:
		parts.append(_("it has a {0} attached").format(rule.attachment_type.lstrip(".").lower()))
	return _("When {0}").format(f" {_('and')} ".join(parts)) if parts else _("For anything")


def then_words(rule) -> str:
	if rule.action == "Route":
		out = _("its asks go to your plate") if rule.asks_to == "Plate" else _("its asks go to the waiting pile")
	elif rule.action == "Drop":
		out = _("not needed")
	elif rule.action == "Ask":
		out = _("always ask me")
	elif rule.action == "Link":
		out = _("link it to {0}").format(frappe.db.get_value(rule.page_doctype, rule.page, {"Life Person": "full_name", "Life Area": "area_name", "Life Note": "title"}[rule.page_doctype])
			if rule.page_doctype and rule.page and frappe.db.exists(rule.page_doctype, rule.page) else _("a page"))
	else:
		where = _("under {0}").format(area_name(rule.area)) if rule.area else _("with no area")
		out = _("file {0}").format(where) + (" " + _("as a {0}").format(rule.file_as.lower()) if rule.file_as else "")
	return out + (", " + _("never a page") if rule.never_page else "")


def words(rule) -> str:
	"""The rule in plain words: "When mail is from sales2@rungamattee.com: file under Tea & Coffee as a report, never a page"."""
	return f"{when_words(rule)}: {then_words(rule)}"


def source_title(space, key) -> str:
	from lifeos.brain import source_page

	try:
		return source_page.title_of(space, key)
	except Exception:  # noqa: BLE001 - a source that is gone is still named
		return key


# ---- the rules of a space ----
def ensure_builtins(space: str):
	"""The two rules Life OS ships, in a space (made once; the owner may change or switch them off)."""
	for key, values in BUILTIN.items():
		if frappe.db.exists("Life Rule", {"space": space, "builtin": key}):
			continue
		values = {k: v for k, v in values.items() if k != "domain"}
		frappe.get_doc({"doctype": "Life Rule", "space": space, "made_by": "Built-in", "builtin": key, "enabled": 1, **values}).insert(ignore_permissions=True)  # system: Life OS's own rules


def own_domains() -> list:
	from lifeos.review import meetings

	return meetings.own_domains()


def specificity(rule) -> int:
	return (100 * bool(rule.sender) + 60 * bool(rule.domain) + 30 * bool(rule.title_words) + 25 * bool(rule.attachment_type) + 15 * bool(rule.item_kind)
		+ 10 * bool(rule.source))


def rules_of(space: str, only_on: bool = True) -> list:
	"""The rules of a space in the order they are tried: most specific first, then the oldest."""
	rows = frappe.get_all("Life Rule", filters={"space": space, **({"enabled": 1} if only_on else {})}, fields=["*"], order_by="creation asc")  # system: the Brain reads the space's rules
	rows = [frappe._dict(r) for r in rows]
	return sorted(rows, key=lambda r: -specificity(r))


# ---- what a capture is, for a rule ----
def source_key(item) -> str:
	return (item.get("source_system") or "upload").strip().lower()


def domain_of(address) -> str:
	return (address or "").rsplit("@", 1)[-1].strip().lower() if "@" in (address or "") else ""


def kinds_of(item) -> set:
	return {x.lower() for x in (item.get("source_type"), item.get("media_kind")) if x}


def facts(item) -> dict:
	from lifeos.library import files

	sender = (item.get("sender") or "").strip().lower()
	types = {(f.file_name or "").rsplit(".", 1)[-1].lower() for f in files.attachments("Life Inbox Item", item.name)} if item.get("name") and not item.get("is_new") else set()
	return {"sender": sender, "domain": domain_of(sender), "source": source_key(item), "kinds": kinds_of(item), "title": (item.get("title") or "").lower(), "types": types}


def matches(rule, f: dict) -> bool:
	if rule.sender and rule.sender.strip().lower() != f["sender"]:
		return False
	if rule.domain or rule.builtin == "own-domains":
		domains = {d.lower().lstrip("@") for d in [*_list(rule.domain), *(own_domains() if rule.builtin == "own-domains" else [])]}
		if not f["domain"] or f["domain"] not in domains:
			return False
	if rule.source and rule.source.strip().lower() != f["source"]:
		return False
	if rule.item_kind and not ({k.lower() for k in _list(rule.item_kind)} & f["kinds"]):
		return False
	if rule.title_words and not any(w.lower() in f["title"] for w in _list(rule.title_words)):
		return False
	if rule.attachment_type and rule.attachment_type.lstrip(".").lower() not in f["types"]:
		return False
	return True


def first_match(item):
	"""The rule that decides this capture, or None."""
	f = facts(item)
	for rule in rules_of(item.space):
		if rule.action != "Route" and matches(rule, f):  # a Route rule is about the asks in a capture, not about filing it (lifeos/brain/asks.py)
			return rule
	return None


def used(rule):
	frappe.db.set_value("Life Rule", rule.name, {"used_count": cint(rule.used_count) + 1, "last_used": now_datetime()}, update_modified=False)


def never_page(space: str, address: str) -> bool:
	"""A rule that matches mail from this address says it never gets a page (the owner's own domains, by the built-in rule)."""
	f = {"sender": (address or "").strip().lower(), "domain": domain_of(address), "source": "gmail", "kinds": {"email"}, "title": "", "types": set()}
	for rule in rules_of(space):
		if rule.never_page and not (rule.source or rule.item_kind or rule.title_words or rule.attachment_type) and matches(rule, f):
			return True
	return False


def must_ask(item) -> bool:
	rule = first_match(item)
	return bool(rule and rule.action == "Ask")


# ---- applying a rule before any model ----
def apply_first(item) -> dict | None:
	"""Decide the capture by its first matching rule, when that rule decides it (File or Drop). Returns {rule, label} when the capture is
	filed, None when the Brain must read it (no rule, a Link rule, which only links, or an Ask rule). The caller holds the claim."""
	rule = first_match(item)
	if not rule or rule.action not in ("File", "Drop", "Link"):
		return None
	label = _("Rule: {0}").format(words(rule))
	used(rule)
	if rule.builtin == "context-items" and item.get("source_type") == "Email Digest":
		return None  # issue 118: a digest needs no area, but it is still read: its summary (To act on, Updates, Reports) is the point
	if rule.action == "Link":
		if rule.page_doctype and rule.page:
			from lifeos.library import subjects

			subjects.link(item.space, "Life Inbox Item", item.name, rule.page_doctype, rule.page, "Brain")
		return None
	if rule.action == "Drop":
		_finish(item, label, _("Not needed: {0}").format(words(rule)))
	elif rule.file_as in ("Note", "Report", "Task"):
		_file_proposal(item, rule, label)
	else:
		_file_here(item, rule, label)
	return {"rule": rule.name, "label": label}


def _finish(item, label, summary, **values):
	frappe.db.set_value("Life Inbox Item", item.name, {"status": "Done", "finished_on": frappe.utils.today(), "processed_by": label[:140], "summary_md": summary,
		"claimed_by": None, "claimed_on": None, "error": None, **values})
	item.reload()


def _file_here(item, rule, label):
	"""The capture is filed where the rule says: under its area (or none), as a chat when the rule says so, and linked to the pages it names."""
	area = None if rule.no_area else rule.area
	if rule.file_as == "Chat":
		made = frappe.get_doc({"doctype": "Life Chat Log", "space": item.space, "title": (item.title or _("Chat"))[:140], "date": frappe.utils.getdate(item.received_on) if item.received_on else frappe.utils.today(),
			"assistant": "Claude" if item.get("source_system") == "claude" or "claude" in (item.title or "").lower() else "Other", "transcript_md": item.raw_text, "inbox_item": item.name,
			"source_system": None, "area": area}).insert(ignore_permissions=True)  # system: the Brain files for the owner, by the owner's rule
		holders = [("Life Chat Log", made.name)]
	else:
		holders = []
	_finish(item, label, _("Filed by your rule: {0}").format(words(rule)), area=area)
	_link_pages(item, [("Life Inbox Item", item.name), *holders])


def _link_pages(item, holders):
	from lifeos.library import subjects

	known = subjects.match_known(item.space, item.get("sender") or "", "", f"{item.title or ''}\n{item.raw_text or ''}")
	for holder in holders:
		subjects.link_all(item.space, *holder, known)


def _file_proposal(item, rule, label):
	"""A Note (or a report), or a Task, made through the same proposal a person's Keep accepts."""
	from lifeos.api import inbox, review

	if not rule.area or rule.no_area:
		frappe.throw(_("A rule that files a {0} needs an area.").format(rule.file_as.lower()), title=_("Rule needs an area"))
	if rule.file_as == "Task":
		kind, payload = "Task", {"title": item.title, "area": rule.area}
	else:
		kind, payload = "Note", {"title": item.title, "content_md": item.raw_text or item.title, "area": rule.area}
	prop = frappe.get_doc({"doctype": "Life Proposal", "space": item.space, "inbox_item": item.name, "kind": kind, "preview": (item.title or kind)[:500],
		"payload": frappe.as_json(payload), "confidence": 1, "status": "Pending", "reason": label[:500]}).insert(ignore_permissions=True)  # system: the Brain files by the owner's rule
	frappe.db.set_value("Life Inbox Item", item.name, "status", "To Review")
	item.reload()
	frappe.flags.lifeos_app_write = True  # the app files by the owner's rule, though the Brain is an agent
	try:
		review._decide(prop, "accept")
	finally:
		frappe.flags.lifeos_app_write = False
	frappe.db.set_value("Life Proposal", prop.name, "filed_by", label[:140])
	inbox._finish_if_decided(frappe.get_doc("Life Inbox Item", item.name))
	frappe.db.set_value("Life Inbox Item", item.name, {"processed_by": label[:140], "claimed_by": None, "claimed_on": None, "area": rule.area})
	item.reload()
	_link_pages(item, [("Life Inbox Item", item.name)])


# ---- learning from what the owner decides ----
def classify(prop):
	"""What a person's decision on a proposal says against the Brain's guess: ("area", chosen), ("drop", ""), ("kind", accepted kind), or None."""
	guess = frappe.parse_json(prop.guess) if isinstance(prop.guess, str) else (prop.guess or {})
	if prop.status == "Rejected":
		accepted = frappe.get_all("Life Proposal", filters={"inbox_item": prop.inbox_item, "status": "Accepted", "kind": ("!=", prop.kind)}, pluck="kind")  # system: the owner's own decisions on this capture
		return ("kind", accepted[0]) if accepted else ("drop", "")
	chosen = frappe.parse_json(prop.payload) if isinstance(prop.payload, str) else (prop.payload or {})
	if prop.status == "Accepted" and guess.get("area") and chosen.get("area") and guess["area"] != chosen["area"]:
		return ("area", chosen["area"])
	return None


def learn(prop, item):
	"""A person decided a proposal. When this is the same correction the second time for one sender (or domain, or source and kind), make the
	rule, without asking. Returns the rule or None. Nothing of a sensitive capture is ever learnt from."""
	if frappe.session.user == permissions.BRAIN_USER or item.get("is_sensitive") or item.get("vault_document") or prop.get("filed_by"):
		return None
	sign = classify(prop)
	if not sign:
		return None
	for conds in _candidates(item, prop):
		if _same_rule_exists(item.space, conds):  # a rule for this exact case stands (switched off or not); a wider one is not made over it
			return None
		if _count_same(item.space, conds, sign) >= SAME_CORRECTION:
			return _make(item.space, {**conds, "source": conds.get("source") or source_key(item)}, sign, prop)
	return None


def _candidates(item, prop):
	"""The ways "the same" can be read for a capture, narrowest first: its sender, its sender's domain, its source and the proposal's kind."""
	out = []
	sender = (item.get("sender") or "").strip().lower()
	if sender:
		out.append({"sender": sender})
		if domain_of(sender) not in PUBLIC:
			out.append({"domain": domain_of(sender)})
	out.append({"source": source_key(item), "item_kind": prop.kind})
	return out


def _same_rule_exists(space, conds) -> bool:
	"""A rule (on or off) already has these conditions: the owner's choice about it stands, so it is not made again."""
	keys = [k for k in ("sender", "domain", "source", "item_kind") if k in conds]
	return any(all((r.get(k) or "").strip().lower() == conds[k].lower() for k in keys) and not r.title_words and not r.attachment_type
		and (set(keys) & {"sender", "domain"} or not (r.sender or r.domain)) for r in rules_of(space, only_on=False))


def _count_same(space, conds, sign) -> int:
	"""How many decisions by a person in this space made the same correction on captures like these."""
	i, p = frappe.qb.DocType("Life Inbox Item"), frappe.qb.DocType("Life Proposal")
	q = frappe.qb.from_(p).join(i).on(i.name == p.inbox_item).select(p.name).where((p.space == space) & p.status.isin(["Accepted", "Rejected"]) & (p.decided_by != permissions.BRAIN_USER)
		& (frappe.query_builder.functions.IfNull(p.filed_by, "") == "") & (i.is_sensitive == 0) & (frappe.query_builder.functions.IfNull(i.vault_document, "") == ""))
	if "sender" in conds:
		q = q.where(i.sender == conds["sender"])
	elif "domain" in conds:
		q = q.where(i.sender.like(f"%@{conds['domain']}"))
	else:
		q = q.where((frappe.query_builder.functions.IfNull(i.source_system, "upload") == conds["source"]) & (p.kind == conds["item_kind"]))
	n = 0
	for name in q.orderby(p.decided_on, order=frappe.qb.desc).limit(30).run(pluck=True):  # system: the owner's own decisions, counted for a rule
		if classify(frappe.get_doc("Life Proposal", name)) == sign:
			n += 1
	return n


def _make(space, conds, sign, prop):
	values = {"sender": conds.get("sender"), "domain": conds.get("domain"), "source": conds.get("source"), "item_kind": conds.get("item_kind")}
	kind, target = sign
	if kind == "drop":
		then = {"action": "Drop"}
	elif kind == "area":
		then = {"action": "File", "area": target, "file_as": prop.kind if prop.kind in ("Note", "Task") else None}
	else:
		then = {"action": "File", "file_as": target if target in ("Note", "Task") else None}
		if not then["file_as"]:
			return None
		area = (frappe.parse_json(prop.payload) if isinstance(prop.payload, str) else prop.payload or {}).get("area")
		if not area:
			return None
		then["area"] = area
	if then["action"] == "File" and not then.get("area"):
		return None
	return frappe.get_doc({"doctype": "Life Rule", "space": space, "made_by": "Brain", "enabled": 1, "learned_from": prop.name, **values, **then}).insert(ignore_permissions=True)  # system: the Brain makes the rule from the owner's own corrections


def recent(space: str, days: int = 14) -> list:
	"""Rules the Brain or Ask made lately, for the quiet "New rule … Change" line."""
	since = frappe.utils.add_to_date(now_datetime(), days=-days)
	rows = frappe.get_all("Life Rule", filters={"space": space, "made_by": ("in", ("Brain", "Owner")), "creation": (">=", since), "learned_from": ("is", "set")},  # system: the owner's space rules
		fields=["name", "creation"], order_by="creation desc", limit=10)
	return [{"name": r.name, "words": words(frappe.get_doc("Life Rule", r.name)), "made": str(r.creation)[:16]} for r in rows]


# ---- recent decisions, as examples for the Brain ----
def examples_for(item) -> list:
	"""Up to EXAMPLES of the owner's recent decisions that look like this capture: the same sender or domain, the same source and kind, then the
	nearest by the words of the title. Each is {title, sender, decided}. Nothing sensitive or from the Vault is used."""
	i, p = frappe.qb.DocType("Life Inbox Item"), frappe.qb.DocType("Life Proposal")
	fn = frappe.query_builder.functions
	rows = (frappe.qb.from_(p).join(i).on(i.name == p.inbox_item).select(p.name, p.kind, p.status, p.payload, p.guess, p.inbox_item, i.title, i.sender, i.source_system, i.source_type)
		.where((p.space == item.space) & p.status.isin(["Accepted", "Rejected"]) & (p.decided_by != permissions.BRAIN_USER) & (i.name != item.name) & (i.is_sensitive == 0)
			& (fn.IfNull(i.vault_document, "") == ""))
		.orderby(p.decided_on, order=frappe.qb.desc).limit(200).run(as_dict=True))  # system: the owner's own recent decisions
	sender = (item.get("sender") or "").strip().lower()
	domain = domain_of(sender)
	mine = set(re.findall(r"[a-z0-9]{4,}", (item.get("title") or "").lower()))
	scored = []
	for n, r in enumerate(rows):
		other = (r.sender or "").lower()
		score = 0
		if sender and other == sender:
			score = 40
		elif domain and domain not in PUBLIC and domain_of(other) == domain:
			score = 30
		elif source_key(r) == source_key(item):
			score = 10 + (10 if r.source_type == item.get("source_type") else 0)
		overlap = len(mine & set(re.findall(r"[a-z0-9]{4,}", (r.title or "").lower())))
		score += min(overlap, 5)
		if score >= 5:
			scored.append((-score, n, r))
	out = []
	for _s, _n, r in sorted(scored)[:EXAMPLES]:
		out.append({"title": r.title or "", "sender": r.sender or "", "decided": decision_words(r)})
	return out


def decision_words(r) -> str:
	"""What the owner decided, in a few words: "kind Task, area Tea & Coffee" or "dropped"."""
	if r.status == "Rejected":
		return "dropped"
	data = frappe.parse_json(r.payload) if r.payload else {}
	return f"kind {r.kind}" + (f", area {area_name(data['area'])}" if data.get("area") else ", no area")


def space_made(doc, method=None):
	ensure_builtins(doc.name)


def applies_to(rule, key: str) -> bool:
	"""Can this rule apply to a capture of the source `key` (a channel, or a kind: kind-document)?"""
	from lifeos.brain import source_page
	from lifeos.skills import template

	if source_page.is_kind(key):
		media = template.KINDS[key[len(source_page.KIND_PREFIX):]][2].lower()
		return not rule.source and (not rule.item_kind or media in {k.lower() for k in _list(rule.item_kind)})
	return not rule.source or rule.source == key


def always_ask(item, prop):
	"""A rule that keeps what comes from this sender (or this source and kind) for the owner. One that already exists is switched to Ask."""
	conds = {"sender": (item.get("sender") or "").strip().lower()} if item.get("sender") else {"source": source_key(item), "item_kind": prop.kind}
	for r in rules_of(item.space, only_on=False):
		if all((r.get(k) or "") == v for k, v in conds.items()) and not r.title_words and not r.attachment_type:
			doc = frappe.get_doc("Life Rule", r.name)
			doc.update({"action": "Ask", "enabled": 1, "file_as": None})
			return doc.save(ignore_permissions=True)  # system: the owner changed their own rule, checked in the API
	return frappe.get_doc({"doctype": "Life Rule", "space": item.space, "made_by": "Owner", "enabled": 1, "action": "Ask", "source": source_key(item) if "sender" in conds else conds["source"],
		**{k: v for k, v in conds.items() if k != "source"}}).insert(ignore_permissions=True)  # system: the owner's own choice, checked in the API


def how_processed(space: str, key: str) -> dict:
	"""A source's page, as the issue lays it out: the rules that apply in the order they are tried, the line about the Brain, and what decided the last ten."""
	from lifeos.api import rules as api
	from lifeos.brain import source_page

	slug = source_page.skill_of(key)
	rows = [frappe.get_doc("Life Rule", r.name) for r in rules_of(space, only_on=False) if applies_to(r, key)]
	return {"key": key, "rules": [api.card(r) for r in rows], "skill": "process-capture", "skill_title": frappe.db.get_value("Life Skill", "process-capture", "title") or "process-capture",
		"channel_skill": slug,
		"brain_line": _("Everything else: the Brain reads it, guesses a kind and an area, and asks you only when unsure."), "recently": _recently(space, key)}


def _recently(space: str, key: str) -> list:
	from lifeos.brain import source_page

	got = source_page.recent(space, key, 10)
	names = [r["name"] for r in got]
	changed = set(frappe.get_all("Life Proposal", filters={"inbox_item": ("in", names or [""]), "decided_by": ("not in", ("", permissions.BRAIN_USER)), "status": ("!=", "Pending"), "filed_by": ("is", "not set")},  # system: the owner's decisions on these captures
		pluck="inbox_item"))
	out = []
	for r in got:
		by = r.get("processed_by") or ""
		if by.startswith("Rule:"):
			decided = by
		elif r["name"] in changed:
			decided = _("You changed it") if _was_changed(r["name"]) else _("The Brain")
		else:
			decided = _("The Brain")
		out.append({**r, "decided": decided})
	return out


def _was_changed(item: str) -> bool:
	for name in frappe.get_all("Life Proposal", filters={"inbox_item": item, "status": ("!=", "Pending")}, pluck="name"):  # system: the owner's decisions on this capture
		if classify(frappe.get_doc("Life Proposal", name)):
			return True
	return False
