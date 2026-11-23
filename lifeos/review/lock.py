"""Tab 4, Reflect, and Lock the week (set 8).

Lock creates or updates each planned goal's task as set 7 did (time, length, what is needed, Waiting on someone else), marks
the top three (`is_top_three`, `top_three_week`; last week's are cleared), stores the review's words and numbers, and locks it.
"""
import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, today

from lifeos.tasks import weekplan
from lifeos.review import findings, goals, stale

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def numbers(review):
	"""The week in numbers: score against target, in and out, findings acted on and dismissed, items cleared, goals planned
	and skipped."""
	from lifeos.api import outbox as outbox_api

	space, a, b = review.doc.space, str(review.doc.period_start), str(review.doc.period_end)
	gp = goals.GoalPlan(review)
	cyc = gp.cycle()
	score = goals.journal_score(frappe.get_doc("Life Cycle", cyc.name)) if cyc else None
	plans = [gp.plan(g.name) for g in gp.goals()]
	f = findings.counts(space, a, b)
	return {"score": score["percent"] if score else None, "target": cint(frappe.db.get_single_value("Life Settings", "score_target")) or 85,
		"came_in": int(outbox_api.total(space, "in", from_date=a, to_date=b)), "went_out": int(outbox_api.total(space, "all", from_date=a, to_date=b)),
		"findings_acted": f["acted"], "findings_dismissed": f["dismissed"], "items_cleared": stale.decided_count(review),
		"goals_planned": sum(1 for p in plans if not p.get("skip") and (p.get("next_action") or "").strip()),
		"goals_skipped": sum(1 for p in plans if p.get("skip"))}


def previous(review):
	return frappe.db.get_value("Life Review", {"space": review.doc.space, "user": review.doc.user, "kind": review.doc.kind, "status": "Locked",
		"name": ("!=", review.doc.name or "")}, ["name", "do_differently", "period_end"], as_dict=True, order_by="period_end desc")


def next_review(on=None):
	"""The next review day and time from Settings > Rhythms, after today."""
	s = frappe.get_cached_doc("Life Settings")
	day = s.weekly_review_day or "Sunday"
	d = add_days(getdate(on or today()), 1)
	while DAYS[d.weekday()] != day:
		d = add_days(d, 1)
	return {"date": str(d), "time": str(s.weekly_review_time or "18:00:00")[:5]}


def preview(review):
	"""What Lock will do: the top three with their times, tasks scheduled and delegated, the next review."""
	gp = goals.GoalPlan(review)
	stars = gp.stars()
	rows = [(g, gp.plan(g.name)) for g in gp.goals()]
	planned = [(g, p) for g, p in rows if not p.get("skip") and (p.get("next_action") or "").strip()]
	return {"top": [{"goal": g.name, "title": p.get("next_action"), "goal_title": g.title, "slot": p.get("slot")} for g, p in planned if g.name in stars],
		"scheduled": sum(1 for g, p in planned if p.get("slot")), "planned": len(planned),
		"delegated": [{"title": p.get("next_action"), "who": p.get("who")} for g, p in planned if not weekplan.is_me(p.get("who"), review.doc.space)],
		"next": next_review()}


def reflect(review):
	prev = previous(review)
	return {"went_well": review.doc.went_well or "", "do_differently": review.doc.do_differently or "", "numbers": numbers(review),
		"last": {"line": prev.do_differently, "check": (review.state.get("playback") or {}).get("text")} if prev and prev.do_differently else None,
		"preview": preview(review)}


def save_words(review, went_well=None, do_differently=None):
	if went_well is not None:
		review.doc.went_well = (went_well or "").strip()[:4000]
	if do_differently is not None:
		review.doc.do_differently = (do_differently or "").strip()[:4000]


def lock(review):
	"""Lock the week. Needs Tasks and Goals done and a line on what went well."""
	if review.doc.status == "Locked":
		frappe.throw(_("This review is already locked."), title=_("Review already locked"))
	if not (review.doc.went_well or "").strip():
		frappe.throw(_("Write what went well first."), title=_("Went well is empty"))
	done = review.done()
	if not done["tasks"] or not done["goals"]:
		frappe.throw(_("Finish Tasks and Goals first."), title=_("Tasks and Goals unfinished"))
	gp = goals.GoalPlan(review)
	stars = gp.stars()
	made = []
	for g in gp.goals():
		p = gp.plan(g.name)
		if p.get("skip") or not (p.get("next_action") or "").strip():
			continue
		task = p.get("task") if p.get("task") and frappe.db.get_value("Life Task", p["task"], "status") in ("Open", "Doing", "Waiting") else None
		doc = weekplan.add(g.name, p["next_action"], task, p.get("slot") or None, p.get("minutes"), p.get("who") or "Me", p.get("note"))
		made.append({"goal": g.name, "task": doc.name, "title": doc.title, "slot": str(doc.scheduled_at)[:16] if doc.scheduled_at else None,
			"star": g.name in stars, "status": doc.status, "waiting_on": doc.waiting_on})
	week = getdate(review.doc.period_end)
	# last week's top three are cleared in one statement (only the flag; nothing else about the tasks changes)
	frappe.db.sql("update `tabLife Task` set is_top_three = 0 where space = %s and is_top_three = 1", review.doc.space)
	for m in made:
		if m["star"]:
			frappe.db.set_value("Life Task", m["task"], {"is_top_three": 1, "top_three_week": week}, update_modified=False)
	n = numbers(review)
	review.doc.update({"score": n["score"] or 0, "score_target": n["target"], "came_in": n["came_in"], "went_out": n["went_out"],
		"findings_acted": n["findings_acted"], "findings_dismissed": n["findings_dismissed"], "items_cleared": n["items_cleared"],
		"goals_planned": n["goals_planned"], "goals_skipped": n["goals_skipped"], "status": "Locked", "locked_on": now_datetime()})
	review.state["locked"] = {"made": made}
	review.doc.minutes_spent = review.minutes()
	review.doc.flags.locking = True
	review.save()
	return summary(review)


def summary(review):
	"""The done screen: minutes, what was decided, the top three, the next review."""
	made = (review.state.get("locked") or {}).get("made") or []
	return {"minutes": review.doc.minutes_spent or 0, "made": made, "top": [m for m in made if m["star"]],
		"scheduled": sum(1 for m in made if m["slot"]), "delegated": sum(1 for m in made if m["status"] == "Waiting"),
		"skipped": review.doc.goals_skipped or 0, "cleared": review.doc.items_cleared or 0, "next": next_review(review.doc.locked_on)}


# ---- last week's note played back ----

def playback(review):
	"""One sentence from the reflect skill checking last week's "do differently" line against this week. Stored once."""
	from lifeos.review import meetings
	from lifeos.skills import call

	prev = previous(review)
	if not prev or not prev.do_differently or review.state.get("playback") is not None:
		return
	if not frappe.db.get_value("Life Space", review.doc.space, "ask_enabled"):
		return
	by_day = {}
	for e in meetings.in_period(review.doc.space, review.doc.period_start, review.doc.period_end):
		by_day.setdefault(get_datetime(e.starts_on).strftime("%A"), []).append(e.subject)
	got = call.ask("reflect", {"line": prev.do_differently, "events_by_weekday": by_day, "numbers": numbers(review)}, space=review.doc.space)
	if got:
		review.state["playback"] = {"text": (got.get("sentence") or "").strip()[:300] or None, "by": got.label}
