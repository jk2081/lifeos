"""Issue 26: the ladder. Six levels computed from the person's own data; levels never skip; dismissing the card."""
import frappe

from lifeos import devtools, ladder
from lifeos.api import meta
from lifeos.tests.base import LifeTestCase

ANYA = "anya26@lifeos.test"
HER = "Anya's space"


class TestLadder(LifeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		devtools.make_user(ANYA, "Anya", ["Life User"])
		devtools.purge_space(HER, drop=True)
		frappe.get_doc({"doctype": "Life Space", "space_name": HER, "owner_user": ANYA,
			"members": [{"user": ANYA, "access": "Write"}]}).insert(ignore_permissions=True)

	def setUp(self):
		super().setUp()
		self.as_user("Administrator")
		for dt in ("Life Task", "Life Inbox Item", "Life Goal", "Life Review"):
			frappe.db.delete(dt, {"space": HER} if dt != "Life Review" else {"user": ANYA})
		frappe.db.delete("Life Space Member", {"parent": HER, "user": ("!=", ANYA)})
		frappe.db.set_value("Life Area", {"space": HER}, "is_on", 0)
		frappe.defaults.clear_default(ladder.DISMISSED_KEY, parent=ANYA)
		ladder.forget(ANYA)

	def level(self):
		ladder.forget(ANYA)
		self.as_user(ANYA)
		out = meta.setup_level()
		self.as_user("Administrator")
		return out

	def mk(self, doctype, **v):
		return frappe.get_doc({"doctype": doctype, "space": HER, **v}).insert(ignore_permissions=True)

	def areas_on(self, n):
		names = frappe.get_all("Life Area", filters={"space": HER, "is_life_area": 1}, pluck="name", limit=n)
		for a in names:
			frappe.db.set_value("Life Area", a, "is_on", 1)
		self.assertEqual(len(names), n)

	def test_1_each_step_moves_the_level_up_by_one(self):
		self.assertEqual(self.level()["level"], 1)
		self.mk("Life Task", title="i26 task")
		self.assertEqual(self.level()["level"], 1)
		self.mk("Life Inbox Item", title="i26 mail", source_type="Email", source_system="gmail")
		self.assertEqual(self.level()["level"], 2)
		self.areas_on(3)
		self.assertEqual(self.level()["level"], 2)  # three areas but no goal yet
		self.mk("Life Goal", title="i26 goal", horizon="Year", target_date="2027-12-31", area=frappe.db.get_value("Life Area", {"space": HER, "is_on": 1}))
		self.assertEqual(self.level()["level"], 3)
		self.mk("Life Review", user=ANYA, kind="Weekly", status="Locked", title="i26 review", period_start="2026-11-09", period_end="2026-11-15")
		self.assertEqual(self.level()["level"], 4)
		self.mk("Life Inbox Item", title="i26 job", job_id="i26-job", status="Done", claimed_by=ANYA)
		self.assertEqual(self.level()["level"], 5)
		self.assertFalse(self.level()["complete"])
		sp = frappe.get_doc("Life Space", HER)
		sp.append("members", {"user": "family@lifeos.test", "access": "Write"})
		sp.save(ignore_permissions=True)
		out = self.level()
		self.assertEqual(out["level"], 6)
		self.assertTrue(out["complete"] and out["next"] is None)

	def test_2_levels_do_not_skip(self):
		self.mk("Life Task", title="i26 task")
		self.mk("Life Review", user=ANYA, kind="Weekly", status="Locked", title="i26 review", period_start="2026-11-09", period_end="2026-11-15")
		out = self.level()
		self.assertEqual(out["level"], 1)
		self.assertEqual(out["next"]["title"], "Connect a source")
		self.assertTrue(out["next"]["text"].startswith("Next: Connect a source"))

	def test_3_the_next_step_for_a_weekly_review_and_an_upload_is_not_a_source(self):
		self.mk("Life Task", title="i26 task")
		self.mk("Life Inbox Item", title="i26 file", source_type="Upload")
		self.assertEqual(self.level()["level"], 1)
		self.mk("Life Inbox Item", title="i26 mail", source_type="Email", source_system="gmail")
		self.areas_on(3)
		self.mk("Life Goal", title="i26 goal", horizon="Year", target_date="2027-12-31", area=frappe.db.get_value("Life Area", {"space": HER, "is_on": 1}))
		nxt = self.level()["next"]
		self.assertEqual(nxt["to"], "/review")
		self.assertIn("a weekly review · 30 minutes on Sunday. Review joins the menu after your first one.", nxt["text"])

	def test_4_dismiss_hides_the_card_for_that_person_only_and_undo_brings_it_back(self):
		self.assertFalse(self.level()["dismissed"])
		self.as_user(ANYA)
		self.assertTrue(meta.dismiss_setup()["dismissed"])
		self.as_user("Administrator")
		self.assertTrue(self.level()["dismissed"])
		self.as_user("family@lifeos.test")
		self.assertFalse(meta.setup_level()["dismissed"])
		self.as_user(ANYA)
		self.assertFalse(meta.dismiss_setup(undo=1)["dismissed"])
