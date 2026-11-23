"""A focus's own page, and what becomes of an Open goal (issue 57). A focus is a Life Area with `is_focus`: ongoing work under a
part with a standard, principles and an annual goal. It is made and edited through `settings.save_item`."""
import frappe
from frappe import _

from lifeos import areas, permissions, readings
from lifeos.api import goals as goal_api


def _focus(area):
	doc = permissions.get_doc_checked("Life Area", area)
	if not doc.is_focus:
		frappe.throw(_("{0} is not a focus.").format(doc.area_name), title=_("Area is not a focus"))
	return doc


GOAL_FIELDS = ["name", "title", "horizon", "outcome", "target_date", "cycle", "serves", "done_when", "measure_kind", "measure", "unit", "start_value",
	"target_value", "current_value", "current_on", "is_someday", "last_activity_on"]


@frappe.whitelist(methods=["GET"])
def get(area: str):
	"""A focus's page: its standard and principles, its goals by horizon (annual, 12 Week Year, others, then the finished, greyed),
	and how it is going: cycles with a goal among the last three, the last activity, and the notes and captures filed under it."""
	doc = _focus(area)
	parent = frappe.db.get_value("Life Area", doc.parent_area, ["name", "area_name", "is_life_area", "parent_area"], as_dict=True)
	life = parent if parent.is_life_area else frappe.db.get_value("Life Area", parent.parent_area, ["name", "area_name"], as_dict=True)
	rows = frappe.get_list("Life Goal", filters={"area": area, "is_archived": 0}, fields=GOAL_FIELDS, order_by="sort_order asc, creation asc", limit=500)
	counts = goal_api.task_counts([r.name for r in rows])
	for r in rows:
		r["tasks_done"], r["tasks_counted"] = counts.get(r.name, (0, 0))
		r["progress"] = readings.summary(r)
		r["target_date"] = str(r.target_date) if r.target_date else None
		r["current_on"] = str(r.current_on) if r.current_on else None
		r["last_activity_on"] = str(r.last_activity_on) if r.last_activity_on else None
	live = [r for r in rows if r.outcome == "In Progress" and not r.is_someday]
	finished = [r for r in rows if r.outcome != "In Progress"]
	annual = [r for r in live if r.horizon == "Year"]
	cycles = frappe.get_list("Life Cycle", filters={"space": doc.space, "status": ("in", ("Active", "Closed"))}, fields=["name", "title"],
		order_by="start_date desc", limit=3)
	with_goal = {r.cycle for r in rows if r.horizon == "12 weeks" and r.cycle}
	last = frappe.get_list("Life Task", filters={"area": area, "is_archived": 0}, fields=["title", "status", "due_date", "scheduled_at", "modified"],
		order_by="modified desc", limit=1)
	return {
		"name": doc.name, "title": doc.area_name, "space": doc.space, "standard": doc.standard, "is_on": doc.is_on,
		"principles": [p.line for p in doc.principles], "colour": doc.colour,
		"part": {"name": parent.name, "area_name": parent.area_name} if not parent.is_life_area else None,
		"life_area": {"name": life.name, "area_name": life.area_name} if life else None,
		"annual": annual, "cycle": [r for r in live if r.horizon == "12 weeks"], "other": [r for r in live if r.horizon in ("Month", "Long term")],
		"finished": finished, "has_annual": bool(annual),
		"going": {
			"cycles_with_goal": len([c for c in cycles if c.name in with_goal]), "cycles_considered": len(cycles),
			"last_activity": {"title": last[0].title, "status": last[0].status, "on": str(last[0].scheduled_at or last[0].due_date or last[0].modified)[:19]} if last else None,
			"notes": frappe.db.count("Life Index", {"space": doc.space, "area": area, "kind": "Note", "is_archived": 0}),
			"captures": frappe.db.count("Life Index", {"space": doc.space, "area": area, "kind": "Inbox", "is_archived": 0}),
		},
		"writable": bool(permissions.is_admin()),
	}


@frappe.whitelist(methods=["GET"])
def annual_for(area: str):
	"""The active Annual goal of a focus ({name, title}, or null): the 12 Week Year goal form suggests it as what the new goal serves."""
	if not permissions.get_doc_checked("Life Area", area).is_focus:
		return None
	return frappe.db.get_value("Life Goal", {"area": area, "horizon": "Year", "outcome": "In Progress", "is_someday": 0, "is_archived": 0},
		["name", "title"], as_dict=True, order_by="sort_order asc, creation asc")


def focuses_without_goal(space, covered):
	"""The active focuses of a space whose area is not in `covered` (the areas the next cycle's goals are filed under): the 12-week review
	asks about each one once, to set a goal this cycle or just maintain it. None while "Use focuses" is off."""
	if not areas.use_focuses():
		return []
	hidden = set(areas.off(space))
	return [f for f in frappe.get_list("Life Area", filters={"space": space, "is_focus": 1, "is_on": 1, "is_archived": 0}, fields=["name", "area_name", "standard"],
		order_by="sort_order asc, area_name asc", limit=500) if f.name not in covered and f.name not in hidden]


@frappe.whitelist(methods=["POST"])
def sort_open(goal: str, action: str, title: str | None = None, target_date: str | None = None, done_when: str | None = None):
	"""What becomes of an Open goal (an existing goal of horizon Long term, shown as "To sort"):
	`focus`: a new focus under the goal's part or area, with the goal's notes; its open tasks move to a new Annual goal under it,
	named `title` (the goal's own name when not given), with `target_date` (the end of the year by default) and `done_when`;
	`annual`: the goal itself becomes an Annual goal with `target_date`;
	`drop`: the goal is dropped. The owner only."""
	goal_api._person_only()
	permissions.require_login()
	doc = permissions.get_doc_checked("Life Goal", goal, "write")
	if doc.horizon != "Long term" or doc.outcome != "In Progress":
		frappe.throw(_("Only an Open goal in progress is sorted this way."), title=_("Goal cannot be sorted"))
	if action == "drop":
		return goal_api.close(goal, "Dropped")
	if action == "annual":
		if not target_date:
			frappe.throw(_("An Annual goal needs a target date."), title=_("Annual goal needs a date"))
		doc.horizon, doc.target_date = "Year", target_date
		doc.save()
		return {"name": doc.name, "horizon": doc.horizon}
	if action != "focus":
		frappe.throw(_("Choose focus, annual or drop."), title=_("Unknown sorting choice"))
	if not areas.use_focuses():
		frappe.throw(_("Switch on Use focuses in Settings → Areas to make a focus."), title=_("Focuses are switched off"))
	if not permissions.is_admin():
		frappe.throw(_("Only the owner can make a focus."), frappe.PermissionError, title=_("Only the owner makes focuses"))
	parent = doc.area
	if parent and frappe.db.get_value("Life Area", parent, "is_focus"):
		parent = frappe.db.get_value("Life Area", parent, "parent_area")
	if not parent:
		parent = areas.ensure(doc.space)[areas.DEFAULT_PARENT]
	name = (doc.title or "").strip()
	focus = frappe.get_doc({"doctype": "Life Area", "space": doc.space, "area_name": name, "parent_area": parent, "is_focus": 1,
		"standard": (doc.done_when or "").strip() or None, "description": doc.notes_md or None})
	focus.insert()
	annual = goal_api.create(title=(title or "").strip() or name, horizon="Year", space=doc.space, area=focus.name,
		target_date=target_date or goal_api.year_end(), done_when=done_when or doc.done_when)
	for t in frappe.get_list("Life Task", filters={"goal": doc.name}, pluck="name", limit=0):
		frappe.db.set_value("Life Task", t, {"goal": annual["name"], "area": focus.name})
	doc.flags.no_archive = True
	doc.outcome, doc.result_note = "Dropped", _("Made into the focus {0}.").format(focus.area_name)
	doc.save()
	return {"focus": focus.name, "annual": annual["name"]}
