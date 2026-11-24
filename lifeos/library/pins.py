"""Pinned pages (issue 111): a person's own short list of pages shown in the sidebar under Library, in the order they chose.

One `Life Pin` per person, page and place in the order; never shared. At most `LIMIT`. Suggestions are only ever offered, never made: "Pin it?" for a
page opened 5 times in 7 days, and "Unpin?" for a pin not opened for 30 days. A count appears when something was linked after the page was last opened."""
import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, now_datetime

from lifeos.library import subjects

LIMIT = 7
PAGE_DOCTYPES = ("Life Person", "Life Area", "Life Note")
OPENS_TO_OFFER, OFFER_DAYS, UNUSED_DAYS = 5, 7, 30


def title_and_kind(doctype: str, name: str) -> tuple[str, str] | None:
	"""(title, kind icon: company, person, part or note) of a page; None when it is gone."""
	if not frappe.db.exists(doctype, name):
		return None
	if doctype == "Life Note":
		return frappe.db.get_value("Life Note", name, "title"), "note"
	return subjects.title_of(doctype, name), subjects.kind_of_subject(doctype, name)


def new_since(doctype: str, name: str, since) -> int:
	"""How many things were linked to a page since a time (0 when it was never opened: nothing is "new" to someone who has not looked yet)."""
	if not since or doctype == "Life Note":
		return 0
	return frappe.db.count("Life Link", {"to_doctype": doctype, "to_name": name, "origin": ("in", ("Brain", "Owner")), "creation": (">", since)})


def mine(user: str | None = None) -> list:
	"""The person's pins, in their order: [{doctype, name, title, kind, new, seen_on}]. A pin whose page is gone or that the person may not read is left out."""
	user = user or frappe.session.user
	out = []
	for p in frappe.get_all("Life Pin", filters={"user": user}, fields=["name", "ref_doctype", "ref_name", "seen_on", "idx_order"], order_by="idx_order asc, creation asc", limit=50):
		got = title_and_kind(p.ref_doctype, p.ref_name)
		if not got or not frappe.has_permission(p.ref_doctype, "read", p.ref_name, user=user):
			continue
		out.append({"doctype": p.ref_doctype, "name": p.ref_name, "title": got[0], "kind": got[1], "new": new_since(p.ref_doctype, p.ref_name, p.seen_on), "seen_on": str(p.seen_on or "")})
	return out


def _row(user, doctype, name):
	return frappe.db.get_value("Life Pin", {"user": user, "ref_doctype": doctype, "ref_name": name})


def pin(doctype: str, name: str, replace: str | None = None, user: str | None = None) -> dict:
	"""Pin a page. With seven already pinned it is refused with the choice of which to unpin (`choose_to_unpin`); `replace` ("Doctype:name") unpins that one first."""
	user = user or frappe.session.user
	if doctype not in PAGE_DOCTYPES or not frappe.db.exists(doctype, name):
		frappe.throw(_("That page does not exist."), frappe.DoesNotExistError, title=_("Page not found"))
	if _row(user, doctype, name):
		return {"pinned": True, "pins": mine(user)}
	have = frappe.get_all("Life Pin", filters={"user": user}, pluck="name")
	if len(have) >= LIMIT:
		if replace:
			rdt, _sep, rname = replace.partition(":")
			gone = _row(user, rdt, rname)
			if not gone:
				frappe.throw(_("That page is not pinned."), title=_("Not pinned"))
			frappe.delete_doc("Life Pin", gone, ignore_permissions=True, force=True)  # system: the person's own pin
		else:
			return {"pinned": False, "refused": True, "message": _("You can pin {0} pages. Which one should go?").format(LIMIT), "choose_to_unpin": mine(user)}
	top = max([frappe.db.get_value("Life Pin", n, "idx_order") or 0 for n in frappe.get_all("Life Pin", filters={"user": user}, pluck="name")] or [0])
	frappe.get_doc({"doctype": "Life Pin", "user": user, "ref_doctype": doctype, "ref_name": name, "idx_order": top + 1, "seen_on": now_datetime()}).insert(ignore_permissions=True)  # system: the person's own pin
	return {"pinned": True, "pins": mine(user)}


def unpin(doctype: str, name: str, user: str | None = None) -> dict:
	user = user or frappe.session.user
	row = _row(user, doctype, name)
	if row:
		frappe.delete_doc("Life Pin", row, ignore_permissions=True, force=True)  # system: the person's own pin
	return {"pins": mine(user)}


def reorder(order: list, user: str | None = None) -> dict:
	"""The pins in the order the person dragged them to: a list of "Doctype:name"."""
	user = user or frappe.session.user
	for i, ref in enumerate(order or []):
		dt, _sep, name = str(ref).partition(":")
		row = _row(user, dt, name)
		if row:
			frappe.db.set_value("Life Pin", row, "idx_order", i + 1, update_modified=False)
	return {"pins": mine(user)}


def visit(doctype: str, name: str, user: str | None = None) -> dict:
	"""The person opened a page: the count on its pin clears, and the opening is kept for the suggestion. Returns {offer_pin: bool}."""
	user = user or frappe.session.user
	if doctype not in PAGE_DOCTYPES:
		return {"offer_pin": False}
	row = _row(user, doctype, name)
	if row:
		frappe.db.set_value("Life Pin", row, "seen_on", now_datetime(), update_modified=False)
	frappe.get_doc({"doctype": "Life Page Visit", "user": user, "ref_doctype": doctype, "ref_name": name, "opened_on": now_datetime()}).insert(ignore_permissions=True)  # system: the person's own visit
	return {"offer_pin": offer_pin(doctype, name, user)}


def _offered_key(doctype, name):
	return f"lifeos_pin_offered:{doctype}:{name}"


def offer_pin(doctype: str, name: str, user: str) -> bool:
	"""True once: the page was opened 5 times in 7 days and is not pinned. The offer is made one time only."""
	if _row(user, doctype, name) or frappe.defaults.get_user_default(_offered_key(doctype, name), user):
		return False
	opens = frappe.db.count("Life Page Visit", {"user": user, "ref_doctype": doctype, "ref_name": name, "opened_on": (">=", add_days(now_datetime(), -OFFER_DAYS))})
	if opens < OPENS_TO_OFFER:
		return False
	frappe.defaults.set_user_default(_offered_key(doctype, name), "1", user)
	return True


def unused(user: str | None = None) -> list:
	"""The pins not opened for 30 days: offered "Unpin?" in the weekly review."""
	user = user or frappe.session.user
	cutoff = add_days(now_datetime(), -UNUSED_DAYS)
	return [p for p in mine(user) if p["seen_on"] and p["seen_on"] < str(cutoff)]


def purge_visits():
	"""Daily: the openings older than 30 days are forgotten."""
	frappe.db.delete("Life Page Visit", {"opened_on": ("<", add_to_date(now_datetime(), days=-30))})
