"""Tests for settings."""
import inspect
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from lifeos.goals import areas, cycles as rules
from lifeos.tools import demo, devtools, seed
from lifeos.library import index
from lifeos import install, permissions
from lifeos.review import ladder
from lifeos.web import queries
from lifeos.api import area as area_api, goals, inbox, meta, onboarding, session, settings, tasks
from lifeos.constants import SPACE_DOCTYPES
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import item, task


class TestSkeleton(LifeTestCase):
	def test_app_is_installed(self):
		self.assertIn("lifeos", frappe.get_installed_apps())
		self.assertTrue(frappe.db.exists("Role", "Life Admin"))
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Event", "fieldname": "life_space"}))

	def test_life_route_rule(self):
		rules = frappe.get_hooks("website_route_rules")
		self.assertIn({"from_route": "/life/<path:app_path>", "to_route": "life"}, rules)

	def test_guest_is_redirected_to_login(self):
		from lifeos.www import life

		frappe.set_user("Guest")
		frappe.local.request = frappe._dict(path="/life")
		with self.assertRaises(frappe.Redirect):
			life.get_context(frappe._dict())
		self.assertIn("/login", frappe.local.flags.redirect_location)

	def test_guest_gets_nothing_from_the_api(self):
		from lifeos.api import session

		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, session.boot)

	def test_boot_lists_spaces(self):
		from lifeos.api import session
		from lifeos.tests.base import PRIVATE, SHARED

		names = [s["name"] for s in session.boot()["spaces"]]
		self.assertIn(PRIVATE, names)
		self.assertIn(SHARED, names)


def index_rows(doctype, name):
	return frappe.db.sql(
		"select kind, space, area, also_in_csv, goal, record_date, title, search_text, is_archived, status "
		"from `tabLife Index` where ref_doctype=%s and ref_name=%s order by kind", (doctype, name), as_dict=True)


class TestModel(LifeTestCase):
	def test_every_doctype_exists_and_is_named_life(self):
		for dt in [*SPACE_DOCTYPES, "Life Space", "Life Settings"]:
			self.assertTrue(frappe.db.exists("DocType", dt), dt)
			self.assertTrue(dt.startswith("Life "))
			self.assertEqual(frappe.get_meta(dt).module, "Life")
		for dt in SPACE_DOCTYPES:
			self.assertTrue(frappe.get_meta(dt).has_field("space"), dt)

	def test_settings_defaults(self):
		s = frappe.get_doc("Life Settings")
		self.assertEqual((s.score_target, s.archive_after_days, s.stale_task_days), (85, 90, 90))
		self.assertEqual(s.weekly_review_day, "Sunday")

	def test_database_indexes(self):
		keys = {r[2] for r in frappe.db.sql("show index from `tabLife Index`")}
		for key in ("life_index_space_date", "life_index_space_area", "life_index_space_goal", "life_index_fulltext"):
			self.assertIn(key, keys)
		link_keys = {r[2] for r in frappe.db.sql("show index from `tabLife Link`")}
		self.assertIn("life_link_from", link_keys)
		self.assertIn("life_link_to", link_keys)
		task_cols = {r[4] for r in frappe.db.sql("show index from `tabLife Task`")}
		self.assertTrue({"space", "status", "due_date"} <= task_cols)

	def test_task_done_sets_completed_on_and_waiting_needs_reason(self):
		task = self.make("Life Task", title="Call Vivek")
		task.status = "Waiting"
		self.assertRaises(frappe.MandatoryError, task.save)
		task.reload()
		task.status = "Waiting"
		task.waiting_on = "Vivek to send papers"
		task.save()
		task.status = "Done"
		task.save()
		self.assertEqual(str(task.completed_on), today())
		task.status = "Open"
		task.save()
		self.assertIsNone(task.completed_on)

	def test_vault_number_is_last_four_only(self):
		doc = frappe.get_doc({"doctype": "Life Vault Document", "space": PRIVATE, "title": "PAN card", "number_last4": "ABCDE1234F"})
		self.assertRaises(frappe.ValidationError, doc.insert)
		doc.number_last4 = "234F"
		doc.insert()
		doc.notes_md = "Account 123456789012"
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_habit_log_is_unique_per_day(self):
		habit = self.make("Life Habit", title="Japa test")
		self.make("Life Habit Log", habit=habit.name, date="2026-11-01")
		dup = frappe.get_doc({"doctype": "Life Habit Log", "space": PRIVATE, "habit": habit.name, "date": "2026-11-01"})
		self.assertRaises(frappe.DuplicateEntryError, dup.insert)
		self.make("Life Habit Log", habit=habit.name, date="2026-11-02")

	def test_cycle_end_date(self):
		cycle = self.make("Life Cycle", title="Test cycle", start_date="2026-10-05")
		self.assertEqual(str(cycle.end_date), "2026-12-27")



class TestAreasAndGoals(LifeTestCase):
	def test_area_from_another_space_is_refused(self):
		task = frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "Wrong area", "area": self.shared_areas["Family"]})
		self.assertRaises(frappe.ValidationError, task.insert)
		task = frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "Wrong also in", "area": self.areas["Tea"],
			"also_in": [{"area": self.shared_areas["Work"]}]})
		self.assertRaises(frappe.ValidationError, task.insert)

	def test_goal_of_a_record_may_sit_in_any_area_of_its_space(self):
		# set 6: projects became goals; a goal is not tied to the record's area (the old area check went with projects)
		goal = self.make("Life Goal", title="Ghillidary turnaround", horizon="Long term", area=self.areas["Tea"])
		ok = self.make("Life Task", title="In the goal's area", area=self.areas["Tea"], goal=goal.name)
		self.assertEqual(ok.goal, goal.name)
		elsewhere = self.make("Life Task", title="Elsewhere", area=self.areas["Personal"], goal=goal.name)
		self.assertEqual(elsewhere.goal, goal.name)
		other = frappe.get_doc({"doctype": "Life Task", "space": SHARED, "title": "Other space", "goal": goal.name})
		self.assertRaises(frappe.ValidationError, other.insert)

	def test_area_names_are_unique_per_space(self):
		dup = frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Tea", "parent_area": self.life["Career"]})
		self.assertRaises(frappe.DuplicateEntryError, dup.insert)
		self.make("Life Area", area_name="Tea", parent_area=self.life["Health"])  # the same name under another area of life
		self.make("Life Area", space=SHARED, area_name="Tea", parent_area=self.shared_life["Career"])


class TestIndex(LifeTestCase):
	def test_saving_writes_one_row(self):
		note = self.make("Life Note", title="Estate training outline", content_md="Trained manpower plan",
			area=self.areas["Tea"], also_in=[{"area": self.areas["Money"]}])
		rows = index_rows("Life Note", note.name)
		self.assertEqual(len(rows), 1)
		r = rows[0]
		self.assertEqual((r.kind, r.space, r.area, r.title), ("Note", PRIVATE, self.areas["Tea"], "Estate training outline"))
		self.assertEqual(r.also_in_csv, f",{self.areas['Money']},")
		self.assertIn("Trained manpower", r.search_text)
		note.title = "Renamed outline"
		note.save()
		self.assertEqual(index_rows("Life Note", note.name)[0].title, "Renamed outline")

	def test_every_filed_doctype_is_indexed(self):
		made = [
			self.make("Life Inbox Item", title="Voice note", raw_text="call the auditor"),
			self.make("Life Task", title="Indexed task"),
			self.make("Life Note", title="Indexed note"),
			self.make("Life Vault Document", title="Passport"),
			self.make("Life Chat Log", title="Mandir planning", date=today(), open_items=[{"text": "Decide the deity"}]),
			self.make("Life Note", title="Journal page 187", page_date="2026-11-14", content_md="Goal Oct to Dec"),
		]
		for doc in made:
			rows = index_rows(doc.doctype, doc.name)
			self.assertEqual(len(rows), 1, doc.doctype)
			self.assertEqual(rows[0].space, PRIVATE)
		self.assertEqual(index_rows("Life Chat Log", made[4].name)[0].status, "Open")
		self.assertEqual(str(index_rows("Life Note", made[5].name)[0].record_date), "2026-11-14")  # a journal page is dated the day it was written

	def test_done_task_gets_a_second_dated_row(self):
		task = self.make("Life Task", title="Finish me")
		self.assertEqual([r.kind for r in index_rows("Life Task", task.name)], ["Task"])
		task.status = "Done"
		task.save()
		self.assertEqual([r.kind for r in index_rows("Life Task", task.name)], ["Task", "Task Done"])
		task.status = "Open"
		task.save()
		self.assertEqual([r.kind for r in index_rows("Life Task", task.name)], ["Task"])

	def test_archiving_and_deleting_update_the_row(self):
		note = self.make("Life Note", title="To archive")
		note.is_archived = 1
		note.save()
		self.assertEqual(index_rows("Life Note", note.name)[0].is_archived, 1)
		self.assertEqual(str(note.archived_on), today())
		note.is_archived = 0
		note.save()
		self.assertEqual(index_rows("Life Note", note.name)[0].is_archived, 0)
		note.delete()
		self.assertEqual(index_rows("Life Note", note.name), [])

	def test_rebuild_produces_the_same_rows(self):
		self.make("Life Note", title="Rebuild note", content_md="alpha", area=self.areas["Tea"])
		done = self.make("Life Task", title="Rebuild task")
		done.status = "Done"
		done.save()
		self.make("Life Chat Log", title="Rebuild chat", date=add_days(today(), -3))
		query = ("select name, ref_doctype, ref_name, space, area, also_in_csv, goal, record_date, title, "
			"search_text, is_archived, kind, status, record_owner from `tabLife Index` order by name")
		before = frappe.db.sql(query)
		self.assertTrue(before)
		frappe.set_user("Administrator")
		index.rebuild()
		self.assertEqual(before, frappe.db.sql(query))


class TestSeed(LifeTestCase):
	def test_structure_is_created_at_install(self):
		# issue 11: every space has the seven areas of life at the top; the owner's own areas come with the seed, as parts.
		# issue 46: a new site has one space (Private); Shared exists only where setup_users made it
		self.assertTrue(frappe.db.exists("Life Space", "Private"))
		for space in frappe.get_all("Life Space", filters={"name": ("in", ("Private", "Shared"))}, pluck="name"):
			top = frappe.get_all("Life Area", filters={"space": space, "parent_area": ("is", "not set")}, pluck="area_name", order_by="sort_order")
			self.assertEqual(top, ["Career", "Health", "Relationships", "Money", "Emotions", "Mind", "Environment"])

	def test_the_demo_cycle_loads_and_removes(self):
		from unittest.mock import patch

		from lifeos.tools import demo

		frappe.set_user("Administrator")
		key = "lifeos_seed_test"
		with patch.object(seed, "DEMO_KEY", key):
			seed._remove(key)
			demo.load_cycle(PRIVATE)
			cycle = frappe.get_doc("Life Cycle", {"space": PRIVATE, "title": demo.CYCLE_TITLE})
			self.assertEqual((str(cycle.start_date), str(cycle.end_date), cycle.status), ("2026-10-05", "2026-12-27", "Active"))
			goals = frappe.get_all("Life Goal", filters={"cycle": cycle.name}, fields=["name", "title", "area"], order_by="sort_order")
			self.assertEqual([g.title for g in goals], [g[0] for g in demo.GOALS])
			self.assertEqual([a.status for a in frappe.get_doc("Life Goal", goals[1].name).actions if a.title == "Book the passport photo"], ["Done"])
			self.assertEqual(len(rules.month_goals(PRIVATE, 2026, 10)), len(demo.OCTOBER))
			self.assertEqual(frappe.get_all("Life Habit", filters={"space": PRIVATE, "tracked_from": ("is", "set")}, pluck="title", order_by="sort_order"), demo.HABITS)
			seed._remove(key)
			self.assertFalse(frappe.db.exists("Life Cycle", cycle.name))
			self.assertEqual(frappe.db.count("Life Habit", {"space": PRIVATE, "title": ("in", demo.HABITS)}), 0)


NEW_SPACE = "I11 New Space"


SEVEN = ["Career", "Health", "Relationships", "Money", "Emotions", "Mind", "Environment"]


class TestLifeAreas(LifeTestCase):
	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in (NEW_SPACE,):
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

	# 4
	def test_an_area_that_is_off_is_hidden_and_comes_back(self):
		mind = self.life["Mind"]
		self.switch(mind, 1)
		books = self.make("Life Area", area_name="i11 Books", parent_area=mind).name
		task_mind = self.make("Life Task", title="i11 task in Mind", area=mind).name
		task_books = self.make("Life Task", title="i11 task in Books", area=books).name
		goal = goals.create("i11 goal in Mind", "Long term", space=PRIVATE, area=mind)["name"]

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


class TestSettingsAreas(LifeTestCase):
	def context_areas(self, space=PRIVATE):
		return {a["name"] for a in meta.space_context(space)["areas"]}

	def row(self, name, space=PRIVATE):
		return next(a for a in settings.get(space)["areas"] if a.name == name)

	# 1
	def test_switching_money_on_and_off_shows_and_hides_it_and_its_goals(self):
		money = self.life["Money"]
		settings.save_item("area", name=money, is_on=0)
		goal = goals.create("i12 goal in Money", "Long term", space=PRIVATE, area=money)["name"]
		self.assertNotIn(money, self.context_areas())
		settings.save_item("area", name=money, is_on=1)
		self.assertIn(money, self.context_areas())
		self.assertIn(goal, {g["name"] for g in goals.list(space=PRIVATE, page_length=100)["goals"]})
		self.assertGreaterEqual(self.row(money)["goals"], 1)
		settings.save_item("area", name=money, is_on=0)
		self.assertNotIn(money, self.context_areas())
		self.assertNotIn(goal, {g["name"] for g in goals.list(space=PRIVATE, page_length=100)["goals"]})
		self.assertTrue(frappe.db.exists("Life Goal", goal))  # nothing is deleted
		settings.save_item("area", name=money, is_on=1)
		self.assertIn(goal, {g["name"] for g in goals.list(space=PRIVATE, page_length=100)["goals"]})

	# 2
	def test_adding_a_part_under_career_lists_it_with_its_description_and_colour(self):
		career = self.life["Career"]
		part = settings.save_item("area", space=PRIVATE, title="i12 CIS Board", parent_area=career, description="Vice Chair",
			colour="violet")["name"]
		row = self.row(part)
		self.assertEqual((row.parent_area, row.description, row.colour, row["goals"]), (career, "Vice Chair", "violet", 0))
		self.assertIn(part, self.context_areas())
		goals.create("i12 board goal", "Long term", space=PRIVATE, area=part)
		self.assertEqual(self.row(part)["goals"], 1)
		self.assertGreaterEqual(self.row(career)["goals"], 1)  # an area of life counts the goals of its parts

	# 3
	def test_archiving_a_part_with_open_work_asks_where_and_moves_it(self):
		career = self.life["Career"]
		part = settings.save_item("area", space=PRIVATE, title="i12 part to archive", parent_area=career)["name"]
		other = settings.save_item("area", space=PRIVATE, title="i12 other part", parent_area=career)["name"]
		open_task = self.make("Life Task", title="i12 open task", area=part).name
		done_task = self.make("Life Task", title="i12 done task", area=part, status="Done").name
		goal = goals.create("i12 goal in the part", "Long term", space=PRIVATE, area=part)["name"]
		work = settings.area_open_work(part)
		self.assertEqual((work["goals"], work["tasks"]), (1, 1))
		self.assertEqual([t.name for t in work["targets"]][0], career)
		self.assertIn(other, [t.name for t in work["targets"]])
		self.assertNotIn(part, [t.name for t in work["targets"]])
		with self.assertRaisesRegex(frappe.ValidationError, "Choose where to move them"):
			settings.save_item("area", name=part, is_archived=1)
		self.assertEqual(frappe.db.get_value("Life Area", part, "is_archived"), 0)
		for wrong in (part, self.life["Health"], self.areas["Personal"]):  # not to itself, nor outside Career
			with self.assertRaises(frappe.ValidationError):
				settings.save_item("area", name=part, is_archived=1, move_to=wrong)
		settings.save_item("area", name=part, is_archived=1, move_to=other)
		self.assertEqual(frappe.db.get_value("Life Area", part, "is_archived"), 1)
		self.assertEqual(frappe.db.get_value("Life Task", open_task, "area"), other)
		self.assertEqual(frappe.db.get_value("Life Goal", goal, "area"), other)
		self.assertEqual(frappe.db.get_value("Life Task", done_task, "area"), part)  # closed work stays where it was
		self.assertIn(open_task, {t["name"] for t in tasks.list(space=PRIVATE, area=other, page_length=100)["tasks"]})
		# to the area of life itself
		settings.save_item("area", name=other, is_archived=1, move_to=career)
		self.assertEqual(frappe.db.get_value("Life Task", open_task, "area"), career)

	# 4
	def test_only_life_admin_changes_areas(self):
		work = self.shared_life["Career"]
		self.as_user(FAMILY)
		got = settings.get(SHARED)
		self.assertFalse(got["is_admin"])
		self.assertTrue(any(a.is_life_area for a in got["areas"]))  # the screen still reads
		for call in (lambda: settings.save_item("area", name=work, is_on=0), lambda: settings.save_item("area", name=work, description="x"),
				lambda: settings.save_item("area", space=SHARED, title="i12 family part", parent_area=work),
				lambda: settings.reorder("area", frappe.as_json([work])), lambda: settings.area_open_work(work)):
			self.assertRaises(frappe.PermissionError, call)
		self.assertEqual(frappe.db.get_value("Life Area", work, "is_on"), 1)
		self.as_user(AGENT)
		with self.assertRaisesRegex(frappe.PermissionError, "Only a person"):
			settings.save_item("area", name=work, is_on=0)

	def test_goal_counts_leave_out_closed_and_someday_goals(self):
		mind = self.life["Mind"]
		settings.save_item("area", name=mind, is_on=1)
		before = areas.goal_counts(PRIVATE).get(mind, 0)
		goals.create("i12 counted", "Long term", space=PRIVATE, area=mind)
		closed = goals.create("i12 achieved", "Long term", space=PRIVATE, area=mind)["name"]
		frappe.db.set_value("Life Goal", closed, "outcome", "Achieved")
		self.assertEqual(areas.goal_counts(PRIVATE).get(mind, 0), before + 1)
		settings.save_item("area", name=mind, is_on=0)


class TestSettings(LifeTestCase):
	def test_rhythms_save_and_read_back(self):
		before = settings.get(space=PRIVATE)["settings"]
		try:
			settings.save({"start_of_day": "05:30:00", "week_starts_on": "Sunday", "cycle_break_week": 0, "weekly_review_day": "Saturday"})
			s = settings.get(space=PRIVATE)["settings"]
			self.assertEqual((s["start_of_day"][:5], s["week_starts_on"], s["cycle_break_week"], s["weekly_review_day"]),
				("05:30", "Sunday", 0, "Saturday"))
		finally:
			settings.save({k: before[k] for k in ("start_of_day", "week_starts_on", "cycle_break_week", "weekly_review_day") if before[k] is not None})

	def test_area_pin_and_colour(self):
		a = self.areas["Tea"]
		settings.save_item("area", name=a, colour="violet", is_pinned=1)
		self.assertEqual(frappe.db.get_value("Life Area", a, ["colour", "is_pinned"]), ("violet", 1))
		settings.save_item("area", name=a, is_pinned=0)
		self.assertEqual(frappe.db.get_value("Life Area", a, "is_pinned"), 0)
		row = next(r for r in settings.get(space=PRIVATE)["areas"] if r.name == a)
		self.assertEqual(row.colour, "violet")

	def test_backups_report_what_the_site_says(self):
		b = settings.get(space=PRIVATE)["backups"]
		self.assertIn("configured", b)
		self.assertFalse(set(b["settings"]) - set(settings.BACKUP_KEYS))


NEW = "i49-owner@lifeos.test"


FRESH = "I49 fresh"


def _drop():
	frappe.set_user("Administrator")
	from lifeos.tools import devtools

	devtools.purge_space(FRESH, drop=True)
	frappe.db.delete("DefaultValue", {"parent": NEW})
	if frappe.db.exists("User", NEW):
		frappe.delete_doc("User", NEW, force=1, ignore_permissions=True)
	permissions.clear_cache()


class TestFirstRun(LifeTestCase):
	def setUp(self):
		_drop()

	def tearDown(self):
		_drop()

	def test_fresh_install_has_one_space_seven_areas_and_no_seed_data(self):

		self.assertEqual(install.STARTING_SPACES, ("Private",))
		source = inspect.getsource(install.after_install) + inspect.getsource(install.setup) + inspect.getsource(install.make_spaces)
		self.assertNotIn("demo.load", source)
		self.assertNotIn("load_cycle", source)
		counts = {dt: frappe.db.count(dt) for dt in ("Life Task", "Life Goal", "Life Inbox Item", "Life Cycle")}
		with patch.object(demo, "load") as d:
			install.setup()
		d.assert_not_called()
		self.assertEqual(counts, {dt: frappe.db.count(dt) for dt in counts})
		# a new space, as install makes Private: the seven areas, Career and Health on, nothing else
		frappe.get_doc({"doctype": "Life Space", "space_name": FRESH, "owner_user": OWNER, "members": [{"user": OWNER, "access": "Write"}]}).insert()
		rows = frappe.get_all("Life Area", filters={"space": FRESH}, fields=["area_name", "is_on", "is_life_area"])
		self.assertEqual(sorted(r.area_name for r in rows), sorted(areas.NAMES))
		self.assertEqual({r.area_name for r in rows if r.is_on}, {"Career", "Health"})
		for dt in ("Life Task", "Life Goal", "Life Inbox Item", "Life Cycle", "Life Note"):
			self.assertEqual(frappe.db.count(dt, {"space": FRESH}), 0, dt)

	def test_new_owner_makes_a_life_admin_who_owns_the_space_and_sets_no_password(self):

		frappe.get_doc({"doctype": "Life Space", "space_name": FRESH, "owner_user": "Administrator"}).insert()
		with patch.object(frappe.db, "commit"):
			out = install.new_owner(NEW, "Asha Rao", send_welcome_email=0, space=FRESH)
		self.assertEqual(out, {"user": NEW, "space": FRESH})
		self.assertTrue({"Life Admin", "Life User"} <= set(frappe.get_roles(NEW)))
		self.assertEqual(frappe.db.get_value("Life Space", FRESH, "owner_user"), NEW)
		self.assertEqual(permissions.user_spaces(NEW).get(FRESH), "Write")
		self.assertEqual(frappe.db.get_value("User", NEW, ["first_name", "last_name"]), ("Asha", "Rao"))
		self.assertFalse(frappe.db.sql("select 1 from __Auth where doctype='User' and name=%s and fieldname='password'", NEW))
		with patch.object(frappe.db, "commit"):
			install.new_owner(NEW, "Asha Rao", send_welcome_email=0, space=FRESH)  # a second run changes nothing
		self.assertEqual(len([m for m in frappe.get_doc("Life Space", FRESH).members if m.user == NEW]), 1)

	def test_the_guide_shows_once_to_an_owner_of_an_empty_site(self):
		frappe.get_doc({"doctype": "Life Space", "space_name": FRESH, "owner_user": "Administrator"}).insert()
		with patch.object(frappe.db, "commit"):
			install.new_owner(NEW, "Asha Rao", send_welcome_email=0, space=FRESH)
		permissions.clear_cache()
		frappe.set_user(NEW)
		self.assertTrue(onboarding.state()["show"])
		self.assertEqual(onboarding.complete("skipped")["status"], "skipped")
		self.assertFalse(onboarding.state()["show"])
		with self.assertRaises(frappe.PermissionError):
			onboarding.reset()
		frappe.set_user("Administrator")
		onboarding.reset(NEW)
		frappe.set_user(NEW)
		self.assertTrue(onboarding.state()["show"])
		# the first things become tasks with an area each; once there are tasks the guide is not offered again
		things = onboarding.add_first_things(["Book the dentist", "Pay the electricity bill", "Plan a run", "A fourth thing"], space=FRESH)
		self.assertEqual(len(things), 3)
		self.assertTrue(all(t["area"] for t in things))
		self.assertFalse(onboarding.state()["show"])

	def test_you_step_sets_the_name_and_time_zone(self):
		frappe.get_doc({"doctype": "Life Space", "space_name": FRESH, "owner_user": "Administrator"}).insert()
		with patch.object(frappe.db, "commit"):
			install.new_owner(NEW, "Asha Rao", send_welcome_email=0, space=FRESH)
		permissions.clear_cache()
		was = frappe.db.get_single_value("System Settings", "time_zone")
		frappe.set_user(NEW)
		with self.assertRaises(frappe.ValidationError):
			onboarding.save_you("Asha Rao", "Not/AZone")
		out = onboarding.save_you("  Asha  K Rao ", "Asia/Kolkata")
		self.assertEqual(out["full_name"], "Asha K Rao")
		self.assertEqual(out["time_zone"], "Asia/Kolkata")
		frappe.set_user("Administrator")
		frappe.db.set_single_value("System Settings", "time_zone", was)

	def test_an_agent_and_a_family_user_never_get_the_guide(self):
		self.as_user(OWNER)
		self.make("Life Task", title="I49 a record, so the site is not empty")
		self.assertFalse(onboarding.state()["show"])  # the owner's spaces have records
		# a fresh site has no records, so the owner's spaces are empty and only the owner is shown the guide
		with patch.object(onboarding, "is_empty", return_value=True):
			self.assertTrue(onboarding.state()["show"])
			for user in (AGENT, FAMILY):
				self.as_user(user)
				self.assertFalse(onboarding.state()["show"], user)


ANYA = "anya26@lifeos.test"


HER = "Anya's space"


class TestLadder(LifeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		devtools.make_user(ANYA, "Anya", ["Life User"])
		devtools.purge_space(HER, drop=True)
		frappe.get_doc({"doctype": "Life Space", "space_name": HER, "owner_user": ANYA,
			"members": [{"user": ANYA, "access": "Write"}]}).insert(ignore_permissions=True)

	def setUp(self):
		super().setUp()
		self.as_user("Administrator")
		for dt in ("Life Task", "Life Inbox Item", "Life Goal", "Life Review"):
			frappe.db.delete(dt, {"space": HER} if dt != "Life Review" else {"user": ANYA})
		frappe.db.delete("Life Space Member", {"parent": HER, "user": ("!=", ANYA)})
		frappe.db.set_value("Life Area", {"space": HER}, "is_on", 0)
		frappe.defaults.clear_default(ladder.DISMISSED_KEY, parent=ANYA)
		ladder.forget(ANYA)

	def level(self):
		ladder.forget(ANYA)
		self.as_user(ANYA)
		out = meta.setup_level()
		self.as_user("Administrator")
		return out

	def mk(self, doctype, **v):
		return frappe.get_doc({"doctype": doctype, "space": HER, **v}).insert(ignore_permissions=True)

	def areas_on(self, n):
		names = frappe.get_all("Life Area", filters={"space": HER, "is_life_area": 1}, pluck="name", limit=n)
		for a in names:
			frappe.db.set_value("Life Area", a, "is_on", 1)
		self.assertEqual(len(names), n)

	def test_1_each_step_moves_the_level_up_by_one(self):
		self.assertEqual(self.level()["level"], 1)
		self.mk("Life Task", title="i26 task")
		self.assertEqual(self.level()["level"], 1)
		self.mk("Life Inbox Item", title="i26 mail", source_type="Email", source_system="gmail")
		self.assertEqual(self.level()["level"], 2)
		self.areas_on(3)
		self.assertEqual(self.level()["level"], 2)  # three areas but no goal yet
		self.mk("Life Goal", title="i26 goal", horizon="Year", target_date="2027-12-31", area=frappe.db.get_value("Life Area", {"space": HER, "is_on": 1}))
		self.assertEqual(self.level()["level"], 3)
		self.mk("Life Review", user=ANYA, kind="Weekly", status="Locked", title="i26 review", period_start="2026-11-09", period_end="2026-11-15")
		self.assertEqual(self.level()["level"], 4)
		self.mk("Life Inbox Item", title="i26 job", job_id="i26-job", status="Done", claimed_by=ANYA)
		self.assertEqual(self.level()["level"], 5)
		self.assertFalse(self.level()["complete"])
		sp = frappe.get_doc("Life Space", HER)
		sp.append("members", {"user": "family@lifeos.test", "access": "Write"})
		sp.save(ignore_permissions=True)
		out = self.level()
		self.assertEqual(out["level"], 6)
		self.assertTrue(out["complete"] and out["next"] is None)

	def test_2_levels_do_not_skip(self):
		self.mk("Life Task", title="i26 task")
		self.mk("Life Review", user=ANYA, kind="Weekly", status="Locked", title="i26 review", period_start="2026-11-09", period_end="2026-11-15")
		out = self.level()
		self.assertEqual(out["level"], 1)
		self.assertEqual(out["next"]["title"], "Connect a source")
		self.assertTrue(out["next"]["text"].startswith("Next: Connect a source"))

	def test_3_the_next_step_for_a_weekly_review_and_an_upload_is_not_a_source(self):
		self.mk("Life Task", title="i26 task")
		self.mk("Life Inbox Item", title="i26 file", source_type="Upload")
		self.assertEqual(self.level()["level"], 1)
		self.mk("Life Inbox Item", title="i26 mail", source_type="Email", source_system="gmail")
		self.areas_on(3)
		self.mk("Life Goal", title="i26 goal", horizon="Year", target_date="2027-12-31", area=frappe.db.get_value("Life Area", {"space": HER, "is_on": 1}))
		nxt = self.level()["next"]
		self.assertEqual(nxt["to"], "/review")
		self.assertIn("a weekly review · 30 minutes on Sunday. Review joins the menu after your first one.", nxt["text"])

	def test_4_dismiss_hides_the_card_for_that_person_only_and_undo_brings_it_back(self):
		self.assertFalse(self.level()["dismissed"])
		self.as_user(ANYA)
		self.assertTrue(meta.dismiss_setup()["dismissed"])
		self.as_user("Administrator")
		self.assertTrue(self.level()["dismissed"])
		self.as_user("family@lifeos.test")
		self.assertFalse(meta.setup_level()["dismissed"])
		self.as_user(ANYA)
		self.assertFalse(meta.dismiss_setup(undo=1)["dismissed"])


class TestOneSpace(LifeTestCase):
	def test_new_site_has_one_space_private(self):
		# Install makes Private only (the test site's second space comes from devtools.make_shared_space
		self.assertEqual(install.STARTING_SPACES, ("Private",))
		frappe.set_user("Administrator")
		with patch.object(install, "STARTING_SPACES", ("Private",)):
			before = set(frappe.get_all("Life Space", pluck="name"))
			install.make_spaces()
			self.assertEqual(set(frappe.get_all("Life Space", pluck="name")), before)

	def test_create_item_without_a_space_files_into_private(self):
		# On a one-space site
		self.as_user(OWNER)
		with patch.object(permissions, "user_spaces", return_value={PRIVATE: "Write"}):
			item = inbox.create_item(title="One space item", raw_text="x")
		self.assertEqual(item["space"], PRIVATE)

	def test_boot_lists_the_spaces(self):
		self.as_user(OWNER)
		self.assertIn(PRIVATE, [s["name"] for s in session.boot()["spaces"]])


class FakeStream:
	"""What `anthropic.Anthropic().messages.stream(...)` returns: a context manager over no events, with a final message."""

	def __init__(self, text="ok"):
		self.text = text

	def __enter__(self):
		return self

	def __exit__(self, *a):
		return False

	def __iter__(self):
		return iter(())

	def get_final_message(self):
		from types import SimpleNamespace

		block = SimpleNamespace(to_dict=lambda: {"type": "text", "text": self.text})
		return SimpleNamespace(content=[block], stop_reason="end_turn", model="deepseek-chat",
			usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0))


def client_module():
	from lifeos.ai import client

	return client


def fake_backend(response=None):
	from lifeos.ai import fake

	return fake.ScriptedFake([response or {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}])


class TestAIProvider(LifeTestCase):
	"""Issue 102: Anthropic or another Anthropic-compatible service, the real reason for a failure, prices of unknown models."""

	SECRET = "sk-secret-key-0123456789"

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		s = frappe.get_single("Life Settings")
		self.before = {f: s.get(f) for f in ("ai_provider", "ask_model", "short_model")}
		self.addCleanup(self.restore)
		frappe.flags.lifeos_ai_backend = None
		frappe.db.delete("Life AI Usage")
		frappe.db.delete("Life Action Log", {"kind": "AI unavailable"})
		frappe.defaults.clear_default(client_module().OFF_KEY, parent="__default")
		frappe.db.set_single_value("Life Settings", "monthly_cap_usd", 30)
		self.ai(anthropic_api_key=self.SECRET)  # also drops a price left by an earlier run

	def restore(self):
		frappe.flags.lifeos_ai_backend = None
		self.ai(ai_provider=self.before["ai_provider"] or "Anthropic", ai_base_url=None, ai_other_key=None, ask_model=self.before["ask_model"],
			short_model=self.before["short_model"], anthropic_api_key=None)
		frappe.defaults.clear_default(client_module().OFF_KEY, parent="__default")

	def ai(self, **values):
		s = frappe.get_single("Life Settings")
		s.update(values)
		s.set("ai_prices", [r for r in s.ai_prices if r.model != "deepseek-chat"])  # the price this class adds never outlives it
		s.save()

	def other(self):
		self.ai(ai_provider="Another service (Anthropic-compatible)", ai_base_url="https://api.deepseek.com/anthropic", ai_other_key=self.SECRET,
			ask_model="deepseek-chat", short_model="deepseek-chat")

	def sent(self, schema=None, text="ok"):
		"""Run one call through the real backend with the SDK mocked; returns (the Anthropic constructor mock, the stream call's kwargs)."""
		with patch("anthropic.Anthropic") as ctor, patch.object(frappe, "get_site_config", return_value={}):
			ctor.return_value.messages.stream.return_value = FakeStream(text)
			client_module().call("Ask", "system text", [{"role": "user", "content": "hi"}], schema=schema)
		return ctor, ctor.return_value.messages.stream.call_args.kwargs

	def test_1_another_service_gets_its_address_and_key_and_none_of_the_anthropic_extras(self):
		self.other()
		ctor, req = self.sent()
		self.assertEqual(ctor.call_args.kwargs["base_url"], "https://api.deepseek.com/anthropic")
		self.assertEqual(ctor.call_args.kwargs["api_key"], self.SECRET)
		self.assertNotIn("output_config", req)
		self.assertNotIn("extra_headers", req)
		self.assertNotIn("extra_body", req)
		self.assertEqual(req["model"], "deepseek-chat")

	def test_2_anthropic_is_sent_exactly_as_before(self):
		self.ai(ask_model="claude-sonnet-5-5")
		ctor, req = self.sent()
		self.assertNotIn("base_url", ctor.call_args.kwargs)
		self.assertEqual(req["output_config"], {"effort": "medium"})
		self.assertEqual(req["extra_headers"], {"anthropic-beta": "server-side-fallback-2026-07-01"})
		self.assertEqual(req["extra_body"], {"fallbacks": "default"})

	def test_3_a_schema_goes_into_the_system_text_and_invalid_json_is_retried_once(self):
		client = client_module()
		self.other()
		schema = {"type": "object", "properties": {"a": {"type": "string"}}}
		answers = iter([FakeStream("not json"), FakeStream('{"a": "x"}')])
		with patch("anthropic.Anthropic") as ctor, patch.object(frappe, "get_site_config", return_value={}):
			ctor.return_value.messages.stream.side_effect = lambda **kw: next(answers)
			out = client.call("Ask", "system text", [{"role": "user", "content": "hi"}], schema=schema)
			calls = ctor.return_value.messages.stream.call_args_list
		self.assertEqual(len(calls), 2)
		self.assertIn("Answer with JSON only, matching this schema:", calls[0].kwargs["system"])
		self.assertNotIn("output_config", calls[0].kwargs)
		self.assertEqual(client.json_of(out["content"]), {"a": "x"})
		# a second invalid answer is not retried again
		answers = iter([FakeStream("no"), FakeStream("still no"), FakeStream('{"a": "late"}')])
		with patch("anthropic.Anthropic") as ctor, patch.object(frappe, "get_site_config", return_value={}):
			ctor.return_value.messages.stream.side_effect = lambda **kw: next(answers)
			out = client.call("Ask", "system text", [{"role": "user", "content": "hi"}], schema=schema)
			self.assertEqual(ctor.return_value.messages.stream.call_count, 2)
		self.assertIsNone(client.json_of(out["content"]))

	def test_4_a_credit_failure_says_so_keeps_the_key_out_and_logs_once_an_hour(self):
		import anthropic
		import httpx

		client = client_module()

		def fail(**kw):
			resp = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
			raise anthropic.BadRequestError(f"Error 400 {self.SECRET}", response=resp,
				body={"error": {"type": "invalid_request_error", "message": f"Your credit balance is too low to access the Anthropic API. {self.SECRET}"}})

		self.ai(ask_model="claude-sonnet-5-5")
		for _n in range(2):
			with patch("anthropic.Anthropic") as ctor, patch.object(frappe, "get_site_config", return_value={}):
				ctor.return_value.messages.stream.side_effect = fail
				with self.assertRaises(client.AIError) as cm:
					client.call("Ask", "s", [{"role": "user", "content": "hi"}])
			self.assertIn("credit", str(cm.exception))
			self.assertNotIn(self.SECRET, str(cm.exception))
			self.assertNotIn("(400)", str(cm.exception))
		rows = frappe.get_all("Life Action Log", filters={"kind": "AI unavailable"}, fields=["reason"])
		self.assertEqual(len(rows), 1)
		self.assertNotIn(self.SECRET, rows[0].reason)
		self.assertIn("credit", client.brain_off())
		# a call that works clears it
		frappe.flags.lifeos_ai_backend = fake_backend()
		client.call("Ask", "s", [{"role": "user", "content": "hi"}])
		self.assertIsNone(client.brain_off())

	def test_5_a_model_with_no_price_is_counted_at_the_highest_known_price(self):
		client = client_module()
		table = client.price_table()
		top = (max(p[0] for p in table.values()), max(p[1] for p in table.values()))
		self.assertEqual(client.cost_of("no-such-model", 1_000_000, 1_000_000), round(top[0] + top[1], 6))
		self.other()
		self.assertEqual(client.unpriced(), ["deepseek-chat"])
		self.assertEqual(settings.ai_settings()["unpriced"], ["deepseek-chat"])
		settings.set_ai_price("deepseek-chat", 0.3, 1.1)
		self.assertEqual(client.unpriced(), [])
		self.assertAlmostEqual(client.cost_of("deepseek-chat", 1_000_000, 0), 0.3)

	def test_6_a_provider_that_refuses_tools_is_a_tools_error(self):
		client = client_module()
		self.assertIsInstance(client.error_from(400, "tools are not supported by this model"), client.ToolsRefused)

	def test_7_test_connection_says_working_or_the_reason(self):
		client = client_module()
		frappe.flags.lifeos_ai_backend = fake_backend()
		out = settings.test_ai_connection()
		self.assertTrue(out["ok"])
		self.assertIn("Working", out["text"])

		def refuse(params):
			raise client.error_from(401, "Authentication Fails, your api key is invalid")

		frappe.flags.lifeos_ai_backend = fake_backend(refuse)
		out = settings.test_ai_connection()
		self.assertFalse(out["ok"])
		self.assertIn("refused the API key", out["text"])
