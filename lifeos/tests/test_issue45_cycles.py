"""Issue 45: Goals > Cycles. The server side: what the month plan and the grid give the screen, and journal pages in the Library list."""
import frappe
from frappe.utils import add_days, getdate, today

from lifeos import journal as rules
from lifeos.api import journal, library
from lifeos.tests.base import PRIVATE, LifeTestCase


class TestCycles(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Goal", {"space": PRIVATE})
		frappe.db.delete("Life Cycle", {"space": PRIVATE})
		frappe.db.delete("Life Month Plan", {"space": PRIVATE})
		frappe.db.set_single_value("Life Settings", "month_plan_enabled", 1)
		frappe.db.set_single_value("Life Settings", "cycle_break_week", 1)
		frappe.clear_cache(doctype="Life Settings")

	def tearDown(self):
		frappe.db.set_single_value("Life Settings", "month_plan_enabled", 1)
		frappe.clear_cache(doctype="Life Settings")
		super().tearDown()

	def test_the_grid_says_when_the_next_cycle_opens(self):  # I45.2
		start = rules.next_monday(add_days(today(), -30))
		cycle = self.make("Life Cycle", title="i45 cycle", start_date=start, status="Active")
		out = journal.grid(cycle=cycle.name, space=PRIVATE)
		nxt = out["next"]
		self.assertEqual(nxt["plan_opens"], str(add_days(getdate(start), 70)))
		self.assertEqual(nxt["starts"], str(rules.next_monday(cycle.end_date)))
		self.assertEqual(nxt["break_week"], [str(add_days(getdate(cycle.end_date), 1)), str(add_days(getdate(nxt["starts"]), -1))])
		frappe.db.set_single_value("Life Settings", "cycle_break_week", 0)
		frappe.clear_cache(doctype="Life Settings")
		self.assertIsNone(journal.grid(cycle=cycle.name, space=PRIVATE)["next"]["break_week"])

	def test_the_month_plan_gives_status_and_carried_month(self):  # I45.5, I45.6
		now = getdate(today())
		last = now.replace(day=1) - frappe.utils.datetime.timedelta(days=1)
		old_plan = rules.get_month_plan(PRIVATE, last.year, last.month, create=True)
		old = rules.add_month_goal(PRIVATE, last.year, last.month, "i45 carried goal")
		carried = rules.carry_month_goal(old.name)
		rules.add_month_goal(PRIVATE, now.year, now.month, "i45 second goal")
		self.make("Life Task", title="i45 task one", goal=carried["row"], status="Done")
		self.make("Life Task", title="i45 task two", goal=carried["row"], status="Open")
		out = journal.month(space=PRIVATE, year=now.year, month=now.month, create=1)
		self.assertTrue(out["enabled"])
		goals = {g["title"]: g for g in out["plan"]["goals"]}
		first = goals["i45 carried goal"]
		self.assertEqual(first["carried_from"], old.name)
		self.assertEqual(first["carried_from_month"], last.month)
		self.assertEqual((first["tasks_done"], first["tasks_counted"]), (1, 2))
		self.assertEqual(goals["i45 second goal"]["carried_from_month"], None)
		# Edit changes a goal's status and the next read shows it
		journal.save_month_goal(plan=out["plan"]["name"], row=goals["i45 second goal"]["row"], status="Done")
		again = {g["title"]: g for g in journal.month(space=PRIVATE, year=now.year, month=now.month)["plan"]["goals"]}
		self.assertEqual(again["i45 second goal"]["status"], "Done")
		self.assertTrue(old_plan)

	def test_the_month_plan_can_be_switched_off(self):  # I45.7
		frappe.db.set_single_value("Life Settings", "month_plan_enabled", 0)
		frappe.clear_cache(doctype="Life Settings")
		self.assertFalse(journal.month(space=PRIVATE)["enabled"])

	def test_journal_pages_are_a_kind_in_the_notes_list(self):  # I45.9
		page = self.make("Life Journal Page", page_date=today(), page_number=7, transcript_md="i45 paper words")
		note = self.make("Life Note", title="i45 a note", content_md="text")
		rows = {r["name"]: r for r in library.list(space=PRIVATE, collection="all", page_length=100)["notes"]}
		self.assertEqual(rows[page.name]["kind"], "Journal page")
		self.assertEqual(rows[note.name]["kind"], "Note")
		# the tree reports how many pages the list adds, so the number over the tree is the list's total
		tree = library.tree(space=PRIVATE, collection="all")
		self.assertEqual(len(tree["notes"]) + tree["journal_pages"], library.list(space=PRIVATE, collection="all")["total"])
		# the goal page's list of notes (My notes) stays notes only
		mine = {r["name"] for r in library.list(space=PRIVATE, page_length=100)["notes"]}
		self.assertNotIn(page.name, mine)
