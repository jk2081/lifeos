"""Set 8, step 5: the Goals tab. The next-action prefill order, exactly three stars, a skip needs a reason, over-capacity, and
the tab's gate."""
import frappe
from frappe.utils import add_days, now_datetime, today

from lifeos.api import settings as settings_api
from lifeos.api import weekly
from lifeos.review import goals as goals_mod
from lifeos.review.record import Review
from lifeos.tests.base import PRIVATE
from lifeos.tests.test_set8_review import ReviewCase
from lifeos.tests.test_ux5_ask import set_key


class GoalsCase(ReviewCase):
	def setUp(self):
		super().setUp()
		frappe.db.sql("update `tabLife Goal` set outcome='Achieved' where space=%s and outcome='In Progress'", PRIVATE)
		self.goals = [self.cycle_goal(f"s8 cycle goal {i}").name for i in range(4)]

	def tab(self):
		return weekly.goals(space=PRIVATE)

	def row(self, goal):
		return next(r for r in self.tab()["rows"] if r["goal"] == goal)


class TestPrefill(GoalsCase):
	def test_the_prefill_order(self):
		g = self.goals[0]
		self.assertEqual((self.row(g)["plan"]["next_action"], self.row(g)["plan"]["source"]), ("", "empty"))  # nothing yet
		oldest = self.make("Life Task", title="s8 oldest task", goal=g, status="Open").name
		self.make("Life Task", title="s8 newer task", goal=g, status="Open")
		frappe.db.delete("Life Review", {"space": PRIVATE})
		self.assertEqual(self.row(g)["plan"]["task"], oldest)
		weekly.start(space=PRIVATE)
		# a task made for this goal in Library comes first
		ev = frappe.get_doc({"doctype": "Event", "subject": "s8 meeting", "starts_on": f"{today()} 09:00:00", "ends_on": f"{today()} 10:00:00",
			"life_space": PRIVATE, "event_type": "Public"}).insert(ignore_permissions=True)
		made = weekly.meeting_plan(space=PRIVATE, event=ev.name, title="s8 from the meeting", goal=g)["task"]
		p = self.row(g)["plan"]
		self.assertEqual((p["task"], p["next_action"], p["source"]), (made, "s8 from the meeting", "review"))
		# what the owner typed wins over everything
		weekly.goal_save(space=PRIVATE, goal=g, values={"next_action": "s8 my own action", "task": None})
		self.assertEqual(self.row(g)["plan"]["next_action"], "s8 my own action")

	def test_the_assistant_fills_what_has_no_task(self):
		set_key("fake-site-model")
		frappe.set_user("owner@lifeos.test")
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 1)
		try:
			weekly.start(space=PRIVATE)
			p = self.row(self.goals[1])["plan"]
			self.assertEqual((p["next_action"], p["source"]), ("Plan the next step for s8 cycle goal 1", "assistant"))
		finally:
			frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 0)

	def test_slots_do_not_overlap(self):
		weekly.start(space=PRIVATE)
		got = [(r["plan"]["slot"], r["plan"]["minutes"]) for r in self.tab()["rows"] if r["plan"]["slot"]]
		spans = sorted((frappe.utils.get_datetime(s), frappe.utils.get_datetime(s) + frappe.utils.datetime.timedelta(minutes=m)) for s, m in got)
		self.assertTrue(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])))


class TestStarsSkipsAndGate(GoalsCase):
	def test_exactly_three_stars_and_skip_needs_a_reason(self):
		for g in self.goals:
			weekly.goal_save(space=PRIVATE, goal=g, values={"next_action": f"act on {g}"})
		t = self.tab()
		self.assertEqual(len(t["stars"]), 3)  # prefilled: the three furthest behind
		self.assertTrue(t["ready"]["ok"])
		weekly.goal_star(space=PRIVATE, goal=t["stars"][0], on=0)
		t = self.tab()
		self.assertFalse(t["ready"]["ok"])
		self.assertIn("Star one more goal to go on", t["ready"]["left"])
		extra = next(g for g in self.goals if g not in t["stars"])
		weekly.goal_star(space=PRIVATE, goal=extra, on=1)
		weekly.goal_star(space=PRIVATE, goal=next(g for g in self.goals if g not in self.tab()["stars"]), on=1)
		self.assertFalse(self.tab()["ready"]["ok"])  # four is not three
		with self.assertRaises(frappe.ValidationError):
			weekly.goal_skip(space=PRIVATE, goal=self.goals[0], reason="  ")
		weekly.goal_skip(space=PRIVATE, goal=self.goals[0], reason="Travelling all week")
		t = self.tab()
		self.assertEqual(self.row(self.goals[0])["plan"]["skip"], "Travelling all week")
		self.assertNotIn(self.goals[0], t["stars"])
		self.assertTrue(t["ready"]["ok"])
		self.assertTrue(Review.find_open(PRIVATE, "owner@lifeos.test").done()["goals"])

	def test_a_goal_with_no_next_action_blocks(self):
		weekly.start(space=PRIVATE)
		t = self.tab()
		self.assertFalse(t["ready"]["ok"])
		self.assertEqual(sorted(t["ready"]["missing"]), sorted(self.goals))

	def test_over_capacity_is_said_and_does_not_block(self):
		settings_api.save({"work_days": "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday", "work_start": "09:00:00", "work_end": "10:00:00"})
		frappe.clear_document_cache("Life Settings", "Life Settings")
		try:
			for g in self.goals:
				weekly.goal_save(space=PRIVATE, goal=g, values={"next_action": f"act on {g}", "minutes": 600, "slot": f"{add_days(today(), 1)} 09:00"})
			cap = self.tab()["capacity"]
			self.assertTrue(cap["over"])
			self.assertGreater(cap["planned_minutes"], cap["free_minutes"])
			self.assertTrue(self.tab()["ready"]["ok"])
		finally:
			settings_api.save({"work_days": "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday", "work_start": "09:00:00", "work_end": "19:00:00"})
			frappe.clear_document_cache("Life Settings", "Life Settings")

	def test_other_goals_fold_and_can_be_planned(self):
		other = self.make("Life Goal", title="s8 Lotwise pilot", horizon="Long term").name
		t = self.tab()
		self.assertEqual(t["others"]["n"], 1)
		weekly.goal_add(space=PRIVATE, goal=other)
		t = self.tab()
		self.assertIn(other, [r["goal"] for r in t["rows"]])
		self.assertEqual(t["others"]["n"], 0)
