"""The seven areas of life (issue 11). Every space has the same seven; any other area is a part of one of them, one level
deep. An area that is off is hidden with its parts and their goals and tasks, and the Brain does not file into it."""
import frappe
from frappe import _

from lifeos.goals.focus_defaults import KINDS, offered

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
# the colours a dot can take; a new area gets the one its space has used least
COLOURS = ["blue", "green", "amber", "violet", "red", "teal", "orange", "pink", "cyan", "gray"]
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


def use_focuses():
	"""The setting "Use focuses" (issue 57): off for a new site. While off, no focus is offered, shown or required."""
	return bool(frappe.db.get_single_value("Life Settings", "use_focuses"))


def hidden_focuses(space):
	"""Names of the focuses of a space while "Use focuses" is off: existing focuses are hidden, not deleted."""
	if use_focuses():
		return []
	return frappe.get_all("Life Area", filters={"space": space, "is_focus": 1}, pluck="name", limit=5000)


def off(space):
	"""Names of the areas of a space that are hidden: those switched off, and everything below an area that is off (its parts,
	and their focuses). Focuses hidden by the setting are not here: their goals stay with their part (`hidden_focuses`)."""
	rows = frappe.get_all("Life Area", filters={"space": space}, fields=["name", "parent_area", "is_on"], limit=5000)
	hidden = {r.name for r in rows if not r.is_on}
	while True:  # a part of an area that is off, and a focus of a part that is off
		more = {r.name for r in rows if r.parent_area in hidden and r.name not in hidden}
		if not more:
			return sorted(hidden)
		hidden |= more


def is_off(space, area):
	return bool(area) and area in off(space)


def off_criterion(space, field):
	"""A pypika criterion that leaves out records filed under an area that is off (`field` is the record's area column), or None
	when every area is on."""
	names = off(space)
	return None if not names else frappe.query_builder.functions.IfNull(field, "").notin(names)


def validate_area(doc):
	"""The rules of `Life Area`: the seven are fixed and sit at the top; any other area is a part of one of the seven in the
	same space, one level deep. Only a person switches an area on or off: the Brain files only into areas that are on."""
	from lifeos import permissions

	check_focus_change(doc)
	if not doc.is_new() and doc.has_value_changed("is_on") and permissions.is_agent():
		frappe.throw(_("Only a person can switch an area on or off."), frappe.PermissionError, title=_("Only a person can switch areas"))
	if doc.is_life_area:
		if not doc.is_new() and doc.has_value_changed("area_name"):
			frappe.throw(_("The seven areas of life cannot be renamed."), title=_("Area of life cannot be renamed"))
		if not life_area_name(doc.area_name):
			frappe.throw(_("Only Career, Health, Relationships, Money, Emotions, Mind and Environment are areas of life."), title=_("Not an area of life"))
		doc.area_name = life_area_name(doc.area_name)
		if doc.parent_area:
			frappe.throw(_("{0} is an area of life and cannot be a part of another area.").format(doc.area_name), title=_("Area of life cannot be nested"))
		return
	if not doc.parent_area:
		frappe.throw(_("{0} must be a part of one of the seven areas of life: Career, Health, Relationships, Money, Emotions, Mind or Environment.")
			.format(doc.area_name), title=_("Part needs an area of life"))
	parent = frappe.db.get_value("Life Area", doc.parent_area, ["space", "is_life_area", "area_name", "is_focus", "parent_area"], as_dict=True)
	if not parent or parent.space != doc.space:
		frappe.throw(_("The area {0} is not in this space.").format(doc.parent_area), title=_("Area is in another space"))
	if parent.is_focus:
		frappe.throw(_("{0} is a focus. Nothing goes below a focus.").format(parent.area_name), title=_("Nothing goes below a focus"))
	if doc.is_focus:  # a focus sits under a part, or under an area of life where there are no parts
		if frappe.db.exists("Life Area", {"parent_area": doc.name}) and not doc.is_new():
			frappe.throw(_("Nothing goes below a focus: {0} holds areas of its own.").format(doc.area_name), title=_("Focus holds areas"))
		return
	if not parent.is_life_area:
		frappe.throw(_("{0} is a part, not an area of life. Parts sit only under Career, Health, Relationships, Money, Emotions, Mind or Environment, one level deep.")
			.format(parent.area_name), title=_("Part is under the wrong area"))
	if frappe.db.exists("Life Area", {"parent_area": doc.name, "is_focus": 0}) and not doc.is_new():
		frappe.throw(_("Parts are one level deep: {0} holds parts of its own.").format(doc.area_name), title=_("Parts are one level deep"))
	if doc.part_kind and doc.part_kind not in KINDS:
		frappe.throw(_("Unknown kind of part."), title=_("Unknown kind of part"))


def check_focus_change(doc):
	"""Only a person creates, changes or switches a focus (issue 57). The Brain may file under one and propose goals under it."""
	from lifeos import permissions

	before = doc.get_doc_before_save()
	if not permissions.is_agent() or not (doc.is_focus or (before and before.is_focus)):
		return
	watched = ("is_focus", "is_on", "area_name", "standard", "parent_area", "is_archived")
	if before is None or any(doc.has_value_changed(f) for f in watched) or [p.line for p in doc.principles] != [p.line for p in before.principles]:
		frappe.throw(_("Only a person can create, change or switch a focus."), frappe.PermissionError, title=_("Only a person can change a focus"))


FIELDS = ["name", "area_name", "parent_area", "is_life_area", "is_on", "description", "sort_order", "colour", "is_pinned", "is_archived",
	"is_focus", "part_kind"]


def ordered(space, include_off=False, include_archived=False, fields=FIELDS, focuses=None):
	"""The areas of a space in picker order: each of the seven, then its parts, each part followed by its focuses. Areas that are
	off (and what is below them) are left out unless `include_off`. Focuses are left out while "Use focuses" is off, unless
	`focuses=True`."""
	filters = {"space": space}
	if not include_archived:
		filters["is_archived"] = 0
	rows = frappe.get_all("Life Area", filters=filters, fields=list(dict.fromkeys([*fields, "name", "parent_area", "is_life_area"])),
		order_by="sort_order asc, area_name asc", limit=5000)
	hidden = set() if include_off else set(off(space))
	if not (use_focuses() if focuses is None else focuses):
		hidden |= set(hidden_focuses(space))
	rows = [r for r in rows if r.name not in hidden]
	kids = {}
	for r in rows:
		if r.parent_area:
			kids.setdefault(r.parent_area, []).append(r)
	out = []

	def add(r):
		out.append(r)
		for k in kids.pop(r.name, []):
			add(k)

	for r in rows:
		if not r.parent_area:
			add(r)
	for orphans in list(kids.values()):  # parts whose area of life is archived or missing
		for r in orphans:
			if all(r.name != x.name for x in out):
				add(r)
	return out


def add_offered_focuses(part, chosen=None):
	"""Create the focuses its kind offers under a part (issue 57), each with its suggested standard: those named in `chosen`, or
	all of them when `chosen` is None. A focus the part already has is left alone. Does nothing while "Use focuses" is off.
	Returns the names created."""
	row = frappe.db.get_value("Life Area", part, ["space", "part_kind", "sort_order"], as_dict=True)
	if not row or not use_focuses():
		return []
	have = {n.lower() for n in frappe.get_all("Life Area", filters={"parent_area": part}, pluck="area_name")}
	made = []
	for i, (name, standard) in enumerate(offered(row.part_kind)):
		if (chosen is not None and name not in chosen) or name.lower() in have:
			continue
		doc = frappe.get_doc({"doctype": "Life Area", "space": row.space, "area_name": name, "parent_area": part, "is_focus": 1,
			"standard": standard, "sort_order": i + 1})
		made.append(doc.insert().name)
	return made


# Issue 12: archiving a part with open work asks where that work goes
OPEN_TASK_STATUSES = ("Open", "Doing", "Waiting", "Someday")


def open_work(area):
	"""The open goals (in progress, not archived) and open tasks (not done, dropped or archived) filed under one area."""
	return {
		"goals": frappe.get_all("Life Goal", filters={"area": area, "outcome": "In Progress", "is_archived": 0}, pluck="name", limit=0),
		"tasks": frappe.get_all("Life Task", filters={"area": area, "status": ("in", OPEN_TASK_STATUSES), "is_archived": 0}, pluck="name", limit=0),
	}


def move_targets(area):
	"""Where the open work of a part can go: its own area of life first, then the other parts of that area that are not
	archived. [{name, area_name, is_life_area}]."""
	row = frappe.db.get_value("Life Area", area, ["space", "parent_area"], as_dict=True)
	if not row or not row.parent_area:
		return []
	life = frappe.db.get_value("Life Area", row.parent_area, ["name", "area_name", "is_life_area"], as_dict=True)
	parts = frappe.get_all("Life Area", filters={"parent_area": row.parent_area, "is_archived": 0, "name": ("!=", area)},
		fields=["name", "area_name", "is_life_area"], order_by="sort_order asc, area_name asc")
	return [life, *parts]


def move_work(area, to):
	"""Move the open goals and tasks of the part `area` to `to`: its own area of life or another of its parts that is not
	archived (see move_targets). Each record is saved as a document, so its index row and permissions follow. A part holds
	few open records, so one save each is fine. Returns the counts moved."""
	src = frappe.db.get_value("Life Area", area, ["space", "area_name", "parent_area"], as_dict=True)
	if to not in {t.name for t in move_targets(area)}:
		frappe.throw(_("Move the open goals and tasks of {0} to its area of life or to another of its parts.").format(src.area_name), title=_("Open work must move first"))
	dest = frappe.db.get_value("Life Area", to, ["area_name"], as_dict=True)
	if is_off(src.space, to):
		frappe.throw(_("{0} is switched off. Choose an area that is on.").format(dest.area_name), title=_("Target area is switched off"))
	work = open_work(area)
	for doctype, key in (("Life Goal", "goals"), ("Life Task", "tasks")):
		for name in work[key]:
			doc = frappe.get_doc(doctype, name)
			doc.area = to
			doc.flags.area_moved = True  # not a correction of a guessed area (issue 13)
			doc.save()
	return {"goals": len(work["goals"]), "tasks": len(work["tasks"])}


def goal_counts(space):
	"""{area: goals in progress filed there}, where each area also counts the goals of what is below it."""
	rows = frappe.get_all("Life Area", filters={"space": space}, fields=["name", "parent_area"], limit=0)
	parent = {r.name: r.parent_area for r in rows}
	out = {}
	for a, n in frappe.get_all("Life Goal", filters={"space": space, "outcome": "In Progress", "is_someday": 0, "is_archived": 0,
			"area": ("is", "set")}, fields=["area", {"COUNT": "*"}], group_by="area", as_list=True):
		while a:  # the area, then each area above it (a focus, its part, its area of life)
			out[a] = out.get(a, 0) + n
			a = parent.get(a)
	return out
