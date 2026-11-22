"""What a fresh site needs: the seven areas of life and the check-in dimensions, made for every space at install.

Nothing personal is loaded. Example records for screenshots and tests are in `lifeos/demo.py`.
`Tracker` and `_remove` keep a list of the records a demo load made, so it can take them out again.
"""
import json

import frappe

DIMENSIONS = ["Physical Health", "Emotions", "Mind", "Environment", "Money", "Relationships", "Career",
	"Community and Spiritual Development"]

DEMO_KEY = "lifeos_demo_records"


# ---------- structure created at install ----------

def make_areas(space, names, under=None):
	"""The areas named, as parts of the seven areas of life (issue 11): a name that is one of the seven is that area; any other
	becomes a part of Career, or of the area of life `under` gives for its name. The areas of life used are switched on, so what is filed there shows. Returns {name: area}."""
	from lifeos import areas

	life = areas.ensure(space)
	out = {}
	for i, name in enumerate(names):
		target = areas.life_area_name(name) or (under or {}).get(name) or areas.DEFAULT_PARENT
		if not frappe.db.get_value("Life Area", life[target], "is_on"):
			frappe.db.set_value("Life Area", life[target], "is_on", 1)
		if areas.life_area_name(name):
			out[name] = life[target]
			continue
		existing = frappe.db.get_value("Life Area", {"space": space, "area_name": name, "parent_area": life[target]})
		if not existing:
			existing = frappe.get_doc({"doctype": "Life Area", "space": space, "area_name": name, "parent_area": life[target],
				"sort_order": i + 1}).insert(ignore_permissions=True).name
		out[name] = existing
	return out


def make_dimensions(space):
	for i, name in enumerate(DIMENSIONS):
		if not frappe.db.exists("Life Dimension", {"space": space, "dimension_name": name}):
			frappe.get_doc({"doctype": "Life Dimension", "space": space, "dimension_name": name, "sort_order": i + 1}).insert(ignore_permissions=True)


def ensure_structure():
	"""The seven areas of life and the check-in dimensions for every space."""
	from lifeos import areas

	for space in frappe.get_all("Life Space", pluck="name"):
		areas.ensure(space)
		if not frappe.db.exists("Life Dimension", {"space": space}):
			make_dimensions(space)


# ---------- tracking what a seed created ----------

class Tracker:
	def __init__(self, key):
		self.key = key
		self.records = json.loads(frappe.db.get_default(key) or "[]")

	def insert(self, data, **flags):
		doc = frappe.get_doc(data)
		for k, v in flags.items():
			doc.flags[k] = v
		doc.insert(ignore_permissions=True)
		self.records.append([doc.doctype, doc.name])
		return doc

	def save(self):
		frappe.db.set_default(self.key, json.dumps(self.records))


def _remove(key):
	records = json.loads(frappe.db.get_default(key) or "[]")
	removed = 0
	for doctype, name in reversed(records):
		if frappe.db.exists(doctype, name):
			if doctype in ("Life Cycle", "Life Goal"):
				frappe.db.delete("Life Action Log", {"cycle" if doctype == "Life Cycle" else "goal": name})
			doc = frappe.get_doc(doctype, name)
			doc.flags.allow_closed = True
			try:
				doc.delete(ignore_permissions=True, force=True)
				removed += 1
			except frappe.LinkExistsError:
				frappe.clear_messages()
	frappe.db.set_default(key, "[]")
	return removed
