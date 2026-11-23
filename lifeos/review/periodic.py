"""The monthly and the 12-week review (issue 47): guided reviews in the weekly review's shell, over one `Life Review` each.

Monthly:  Look back, Decide (each unfinished month goal: Finish, Carry or Drop), Plan (next month's goals and habits), Reflect.
12 weeks: Score, Goals (each cycle goal: Done, Carry or Drop), Plan the next cycle, Reflect.

Nothing is written to the plan or the cycle until Lock; the decisions, the plan and the words are kept in the review's state as
they are made, so a review can be left and picked up again. The monthly review is due from the first review day (Rhythms) after
a month ends, until done; the 12-week review from the last day of a cycle, until done, and it replaces that week's weekly review.
"""
import json
import uuid

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from lifeos.goals import cycles, readings
from lifeos.goals import habits as habit_rules
from lifeos.review.record import MONTHS, Review, span_text

MONTHLY, CYCLE, WEEKLY = "Monthly", "12 Weeks", "Weekly"
SLUGS = {"monthly": MONTHLY, "12-weeks": CYCLE}
TABS = {MONTHLY: ("look", "decide", "plan", "reflect"), CYCLE: ("score", "goals", "plan", "reflect")}
LABELS = {"look": "Look back", "decide": "Decide", "plan": "Plan", "reflect": "Reflect", "score": "Score", "goals": "Each goal"}
MINUTES = {MONTHLY: {"look": 4, "decide": 6, "plan": 7, "reflect": 3}, CYCLE: {"score": 8, "goals": 12, "plan": 18, "reflect": 7}}
TITLES = {MONTHLY: "Monthly review", CYCLE: "12-week review"}
PILES = {MONTHLY: ("finish", "carry", "drop"), CYCLE: ("done", "carry", "drop")}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def kind_of(slug):
	if slug not in SLUGS:
		frappe.throw(_("Unknown review."), title=_("Unknown review"))
	return SLUGS[slug]


def slug_of(kind):
	return {v: k for k, v in SLUGS.items()}.get(kind, "weekly")


# ---- what is due ----

def review_day():
	return frappe.get_cached_doc("Life Settings").weekly_review_day or "Sunday"


def first_review_day_after(day):
	"""The first date after `day` that falls on the review day of Rhythms."""
	d = add_days(getdate(day), 1)
	index = DAYS.index(review_day())
	while d.weekday() != index:
		d = add_days(d, 1)
	return d


def month_due(space, user, day=None):
	"""{year, month, from} of the month to review, or None: the last month that ended, from the first review day after its
	end until it is locked. A month with no goals has nothing to look back on."""
	day = getdate(day or today())
	last = add_days(day.replace(day=1), -1)
	due_from = first_review_day_after(last)
	if day < due_from:
		return None
	first, end = cycles.month_bounds(last.year, last.month)
	if frappe.db.exists("Life Review", {"space": space, "user": user, "kind": MONTHLY, "status": "Locked", "period_end": end}):
		return None
	if not frappe.db.exists("Life Goal", {"space": space, "horizon": "Month", "target_date": ("between", [first, end])}):
		return None
	return {"year": last.year, "month": last.month, "from": str(due_from)}


def cycle_due(space, day=None):
	"""The active cycle that has ended (from its last day), until its review is locked, which closes it."""
	day = getdate(day or today())
	return frappe.db.get_value("Life Cycle", {"space": space, "status": "Active", "end_date": ("<=", day)}, ["name", "title", "start_date", "end_date"],
		as_dict=True, order_by="end_date asc")


def weekly_due(space, user, day=None):
	"""The weekly review is due from the review day of the week until it is locked, unless the 12-week review replaces it."""
	day = getdate(day or today())
	if cycle_due(space, day):
		return False
	if Review.find_open(space, user):
		return True
	week_start = add_days(day, -day.weekday())
	if day.weekday() < DAYS.index(review_day()):
		return False
	return not frappe.db.exists("Life Review", {"space": space, "user": user, "kind": WEEKLY, "status": "Locked", "period_end": (">=", week_start)})


def due(space, user, day=None):
	"""The reviews due, in the order to do them: the 12-week review or else the weekly one, then the monthly."""
	out = []
	cyc = cycle_due(space, day)
	if cyc:
		out.append({"kind": "12-weeks", "title": TITLES[CYCLE], "text": "The 12-week review is due: start it", "detail": cyc.title})
	elif weekly_due(space, user, day):
		out.append({"kind": "weekly", "title": "Weekly review", "text": "The weekly review is due: start it", "detail": None})
	m = month_due(space, user, day)
	if m:
		out.append({"kind": "monthly", "title": TITLES[MONTHLY], "text": f"The {MONTHS[m['month'] - 1]} review is due: start it", "detail": f"{MONTHS[m['month'] - 1]} {m['year']}"})
	return out


# ---- the review ----

class Periodic(Review):
	"""A monthly or 12-week review: the weekly review's record with tabs, done states and period of its own."""

	@property
	def kind(self):
		return self.doc.kind

	@property
	def tabs(self):
		return TABS[self.doc.kind]

	@classmethod
	def target(cls, space, user, kind, day=None):
		"""What a review that starts now would cover: the month ({year, month}) or the cycle ({cycle}), or None when it is not due."""
		if kind == MONTHLY:
			return month_due(space, user, day)
		cyc = cycle_due(space, day)
		return {"cycle": cyc.name} if cyc else None

	@classmethod
	def virtual(cls, space, user, day=None, kind=MONTHLY):
		target = cls.target(space, user, kind, day)
		if not target:
			return None
		if kind == MONTHLY:
			start, end = cycles.month_bounds(target["year"], target["month"])
			title = f"Monthly review, {MONTHS[target['month'] - 1]} {target['year']}"
		else:
			cyc = frappe.get_doc("Life Cycle", target["cycle"])
			start, end = getdate(cyc.start_date), getdate(cyc.end_date)
			title = f"12-week review, {cyc.title}"
		doc = frappe.new_doc("Life Review")
		doc.update({"space": space, "user": user, "kind": kind, "status": "Open", "period_start": start, "period_end": end, "title": title,
			"tab_state": "{}"})
		rv = cls(doc)
		rv.state["target"] = target
		doc.tab_state = json.dumps(rv.state, default=str)
		return rv

	@classmethod
	def current(cls, space, user, kind, day=None):
		"""The Open review, or one locked in the last days (shown as done), or the unsaved one that would start now, or None."""
		got = cls.find_open(space, user, kind)
		if got:
			return got
		last = cls.latest_locked(space, user, kind)
		if last and last.doc.locked_on and (getdate(day or today()) - getdate(last.doc.locked_on)).days < 3:
			return last
		return cls.virtual(space, user, day, kind)

	@classmethod
	def begin(cls, space, user, kind, day=None):
		got = cls.find_open(space, user, kind)
		if got:
			return got
		got = cls.current(space, user, kind, day)
		if got is None:
			frappe.throw(_("This review is not due."), title=_("Review is not due"))
		if got.saved:
			return got  # locked
		got.state["started_on"] = str(now_datetime())[:19]
		got.doc.tab_state = json.dumps(got.state, default=str)
		got.doc.insert()
		return got

	# ---- who and what ----

	def month(self):
		t = self.state.get("target") or {}
		return t.get("year"), t.get("month")

	def cycle(self):
		name = (self.state.get("target") or {}).get("cycle")
		return frappe.get_doc("Life Cycle", name) if name else None

	def goals(self):
		"""The goals the Decide / Each goal tab is about: open month goals, or the cycle's goals still in progress."""
		if self.kind == MONTHLY:
			y, m = self.month()
			return [{"name": g["row"], "title": g["title"], "area": g["area"], "tasks_done": g["tasks_done"], "tasks_counted": g["tasks_counted"]}
				for g in cycles.month_goals(self.doc.space, y, m) if g["status"] == "Open"]
		cyc = self.cycle()
		rows = frappe.get_all("Life Goal", filters={"cycle": cyc.name, "outcome": "In Progress"}, order_by="sort_order asc, creation asc",
			fields=["name", "title", "area", "serves", "done_when", "target_value", "measure_kind", "unit"]) if cyc else []
		return rows

	# ---- decisions: saved as they are made ----

	def decisions(self):
		return self.state.setdefault("decisions", {})

	def decide(self, goal, pile, date=None, reason=None, target=None):
		if goal not in {g["name"] if isinstance(g, dict) else g.name for g in self.goals()}:
			frappe.throw(_("That goal is not up for decision in this review."), title=_("Goal not up for decision"))
		if pile not in PILES[self.kind]:
			frappe.throw(_("Unknown pile."), title=_("Unknown pile"))
		d = {"pile": pile}
		if pile == "finish":
			d["date"] = str(getdate(date)) if date else None
		if pile == "drop":
			d["reason"] = (reason or "").strip()[:500]
		if pile == "carry" and target not in (None, ""):
			d["target"] = flt(target)
		self.decisions()[goal] = d
		return d

	def undecide(self, goal):
		self.decisions().pop(goal, None)

	def decision_problems(self):
		"""What is still missing in the decisions, as one line per goal."""
		out = []
		for g in self.goals():
			g = g if isinstance(g, dict) else g.as_dict()
			d = self.decisions().get(g["name"])
			if not d:
				out.append(f"{g['title']}: decide what happens to it")
			elif d["pile"] == "finish" and not d.get("date"):
				out.append(f"{g['title']}: give the date it will be finished")
			elif d["pile"] == "drop" and not d.get("reason"):
				out.append(f"{g['title']}: say why you are dropping it")
		return out

	def decision_rows(self):
		decided = self.decisions()
		rows = []
		for g in self.goals():
			g = dict(g)
			g["area_name"] = frappe.db.get_value("Life Area", g["area"], "area_name") if g.get("area") else None
			g["decision"] = decided.get(g["name"])
			if self.kind == CYCLE:
				g["result"] = self._result(g["name"])
			rows.append(g)
		piles = {p: sum(1 for r in rows if (r["decision"] or {}).get("pile") == p) for p in PILES[self.kind]}
		undecided = sum(1 for r in rows if not r["decision"])
		return {"goals": rows, "piles": piles, "undecided": undecided, "problems": self.decision_problems()}

	# ---- tab 1 ----

	def look(self):
		return self.look_month() if self.kind == MONTHLY else self.score()

	def look_month(self):
		"""The month's goals (done, in progress, missed), its habits against their target, and the weekly scores of its weeks."""
		space = self.doc.space
		y, m = self.month()
		first, last = cycles.month_bounds(y, m)
		goals = []
		for g in cycles.month_goals(space, y, m):
			status = {"Done": "done", "Open": "progress" if g["tasks_done"] else "missed"}.get(g["status"], "missed")
			goals.append({**g, "area_name": frappe.db.get_value("Life Area", g["area"], "area_name") if g["area"] else None, "result": status})
		habits = habit_rules.habits_month(space, y, m)["habits"]
		weeks = []
		for cyc in frappe.get_all("Life Cycle", filters={"space": space, "start_date": ("<=", last), "end_date": (">=", first)}, pluck="name"):
			doc = frappe.get_doc("Life Cycle", cyc)
			actions, ticks = cycles._actions(doc.name), cycles._ticks(doc.name)
			for w in range(1, cycles.WEEKS + 1):
				ws, we = cycles.week_dates(doc, w)
				if first <= getdate(we) <= last:  # a week belongs to the month it ends in
					weeks.append({"week": w, "cycle": doc.title, "from": str(ws), "to": str(we), "label": span_text(ws, we),
						"percent": cycles.week_score(doc, w, actions, ticks)["percent"]})
		avg = round(sum(w["percent"] for w in weeks) / len(weeks), 1) if weeks else None
		return {"title": f"{MONTHS[m - 1]} {y}", "goals": goals, "habits": [{k: h[k] for k in ("habit", "title", "done", "target", "percent", "days_per_week")} for h in habits],
			"weeks": weeks, "average": avg, "target": cint(frappe.db.get_single_value("Life Settings", "score_target")) or 85}

	def score(self):
		"""The cycle's twelve weekly scores, the average against the target and each goal's result, as the cycle view gives them."""
		grid = cycles.grid(self.cycle().name)
		goals = [{"name": g["name"], "title": g["title"], "percent": g["percent"], "result": g["result"], "outcome": g["outcome"]} for g in grid["goals"]]
		return {"title": grid["cycle"]["title"], "weeks": [{"week": w["week"], "percent": w["percent"]} for w in grid["weeks"]],
			"average": grid["average"], "target": grid["target"], "goals": goals}

	def _result(self, goal):
		cyc = self.cycle()
		actions, ticks = cycles._actions(cyc.name), cycles._ticks(cyc.name)
		from lifeos.goals import readings

		g = frappe.db.get_value("Life Goal", goal, ["name", "measure_kind", "measure", "unit", "start_value", "target_value", "current_value", "current_on"], as_dict=True)
		pct = cycles.goal_percent(cyc, [a for a in actions if a.goal == goal], ticks, cycles.WEEKS)
		return {"percent": pct, **readings.summary({**g, "horizon": "12 weeks", "score": pct})}

	# ---- tab 3: the plan ----

	def plan_state(self):
		return self.state.setdefault("plan", {"extra": [], "habits": None, "edits": {}, "confirmed": False, "maintain": []})

	def carried(self):
		"""The goals carried on, in their current order."""
		return [g for g in self.goals() if (self.decisions().get(g["name"] or "") or {}).get("pile") == "carry"]

	def plan(self):
		return self.plan_month() if self.kind == MONTHLY else self.plan_cycle()

	def plan_month(self):
		y, m = self.month()
		ny, nm = cycles.next_month(y, m)
		st = self.plan_state()
		goals = [{"id": g["name"], "title": g["title"], "area": g.get("area"), "serves": frappe.db.get_value("Life Goal", g["name"], "serves"),
			"carried_from": g["name"]} for g in self.carried()]
		goals += [{"id": x["id"], "title": x["title"], "area": x.get("area"), "serves": x.get("serves"), "carried_from": None,
			"done_when": x.get("done_when") or ""} for x in st["extra"]]
		habits = st["habits"]
		if habits is None:  # next month starts from this month's habits, the ones still tracked at its end
			habits = [{"habit": h["habit"], "days_per_week": h["days_per_week"]} for h in habit_rules.habits_month(self.doc.space, y, m)["habits"] if not h["removed"]]
		titles = dict(frappe.get_all("Life Habit", filters={"name": ("in", [h["habit"] for h in habits] or [""])}, fields=["name", "title"], as_list=True))
		for g in goals:
			g["area_name"] = frappe.db.get_value("Life Area", g["area"], "area_name") if g.get("area") else None
			g["serves_title"] = frappe.db.get_value("Life Goal", g["serves"], "title") if g.get("serves") else None
		return {"title": f"{MONTHS[nm - 1]} {ny}", "goals": goals, "habits": [{**h, "title": titles.get(h["habit"], h["habit"])} for h in habits],
			"confirmed": bool(st.get("confirmed")), "serves_options": self.serves_options(), "problems": self.plan_problems(goals),
			"habit_options": [{"value": h.name, "label": h.title} for h in frappe.get_all("Life Habit", filters={"space": self.doc.space, "is_archived": 0},
				fields=["name", "title"], order_by="title asc")]}

	def serves_options(self):
		"""The longer goals a goal of the next period can serve: cycle and year goals for a month goal, year and long-term goals for a
		cycle goal."""
		horizons = ["12 weeks", "Year"] if self.kind == MONTHLY else ["Year", "Long term"]
		rows = frappe.get_all("Life Goal", filters={"space": self.doc.space, "is_archived": 0, "outcome": "In Progress", "horizon": ("in", horizons)},
			fields=["name", "title"], order_by="horizon desc, sort_order asc", limit=60)
		return [{"value": r.name, "label": r.title} for r in rows]

	def plan_problems(self, goals):
		out = []
		if not goals:
			out.append("Add at least one goal for next month")
		for g in goals:
			if not (g["title"] or "").strip():
				out.append("Every goal needs a title")
			elif not g.get("area"):
				out.append(f"{g['title']}: choose an area")
			elif not g["carried_from"] and readings.done_when_required() and not (g.get("done_when") or "").strip():
				out.append(f"{g['title']}: say when it is done")
		return out

	def plan_cycle(self):
		cyc = self.cycle()
		start = cycles.next_monday(cyc.end_date)
		end = add_days(start, 83)
		st = self.plan_state()
		goals = []
		for g in self.carried():
			old = frappe.get_doc("Life Goal", g["name"])
			e = st["edits"].get(old.name) or {}
			actions = e.get("actions")
			if actions is None:
				actions = [{"title": a.title, "per_week": a.per_week} for a in old.actions if a.status == "Open"]
			target = (self.decisions().get(old.name) or {}).get("target")
			goals.append({"id": old.name, "carried_from": old.name, "title": old.title, "area": old.area, "serves": old.serves,
				"done_when": e["done_when"] if "done_when" in e else (old.done_when or ""), "actions": actions,
				"target": e.get("target", target if target is not None else old.target_value), "measure_kind": old.measure_kind, "unit": old.unit})
		for x in st["extra"]:
			goals.append({"id": x["id"], "carried_from": None, "title": x["title"], "area": x.get("area"), "serves": x.get("serves"),
				"done_when": x.get("done_when") or "", "actions": x.get("actions") or [], "target": None, "measure_kind": None, "unit": None})
		for g in goals:
			g["area_name"] = frappe.db.get_value("Life Area", g["area"], "area_name") if g.get("area") else None
		settings = frappe.get_cached_doc("Life Settings")
		days = {"start": str(start), "end": str(end), "title": cycles.cycle_title(start),
			"break_week": [str(add_days(getdate(cyc.end_date), 1)), str(add_days(start, -1))] if settings.cycle_break_week and add_days(start, -1) > add_days(getdate(cyc.end_date), 1) else None}
		from lifeos.api import focus  # issue 57: each active focus with no goal in the next cycle gets one question

		maintain = set(st.get("maintain") or [])
		asked = [f for f in focus.focuses_without_goal(self.doc.space, {g["area"] for g in goals}) if f.name not in maintain]
		return {"dates": days, "goals": goals, "confirmed": bool(st.get("confirmed")), "problems": self.cycle_plan_problems(goals),
			"serves_options": self.serves_options(), "focuses": asked, "maintained": sorted(maintain)}

	def cycle_plan_problems(self, goals):
		out = []
		if not goals:
			out.append("Add at least one goal for the next cycle")
		for g in goals:
			if not (g["title"] or "").strip():
				out.append("Every goal needs a title")
			elif not (g["done_when"] or "").strip() and g.get("measure_kind") != "Number":
				out.append(f"{g['title']}: say when it is done")
			elif not [a for a in g["actions"] if (a.get("title") or "").strip()]:
				out.append(f"{g['title']}: add a lead action")
		return out

	def plan_save(self, extra=None, habits=None, edits=None, confirm=False, maintain=None):
		st = self.plan_state()
		if maintain is not None:
			st["maintain"] = [m for m in maintain if isinstance(m, str)][:200]
		if extra is not None:
			clean = []
			for x in extra:
				if not isinstance(x, dict):
					continue
				row = {"id": x.get("id") or uuid.uuid4().hex[:10], "title": (x.get("title") or "").strip()[:140], "area": x.get("area") or None,
					"serves": x.get("serves") or None}
				row["done_when"] = (x.get("done_when") or "").strip()[:500]
				if self.kind == CYCLE:
					row["actions"] = _clean_actions(x.get("actions"))
				clean.append(row)
			st["extra"] = clean
		if habits is not None:
			seen, out = set(), []
			for h in habits:
				if h.get("habit") and h["habit"] not in seen and frappe.db.exists("Life Habit", h["habit"]):
					seen.add(h["habit"])
					out.append({"habit": h["habit"], "days_per_week": min(7, max(1, cint(h.get("days_per_week")) or 7))})
			st["habits"] = out
		if edits is not None:
			names = {g["name"] for g in self.carried()}
			for name, e in (edits or {}).items():
				if name not in names or not isinstance(e, dict):
					continue
				cur = st["edits"].setdefault(name, {})
				if "done_when" in e:
					cur["done_when"] = (e["done_when"] or "").strip()[:500]
				if "actions" in e:
					cur["actions"] = _clean_actions(e["actions"])
				if "target" in e:
					cur["target"] = None if e["target"] in (None, "") else flt(e["target"])
		if confirm:
			st["confirmed"] = True
		elif extra is not None or habits is not None or edits is not None or maintain is not None:
			st["confirmed"] = False

	# ---- tab states ----

	def done(self):
		first, second, third, fourth = self.tabs
		plan = self.plan()
		return {first: bool((self.state.get("visited") or {}).get(first)), second: not self.decision_problems(),
			third: bool(plan["confirmed"]) and not plan["problems"], fourth: self.doc.status == "Locked"}

	def openable(self, done=None):
		done = done or self.done()
		out, ok = {}, True
		for i, tab in enumerate(self.tabs):
			out[tab] = ok
			ok = ok and (done[tab] or i == 0)
		return out

	def first_unfinished(self, done=None):
		done = done or self.done()
		return next((t for t in self.tabs if not done[t]), "reflect")

	def visit(self, tab):
		if tab in self.tabs:
			self.state.setdefault("visited", {})[tab] = 1

	def reflection(self):
		return {"went_well": self.doc.went_well or "", "not_well": self.state.get("not_well") or "", "change": self.doc.do_differently or ""}

	def save_words(self, went_well=None, not_well=None, change=None):
		if went_well is not None:
			self.doc.went_well = (went_well or "").strip()[:4000]
		if not_well is not None:
			self.state["not_well"] = (not_well or "").strip()[:4000]
		if change is not None:
			self.doc.do_differently = (change or "").strip()[:4000]

	def header(self):
		done = self.done()
		slug = slug_of(self.kind)
		tabs = [{"value": t, "label": LABELS[t], "n": i + 1} for i, t in enumerate(self.tabs)]
		return {"name": self.doc.name if self.saved else None, "status": self.doc.status, "kind": self.kind, "slug": slug, "title": TITLES[self.kind],
			"period_text": self.period_label(), "period_start": str(self.doc.period_start), "period_end": str(self.doc.period_end), "tabs": tabs,
			"minutes": sum(MINUTES[self.kind].values()), "tab_minutes": MINUTES[self.kind], "done": done, "openable": self.openable(done),
			"first": self.first_unfinished(done), "locked_on": self.doc.locked_on,
			"minutes_spent": self.doc.minutes_spent if self.doc.status == "Locked" else None}

	def period_label(self):
		if self.kind == MONTHLY:
			y, m = self.month()
			return f"{MONTHS[m - 1]} {y}"
		return f"{self.doc.title.split(', ', 1)[-1]}: {span_text(self.doc.period_start, self.doc.period_end)}"


def _clean_actions(actions):
	out = []
	for a in actions or []:
		title = (a.get("title") or "").strip()[:140]
		if title:
			out.append({"title": title, "per_week": min(7, max(1, cint(a.get("per_week")) or 1))})
	return out


# ---- Lock ----

def lock(rv):
	if rv.doc.status == "Locked":
		frappe.throw(_("This review is already locked."), title=_("Review already locked"))
	if not (rv.doc.went_well or "").strip():
		frappe.throw(_("Write what went well first."), title=_("What went well missing"))
	done = rv.done()
	if not all(done[t] for t in rv.tabs[:3] if t != rv.tabs[0]):
		frappe.throw(_("Finish Decide and Plan first.") if rv.kind == MONTHLY else _("Finish Each goal and Plan the next cycle first."), title=_("Review steps unfinished"))
	made = lock_month(rv) if rv.kind == MONTHLY else lock_cycle(rv)
	rv.doc.update({"status": "Locked", "locked_on": now_datetime(), **made["numbers"]})
	rv.state["locked"] = made["summary"]
	rv.doc.minutes_spent = rv.minutes()
	rv.doc.flags.locking = True
	rv.save()
	return summary(rv)


def lock_month(rv):
	"""Write next month's goals: the carried goals first, then the new ones, in order, and its habits; mark the carried goals
	Carried (their open tasks move) and the dropped ones Dropped with the reason; Finish dates move the goal's date."""
	space = rv.doc.space
	y, m = rv.month()
	ny, nm = cycles.next_month(y, m)
	decided = rv.decisions()
	plan = rv.plan_month()  # worked out before anything is written
	for name, d in decided.items():
		if d["pile"] == "drop":
			goal = frappe.get_doc("Life Goal", name)
			goal.update({"outcome": "Dropped", "result_note": d.get("reason")})
			goal.save()
		elif d["pile"] == "finish" and d.get("date"):
			frappe.db.set_value("Life Goal", name, "target_date", getdate(d["date"]))
	made = []
	for g in plan["goals"]:
		if g["carried_from"]:
			old = frappe.get_doc("Life Goal", g["carried_from"])
			new = cycles.add_month_goal(space, ny, nm, old.title, g.get("area") or old.area, carried_from=old.name, serves=g.get("serves") or old.serves)
			old.outcome = "Carried"
			old.save()
			cycles.move_open_tasks(old.name, new.name)
		else:
			new = cycles.add_month_goal(space, ny, nm, g["title"], g["area"], serves=g.get("serves"), done_when=g.get("done_when"))
		made.append({"goal": new.name, "title": new.title, "carried": bool(g["carried_from"])})
	if plan["habits"]:
		habit_rules.set_month_habits(space, ny, nm, [{"habit": h["habit"], "days_per_week": h["days_per_week"]} for h in plan["habits"]])
	look = rv.look_month()
	piles = {p: sum(1 for d in decided.values() if d["pile"] == p) for p in PILES[MONTHLY]}
	return {"numbers": {"score": look["average"] or 0, "score_target": look["target"], "goals_planned": len(made), "goals_skipped": piles["drop"]},
		"summary": {"made": made, "piles": piles, "next": f"{MONTHS[nm - 1]} {ny}", "habits": len(plan["habits"])}}


def lock_cycle(rv):
	"""Close the cycle with its final score (`cycles.close_cycle`), create the next one with its goals and actions."""
	cyc = rv.cycle()
	decided = rv.decisions()
	outcome = {"done": "Achieved", "carry": "Carried", "drop": "Dropped"}
	outcomes = [{"goal": g["name"], "outcome": outcome[decided[g["name"]]["pile"]], "result_note": decided[g["name"]].get("reason")} for g in rv.goals()]
	plan = rv.plan_cycle()
	frappe.flags.lifeos_allow_early_close = True  # the review is due from the cycle's last day
	try:
		closed = cycles.close_cycle(cyc.name, outcomes)
	finally:
		frappe.flags.lifeos_allow_early_close = False
	carried = [g["carried_from"] for g in plan["goals"] if g["carried_from"]]
	nxt = cycles.plan_next_cycle(cyc.name, carried, plan["dates"]["title"])
	copies = dict(frappe.get_all("Life Goal", filters={"cycle": nxt["cycle"], "carried_from": ("in", carried or [""])}, fields=["carried_from", "name"], as_list=True))
	for i, g in enumerate(plan["goals"]):
		actions = [{"title": a["title"], "per_week": a["per_week"], "status": "Open"} for a in g["actions"]]
		if g["carried_from"]:
			goal = frappe.get_doc("Life Goal", copies[g["carried_from"]])
			goal.done_when = g["done_when"]
			if g.get("target") is not None and goal.measure_kind == "Number":
				goal.target_value = g["target"]
			goal.set("actions", actions)
			goal.sort_order = i + 1
			goal.save()
		else:
			new_goal = frappe.get_doc({"doctype": "Life Goal", "space": rv.doc.space, "cycle": nxt["cycle"], "horizon": "12 weeks", "title": g["title"], "area": g["area"],
				"serves": g.get("serves") or None, "done_when": g["done_when"], "sort_order": i + 1, "actions": actions})
			new_goal.flags.carried = bool(g["carried_from"])  # a goal carried on keeps what it had, even with no Done when
			new_goal.insert()
	piles = {p: sum(1 for d in decided.values() if d["pile"] == p) for p in PILES[CYCLE]}
	return {"numbers": {"score": closed["final_score"], "score_target": cint(frappe.db.get_single_value("Life Settings", "score_target")) or 85,
		"goals_planned": len(plan["goals"]), "goals_skipped": piles["drop"]},
		"summary": {"cycle": cyc.name, "final_score": closed["final_score"], "next_cycle": nxt["cycle"], "next_title": nxt["title"], "next_start": nxt["start_date"],
			"piles": piles, "made": [{"title": g["title"], "carried": bool(g["carried_from"])} for g in plan["goals"]]}}


def summary(rv):
	s = dict(rv.state.get("locked") or {})
	return {"minutes": rv.doc.minutes_spent or 0, "kind": rv.kind, "slug": slug_of(rv.kind), **s}


# ---- past reviews ----

def past(user, space=None, limit=50):
	"""Locked reviews of every kind, newest first, each with its kind."""
	filters = {"user": user, "status": "Locked"}
	if space:
		filters["space"] = space
	rows = frappe.get_all("Life Review", filters=filters, fields=["name", "kind", "title", "period_start", "period_end", "locked_on", "score", "minutes_spent"],
		order_by="locked_on desc", limit=limit)
	return [{**r, "period_start": str(r.period_start), "period_end": str(r.period_end), "locked_on": str(r.locked_on)[:16] if r.locked_on else None} for r in rows]
