"""Tests for tasks."""
import datetime

import frappe
from frappe.utils import add_days, add_to_date, getdate, now_datetime, today

from lifeos import archive as archive_rules, counts, datewords, outbox, permissions, trash
from lifeos.api import archive, area as area_api, calendar as calendar_api, chats, goals, goals as goal_api, inbox, library, outbox as outbox_api, review, someday, tasks, timeline, today as today_api, vault, views
from lifeos.api.utils import std_filters, std_order
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, OWNER, PRIVATE, SHARED
from lifeos.tests.helpers import item, set_key, task, text


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
		goal_cycle = self.make("Life Cycle", title="M4 cycle", start_date=today())
		goal = self.make("Life Goal", cycle=goal_cycle.name, title="M4 goal")
		open_goal = self.make("Life Goal", title="M4 open goal", horizon="Long term", area=self.areas["Tea"])
		a = self.make("Life Task", title="A later IV", due_date=add_days(today(), 9), priority="IV", area=self.areas["Tea"], goal=open_goal.name)
		b = self.make("Life Task", title="B today II", due_date=today(), priority="II", area=self.areas["Tea"])
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
		self.assertTrue(frappe.db.exists("Life Month Plan", new.month_plan))
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
	# set 6: area pages went (the lens shows an area on every place, see test_permissions); the area tree keeps the counts
	def test_area_tree_counts_with_sub_areas(self):
		tea = self.life["Career"]  # issue 11: an area of life with its parts
		sub = self.make("Life Area", area_name="Ghatia m4", parent_area=tea)
		goal = self.make("Life Goal", title="Mandir m4", horizon="Long term", area=sub.name)
		self.make("Life Goal", title="Mandir m4 done", horizon="Long term", area=tea, outcome="Achieved")
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
		goal = self.make("Life Goal", title="Turnaround m4", horizon="Long term", area=self.areas["Tea"], done_when="A plan")
		t1 = self.make("Life Task", title="P task 1", area=self.areas["Tea"], goal=goal.name)
		self.make("Life Task", title="P task 2", area=self.areas["Tea"], goal=goal.name, status="Done")
		self.make("Life Note", title="P note", area=self.areas["Tea"], goal=goal.name)
		card = next(g for g in goal_api.list(space=PRIVATE, horizon="Long term")["goals"] if g["name"] == goal.name)
		self.assertEqual((card["tasks_counted"], card["tasks_done"], card["area_name"], card["done_when"]), (2, 1, "Tea", "A plan"))
		page = goal_api.get(goal.name)
		self.assertEqual((page["goal"]["status"], page["goal"]["done_when"]), ("Active", "A plan"))
		self.assertEqual((page["tabs"]["tasks"], page["tabs"]["notes"]), (1, 1))
		self.assertEqual([t["name"] for t in tasks.list(space=PRIVATE, goal=goal.name)["tasks"]], [t1.name])
		self.assertEqual(page["record_count"], 3)
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


class TestAllTasks(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Task", {"space": PRIVATE})
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		self.career, self.health, self.tea = self.life["Career"], self.life["Health"], self.areas["Tea"]
		for a in (self.career, self.health):
			frappe.db.set_value("Life Area", a, "is_on", 1)

	def names(self, res):
		return [t["name"] for g in res["groups"] for p in g["parts"] for t in p["tasks"]]

	def test_every_open_task_appears_once_under_its_area(self):
		a = self.make("Life Task", title="i21 a", area=self.career, status="Open").name
		b = self.make("Life Task", title="i21 b", area=self.tea, status="Doing").name
		c = self.make("Life Task", title="i21 c", area=self.health, status="Waiting", waiting_on="Vivek").name
		d = self.make("Life Task", title="i21 none", status="Open").name
		self.make("Life Task", title="i21 done", area=self.health, status="Done")
		res = tasks.all_tasks(space=PRIVATE)
		self.assertEqual(sorted(self.names(res)), sorted([a, b, c, d]))
		self.assertEqual(res["total"], 4)
		career = next(g for g in res["groups"] if g["area"] == self.career)
		# a task saved with no area gets a guessed one (issue 13), so it is under an area too
		guessed = next(t for g in res["groups"] for p in g["parts"] for t in p["tasks"] if t["name"] == d)
		self.assertTrue(guessed["area_guessed"] and guessed["area"])
		self.assertEqual([t["name"] for t in career["parts"][-1]["tasks"]], [b])
		self.assertIn(a, [t["name"] for t in career["parts"][0]["tasks"]])
		self.assertEqual(tasks.count(PRIVATE, status="open"), 4)

	def test_goal_and_due_date_regroup_the_same_tasks(self):
		g = self.make("Life Goal", title="i21 goal", area=self.career, horizon="Long term").name
		self.make("Life Task", title="i21 g", area=self.career, goal=g, due_date=today())
		self.make("Life Task", title="i21 late", area=self.health, due_date=add_days(today(), -2))
		self.make("Life Task", title="i21 undated", area=self.health)
		same = sorted(self.names(tasks.all_tasks(space=PRIVATE)))
		by_goal = tasks.all_tasks(space=PRIVATE, group="goal")
		by_due = tasks.all_tasks(space=PRIVATE, group="due")
		self.assertEqual(sorted(self.names(by_goal)), same)
		self.assertEqual(sorted(self.names(by_due)), same)
		self.assertEqual([x["label"] for x in by_goal["groups"]], ["i21 goal", "No goal"])
		self.assertEqual([x["key"] for x in by_due["groups"]], ["overdue", "today", "none"])

	def test_filters_and_counts(self):
		self.make("Life Task", title="i21 soon", area=self.career, due_date=today())
		self.make("Life Task", title="i21 far", area=self.career, due_date=add_days(today(), 60))
		self.make("Life Task", title="i21 wait", area=self.career, status="Waiting", waiting_on="Mr. Rao")
		self.make("Life Task", title="i21 done", area=self.career, status="Done")
		counts = tasks.all_tasks(space=PRIVATE)["counts"]
		self.assertEqual(counts, dict(open=3, due=1, waiting=1, stuck=0, someday=0, done=1))
		for show, n in (("due", 1), ("waiting", 1), ("done", 1)):
			self.assertEqual(tasks.all_tasks(space=PRIVATE, show=show)["total"], n)
		self.assertEqual(tasks.all_tasks(space=PRIVATE, q="soon")["total"], 1)
		self.assertEqual(tasks.all_tasks(space=PRIVATE, area=self.health)["total"], 0)
		with self.assertRaises(frappe.ValidationError):
			tasks.all_tasks(space=PRIVATE, show="x")

	def test_the_someday_filter_is_the_someday_pages_tasks(self):
		t = self.make("Life Task", title="i21 parked", area=self.career).name
		someday.park("Life Task", t)
		self.make("Life Task", title="i21 open", area=self.career)
		old = [r["name"] for r in someday.list(space=PRIVATE, tab="tasks", page_length=100)["rows"]]
		new = self.names(tasks.all_tasks(space=PRIVATE, show="someday"))
		self.assertEqual(sorted(new), sorted(old))
		self.assertIn(t, new)

	def test_a_guessed_area_and_the_top_three_come_through(self):
		t = self.make("Life Task", title="i21 guess", area=self.career, area_guessed=1, area_confidence=70, is_top_three=1).name
		row = next(x for g in tasks.all_tasks(space=PRIVATE)["groups"] for p in g["parts"] for x in p["tasks"] if x["name"] == t)
		self.assertTrue(row["area_guessed"])
		self.assertTrue(row["is_top_three"])
		self.assertEqual(row["area_name"], "Career")

	def test_an_area_that_is_off_hides_its_tasks_and_the_counts_agree(self):
		self.make("Life Task", title="i21 h", area=self.health)
		self.make("Life Task", title="i21 c", area=self.career)
		frappe.db.set_value("Life Area", self.health, "is_on", 0)
		res = tasks.all_tasks(space=PRIVATE)
		self.assertEqual((res["total"], res["counts"]["open"]), (1, 1))


class TestNoGoal(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Task", {"space": PRIVATE})
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		self.career, self.health = self.life["Career"], self.life["Health"]
		for a in (self.career, self.health):
			frappe.db.set_value("Life Area", a, "is_on", 1)

	def names(self, res):
		return [t["name"] for g in res["groups"] for t in g["tasks"]]

	def test_tasks_with_no_goal_by_area_and_the_count(self):
		g = self.make("Life Goal", title="i22 goal", area=self.career, horizon="Long term").name
		a = self.make("Life Task", title="i22 a", area=self.career).name
		b = self.make("Life Task", title="i22 b", area=self.health, status="Waiting", waiting_on="Rao").name
		self.make("Life Task", title="i22 has goal", area=self.career, goal=g)
		self.make("Life Task", title="i22 done", area=self.career, status="Done")
		res = tasks.no_goal(space=PRIVATE)
		self.assertEqual(sorted(self.names(res)), sorted([a, b]))
		self.assertEqual({g["area"] for g in res["groups"]}, {self.career, self.health})
		self.assertEqual(tasks.no_goal_total(space=PRIVATE)["count"], 2)

	def test_an_area_that_is_off_still_lists_its_tasks(self):
		t = self.make("Life Task", title="i22 off", area=self.health).name
		frappe.db.set_value("Life Area", self.health, "is_on", 0)
		res = tasks.no_goal(space=PRIVATE)
		group = next(g for g in res["groups"] if g["area"] == self.health)
		self.assertFalse(group["is_on"])
		self.assertEqual([x["name"] for x in group["tasks"]], [t])
		self.assertEqual(tasks.no_goal_total(space=PRIVATE)["count"], 1)

	def test_fine_as_is_confirms_the_area_and_leaves_the_list(self):
		t = self.make("Life Task", title="i22 fine", area=self.career, area_guessed=1, area_confidence=60).name
		tasks.keep_standalone(t)
		self.assertEqual(frappe.db.get_value("Life Task", t, ["standalone", "area_guessed"]), (1, 0))
		self.assertEqual(self.names(tasks.no_goal(space=PRIVATE)), [])
		self.assertEqual(tasks.no_goal_total(space=PRIVATE)["count"], 0)

	def test_a_suggestion_needs_three_tasks_sharing_a_word(self):
		for t in ("Call Mehi Motors about the quote", "Send Mehi Motors the drawings", "Visit Mehi Motors plant"):
			self.make("Life Task", title=t, area=self.career)
		self.make("Life Task", title="Pay the electricity bill", area=self.career)
		self.make("Life Task", title="Stretch", area=self.health)
		res = tasks.no_goal(space=PRIVATE)
		career = next(g for g in res["groups"] if g["area"] == self.career)
		self.assertEqual(len(career["suggestion"]["tasks"]), 3)
		self.assertIsNone(next(g for g in res["groups"] if g["area"] == self.health)["suggestion"])

	def test_make_goal_creates_one_goal_and_attaches_the_tasks(self):
		ts = [self.make("Life Task", title=f"i22 mehi {n}", area=self.career).name for n in range(3)]
		other = self.make("Life Task", title="i22 other", area=self.career).name
		out = tasks.make_goal(ts, space=PRIVATE, area=self.career)
		goal = frappe.get_doc("Life Goal", out["goal"])
		self.assertEqual((goal.area, goal.horizon, goal.outcome), (self.career, "Year", "In Progress"))
		self.assertEqual(frappe.db.count("Life Goal", {"space": PRIVATE}), 1)
		for t in ts:
			self.assertEqual(frappe.db.get_value("Life Task", t, "goal"), goal.name)
		self.assertFalse(frappe.db.get_value("Life Task", other, "goal"))
		self.assertEqual(self.names(tasks.no_goal(space=PRIVATE)), [other])
		with self.assertRaises(frappe.ValidationError):  # a task that has a goal now cannot be made a goal again
			tasks.make_goal(ts[:1], space=PRIVATE)

	def test_make_goal_takes_its_title_from_the_assistant_when_a_key_is_set(self):
		from lifeos.ai import fake
		from lifeos.tests.helpers import set_key

		ts = [self.make("Life Task", title=f"Call Vivek about plan {n}", area=self.career).name for n in range(3)]
		set_key("sk-test-not-real")
		backend = frappe.flags.lifeos_ai_backend = fake.ScriptedFake([{"content": [{"type": "text", "text": '{"kind": "Title", "title": "Agree the plan with Vivek"}'}],
			"stop_reason": "end_turn", "usage": {"input_tokens": 100, "output_tokens": 10}}])
		used = frappe.db.count("Life AI Usage", {"purpose": "Skill: define-goal"})
		try:
			out = tasks.make_goal(ts, space=PRIVATE, area=self.career)
		finally:
			frappe.flags.lifeos_ai_backend = None
			set_key(None)
		self.assertEqual(out["title"], "Agree the plan with Vivek")
		self.assertEqual(len(backend.received), 1)
		self.assertEqual(frappe.db.count("Life AI Usage", {"purpose": "Skill: define-goal"}), used + 1)

	def test_make_goal_names_the_goal_from_the_titles_without_a_key(self):
		ts = [self.make("Life Task", title=f"Quote for Zorbax {n}", area=self.career).name for n in range(3)]
		self.assertEqual(tasks.make_goal(ts, space=PRIVATE, area=self.career)["title"], "Get Zorbax done")


def exits(doctype, name, counting=True):
	f = {"record_doctype": doctype, "record_name": name}
	if counting:
		f["reversed"] = 0
	return frappe.get_all("Life Exit", filters=f, pluck="pile", order_by="creation asc")


class OutboxCase(LifeTestCase):
	def task(self, title="ux7 task", **kw):
		return frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": title, "area": self.areas["Tea"], "status": "Open", **kw}).insert()


class TestTaskExits(OutboxCase):
	def test_done_and_reopen(self):
		t = self.task()
		tasks.set_status(t.name, "Done")
		self.assertEqual(exits("Life Task", t.name), ["Done"])
		tasks.set_status(t.name, "Open")
		self.assertEqual(exits("Life Task", t.name), [])
		self.assertEqual(exits("Life Task", t.name, counting=False), ["Done"])

	def test_delegated_only_to_someone_else(self):
		t = self.task()
		tasks.set_status(t.name, "Waiting", waiting_on="Jai")  # the owner's own name: not delegated
		self.assertEqual(exits("Life Task", t.name), [])
		tasks.set_status(t.name, "Waiting", waiting_on="Mithun")
		self.assertEqual(exits("Life Task", t.name), ["Delegated"])
		tasks.set_status(t.name, "Done")  # moving pile: counted once
		self.assertEqual(exits("Life Task", t.name), ["Done"])
		tasks.set_status(t.name, "Open")
		self.assertEqual(exits("Life Task", t.name), [])

	def test_parked_and_brought_back(self):
		t = self.task()
		someday.park("Life Task", t.name)
		self.assertEqual(exits("Life Task", t.name), ["Parked"])
		someday.bring_back("Life Task", t.name)
		self.assertEqual(exits("Life Task", t.name), [])

	def test_dropped_and_deleted_and_restored(self):
		t = self.task()
		tasks.set_status(t.name, "Dropped")
		self.assertEqual(exits("Life Task", t.name), ["Discarded"])
		tasks.set_status(t.name, "Open")
		self.assertEqual(exits("Life Task", t.name), [])
		trash.delete("Life Task", t.name)
		self.assertEqual(exits("Life Task", t.name), ["Discarded"])
		dd = frappe.db.get_value("Deleted Document", {"deleted_doctype": "Life Task", "deleted_name": t.name, "restored": 0})
		trash.restore(dd)
		self.assertEqual(exits("Life Task", t.name), [])

	def test_deleting_a_done_task_keeps_its_done_exit(self):
		t = self.task()
		tasks.set_status(t.name, "Done")
		trash.delete("Life Task", t.name)
		self.assertEqual(exits("Life Task", t.name), ["Done"])


class TestGoalExits(OutboxCase):
	def test_outcomes_someday_and_delete(self):
		g = goals.create("ux7 g1", "Year", space=PRIVATE, target_date=add_days(today(), 60), done_when="x")["name"]
		goals.close(g, "Achieved")
		self.assertEqual(exits("Life Goal", g), ["Done"])
		goals.close(g, "In Progress")
		self.assertEqual(exits("Life Goal", g), [])
		goals.close(g, "Partly Achieved")
		self.assertEqual(exits("Life Goal", g), ["Done"])
		goals.close(g, "Not Achieved")
		self.assertEqual(exits("Life Goal", g), ["Discarded"])
		goals.close(g, "In Progress")
		someday.park("Life Goal", g)
		self.assertEqual(exits("Life Goal", g), ["Parked"])
		someday.bring_back("Life Goal", g)
		self.assertEqual(exits("Life Goal", g), [])
		trash.delete("Life Goal", g)
		self.assertEqual(exits("Life Goal", g), ["Discarded"])

	def test_open_goal_dropped(self):
		g = goals.create("ux7 g2", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		goals.set_status(g, "Dropped")
		self.assertEqual(exits("Life Goal", g), ["Discarded"])
		goals.set_status(g, "Active")
		self.assertEqual(exits("Life Goal", g), [])


class TestCaptureAndIdeaExits(OutboxCase):
	def item_with(self, *titles):
		created = inbox.create_item(space=PRIVATE, title="ux7 capture", source_type="Message", raw_text="x")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		inbox.submit_result(created["name"], summary_md="s", proposals=[
			{"kind": "Task", "preview": t, "payload": {"title": t, "area": "Tea"}} for t in titles])
		self.as_user(OWNER)
		return created["name"], frappe.get_all("Life Proposal", filters={"inbox_item": created["name"]}, pluck="name", order_by="sort_order")

	def test_accepted_is_done(self):
		item, props = self.item_with("ux7 a", "ux7 b")
		review.decide(props[0], "accept")
		self.assertEqual(exits("Life Inbox Item", item), [])  # still in the Inbox
		review.decide(props[1], "reject")
		self.assertEqual(exits("Life Inbox Item", item), ["Done"])

	def test_all_rejected_is_discarded_and_undo_reverses(self):
		item, props = self.item_with("ux7 c")
		review.decide(props[0], "reject")
		self.assertEqual(exits("Life Inbox Item", item), ["Discarded"])

	def test_undo_of_an_accept_reverses(self):
		from lifeos.api import reset

		item, props = self.item_with("ux7 d")
		review.decide(props[0], "accept")
		self.assertEqual(exits("Life Inbox Item", item), ["Done"])
		reset.undo_decision(props[0]) if hasattr(reset, "undo_decision") else reset.undo([{"op": "unaccept", "proposal": props[0]}])
		self.assertEqual(exits("Life Inbox Item", item), [])

	def test_just_keep_is_done_and_delete_is_discarded(self):
		created = inbox.create_item(space=PRIVATE, title="ux7 keep", source_type="Message", raw_text="x", intent="Just keep")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		inbox.submit_result(created["name"], transcript_md="x")
		self.as_user(OWNER)
		self.assertEqual(exits("Life Inbox Item", created["name"]), ["Done"])
		other = inbox.create_item(space=PRIVATE, title="ux7 junk", source_type="Message", raw_text="x")
		trash.delete("Life Inbox Item", other["name"])
		self.assertEqual(exits("Life Inbox Item", other["name"]), ["Discarded"])

	def test_something_parked_new_is_brought_back_and_purged(self):
		parked = someday.create("ux7 parked", space=PRIVATE, area=self.areas["Tea"])["name"]
		self.assertEqual(exits("Life Task", parked), ["Parked"])
		someday.bring_back("Life Task", parked)
		self.assertEqual(exits("Life Task", parked), [])
		parked2 = someday.create("ux7 parked 2", space=PRIVATE, area=self.areas["Tea"])["name"]
		someday.purge("Life Task", parked2)
		self.assertEqual(exits("Life Task", parked2), ["Parked"])  # it had already left the plate: that exit stands


class TestInAndOut(OutboxCase):
	def test_in_counts_nothing_twice(self):
		a, b = outbox.period_bounds("week")
		before = outbox_api.in_count(PRIVATE, None, a, b)
		self.task("ux7 direct")  # +1
		item = inbox.create_item(space=PRIVATE, title="ux7 in", source_type="Message", raw_text="x")  # +1
		self.task("ux7 from capture", inbox_item=item["name"])  # from a capture: 0
		someday.create("ux7 in parked", space=PRIVATE, area=self.areas["Tea"])  # a task made directly, parked: +1
		goals.create("ux7 in goal", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")  # +1
		self.assertEqual(outbox_api.in_count(PRIVATE, None, a, b) - before, 4)

	def test_today_line_matches_its_lists(self):
		t = self.task("ux7 line")
		tasks.set_status(t.name, "Done")
		line = counts.get(space=PRIVATE, which="week")  # issue 55: the line moved from Today to Brain > Activity
		for key, pile in (("in", "in"), ("out", "all")):
			door = line[key]
			self.assertEqual(door["to"]["path"], "/brain/outbox")
			self.assertEqual(door["to"]["query"]["pile"], pile)
			rows = outbox_api.list(space=PRIVATE, pile=pile, period="week", page_length=500)
			self.assertEqual(door["n"], len(rows["rows"]))
			self.assertEqual(door["n"], rows["total"])
		listed = outbox_api.list(space=PRIVATE, pile="Done", page_length=500)
		self.assertIn(t.name, [r.record for r in listed["rows"]])
		self.assertEqual(listed["tabs"]["all"], sum(listed["tabs"][p] for p in outbox.PILES))

	def test_lens_keeps_to_the_area(self):
		t = self.task("ux7 lens", area=self.areas["Money"])
		tasks.set_status(t.name, "Done")
		tea = outbox_api.list(space=PRIVATE, pile="Done", area=self.areas["Tea"], page_length=500)
		self.assertNotIn(t.name, [r.record for r in tea["rows"]])

	def test_chart_has_eight_weeks(self):
		weeks = outbox_api.chart(space=PRIVATE)["weeks"]
		self.assertEqual(len(weeks), 8)
		self.assertEqual(getdate(weeks[-1]["week_of"]).weekday(), 0)


class TestBringBack(OutboxCase):
	def exit_of(self, doctype, name):
		return frappe.db.get_value("Life Exit", {"record_doctype": doctype, "record_name": name, "reversed": 0})

	def test_reopen_unpark_and_restore(self):
		done = self.task("ux7 bb done")
		tasks.set_status(done.name, "Done")
		outbox_api.bring_back(self.exit_of("Life Task", done.name))
		self.assertEqual(frappe.db.get_value("Life Task", done.name, "status"), "Open")
		self.assertEqual(exits("Life Task", done.name), [])

		parked = self.task("ux7 bb parked")
		someday.park("Life Task", parked.name)
		outbox_api.bring_back(self.exit_of("Life Task", parked.name))
		self.assertEqual(frappe.db.get_value("Life Task", parked.name, "status"), "Open")

		gone = self.task("ux7 bb deleted")
		trash.delete("Life Task", gone.name)
		outbox_api.bring_back(self.exit_of("Life Task", gone.name))
		self.assertTrue(frappe.db.exists("Life Task", gone.name))
		self.assertEqual(exits("Life Task", gone.name), [])

	def test_agents_and_readers_cannot(self):
		t = self.task("ux7 bb agent")
		tasks.set_status(t.name, "Done")
		e = self.exit_of("Life Task", t.name)
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, outbox_api.bring_back, e)
		self.assertRaises(frappe.PermissionError, outbox_api.list, space=PRIVATE)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, outbox_api.bring_back, e)


class TestListFilters(LifeTestCase):
	def names(self, rows, key="name"):
		return {r[key] for r in rows}

	def test_task_due_filter(self):
		now = getdate(today())
		late = self.make("Life Task", title="ux1 late", due_date=add_days(now, -3))
		due = self.make("Life Task", title="ux1 today", due_date=now)
		far = self.make("Life Task", title="ux1 far", due_date=add_days(now, 40))
		none = self.make("Life Task", title="ux1 no date")
		get = lambda **f: self.names(tasks.list(space=PRIVATE, page_length=100, **f)["tasks"])  # noqa: E731
		self.assertIn(late.name, get(due="overdue"))
		self.assertNotIn(due.name, get(due="overdue"))
		self.assertEqual({late.name, due.name} & get(due="today"), {due.name})
		both = get(due="today,overdue")
		self.assertTrue({late.name, due.name} <= both)
		self.assertFalse({far.name, none.name} & both)
		self.assertIn(none.name, get(due="none"))
		self.assertNotIn(due.name, get(due="none"))
		self.assertIn(due.name, get(due="week"))
		self.assertNotIn(far.name, get(due="week"))
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, due="sometime")
		# the Today numbers are counted with the same filters as the lists they link to
		t = today_api.get(space=PRIVATE)
		self.assertEqual(t["tasks"]["due"], tasks.list(space=PRIVATE, due="today,overdue")["total"])
		self.assertEqual(t["tasks"]["overdue"], tasks.list(space=PRIVATE, due="overdue")["total"])
		self.assertEqual(t["open_loops"], tasks.list(space=PRIVATE, loops=1)["total"])

	def test_task_done_loops_sort_and_completed(self):
		goal = self.make("Life Goal", title="ux1 goal", horizon="Long term", area=self.areas["Tea"])
		a = self.make("Life Task", title="ux1 b open", goal=goal.name, area=self.areas["Tea"])
		b = self.make("Life Task", title="ux1 a done", goal=goal.name, area=self.areas["Tea"], status="Done")
		c = self.make("Life Task", title="ux1 c carried", goal=goal.name, area=self.areas["Tea"], status="Carried")
		get = lambda **f: tasks.list(space=PRIVATE, goal=goal.name, page_length=100, **f)  # noqa: E731
		self.assertEqual(self.names(get()["tasks"]), {a.name})
		self.assertEqual(self.names(get(done=1)["tasks"]), {a.name, b.name})
		self.assertEqual(self.names(get(status="Carried")["tasks"]), {c.name})
		# "4 of 10 tasks done" on a goal card: the total equals the list with Show done and archived records
		card = next(g for g in goals.list(space=PRIVATE, horizon="Long term")["goals"] if g["name"] == goal.name)
		self.assertEqual(card["tasks_counted"], get(done=1, include_archived=1)["total"])
		self.assertEqual([t["title"] for t in get(done=1, sort="title")["tasks"]], ["ux1 a done", "ux1 b open"])
		self.assertEqual([t["title"] for t in get(done=1, sort="title", dir="desc")["tasks"]], ["ux1 b open", "ux1 a done"])
		self.assertEqual([t["title"] for t in get(done=1, sort="title; drop table x")["tasks"]][:0], [])  # an unknown sort is ignored
		self.assertEqual(self.names(get(status="Done", completed_from=today(), completed_to=today())["tasks"]), {b.name})
		self.assertEqual(get(status="Done", completed_from=add_days(today(), 1))["total"], 0)
		old = self.make("Life Task", title="ux1 loop", goal=goal.name, area=self.areas["Tea"])
		frappe.db.set_value("Life Task", old.name, "creation", add_days(today(), -30), update_modified=False)
		self.assertEqual(self.names(get(loops=1)["tasks"]), {old.name})
		self.assertEqual(tasks.list(space=PRIVATE, loops=1)["total"], tasks.open_loops(space=PRIVATE)["total"])

	def test_area_filter_takes_sub_areas(self):
		career = self.life["Career"]  # issue 11: an area of life with its parts
		sub = self.make("Life Area", area_name="ux1 Estate", parent_area=career)
		t = self.make("Life Task", title="ux1 in sub", area=sub.name)
		unfiled = self.make("Life Task", title="ux1 unfiled")
		frappe.db.set_value("Life Task", unfiled.name, {"area": None, "area_guessed": 0})  # issue 13 guesses one on save
		self.assertIn(t.name, self.names(tasks.list(space=PRIVATE, area=career, page_length=100)["tasks"]))
		self.assertNotIn(t.name, self.names(tasks.list(space=PRIVATE, area=self.areas["Money"], page_length=100)["tasks"]))
		none = self.names(tasks.list(space=PRIVATE, area="none", page_length=100)["tasks"])
		self.assertIn(unfiled.name, none)
		self.assertNotIn(t.name, none)
		tree = {a["name"]: a for a in area_api.tree(space=PRIVATE)["areas"]}
		self.assertEqual(tree[career]["open_tasks"], tasks.list(space=PRIVATE, area=career)["total"])

	def test_inbox_filters(self):
		a = self.make("Life Inbox Item", title="ux1 voice", source_type="Voice Note", status="New", area=self.areas["Tea"])
		b = self.make("Life Inbox Item", title="ux1 mail", source_type="Email", status="New")
		frappe.db.set_value("Life Inbox Item", b.name, "received_on", add_days(today(), -10))
		get = lambda **f: inbox.list(space=PRIVATE, page_length=100, **f)  # noqa: E731
		self.assertEqual({a.name, b.name} & self.names(get(source_type="Voice Note")["items"]), {a.name})
		self.assertEqual({a.name, b.name} & self.names(get(area=self.areas["Tea"])["items"]), {a.name})
		self.assertEqual({a.name, b.name} & self.names(get(area="none")["items"]), {b.name})
		self.assertEqual({a.name, b.name} & self.names(get(from_date=add_days(today(), -1))["items"]), {a.name})
		self.assertEqual({a.name, b.name} & self.names(get(to_date=add_days(today(), -5))["items"]), {b.name})
		res = get(status="New", source_type="Email")
		self.assertEqual(res["total"], len(res["items"]))
		self.assertEqual(get(status='["New", "Processing"]')["total"], get(status="New")["total"] + get(status="Processing")["total"])
		frappe.get_doc({"doctype": "Life Proposal", "space": PRIVATE, "inbox_item": a.name, "kind": "Task", "preview": "x",
			"payload": "{}", "confidence": 0.9, "status": "Pending"}).insert(ignore_permissions=True)
		res = get(source_type="Voice Note")
		row = next(r for r in res["items"] if r["name"] == a.name)
		self.assertEqual((row["pending"], row["proposals"], row["area_name"]), (1, 1, "Tea"))
		self.assertEqual(res["pending_total"], sum(r["pending"] for r in res["items"]))

	def test_open_goal_filters(self):
		sub = self.make("Life Area", area_name="ux1 Garden", parent_area=self.areas["Money"])
		a = self.make("Life Goal", title="ux1 active", horizon="Long term", area=sub.name)
		h = self.make("Life Goal", title="ux1 hold", horizon="Long term", area=self.areas["Money"], on_hold=1)
		get = lambda **f: goals.list(space=PRIVATE, horizon="Long term", **f)  # noqa: E731
		self.assertEqual(self.names(get(area=self.areas["Money"])["goals"]), {a.name, h.name})
		self.assertEqual(self.names(get(area=self.areas["Money"], filters=[["on_hold", "=", 0]])["goals"]), {a.name})
		self.assertEqual(get(area=self.areas["Money"], filters=[["on_hold", "=", 1]])["total"], 1)
		self.assertEqual(get(area=self.areas["Money"], state="achieved")["total"], 0)
		tree = {r["name"]: r for r in area_api.tree(space=PRIVATE)["areas"]}
		self.assertEqual(tree[self.areas["Money"]]["goals"], goals.list(space=PRIVATE, area=self.areas["Money"])["total"])
		self.assertRaises(frappe.ValidationError, goals.list, space=PRIVATE, state="Nope")

	def test_vault_filters(self):
		person = self.make("Life Person", full_name="ux1 Holder")
		now = getdate(today())
		gone = self.make("Life Vault Document", title="ux1 expired", doc_type="ID", holder=person.name, expiry_date=add_days(now, -5))
		soon = self.make("Life Vault Document", title="ux1 soon", doc_type="Travel", expiry_date=add_days(now, 30), area=self.areas["Personal"])
		later = self.make("Life Vault Document", title="ux1 later", doc_type="Travel", expiry_date=add_days(now, 300))
		never = self.make("Life Vault Document", title="ux1 never", doc_type="Tax")
		mine = {gone.name, soon.name, later.name, never.name}
		get = lambda **f: mine & self.names(vault.list(space=PRIVATE, **f)["documents"])  # noqa: E731
		self.assertEqual(get(expiry="expired"), {gone.name})
		self.assertEqual(get(expiry="soon"), {soon.name})
		self.assertEqual(get(expiry="later"), {later.name})
		self.assertEqual(get(expiry="none"), {never.name})
		self.assertEqual(get(holder=person.name), {gone.name})
		self.assertEqual(get(holder="none"), {soon.name, later.name, never.name})
		self.assertEqual(get(doc_type="Travel"), {soon.name, later.name})
		self.assertEqual(get(area=self.areas["Personal"]), {soon.name})
		self.assertRaises(frappe.ValidationError, vault.list, space=PRIVATE, expiry="whenever")
		res = vault.list(space=PRIVATE, expiry="soon")
		self.assertEqual(res["total"], len(res["documents"]))
		self.assertEqual(res["soon"], res["total"])
		self.assertEqual(today_api.get(space=PRIVATE)["vault_soon"], res["total"])
		self.assertEqual(vault.list(space=PRIVATE)["expired"], vault.list(space=PRIVATE, expiry="expired")["total"])

	def test_chat_filters(self):
		goal = self.make("Life Goal", title="ux1 chat goal", horizon="Long term", area=self.areas["Tea"])
		a = chats.log(space=PRIVATE, title="ux1 chat open", area=self.areas["Tea"], goal=goal.name, open_items=["Follow up"])["name"]
		b = chats.log(space=PRIVATE, title="ux1 chat old", date=add_days(today(), -20))["name"]
		mine = {a, b}
		get = lambda **f: chats.list(space=PRIVATE, **f)  # noqa: E731
		self.assertEqual(mine & self.names(get(open_items=1)["chats"]), {a})
		self.assertEqual(mine & self.names(get(area=self.areas["Tea"])["chats"]), {a})
		self.assertEqual(mine & self.names(get(area="none")["chats"]), {b})
		self.assertEqual(mine & self.names(get(goal=goal.name)["chats"]), {a})
		self.assertEqual(mine & self.names(get(from_date=add_days(today(), -2))["chats"]), {a})
		self.assertEqual(mine & self.names(get(to_date=add_days(today(), -10))["chats"]), {b})
		res = get()
		self.assertEqual(res["with_open_items"], get(open_items=1)["total"])
		tea = next(x for x in res["by_area"] if x["area"] == self.areas["Tea"])
		self.assertEqual(tea["count"], get(area=self.areas["Tea"])["total"])
		self.assertEqual(sum(x["count"] for x in res["by_area"]), res["total"])
		for g in ("day", "area", "goal"):
			self.assertEqual(get(group_by=g)["total"], res["total"])
		one = chats.get(a)
		self.assertEqual((one["title"], one["open_count"], one["area_name"]), ("ux1 chat open", 1, "Tea"))
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, chats.get, a)

	def test_library_list(self):
		goal = self.make("Life Goal", title="ux1 note goal", horizon="Long term", area=self.areas["Tea"])
		a = self.make("Life Note", title="ux1 reference", area=self.areas["Tea"], content_md="a")
		b = self.make("Life Note", title="ux1 goal note", area=self.areas["Tea"], goal=goal.name, content_md="b")
		c = self.make("Life Note", title="ux1 loose", content_md="c")
		mine = {a.name, b.name, c.name}
		get = lambda **f: library.list(space=PRIVATE, page_length=100, **f)  # noqa: E731
		self.assertEqual(mine & self.names(get(area=self.areas["Tea"])["notes"]), {a.name, b.name})
		self.assertEqual(mine & self.names(get(area=self.areas["Tea"], goal="none")["notes"]), {a.name})
		self.assertEqual(mine & self.names(get(goal=goal.name)["notes"]), {b.name})
		self.assertEqual(mine & self.names(get(area="none")["notes"]), {c.name})
		self.assertEqual(goals.get(goal.name)["tabs"]["notes"], get(goal=goal.name, collection="all")["total"])

	def test_archive_filters(self):
		t = self.make("Life Task", title="ux1 archived task", area=self.areas["Tea"], status="Done")
		n = self.make("Life Note", title="ux1 archived note", area=self.areas["Money"], content_md="x")
		archive_rules.set_archived("Life Task", t.name, True, "Auto")
		archive_rules.set_archived("Life Note", n.name, True, "Manual")
		mine = {t.name, n.name}
		get = lambda **f: archive.list(space=PRIVATE, page_length=100, **f)  # noqa: E731
		names = lambda res: mine & {r["ref_name"] for r in res["records"]}  # noqa: E731
		self.assertEqual(names(get()), mine)
		self.assertEqual(names(get(doctype="Life Task")), {t.name})
		self.assertEqual(names(get(area=self.areas["Money"])), {n.name})
		self.assertEqual(names(get(reason="Auto")), {t.name})
		self.assertEqual(names(get(reason="Auto", archived_from=today(), archived_to=today())), {t.name})
		self.assertEqual(names(get(reason="Auto", archived_from=add_days(today(), 1))), set())
		res = get(doctype="Life Note", area=self.areas["Money"])
		self.assertEqual(res["total"], len(res["records"]))

	def test_calendar_entry(self):
		d = calendar_api.add_important_date(space=PRIVATE, title="ux1 birthday", day=3, month=4)["name"]
		e = calendar_api.add_event(space=PRIVATE, subject="ux1 event", starts_on=f"{today()} 10:00:00")["name"]
		self.assertEqual(calendar_api.entry("date", d)["title"], "ux1 birthday")
		self.assertEqual(calendar_api.entry("event", e)["title"], "ux1 event")
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, calendar_api.entry, "date", d)
		self.assertRaises(frappe.PermissionError, calendar_api.entry, "event", e)


NO_SPACE_SCREEN = "ux2-test-screen"


class TestViewState(LifeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		# only the rows these tests made: the test site also holds views saved through the browser by the same users
		frappe.db.delete("Life View State", {"space": ("in", [PRIVATE, SHARED])})
		frappe.db.delete("Life View State", {"screen": NO_SPACE_SCREEN})
		super().tearDown()

	def mine(self):
		"""The session user's saved views in the test spaces."""
		return {k: v for k, v in views.get_all().items() if k.split("|", 1)[1] in (PRIVATE, SHARED)}

	def test_a_user_reads_and_writes_only_their_own_states(self):
		views.save("tasks", PRIVATE, {"query": {"status": "Done"}, "view": "table"})
		views.save("tasks", SHARED, {"query": {"priority": "I"}})
		views.save("vault", PRIVATE, {"query": {}})
		mine = self.mine()
		self.assertEqual(mine[f"tasks|{PRIVATE}"], {"query": {"status": "Done"}, "view": "table"})
		self.assertEqual(mine[f"tasks|{SHARED}"]["query"], {"priority": "I"})
		self.assertEqual(len(mine), 3)
		# saving again replaces: one row per user, screen and space
		views.save("tasks", PRIVATE, {"query": {}})
		self.assertEqual(views.get_all()[f"tasks|{PRIVATE}"], {"query": {}})
		self.assertEqual(frappe.db.count("Life View State", {"user": OWNER, "screen": "tasks", "space": PRIVATE}), 1)
		row = frappe.db.get_value("Life View State", {"user": OWNER, "screen": "tasks", "space": PRIVATE}, "name")

		self.as_user(FAMILY)
		self.assertEqual(self.mine(), {})  # nothing of the owner's, although both are members of the shared space
		views.save("tasks", SHARED, {"query": {"status": "Waiting"}})
		self.assertEqual(self.mine(), {f"tasks|{SHARED}": {"query": {"status": "Waiting"}}})
		self.assertFalse(any(k.endswith(f"|{PRIVATE}") for k in views.get_all()))
		self.assertRaises(frappe.PermissionError, views.save, "tasks", PRIVATE, {"query": {}})  # not a member of that space
		# the DocType itself is closed too: no listing, reading or changing another person's row
		self.assertEqual(frappe.get_list("Life View State", filters={"user": OWNER}), [])
		self.assertEqual(len(frappe.get_list("Life View State", filters={"space": ("in", [PRIVATE, SHARED])})), 1)
		self.assertEqual({r.user for r in frappe.get_list("Life View State", fields=["user"])}, {FAMILY})
		self.assertFalse(frappe.has_permission("Life View State", "read", frappe.get_doc("Life View State", row)))
		self.assertFalse(frappe.has_permission("Life View State", "write", frappe.get_doc("Life View State", row)))
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Life View State", row).check_permission, "write")

		self.as_user(OWNER)
		self.assertEqual(views.get_all()[f"tasks|{SHARED}"]["query"], {"priority": "I"})  # the family member's save did not touch it

	def test_agents_have_no_saved_views(self):
		views.save("tasks", PRIVATE, {"query": {"status": "Done"}})
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, views.get_all)
		self.assertRaises(frappe.PermissionError, views.save, "tasks", PRIVATE, {"query": {}})
		self.assertRaises(frappe.PermissionError, frappe.get_list, "Life View State")
		self.assertFalse(frappe.has_permission("Life View State", "read"))
		self.assertFalse(frappe.has_permission("Life View State", "create"))

	def test_what_is_saved(self):
		views.save("tasks", PRIVATE, {"query": {"status": "Done"}, "open": "task:abc"})
		self.assertNotIn("open", views.get_all()[f"tasks|{PRIVATE}"])  # the open record is never saved
		self.assertRaises(frappe.ValidationError, views.save, "", PRIVATE, {})
		self.assertRaises((frappe.ValidationError, frappe.FrappeTypeError), views.save, "tasks", PRIVATE, [1, 2])  # refused by the type hint since pre-step 6
		self.assertRaises(frappe.ValidationError, views.save, "tasks", PRIVATE, {"query": {"x": "y" * 30000}})
		self.assertRaises(frappe.PermissionError, views.save, "tasks", "No such space", {})
		views.save(NO_SPACE_SCREEN, None, {"view": "a"})  # a screen that is not tied to a space
		self.assertEqual(views.get_all()[f"{NO_SPACE_SCREEN}|"], {"view": "a"})
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, views.get_all)


class TestStandardFilters(LifeTestCase):
	def names(self, rows, key="name"):
		return {r[key] for r in rows}

	def test_field_names_are_checked_against_the_doctype(self):
		for bad in ("no_such_field", "title; drop table tabUser", "t.title", "`title`", "space or 1=1", "", "also_in", "organisation_section"):
			self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[[bad, "=", "x"]])
			self.assertRaises(frappe.ValidationError, std_filters, "Life Task", [[bad, "=", "x"]])
		for bad in ("no_such_field desc", "title desc; drop table tabUser", "title sideways", "title desc nulls"):
			self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, order_by=bad)
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["title", "regexp", "x"]])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["title", "=", ["a", "b"]]])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["title"]])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["Life Note", "title", "=", "x"]])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, filters=[["title", "like", "x"]] * 30)
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, fields=["password"])
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, summary={"fields": ["nope"], "aggregates": []})
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE, summary={"fields": ["status"], "aggregates": [{"function": "sleep"}]})
		self.assertRaises(frappe.ValidationError, tasks.list, space=PRIVATE,
			summary={"fields": ["status"], "aggregates": [{"function": "max", "fieldname": "1); drop table x; --"}]})
		# a value is always a parameter, never part of the SQL
		conds, values = std_filters("Life Task", [["title", "=", "x' or '1'='1"]], "t")
		self.assertEqual(conds, ["ifnull(t.`title`, '') = %(sf0)s"])
		self.assertEqual(values, {"sf0": "x' or '1'='1"})
		self.assertEqual(std_order("Life Task", "due_date desc, title asc", "t"), "t.`due_date` desc, t.`title` asc")
		self.assertEqual(std_order("Life Task", "priority desc", "t", {"priority": "case t.priority when 'I' then 1 else 5 end"}),
			"case t.priority when 'I' then 1 else 5 end desc")
		self.assertIsNone(std_order("Life Task", "", "t"))

	def test_task_filters_operators_and_sort(self):
		now = getdate(today())
		a = self.make("Life Task", title="ux2 alpha", priority="I", due_date=add_days(now, 2), area=self.areas["Tea"])
		b = self.make("Life Task", title="ux2 beta", priority="II", due_date=add_days(now, 9), waiting_on="the bank", status="Waiting")
		c = self.make("Life Task", title="ux2 gamma")
		get = lambda **kw: tasks.list(space=PRIVATE, page_length=100, filters=[["title", "like", "ux2"], *kw.pop("f", [])], **kw)  # noqa: E731
		self.assertEqual(self.names(get()["tasks"]), {a.name, b.name, c.name})
		self.assertEqual(get()["total"], 3)
		self.assertEqual(self.names(get(f=[["priority", "=", "I"]])["tasks"]), {a.name})
		self.assertEqual(self.names(get(f=[["priority", "!=", "I"]])["tasks"]), {b.name, c.name})
		self.assertEqual(self.names(get(f=[["priority", "in", ["I", "II"]]])["tasks"]), {a.name, b.name})
		self.assertEqual(self.names(get(f=[["priority", "not in", "I, II"]])["tasks"]), {c.name})
		self.assertEqual(self.names(get(f=[["due_date", "is", "not set"]])["tasks"]), {c.name})
		self.assertEqual(self.names(get(f=[["due_date", "is", "set"]])["tasks"]), {a.name, b.name})
		self.assertEqual(self.names(get(f=[["waiting_on", "is", "set"]])["tasks"]), {b.name})
		self.assertEqual(self.names(get(f=[["due_date", ">", str(add_days(now, 5))]])["tasks"]), {b.name})
		self.assertEqual(self.names(get(f=[["due_date", "between", [str(now), str(add_days(now, 3))]]])["tasks"]), {a.name})
		self.assertEqual(self.names(get(f=[["title", "not like", "beta"]])["tasks"]), {a.name, c.name})
		self.assertEqual(self.names(get(f=[["Life Task", "priority", "=", "II"]])["tasks"]), {b.name})
		self.assertEqual(self.names(get(f=[["creation", "timespan", "today"]])["tasks"]), {a.name, b.name, c.name})
		# standard filters narrow the list's own filters: they never widen them, and the space is always applied
		self.assertEqual(self.names(get(area=self.areas["Tea"])["tasks"]), {a.name})
		self.assertEqual(self.names(get(status="Waiting", f=[["priority", "=", "II"]])["tasks"]), {b.name})
		self.assertEqual(get(f=[["space", "=", SHARED]])["total"], 0)
		self.assertEqual([t["title"] for t in get(order_by="title desc")["tasks"]], ["ux2 gamma", "ux2 beta", "ux2 alpha"])
		self.assertEqual([t["title"] for t in get(order_by="priority desc, title asc")["tasks"]], ["ux2 gamma", "ux2 beta", "ux2 alpha"])
		self.assertEqual(get(fields=["waiting_on", "modified"])["tasks"][0].keys() >= {"waiting_on", "modified", "title"}, True)
		s = get(summary={"fields": ["status"], "aggregates": [{"function": "count"}], "order_by": "_aggregate_0 desc", "totals": 1})["summary"]
		self.assertEqual({r["status"]: r["_aggregate_0"] for r in s["rows"]}, {"Open": 2, "Waiting": 1})
		self.assertEqual(s["total"], 2)
		self.assertEqual(s["totals"]["_aggregate_0"], 3)
		s = get(summary={"fields": ["area"], "aggregates": [{"function": "count"}, {"function": "max", "fieldname": "due_date"}]})["summary"]
		tea = next(r for r in s["rows"] if r["area"] == self.areas["Tea"])
		self.assertEqual((tea["area__label"], tea["_aggregate_0"], tea["_aggregate_1"]), ("Tea", 1, str(add_days(now, 2))))

	def test_every_list_takes_standard_filters(self):
		tea = self.areas["Tea"]
		goal = self.make("Life Goal", title="ux2 goal", horizon="Long term", area=tea)
		self.make("Life Goal", title="ux2 other", horizon="Long term", area=tea)
		note = self.make("Life Note", title="ux2 note", area=tea, content_md="x")
		self.make("Life Note", title="ux2 second", area=tea, content_md="x")
		doc = self.make("Life Vault Document", title="ux2 passport", doc_type="Travel", area=tea, number_last4="1234")
		self.make("Life Vault Document", title="ux2 lease", doc_type="Property", area=tea)
		chat = self.make("Life Chat Log", title="ux2 chat", date=today(), area=tea, assistant="ChatGPT")
		self.make("Life Chat Log", title="ux2 chat two", date=today(), area=tea)
		item = self.make("Life Inbox Item", title="ux2 item", source_type="Email")
		self.make("Life Inbox Item", title="ux2 item two")
		like = [["title", "like", "ux2"]]
		self.assertEqual(self.names(goals.list(space=PRIVATE, filters=[*like, ["title", "=", "ux2 goal"]])["goals"]), {goal.name})
		self.assertEqual(goals.list(space=PRIVATE, filters=like)["total"], 2)
		self.assertEqual([p["title"] for p in goals.list(space=PRIVATE, filters=like, order_by="title desc")["goals"]], ["ux2 other", "ux2 goal"])
		self.assertEqual(self.names(vault.list(space=PRIVATE, filters=[*like, ["number_last4", "=", "1234"]])["documents"]), {doc.name})
		self.assertEqual(vault.list(space=PRIVATE, filters=like)["total"], 2)
		self.assertEqual(vault.list(space=PRIVATE, filters=like, fields=["issue_date"])["documents"][0].keys() >= {"issue_date"}, True)
		self.assertEqual(self.names(chats.list(space=PRIVATE, filters=[*like, ["assistant", "=", "ChatGPT"]])["chats"]), {chat.name})
		self.assertEqual(self.names(inbox.list(space=PRIVATE, filters=[*like, ["source_type", "=", "Email"]])["items"]), {item.name})
		self.assertEqual(inbox.list(space=PRIVATE, filters=like)["total"], 2)
		# the cross-type lists filter on the columns of Life Index
		self.assertEqual(self.names(library.list(space=PRIVATE, filters=[["title", "=", "ux2 note"]])["notes"]), {note.name})
		got = timeline.get(space=PRIVATE, filters=[*like, ["ref_doctype", "=", "Life Vault Document"]])
		self.assertEqual(got["total"], 2)
		self.assertEqual({e["ref_name"] for d in got["days"] for e in d["entries"]} >= {doc.name}, True)
		self.assertEqual(timeline.get(space=PRIVATE, filters=like, summary={"fields": ["kind"], "aggregates": [{"function": "count"}]})["summary"]["total"] >= 4, True)
		frappe.db.set_value("Life Note", note.name, {"is_archived": 1, "archived_on": today(), "archive_reason": "Manual"})
		frappe.get_doc("Life Note", note.name).save()
		self.assertEqual({r["ref_name"] for r in archive.list(space=PRIVATE, filters=[["kind", "=", "Note"], *like])["records"]}, {note.name})
		for method in (goals.list, vault.list, chats.list, inbox.list, library.list, archive.list):
			self.assertRaises(frappe.ValidationError, method, space=PRIVATE, filters=[["no_such_field", "=", 1]])
			self.assertRaises(frappe.ValidationError, method, space=PRIVATE, order_by="no_such_field desc")
		self.assertRaises(frappe.ValidationError, timeline.get, space=PRIVATE, filters=[["no_such_field", "=", 1]])
		# a second user still sees nothing from a private space, whatever the filters say
		self.as_user(FAMILY)
		for method in (tasks.list, goals.list, vault.list, chats.list, inbox.list, library.list, archive.list, timeline.get):
			self.assertRaises(frappe.PermissionError, method, space=PRIVATE, filters=[["space", "=", PRIVATE]])


class TestTabCounts(LifeTestCase):
	def test_tasks(self):
		tea, money = self.areas["Tea"], self.areas["Money"]
		self.make("Life Task", title="ux3t open", area=tea)
		self.make("Life Task", title="ux3t doing", area=tea, status="Doing")
		self.make("Life Task", title="ux3t waiting", area=tea, status="Waiting", waiting_on="the bank", due_date=today())
		self.make("Life Task", title="ux3t done", area=money, status="Done")
		self.make("Life Task", title="ux3t dropped", area=money, status="Dropped")
		old = self.make("Life Task", title="ux3t loop", area=money, status="Waiting", waiting_on="a reply")
		frappe.db.set_value("Life Task", old.name, "creation", add_days(today(), -30), update_modified=False)

		def check(**f):
			get = lambda **a: tasks.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(set(tabs), {"open", "loops", "Waiting", "Done", "Someday", "all"})
			self.assertEqual(tabs["open"], get(status="open_doing")["total"])
			self.assertEqual(tabs["loops"], get(status="open", loops=1)["total"])
			self.assertEqual(tabs["Waiting"], get(status="Waiting")["total"])
			self.assertEqual(tabs["Done"], get(status="Done")["total"])
			self.assertEqual(tabs["all"], get(status="all")["total"])
			# the counts do not depend on the tab that is asked for
			self.assertEqual(get(status="Done")["tabs"], tabs)
			self.assertEqual(get(status="open", loops=1)["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3t %"]]  # other tests of this class leave tasks in the space
		check()
		tabs = check(filters=mine)
		self.assertEqual((tabs["open"], tabs["loops"], tabs["Waiting"], tabs["Done"], tabs["all"]), (2, 1, 2, 1, 6))
		in_tea = check(area=tea, filters=mine)
		self.assertEqual((in_tea["open"], in_tea["loops"], in_tea["Waiting"], in_tea["Done"], in_tea["all"]), (2, 0, 1, 0, 3))
		check(due="today,overdue")
		self.assertEqual(check(filters=[["title", "like", "ux3t d"]])["all"], 3)
		# "open" in the API still holds Waiting tasks; the Open tab and every number that leads to it do not
		self.assertEqual(tasks.list(space=PRIVATE, filters=mine)["total"], 4)
		self.assertEqual(tasks.count(PRIVATE, area=tea), tasks.list(space=PRIVATE, area=tea)["tabs"]["open"])
		self.assertEqual(today_api.get(space=PRIVATE)["tasks"]["due"], tasks.list(space=PRIVATE, status="open_doing", due="today,overdue")["total"])

	def test_inbox(self):
		tea = self.areas["Tea"]
		for i, status in enumerate(["New", "Processing", "To Review", "To Review", "Failed", "Done"]):
			doc = self.make("Life Inbox Item", title=f"ux3 inbox {i}", source_type="Message", raw_text="x", area=tea if i % 2 else None)
			frappe.db.set_value("Life Inbox Item", doc.name, "status", status)

		def check(**f):
			get = lambda **a: inbox.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(tabs["To Review"], get(status="To Review")["total"])
			self.assertEqual(tabs["Waiting"], get(status='["New", "Processing"]')["total"])
			self.assertEqual(tabs["Failed"], get(status="Failed")["total"])
			self.assertEqual(tabs["Done"], get(status="Done")["total"])
			self.assertEqual(tabs["all"], get()["total"])
			self.assertEqual(get(status="Done")["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 inbox %"]]
		check()
		self.assertEqual(check(filters=mine), {"To Review": 2, "Waiting": 2, "Failed": 1, "Done": 1, "all": 6})
		self.assertEqual(check(area=tea, filters=mine), {"To Review": 1, "Waiting": 1, "Failed": 0, "Done": 1, "all": 3})
		check(source_type="Message")

	def test_open_goals(self):
		# set 6: projects became goals of type Open; their states are the Goals screen's tabs
		tea, money = self.areas["Tea"], self.areas["Money"]
		self.make("Life Goal", title="ux3 p active", horizon="Long term", area=tea)
		self.make("Life Goal", title="ux3 p active 2", horizon="Long term", area=money)
		self.make("Life Goal", title="ux3 p hold", horizon="Long term", area=tea, on_hold=1)
		dropped = self.make("Life Goal", title="ux3 p dropped", horizon="Long term", area=money)
		goals.set_status(dropped.name, "Dropped")
		done = self.make("Life Goal", title="ux3 p done", horizon="Long term", area=tea)
		goals.set_status(done.name, "Done")

		def check(**f):
			get = lambda **a: goals.list(space=PRIVATE, horizon="Long term", **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			for state in ("in_progress", "achieved", "closed", "someday", "all"):
				self.assertEqual(tabs[state], get(state=state)["total"], state)
			self.assertEqual(tabs["in_progress"], get()["total"])  # active and on hold
			self.assertEqual(get(state="achieved")["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 p %"]]
		check()
		self.assertEqual(check(filters=mine), {"in_progress": 3, "achieved": 1, "closed": 1, "someday": 0, "all": 5})
		self.assertEqual(check(area=tea, filters=mine), {"in_progress": 2, "achieved": 1, "closed": 0, "someday": 0, "all": 3})

	def test_archive(self):
		tea = self.areas["Tea"]
		task = self.make("Life Task", title="ux3 archived task", area=tea, status="Done")
		note = self.make("Life Note", title="ux3 archived note", area=tea, body_md="x")
		other = self.make("Life Note", title="ux3 archived note 2", area=self.areas["Money"], body_md="x")
		for doc in (task, note, other):
			archive.set(doc.doctype, doc.name)

		def check(**f):
			get = lambda **a: archive.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(set(tabs), {"all", "Life Task", "Life Note", "Life Inbox Item", "Life Chat Log", "Life Vault Document", "Life Journal Page"})
			for dt in tabs:
				self.assertEqual(tabs[dt], get(doctype=None if dt == "all" else dt)["total"], dt)
			self.assertEqual(get(doctype="Life Note")["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 archived %"]]
		check()
		tabs = check(filters=mine)
		self.assertEqual((tabs["all"], tabs["Life Task"], tabs["Life Note"], tabs["Life Chat Log"]), (3, 1, 2, 0))
		in_tea = check(area=tea, filters=mine)
		self.assertEqual((in_tea["all"], in_tea["Life Task"], in_tea["Life Note"]), (2, 1, 1))
		check(reason="Manual")

	def test_chats(self):
		tea = self.areas["Tea"]
		chats.log(space=PRIVATE, title="ux3 chat open", summary_md="s", open_items=["call the bank"], area=tea)
		chats.log(space=PRIVATE, title="ux3 chat quiet", summary_md="s", area=tea)
		chats.log(space=PRIVATE, title="ux3 chat open 2", summary_md="s", open_items=["write back"])

		def check(**f):
			get = lambda **a: chats.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(tabs["all"], get()["total"])
			self.assertEqual(tabs["open"], get(open_items=1)["total"])
			self.assertEqual(get(open_items=1)["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 chat %"]]
		check()
		self.assertEqual(check(filters=mine), {"all": 3, "open": 2})
		self.assertEqual(check(area=tea, filters=mine), {"all": 2, "open": 1})

	def test_vault(self):
		now = getdate(today())
		tea = self.areas["Tea"]
		self.make("Life Vault Document", title="ux3 expired", doc_type="Travel", area=tea, expiry_date=add_days(now, -5))
		self.make("Life Vault Document", title="ux3 soon", doc_type="Travel", area=tea, expiry_date=add_days(now, 30))
		self.make("Life Vault Document", title="ux3 soon 2", doc_type="Insurance", area=self.areas["Money"], expiry_date=add_days(now, 60))
		self.make("Life Vault Document", title="ux3 later", doc_type="Insurance", area=tea, expiry_date=add_days(now, 61))
		self.make("Life Vault Document", title="ux3 no date", doc_type="Other", area=tea)

		def check(**f):
			get = lambda **a: vault.list(space=PRIVATE, **f, **a)  # noqa: E731
			tabs = get()["tabs"]
			self.assertEqual(tabs["all"], get()["total"])
			self.assertEqual(tabs["soon"], get(expiry="soon")["total"])
			self.assertEqual(tabs["expired"], get(expiry="expired")["total"])
			self.assertEqual(get(expiry="expired")["tabs"], tabs)
			return tabs

		mine = [["title", "like", "ux3 %"], ["title", "not like", "ux3 private%"]]
		self.assertEqual(check(filters=mine), {"all": 5, "soon": 2, "expired": 1})
		self.assertEqual(check(area=tea, filters=mine), {"all": 4, "soon": 1, "expired": 1})
		self.assertEqual(check(doc_type="Insurance", filters=mine), {"all": 2, "soon": 1, "expired": 0})
		# the Expiring soon tab is the 60-day window Today counts
		self.assertEqual(check()["soon"], today_api.get(space=PRIVATE)["vault_soon"])

	def test_a_member_of_another_space_sees_only_their_own_counts(self):
		self.make("Life Task", title="ux3 private task")
		self.make("Life Task", title="ux3 shared task", space=SHARED)
		self.make("Life Goal", title="ux3 private goal", horizon="Long term", area=self.areas["Tea"])
		self.make("Life Vault Document", title="ux3 private doc", doc_type="Travel", area=self.areas["Tea"], expiry_date=add_days(today(), 10))
		chats.log(space=PRIVATE, title="ux3 private chat", summary_md="s", open_items=["x"])
		self.make("Life Inbox Item", title="ux3 private inbox", source_type="Message", raw_text="x")
		note = self.make("Life Note", title="ux3 private archived", body_md="x")
		archive.set("Life Note", note.name)
		owner_tabs = tasks.list(space=SHARED)["tabs"]
		self.assertEqual(owner_tabs["open"], 1)
		self.assertGreaterEqual(tasks.list(space=PRIVATE)["tabs"]["open"], 1)

		self.as_user(FAMILY)
		# the family member is in the shared space only: its counts are the shared space's, and the private space is refused
		self.assertEqual(tasks.list(space=SHARED)["tabs"], owner_tabs)
		for method in (tasks.list, inbox.list, goals.list, archive.list, chats.list, vault.list):
			self.assertRaises(frappe.PermissionError, method, space=PRIVATE)
			tabs = method(space=SHARED)["tabs"]
			self.assertEqual(sum(tabs.values()), 2 if method is tasks.list else 0, method.__module__)
		self.assertNotIn(PRIVATE, permissions.user_spaces())


class TestRecordPageTabs(LifeTestCase):
	"""The tab counts of the goal page equal the main screen's list filtered by that goal. (Area pages went in set 6: the
	lens narrows every list to an area, see test_permissions.)"""

	def test_goal_page(self):
		tea = self.areas["Tea"]
		p = self.make("Life Goal", title="ux3 page goal", horizon="Long term", area=tea)
		self.make("Life Task", title="ux3 page task", area=tea, goal=p.name)
		self.make("Life Task", title="ux3 page done", area=tea, goal=p.name, status="Done")
		self.make("Life Note", title="ux3 page note", area=tea, goal=p.name, content_md="see [[ux3 page goal]]")
		tabs = goals.get(p.name)["tabs"]
		self.assertEqual(tabs["tasks"], 1)
		self.assertEqual(tabs["notes"], 1)
		self.assertEqual(tabs["captures"], 0)
		self.assertEqual(tabs["chats"], 0)
		self.assertGreaterEqual(tabs["links"], 1)
		self.assertEqual(tabs["tasks"], tasks.list(space=PRIVATE, goal=p.name, status="open_doing")["total"])
		self.assertEqual(tabs["notes"], library.list(space=PRIVATE, goal=p.name, collection="all")["total"])
		self.assertEqual(tabs["chats"], chats.list(space=PRIVATE, goal=p.name)["total"])

	def test_other_space_member_cannot_read_the_counts(self):
		tea = self.areas["Tea"]
		p = self.make("Life Goal", title="ux3 hidden goal", horizon="Long term", area=tea)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, goals.get, p.name)
