"""Issue 14: the new navigation. The server's part: whether Review is in the sidebar (after the person's first locked weekly
review) and the Brain's Needs you count, which is the Inbox's. The sidebar, the tabs as routes, the old routes and the
phone bar are checked in the browser by acceptance checks I14.<width>.1 to .7."""
import frappe
from frappe.utils import add_days, now_datetime, today

from lifeos.api import inbox, session
from lifeos.tests.base import FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


class TestNavigation(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Review", {"user": ("in", [OWNER, FAMILY])})

	def lock(self, user, space=PRIVATE):
		return frappe.get_doc({"doctype": "Life Review", "space": space, "user": user, "kind": "Weekly", "status": "Locked",
			"period_start": add_days(today(), -6), "period_end": today(), "locked_on": now_datetime(), "title": "i14 review",
			"tab_state": "{}"}).insert(ignore_permissions=True)

	# acceptance test 2: Review is hidden until one is locked, then shown
	def test_review_is_shown_only_after_the_person_locks_a_weekly_review(self):
		self.assertFalse(session.counts(PRIVATE)["reviewed"])
		frappe.get_doc({"doctype": "Life Review", "space": PRIVATE, "user": OWNER, "kind": "Weekly", "status": "Open",
			"period_start": add_days(today(), -6), "period_end": today(), "title": "i14 open", "tab_state": "{}"}).insert(ignore_permissions=True)
		self.assertFalse(session.counts(PRIVATE)["reviewed"], "an open review does not count")
		self.lock(OWNER)
		self.assertTrue(session.counts(PRIVATE)["reviewed"])
		self.assertTrue(session.counts(SHARED)["reviewed"], "the review is the person's, whichever space is open")
		frappe.set_user(FAMILY)
		self.assertFalse(session.counts(SHARED)["reviewed"], "another person's review does not show Review")

	# acceptance test 3: Brain's count is the Inbox count
	def test_the_brain_count_is_the_number_of_inbox_items_to_review(self):
		item = inbox.create_item("i14 capture to review", "Message", space=PRIVATE, raw_text="i14")
		frappe.db.set_value("Life Inbox Item", item["name"], "status", "To Review")
		c = session.counts(PRIVATE)
		listed = inbox.list(space=PRIVATE, status='["To Review"]', page_length=1)["total"]
		self.assertGreaterEqual(listed, 1)
		self.assertEqual(c["to_review"], listed)
		self.assertEqual(c["doors"]["inbox"]["n"], listed)
