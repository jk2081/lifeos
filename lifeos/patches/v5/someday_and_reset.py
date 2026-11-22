"""UX fixes, set 5: fill the new dates on existing rows, so the counts that read them see every record.
- Life Note.last_opened_on: the day it was made (nobody's opening was recorded before).
- Life Task.last_touched_on, where empty: the day it was made."""
import frappe


def execute():
	frappe.db.sql("update `tabLife Note` set last_opened_on = date(creation) where last_opened_on is null")
	frappe.db.sql("""update `tabLife Index` x join `tabLife Note` n on n.name = x.ref_name and x.ref_doctype = 'Life Note'
		set x.last_opened_on = n.last_opened_on where x.last_opened_on is null""")
	frappe.db.sql("update `tabLife Task` set last_touched_on = date(creation) where last_touched_on is null")
	s = frappe.get_single("Life Settings")
	changed = False
	for field, value in (("stuck_after_days", 30), ("stuck_limit", 50), ("open_task_goal", 100), ("someday_review_months", 3),
			("ask_model", "claude-sonnet-5-5"), ("short_model", "claude-haiku-5-5"), ("monthly_cap_usd", 30)):
		if not s.get(field):
			s.set(field, value)
			changed = True
	if not s.ai_prices:
		from lifeos.ai.client import DEFAULT_PRICES

		for model, (inp, out) in DEFAULT_PRICES.items():
			s.append("ai_prices", {"model": model, "input_per_mtok": inp, "output_per_mtok": out})
		changed = True
	if changed:
		s.flags.ignore_permissions = True
		s.save()
	frappe.db.sql("update `tabLife Space` set ask_enabled = 1 where ask_enabled is null")
