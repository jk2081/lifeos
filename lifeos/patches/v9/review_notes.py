"""Set 8: each weekly review note of set 7 and earlier ("Weekly review, 16 Nov 2026" under Reviews) becomes a Locked Life
Review for the week it names, with the note in `went_well`. The note stays where it is; `note` on the review points to it, which
makes the patch safe to run again. A note whose title does not parse as a date is left alone (see DECISIONS.md)."""
from datetime import datetime

import frappe
from frappe.utils import add_days

PREFIX = "Weekly review, "


def execute():
	for n in frappe.db.sql("""select name, space, title, content_md, owner, modified from `tabLife Note`
		where title like 'Weekly review, %%'""", as_dict=True):
		if frappe.db.exists("Life Review", {"note": n.name}):
			continue
		try:
			start = datetime.strptime(n.title[len(PREFIX):].strip(), "%d %b %Y").date()
		except ValueError:
			continue
		user = n.owner if n.owner and n.owner != "Administrator" else frappe.db.get_value("Life Space", n.space, "owner_user")
		if not user:
			continue
		frappe.get_doc({"doctype": "Life Review", "space": n.space, "user": user, "kind": "Weekly", "status": "Locked",
			"period_start": start, "period_end": add_days(start, 6), "title": n.title, "went_well": (n.content_md or "").strip() or "(no notes)",
			"locked_on": n.modified, "note": n.name, "tab_state": "{}"}).insert(ignore_permissions=True)
