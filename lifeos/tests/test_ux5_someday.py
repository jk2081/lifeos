"""UX fixes, set 5: the count helper, Someday, the trash."""
import json

import frappe
from frappe.utils import add_days, add_months, getdate, today

from lifeos import counts, trash
from lifeos.api import goals, inbox, projects, someday, tasks
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


def _call_door(door, space=PRIVATE):
	"""Run the list a count links to, with the arguments that screen sends, and return its total."""
	q = door["to"]["query"]
	path = door["to"]["path"]
	if path == "/tasks":
		return tasks.list(space=space, status=q.get("status"), due=q.get("due"), filters=q.get("f"), page_length=1)["total"]
	if path == "/projects":
		return projects.list(space=space, status=q.get("status"), filters=q.get("f"), page_length=1)["total"]
	if path == "/goals":
		return goals.list(space=space, state=q.get("status"), filters=q.get("f"), page_length=1)["total"]
	if path == "/inbox":
		return inbox.list(space=space, status=json.dumps([q["status"]]), filters=q.get("f"), page_length=1)["total"]
	if path == "/someday":
		return someday.list(space=space, tab=q.get("tab") or "all", filters=q.get("f"), page_length=1)["total"]
	raise AssertionError(path)


class TestCounts(LifeTestCase):
	def test_every_count_equals_its_list(self):
		old = self.make("Life Task", title="ux5 stuck task", area=self.areas["Tea"])
		frappe.db.set_value("Life Task", old.name, "last_touched_on", add_days(today(), -200))
		self.make("Life Task", title="ux5 fresh task", area=self.areas["Tea"], status="Waiting", waiting_on="Kunal")
		band = counts.open_band(PRIVATE)
		for key in ("open_tasks", "stuck", "projects", "idle_projects", "goals", "inbox", "inbox_old"):
			self.assertEqual(band[key]["n"], _call_door(band[key]), key)
		self.assertGreaterEqual(band["stuck"]["n"], 1)
		self.assertIn("f", band["stuck"]["to"]["query"])
		inv = counts.inventory(PRIVATE)
		for row in inv["rows"]:
			cells = row["cells"]
			if row["key"] in ("tasks", "projects", "goals", "inbox", "someday"):
				for c in cells.values():
					self.assertEqual(c["n"], _call_door(c), row["key"])
			self.assertEqual(sum(cells[k]["n"] for k in ("under_30", "30_90", "90_180", "over_180")), cells["total"]["n"], row["key"])
		self.assertGreaterEqual(inv["rows"][0]["cells"]["over_180"]["n"], 1)

	def test_stuck_limit_marks_over(self):
		s = frappe.get_single("Life Settings")
		before = s.stuck_limit
		s.stuck_limit = 0
		s.save()
		try:
			t = self.make("Life Task", title="ux5 over limit", area=self.areas["Tea"])
			frappe.db.set_value("Life Task", t.name, "last_touched_on", add_days(today(), -100))
			self.assertTrue(counts.open_band(PRIVATE)["over_limit"])
		finally:
			frappe.set_user("Administrator")
			s = frappe.get_single("Life Settings")
			s.stuck_limit = before or 50
			s.save()


class TestSomeday(LifeTestCase):
	def test_park_task_project_goal_idea_and_leave_the_open_lists(self):
		t = self.make("Life Task", title="ux5 park me", area=self.areas["Tea"])
		created = str(t.creation)
		p = self.make("Life Project", title="ux5 parked project", area=self.areas["Tea"], status="Active")
		pt = [self.make("Life Task", title=f"ux5 project task {i}", area=self.areas["Tea"], project=p.name) for i in range(2)]
		g = self.make("Life Goal", title="ux5 parked goal", goal_type="Open", area=self.areas["Tea"])
		before = counts.open_tasks(PRIVATE)["n"]
		someday.park("Life Task", t.name, note="later")
		someday.park("Life Project", p.name)
		someday.park("Life Goal", g.name)
		idea = someday.create_idea("ux5 an idea", space=PRIVATE, area=self.areas["Tea"])
		self.assertEqual(counts.open_tasks(PRIVATE)["n"], before - 3)
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Someday")
		self.assertEqual(str(frappe.db.get_value("Life Task", t.name, "creation")), created)
		self.assertEqual(frappe.db.get_value("Life Goal", g.name, "outcome"), "In Progress")
		for x in pt:
			self.assertEqual(frappe.db.get_value("Life Task", x.name, "someday_with"), p.name)
		names = [r.name for r in tasks.list(space=PRIVATE, status="all", page_length=100)["tasks"]]
		self.assertNotIn(t.name, names)
		self.assertNotIn(g.name, [r["name"] for r in goals.list(space=PRIVATE, page_length=100)["rows"]] if "rows" in goals.list(space=PRIVATE) else [])
		lst = someday.list(space=PRIVATE)
		got = {r.name for r in lst["rows"]}
		self.assertTrue({t.name, p.name, g.name, idea["name"]} <= got)
		self.assertEqual(lst["tabs"]["projects"], 1)
		row = next(r for r in lst["rows"] if r.name == p.name)
		self.assertEqual(row["tasks"], 2)
		self.assertEqual(lst["tabs"]["due"], 0)
		self.assertEqual(getdate(next(r for r in lst["rows"] if r.name == t.name)["someday_review_on"]), getdate(add_months(today(), 3)))
		# the clock moves past the review date
		frappe.db.set_value("Life Task", t.name, "someday_review_on", add_days(today(), -1))
		self.assertEqual(someday.list(space=PRIVATE, tab="due")["total"], 1)
		self.assertEqual(counts.someday_due(PRIVATE)["n"], 1)
		# bring back with a date
		someday.bring_back("Life Task", t.name, due_date=add_days(today(), 2))
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Open")
		self.assertIn(t.name, [r.name for r in tasks.list(space=PRIVATE, status="open", page_length=100)["tasks"]])
		someday.bring_back("Life Project", p.name, status="Active")
		self.assertEqual({frappe.db.get_value("Life Task", x.name, "status") for x in pt}, {"Open"})
		made = someday.bring_back("Life Idea", idea["name"], make="task")
		self.assertEqual(made["made"]["doctype"], "Life Task")
		# keep
		someday.park("Life Goal", g.name) if not frappe.db.get_value("Life Goal", g.name, "is_someday") else None
		out = someday.keep("Life Goal", g.name)
		self.assertEqual(getdate(out["review_on"]), getdate(add_months(today(), 3)))

	def test_purge_moves_to_trash_and_restore_brings_it_back(self):
		t = self.make("Life Task", title="ux5 purge me", area=self.areas["Tea"])
		created = str(t.creation)
		someday.park("Life Task", t.name)
		someday.purge("Life Task", t.name)
		self.assertFalse(frappe.db.exists("Life Task", t.name))
		rows = trash.list(space=PRIVATE)["rows"]
		row = next(r for r in rows if r["record"] == t.name)
		self.assertEqual(row["title"], "ux5 purge me")
		trash.restore(row["name"])
		self.assertTrue(frappe.db.exists("Life Task", t.name))
		self.assertEqual(str(frappe.db.get_value("Life Task", t.name, "creation")), created)
		self.assertNotIn(t.name, [r["record"] for r in trash.list(space=PRIVATE)["rows"]])

	def test_agents_cannot_park_purge_or_delete_and_family_cannot_see_private_trash(self):
		t = self.make("Life Task", title="ux5 agent no", area=self.areas["Tea"])
		self.as_user(AGENT)
		for fn in (lambda: someday.park("Life Task", t.name), lambda: someday.purge("Life Task", t.name), lambda: trash.delete("Life Task", t.name)):
			with self.assertRaises(frappe.PermissionError):
				fn()
		self.as_user(OWNER)
		trash.delete("Life Task", t.name)
		self.as_user(FAMILY)
		self.assertNotIn(t.name, [r["record"] for r in trash.list(space=SHARED)["rows"]])
		with self.assertRaises(frappe.PermissionError):
			trash.list(space=PRIVATE)

	def test_someday_proposal_parks_only_on_accept(self):
		from lifeos.api import review

		t = self.make("Life Task", title="ux5 propose park", area=self.areas["Tea"])
		item = inbox.create_item(title="ux5 someday item", source_type="Message", space=PRIVATE, raw_text="x")
		self.as_user(AGENT)
		frappe.db.sql("update `tabLife Inbox Item` set received_on = %s where name = %s", (add_days(today(), -4000), item["name"]))
		inbox.claim_next(space=PRIVATE)
		inbox.submit_result(item["name"], summary_md="s", proposals=[{"kind": "Someday", "payload": {"record_type": "Task", "record": t.name, "note": "later"}}])
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Open")
		self.as_user(OWNER)
		prop = frappe.get_all("Life Proposal", filters={"inbox_item": item["name"]}, pluck="name")[0]
		review.decide(prop, "accept")
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Someday")

	def test_trash_purge_job_removes_old_rows(self):
		t = self.make("Life Task", title="ux5 old trash", area=self.areas["Tea"])
		trash.delete("Life Task", t.name)
		frappe.set_user("Administrator")
		dd = frappe.db.get_value("Deleted Document", {"deleted_doctype": "Life Task", "deleted_name": t.name})
		frappe.db.set_value("Deleted Document", dd, "creation", add_days(today(), -31), update_modified=False)
		trash.purge_old()
		self.assertFalse(frappe.db.exists("Deleted Document", dd))
