"""Set 8, step 6: Reflect and Lock the week. Lock makes the goals' tasks (scheduled and delegated), marks the top three, stores
the numbers and text, and locks; Today shows the top three first; last week's note is played back."""
import frappe
from frappe.utils import add_days, today

from lifeos.api import today as today_api
from lifeos.api import weekly
from lifeos.review.record import Review
from lifeos.tests.base import OWNER, PRIVATE
from lifeos.tests.test_set8_goals import GoalsCase
from lifeos.tests.test_ux5_ask import set_key


class TestLock(GoalsCase):
	def plan_all(self):
		slot = f"{add_days(today(), 1)} 10:00"
		for i, g in enumerate(self.goals):
			who = "Kunal" if i == 1 else "Me"
			weekly.goal_save(space=PRIVATE, goal=g, values={"next_action": f"s8 next {i}", "slot": slot if i == 0 else "", "minutes": 45, "who": who,
				"note": "the figures"})
		weekly.goal_skip(space=PRIVATE, goal=self.goals[3], reason="Waiting for the season")
		return weekly.goals(space=PRIVATE)["stars"]

	def test_lock_needs_what_went_well_and_the_tabs_before(self):
		weekly.start(space=PRIVATE)
		with self.assertRaises(frappe.ValidationError):
			weekly.lock(space=PRIVATE, went_well="")
		with self.assertRaises(frappe.ValidationError):
			weekly.lock(space=PRIVATE, went_well="Closed the blend sheet")  # goals not planned yet

	def test_lock_makes_tasks_pins_the_top_three_and_locks(self):
		old = self.make("Life Task", title="s8 last week's star", status="Open", is_top_three=1, top_three_week=add_days(today(), -7)).name
		stars = self.plan_all()
		self.assertEqual(len(stars), 3)
		out = weekly.lock(space=PRIVATE, went_well="Closed the blend sheet in one sitting", do_differently="No calls on Tuesday")
		self.assertEqual(out["header"]["status"], "Locked")
		made = {m["goal"]: m for m in out["made"]}
		self.assertEqual(set(made), set(self.goals[:3]))  # the skipped one has no task
		first = frappe.db.get_value("Life Task", made[self.goals[0]]["task"], ["title", "scheduled_at", "duration_min", "notes_md", "status"], as_dict=True)
		self.assertEqual((first.title, str(first.scheduled_at)[:16], first.duration_min), ("s8 next 0", f"{add_days(today(), 1)} 10:00", 45))
		self.assertIn("the figures", first.notes_md)
		self.assertEqual(frappe.db.get_value("Life Task", made[self.goals[1]]["task"], ["status", "waiting_on"]), ("Waiting", "Kunal"))
		tops = frappe.get_all("Life Task", filters={"space": PRIVATE, "is_top_three": 1}, pluck="name")
		self.assertEqual(sorted(tops), sorted(made[g]["task"] for g in stars))
		self.assertEqual(frappe.db.get_value("Life Task", old, "is_top_three"), 0)  # last week's are cleared
		doc = frappe.get_doc("Life Review", out["header"]["name"])
		self.assertEqual((doc.went_well, doc.do_differently, doc.goals_planned, doc.goals_skipped), ("Closed the blend sheet in one sitting", "No calls on Tuesday", 3, 1))
		self.assertTrue(doc.locked_on and doc.minutes_spent >= 1)
		# Today: the top three first, starred
		got = today_api.get(space=PRIVATE)
		first_group = next(g for g in got["next"]["groups"] if g["rows"])
		self.assertEqual(first_group["key"], "top")
		self.assertEqual({r["name"] for r in first_group["rows"]}, set(tops))
		# the locked review is shown as done; the next starts after it
		self.assertEqual(weekly.get(space=PRIVATE)["status"], "Locked")
		self.assertEqual(str(Review.period(PRIVATE, OWNER, add_days(today(), 7))[0]), str(add_days(today(), 1)))
		with self.assertRaises(frappe.ValidationError):
			weekly.goal_save(space=PRIVATE, goal=self.goals[0], values={"next_action": "x"})

	def test_last_weeks_note_is_played_back(self):
		frappe.get_doc({"doctype": "Life Review", "space": PRIVATE, "user": OWNER, "status": "Locked", "period_start": add_days(today(), -14),
			"period_end": add_days(today(), -8), "locked_on": add_days(frappe.utils.now_datetime(), -8), "went_well": "x",
			"do_differently": "Too many calls on Tuesday"}).insert()
		self.assertEqual(weekly.reflect(space=PRIVATE)["last"], {"line": "Too many calls on Tuesday", "check": None})  # no key: the line only
		set_key("fake-site-model")
		frappe.set_user(OWNER)
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 1)
		try:
			tuesday = next(add_days(today(), -n) for n in range(1, 7) if frappe.utils.getdate(add_days(today(), -n)).weekday() == 1)
			frappe.get_doc({"doctype": "Event", "subject": "s8 call with Vivek", "starts_on": f"{tuesday} 11:00:00", "ends_on": f"{tuesday} 11:30:00",
				"life_space": PRIVATE, "event_type": "Public"}).insert(ignore_permissions=True)
			weekly.start(space=PRIVATE)
			self.assertEqual(weekly.reflect(space=PRIVATE)["last"]["check"], "This week Tuesday had 1 call.")
		finally:
			frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 0)
