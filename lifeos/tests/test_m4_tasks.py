import datetime

import frappe
from frappe.utils import add_days, add_to_date, getdate, now_datetime, today

from lifeos import datewords, index
from lifeos.api import area as area_api
from lifeos.api import goals as goal_api
from lifeos.api import library, tasks, timeline
from lifeos.api import today as today_api
from lifeos.tests.base import FAMILY, PRIVATE, SHARED, LifeTestCase


class TestDateWords(LifeTestCase):
	def test_date_words(self):
		base = datetime.date(2026, 11, 14)  # a Saturday
		cases = {
			"Call Vivek tomorrow": ("Call Vivek", "2026-11-15"),
			"Call Vivek today": ("Call Vivek", "2026-11-14"),
			"Send quote request fri": ("Send quote request", "2026-11-20"),
			"Send quote request on Friday": ("Send quote request", "2026-11-20"),
			"sat: golf": ("golf", "2026-11-21"),
			"Pay the bonus 20 nov": ("Pay the bonus", "2026-11-20"),
			"Pay the bonus Nov 3": ("Pay the bonus", "2027-11-03"),
			"File return 2026-12-01": ("File return", "2026-12-01"),
			"Plan trip next week": ("Plan trip", "2026-11-16"),
			"Renew licence in 3 days": ("Renew licence", "2026-11-17"),
			"Buy sun screen for the trip": ("Buy sun screen for the trip", None),
			"Fix the Monday report": ("Fix the Monday report", None),
		}
		for text, (title, when) in cases.items():
			got_title, got_when = datewords.parse(text, base)
			self.assertEqual((got_title, str(got_when) if got_when else None), (title, when), text)


class TestTasks(LifeTestCase):
	def test_quick_add(self):
		t = tasks.quick_add("Call the auditor tomorrow", space=PRIVATE)
		self.assertEqual((t["title"], t["due_date"], t["status"]), ("Call the auditor", str(add_days(getdate(today()), 1)), "Open"))
		plain = tasks.quick_add("Just a title", space=PRIVATE, area=self.areas["Tea"])
		self.assertEqual((plain["due_date"], plain["area_name"]), (None, "Tea"))
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, tasks.quick_add, "Sneak", space=PRIVATE)

	def test_list_filters_and_order(self):
		tag = self.make("Life Tag", tag_name="m4tag")
		goal_cycle = self.make("Life Cycle", title="M4 cycle", start_date=today())
		goal = self.make("Life Goal", cycle=goal_cycle.name, title="M4 goal")
		open_goal = self.make("Life Goal", title="M4 open goal", goal_type="Open", area=self.areas["Tea"])
		a = self.make("Life Task", title="A later IV", due_date=add_days(today(), 9), priority="IV", area=self.areas["Tea"], goal=open_goal.name)
		b = self.make("Life Task", title="B today II", due_date=today(), priority="II", area=self.areas["Tea"], tags=[{"tag": tag.name}])
		c = self.make("Life Task", title="C today I", due_date=today(), priority="I", area=self.areas["Money"], also_in=[{"area": self.areas["Tea"]}], goal=goal.name)
		d = self.make("Life Task", title="D no date", area=self.areas["Personal"])
		done = self.make("Life Task", title="E done", area=self.areas["Tea"], status="Done")
		names = [t["name"] for t in tasks.list(space=PRIVATE, page_length=100)["tasks"]]
		self.assertLess(names.index(c.name), names.index(b.name))  # same day: I before II
		self.assertLess(names.index(b.name), names.index(a.name))
		self.assertLess(names.index(a.name), names.index(d.name))  # no date last
		self.assertNotIn(done.name, names)
		in_tea = {t["name"] for t in tasks.list(space=PRIVATE, area=self.areas["Tea"])["tasks"]}
		self.assertTrue({a.name, b.name, c.name} <= in_tea and d.name not in in_tea)
		self.assertEqual([t["name"] for t in tasks.list(space=PRIVATE, goal=open_goal.name)["tasks"]], [a.name])
		self.assertEqual([t["name"] for t in tasks.list(space=PRIVATE, tag=tag.name)["tasks"]], [b.name])
		self.assertEqual([t["name"] for t in tasks.list(space=PRIVATE, goal=goal.name)["tasks"]], [c.name])
		self.assertIn(c.name, [t["name"] for t in tasks.list(space=PRIVATE, priority="I")["tasks"]])
		self.assertIn(done.name, [t["name"] for t in tasks.list(space=PRIVATE, status="done")["tasks"]])
		self.assertLessEqual(len(tasks.list(space=PRIVATE, page_length=5000)["tasks"]), 100)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, tasks.list, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, tasks.get, a.name)
		self.assertRaises(frappe.PermissionError, tasks.set_status, a.name, "Done")

	def test_status_rules(self):
		t = self.make("Life Task", title="Status task")
		self.assertRaises(frappe.MandatoryError, tasks.set_status, t.name, "Waiting")
		out = tasks.set_status(t.name, "Waiting", waiting_on="Vivek")
		self.assertEqual(out["waiting_on"], "Vivek")
		self.assertEqual(tasks.set_status(t.name, "Done")["completed_on"], today())

	def test_carry_forward_task(self):
		t = self.make("Life Task", title="Start RMT newsletter", priority="I", area=self.areas["Tea"], due_date=today())
		out = tasks.carry_forward(t.name)
		old = frappe.get_doc("Life Task", t.name)
		new = frappe.get_doc("Life Task", out["task"])
		now = getdate(today())
		ny, nm = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
		self.assertEqual((old.status, new.status, new.carried_from, new.title, new.priority), ("Carried", "Open", old.name, old.title, "I"))
		self.assertEqual(new.month_plan, f"{PRIVATE}-{ny}-{nm:02d}")
		plan = frappe.get_doc("Life Month Plan", new.month_plan)
		self.assertIn(new.name, [g.task for g in plan.goals])
		self.assertRaises(frappe.ValidationError, tasks.carry_forward, t.name)  # already carried

	def test_open_loops(self):
		before = tasks.open_loops(space=PRIVATE)["total"]
		old = self.make("Life Task", title="Old loop")
		frappe.db.set_value("Life Task", old.name, "creation", add_to_date(now_datetime(), days=-15), update_modified=False)
		recent = self.make("Life Task", title="Recent, no date")
		dated = self.make("Life Task", title="Old with date", due_date=add_days(today(), 3))
		frappe.db.set_value("Life Task", dated.name, "creation", add_to_date(now_datetime(), days=-30), update_modified=False)
		res = tasks.open_loops(space=PRIVATE)
		names = [t["name"] for t in res["tasks"]]
		self.assertEqual(res["total"], before + 1)
		self.assertIn(old.name, names)
		self.assertNotIn(recent.name, names)
		self.assertNotIn(dated.name, names)
		self.assertEqual(today_api.get(space=PRIVATE)["open_loops"], before + 1)


class TestToday(LifeTestCase):
	def test_today_in_one_call(self):
		habit = self.make("Life Habit", title="Japa m4")
		now = getdate(today())
		plan_name = f"{PRIVATE}-{now.year}-{now.month:02d}"
		if frappe.db.exists("Life Month Plan", plan_name):
			plan = frappe.get_doc("Life Month Plan", plan_name)
			plan.append("habits", {"habit": habit.name})
			plan.save()
		else:
			self.make("Life Month Plan", year=now.year, month=now.month, habits=[{"habit": habit.name, "tracked_from": now.replace(day=1)}])
		self.make("Life Habit Log", habit=habit.name, date=now)
		due = self.make("Life Task", title="Due today", due_date=now)
		over = self.make("Life Task", title="Overdue", due_date=add_days(now, -2))
		self.make("Life Task", title="Later", due_date=add_days(now, 5))
		event = frappe.get_doc({"doctype": "Event", "subject": "Golf round m4", "starts_on": f"{now} 07:00:00", "life_space": PRIVATE}).insert()
		doc = self.make("Life Vault Document", title="Driving licence m4", expiry_date=add_days(now, 30), remind_days_before=60)
		far = self.make("Life Vault Document", title="Passport m4", expiry_date=add_days(now, 400))
		item = self.make("Life Inbox Item", title="To review m4", status="To Review")
		data = today_api.get(space=PRIVATE)
		titles = [t["title"] for t in data["tasks"]["items"]]
		self.assertIn("Due today", titles)
		self.assertIn("Overdue", titles)
		self.assertNotIn("Later", titles)
		self.assertGreaterEqual(data["tasks"]["overdue"], 1)
		self.assertIn("Golf round m4", [e["title"] for e in data["events"]])
		self.assertIn({"habit": habit.name, "title": "Japa m4", "done": True}, data["habits"])
		self.assertIn(item.name, [i["name"] for i in data["to_review"]["items"]])
		vault = [c for c in data["coming_up"] if c["kind"] == "vault"]
		self.assertIn(doc.name, [c["name"] for c in vault])
		self.assertNotIn(far.name, [c["name"] for c in vault])
		self.assertEqual([c["days"] for c in vault if c["name"] == doc.name], [30])
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, today_api.get, space=PRIVATE)
		shared = today_api.get(space=SHARED)
		self.assertNotIn("Golf round m4", [e["title"] for e in shared["events"]])
		self.assertEqual(shared["tasks"]["items"], [])

	def test_today_groups_and_reschedule(self):
		now = getdate(today())
		mine = [self.make("Life Task", title=f"Today group {i}", due_date=now) for i in range(2)]
		old = [self.make("Life Task", title=f"Overdue group {i}", due_date=add_days(now, -3 - i)) for i in range(9)]
		data = today_api.get(space=PRIVATE)["tasks"]
		self.assertEqual(data["group_rows"], 7)
		self.assertTrue({t.name for t in mine} <= {t["name"] for t in data["today"]})
		self.assertTrue(all(t["due_date"] == str(now) for t in data["today"]))
		self.assertLessEqual(len(data["overdue_items"]), 7)
		self.assertTrue(all(t["due_date"] < str(now) for t in data["overdue_items"]))
		self.assertGreaterEqual(data["overdue"], 9)
		self.assertLessEqual(data["oldest_overdue"], str(add_days(now, -11)))
		# the counts are the ones the Tasks list gives for the same filters
		self.assertEqual(data["today_count"], tasks.count(PRIVATE, due="today"))
		# the family member cannot move the owner's tasks; a date in the past is refused
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, tasks.reschedule_overdue, space=PRIVATE)
		self.as_user("Administrator")
		self.assertRaises(frappe.ValidationError, tasks.reschedule_overdue, space=PRIVATE, to_date=add_days(now, -1))
		out = tasks.reschedule_overdue(space=PRIVATE, to_date=add_days(now, 1))
		self.assertGreaterEqual(out["moved"], 9)
		self.assertEqual({str(frappe.db.get_value("Life Task", t.name, "due_date")) for t in old}, {str(add_days(now, 1))})
		after = today_api.get(space=PRIVATE)["tasks"]
		self.assertEqual((after["overdue"], after["overdue_items"], after["oldest_overdue"]), (0, [], None))


class TestAreasGoalsTimeline(LifeTestCase):
	# set 6: area pages went (the lens shows an area on every place, see test_ux6_lens); the area tree keeps the counts
	def test_area_tree_counts_with_sub_areas(self):
		tea = self.areas["Tea"]
		sub = self.make("Life Area", area_name="Ghatia m4", parent_area=tea)
		goal = self.make("Life Goal", title="Mandir m4", goal_type="Open", area=sub.name)
		self.make("Life Goal", title="Mandir m4 done", goal_type="Open", area=tea, outcome="Achieved")
		self.make("Life Task", title="Area task m4", area=tea, goal=goal.name)
		self.make("Life Task", title="Sub-area task m4", area=sub.name)
		self.make("Life Note", title="Reference note m4", area=sub.name)
		self.make("Life Note", title="Archived note m4", area=tea, is_archived=1)
		tree = area_api.tree(space=PRIVATE)
		row = {a["name"]: a for a in tree["areas"]}
		self.assertEqual(row[sub.name]["parent_area"], tea)
		# each number equals the list it opens: the area with its sub-areas
		self.assertEqual(row[tea]["open_tasks"], tasks.list(space=PRIVATE, area=tea, page_length=1)["total"])
		self.assertEqual(row[tea]["goals"], goal_api.list(space=PRIVATE, area=tea, page_length=1)["total"])
		self.assertEqual(row[sub.name]["goals"], 1)
		self.assertEqual(row[tea]["notes"], library.list(space=PRIVATE, area=tea, collection="all", page_length=1)["total"])
		self.assertGreaterEqual(row[tea]["open_tasks"], 2)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, area_api.tree, space=PRIVATE)

	def test_open_goals_list_and_page(self):
		goal = self.make("Life Goal", title="Turnaround m4", goal_type="Open", area=self.areas["Tea"], done_when="A plan")
		t1 = self.make("Life Task", title="P task 1", area=self.areas["Tea"], goal=goal.name)
		self.make("Life Task", title="P task 2", area=self.areas["Tea"], goal=goal.name, status="Done")
		self.make("Life Note", title="P note", area=self.areas["Tea"], goal=goal.name)
		card = next(g for g in goal_api.list(space=PRIVATE, goal_type="Open")["goals"] if g["name"] == goal.name)
		self.assertEqual((card["tasks_counted"], card["tasks_done"], card["area_name"], card["done_when"]), (2, 1, "Tea", "A plan"))
		page = goal_api.get(goal.name)
		self.assertEqual((page["goal"]["status"], page["goal"]["done_when"]), ("Active", "A plan"))
		self.assertEqual((page["tabs"]["tasks"], page["tabs"]["notes"]), (1, 1))
		self.assertEqual([t["name"] for t in tasks.list(space=PRIVATE, goal=goal.name)["tasks"]], [t1.name])
		self.assertEqual(page["record_count"], 3)
		self.assertEqual(goal_api.completion_info(goal.name)["records"], 3)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, goal_api.get, goal.name)

	def test_timeline_by_day_and_archive_switch(self):
		note = self.make("Life Note", title="Timeline note m4", area=self.areas["Tea"])
		old = self.make("Life Chat Log", title="Timeline chat m4", date=add_days(today(), -3))
		task = self.make("Life Task", title="Timeline task m4")
		task.status = "Done"
		task.save()
		hidden = self.make("Life Note", title="Timeline archived m4", is_archived=1)
		data = timeline.get(space=PRIVATE, page_length=100)
		dates = [d["date"] for d in data["days"]]
		self.assertEqual(dates, sorted(dates, reverse=True))
		today_entries = next(d for d in data["days"] if d["date"] == today())["entries"]
		kinds = [(e["ref_name"], e["kind"]) for e in today_entries]
		self.assertIn((note.name, "Note"), kinds)
		self.assertIn((task.name, "Task"), kinds)
		self.assertIn((task.name, "Task Done"), kinds)
		everything = [e["ref_name"] for d in data["days"] for e in d["entries"]]
		self.assertIn(old.name, everything)
		self.assertNotIn(hidden.name, everything)
		with_archived = timeline.get(space=PRIVATE, include_archived=1, page_length=100)
		self.assertIn(hidden.name, [e["ref_name"] for d in with_archived["days"] for e in d["entries"]])
		only_notes = timeline.get(space=PRIVATE, doctype="Life Note", area=self.areas["Tea"])
		self.assertEqual({e["ref_doctype"] for d in only_notes["days"] for e in d["entries"]}, {"Life Note"})
		one_day = timeline.get(space=PRIVATE, from_date=add_days(today(), -3), to_date=add_days(today(), -3))
		self.assertEqual([d["date"] for d in one_day["days"]], [str(add_days(getdate(today()), -3))])
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, timeline.get, space=PRIVATE)
		shared = timeline.get(space=SHARED)
		self.assertNotIn(note.name, [e["ref_name"] for d in shared["days"] for e in d["entries"]])
