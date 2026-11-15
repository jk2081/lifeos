"""UX fixes, set 3: report, without changing, any user who has Life Agent together with Life User or Life Admin.
Saving such a user is refused from now on (lifeos.permissions.validate_user_roles)."""
import frappe


def execute():
	rows = frappe.db.sql(
		"""select a.parent from `tabHas Role` a
		where a.parenttype = 'User' and a.role = 'Life Agent'
		and exists (select 1 from `tabHas Role` b where b.parent = a.parent and b.parenttype = 'User' and b.role in ('Life User', 'Life Admin'))""")
	for (user,) in rows:
		print(f"Life OS: {user} has Life Agent together with Life User or Life Admin. Remove one of them; the app treats this user as a person, not an agent.")
