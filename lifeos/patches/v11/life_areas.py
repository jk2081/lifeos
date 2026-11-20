"""Issue 11: every space gets the seven areas of life, and each area it already has becomes a part of one of them.

An area named like one of the seven is reused as that area. Every other area becomes a part, by the table below; a sub-area
the table does not know follows the area it sat under; anything else becomes a part of Career and is listed in the output.
Records keep pointing at the same area rows, so nothing is re-filed. Career and Health are on, and so is every area that
received a part, so nothing that was visible before disappears. A space that already has the seven and no other top-level
area is left alone, so this can run again."""
import frappe

from lifeos import areas

# an existing area's name (any case) -> the area of life it becomes a part of
MAPPING = {
	"business that works": "Career", "btw": "Career", "tea & coffee": "Career", "tea and coffee": "Career", "tea": "Career",
	"coffee": "Career", "cis board": "Career", "work": "Career", "business": "Career", "office": "Career", "jobs": "Career",
	"family": "Relationships", "friends": "Relationships", "community": "Relationships", "people": "Relationships",
	"money & legal": "Money", "money and legal": "Money", "legal": "Money", "finance": "Money", "investments": "Money",
	"taxes": "Money",
	"personal & health": "Health", "personal and health": "Health", "personal": "Health", "fitness": "Health",
	"sleep": "Health", "food": "Health", "golf": "Health",
	"learning": "Mind", "reading": "Mind", "skills": "Mind", "books": "Mind",
	"unstoppable & content": "Emotions", "unstoppable and content": "Emotions", "mood": "Emotions", "practice": "Emotions",
	"spiritual": "Emotions",
	"home": "Environment", "house": "Environment", "places": "Environment", "property": "Environment",
}


def life_area_for(name):
	"""The area of life an area of this name belongs under, or None when the table does not know it."""
	return areas.life_area_name(name) or MAPPING.get(str(name or "").strip().lower())


def execute():
	unknown = run()
	for space, names in unknown.items():
		print(f"Life areas: in {space}, put under Career because the mapping table does not know them: {', '.join(names)}")


def run(spaces=None):
	"""Apply the change to every space (or the ones named). Returns {space: [area names put under Career unknown]}."""
	unknown = {}
	for space in spaces or frappe.get_all("Life Space", pluck="name"):
		missed = convert_space(space)
		if missed:
			unknown[space] = missed
	areas.clear_cache()
	return unknown


def convert_space(space):
	rows = frappe.get_all("Life Area", filters={"space": space}, fields=["name", "area_name", "parent_area", "is_life_area"], limit=10000)
	have = {r.area_name for r in rows if r.is_life_area and not r.parent_area}
	if set(areas.NAMES) <= have and all(r.parent_area or r.is_life_area for r in rows):
		return []
	before = {r.name: r for r in rows}
	life = areas.ensure(space, on=())
	life_rows = set(life.values())
	used, missed = set(areas.ON_BY_DEFAULT), []
	used.update(n for n, row in life.items() if row in before)  # reused by name: it held records before
	for r in rows:
		if r.name in life_rows:
			continue
		target = target_of(r, before)
		if not target:
			target = areas.DEFAULT_PARENT
			missed.append(r.area_name)
		used.add(target)
		if r.parent_area != life[target]:
			frappe.db.set_value("Life Area", r.name, "parent_area", life[target], update_modified=False)
	for name, row in life.items():
		if name in used:
			frappe.db.set_value("Life Area", row, "is_on", 1, update_modified=False)
	return missed


def target_of(row, before):
	"""The area of life for an existing area: its own name in the table, else the nearest area above it that the table knows."""
	seen = set()
	while row and row.name not in seen:
		seen.add(row.name)
		target = life_area_for(row.area_name)
		if target:
			return target
		row = before.get(row.parent_area)
	return None
