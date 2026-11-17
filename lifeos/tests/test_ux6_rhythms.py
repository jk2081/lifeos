"""UX fixes, set 6: rhythm banners on Today. The clock is moved with `at`, which a test site allows."""
import frappe
from frappe.utils import add_days, getdate

from lifeos import rhythms
from lifeos.api import today as today_api
from lifeos.tests.base import AGENT, PRIVATE, LifeTestCase

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class TestBanners(LifeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		s = frappe.get_single("Life Settings")
		cls.saved = (s.weekly_review_day, s.weekly_review_time, s.month_plan_enabled)
		s.weekly_review_day, s.weekly_review_time, s.month_plan_enabled = "Sunday", "18:00:00", 1
		s.save()
		frappe.conf.lifeos_test_clock = 1
		# a cycle whose week 11 starts on 2027-03-15 (it started on 2027-01-04)
		cls.cycle = frappe.get_doc({"doctype": "Life Cycle", "space": PRIVATE, "title": "ux6 cycle", "start_date": "2027-01-04",
			"end_date": "2027-03-28", "status": "Planned"}).insert().name

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.conf.lifeos_test_clock = 0
		s = frappe.get_single("Life Settings")
		s.weekly_review_day, s.weekly_review_time, s.month_plan_enabled = cls.saved
		s.save()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.db.delete("Life View State", {"screen": rhythms.SCREEN})

	def banner(self, at):
		return rhythms.banner(PRIVATE, at)

	def test_weekly_review_from_its_time_until_skipped_or_done(self):
		self.assertIsNone(self.banner("2027-02-14 17:00:00"))  # a Sunday, before 18:00
		b = self.banner("2027-02-14 18:30:00")
		self.assertEqual((b["key"], b["occurrence"]), ("review", "review:2027-02-08"))
		self.assertIsNone(self.banner("2027-02-13 19:00:00"))  # Saturday
		rhythms.dismiss(b["occurrence"])
		self.assertIsNone(self.banner("2027-02-14 19:00:00"))
		self.assertEqual(self.banner("2027-02-21 19:00:00")["occurrence"], "review:2027-02-15")  # next week it is back
		frappe.get_doc({"doctype": "Life Note", "space": PRIVATE, "title": "Weekly review, 15 Feb 2027", "content_md": "done"}).insert()
		self.assertIsNone(self.banner("2027-02-21 19:00:00"))

	def test_month_plan_in_the_first_three_days(self):
		b = self.banner("2027-02-02 09:00:00")
		self.assertEqual((b["key"], b["text"]), ("month", "Plan February"))
		self.assertIsNone(self.banner("2027-02-04 09:00:00"))
		frappe.get_doc({"doctype": "Life Month Plan", "space": PRIVATE, "year": 2027, "month": 2}).insert()
		self.assertIsNone(self.banner("2027-02-02 09:00:00"))

	def test_cycle_weeks_and_precedence(self):
		frappe.db.set_value("Life Cycle", self.cycle, "status", "Active")
		other = frappe.get_all("Life Cycle", filters={"space": PRIVATE, "status": "Active", "name": ("!=", self.cycle)}, pluck="name")
		for c in other:
			frappe.db.set_value("Life Cycle", c, "status", "Closed")
		self.assertEqual(self.banner("2027-03-16 10:00:00")["key"], "plan-next")  # week 11, a Tuesday
		self.assertEqual(self.banner("2027-03-23 10:00:00")["key"], "close")  # week 12
		self.assertEqual(self.banner("2027-03-21 19:00:00")["key"], "review")  # Sunday of week 11: the review comes first
		frappe.get_doc({"doctype": "Life Cycle", "space": PRIVATE, "title": "ux6 next", "start_date": "2027-04-05", "end_date": "2027-06-27",
			"status": "Planned"}).insert()
		self.assertIsNone(self.banner("2027-03-16 10:00:00"))

	def test_skip_through_the_api_and_agents_get_none(self):
		frappe.set_user(self.owner_user())
		today_api.skip_banner("month:2027-02")
		self.assertIsNone(rhythms.banner(PRIVATE, "2027-02-02 09:00:00"))
		self.assertRaises(frappe.ValidationError, today_api.skip_banner, "anything")
		self.as_user(AGENT)
		self.assertIsNone(today_api.get(space=PRIVATE, at="2027-02-02 09:00:00")["banner"])

	def test_the_clock_moves_only_on_a_test_site(self):
		frappe.conf.lifeos_test_clock = 0
		try:
			self.assertEqual(getdate(rhythms.clock("2000-01-01 10:00:00")), getdate())
		finally:
			frappe.conf.lifeos_test_clock = 1
		self.assertEqual(str(rhythms.clock("2000-01-01 10:00:00"))[:10], "2000-01-01")
		self.assertEqual(add_days(getdate("2027-02-14"), 0).weekday(), DAYS.index("Sunday"))

	def owner_user(self):
		from lifeos.tests.base import OWNER

		return OWNER
