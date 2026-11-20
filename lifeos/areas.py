"""The seven areas of life (issue 11). Every space has the same seven; any other area is a part of one of them, one level
deep. An area that is off is hidden with its parts and their goals and tasks, and the Brain does not file into it."""
import frappe
from frappe import _

# (name, one-line description, colour of its dot), in the order the pickers list them
LIFE_AREAS = [
	("Career", "Work, businesses, roles you hold", "blue"),
	("Health", "Body, fitness, sleep, food", "green"),
	("Relationships", "Family, friends, community", "red"),
	("Money", "Income, investments, taxes, legal", "orange"),
	("Emotions", "Mood, stress, practice", "amber"),
	("Mind", "Learning, reading, skills", "violet"),
	("Environment", "Home, places, things you own", "teal"),
]
NAMES = [a[0] for a in LIFE_AREAS]
ON_BY_DEFAULT = ("Career", "Health")
DEFAULT_PARENT = "Career"


def life_area_name(name):
	"""The canonical name if `name` is one of the seven (any case), else None."""
	key = str(name or "").strip().lower()
	return next((n for n in NAMES if n.lower() == key), None)


def ensure(space, on=ON_BY_DEFAULT):
	"""Create the seven in a space if they are missing, and return {name: row name}. An area already named like one of the
	seven at the top level is reused. `on` lists the ones switched on when created."""
	out = {}
	for i, (name, description, colour) in enumerate(LIFE_AREAS):
		existing = frappe.db.get_value("Life Area", {"space": space, "is_life_area": 1, "area_name": name})
		if not existing:
			existing = frappe.db.get_value("Life Area", {"space": space, "area_name": name, "parent_area": ("is", "not set")})
			if existing:
				frappe.db.set_value("Life Area", existing, {"is_life_area": 1, "description": description, "sort_order": i + 1,
					"is_archived": 0, "archived_on": None}, update_modified=False)
		if not existing:
			doc = frappe.get_doc({"doctype": "Life Area", "space": space, "area_name": name, "is_life_area": 1, "description": description,
				"colour": colour, "sort_order": i + 1, "is_on": 1 if name in on else 0, "is_pinned": 1 if name in on else 0})
			existing = doc.insert(ignore_permissions=True).name
		out[name] = existing
	return out


def life_areas(space):
	"""{name: row name} of the seven in a space."""
	return dict(frappe.get_all("Life Area", filters={"space": space, "is_life_area": 1}, fields=["area_name", "name"], as_list=True))


def off(space):
	"""Names of the areas of a space that are hidden: those switched off, and the parts of a life area that is off."""
	rows = frappe.get_all("Life Area", filters={"space": space}, fields=["name", "parent_area", "is_on"], limit=5000)
	hidden = {r.name for r in rows if not r.is_on}
	return sorted(hidden | {r.name for r in rows if r.parent_area in hidden})


def is_off(space, area):
	return bool(area) and area in off(space)


def off_clause(space, column, values, key="off_areas"):
	"""SQL that leaves out records filed under an area that is off: "" when every area is on, otherwise a condition that
	starts with " and ". `column` is fixed SQL from the caller; the names go in `values`."""
	names = off(space)
	if not names:
		return ""
	values[key] = names
	return f" and ifnull({column}, '') not in %({key})s"


def validate_area(doc):
	"""The rules of `Life Area`: the seven are fixed and sit at the top; any other area is a part of one of the seven in the
	same space, one level deep. Only a person switches an area on or off: the Brain files only into areas that are on."""
	from lifeos import permissions

	if not doc.is_new() and doc.has_value_changed("is_on") and permissions.is_agent():
		frappe.throw(_("Only a person can switch an area on or off."), frappe.PermissionError)
	if doc.is_life_area:
		if not doc.is_new() and doc.has_value_changed("area_name"):
			frappe.throw(_("The seven areas of life cannot be renamed."))
		if not life_area_name(doc.area_name):
			frappe.throw(_("Only Career, Health, Relationships, Money, Emotions, Mind and Environment are areas of life."))
		doc.area_name = life_area_name(doc.area_name)
		if doc.parent_area:
			frappe.throw(_("{0} is an area of life and cannot be a part of another area.").format(doc.area_name))
		return
	if not doc.parent_area:
		frappe.throw(_("{0} must be a part of one of the seven areas of life: Career, Health, Relationships, Money, Emotions, Mind or Environment.")
			.format(doc.area_name))
	parent = frappe.db.get_value("Life Area", doc.parent_area, ["space", "is_life_area", "area_name"], as_dict=True)
	if not parent or parent.space != doc.space:
		frappe.throw(_("The area {0} is not in this space.").format(doc.parent_area))
	if not parent.is_life_area:
		frappe.throw(_("{0} is a part, not an area of life. Parts sit only under Career, Health, Relationships, Money, Emotions, Mind or Environment, one level deep.")
			.format(parent.area_name))
	if frappe.db.exists("Life Area", {"parent_area": doc.name}) and not doc.is_new():
		frappe.throw(_("Parts are one level deep: {0} holds parts of its own.").format(doc.area_name))


FIELDS = ["name", "area_name", "parent_area", "is_life_area", "is_on", "description", "sort_order", "colour", "is_pinned", "is_archived"]


def ordered(space, include_off=False, include_archived=False, fields=FIELDS):
	"""The areas of a space in picker order: each of the seven, then its parts. Areas that are off (and the parts of an area
	that is off) are left out unless `include_off`."""
	filters = {"space": space}
	if not include_archived:
		filters["is_archived"] = 0
	rows = frappe.get_all("Life Area", filters=filters, fields=list(dict.fromkeys([*fields, "name", "parent_area", "is_life_area"])),
		order_by="sort_order asc, area_name asc", limit=5000)
	hidden = set() if include_off else set(off(space))
	rows = [r for r in rows if r.name not in hidden]
	parts = {}
	for r in rows:
		if r.parent_area:
			parts.setdefault(r.parent_area, []).append(r)
	out = []
	for r in rows:
		if not r.parent_area:
			out.append(r)
			out.extend(parts.pop(r.name, []))
	for rest in parts.values():  # parts whose area of life is archived or missing
		out.extend(rest)
	return out
