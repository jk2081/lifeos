"""Ask tool: the daily email digests Life OS already wrote (issue 107). For "summarise the last two weeks" Ask reads these first and searches the
inbox only for the days that have none."""
import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate

from lifeos import permissions
from lifeos.tools import actions

MAX_DAYS = 62
TEXT_CAP = 4000


def read(start: str, end: str, space: str | None = None, source_system: str | None = None) -> dict:
	"""The daily email digests of the days `start` to `end` (YYYY-MM-DD, both included): each day's digest text, and the days that have no digest.
	A digest is one note of the mail from real people that came in that day. Use it before searching the inbox for a period."""
	space = permissions.resolve_space(space)
	actions.check_read(space, source_system)
	lo, hi = getdate(start), getdate(end)
	if hi < lo or (hi - lo).days >= MAX_DAYS:
		frappe.throw(_("Ask for at most {0} days, start first.").format(MAX_DAYS), title=_("Period not understood"))
	user = frappe.session.user if not permissions.is_agent() else actions.person_of_space(space)
	by_day = {}
	rows = frappe.get_list("Life Inbox Item", filters={"space": space, "source_type": "Email Digest", "external_id": ["like", f"digest:{user}:day:%"]},
		fields=["name", "title", "raw_text", "external_id", "is_sensitive"], order_by="external_id asc", limit=500)
	for r in rows:
		day = getdate(r.external_id.rsplit(":", 1)[1])
		if lo <= day <= hi and not r.is_sensitive:
			by_day[day] = r
	days = [{"date": str(d), "item": r.name, "title": r.title, "text": (r.raw_text or "")[:TEXT_CAP]} for d, r in sorted(by_day.items())]
	missing = [str(add_days(lo, i)) for i in range((hi - lo).days + 1) if add_days(lo, i) not in by_day]
	return {"digests": days, "missing_days": missing, "from": str(lo), "to": str(hi), "found": cint(len(days))}
