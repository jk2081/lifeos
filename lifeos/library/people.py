"""People and organisations (issue 25): a Life Person is one place for a person or an organisation, linked to the wiki page
that describes them. Plumbing only: finding, creating and linking; who someone is comes from the wiki page's text."""
import re

import frappe

from lifeos.life.doctype.life_person.life_person import split_aliases

KINDS = ("Person", "Organisation")
# a title that reads like a company name; the patch uses it, and nothing else decides what a page is about
ORG_WORDS = re.compile(r"\b(pvt\.?|private|ltd\.?|limited|llp|llc|inc\.?|corp\.?|corporation|co\.|company|bank|motors|industries|enterprises|trust|foundation|association|university|hospital|society)\b", re.I)


def kind_of(value) -> str | None:
	"""'person', 'organization', 'Organisation' ... as one of KINDS, or None."""
	v = (value or "").strip().lower()
	if v in ("person", "people"):
		return "Person"
	if v in ("organisation", "organization", "org", "company"):
		return "Organisation"
	return None


def names_of(person) -> list[str]:
	"""The name and the other names a person goes by."""
	return [n for n in [person.get("full_name"), *split_aliases(person.get("aliases"))] if n]


def find(space, title):
	"""The Life Person of a space whose name or another name is `title` (any case), or None."""
	t = " ".join((title or "").split()).lower()
	if not t:
		return None
	for p in frappe.get_all("Life Person", filters={"space": space}, fields=["name", "full_name", "aliases", "kind", "wiki_page"], order_by="creation asc", limit=5000):
		if t in [n.lower() for n in names_of(p)]:
			return p
	return None


def link_page(note, kind=None) -> str | None:
	"""Link a Wiki page to the Life Person it is about, creating one when there is none. kind: Person or Organisation.
	A person who already has the page's title (or goes by it) is reused, so running this twice makes no duplicate."""
	kind = kind_of(kind)
	if not kind or note.collection != "Wiki":
		return None
	person = frappe.db.get_value("Life Person", note.get("person"), ["name", "wiki_page"], as_dict=True) if note.get("person") else None
	person = person or find(note.space, note.title)
	if person:
		name = person.name
		if not person.wiki_page or person.wiki_page == note.name:
			frappe.db.set_value("Life Person", name, "wiki_page", note.name, update_modified=False)
	else:
		doc = frappe.get_doc({"doctype": "Life Person", "space": note.space, "full_name": note.title, "kind": kind, "area": note.get("area") or None,
			"wiki_page": note.name})
		doc.insert(ignore_permissions=True)  # the caller has already checked write access to the space
		name = doc.name
	if note.get("person") != name:
		frappe.db.set_value("Life Note", note.name, "person", name, update_modified=False)
		note.person = name
	return name


def link_existing(space=None) -> dict:
	"""The patch: link the Wiki pages that match a Life Person by title or name, make an Organisation for a page that reads like
	a company, and list the pages about people it could not place (it never guesses a person). Safe to run again."""
	linked, created, undecided = [], [], []
	filters = {"collection": "Wiki", "person": ("is", "not set"), "is_rules": 0}
	if space:
		filters["space"] = space
	for n in frappe.get_all("Life Note", filters=filters, fields=["name", "space", "title", "summary", "area", "collection", "person"], order_by="creation asc", limit=100000):
		found = find(n.space, n.title)
		about = kind_of((n.summary or "").replace("·", " ").split(" ")[0] if n.summary else "")
		if found:
			link_page(n, found.kind)
			linked.append(n.name)
		elif about == "Organisation" or (about is None and ORG_WORDS.search(n.title or "") and not (n.summary or "").lower().startswith(("person", "people"))):
			link_page(n, "Organisation")
			created.append(n.name)
		elif about == "Person":
			undecided.append((n.name, n.title, "a person, but no Life Person with that name"))
	return {"linked": linked, "created": created, "undecided": undecided}
