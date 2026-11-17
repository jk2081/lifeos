"""Set 6: every project becomes an open-ended goal (goal type Open), and every link to a project points to that goal.

The mapping is in DECISIONS.md ("Set 6: Simplify", Projects become goals):
  Active  -> outcome In Progress
  On Hold -> outcome In Progress, on_hold = 1
  Done    -> outcome Achieved, closed_on and completed_on = the project's completed_on
  Dropped -> outcome Dropped, closed_on and completed_on = the project's completed_on
  Someday -> outcome In Progress, is_someday = 1, with the project's Someday dates and note
The project's outcome text becomes the goal's "Done when", and its notes, target date, archive state, last activity,
creation and modification dates carry over. The new goal's name is stored on the project (`migrated_to`).

Every step only fills what is still empty or still names a project, so running the patch again changes nothing.
The old `project` columns are read with plain SQL: Frappe keeps a column when its field leaves the DocType, and a new
site never had them (each read checks first).
"""
import json

import frappe
from frappe.utils import getdate

STATUS = {
	"Active": ("In Progress", 0, 0), "On Hold": ("In Progress", 1, 0), "Done": ("Achieved", 0, 0),
	"Dropped": ("Dropped", 0, 0), "Someday": ("In Progress", 0, 1),
}
# DocTypes whose `project` field became `goal` (the meaning is "belongs to")
RENAMED = ("Life Chat Log", "Life Idea", "Life Inbox Item", "Life Journal Page", "Life Note", "Life Vault Document")
# Dynamic links: (DocType, doctype field, name field)
DYNAMIC = (
	("Life Ask Thread", "scope_doctype", "scope_name"), ("Life Idea", "source_doctype", "source_name"),
	("Life Idea", "brought_to_doctype", "brought_to_name"), ("Life Insight Evidence", "ref_doctype", "ref_name"),
	("Life Note Source", "source_doctype", "source_name"), ("Life Proposal", "created_doctype", "created_name"),
	("Life Wiki Change", "source_doctype", "source_name"),
)


def execute():
	if not frappe.db.table_exists("Life Project"):
		return
	frappe.reload_doc("life", "doctype", "life_goal")
	frappe.reload_doc("life", "doctype", "life_project")
	goal_of = make_goals()
	if not goal_of:
		return
	changed = set()
	changed |= serves_from_goal_project(goal_of)
	changed |= tasks(goal_of)
	changed |= renamed_links(goal_of)
	connections(goal_of)
	life_links(goal_of)
	dynamic_links(goal_of)
	proposals(goal_of)
	view_states(goal_of)
	reindex(changed)


def has(doctype, column):
	return frappe.db.table_exists(doctype) and frappe.db.has_column(doctype, column)


def make_goals():
	"""One open-ended goal per project. Returns {project name: goal name}."""
	goal_of = {}
	for p in frappe.get_all("Life Project", fields=["*"], order_by="creation asc", limit=100000):
		if p.migrated_to and frappe.db.exists("Life Goal", p.migrated_to):
			goal_of[p.name] = p.migrated_to
			continue
		outcome, on_hold, someday = STATUS.get(p.status or "Active", STATUS["Active"])
		closed = p.completed_on if outcome != "In Progress" else None
		if outcome != "In Progress" and not closed:
			closed = getdate(p.modified)
		g = frappe.get_doc({
			"doctype": "Life Goal", "space": p.space, "title": p.title, "goal_type": "Open", "area": p.area,
			"target_date": p.target_date, "done_when": p.outcome, "notes_md": p.notes_md, "outcome": outcome, "on_hold": on_hold,
			"is_someday": someday, "someday_on": p.someday_on if someday else None, "someday_review_on": p.someday_review_on if someday else None,
			"someday_note": p.someday_note if someday else None, "closed_on": closed,
		})
		g.flags.ignore_permissions = True
		g.flags.no_archive = True  # the project's own archive state is copied below, not recomputed
		g.flags.keep_touched = True
		g.insert()
		# the project's dates: created, last changed, completed, last activity, archived
		frappe.db.set_value("Life Goal", g.name, {
			"creation": p.creation, "modified": p.modified, "owner": p.owner, "modified_by": p.modified_by,
			"closed_on": closed, "completed_on": closed, "last_activity_on": p.last_activity_on,
			"is_archived": p.is_archived or 0, "archived_on": p.archived_on,
		}, update_modified=False)
		frappe.db.set_value("Life Project", p.name, "migrated_to", g.name, update_modified=False)
		goal_of[p.name] = g.name
	return goal_of


def serves_from_goal_project(goal_of):
	"""A goal that belonged to a project now serves the goal the project became."""
	if not has("Life Goal", "project"):
		return set()
	for name, project in frappe.db.sql("select name, project from `tabLife Goal` where ifnull(project, '') != '' and ifnull(serves, '') = ''"):
		target = goal_of.get(project)
		if target and target != name:
			frappe.db.set_value("Life Goal", name, "serves", target, update_modified=False)
	return set()


def tasks(goal_of):
	"""A task's project becomes its goal. A task that already had a goal keeps it; the project's goal is then the goal its
	goal serves (when that one serves nothing yet), or else a link between the task and the project's goal."""
	changed = set()
	if has("Life Task", "project"):
		rows = frappe.db.sql("select name, project, goal, space from `tabLife Task` where ifnull(project, '') != ''", as_dict=True)
		for t in rows:
			target = goal_of.get(t.project)
			if not target or t.goal == target:
				continue
			if not t.goal:
				frappe.db.set_value("Life Task", t.name, "goal", target, update_modified=False)
				changed.add(("Life Task", t.name))
				continue
			own = frappe.db.get_value("Life Goal", t.goal, ["serves", "space"], as_dict=True)
			if own and not own.serves and own.space == frappe.db.get_value("Life Goal", target, "space") and not _serves_chain(target, t.goal):
				frappe.db.set_value("Life Goal", t.goal, "serves", target, update_modified=False)
			elif own and own.serves != target:
				_link(t.space, "Life Task", t.name, "Life Goal", target)
	for name, project in frappe.db.sql("select name, someday_with from `tabLife Task` where ifnull(someday_with, '') != ''"):
		if project in goal_of:
			frappe.db.set_value("Life Task", name, "someday_with", goal_of[project], update_modified=False)
	return changed


def _serves_chain(start, goal):
	"""True when `start` already serves `goal`, directly or through others (setting the reverse would make a loop)."""
	seen, cur = set(), start
	while cur and cur not in seen:
		if cur == goal:
			return True
		seen.add(cur)
		cur = frappe.db.get_value("Life Goal", cur, "serves")
	return False


def _link(space, from_dt, from_name, to_dt, to_name):
	if frappe.db.exists("Life Link", {"from_doctype": from_dt, "from_name": from_name, "to_doctype": to_dt, "to_name": to_name}):
		return
	frappe.get_doc({"doctype": "Life Link", "space": space, "from_doctype": from_dt, "from_name": from_name, "to_doctype": to_dt,
		"to_name": to_name}).insert(ignore_permissions=True)


def renamed_links(goal_of):
	changed = set()
	for dt in RENAMED:
		if not has(dt, "project"):
			continue
		# nosemgrep: frappe-sql-format-injection -- `dt` comes from the constant RENAMED
		for name, project in frappe.db.sql(f"select name, project from `tab{dt}` where ifnull(project, '') != '' and ifnull(goal, '') = ''"):
			if project in goal_of:
				frappe.db.set_value(dt, name, "goal", goal_of[project], update_modified=False)
				changed.add((dt, name))
	return changed


def connections(goal_of):
	if not has("Life Connection", "default_project"):
		return
	for name, project in frappe.db.sql(
			"select name, default_project from `tabLife Connection` where ifnull(default_project, '') != '' and ifnull(default_goal, '') = ''"):
		if project in goal_of:
			frappe.db.set_value("Life Connection", name, "default_goal", goal_of[project], update_modified=False)


def life_links(goal_of):
	for end in ("from", "to"):
		rows = frappe.db.sql(f"select name, {end}_name from `tabLife Link` where {end}_doctype = 'Life Project'")  # nosemgrep: frappe-sql-format-injection -- `end` is "from" or "to"
		for name, project in rows:
			if project in goal_of:
				frappe.db.set_value("Life Link", name, {f"{end}_doctype": "Life Goal", f"{end}_name": goal_of[project]}, update_modified=False)


def dynamic_links(goal_of):
	for dt, dtfield, namefield in DYNAMIC:
		if not has(dt, dtfield):
			continue
		# nosemgrep: frappe-sql-format-injection -- DocType and field names come from the constant DYNAMIC
		rows = frappe.db.sql(f"select name, `{namefield}` from `tab{dt}` where `{dtfield}` = 'Life Project'")
		for name, project in rows:
			if project in goal_of:
				frappe.db.set_value(dt, name, {dtfield: "Life Goal", namefield: goal_of[project]}, update_modified=False)


def proposals(goal_of):
	"""Proposals not yet decided: a payload's project becomes its goal; a Someday proposal of a project parks its goal."""
	for name, payload in frappe.db.sql("select name, payload from `tabLife Proposal` where status = 'Pending' and payload like '%%roject%%'"):
		try:
			data = json.loads(payload or "{}")
		except ValueError:
			continue
		if not isinstance(data, dict):
			continue
		new = dict(data)
		if new.get("project"):
			project = new.pop("project")
			new.setdefault("goal", goal_of.get(project, project))
		if new.get("record_type") == "Project":
			new["record_type"] = "Goal"
			new["record"] = goal_of.get(new.get("record"), new.get("record"))
		if new != data:
			frappe.db.set_value("Life Proposal", name, "payload", json.dumps(new), update_modified=False)


def view_states(goal_of):
	"""Remembered list views: `project=` in a saved query becomes `goal=`, and a filter on project one on goal."""
	for name, state in frappe.db.sql("select name, state from `tabLife View State` where state like '%%project%%'"):
		try:
			data = json.loads(state or "{}")
		except ValueError:
			continue
		q = data.get("query") if isinstance(data, dict) else None
		if not isinstance(q, dict):
			continue
		new = dict(q)
		if "project" in new:
			value = new.pop("project")
			new.setdefault("goal", goal_of.get(value, value))
		if isinstance(new.get("f"), str) and "project" in new["f"]:
			try:
				conds = json.loads(new["f"])
				new["f"] = json.dumps([["goal", c[1], _map(c[2], goal_of)] if c and c[0] == "project" else c for c in conds])
			except (ValueError, TypeError, IndexError):
				pass
		if new != q:
			data["query"] = new
			frappe.db.set_value("Life View State", name, "state", json.dumps(data, separators=(",", ":")), update_modified=False)


def _map(value, goal_of):
	if isinstance(value, list):
		return [goal_of.get(v, v) for v in value]
	return goal_of.get(value, value)


def reindex(changed):
	from lifeos import index

	for dt, name in changed:
		if frappe.db.exists(dt, name) and dt in index.KINDS:
			index.update(frappe.get_doc(dt, name))
	# every row's goal column: rows written before set 6 had none
	frappe.db.sql("update `tabLife Index` set goal = '' where goal is null")
	for dt in index.KINDS:
		if dt == "Life Task" or has(dt, "goal"):
			# nosemgrep: frappe-sql-format-injection -- `dt` comes from index.KINDS, a constant
			frappe.db.sql(f"""update `tabLife Index` i join `tab{dt}` t on t.name = i.ref_name set i.goal = ifnull(t.goal, '')
				where i.ref_doctype = %s and ifnull(i.goal, '') != ifnull(t.goal, '')""", dt)
