"""Issue 57: Focuses, an optional level under each part, with opinionated defaults, a standard, principles and annual goals."""
import frappe

from lifeos import areas, focus_defaults
from lifeos.api import focus, goals, inbox, settings
from lifeos.tests.base import AGENT, OWNER, PRIVATE, LifeTestCase


def use(on):
	frappe.db.set_single_value("Life Settings", "use_focuses", 1 if on else 0)


class TestFocuses(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		for name in frappe.get_all("Life Area", filters={"space": PRIVATE, "is_focus": 1}, pluck="name"):
			frappe.delete_doc("Life Area", name, force=True)
		use(True)
		self.tea = self.areas["Tea"]

	def tearDown(self):
		use(False)
		super().tearDown()

	def focus(self, name="Yield", parent=None, **kw):
		return frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": name, "parent_area": parent or self.tea, "is_focus": 1, **kw}).insert()

	def test_1_a_focus_sits_under_a_part_or_a_life_area_and_nothing_goes_below_it(self):
		under_part = self.focus("Yield")
		under_area = self.focus("Fitness", parent=self.life["Health"])
		self.assertTrue(under_part.is_focus and under_area.is_focus)
		with self.assertRaises(frappe.ValidationError):
			self.focus("Deeper", parent=under_part.name)
		with self.assertRaises(frappe.ValidationError):  # a part cannot go below a focus either
			frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Sub", "parent_area": under_part.name}).insert()
		part = frappe.get_doc("Life Area", self.tea)  # a part with focuses is still a valid part
		part.description = "still valid"
		part.save()

	def test_2_a_part_of_a_kind_offers_its_focuses(self):
		names = lambda kind: [f["name"] for f in settings.focus_offers(kind)]  # noqa: E731
		self.assertEqual(names("Company"), ["Review cadence", "Systems", "Marketing", "People", "Finance"])
		self.assertEqual(names("Estate"), ["Yield", "Quality", "People", "Systems"])
		self.assertEqual(names("Household"), ["Home", "Money admin", "Health admin"])
		self.assertEqual(names("Other"), [])
		self.assertTrue(all(st for _n, st in focus_defaults.offered("Company")))
		out = settings.save_item("area", space=PRIVATE, title="Acme", parent_area=self.life["Career"], part_kind="Company")
		self.assertEqual(len(out["focuses"]), 5)
		kids = frappe.get_all("Life Area", filters={"parent_area": out["name"]}, fields=["area_name", "is_focus", "standard"])
		self.assertEqual({k.area_name for k in kids}, set(names("Company")))
		self.assertTrue(all(k.is_focus and k.standard for k in kids))
		chosen = settings.save_item("area", space=PRIVATE, title="Estate Two", parent_area=self.life["Career"], part_kind="Estate", focuses=["Yield", "Quality"])
		self.assertEqual(len(chosen["focuses"]), 2)

	def test_3_with_use_focuses_off_no_focus_is_shown_or_required(self):
		f = self.focus("Yield")
		self.make("Life Goal", title="i57 under focus", horizon="Year", target_date="2027-03-01", area=f.name)
		self.assertIn(f.name, [a.name for a in areas.ordered(PRIVATE)])
		use(False)
		self.assertNotIn(f.name, [a.name for a in areas.ordered(PRIVATE)])
		self.assertNotIn(f.name, [a["name"] for a in inbox.space_context(PRIVATE)["areas"]])
		self.assertNotIn(f.name, [a["name"] for a in settings.get(space=PRIVATE)["areas"]])
		data = goals.by_area(space=PRIVATE, show="open")
		self.assertEqual(data["focus_count"], 0)
		part_group = next(g for s in data["sections"] for g in s["groups"] if g["area"] and g["area"]["name"] == self.tea)
		self.assertEqual([x["title"] for x in part_group["goals"]], ["i57 under focus"])  # the goal sits under its part
		self.assertEqual(part_group["focuses"], [])
		self.assertEqual(areas.add_offered_focuses(self.tea), [])
		use(True)
		self.assertEqual(goals.by_area(space=PRIVATE, show="open")["focus_count"], 1)

	def test_a_new_site_has_it_off(self):
		self.assertEqual(str(frappe.get_meta("Life Settings").get_field("use_focuses").default), "0")

	def test_by_area_puts_the_annual_goal_first_and_marks_a_focus_without_one(self):
		f = self.focus("Yield")
		self.make("Life Goal", title="i57 quarterly", horizon="Month", target_date="2026-11-30", area=f.name)
		data = goals.by_area(space=PRIVATE, show="open")
		entry = next(e for s in data["sections"] for g in s["groups"] for e in g["focuses"] if e["name"] == f.name)
		self.assertFalse(entry["has_annual"])
		self.make("Life Goal", title="i57 annual", horizon="Year", target_date="2027-03-01", area=f.name)
		data = goals.by_area(space=PRIVATE, show="open")
		entry = next(e for s in data["sections"] for g in s["groups"] for e in g["focuses"] if e["name"] == f.name)
		self.assertTrue(entry["has_annual"])
		self.assertEqual([g["title"] for g in entry["goals"]], ["i57 annual", "i57 quarterly"])

	def test_the_focus_page_has_the_standard_principles_and_goals_by_horizon(self):
		f = self.focus("Yield", standard="Above 1,700 kg/ha")
		settings.save_item("area", name=f.name, principles=["One system", "Fix the process first"])
		self.make("Life Goal", title="i57 annual", horizon="Year", target_date="2027-03-01", area=f.name)
		self.make("Life Goal", title="i57 old", horizon="Year", target_date="2026-03-01", area=f.name, outcome="Achieved")
		page = focus.get(f.name)
		self.assertEqual((page["standard"], page["principles"]), ("Above 1,700 kg/ha", ["One system", "Fix the process first"]))
		self.assertEqual([g["title"] for g in page["annual"]], ["i57 annual"])
		self.assertEqual([g["title"] for g in page["finished"]], ["i57 old"])
		self.assertTrue(page["has_annual"])
		settings.save_item("area", name=f.name, principles=["Fix the process first", "One system"])  # reordered
		self.assertEqual(focus.get(f.name)["principles"], ["Fix the process first", "One system"])
		self.assertEqual(focus.annual_for(f.name)["title"], "i57 annual")
		with self.assertRaises(frappe.ValidationError):
			focus.get(self.tea)

	def test_7_a_new_goal_cannot_be_open(self):
		frappe.flags.lifeos_allow_open_goals = False
		with self.assertRaises(frappe.ValidationError):
			goals.create(title="i57 open", horizon="Long term", space=PRIVATE)
		with self.assertRaises(frappe.ValidationError):  # no horizon and no date would be Open too
			goals.create(title="i57 open", space=PRIVATE)
		self.assertTrue(goals.create(title="i57 annual", horizon="Year", target_date="2027-03-01", space=PRIVATE)["name"])
		cycle = self.make("Life Cycle", title="i57 cycle", start_date="2026-11-02", end_date="2027-01-24", status="Active").name
		self.assertTrue(goals.create(title="i57 twelve", horizon="12 weeks", cycle=cycle, space=PRIVATE)["name"])
		year = goals.create(title="i57 to open", horizon="Year", target_date="2027-03-01", space=PRIVATE)["name"]
		with self.assertRaises(frappe.ValidationError):
			goals.update(year, {"horizon": "Long term"})

	def test_8_an_open_goal_is_marked_and_made_a_focus_with_an_annual_goal_holding_its_tasks(self):
		g = self.make("Life Goal", title="i57 RMT: improve systems", horizon="Long term", area=self.tea, done_when="Numbers by 9 am", notes_md="Ongoing work").name
		t = self.make("Life Task", title="i57 audit walk", goal=g, area=self.tea).name
		data = goals.by_area(space=PRIVATE, show="open")
		card = next(r for s in data["sections"] for grp in s["groups"] for r in grp["goals"] if r["name"] == g)
		self.assertEqual(card["to_sort"], 1)
		out = focus.sort_open(g, "focus", title="Systems on ERPNext", target_date="2027-03-31", done_when="All stores on ERPNext")
		self.assertEqual(frappe.db.get_value("Life Area", out["focus"], ["is_focus", "parent_area", "standard"]), (1, self.tea, "Numbers by 9 am"))
		annual = frappe.get_doc("Life Goal", out["annual"])
		self.assertEqual((annual.title, annual.horizon, annual.area), ("Systems on ERPNext", "Year", out["focus"]))
		self.assertEqual(frappe.db.get_value("Life Task", t, "goal"), annual.name)
		self.assertEqual(frappe.db.get_value("Life Goal", g, "outcome"), "Dropped")
		self.assertFalse(frappe.db.get_value("Life Task", t, "is_archived"))

	def test_an_open_goal_becomes_an_annual_goal_or_is_dropped(self):
		a = self.make("Life Goal", title="i57 a", horizon="Long term", area=self.tea).name
		b = self.make("Life Goal", title="i57 b", horizon="Long term", area=self.tea).name
		with self.assertRaises(frappe.ValidationError):
			focus.sort_open(a, "annual")
		focus.sort_open(a, "annual", target_date="2027-06-30")
		self.assertEqual(frappe.db.get_value("Life Goal", a, ["horizon", "target_date"], as_dict=True).horizon, "Year")
		focus.sort_open(b, "drop")
		self.assertEqual(frappe.db.get_value("Life Goal", b, "outcome"), "Dropped")

	def test_9_an_agent_cannot_create_or_switch_a_focus_but_can_file_under_one(self):
		f = self.focus("Yield")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Quality", "parent_area": self.tea, "is_focus": 1}).insert()
		doc = frappe.get_doc("Life Area", f.name)
		doc.standard = "changed"
		with self.assertRaises(frappe.PermissionError):
			doc.save()
		with self.assertRaises(frappe.PermissionError):
			settings.save_item("area", name=f.name, is_on=0)
		item = self.make("Life Task", title="i57 filed by the agent", area=f.name)
		self.assertEqual(item.area, f.name)

	def test_the_core_card_carries_each_focus_with_its_standard_and_principles(self):
		from lifeos import context

		self.focus("Yield", standard="Above 1,700 kg/ha")
		settings.save_item("area", name=frappe.db.get_value("Life Area", {"space": PRIVATE, "area_name": "Yield"}), principles=["One system"])
		card = context.card(PRIVATE, hidden=False)
		self.assertIn("Yield", card)
		self.assertIn("Above 1,700 kg/ha", card)
		self.assertIn("1. One system", card)
		use(False)
		context.changed()
		self.assertNotIn("Above 1,700 kg/ha", context.card(PRIVATE, hidden=False))
