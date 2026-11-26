"""Ask tool: save an answer as a note (issue 107)."""
import frappe
from frappe import _

from lifeos.tools import actions


def save(title: str, body: str, area: str, part: str | None = None, space: str | None = None, source_system: str | None = None, asked_by: str | None = None, owner_message: str | None = None) -> dict:
	"""Save `body` (Markdown), for example a summary you wrote, as a note called `title` under an `area` (and a `part`), by their names."""
	return actions.write("notes.save", space, {"title": title, "body": body, "area": area, "part": part}, source_system, owner_message, asked_by)


def _save(space: str, title: str, body: str, area: str, part: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.api import library

	if not (title or "").strip():
		frappe.throw(_("A note needs a title."), title=_("Note needs a title"))
	where = actions.area_of(space, area, part)
	note = library.save(space=space, title=title, content_md=body or "", area=where)
	return _("Saved note {0}").format(note["title"]), {"note": note["name"], "title": note["title"], "area": where}, {"delete": [["Life Note", note["name"]]]}
