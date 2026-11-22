"""Issue 60: one kind of goal with a horizon, one parking lot (Someday), no tags."""
import os

import frappe
from frappe.utils import add_days, add_months, getdate, today

from lifeos import journal as rules
from lifeos.api import inbox, reset, someday
from lifeos.life.doctype.life_goal.life_goal import derive_horizon
from lifeos.review import pile_actions
from lifeos.tests.base import AGENT, OWNER, PRIVATE, LifeTestCase

APP = os.path.dirname(os.path.dirname(__file__))
REPO = os.path.dirname(APP)


def set_planning(value):
	frappe.db.set_single_value("Life Settings", "planning_period", value)
	frappe.clear_cache(doctype="Life Settings")


class TestHorizon(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		frappe.db.delete("Life Cycle", {"space": PRIVATE})

	def tearDown(self):
		set_planning("12 Week Years")
		super().tearDown()

	def test_horizon_follows_the_target_date_and_the_cycle(self):  # I60.1
		now = getdate(today())
		self.assertEqual(derive_horizon(add_days(now.replace(day=1), 0), None, PRIVATE), "Month")
		next_march = now.replace(year=now.year + 1, month=3, day=15) if now.month >= 3 else now.replace(month=3, day=15)
		self.assertEqual(derive_horizon(next_march, None, PRIVATE), "Year")
		self.assertEqual(derive_horizon(add_months(now, 36), None, PRIVATE), "Long term")
		self.assertEqual(derive_horizon(None, None, PRIVATE), "Long term")
		cycle = self.make("Life Cycle", title="i60 cycle", start_date=today(), status="Active")
		self.assertEqual(derive_horizon(None, cycle.name, PRIVATE), "12 weeks")
		goal = self.make("Life Goal", title="i60 in the cycle", cycle=cycle.name)
		self.assertEqual(goal.horizon, "12 weeks")
		dated = self.make("Life Goal", title="i60 dated", target_date=add_months(now, 36))
		self.assertEqual(dated.horizon, "Long term")
		month = self.make("Life Goal", title="i60 this month", target_date=now)
		self.assertEqual(month.horizon, "Month")

	def test_a_date_inside_the_active_cycle_is_a_12_week_goal(self):
		cycle = self.make("Life Cycle", title="i60 cycle two", start_date=add_days(today(), -30), status="Active")
		d = add_days(cycle.start_date, 75) if getdate(add_days(cycle.start_date, 75)).month != getdate(today()).month else add_days(cycle.start_date, 80)
		self.assertEqual(derive_horizon(d, None, PRIVATE), "12 weeks")

	def test_quarters_follow_the_calendar_quarter(self):  # I60.2
		now = getdate(today())
		qm = ((now.month - 1) // 3) * 3 + 1
		other_month = qm + 2 if now.month != qm + 2 else qm
		in_quarter = now.replace(month=other_month, day=15)
		if (in_quarter.year, in_quarter.month) == (now.year, now.month):
			in_quarter = now.replace(month=qm + 1, day=15)
		self.make("Life Cycle", title="i60 away", start_date=add_days(today(), -300), status="Active")
		self.assertNotEqual(derive_horizon(in_quarter, None, PRIVATE), "12 weeks")  # 12 Week Years: no cycle covers it
		set_planning("Quarters")
		self.assertEqual(derive_horizon(in_quarter, None, PRIVATE), "12 weeks")
		goal = self.make("Life Goal", title="i60 quarter goal", target_date=in_quarter)  # needs no cycle
		self.assertEqual((goal.horizon, goal.cycle), ("12 weeks", None))

	def test_year_and_month_goals_need_a_date_and_only_12_weeks_has_a_cycle(self):
		self.assertRaises(frappe.ValidationError, self.make, "Life Goal", title="i60 year", horizon="Year")
		self.assertRaises(frappe.ValidationError, self.make, "Life Goal", title="i60 month", horizon="Month")
		cycle = self.make("Life Cycle", title="i60 cycle three", start_date=today(), status="Active")
		self.assertRaises(frappe.ValidationError, self.make, "Life Goal", title="i60 odd", horizon="Year", target_date=add_months(today(), 5), cycle=cycle.name)


class TestRemoved(LifeTestCase):
	def test_the_old_records_are_gone(self):  # I60.3
		for dt in ("Life Month Plan Goal", "Life Idea", "Life Tag", "Life Tag Link"):
			self.assertFalse(frappe.db.exists("DocType", dt), dt)
			self.assertFalse(frappe.db.table_exists(dt), dt)
		for dt in ("Life Task", "Life Note", "Life Inbox Item", "Life Vault Document", "Life Chat Log", "Life Journal Page"):
			self.assertFalse(frappe.get_meta(dt).has_field("tags"), dt)
		self.assertFalse(frappe.get_meta("Life Month Plan").has_field("goals"))
		self.assertFalse(frappe.get_meta("Life Goal").has_field("goal_type"))

	def test_no_code_names_them(self):  # I60.7
		banned = ("Life Idea", "Life Tag", "Life Month Plan Goal")
		pattern_tags = ("tags", "tag_ids", "tags_csv")
		bad = []
		roots = [APP, os.path.join(REPO, "frontend", "src"), os.path.join(REPO, "agent")]
		skip = ("node_modules", "public", "patches", "__pycache__", "test_issue60_horizons_someday_no_tags.py")
		for root in roots:
			for base, dirs, files in os.walk(root):
				dirs[:] = [d for d in dirs if d not in skip]
				for f in files:
					if f in skip or not f.endswith((".py", ".js", ".vue", ".md")):
						continue
					text = open(os.path.join(base, f), encoding="utf-8", errors="ignore").read()
					for word in banned:
						if word in text:
							bad.append((os.path.join(base, f), word))
					for line_no, line in enumerate(text.splitlines(), 1):
						if any(f'"{p}"' in line or f"'{p}'" in line or f".{p}" in line or f"{p}:" in line for p in pattern_tags):
							bad.append((os.path.join(base, f), f"line {line_no}: {line.strip()[:80]}"))
		self.assertEqual(bad, [])


class TestSomeday(LifeTestCase):
	def test_park_makes_a_someday_task_or_note_from_reset_old_inbox_and_piles(self):  # I60.5
		t = self.make("Life Task", title="i60 reset", area=self.areas["Tea"])
		reset.decide("Life Task", t.name, "someday")
		self.assertEqual(frappe.db.get_value("Life Task", t.name, "status"), "Someday")
		t2 = self.make("Life Task", title="i60 pile", area=self.areas["Tea"])
		pile_actions.apply({"doctype": "Life Task", "name": t2.name}, "park")
		self.assertEqual(frappe.db.get_value("Life Task", t2.name, "status"), "Someday")
		made = inbox.create_item(space=PRIVATE, title="i60 old capture", source_type="Message", raw_text="a thought")
		before = {dt: frappe.db.count(dt) for dt in ("Life Task", "Life Note")}
		pile_actions.apply({"doctype": "Life Inbox Item", "name": made["name"]}, "park")
		note = frappe.get_doc("Life Note", {"inbox_item": made["name"]})
		self.assertEqual((note.is_someday, bool(note.someday_review_on)), (1, True))
		self.assertEqual(frappe.db.count("Life Task"), before["Life Task"])
		self.assertEqual(frappe.db.count("Life Note"), before["Life Note"] + 1)

	def test_create_makes_a_someday_task_or_note(self):
		task = someday.create("i60 maybe", space=PRIVATE)
		self.assertEqual((task["doctype"], frappe.db.get_value("Life Task", task["name"], "status")), ("Life Task", "Someday"))
		note = someday.create("i60 thought", space=PRIVATE, as_note=1)
		self.assertEqual(frappe.db.get_value("Life Note", note["name"], "is_someday"), 1)
		rows = {r.name: r.type for r in someday.list(space=PRIVATE, page_length=100)["rows"]}
		self.assertEqual((rows[task["name"]], rows[note["name"]]), ("Task", "Note"))


class TestAgentProposals(LifeTestCase):
	def test_a_month_goal_proposal_is_accepted_as_a_goal_with_horizon_month(self):  # I60.6
		self.as_user(AGENT)
		made = inbox.create_item(space=PRIVATE, title="i60 agent", source_type="Message", raw_text="x")
		frappe.db.set_value("Life Inbox Item", made["name"], {"status": "Processing", "claimed_by": AGENT})
		now = getdate(today())
		out = inbox.submit_result(made["name"], summary_md="s", proposals=[
			{"kind": "Month Goal", "payload": {"title": "i60 old kind", "year": now.year, "month": now.month, "area": "Tea"}},
			{"kind": "Goal", "payload": {"title": "i60 new kind", "horizon": "Long term"}}])
		self.assertEqual(out["errors"], [])
		self.as_user(OWNER)
		from lifeos.api import review

		self.assertEqual(review.decide_all(made["name"], "accept")["errors"], [])
		goal = frappe.get_doc("Life Goal", {"title": "i60 old kind", "space": PRIVATE})
		self.assertEqual((goal.horizon, getdate(goal.target_date).month), ("Month", now.month))
		self.assertIn(goal.name, [g["row"] for g in rules.month_goals(PRIVATE, now.year, now.month)])
		self.assertEqual(frappe.db.get_value("Life Goal", {"title": "i60 new kind"}, "horizon"), "Long term")
