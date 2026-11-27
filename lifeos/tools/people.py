"""Ask tool: add a person (issue 107), with their company, linked to a page."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.library import people as library
from lifeos.tools import actions


def add(name: str, email: str | None = None, company: str | None = None, link_to: str | None = None, space: str | None = None,
		source_system: str | None = None, asked_by: str | None = None, owner_message: str | None = None) -> dict:
	"""Add a person by `name`, with their `email` and `company` (made as an organisation when it is new), and link them to a page (`link_to`, a page's name):
	the page then lists them under "People" as [[Name]]. A person who is already there is reused, not added twice."""
	return actions.write("people.add", space, {"name": name, "email": email, "company": company, "link_to": link_to}, source_system, owner_message, asked_by)


def _add(space: str, name: str, email: str | None = None, company: str | None = None, link_to: str | None = None) -> tuple[str, dict, dict | None]:
	page = permissions.get_doc_checked("Life Note", link_to, "write") if link_to else None
	if page and page.space != space:
		frappe.throw(_("That page is in another space."), title=_("Page is in another space"))
	made, found_org = [], None
	person, new = library.add(space, name, email=email)
	if new:
		made.append(("Life Person", person.name))
	else:
		found_org = person.organisation
		if email and not person.email:
			person.email = email
			person.save()
	org = None
	if company and company.strip():
		org = library.find(space, company)
		if not org:
			org = frappe.get_doc({"doctype": "Life Person", "space": space, "full_name": company.strip()[:140], "kind": "Organisation"}).insert()
			made.append(("Life Person", org.name))
		if person.organisation != org.name:
			person.organisation = org.name
			person.save()
	if page:
		text = page.content_md or ""
		if f"[[{person.full_name}]]" not in text:
			from lifeos.api import wiki

			page.content_md = text.rstrip() + ("\n\n## People\n" if "## People" not in text else "\n") + f"- [[{person.full_name}]]" + (f", {company.strip()}" if company else "") + "\n"
			before = text
			page.save()
			if page.collection == "Wiki":
				wiki.person_edited(page, before)
	line = _("Added {0}").format(person.full_name) if made else _("{0} was already there").format(person.full_name)
	return (line, {"person": person.name, "name": person.full_name, "organisation": org.name if org else None, "page": page.name if page else None},
		{"clear": [["Life Person", person.name, "organisation"]] if org and org.name != found_org else [], "delete": [[dt, n] for dt, n in made], **({"restore_text": text, "page": page.name} if page and text != page.content_md else {})} if made or (page and text != page.content_md) else None)
