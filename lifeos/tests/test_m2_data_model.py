import frappe
from frappe.utils import add_days, today

from lifeos import index, seed
from lifeos.constants import SPACE_DOCTYPES
from lifeos.tests.base import PRIVATE, SHARED, LifeTestCase


def index_rows(doctype, name):
	return frappe.db.sql(
		"select kind, space, area, also_in_csv, goal, tags_csv, record_date, title, search_text, is_archived, status "
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

	def test_important_date_validation(self):
		self.make("Life Important Date", title="Leap birthday", day=29, month=2)
		bad = frappe.get_doc({"doctype": "Life Important Date", "space": PRIVATE, "title": "Bad", "day": 31, "month": 4})
		self.assertRaises(frappe.ValidationError, bad.insert)

	def test_habit_log_is_unique_per_day(self):
		habit = self.make("Life Habit", title="Japa test")
		self.make("Life Habit Log", habit=habit.name, date="2026-11-01")
		dup = frappe.get_doc({"doctype": "Life Habit Log", "space": PRIVATE, "habit": habit.name, "date": "2026-11-01"})
		self.assertRaises(frappe.DuplicateEntryError, dup.insert)
		self.make("Life Habit Log", habit=habit.name, date="2026-11-02")

	def test_check_in_ranges(self):
		from lifeos.life.doctype.life_check_in.life_check_in import parse_range

		self.assertEqual(parse_range("2-3"), (2.0, 3.0))
		self.assertEqual(parse_range("7"), (7.0, 7.0))
		self.assertEqual(parse_range(6.5), (6.5, 6.5))
		self.assertEqual(parse_range(""), (None, None))
		dim = frappe.db.get_value("Life Dimension", {"space": PRIVATE, "dimension_name": "Money"})
		doc = self.make("Life Check-in", date=today(), scores=[
			{"dimension": dim, "habits_low": 2, "habits_high": 3, "situation_low": 7, "situation_high": 7}])
		self.assertEqual((doc.scores[0].habits_low, doc.scores[0].habits_high), (2, 3))
		bad = frappe.get_doc({"doctype": "Life Check-in", "space": PRIVATE, "date": today(),
			"scores": [{"dimension": dim, "habits_low": 4, "habits_high": 11}]})
		self.assertRaises(frappe.ValidationError, bad.insert)

	def test_cycle_end_date(self):
		cycle = self.make("Life Cycle", title="Test cycle", start_date="2026-10-05")
		self.assertEqual(str(cycle.end_date), "2026-12-27")

	def test_month_plan_name(self):
		plan = self.make("Life Month Plan", year=2031, month=3)
		self.assertEqual(plan.name, f"{PRIVATE}-2031-03")
		dup = frappe.get_doc({"doctype": "Life Month Plan", "space": PRIVATE, "year": 2031, "month": 3})
		self.assertRaises(frappe.DuplicateEntryError, dup.insert)


class TestAreasAndGoals(LifeTestCase):
	def test_area_from_another_space_is_refused(self):
		task = frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "Wrong area", "area": self.shared_areas["Family"]})
		self.assertRaises(frappe.ValidationError, task.insert)
		task = frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": "Wrong also in", "area": self.areas["Tea"],
			"also_in": [{"area": self.shared_areas["Work"]}]})
		self.assertRaises(frappe.ValidationError, task.insert)

	def test_tag_from_another_space_is_refused(self):
		tag = self.make("Life Tag", space=SHARED, tag_name="groceries")
		note = frappe.get_doc({"doctype": "Life Note", "space": PRIVATE, "title": "Tagged", "tags": [{"tag": tag.name}]})
		self.assertRaises(frappe.ValidationError, note.insert)

	def test_goal_of_a_record_may_sit_in_any_area_of_its_space(self):
		# set 6: projects became goals; a goal is not tied to the record's area (the old area check went with projects)
		goal = self.make("Life Goal", title="Ghillidary turnaround", goal_type="Open", area=self.areas["Tea"])
		ok = self.make("Life Task", title="In the goal's area", area=self.areas["Tea"], goal=goal.name)
		self.assertEqual(ok.goal, goal.name)
		elsewhere = self.make("Life Task", title="Elsewhere", area=self.areas["Personal"], goal=goal.name)
		self.assertEqual(elsewhere.goal, goal.name)
		other = frappe.get_doc({"doctype": "Life Task", "space": SHARED, "title": "Other space", "goal": goal.name})
		self.assertRaises(frappe.ValidationError, other.insert)

	def test_area_names_are_unique_per_space(self):
		dup = frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Tea"})
		self.assertRaises(frappe.DuplicateEntryError, dup.insert)
		self.make("Life Area", area_name="Ghatia", parent_area=self.areas["Tea"])
		self.make("Life Area", space=SHARED, area_name="Tea")


class TestIndex(LifeTestCase):
	def test_saving_writes_one_row(self):
		tag = self.make("Life Tag", tag_name="audit")
		note = self.make("Life Note", title="Estate training outline", content_md="Trained manpower plan",
			area=self.areas["Tea"], also_in=[{"area": self.areas["Money"]}], tags=[{"tag": tag.name}])
		rows = index_rows("Life Note", note.name)
		self.assertEqual(len(rows), 1)
		r = rows[0]
		self.assertEqual((r.kind, r.space, r.area, r.title), ("Note", PRIVATE, self.areas["Tea"], "Estate training outline"))
		self.assertEqual(r.also_in_csv, f",{self.areas['Money']},")
		self.assertEqual(r.tags_csv, f",{tag.name},")
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
			self.make("Life Journal Page", page_date=today(), page_number="187", transcript_md="Goal Oct to Dec"),
			self.make("Life Check-in", date=today(), reflection_md="steady week"),
			self.make("Life Month Plan", year=2032, month=5, mindsweep_md="## Land"),
		]
		for doc in made:
			rows = index_rows(doc.doctype, doc.name)
			self.assertEqual(len(rows), 1, doc.doctype)
			self.assertEqual(rows[0].space, PRIVATE)
		self.assertEqual(index_rows("Life Chat Log", made[4].name)[0].status, "Open")
		self.assertEqual(str(index_rows("Life Month Plan", made[7].name)[0].record_date), "2032-05-01")

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
		query = ("select name, ref_doctype, ref_name, space, area, also_in_csv, goal, tags_csv, record_date, title, "
			"search_text, is_archived, kind, status, record_owner from `tabLife Index` order by name")
		before = frappe.db.sql(query)
		self.assertTrue(before)
		frappe.set_user("Administrator")
		index.rebuild()
		self.assertEqual(before, frappe.db.sql(query))


class TestSeed(LifeTestCase):
	def test_structure_is_created_at_install(self):
		names = frappe.get_all("Life Area", filters={"space": "Private", "parent_area": ("is", "not set")}, pluck="area_name")
		for name in seed.PRIVATE_AREAS:
			self.assertIn(name, names)
		shared = frappe.get_all("Life Area", filters={"space": "Shared"}, pluck="area_name")
		self.assertEqual(sorted(shared), sorted(seed.SHARED_AREAS))
		self.assertEqual(frappe.db.count("Life Dimension", {"space": "Private"}), 8)

	def test_load_and_remove(self):
		frappe.set_user("Administrator")
		key = "lifeos_seed_test"
		seed.remove(key)
		seed.load(PRIVATE, key)
		cycle = frappe.get_doc("Life Cycle", {"space": PRIVATE, "title": seed.CYCLE_TITLE})
		self.assertEqual((str(cycle.start_date), str(cycle.end_date), cycle.status), ("2026-10-05", "2026-12-27", "Active"))
		goals = frappe.get_all("Life Goal", filters={"cycle": cycle.name}, fields=["name", "title", "area"], order_by="sort_order")
		self.assertEqual([g.title for g in goals], [g[0] for g in seed.GOALS])
		loops = frappe.get_doc("Life Goal", goals[1].name)
		self.assertEqual(len(loops.actions), 6)
		self.assertEqual([a.status for a in loops.actions if a.title == "Anya passport"], ["Done"])
		self.assertEqual(frappe.db.get_value("Life Area", goals[0].area, "area_name"), "Tea & Coffee")
		october = frappe.get_doc("Life Month Plan", f"{PRIVATE}-2026-10")
		self.assertEqual(len(october.goals), 14)
		self.assertEqual(sum(1 for g in october.goals if g.status == "Carried"), 9)
		self.assertEqual(len(october.habits), 4)
		self.assertIn("## Land monetisation", october.mindsweep_md)
		november = frappe.get_doc("Life Month Plan", f"{PRIVATE}-2026-11")
		self.assertEqual([frappe.db.get_value("Life Habit", h.habit, "title") for h in november.habits], seed.HABITS)
		self.assertEqual(frappe.db.count("Life Check-in", {"space": PRIVATE}), 0)
		self.assertEqual(frappe.db.count("Life Important Date", {"space": PRIVATE}), 0)
		self.assertIn("already loaded", seed.load(PRIVATE, key))
		seed.remove(key)
		self.assertFalse(frappe.db.exists("Life Cycle", cycle.name))
		self.assertFalse(frappe.db.exists("Life Month Plan", f"{PRIVATE}-2026-10"))
		self.assertEqual(frappe.db.count("Life Habit", {"space": PRIVATE, "title": ("in", seed.HABITS)}), 0)
