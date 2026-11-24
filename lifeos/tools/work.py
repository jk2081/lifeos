"""Ask tools for what the owner plans (issue 107): a task and an event, made straight away when the owner asked for them. A task or an event Ask suggests
on its own stays a button the owner clicks."""
import frappe
from frappe import _

from lifeos.tools import actions


def add_task(title: str, area: str | None = None, part: str | None = None, due_date: str | None = None, space: str | None = None) -> dict:
	"""Make a task called `title`, under an `area` (and a `part`) by their names, with an optional due date (YYYY-MM-DD). Owner only."""
	return actions.write("tasks.add", space, {"title": title, "area": area, "part": part, "due_date": due_date})


def _add_task(space: str, title: str, area: str | None = None, part: str | None = None, due_date: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.api import tasks

	where = actions.area_of(space, area, part) if area or part else None
	task = tasks.quick_add(title, space=space, area=where, due_date=due_date or None)
	return _("Made task {0}").format(task["title"]), {"task": task["name"], "title": task["title"], "due_date": str(task.get("due_date") or "")}, {"delete": [["Life Task", task["name"]]]}


def add_event(title: str, start: str, end: str | None = None, all_day: bool = False, description: str | None = None, space: str | None = None) -> dict:
	"""Put an event on the calendar: `start` and `end` as YYYY-MM-DD or YYYY-MM-DD HH:MM. Owner only."""
	return actions.write("events.add", space, {"title": title, "start": start, "end": end, "all_day": all_day, "description": description})


def _add_event(space: str, title: str, start: str, end: str | None = None, all_day: bool = False, description: str | None = None) -> tuple[str, dict, dict | None]:
	from lifeos.api import calendar

	made = calendar.add_event(space=space, subject=title, starts_on=start, ends_on=end, all_day=1 if all_day else 0, description=description)
	return _("Added event {0} on {1}").format(title, str(start)[:16]), {"event": made["name"], "title": title}, {"events": [made["name"]]}
