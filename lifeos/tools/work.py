"""Ask tools for what the owner plans (issue 107): a task and an event, made straight away when the owner asked for them, by the owner or through an agent
(issue 125). A task or an event Ask suggests on its own stays a button the owner clicks; an agent's own idea follows its "Add tasks and events" switch."""
import frappe
from frappe import _

from lifeos.tools import actions


def add_task(title: str, area: str | None = None, part: str | None = None, due_date: str | None = None, person: str | None = None, space: str | None = None, source_system: str | None = None, asked_by: str | None = None, owner_message: str | None = None) -> dict:
	"""Make a task called `title`, under an `area` (and a `part`) by their names, with an optional due date (YYYY-MM-DD) and the `person` it is about (by name; the task then links to them)."""
	return actions.write("tasks.add", space, {"title": title, "area": area, "part": part, "due_date": due_date, "person": person}, source_system, owner_message, asked_by)


def _add_task(space: str, title: str, area: str | None = None, part: str | None = None, due_date: str | None = None, person: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.api import tasks
	from lifeos.library import people

	where = actions.area_of(space, area, part) if area or part else None
	task = tasks.quick_add(title, space=space, area=where, due_date=due_date or None)
	found = people.find(space, person) if person else None
	if found:  # the task links to the person: a [[link]] in its notes, which Life OS resolves on save
		doc = frappe.get_doc("Life Task", task["name"])
		doc.notes_md = f"With [[{found.full_name}]]"
		doc.save()
	return _("Made task {0}").format(task["title"]), {"task": task["name"], "title": task["title"], "due_date": str(task.get("due_date") or ""), "person": found.full_name if found else ""}, {"delete": [["Life Task", task["name"]]]}


def add_event(title: str, start: str, end: str | None = None, all_day: bool = False, description: str | None = None, space: str | None = None, source_system: str | None = None, asked_by: str | None = None, owner_message: str | None = None) -> dict:
	"""Put an event on the calendar: `start` and `end` as YYYY-MM-DD or YYYY-MM-DD HH:MM."""
	return actions.write("events.add", space, {"title": title, "start": start, "end": end, "all_day": all_day, "description": description}, source_system, owner_message, asked_by)


def _add_event(space: str, title: str, start: str, end: str | None = None, all_day: bool = False, description: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.api import calendar

	made = calendar.add_event(space=space, subject=title, starts_on=start, ends_on=end, all_day=1 if all_day else 0, description=description)
	return _("Added event {0} on {1}").format(title, str(start)[:16]), {"event": made["name"], "title": title}, {"events": [made["name"]]}
