"""The weekly review's new steps (set 7): step 1's key results (readings to confirm, goals that need a finish line, number goals
with no recent reading) and step 3's goal work for the coming week. People only."""
import frappe
from frappe import _
from frappe.utils import cint

from lifeos import permissions, readings, weekplan
from lifeos.api.utils import in_area, lens_area


SOURCES = ("Life Inbox Item", "Life Chat Log", "Life Note")  # what a reading can cite


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("The weekly review is for people."), frappe.PermissionError)


def _in_lens(space, area, rows, key="name"):
	if not area:
		return rows
	keep = in_area(space, area, "Life Goal", [r[key] for r in rows])
	return [r for r in rows if r[key] in keep]


@frappe.whitelist(methods=["GET"])
def key_results(space: str | None = None, area: str | None = None):
	"""Step 1 of the weekly review: every Suggested reading with its excerpt and source, goals in progress with neither a finish
	line nor a number, and number goals with no reading in the last 14 days ("Where is X now?")."""
	_person()
	space = permissions.resolve_space(space)
	area = lens_area(area)
	goals = frappe.get_all("Life Goal", filters={"space": space, "outcome": "In Progress", "is_someday": 0, "is_archived": 0},
		fields=["name", "title", "horizon", "area", "done_when", "measure_kind", "measure", "unit", "start_value", "target_value", "current_value",
			"current_on", "notes_md", "cycle"], limit=500)
	goals = _in_lens(space, area, goals)
	by_name = {g.name: g for g in goals}
	suggested = frappe.get_all("Life Goal Reading", filters={"space": space, "status": "Suggested", "goal": ("in", list(by_name) or ["-"])},
		fields=["name", "goal", "date", "value", "status", "excerpt", "source_doctype", "source_name", "suggested_by", "confirmed_on"],
		order_by="date desc, creation desc", limit=200)
	titles = {}
	for dt in {r.source_doctype for r in suggested if r.source_doctype in SOURCES}:
		names = [r.source_name for r in suggested if r.source_doctype == dt and r.source_name]
		titles.update({(dt, n): t for n, t in frappe.get_all(dt, filters={"name": ("in", names)}, fields=["name", "title"], as_list=True)})
	to_confirm = []
	for r in suggested:
		g = by_name[r.goal]
		to_confirm.append({**readings.reading_dict(r), "goal_title": g.title, "unit": g.unit, "measure": g.measure,
			"source_title": titles.get((r.source_doctype, r.source_name))})
	cycles = frappe.get_all("Life Cycle", filters={"space": space, "status": "Active"}, pluck="name")
	no_line = [{"name": g.name, "title": g.title, "horizon": g.horizon, "area": g.area, "notes_md": g.notes_md} for g in goals
		if not readings.has_finish_line(g) and (g.horizon != "12 weeks" or g.cycle in cycles)]
	stale = [{"name": g["name"], "title": g["title"], "measure": g["measure"], "unit": g["unit"], "last_reading_on": g.get("last_reading_on"),
		"progress": readings.summary(g)} for g in readings.stale_number_goals(space, [g for g in goals if g.measure_kind == "Number"])]
	return {"readings": to_confirm, "needs_finish_line": no_line, "stale": stale}


@frappe.whitelist(methods=["POST"])
def goal_plan(space: str | None = None, area: str | None = None):
	"""Step 3 of the weekly review: one card per active goal in the lens, with a suggested next action, slot and length. POST:
	the suggestions may call the assistant, which is recorded against the month's spend."""
	_person()
	space = permissions.resolve_space(space, write=True)
	space_ai = frappe.db.get_value("Life Space", space, "ask_enabled")
	return weekplan.cards(space, lens_area(area), ai=bool(space_ai))


@frappe.whitelist(methods=["POST"])
def add_goal_work(goal: str, title: str | None = None, task: str | None = None, scheduled_at: str | None = None, duration_min: int | None = None,
		who: str | None = None, note: str | None = None):
	"""Create or update the task under a goal from its card: `scheduled_at` (empty for no set time), `duration_min`, the note in
	its notes, and `who` (empty or Me for the owner; anyone else makes the task Waiting on them)."""
	_person()
	doc = weekplan.add(goal, title, task, scheduled_at, cint(duration_min) or None, who, note)
	return {"task": doc.name, "title": doc.title, "status": doc.status, "waiting_on": doc.waiting_on,
		"scheduled_at": str(doc.scheduled_at)[:19] if doc.scheduled_at else None, "duration_min": doc.duration_min}
