"""UX fixes, set 6: Settings > Rhythms, the area pins and colours, Backups."""
import frappe

from lifeos.api import settings
from lifeos.tests.base import PRIVATE, LifeTestCase


class TestSettings(LifeTestCase):
	def test_rhythms_save_and_read_back(self):
		before = settings.get(space=PRIVATE)["settings"]
		try:
			settings.save({"start_of_day": "05:30:00", "week_starts_on": "Sunday", "month_plan_enabled": 0, "cycle_break_week": 0, "weekly_review_day": "Saturday"})
			s = settings.get(space=PRIVATE)["settings"]
			self.assertEqual((s["start_of_day"][:5], s["week_starts_on"], s["month_plan_enabled"], s["cycle_break_week"], s["weekly_review_day"]),
				("05:30", "Sunday", 0, 0, "Saturday"))
		finally:
			settings.save({k: before[k] for k in ("start_of_day", "week_starts_on", "month_plan_enabled", "cycle_break_week", "weekly_review_day") if before[k] is not None})

	def test_area_pin_and_colour(self):
		a = self.areas["Tea"]
		settings.save_item("area", name=a, colour="violet", is_pinned=1)
		self.assertEqual(frappe.db.get_value("Life Area", a, ["colour", "is_pinned"]), ("violet", 1))
		settings.save_item("area", name=a, is_pinned=0)
		self.assertEqual(frappe.db.get_value("Life Area", a, "is_pinned"), 0)
		row = next(r for r in settings.get(space=PRIVATE)["areas"] if r.name == a)
		self.assertEqual(row.colour, "violet")

	def test_backups_report_what_the_site_says(self):
		b = settings.get(space=PRIVATE)["backups"]
		self.assertIn("configured", b)
		self.assertFalse(set(b["settings"]) - set(settings.BACKUP_KEYS))
