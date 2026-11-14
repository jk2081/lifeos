import datetime

import frappe
from frappe.utils import add_days, add_to_date, getdate, now_datetime, today

from lifeos import datewords, index
from lifeos.api import area as area_api
from lifeos.api import projects as project_api
from lifeos.api import tasks, timeline
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
		project = self.make("Life Project", title="M4 project", area=self.areas["Tea"])
		a = self.make("Life Task", title="A later IV", due_date=add_days(today(), 9), priority="IV", area=self.areas["Tea"], project=project.name)
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
		self.assertEqual([t["name"] for t in tasks.list(space=PRIVATE, project=project.name)["tasks"]], [a.name])
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


class TestAreasProjectsTimeline(LifeTestCase):
	def test_also_in_shows_on_both_area_pages(self):
		note = self.make("Life Note", title="Land ceiling writ m4", area=self.areas["Money"], also_in=[{"area": self.areas["Tea"]}])
		home = area_api.get(self.areas["Money"])
		other = area_api.get(self.areas["Tea"])
		self.assertIn(note.name, [n["ref_name"] for n in home["notes"]])
		self.assertNotIn(note.name, [n["ref_name"] for n in home["references"]])
		self.assertIn(note.name, [n["ref_name"] for n in other["references"]])
		self.assertNotIn(note.name, [n["ref_name"] for n in other["notes"]])

	def test_area_page_gathers_everything(self):
		tea = self.areas["Tea"]
		sub = self.make("Life Area", area_name="Ghatia m4", parent_area=tea)
		project = self.make("Life Project", title="Mandir m4", area=tea)
		task = self.make("Life Task", title="Area task m4", area=tea, project=project.name)
		sub_task = self.make("Life Task", title="Sub-area task m4", area=sub.name)
		note = self.make("Life Note", title="Reference note m4", area=tea)
		project_note = self.make("Life Note", title="Project note m4", area=tea, project=project.name)
		doc = self.make("Life Vault Document", title="Contractor brief m4", area=tea)
		chat = self.make("Life Chat Log", title="Mandir chat m4", date=today(), area=tea, open_items=[{"text": "one"}, {"text": "two", "status": "Closed"}])
		archived = self.make("Life Note", title="Archived note m4", area=tea, is_archived=1)
		page = area_api.get(tea)
		self.assertIn(sub.name, [s["name"] for s in page["sub_areas"]])
		self.assertIn(project.name, [p["name"] for p in page["projects"]])
		task_names = [t["name"] for t in page["tasks"]]
		self.assertTrue(page["counts"]["open_tasks"] >= 2)
		notes = [n["ref_name"] for n in page["notes"]]
		self.assertIn(note.name, notes)
		self.assertNotIn(project_note.name, notes)  # a note with a project is not reference material
		self.assertNotIn(archived.name, notes)
		self.assertIn(doc.name, [d["ref_name"] for d in page["documents"]])
		self.assertEqual([c["open_items"] for c in page["chats"] if c["ref_name"] == chat.name], [1])
		self.assertTrue(len(page["timeline"]) <= 20 and task.name in [t["ref_name"] for t in page["timeline"]])
		self.assertIn(sub_task.name, [t["ref_name"] for t in page["timeline"]])
		self.assertIn(archived.name, [n["ref_name"] for n in area_api.get(tea, include_archived=1)["notes"]])
		tree = area_api.tree(space=PRIVATE)
		self.assertEqual([a["parent_area"] for a in tree["areas"] if a["name"] == sub.name], [tea])
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, area_api.get, tea)
		self.assertRaises(frappe.PermissionError, area_api.tree, space=PRIVATE)

	def test_projects_list_and_page(self):
		project = self.make("Life Project", title="Turnaround m4", area=self.areas["Tea"], outcome="A plan")
		t1 = self.make("Life Task", title="P task 1", area=self.areas["Tea"], project=project.name)
		t2 = self.make("Life Task", title="P task 2", area=self.areas["Tea"], project=project.name, status="Done")
		note = self.make("Life Note", title="P note", area=self.areas["Tea"], project=project.name)
		groups = project_api.list(space=PRIVATE)["groups"]
		card = next(p for g in groups for p in g["projects"] if p["name"] == project.name)
		self.assertEqual((card["tasks_total"], card["tasks_done"], card["area_name"]), (2, 1, "Tea"))
		page = project_api.get(project.name)
		self.assertEqual([t["name"] for t in page["tasks"]], [t1.name])
		self.assertEqual([t["name"] for t in page["done_tasks"]], [t2.name])
		self.assertEqual([n["ref_name"] for n in page["notes"]], [note.name])
		self.assertEqual(project_api.completion_info(project.name)["records"], 3)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, project_api.get, project.name)

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
