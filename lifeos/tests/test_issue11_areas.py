"""Issue 11: the seven areas of life, with parts, switchable on and off."""
import frappe

from lifeos import areas, devtools, queries, seed
from lifeos.api import area as area_api
from lifeos.api import goals, inbox, meta, settings, tasks
from lifeos.patches.v11 import life_areas as patch
from lifeos.tests.base import AGENT, PRIVATE, LifeTestCase

NEW_SPACE, SEED_COPY = "I11 New Space", "I11 Seed Copy"
SEVEN = ["Career", "Health", "Relationships", "Money", "Emotions", "Mind", "Environment"]


class TestLifeAreas(LifeTestCase):
	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in (NEW_SPACE, SEED_COPY):
			devtools.purge_space(name, drop=True)
		frappe.db.commit()
		super().tearDownClass()

	def switch(self, area, on):
		settings.save_item("area", name=area, is_on=on)

	# 1
	def test_a_new_space_has_the_seven_with_career_and_health_on(self):
		frappe.set_user("Administrator")
		devtools.purge_space(NEW_SPACE, drop=True)
		frappe.set_user(devtools.OWNER)
		space = settings.create_space(NEW_SPACE)["name"]
		rows = frappe.get_all("Life Area", filters={"space": space}, fields=["area_name", "is_life_area", "is_on", "parent_area", "description"],
			order_by="sort_order")
		self.assertEqual([r.area_name for r in rows], SEVEN)
		self.assertTrue(all(r.is_life_area and not r.parent_area and r.description for r in rows))
		self.assertEqual([r.area_name for r in rows if r.is_on], ["Career", "Health"])
		self.assertEqual(rows[0].description, "Work, businesses, roles you hold")

	# 2
	def test_parts_sit_only_under_the_seven_one_level_deep(self):
		part = self.make("Life Area", area_name="i11 Business That Works", parent_area=self.life["Career"])
		self.assertEqual(part.parent_area, self.life["Career"])
		with self.assertRaisesRegex(frappe.ValidationError, "is a part, not an area of life"):
			self.make("Life Area", area_name="i11 Part of a part", parent_area=part.name)
		# an area outside the seven, as on a site before the change: nothing may be put under it
		old = frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "i11 Old top area"})
		old.db_insert()
		with self.assertRaisesRegex(frappe.ValidationError, "is a part, not an area of life"):
			self.make("Life Area", area_name="i11 Under the old area", parent_area=old.name)
		with self.assertRaisesRegex(frappe.ValidationError, "must be a part of one of the seven"):
			self.make("Life Area", area_name="i11 New top area")
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be renamed"):
			doc = frappe.get_doc("Life Area", self.life["Mind"])
			doc.area_name = "Brain"
			doc.save()
		with self.assertRaisesRegex(frappe.ValidationError, "Switch it off"):
			settings.save_item("area", name=self.life["Mind"], is_archived=1)
		# a part added in Settings with no area of life named goes under Career
		added = settings.save_item("area", space=PRIVATE, title="i11 Added in settings")
		self.assertEqual(frappe.db.get_value("Life Area", added["name"], "parent_area"), self.life["Career"])

	# 3
	def test_the_patch_turns_the_seed_areas_into_parts(self):
		frappe.set_user("Administrator")
		devtools.purge_space(SEED_COPY, drop=True)
		frappe.get_doc({"doctype": "Life Space", "space_name": SEED_COPY, "owner_user": devtools.OWNER,
			"members": [{"user": devtools.OWNER, "access": "Write"}]}).insert()
		frappe.db.delete("Life Area", {"space": SEED_COPY})  # as before the change: the seed's areas and no areas of life
		old = {}
		for i, name in enumerate([*seed.PRIVATE_AREAS, "Health", "i11 Unknown venture"]):
			doc = frappe.get_doc({"doctype": "Life Area", "space": SEED_COPY, "area_name": name, "sort_order": i + 1})
			doc.db_insert()
			old[name] = doc.name
		sub = frappe.get_doc({"doctype": "Life Area", "space": SEED_COPY, "area_name": "Ghatia", "parent_area": old["Tea & Coffee"]})
		sub.db_insert()
		old["Ghatia"] = sub.name
		filed = []
		for name, area in old.items():
			for doctype, extra in (("Life Task", {}), ("Life Goal", {"goal_type": "Open"}), ("Life Note", {})):
				doc = frappe.get_doc({"doctype": doctype, "space": SEED_COPY, "title": f"i11 {doctype} in {name}", "area": area, **extra})
				doc.insert()
				filed.append((doctype, doc.name, area))

		missed = patch.run([SEED_COPY])

		self.assertEqual(missed, {SEED_COPY: ["i11 Unknown venture"]})
		life = areas.life_areas(SEED_COPY)
		self.assertEqual(sorted(life), sorted(SEVEN))
		self.assertEqual(life["Health"], old["Health"])  # already one of the seven by name: reused
		expected = {"Business That Works": "Career", "Tea & Coffee": "Career", "Ghatia": "Career", "Family": "Relationships",
			"Money & Legal": "Money", "Personal": "Health", "Learning": "Mind", "Unstoppable & Content": "Emotions",
			"i11 Unknown venture": "Career"}
		for name, target in expected.items():
			self.assertEqual(frappe.db.get_value("Life Area", old[name], "parent_area"), life[target], name)
		for doctype, name, area in filed:
			self.assertEqual(frappe.db.get_value(doctype, name, "area"), area, f"{doctype} {name}")
		on = {n for n, row in life.items() if frappe.db.get_value("Life Area", row, "is_on")}
		self.assertEqual(on, {"Career", "Health", "Relationships", "Money", "Mind", "Emotions"})  # Environment got nothing
		self.assertEqual(patch.run([SEED_COPY]), {})  # a second run changes nothing

	# 4
	def test_an_area_that_is_off_is_hidden_and_comes_back(self):
		mind = self.life["Mind"]
		self.switch(mind, 1)
		books = self.make("Life Area", area_name="i11 Books", parent_area=mind).name
		task_mind = self.make("Life Task", title="i11 task in Mind", area=mind).name
		task_books = self.make("Life Task", title="i11 task in Books", area=books).name
		goal = goals.create("i11 goal in Mind", "Open", space=PRIVATE, area=mind)["name"]

		def visible():
			ctx = meta.space_context(PRIVATE)
			listed = {t["name"] for t in tasks.list(space=PRIVATE, page_length=100)["tasks"]}
			under_lens = {t["name"] for t in tasks.list(space=PRIVATE, area=mind, page_length=100)["tasks"]}
			return {
				"context": {mind, books} & {a["name"] for a in ctx["areas"]},
				"context goals": goal in {g["name"] for g in ctx["goals"]},
				"off": "Mind" in ctx["areas_off"],
				"tasks": {task_mind, task_books} & listed,
				"lens": {task_mind, task_books} & under_lens,
				"goals": goal in {g["name"] for g in goals.list(space=PRIVATE, page_length=100)["goals"]},
				"goal picker": goal in {g["name"] for g in goals.picker(space=PRIVATE)},
				"area picker": {mind, books} & {r[0] for r in queries.link_query("Life Area", "", "area_name", 0, 100, {"space": PRIVATE})},
				"tree": {mind, books} & {a["name"] for a in area_api.tree(space=PRIVATE)["areas"]},
			}

		shown = visible()
		self.assertEqual(shown, {"context": {mind, books}, "context goals": True, "off": False, "tasks": {task_mind, task_books},
			"lens": {task_mind, task_books}, "goals": True, "goal picker": True, "area picker": {mind, books}, "tree": {mind, books}})
		self.switch(mind, 0)
		self.assertEqual(visible(), {"context": set(), "context goals": False, "off": True, "tasks": set(), "lens": set(), "goals": False,
			"goal picker": False, "area picker": set(), "tree": set()})
		self.assertTrue(frappe.db.exists("Life Task", task_books))  # nothing is deleted
		self.switch(mind, 1)
		self.assertEqual(visible(), shown)
		self.switch(mind, 0)

	# 5
	def test_a_proposal_for_an_area_that_is_off_is_refused(self):
		frappe.db.sql("update `tabLife Inbox Item` set status='Done' where space=%s and status in ('New', 'Processing')", PRIVATE)
		env = self.life["Environment"]
		self.assertTrue(areas.is_off(PRIVATE, env))
		item = inbox.create_item(space=PRIVATE, title="i11 item")
		self.as_user(AGENT)
		self.assertEqual(inbox.claim_next(space=PRIVATE)["name"], item["name"])
		out = inbox.submit_result(item["name"], summary_md="i11", proposals=[
			{"kind": "Task", "payload": {"title": "i11 fix the roof", "area": "Environment"}},
			{"kind": "Task", "payload": {"title": "i11 call the bank", "area": "Money"}},
		])
		self.assertEqual([c["index"] for c in out["created"]], [1])
		self.assertEqual(len(out["errors"]), 1)
		self.assertIn("The area Environment is switched off", out["errors"][0]["error"])
		self.assertIn("Settings > Areas", out["errors"][0]["error"])
		# and the Brain cannot switch the area on to file there
		with self.assertRaisesRegex(frappe.PermissionError, "Only a person"):
			settings.save_item("area", name=env, is_on=1)
		self.assertTrue(areas.is_off(PRIVATE, env))
