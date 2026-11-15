"""Small helpers shared by the API modules."""
import frappe
from frappe.utils import cint

MAX_PAGE = 100


def page(start=0, page_length=20):
	"""Clamp paging arguments. No list method returns more than 100 rows."""
	return max(cint(start), 0), min(max(cint(page_length) or 20, 1), MAX_PAGE)


def parse(value, default=None):
	"""Arguments arrive as JSON strings over HTTP and as objects over MCP."""
	if value is None or value == "":
		return default
	if isinstance(value, str):
		try:
			return frappe.parse_json(value)
		except ValueError:
			return value
	return value


def flag(value) -> bool:
	if isinstance(value, str):
		return value.strip().lower() in ("1", "true", "yes", "on")
	return bool(value)


def names_map(doctype, names, field):
	names = [n for n in set(names) if n]
	if not names:
		return {}
	return dict(frappe.get_all(doctype, filters={"name": ("in", names)}, fields=["name", field], as_list=True))


def user_names(users):
	users = [u for u in set(users) if u]
	if not users:
		return {}
	out = {}
	for name, first, full in frappe.get_all("User", filters={"name": ("in", users)}, fields=["name", "first_name", "full_name"], as_list=True):
		out[name] = first or full or name
	return out


def descendants(space, area):
	"""The area and every area below it."""
	rows = frappe.get_all("Life Area", filters={"space": space}, fields=["name", "parent_area"], limit=2000)
	children = {}
	for r in rows:
		children.setdefault(r.parent_area, []).append(r.name)
	out, stack = [], [area]
	while stack:
		cur = stack.pop()
		if cur in out:
			continue
		out.append(cur)
		stack.extend(children.get(cur, []))
	return out


def area_filter(space, area, column, values, also_in=None):
	"""SQL for an Area filter, the same on every list: the area with its sub-areas, or "none" for records with no area.
	`also_in` is the parenttype of a record that can also be filed under other areas."""
	if area == "none":
		return f"ifnull({column}, '') = ''"
	values["area_ids"] = descendants(space, area)
	sql = f"{column} in %(area_ids)s"
	if also_in:
		name = column.rsplit(".", 1)[0] + ".name" if "." in column else "name"
		sql = (f"({sql} or exists (select 1 from `tabLife Also In` ai where ai.parent = {name} "
			f"and ai.parenttype = '{also_in}' and ai.area in %(area_ids)s))")
	return sql


def order_by(sort, direction, allowed, default):
	"""An ORDER BY for a list. `allowed` maps the sort keys a caller may name to SQL, so nothing else reaches the query."""
	if not sort or sort not in allowed:
		return default
	way = "desc" if str(direction or "").lower() == "desc" else "asc"
	return ", ".join(f"{part.strip()} {way}" for part in allowed[sort].split(","))
