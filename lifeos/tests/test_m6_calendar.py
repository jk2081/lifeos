import frappe
from frappe.utils import add_days, getdate, today

from lifeos.api import calendar
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


def titles(items, source=None):
	return [i["title"] for i in items if not source or i["source"] == source]


class TestCalendar(LifeTestCase):
	def test_important_dates_repeat_every_year(self):
		calendar.add_important_date(space=PRIVATE, title="Ruchi m6", day=14, month=1, kind="Birthday")
		for year in (2026, 2027, 2031):
			items = calendar.get(space=PRIVATE, from_date=f"{year}-01-10", to_date=f"{year}-01-20")["items"]
			hits = [i for i in items if i["source"] == "important" and i["title"] == "Ruchi m6"]
			self.assertEqual([h["date"] for h in hits], [f"{year}-01-14"])

	def test_29_february_shows_every_year(self):
		calendar.add_important_date(space=PRIVATE, title="Leap day m6", day=29, month=2)
		leap = calendar.get(space=PRIVATE, from_date="2028-02-25", to_date="2028-03-02")["items"]
		self.assertEqual([i["date"] for i in leap if i["title"] == "Leap day m6"], ["2028-02-29"])
		common = calendar.get(space=PRIVATE, from_date="2027-02-25", to_date="2027-03-02")["items"]
		self.assertEqual([i["date"] for i in common if i["title"] == "Leap day m6"], ["2027-02-28"])
		self.assertIn("Leap day m6", [e["title"] for e in calendar.year(space=PRIVATE, year=2027)["days"]["2027-02-28"]])

	def test_year_of_first_occurrence(self):
		calendar.add_important_date(space=PRIVATE, title="Wedding m6", day=23, month=11, year=2010, kind="Anniversary")
		items = calendar.get(space=PRIVATE, from_date="2026-11-20", to_date="2026-11-25")["items"]
		self.assertEqual([i["label"] for i in items if i["title"] == "Wedding m6"], ["Wedding m6 (16)"])
		self.assertEqual([i for i in calendar.get(space=PRIVATE, from_date="2009-11-20", to_date="2009-11-25")["items"] if i["title"] == "Wedding m6"], [])

	def test_calendar_merges_four_sources(self):
		day = add_days(getdate(today()), 3)
		calendar.add_event(space=PRIVATE, subject="Meeting m6", starts_on=f"{day} 10:00:00", ends_on=f"{day} 11:00:00")
		calendar.add_important_date(space=PRIVATE, title="Birthday m6", day=day.day, month=day.month)
		self.make("Life Task", title="Task due m6", due_date=day)
		self.make("Life Task", title="Done task m6", due_date=day, status="Done")
		self.make("Life Vault Document", title="Passport m6", expiry_date=day)
		data = calendar.get(space=PRIVATE, from_date=str(day), to_date=str(day))
		self.assertEqual(titles(data["items"], "event"), ["Meeting m6"])
		self.assertEqual(titles(data["items"], "important"), ["Birthday m6"])
		self.assertEqual(titles(data["items"], "task"), ["Task due m6"])
		self.assertEqual(titles(data["items"], "vault"), ["Passport m6 expires"])
		self.assertEqual(data["google"]["connected"], False)  # works without the Google connection
		wide = calendar.get(space=PRIVATE, from_date="2026-01-01", to_date="2027-12-31")
		self.assertLessEqual((getdate(wide["to_date"]) - getdate(wide["from_date"])).days, 100)

	def test_year_view_rules(self):
		calendar.add_event(space=PRIVATE, subject="Phuket m6", starts_on="2029-01-07", ends_on="2029-01-11", all_day=1)
		calendar.add_event(space=PRIVATE, subject="Board day m6", starts_on="2029-02-26", all_day=1)
		calendar.add_event(space=PRIVATE, subject="Timed meeting m6", starts_on="2029-03-03 10:00:00", ends_on="2029-03-03 11:00:00")
		calendar.add_important_date(space=PRIVATE, title="Jai m6", day=20, month=1)
		self.make("Life Vault Document", title="Licence m6", expiry_date="2029-12-12")
		cycle = self.make("Life Cycle", title="Y cycle", start_date="2029-10-01", status="Planned")
		data = calendar.year(space=PRIVATE, year=2029)
		days = data["days"]
		for d in ("07", "08", "09", "10", "11"):  # a multi-day event marks each of its days
			self.assertIn(("trip", "Phuket m6"), [(e["type"], e["title"]) for e in days[f"2029-01-{d}"]])
		self.assertNotIn("2029-01-12", [k for k, v in days.items() if any(e["title"] == "Phuket m6" for e in v)])
		self.assertIn(("event", "Board day m6"), [(e["type"], e["title"]) for e in days["2029-02-26"]])
		self.assertNotIn("Timed meeting m6", [e["title"] for v in days.values() for e in v])  # timed meetings are left out
		self.assertIn("Jai m6", [e["title"] for e in days["2029-01-20"]])
		self.assertIn(("vault", "Licence m6 expires"), [(e["type"], e["title"]) for e in days["2029-12-12"]])
		self.assertIn("12WY starts", [e["title"] for e in days["2029-10-01"]])
		self.assertIn("12WY ends", [e["title"] for e in days["2029-12-23"]])
		self.assertEqual([c["name"] for c in data["cycles"]], [cycle.name])
		self.assertIn("Jai m6", [e["title"] for e in calendar.year(space=PRIVATE, year=2030)["days"]["2030-01-20"]])  # in every year

	def test_agent_event_is_visible_to_the_owner_and_not_to_outsiders(self):
		self.as_user(AGENT)
		out = calendar.add_event(space=PRIVATE, subject="Agent event m6", starts_on="2026-11-20 09:00:00")
		event = frappe.get_doc("Event", out["name"])
		self.assertEqual((event.owner, event.life_space), (AGENT, PRIVATE))
		self.as_user(OWNER)
		self.assertIn(out["name"], frappe.get_list("Event", pluck="name", limit=0))
		self.assertTrue(frappe.get_doc("Event", out["name"]).has_permission("read"))
		self.assertIn("Agent event m6", titles(calendar.get(space=PRIVATE, from_date="2026-11-20", to_date="2026-11-20")["items"]))
		self.as_user(FAMILY)
		self.assertNotIn(out["name"], frappe.get_list("Event", pluck="name", limit=0))
		self.assertFalse(frappe.get_doc("Event", out["name"]).has_permission("read"))
		self.assertRaises(frappe.PermissionError, calendar.get, space=PRIVATE)
		self.assertRaises(frappe.PermissionError, calendar.year, space=PRIVATE)
		self.assertNotIn("Agent event m6", titles(calendar.get(space=SHARED, from_date="2026-11-20", to_date="2026-11-20")["items"]))
		self.assertRaises(frappe.PermissionError, calendar.delete_event, out["name"])
		self.assertRaises(frappe.PermissionError, calendar.add_event, space=PRIVATE, subject="x", starts_on="2026-11-20")
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, calendar.delete_event, out["name"])  # agents never delete
		self.as_user(OWNER)
		calendar.delete_event(out["name"])

	def test_event_from_a_user_takes_their_default_space(self):
		# the family member owns no space, so the site default applies when they belong to it
		before = frappe.db.get_single_value("Life Settings", "default_space")
		frappe.db.set_single_value("Life Settings", "default_space", SHARED)
		self.addCleanup(frappe.db.set_single_value, "Life Settings", "default_space", before)
		self.as_user(FAMILY)
		event = frappe.get_doc({"doctype": "Event", "subject": "Synced from Google m6", "starts_on": "2026-11-21 09:00:00"}).insert()
		self.assertEqual(event.life_space, SHARED)
		self.as_user(OWNER)
		self.assertIn("Synced from Google m6", titles(calendar.get(space=SHARED, from_date="2026-11-21", to_date="2026-11-21")["items"]))
