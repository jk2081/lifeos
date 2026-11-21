"""UX fixes, set 5: rule insights, no repeats after a dismissal, snoozes that return, at most 12 a day."""
import frappe
from frappe.utils import add_days, getdate, today

from lifeos import insights, journal
from lifeos.api import insights as api
from lifeos.tests.base import AGENT, PRIVATE, LifeTestCase


class TestRuleInsights(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Insight", {"space": PRIVATE})
		# what earlier tests left is fresh again, so each test sees only what it seeds
		frappe.db.sql("update `tabLife Task` set last_touched_on=%s where space=%s", (today(), PRIVATE))
		frappe.db.sql("update `tabLife Goal` set last_activity_on=%s where space=%s", (today(), PRIVATE))

	def _stuck_tasks(self, n=4, area="Tea"):
		out = []
		for i in range(n):
			t = self.make("Life Task", title=f"ux5 stuck {area} {frappe.generate_hash(length=6)}", area=self.areas[area])
			frappe.db.set_value("Life Task", t.name, "last_touched_on", add_days(today(), -120))
			out.append(t)
		return out

	def test_stuck_cycle_and_habit_insights_from_seeded_data(self):
		self._stuck_tasks()
		# a cycle in week 5 with a goal that has had no ticks and no tasks
		start = journal.monday_of(add_days(today(), -28)) if hasattr(journal, "monday_of") else add_days(today(), -28 - getdate(today()).weekday())
		cyc = self.make("Life Cycle", title="ux5 cycle", start_date=start, status="Active")
		self.make("Life Goal", cycle=cyc.name, title="ux5 quiet goal", horizon="12 weeks", area=self.areas["Tea"],
			actions=[{"title": "ux5 action", "per_week": 1}])
		# a habit done every day last month and never this month
		h = self.make("Life Habit", title="ux5 Workout")
		now = getdate(today())
		prev = frappe.utils.add_months(now, -1)
		for y, m in ((prev.year, prev.month), (now.year, now.month)):
			plan = journal.get_month_plan(PRIVATE, y, m, create=True)
			if h.name not in [r.habit for r in plan.habits]:
				plan.append("habits", {"habit": h.name, "days_per_week": 7})
				plan.save()
		first, last = journal.month_bounds(prev.year, prev.month)
		d = first
		while d <= last:
			self.make("Life Habit Log", habit=h.name, date=d, done=1)
			d = add_days(d, 1)
		stats = insights.run(PRIVATE, ai=False)
		kinds = {r.kind: r.title for r in frappe.get_all("Life Insight", filters={"space": PRIVATE}, fields=["kind", "title"])}
		self.assertIn("Stuck", kinds)
		self.assertIn("12 Week Year", kinds)
		if now.day >= 7:
			self.assertIn("Habit", kinds)
		self.assertGreater(stats["created"], 0)
		got = api.list(space=PRIVATE)
		stuck = next(r for r in got["rows"] if r.kind == "Stuck" and "Tea" in r.title)
		self.assertTrue(stuck["actionable"])
		self.assertEqual(len(stuck["evidence"]), 4)
		self.assertTrue(stuck["evidence"][0]["ref"].startswith("task:"))

	def test_dismissed_does_not_return_snoozed_returns_after_date(self):
		mine = self._stuck_tasks(4, "Money")

		def money_insight(status=None):
			rows = frappe.db.sql("""select i.name, i.status, i.fingerprint from `tabLife Insight` i where i.space=%s and i.kind='Stuck'
				and exists (select 1 from `tabLife Insight Evidence` e where e.parent=i.name and e.ref_name=%s)""", (PRIVATE, mine[0].name), as_dict=True)
			return [r for r in rows if not status or r.status == status]

		insights.run(PRIVATE, ai=False)
		first = money_insight("New")[0]
		api.dismiss(first.name, "Not relevant")
		insights.run(PRIVATE, ai=False)
		self.assertEqual(money_insight("New"), [])
		self.assertEqual(frappe.db.get_value("Life Insight", first.name, "status"), "Dismissed")
		# the evidence changes: a fifth stuck task in the same area makes it a new finding
		mine += self._stuck_tasks(1, "Money")
		insights.run(PRIVATE, ai=False)
		new = money_insight("New")
		self.assertEqual(len(new), 1)
		self.assertNotEqual(new[0].fingerprint, first.fingerprint)
		api.snooze(new[0].name, add_days(today(), 3))
		insights.run(PRIVATE, ai=False)
		self.assertEqual(frappe.db.get_value("Life Insight", new[0].name, "status"), "Snoozed")
		frappe.db.set_value("Life Insight", new[0].name, "snooze_until", add_days(today(), -1))
		insights.run(PRIVATE, ai=False)
		self.assertEqual(frappe.db.get_value("Life Insight", new[0].name, "status"), "New")

	def test_at_most_twelve_new_a_day(self):
		for i in range(15):
			p = self.make("Life Goal", title=f"ux5 idle {i}", horizon="Long term", area=self.areas["Tea"])
			frappe.db.set_value("Life Goal", p.name, "last_activity_on", add_days(today(), -100))
		stats = insights.run(PRIVATE, ai=False)
		self.assertEqual(stats["created"], 12)
		self.assertEqual(frappe.db.count("Life Insight", {"space": PRIVATE, "found_on": today()}), 12)
		self.assertEqual(insights.run(PRIVATE, ai=False)["created"], 0)

	def test_act_move_to_someday_and_agents_refused(self):
		ts = self._stuck_tasks()
		insights.run(PRIVATE, ai=False)
		row = next(r for r in api.list(space=PRIVATE)["rows"] if r.kind == "Stuck")
		i = next(n for n, a in enumerate(row["actions"]) if a["kind"] == "move_someday")
		out = api.act(row.name, i)
		self.assertEqual(out["done"], 4)
		self.assertEqual({frappe.db.get_value("Life Task", t.name, "status") for t in ts}, {"Someday"})
		self.assertEqual(frappe.db.get_value("Life Insight", row.name, "status"), "Acted")
		self.as_user(AGENT)
		with self.assertRaises(frappe.PermissionError):
			api.list(space=PRIVATE)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Life Insight", filters={"space": PRIVATE})
