"""Set 8, step 4: the Tasks tab. Left your plate counts against the Outbox for the review's period (the count rule), and the
tab is done once Needs you and every pile are cleared."""
import frappe

from lifeos.api import outbox as outbox_api
from lifeos.api import weekly
from lifeos.tests.base import PRIVATE
from lifeos.tests.test_set8_review import ReviewCase


class TestTasksTab(ReviewCase):
	def test_left_your_plate_counts_open_lists_with_that_many_rows(self):
		done = self.make("Life Task", title="s8 plate done", status="Open")
		done.status = "Done"
		done.save()
		parked = self.task("s8 plate park", age=70)
		weekly.start(space=PRIVATE)
		weekly.pile_settle(space=PRIVATE, key="tasks", ref=self.ref(parked), decision="park")
		got = weekly.plate(space=PRIVATE)
		by = {x["pile"]: x for x in got["piles"]}
		self.assertGreaterEqual(by["Done"]["n"], 1)
		self.assertGreaterEqual(by["Parked"]["n"], 1)
		for x in [*got["piles"], got["in"], got["out"]]:
			q = x["to"]["query"]
			listed = outbox_api.list(space=PRIVATE, pile=q["pile"], from_date=q["from"], to_date=q["to"], page_length=500)
			self.assertEqual(x["n"], listed["total"])
			self.assertEqual(x["n"], len(listed["rows"]))
		self.assertEqual(got["out"]["n"], sum(x["n"] for x in got["piles"]))

	def test_next_goals_opens_when_the_piles_are_cleared(self):
		goal = self.cycle_goal("s8 tasks goal")
		needs = self.task("s8 tasks needs", age=40, goal=goal.name)
		old = self.task("s8 tasks old", age=70)
		head = weekly.start(space=PRIVATE)
		self.assertFalse(head["done"]["tasks"])
		weekly.pile_settle(space=PRIVATE, key="tasks", ref=self.ref(needs), decision="keep")
		self.assertFalse(weekly.get(space=PRIVATE)["done"]["tasks"])
		head = weekly.pile_accept(space=PRIVATE, key="tasks", pile="park")["header"]
		self.assertTrue(head["done"]["tasks"])
		self.assertEqual(frappe.db.get_value("Life Task", old, "status"), "Someday")
