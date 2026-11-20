"""Seed data from section 11 of the spec.

Load:    bench --site SITE execute lifeos.seed.load
Remove:  bench --site SITE execute lifeos.seed.remove

`load_demo` and `remove_demo` add and remove example records (ticks, tasks, chats, notes) used for
screenshots and manual testing. They are not part of the owner's seed.
"""
import json

import frappe
from frappe.utils import add_days, getdate, today

DIMENSIONS = ["Physical Health", "Emotions", "Mind", "Environment", "Money", "Relationships", "Career",
	"Community and Spiritual Development"]
PRIVATE_AREAS = ["Business That Works", "Family", "Learning", "Money & Legal", "Personal", "Tea & Coffee", "Unstoppable & Content"]
SHARED_AREAS = ["Work", "Personal & Health", "Money & Legal", "Family"]
HABITS = ["Japa", "Mala", "Journal", "Workout"]
CYCLE_TITLE = "Oct to Dec 2026"
CYCLE_START = "2026-10-05"  # first Monday of October 2026

# (goal, area, [actions]); an action ending in "*" is already done
GOALS = [
	("RMT: improve systems", "Tea & Coffee", ["Appoint ERP champion", "Start internal audit", "Start RMT newsletter", "Start training programme"]),
	("Close open loops", "Personal", ["Ruchi ITR", "Driver's licence", "Anya passport*", "Generic promotion [?]", "Investment OS first version", "Pay managers"]),
	("Golf: hit 5 birdies", "Personal", ["300-ball hitting practice with one club, 6 iron", "Practise 5-footers", "Get a small practice mat"]),
	("Money", "Money & Legal", ["Meet Arjun Singh for PMS", "Complete a usable MoneyOS"]),
	("RMT: GHL turnaround", "Tea & Coffee", ["Discuss going with Nowrojee", "Make a detailed plan for poor sections", "Visit leased gardens", "Start internal audit"]),
	("Get super-fit", "Personal", ["Drop fat", "Increase protein", "Burpees and workout", "Walking"]),
	("Mind and learning", "Learning", ["Agentic certification", "ERPNext certification", "Read three books [?]", "Accounting in ERPNext"]),
]

# (priority, goal, status, area)
OCTOBER = [
	("I", "Appoint internal auditor", "Carried", "Tea & Coffee"),
	("I", "Start RMT newsletter", "Carried", "Tea & Coffee"),
	("I", "Renew driving licence", "Carried", "Personal"),
	("I", "RMT estate training programme", "Carried", "Tea & Coffee"),
	("IV", "Ruchi ITR", "Open", "Money & Legal"),
	("IV", "Anya passport", "Done", "Family"),
	("I", "Sarjapur next step", "Done", "Money & Legal"),
	("I", "Complete agentic coding class", "Carried", "Learning"),
	("IV", "Accounts flow in ERP", "Open", "Tea & Coffee"),
	("I", "GHL deep review session", "Carried", "Tea & Coffee"),
	("I", "GHL poor performing sections", "Carried", "Tea & Coffee"),
	("I", "GHL outside garden plan", "Carried", "Tea & Coffee"),
	("I", "GHL visit", "Carried", "Tea & Coffee"),
	("IV", "Pay the managers cash bonus", "Open", "Tea & Coffee"),
]
MINDSWEEP = ["Trained manpower and a formal training programme", "Money visibility", "Raw Jute and EGIL", "Land monetisation", "RMT new crops"]

SEED_KEY = "lifeos_seed_records"
DEMO_KEY = "lifeos_demo_records"


# ---------- structure created at install ----------

def make_areas(space, names):
	"""The areas named, as parts of the seven areas of life (issue 11): a name that is one of the seven is that area; any other
	becomes a part of the area the patch's mapping table gives (Career when it does not know the name). The areas of life
	used are switched on, so what is filed there shows. Returns {name: area}."""
	from lifeos import areas
	from lifeos.patches.v11.life_areas import life_area_for

	life = areas.ensure(space)
	out = {}
	for i, name in enumerate(names):
		target = life_area_for(name) or areas.DEFAULT_PARENT
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
	areas.clear_cache()
	return out


def make_dimensions(space):
	for i, name in enumerate(DIMENSIONS):
		if not frappe.db.exists("Life Dimension", {"space": space, "dimension_name": name}):
			frappe.get_doc({"doctype": "Life Dimension", "space": space, "dimension_name": name, "sort_order": i + 1}).insert(ignore_permissions=True)


def ensure_structure():
	"""The seven areas of life and the check-in dimensions for the two starting spaces. The owner's own areas come with the
	seed, as parts (issue 11)."""
	from lifeos import areas

	for space in ("Private", "Shared"):
		if not frappe.db.exists("Life Space", space):
			continue
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


# ---------- the owner's seed ----------

def load(space="Private", key=SEED_KEY):
	"""Load the seed of section 11 into a space. Safe to run twice."""
	if json.loads(frappe.db.get_default(key) or "[]"):
		return "Seed is already loaded. Run lifeos.seed.remove first to reload it."
	ensure_structure()
	areas = make_areas(space, SHARED_AREAS if space == "Shared" else PRIVATE_AREAS)
	# the lens's defaults (set 6): a colour for every area and the top-level areas pinned, as the migration gives older sites
	from lifeos.patches.v7 import lens_areas

	lens_areas.execute()
	t = Tracker(key)

	habits = []
	for title in HABITS:
		name = frappe.db.get_value("Life Habit", {"space": space, "title": title})
		habits.append(name or t.insert({"doctype": "Life Habit", "space": space, "title": title}).name)

	cycle = t.insert({"doctype": "Life Cycle", "space": space, "title": CYCLE_TITLE, "start_date": CYCLE_START, "status": "Active"})
	for i, (title, area, actions) in enumerate(GOALS):
		rows = []
		for a in actions:
			done = a.endswith("*")
			rows.append({"title": a.rstrip("*"), "per_week": 1, "status": "Done" if done else "Open",
				"done_on": add_days(CYCLE_START, 14) if done else None})
		t.insert({"doctype": "Life Goal", "space": space, "cycle": cycle.name, "title": title, "area": areas.get(area),
			"sort_order": i + 1, "actions": rows})

	habit_rows = [{"habit": h, "days_per_week": 7, "sort_order": i + 1} for i, h in enumerate(habits)]
	t.insert({
		"doctype": "Life Month Plan", "space": space, "year": 2026, "month": 10,
		"goals": [{"priority": p, "title": g, "status": s, "area": areas.get(a)} for p, g, s, a in OCTOBER],
		"habits": [dict(r, tracked_from="2026-10-01") for r in habit_rows],
		"mindsweep_md": "\n\n".join(f"## {topic}" for topic in MINDSWEEP) + "\n",
	})
	t.insert({
		"doctype": "Life Month Plan", "space": space, "year": 2026, "month": 11,
		"habits": [dict(r, tracked_from="2026-11-01") for r in habit_rows],
	})
	t.save()
	return f"Seed loaded into {space}: {len(t.records)} records."


def remove(key=SEED_KEY):
	"""Remove what `load` created."""
	n = _remove(key)
	return f"Seed removed: {n} records."
