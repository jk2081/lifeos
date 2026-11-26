"""Ask tools for wiki pages (issue 107): make a page under an area or part, and add to one. The page body is Markdown that can cite emails, files and
people with [[Title]] links. Every change is also a Life Wiki Change, so it can be undone from the page's history too."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.tools import actions

KINDS = ("Prospect", "Client", "Project", "Person", "Note")
ABOUT = {"Prospect": "Organisation", "Client": "Organisation", "Person": "Person"}  # what a page of this kind is about; a Life Person is made for it


def create(title: str, area: str, part: str | None = None, kind: str | None = None, body: str | None = None, sources: list | None = None,
		summary: str | None = None, space: str | None = None, source_system: str | None = None, asked_by: str | None = None, owner_message: str | None = None) -> dict:
	"""Create a wiki page called `title` under an `area` (and a `part` of it), by their names. `kind` is one of Prospect, Client, Project, Person or Note.
	A Prospect, Client or Person page is also made a person or organisation, so they can be linked. `body` is Markdown and may link people and pages as
	[[Name]]. `summary` is one line on what the page is about (the start of the body when left out). `sources` are emails or captures it is written from, as
	"Life Inbox Item:<name>". Refuses a title the wiki already has: update that page."""
	return actions.write("pages.create", space, {"title": title, "area": area, "part": part, "kind": kind, "body": body, "sources": sources, "summary": summary}, source_system, owner_message, asked_by)


def _create(space: str, title: str, area: str | None, part: str | None = None, kind: str | None = None, body: str | None = None,
		sources: list | None = None, summary: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.api import wiki

	if kind and kind not in KINDS:
		frappe.throw(_("A page is a Prospect, Client, Project, Person or Note."), title=_("Page kind not understood"))
	where = actions.area_of(space, area, part)
	first = next((ln.lstrip("# ").strip() for ln in (body or "").splitlines() if ln.strip()), "")
	made = wiki.create_page(space=space, title=title, content_md=body or "", summary=(summary or first or " ".join(x for x in (kind, title) if x))[:140], area=where,
		sources=sources or None, about=ABOUT.get(kind or ""))
	if kind:
		frappe.db.set_value("Life Note", made["name"], "kind", kind)
	place = _place(where)
	person = frappe.db.get_value("Life Note", made["name"], "person")
	line = _("Created page {0} ({1})").format(made["title"], ", ".join(x for x in (kind, place) if x)) if kind or place else _("Created page {0}").format(made["title"])
	return (line, {"page": made["name"], "title": made["title"], "kind": kind, "area": where, "person": person},
		{"clear": [["Life Note", made["name"], "person"]] if person else [],
			"delete": [*([["Life Person", person]] if person and frappe.db.get_value("Life Person", person, "wiki_page") == made["name"] else []), ["Life Note", made["name"]]]})


def _place(area: str | None) -> str:
	"""An area as the owner reads it: "Career › BTW" for a part, "Career" for an area."""
	if not area:
		return ""
	name, parent = frappe.db.get_value("Life Area", area, ["area_name", "parent_area"])
	return f"{frappe.db.get_value('Life Area', parent, 'area_name')} › {name}" if parent else name


def update(page: str, body: str | None = None, add_links: list | None = None, space: str | None = None, source_system: str | None = None, asked_by: str | None = None, owner_message: str | None = None) -> dict:
	"""Change a wiki page: replace its text with `body` (Markdown), and/or add `add_links`, a list of page or person titles to link under "Links" as
	[[Title]]. Read the page first when you only add to it, and send its whole new text."""
	return actions.write("pages.update", space, {"page": page, "body": body, "add_links": add_links}, source_system, owner_message, asked_by)


def _update(space: str, page: str, body: str | None = None, add_links: list | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.api import wiki

	doc = permissions.get_doc_checked("Life Note", page, "write")
	if doc.space != space:
		frappe.throw(_("That page is in another space."), title=_("Page is in another space"))
	text = doc.content_md if body is None else body
	have = text or ""
	new = [t.strip() for t in add_links or [] if str(t).strip() and f"[[{str(t).strip()}]]" not in have]
	if new:
		text = have.rstrip() + ("\n\n## Links\n" if "## Links" not in have else "\n") + "\n".join(f"- [[{t}]]" for t in new) + "\n"
	if text == (doc.content_md or ""):
		return _("Page {0} already says that").format(doc.title), {"page": doc.name, "title": doc.title}, None
	got = wiki.update_page(doc.name, content_md=text, base_version=wiki.version_of(doc))
	change = frappe.db.get_value("Life Wiki Change", {"note": doc.name}, "name", order_by="creation desc")
	return (_("Changed page {0}").format(doc.title), {"page": doc.name, "title": doc.title, "version": got.get("version")},
		{"restore_change": change} if change else None)
