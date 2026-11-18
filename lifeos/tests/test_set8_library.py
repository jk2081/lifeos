"""Set 8, step 3: the Library tab. Came in counts against their lists (the count rule), the calendar strip, a meeting opened,
a task planned from a meeting, revelations at most five with "N left", and acting on a finding from the review."""
import frappe
from frappe.utils import add_days, get_datetime, today

from lifeos.api import library as library_api
from lifeos.api import sources, weekly
from lifeos.review import findings, gcal
from lifeos.tests.base import OWNER, PRIVATE
from lifeos.tests.test_set8_calendar import ME, CalCase, gevent


class LibCase(CalCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Review", {"space": PRIVATE})


class TestLibrary(LibCase):
	def test_came_in_counts_open_lists_with_exactly_that_many_rows(self):
		self.capture("s8 voice", get_datetime(f"{self.day} 09:00"))
		self.capture("s8 mail", get_datetime(f"{self.day} 09:00"), kind="Email")
		got = weekly.library(space=PRIVATE)
		rows = {r["key"]: r for r in got["came_in"]["rows"]}
		for key in ("captures", "chats", "emails"):
			q = rows[key]["to"]["query"]
			listed = sources.list(space=PRIVATE, tab=q.get("tab") or "all", from_date=q["from"], to_date=q["to"], filters=q.get("f"), page_length=500)
			self.assertEqual(rows[key]["n"], len(listed["sources"]), key)
		self.assertGreaterEqual(rows["captures"]["n"], 1)
		self.assertGreaterEqual(rows["emails"]["n"], 1)
		notes = library_api.list(space=PRIVATE, filters=rows["notes"]["to"]["query"]["f"], collection="all", page_length=500)
		self.assertEqual(rows["notes"]["n"], notes["total"])
		self.assertEqual(got["came_in"]["total"], sum(r["n"] for r in rows.values()))

	def test_strip_meeting_and_a_task_planned_from_it(self):
		fake = frappe.local.conf.get("lifeos_fake_calendar")
		frappe.local.conf.lifeos_fake_calendar = 0
		try:
			self.assertIsNone(weekly.library(space=PRIVATE)["strip"])  # no calendar: one line instead
		finally:
			frappe.local.conf.lifeos_fake_calendar = fake
		m = self.read(gevent("lib", f"{self.day} 15:00", 60, "Dalmia: blend sheet", [ME, "mithun@dalmia.example"]))["Dalmia: blend sheet"].name
		voice = self.capture("2 min, recorded 16:20", get_datetime(f"{self.day} 16:20"))
		weekly.start(space=PRIVATE)  # links what was captured
		strip = weekly.library(space=PRIVATE)["strip"]
		cell = next(e for d in strip["days"] for e in d["events"] if e["name"] == m)
		self.assertEqual((cell["matters"], cell["mark"]), (True, "linked"))
		detail = weekly.meeting(space=PRIVATE, event=m)
		self.assertEqual([l["name"] for l in detail["linked"]], [voice])
		goal = self.make("Life Goal", title="s8 Lotwise pilot", goal_type="Open")
		out = weekly.meeting_plan(space=PRIVATE, event=m, title="Send Mithun the lot sizes", goal=goal.name)
		self.assertEqual(frappe.db.get_value("Life Task", out["task"], "goal"), goal.name)
		self.assertIn(out["task"], [l["name"] for l in weekly.meeting(space=PRIVATE, event=m)["linked"]])
		self.assertEqual(weekly.meetings_list(space=PRIVATE)["rows"][0]["name"], m)

	def test_revelations_at_most_five_and_how_many_are_left(self):
		for i in range(7):
			findings.add(PRIVATE, "Promise", f"s8 promise {i}", [{"ref_doctype": "Life Goal", "ref_name": self.make("Life Goal", title=f"s8 g{i}", goal_type="Open").name}],
				[{"kind": "make_task", "label": "Make task", "title": f"s8 task {i}"}, {"kind": "dismiss", "label": "Not needed"}], source="AI")
		weekly.start(space=PRIVATE)
		got = weekly.library(space=PRIVATE)
		self.assertEqual((len(got["revelations"]), got["revelations_shown"]), (5, 5))
		first, second = got["revelations"][0], got["revelations"][1]
		out = weekly.finding_act(space=PRIVATE, insight=first["name"], index=0)
		self.assertTrue(frappe.db.exists("Life Task", out["task"]))
		weekly.finding_act(space=PRIVATE, insight=second["name"], index=1)
		self.assertEqual(frappe.db.get_value("Life Insight", second["name"], "status"), "Dismissed")
		got = weekly.library(space=PRIVATE)
		self.assertEqual((len(got["revelations"]), got["revelations_shown"]), (3, 5))  # "3 left", the next two do not move in


class TestReadingFromRevelations(LibCase):
	def test_confirm_a_reading_from_the_review(self):
		goal = self.make("Life Goal", title="s8 yield rev", goal_type="Open", measure_kind="Number", measure="yield", unit="kg/ha", start_value=1000, target_value=1800)
		r = frappe.get_doc({"doctype": "Life Goal Reading", "space": PRIVATE, "goal": goal.name, "date": today(), "value": 1460, "status": "Suggested",
			"suggested_by": "Agent", "excerpt": "1460 kg/ha"}).insert()
		weekly.start(space=PRIVATE)
		ins = frappe.db.get_value("Life Insight", {"reading": r.name})
		weekly.finding_act(space=PRIVATE, insight=ins, index=0)
		self.assertEqual(frappe.db.get_value("Life Goal", goal.name, "current_value"), 1460)
		self.assertEqual(frappe.db.get_value("Life Insight", ins, "status"), "Acted")
