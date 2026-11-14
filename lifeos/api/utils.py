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
