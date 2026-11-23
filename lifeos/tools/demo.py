"""Example records for screenshots and manual testing. Not the owner's data.

Load:    bench --site SITE execute lifeos.tools.demo.load
Remove:  bench --site SITE execute lifeos.tools.demo.remove
"""
import frappe
from frappe.utils import add_days, add_to_date, getdate, now_datetime, today

from lifeos.calendar import calendar_data
from lifeos.goals import cycles
from lifeos.tools import devtools, seed
from lifeos import permissions
from lifeos.goals import habits as habit_rules

DEMO_AREAS = ["Business That Works", "Family", "Learning", "Money & Legal", "Personal", "Tea & Coffee", "Unstoppable & Content"]
CYCLE_TITLE = "Oct to Dec 2026"
CYCLE_START = "2026-10-05"  # first Monday of October 2026
HABITS = ["Meditate", "Walk", "Journal", "Workout"]

# (goal, area, [actions]); an action ending in "*" is already done
GOALS = [
	("Launch the new website", "Business That Works", ["Write the launch plan", "Pick a designer", "Draft the home page", "Set up analytics"]),
	("Tidy up loose ends", "Personal", ["File the tax return", "Renew the licence", "Book the passport photo*", "Fix the bookshelf", "Back up the photos"]),
	("Run a 10 km race", "Personal", ["Run three times a week", "Stretch after each run", "Buy new shoes"]),
	("Build a savings buffer", "Money & Legal", ["Meet the adviser", "Set up a monthly transfer"]),
	("Improve the tea blend", "Tea & Coffee", ["Taste five samples", "Write the tasting notes", "Visit the supplier", "Agree the new blend"]),
	("Get stronger", "Personal", ["Cut sugar", "Eat more protein", "Strength session", "Walk daily"]),
	("Learn a new skill", "Learning", ["Finish the course", "Do the exercises", "Read three books [?]", "Build a small project"]),
]
# (goal, status, area) for the October plan, in priority order
OCTOBER = [
	("Hire a part-time assistant", "Carried", "Business That Works"), ("Publish the first newsletter", "Carried", "Business That Works"),
	("Renew the driving licence", "Carried", "Personal"), ("File the tax return", "Open", "Money & Legal"),
	("Book the passport photo", "Done", "Family"), ("Finish the course", "Carried", "Learning"), ("Agree the new blend", "Open", "Tea & Coffee"),
]

# ticks per action for the weeks so far: x done, - missed
TICKS = {
	"Write the launch plan": "--xxxx", "Pick a designer": "-----x", "Draft the home page": "-x-xxx",
	"File the tax return": "---xxx", "Book the passport photo": "--x", "Run three times a week": "x-xx-x",
	"Stretch after each run": "xx-xxx", "Set up a monthly transfer": "-xxxxx", "Taste five samples": "--xxxx",
	"Visit the supplier": "---x--", "Strength session": "x--x-x", "Walk daily": "xx-xxx", "Finish the course": "-xxxxx",
	"Do the exercises": "--xx-x",
}
HABIT_MISSES = {"Meditate": {4, 10}, "Walk": {2, 4, 9, 10}, "Journal": {1, 3, 4, 6, 8, 10, 12}, "Workout": {1, 2, 4, 5, 7, 9, 10, 12}}


def _user(email):
	return email if frappe.db.exists("User", email) else "Administrator"


def load_cycle(space):
	"""The active cycle with its goals and actions, the habits and October's goals."""
	from frappe.utils import add_days as _add

	seed.ensure_structure()
	frappe.db.set_single_value("Life Settings", "use_focuses", 1)  # the demo site uses focuses (issue 57); a new site does not
	areas = seed.make_areas(space, DEMO_AREAS)
	t = seed.Tracker(seed.DEMO_KEY)
	for i, title in enumerate(HABITS):
		tracking = {"days_per_week": 7, "sort_order": i + 1, "tracked_from": "2026-10-01"}
		name = frappe.db.get_value("Life Habit", {"space": space, "title": title})
		if name:
			frappe.db.set_value("Life Habit", name, tracking)
		else:
			t.insert({"doctype": "Life Habit", "space": space, "title": title, **tracking})
	cycle = t.insert({"doctype": "Life Cycle", "space": space, "title": CYCLE_TITLE, "start_date": CYCLE_START, "status": "Active"})
	for i, (title, area, actions) in enumerate(GOALS):
		rows = []
		for a in actions:
			done = a.endswith("*")
			rows.append({"title": a.rstrip("*"), "per_week": 1, "status": "Done" if done else "Open",
				"done_on": _add(CYCLE_START, 14) if done else None})
		t.insert({"doctype": "Life Goal", "space": space, "cycle": cycle.name, "title": title, "area": areas.get(area),
			"sort_order": i + 1, "actions": rows})
	for order, (title, status, area_name) in enumerate(OCTOBER, 1):
		t.insert({"doctype": "Life Goal", "space": space, "title": title, "horizon": "Month", "target_date": "2026-10-31", "sort_order": order,
			"area": areas.get(area_name), "outcome": {"Done": "Achieved", "Carried": "Carried"}.get(status, "In Progress")})
	t.save()


def load(space="Private"):
	"""The demo's goals are made as plain records, many of them with no Done when: the setting that asks for one is off while
	they are made, and left as it was."""
	was = frappe.db.get_value("Singles", {"doctype": "Life Settings", "field": "require_done_when"}, "value", order_by=None)
	frappe.db.set_single_value("Life Settings", "require_done_when", 0)
	frappe.flags.lifeos_allow_open_goals = True  # the demo's open-ended goals predate the retirement of the Open goal (issue 57)
	try:
		return _load(space)
	finally:
		frappe.flags.lifeos_allow_open_goals = False
		frappe.db.delete("Singles", {"doctype": "Life Settings", "field": "require_done_when"})
		if was is not None:
			frappe.db.set_single_value("Life Settings", "require_done_when", was)
		frappe.clear_cache(doctype="Life Settings")


def _load(space="Private"):
	if frappe.parse_json(frappe.db.get_default(seed.DEMO_KEY) or "[]"):
		return "Demo data is already loaded. Run lifeos.tools.demo.remove first."
	if not frappe.db.exists("Life Cycle", {"space": space, "title": CYCLE_TITLE}):
		load_cycle(space)
	owner, agent = _user(devtools.OWNER), _user(devtools.AGENT)
	frappe.set_user(owner)  # nosemgrep: frappe-setuser -- demo data: records are made through the API as the owner and the agent would make them
	permissions.clear_cache()
	t = seed.Tracker(seed.DEMO_KEY)
	now = getdate(today())
	area = {a.area_name: a.name for a in frappe.get_all("Life Area", filters={"space": space}, fields=["name", "area_name"])}
	career, tea = area["Career"], area["Tea & Coffee"]

	# the estates are parts of Career beside Tea & Coffee: parts are one level deep (issue 11)
	for i, name in enumerate(["Ghatia", "Ghillidary", "Chandighat", "Chikmagalur", "Head office"]):
		area[name] = t.insert({"doctype": "Life Area", "space": space, "area_name": name, "parent_area": career, "sort_order": i + 10}).name

	people = {}
	for name, relation in (("Jai", "Self"), ("Ruchi", "Wife"), ("Anya", "Daughter"), ("Vivek", "Accountant")):
		people[name] = t.insert({"doctype": "Life Person", "space": space, "full_name": name, "relation": relation}).name

	def open_goal(title, area_name, status="Active", outcome=None, target=None):
		# an open-ended goal: a long-term goal with a finish line
		goal = t.insert({"doctype": "Life Goal", "space": space, "title": title, "area": area[area_name], "horizon": "Long term",
			"on_hold": 1 if status == "On Hold" else 0, "done_when": outcome, "measure_kind": "Milestone" if outcome else None, "target_date": target}).name
		return goal

	ghl = open_goal("Ghillidary turnaround", "Tea & Coffee", outcome="A drainage and replanting plan for the poor sections", target="2026-12-31")
	mandir = open_goal("Ghatia mandir", "Tea & Coffee", outcome="Contractor appointed within the budget")
	audit = open_goal("RMT internal audit", "Tea & Coffee", "On Hold", "First internal audit completed")
	funnel = open_goal("Owner outreach funnel", "Business That Works", outcome="Twenty owner conversations booked")
	dalmia = open_goal("Dalmia Gold", "Business That Works", outcome="Blend blueprint agreed with Mithun")

	goals = {g.title: g.name for g in frappe.get_all("Life Goal", filters={"space": space, "cycle": ("like", "%")}, fields=["name", "title", "cycle"])
		if frappe.db.get_value("Life Cycle", g.cycle, "status") == "Active"}

	def task(title, area_name, age=0, **kw):
		doc = t.insert({"doctype": "Life Task", "space": space, "title": title, "area": area.get(area_name), **kw})
		if age:
			frappe.db.set_value("Life Task", doc.name, "creation", add_to_date(now_datetime(), days=-age), update_modified=False)
			doc.reload()
			from lifeos.library import index
			index.update(doc)
		return doc

	task("Download Merrill statements for Ruchi ITR", "Money & Legal", due_date=add_days(now, -2))
	task("Send quote request to data vendors", "Business That Works", due_date=now, priority="I", goal=funnel)
	task("Six questions to Mithun on the blend sheets", "Business That Works", due_date=now, priority="I", goal=dalmia)
	task("Run 5 km, easy pace", "Personal", due_date=now, goal=goals.get("Run a 10 km race"))
	task("Make detailed plan for poor sections", "Tea & Coffee", due_date=add_days(now, 5), priority="I", goal=ghl)
	task("Visit leased gardens", "Tea & Coffee", age=20, priority="I", goal=ghl)
	task("Decide the main deity for the sanctum", "Tea & Coffee", age=7, goal=mandir)
	task("Start RMT newsletter", "Tea & Coffee", age=30)
	task("Shortlist three contractors", "Tea & Coffee", due_date=add_days(now, 9), goal=mandir)
	task("Agree audit scope with the auditor", "Tea & Coffee", age=40, goal=audit, status="Waiting", waiting_on="Auditor to confirm dates")
	for title, a in (("Renew club membership", "Personal"), ("Fix the study bookshelf", "Family"), ("Read the PMS term sheet", "Money & Legal"),
			("Back up the photo library", "Personal")):
		task(title, a, age=25)
	for title, days in (("Soil test report for section 7", 3), ("Drainage survey, lower division", 6), ("Replanting budget draft", 12), ("Nursery stock count", 16)):
		doc = task(title, "Tea & Coffee", goal=ghl, age=days + 5)
		doc.status = "Done"
		doc.save()
		frappe.db.set_value("Life Task", doc.name, "completed_on", add_days(now, -days), update_modified=False)
		doc.reload()
		from lifeos.library import index
		index.update(doc)
	stale = task("Sort old tax papers", "Money & Legal", age=120)
	frappe.db.set_value("Life Task", stale.name, "last_touched_on", add_days(now, -120), update_modified=False)

	training = t.insert({"doctype": "Life Note", "space": space, "title": "Estate training programme outline", "area": tea,
		"content_md": "## Aim\n\nTrained manpower and a formal training programme for every estate.\n\n## First steps\n\n- Supervisors first, then field staff\n- One module a month\n- See [[New crops by estate]] for the crop side\n"})
	crops = t.insert({"doctype": "Life Note", "space": space, "title": "New crops by estate", "area": tea,
		"content_md": "Pepper and avocado trials.\n\n| Estate | Crop |\n| --- | --- |\n| Ghatia | Pepper |\n| Chikmagalur | Avocado |\n"})
	t.insert({"doctype": "Life Note", "space": space, "title": "Recreation area layout, pickleball and pavilion", "area": tea, "goal": mandir,
		"content_md": "Court next to the pavilion. Links to [[Estate training programme outline]] for the staff welfare part and to [[Ruchi]]."})
	t.insert({"doctype": "Life Note", "space": space, "title": "Land ceiling writ, labour lines", "area": area["Money & Legal"],
		"also_in": [{"area": tea}], "content_md": "Notes on the writ. Relevant to the estates as well.\n\nSee [[New crops by estate]]."})
	t.insert({"doctype": "Life Note", "space": space, "title": "Dalmia Gold blend blueprint", "area": area["Business That Works"],
		"also_in": [{"area": tea}], "goal": dalmia, "content_md": "Blend sheet questions for Mithun."})
	reviews = t.insert({"doctype": "Life Note", "space": space, "title": "Reviews", "area": area["Personal"], "content_md": "Weekly review notes live under this note."})

	licence = t.insert({"doctype": "Life Vault Document", "space": space, "title": "Driving licence", "doc_type": "ID", "holder": people["Jai"],
		"number_last4": "4821", "expiry_date": add_days(now, 28), "remind_days_before": 60, "area": area["Personal"]})
	t.insert({"doctype": "Life Vault Document", "space": space, "title": "Anya passport", "doc_type": "Travel", "holder": people["Anya"],
		"number_last4": "7730", "issue_date": "2026-10-20", "expiry_date": "2031-10-19", "area": area["Family"]})
	brief = t.insert({"doctype": "Life Vault Document", "space": space, "title": "Ghatia Mandir, Contractor Brief", "doc_type": "Property",
		"area": tea, "goal": mandir})
	f = devtools.attach("Life Vault Document", brief.name, "Ghatia Mandir, Contractor Brief.pdf", devtools.pdf_bytes(), "file")
	brief.db_set("file", f.file_url, update_modified=False)

	def chat(title, days_ago, area_name, items, goal=None, assistant="Claude", summary=""):
		return t.insert({"doctype": "Life Chat Log", "space": space, "title": title, "date": add_days(now, -days_ago), "assistant": assistant,
			"url": "https://claude.ai/chat/example", "area": area[area_name], "goal": goal, "summary_md": summary,
			"open_items": [{"text": x} for x in items]})

	chat("Mandir size and budget planning", 6, "Tea & Coffee", ["Decide the main deity for the sanctum", "Get two contractor quotes",
		"Confirm the plinth height", "Ask the priest about the consecration date"], mandir, summary="Sized the mandir at 600 sq ft and set a budget ceiling.")
	chat("Low-cost tea estate sports setup", 6, "Tea & Coffee", ["Price a pickleball court", "Find a pavilion design"], summary="Options for a recreation area for staff.")
	chat("Ruchi ITR, Merrill statements", 1, "Money & Legal", ["Download Merrill statements"], summary="What the accountant needs for the ITR.")
	chat("Owner outreach funnel copy", 3, "Business That Works", [], funnel, "ChatGPT", "Drafted the first outreach email.")

	for title, day, month, kind in (("Anniversary", 23, 11, "Anniversary"), ("Ruchi", 14, 1, "Birthday"), ("Jai", 20, 1, "Birthday"), ("Anya", 14, 9, "Birthday")):
		t.track(calendar_data.add_yearly_date(space, title, day, month, kind=kind))

	def event(subject, starts, ends=None, all_day=0):
		return t.insert({"doctype": "Event", "subject": subject, "starts_on": starts, "ends_on": ends, "all_day": all_day,
			"event_type": "Public", "life_space": space})

	event("Golf round", f"{now} 07:00:00", f"{now} 10:00:00")
	event("Call with Vivek on the ITR", f"{now} 16:30:00", f"{now} 17:00:00")
	event("Weekly review", f"{add_days(now, 1)} 18:00:00", f"{add_days(now, 1)} 19:00:00")
	event("Phuket", f"{now.year}-01-07 00:00:00", f"{now.year}-01-11 23:59:59", 1)
	event("Christmas", f"{now.year}-12-25 00:00:00", f"{now.year}-12-25 23:59:59", 1)
	event("Board meeting", f"{now.year}-02-26 00:00:00", f"{now.year}-02-26 23:59:59", 1)

	# ticks on the 12 Week Year grid
	cycle = frappe.get_doc("Life Cycle", {"space": space, "status": "Active"})
	cur = cycles.current_week(cycle)
	for a in cycles._actions(cycle.name):
		pattern = TICKS.get(a.title, "")
		for week, mark in enumerate(pattern, start=1):
			if mark == "x" and week <= cur and not frappe.db.exists("Life Action Log", {"action_id": a.name, "week": week}):
				start, end = cycles.week_dates(cycle, week)
				t.insert({"doctype": "Life Action Log", "space": space, "goal": a.goal, "action_id": a.name, "cycle": cycle.name,
					"week": week, "date": min(end, now) if week == cur else start, "count": 1})
		cycles._update_tick_summary(a.name)

	# a closed earlier cycle, so the Goals tab shows history
	old = t.insert({"doctype": "Life Cycle", "space": space, "title": "Jul to Sep 2026", "start_date": "2026-07-06", "status": "Planned"})
	for title, a, outcome, score in (("Golf: break 90", "Personal", "Achieved", 90), ("Start the ERP rollout", "Tea & Coffee", "Partly Achieved", 55),
			("Read twelve books", "Learning", "Dropped", 20)):
		t.insert({"doctype": "Life Goal", "space": space, "cycle": old.name, "title": title, "area": area[a], "outcome": outcome,
			"final_score": score, "actions": [{"title": "Weekly session"}, {"title": "Monthly review"}]})
	old.status, old.final_score, old.closed_on = "Closed", 58, "2026-09-28"
	old.save()

	# habits this month
	for title, a in (("Ghillidary drainage plan agreed", "Tea & Coffee"), ("File the ITR", "Money & Legal")):  # this month's goals, in priority order
		cycles.add_month_goal(space, now.year, now.month, title, area[a])
	for row in habit_rules.habits_month(space, now.year, now.month)["habits"]:
		title = row["title"]
		for day in range(1, now.day + 1):
			if day in HABIT_MISSES.get(title, set()) or (day == now.day and title in ("Journal", "Workout")):
				continue
			d = now.replace(day=day)
			if not frappe.db.exists("Life Habit Log", {"habit": row["habit"], "date": d}):
				t.insert({"doctype": "Life Habit Log", "space": space, "habit": row["habit"], "date": d, "done": 1})

	# inbox items, processed by the fake agent as the agent user
	from lifeos.api import inbox

	fake = devtools.load_fake_agent()
	made = []
	for title, source, instruction, file_name, content in (
		("Journal photo, pages 187 to 188", "Journal Photo", "transcribe and update my journal", "journal-187-188.png", devtools.journal_png()),
		("Voice note, 2 min 10 s", "Voice Note", "", None, None),
		("Mithun production documents.pdf", "Upload", "summarise and extract to-dos", "Mithun production documents.pdf", devtools.pdf_bytes()),
	):
		item = inbox.create_item(title=title, source_type=source, space=space, instruction=instruction)
		t.records.append(["Life Inbox Item", item["name"]])
		if file_name:
			devtools.attach("Life Inbox Item", item["name"], file_name, content)
		made.append(item["name"])
	frappe.set_user(agent)  # nosemgrep: frappe-setuser -- demo data: records are made through the API as the owner and the agent would make them
	permissions.clear_cache()
	for _ in made:
		fake.process_one(devtools.LocalClient(), log=lambda *a: None)
	frappe.set_user("Administrator")  # nosemgrep: frappe-setuser -- demo data: records are made through the API as the owner and the agent would make them
	t.save()
	load_set7(space)
	return f"Demo data loaded into {space}: {len(t.records)} records."


def load_set7(space="Private"):
	"""Set 7: a number goal with confirmed readings and one suggested by an agent, served by the open-ended Ghillidary goal."""
	t = seed.Tracker(seed.DEMO_KEY)
	if frappe.db.exists("Life Goal", {"space": space, "title": "Ghillidary yield to 1,800 kg/ha"}):
		return "Already loaded."
	area = frappe.db.get_value("Life Area", {"space": space, "area_name": "Tea & Coffee"})
	g = t.insert({"doctype": "Life Goal", "space": space, "title": "Ghillidary yield to 1,800 kg/ha", "horizon": "Year", "area": area,
		"target_date": f"{getdate(today()).year + 1}-12-31", "measure_kind": "Number", "measure": "Ghillidary yield", "unit": "kg/ha",
		"start_value": 1200, "target_value": 1800, "notes_md": "Made tea per hectare, a rolling twelve months."})
	for weeks, value in ((9, 1250), (5, 1320), (2, 1410)):
		t.insert({"doctype": "Life Goal Reading", "space": space, "goal": g.name, "date": add_days(today(), -7 * weeks), "value": value,
			"status": "Confirmed", "suggested_by": "Owner"})
	t.insert({"doctype": "Life Goal Reading", "space": space, "goal": g.name, "date": add_days(today(), -1), "value": 1460, "status": "Suggested",
		"suggested_by": "Agent", "excerpt": "Ghillidary yield for the last twelve months is now 1,460 kg/ha."})
	turnaround = frappe.db.get_value("Life Goal", {"space": space, "title": "Ghillidary turnaround"})
	if turnaround:
		frappe.db.set_value("Life Goal", turnaround, "serves", g.name)
	t.save()
	return "Set 7 demo data loaded."


def remove():
	items = [n for dt, n in frappe.parse_json(frappe.db.get_default(seed.DEMO_KEY) or "[]") if dt == "Life Inbox Item"]
	for item in items:
		for dt in ("Life Task", "Life Note", "Life Vault Document"):
			for name in frappe.get_all(dt, filters={"inbox_item": item}, pluck="name"):
				frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
	n = seed._remove(seed.DEMO_KEY)
	return f"Demo data removed: {n} records."


# ---------- UX fixes, set 4: sources and the wiki ----------
DEMO4_KEY = "lifeos_demo_v4_records"
DIGEST = """## Needs your attention
- Mithun Sarkar: the December despatch dates need your yes [Open](https://mail.google.com/mail/u/0/#inbox/demo-mithun)
- Vivek: two papers missing for the ITR [Open](https://mail.google.com/mail/u/0/#inbox/demo-vivek)

## Waiting on others
- The auditors: scope letter promised for Friday [Open](https://mail.google.com/mail/u/0/#inbox/demo-audit)

## Dates and deadlines
- 20 Nov: board meeting, Kolkata
- 30 Nov: advance tax instalment

## FYI from people
- Anya: photos from the school trip

## Company information
- Q3 tea prices at the Kolkata auction are out

## Left out
- 23 newsletters and 6 notifications
"""


def load_v4(space="Private"):
	"""Example sources and wiki pages for the Sources and Wiki screens. Remove with lifeos.tools.demo.remove_v4."""
	from lifeos.api import inbox, wiki

	if frappe.parse_json(frappe.db.get_default(DEMO4_KEY) or "[]"):
		return "The set 4 demo is already loaded. Run lifeos.tools.demo.remove_v4 first."
	owner, agent = _user(devtools.OWNER), _user(devtools.AGENT)
	frappe.set_user(owner)  # nosemgrep: frappe-setuser -- demo data: records are made through the API as the owner and the agent would make them
	permissions.clear_cache()
	t = seed.Tracker(DEMO4_KEY)
	area = {a.area_name: a.name for a in frappe.get_all("Life Area", filters={"space": space}, fields=["name", "area_name"])}
	made = []
	for title, stype, text, intent, extra in (
		("Email digest, 16 Nov", "Email Digest", DIGEST, "Process", {"source_system": "gmail", "external_id": "demo-digest-2026-11-16"}),
		("Fair trade premium, explained", "Web", "What the fair trade premium is and how estates use it.", "Add to wiki", {"source_url": "https://example.com/fair-trade-premium"}),
		("Mithun on the Ghatia factory", "Message", "Mithun Sarkar runs production at the Ghatia factory. He wants a second dryer before March.", "Add to wiki", {}),
		("Receipt, nursery stock", "Message", "Receipt for 2,000 clone plants from the nursery.", "Just keep", {}),
	):
		item = inbox.create_item(title=title, source_type=stype, space=space, raw_text=text, intent=intent, **extra)
		t.records.append(["Life Inbox Item", item["name"]])
		made.append(item["name"])
	frappe.set_user(agent)  # nosemgrep: frappe-setuser -- demo data: records are made through the API as the owner and the agent would make them
	permissions.clear_cache()
	fake = devtools.load_fake_agent()
	for _ in made:
		fake.process_one(devtools.LocalClient(), log=lambda *a: None)
	src = {"doctype": "Life Inbox Item", "name": made[2]}
	for title, summary, body, a in (
		("Mithun Sarkar", "Production manager at the Ghatia factory.", "# Mithun Sarkar\n\nRuns production at the [[Ghatia factory]]. Wants a second dryer before March.\n\nSee [[Dalmia Gold blend blueprint]].", "Tea & Coffee"),
		("Ghatia factory", "The tea factory at the Ghatia estate.", "# Ghatia factory\n\nManaged by [[Mithun Sarkar]].\n\n## Machines\n\n- One dryer\n- Two rollers\n", "Tea & Coffee"),
		("Fair trade premium", "A sum paid on top of the price for community projects.", "# Fair trade premium\n\nPaid per kilo on top of the price. Spent by a joint body on community projects.", "Business That Works"),
	):
		try:
			p = wiki.create_page(space=space, title=title, summary=summary, content_md=body, area=area.get(a), sources=[src], change_note="From a demo source.", source=src)
			t.records.append(["Life Note", p["name"]])
		except frappe.DuplicateEntryError:
			pass
	frappe.set_user("Administrator")  # nosemgrep: frappe-setuser -- demo data: records are made through the API as the owner and the agent would make them
	for name in frappe.get_all("Life Note", filters={"space": space, "collection": "Wiki"}, pluck="name"):
		if ["Life Note", name] not in t.records:
			t.records.append(["Life Note", name])
	t.save()
	return f"Set 4 demo loaded into {space}: {len(t.records)} records."


def remove_v4():
	items = [n for dt, n in frappe.parse_json(frappe.db.get_default(DEMO4_KEY) or "[]") if dt == "Life Inbox Item"]
	for item in items:
		for dt in ("Life Task", "Life Note"):
			for name in frappe.get_all(dt, filters={"inbox_item": item}, pluck="name"):
				frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
	notes = [n for dt, n in frappe.parse_json(frappe.db.get_default(DEMO4_KEY) or "[]") if dt == "Life Note"]
	frappe.db.delete("Life Wiki Change", {"note": ("in", notes or [""])})
	n = seed._remove(DEMO4_KEY)
	return f"Set 4 demo removed: {n} records."
