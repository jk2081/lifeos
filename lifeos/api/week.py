"""The weekly review's step 1: key results (readings to confirm, goals that need a finish line, number goals with no recent
reading). People only."""
import frappe
from frappe import _

from lifeos import permissions, readings
from lifeos.api.utils import in_area, lens_area


SOURCES = ("Life Inbox Item", "Life Chat Log", "Life Note")  # what a reading can cite


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("The weekly review is for people."), frappe.PermissionError, title=_("Reviews are for people"))


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
	goals = frappe.get_list("Life Goal", filters={"space": space, "outcome": "In Progress", "is_someday": 0, "is_archived": 0},
		fields=["name", "title", "horizon", "area", "done_when", "measure_kind", "measure", "unit", "start_value", "target_value", "current_value",
			"current_on", "notes_md", "cycle"], limit=500)
	goals = _in_lens(space, area, goals)
	by_name = {g.name: g for g in goals}
	suggested = frappe.get_list("Life Goal Reading", filters={"space": space, "status": "Suggested", "goal": ("in", list(by_name) or ["-"])},
		fields=["name", "goal", "date", "value", "status", "excerpt", "source_doctype", "source_name", "suggested_by", "confirmed_on"],
		order_by="date desc, creation desc", limit=200)
	titles = {}
	for dt in {r.source_doctype for r in suggested if r.source_doctype in SOURCES}:
		names = [r.source_name for r in suggested if r.source_doctype == dt and r.source_name]
		titles.update({(dt, n): t for n, t in frappe.get_list(dt, filters={"name": ("in", names)}, fields=["name", "title"], as_list=True)})
	to_confirm = []
	for r in suggested:
		g = by_name[r.goal]
		to_confirm.append({**readings.reading_dict(r), "goal_title": g.title, "unit": g.unit, "measure": g.measure,
			"source_title": titles.get((r.source_doctype, r.source_name))})
	cycles = frappe.get_list("Life Cycle", filters={"space": space, "status": "Active"}, pluck="name")
	no_line = [{"name": g.name, "title": g.title, "horizon": g.horizon, "area": g.area, "notes_md": g.notes_md} for g in goals
		if not readings.has_finish_line(g) and (g.horizon != "12 weeks" or g.cycle in cycles)]
	stale = [{"name": g["name"], "title": g["title"], "measure": g["measure"], "unit": g["unit"], "last_reading_on": g.get("last_reading_on"),
		"progress": readings.summary(g)} for g in readings.stale_number_goals(space, [g for g in goals if g.measure_kind == "Number"])]
	return {"readings": to_confirm, "needs_finish_line": no_line, "stale": stale}
