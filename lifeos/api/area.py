"""The area tree (Settings > Areas and pickers). Area pages went in set 6: the lens shows an area on every place."""
import frappe

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
def tree(space: str | None = None, include_archived: bool | int = 0):
	"""Every area of a space with its parent and small counts, for the Areas screen and for pickers."""
	space = permissions.resolve_space(space)
	filters = {"space": space}
	if not flag(include_archived):
		filters["is_archived"] = 0
	areas = frappe.get_all("Life Area", filters=filters, fields=["name", "area_name", "parent_area", "sort_order", "is_archived", "colour", "is_pinned"],
		order_by="sort_order asc, area_name asc", limit=1000)
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
		"tags": frappe.get_all("Life Tag", filters={"space": space, "is_archived": 0}, fields=["name", "tag_name"], order_by="tag_name", limit=500),
		"unfiled_tasks": task_api.count(space, area="none")}
