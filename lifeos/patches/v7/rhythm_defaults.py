"""Set 6, Settings > Rhythms: the new settings start with their defaults on a site that existed before them. The weekly
review day and time and the score target keep their values; they only move on screen."""
import frappe

DEFAULTS = {"start_of_day": "06:00:00", "week_starts_on": "Monday", "month_plan_enabled": 1, "cycle_break_week": 1}


def execute():
	frappe.reload_doc("life", "doctype", "life_settings")
	for field, value in DEFAULTS.items():
		# a setting never saved has no row in tabSingles (a Check would read as 0, not as "not set")
		saved = frappe.db.sql("select 1 from `tabSingles` where doctype='Life Settings' and field=%s and ifnull(value, '') != ''", field)
		if not saved:
			frappe.db.set_single_value("Life Settings", field, value)
