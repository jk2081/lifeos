"""The area tree (Settings > Areas and pickers). Area pages went in set 6: the lens shows an area on every place."""
import frappe

from lifeos.goals import areas as life_areas
from lifeos import permissions
from lifeos.api import tasks as task_api
from lifeos.api.utils import flag


def chat_open_counts(names):
	if not names:
		return {}
	return dict(frappe.db.sql(
		"select parent, count(*) from `tabLife Chat Open Item` where parenttype='Life Chat Log' and status='Open' and parent in %s group by parent",
		(names,)))


@frappe.whitelist(methods=["GET"])
def tree(space: str | None = None, include_archived: bool | int = 0, include_off: bool | int = 0):
	"""Every area of a space with its parent and small counts, for the Areas screen and for pickers: each of the seven areas of
	life followed by its parts (issue 11). Areas that are off, with their parts, are left out unless include_off=1."""
	space = permissions.resolve_space(space)
	areas = life_areas.ordered(space, include_off=flag(include_off), include_archived=flag(include_archived))
	# each number is counted the way the list it links to is filtered: the area with its sub-areas
	kids = {}
	for a in areas:
		kids.setdefault(a.parent_area, []).append(a.name)

	def below(name):
		out = [name]
		for k in kids.get(name, []):
			out.extend(below(k))
		return out

	direct_goals = dict(frappe.db.sql(
		"select area, count(*) from `tabLife Goal` where space=%s and outcome='In Progress' and is_someday=0 and is_archived=0 group by area", space))
	direct_notes = dict(frappe.db.sql("select area, count(*) from `tabLife Index` where space=%s and kind='Note' and is_archived=0 group by area", space))
	for a in areas:
		ids = below(a.name)
		a["open_tasks"] = task_api.count(space, area=a.name)
		a["goals"] = sum(direct_goals.get(i, 0) for i in ids)
		a["notes"] = sum(direct_notes.get(i, 0) for i in ids)
	return {"space": space, "areas": areas,
		"unfiled_tasks": task_api.count(space, area="none")}
