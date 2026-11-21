"""Development helpers for the set 8 acceptance checks (tools/acceptance.mjs, S8): data shaped like the owner's for the weekly
review, on the acceptance site only, and its clean-up. Every record's title carries "S8 … <width> <stamp>"."""
import json

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

OWNER = "owner@lifeos.test"
SPACE = "Private"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def setup(tag):
	"""Owner-shaped data around a fresh review; returns the names the checks use, and the settings to restore."""
	if frappe.conf.get("lifeos_fake_calendar") != 1 or not frappe.conf.get("lifeos_strict_get"):
		frappe.throw("Only on the acceptance site.")  # nosemgrep: frappe-missing-translate-function-python -- development tool, never shown in the app
	from lifeos import readings
	from lifeos.review import gcal

	frappe.set_user(OWNER)  # nosemgrep: frappe-setuser -- development tool on the acceptance site: the owner-shaped data is made as the owner
	frappe.db.delete("Life Review", {"space": SPACE, "user": OWNER})
	s = frappe.get_single("Life Settings")
	was = {"weekly_review_day": s.weekly_review_day, "weekly_review_time": str(s.weekly_review_time or "18:00:00")}
	s.weekly_review_day, s.weekly_review_time = DAYS[getdate(today()).weekday()], "00:00:00"
	s.save(ignore_permissions=True)
	_unskip_banner()
	# earlier checks' findings out of the way, so the five revelations are this run's
	frappe.db.sql("update `tabLife Insight` set status='Dismissed' where space=%s and status='New'", SPACE)
	area = frappe.db.get_value("Life Area", {"space": SPACE, "area_name": "Tea & Coffee"})
	cycle = frappe.db.get_value("Life Cycle", {"space": SPACE, "status": "Active"})
	cycle_goal = frappe.db.get_value("Life Goal", {"cycle": cycle, "outcome": "In Progress"}, "name", order_by="sort_order asc")
	out = {"was": was}
	# a number goal in the cycle, with a reading suggested from a voice note
	src = _item(f"S8 voice reading {tag}", "Voice Note", "Done", f"Mr. Rao reported 1,460 kg/ha for October ({tag}).")
	out["number"] = _doc("Life Goal", title=f"S8 yield {tag}", horizon="12 weeks", cycle=cycle, area=area, measure_kind="Number",
		measure="Ghillidary yield", unit="kg/ha", start_value=1200, target_value=1800)
	out["reading"] = readings.suggest(out["number"], 1460, excerpt="Mr. Rao reported 1,460 kg/ha for October.", source_doctype="Life Inbox Item",
		source_name=src, by="Agent").name
	# a milestone goal without its finish line, and a goal no longer in a cycle
	out["milestone"] = _doc("Life Goal", title=f"S8 milestone {tag}", horizon="12 weeks", cycle=cycle, area=area, measure_kind="Milestone", done_when="Signed")
	frappe.db.set_value("Life Goal", out["milestone"], "done_when", None)
	# stuck and waiting tasks, made before the review's period
	def task(title, age, **kw):
		name = _doc("Life Task", title=f"S8 {title} {tag}", status=kw.pop("status", "Open"), area=area, **kw)
		frappe.db.set_value("Life Task", name, {"last_touched_on": add_days(today(), -age), "creation": add_days(now_datetime(), -max(age, 20))},
			update_modified=False)
		return name
	out["needs"] = task("serves the cycle", 40, goal=cycle_goal)
	out["keep"] = task("still recent", 40)
	out["park"] = [task(f"park {i}", 70 + i) for i in range(3)]
	out["letgo"] = task("ancient", 130)
	out["waiting"] = task("drainage photos", 10, status="Waiting", waiting_on="Ravi")
	# Inbox items of every kind, waiting for review
	out["inbox"] = [_item(f"S8 {k.lower()} {tag}", k, "To Review", "x", proposal=True) for k in ("Voice Note", "Email", "Journal Photo", "Message", "Web")]
	# a voice note made right after a meeting that matters, with a promise in it
	gcal.sync_user(OWNER)
	ev = frappe.db.get_value("Event", {"google_calendar_event_id": "fixture-dalmia", "life_space": SPACE}, ["name", "ends_on"], as_dict=True)
	out["meeting"] = ev.name
	out["voice"] = _item(f"S8 voice after Dalmia {tag}", "Voice Note", "Done", f"I will S8 send the blend sheet to Mithun {tag}. Good meeting.",
		at=get_datetime(ev.ends_on) + frappe.utils.datetime.timedelta(minutes=10))
	frappe.db.set_value("Event", ev.name, "life_followups_on", None, update_modified=False)
	return out


def cleanup(stamp, was=None):
	"""Remove what the run made that its titles do not mark, and put the settings back."""
	frappe.db.delete("Life Review", {"space": SPACE, "user": OWNER})
	frappe.db.sql("update `tabLife Task` set is_top_three = 0 where space = %s and is_top_three = 1", SPACE)
	for name in frappe.get_all("Life Task", filters={"space": SPACE, "title": ("like", f"Chase %{stamp}%")}, pluck="name"):
		frappe.delete_doc("Life Task", name, ignore_permissions=True, force=True, delete_permanently=True)
	frappe.db.sql("delete from `tabLife Insight` where space = %s and (title like %s or body like %s)", (SPACE, f"%{stamp}%", f"%{stamp}%"))
	for link in frappe.get_all("Life Meeting Link", filters={"space": SPACE}, fields=["name", "record_doctype", "record_name"]):
		if not frappe.db.exists(link.record_doctype, link.record_name):
			frappe.db.delete("Life Meeting Link", link.name)
	if was:
		was = json.loads(was) if isinstance(was, str) else was
		s = frappe.get_single("Life Settings")
		s.weekly_review_day, s.weekly_review_time = was["weekly_review_day"], was["weekly_review_time"]
		s.save(ignore_permissions=True)


def _doc(doctype, **values):
	d = frappe.get_doc({"doctype": doctype, "space": SPACE, **values})
	d.flags.ignore_permissions = True
	return d.insert().name


def _item(title, kind, status, text, proposal=False, at=None):
	name = _doc("Life Inbox Item", title=title, source_type=kind, raw_text=text, status=status)
	if at:
		frappe.db.set_value("Life Inbox Item", name, "received_on", at, update_modified=False)
	if proposal:
		frappe.get_doc({"doctype": "Life Proposal", "space": SPACE, "inbox_item": name, "kind": "Task", "status": "Pending",
			"preview": f"Task: {title}", "payload": json.dumps({"title": title})}).insert(ignore_permissions=True)
	return name


def _unskip_banner():
	from lifeos import rhythms

	state = rhythms._state(OWNER)
	for k in ("skipped", "done"):
		state[k] = [o for o in state.get(k, []) if not o.startswith("review:")]
	rhythms._save(state, OWNER)
