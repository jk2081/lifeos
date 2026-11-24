"""Issue 100: the events already on the calendar get the rule's answer for `life_key_date` (all-day and multi-day events are key dates);
the key-date skill judges the ones that change from now on."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from lifeos import install


def execute():
	create_custom_fields({"Event": install.MEETING_FIELDS}, ignore_validate=True)  # the fields come with the app's migrate, which runs after patches
	frappe.db.sql("""update `tabEvent` set life_key_date = if(all_day = 1 or date(ends_on) > date(starts_on), 1, 0), life_key_date_set_by = 'Rule'
		where ifnull(life_key_date_set_by, '') = ''""")
