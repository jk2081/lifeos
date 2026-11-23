"""Tab 3, Goals (set 8): one row per goal in the current cycle, with its mark, progress and a next action, when, length and
who for the coming week; exactly three starred; a goal skipped this week needs a reason.

The next action is prefilled in this order: a task made in Library or Tasks for this goal during this review, the goal's
oldest open task, the assistant's suggestion (within the cap), or empty. Slots are set 7's: inside working hours, never over an
event (Google's included) or another scheduled task, and the plans of one review never overlap each other.
"""
import frappe
from frappe import _
from frappe.utils import cint

from lifeos import readings, weekplan
from lifeos.review import goal_week

STARS = 3
OPEN = ("Open", "Doing")


class GoalPlan:
	def __init__(self, review):
		self.review = review
		self.space = review.doc.space
		self.st = review.state.setdefault("goals", {})
		self.st.setdefault("plans", {})
		self.st.setdefault("extra", [])
		self._goals = None

	# ---- which goals ----

	def cycle(self):
		return frappe.db.get_value("Life Cycle", {"space": self.space, "status": "Active"}, ["name", "title", "start_date", "end_date"], as_dict=True)

	def goals(self):
		"""The cycle's goals in progress, then the other goals planned in this review."""
		if self._goals is None:
			active = weekplan.active_goals(self.space)
			cyc = self.cycle()
			self._goals = [g for g in active if cyc and g.cycle == cyc.name] + [g for g in active if g.name in self.st["extra"] and not (cyc and g.cycle == cyc.name)]
			self._others = [g for g in active if g not in self._goals]
		return self._goals

	def cycle_names(self):
		cyc = self.cycle()
		return [g.name for g in self.goals() if cyc and g.cycle == cyc.name]

	def others(self):
		self.goals()
		return self._others

	# ---- the plans ----

	def plan(self, goal):
		"""The plan of one goal: the owner's, or the prefill (a task made during the review wins over a prefill)."""
		p = dict(self.st["plans"].get(goal) or {})
		made = next((c for c in reversed(self.review.state.get("created_tasks") or []) if c.get("goal") == goal
			and frappe.db.get_value("Life Task", c["task"], "status") in OPEN), None)
		if made and p.get("source") != "owner" and p.get("task") != made["task"]:
			p.update({"task": made["task"], "next_action": frappe.db.get_value("Life Task", made["task"], "title"), "source": "review"})
		return p

	def prefill(self, ai=False, now=None):
		"""Prefill every goal without a plan, and give each a slot; the assistant is asked once, for the goals with no task."""
		goals = [g for g in self.goals() if g.name not in self.st["plans"]]
		if not goals:
			return
		oldest = {}
		for t in frappe.get_all("Life Task", filters={"goal": ("in", [g.name for g in goals]), "status": ("in", list(OPEN)), "is_archived": 0,
				"scheduled_at": ("is", "not set")}, fields=["name", "title", "goal"], order_by="creation asc", limit=2000):
			oldest.setdefault(t.goal, t)
		advice, by = weekplan.suggest(self.space, [g for g in goals if g.name not in oldest], oldest) if ai else ({}, None)
		taken = goal_week.taken_by_plans(self)
		free = goal_week.free_left(self, now, extra_taken=taken)
		for g in goals:
			task, tip = oldest.get(g.name), advice.get(g.name) or {}
			minutes = tip.get("minutes") if tip.get("minutes") in weekplan.LENGTHS else weekplan.DEFAULT_MINUTES
			slot = weekplan.first_slot(free, minutes)
			if slot:
				free = weekplan.subtract(free, [(slot, slot + frappe.utils.datetime.timedelta(minutes=minutes))])
			self.st["plans"][g.name] = {"task": task.name if task else None, "next_action": task.title if task else (tip.get("next_action") or ""),
				"source": "oldest" if task else ("assistant" if tip.get("next_action") else "empty"), "by": by if not task and tip.get("next_action") else None, "slot": str(slot)[:16] if slot else None,
				"minutes": minutes, "who": "Me", "note": "", "skip": None}

	def save(self, goal, values):
		if goal not in [g.name for g in self.goals()]:
			frappe.throw(_("That goal is not in this review."), title=_("Goal not in this review"))
		p = self.plan(goal)
		for k in ("next_action", "task", "slot", "minutes", "who", "note"):
			if k not in values:
				continue
			v = values[k]
			# the values come from the browser: a dict or a list here would act as a filter later
			if v is not None and not isinstance(v, (str, int, float)) or (k != "minutes" and isinstance(v, (int, float))):
				frappe.throw(_("{0} must be text.").format(k), title=_("Value must be text"))
			p[k] = v
		p["next_action"] = " ".join(str(p.get("next_action") or "").split())[:140]
		if p.get("task") and frappe.db.get_value("Life Task", p["task"], "goal") != goal:
			frappe.throw(_("That task is not under this goal."), title=_("Task is not under goal"))
		minutes = cint(p.get("minutes")) or weekplan.DEFAULT_MINUTES
		if minutes < 5 or minutes > 600:
			frappe.throw(_("The length must be between 5 minutes and 10 hours."), title=_("Length out of range"))
		if p.get("slot"):
			frappe.utils.get_datetime(p["slot"])  # refuses what is not a date and time
		p["who"] = " ".join(str(p.get("who") or "Me").split())[:140]
		p["note"] = str(p.get("note") or "")[:2000]
		p.update({"minutes": minutes, "slot": str(p["slot"])[:16] if p.get("slot") else None, "skip": None, "source": "owner"})
		self.st["plans"][goal] = p
		return p

	def skip(self, goal, reason):
		reason = " ".join((reason or "").split())[:200]
		if not reason:
			frappe.throw(_("Say why this goal is skipped this week."), title=_("Skipped goal needs a reason"))
		p = self.plan(goal)
		p.update({"skip": reason, "source": "owner"})
		self.st["plans"][goal] = p
		self.st["stars"] = [s for s in self.stars() if s != goal]

	def unskip(self, goal):
		p = self.plan(goal)
		p["skip"] = None
		self.st["plans"][goal] = p

	def add_other(self, goal):
		if goal not in [g.name for g in self.others()] and goal not in self.st["extra"]:
			frappe.throw(_("That goal is not in progress."), title=_("Goal is not in progress"))
		if goal not in self.st["extra"]:
			self.st["extra"].append(goal)
		self._goals = None

	# ---- stars ----

	def stars(self):
		"""Exactly three: the owner's, else the assistant's suggestion, else the three cycle goals furthest behind."""
		if self.st.get("stars") is not None:
			return [s for s in self.st["stars"] if s in [g.name for g in self.goals()]]
		return self.suggested_stars()

	def suggested_stars(self):
		rows = [g for g in self.goals() if not self.plan(g.name).get("skip")]
		cycle = [g for g in rows if g.name in self.cycle_names()]
		pool = cycle if len(cycle) >= STARS else rows
		behind = sorted(pool, key=lambda g: goal_week.percent(self, g))
		got = self.st.get("star_tip") or []
		chosen = [s for s in got if s in [g.name for g in pool]][:STARS]
		return chosen if len(chosen) == min(STARS, len(pool)) else [g.name for g in behind[:STARS]]

	def set_star(self, goal, on):
		stars = list(self.stars())
		if on and goal not in stars:
			if self.plan(goal).get("skip"):
				frappe.throw(_("A skipped goal cannot be one of the top three."), title=_("Skipped goal cannot be top"))
			stars.append(goal)
		elif not on:
			stars = [s for s in stars if s != goal]
		self.st["stars"] = stars

	def needed(self):
		planned = [g for g in self.goals() if not self.plan(g.name).get("skip")]
		return min(STARS, len(planned))

	# ---- done? ----

	def ready(self):
		"""Every cycle goal has a next action or a skip with a reason, and the stars are exactly three."""
		missing = [n for n in self.cycle_names() if not self.plan(n).get("skip") and not (self.plan(n).get("next_action") or "").strip()]
		stars, need = len(self.stars()), self.needed()
		left = []
		if missing:
			left.append(f"{len(missing)} goal{'s need' if len(missing) > 1 else ' needs'} a next action or a skip")
		if stars < need:
			left.append(f"Star {need - stars} more goal{'s' if need - stars > 1 else ''} to go on" if need - stars > 1 else "Star one more goal to go on")
		elif stars > need:
			left.append(f"Unstar {stars - need} goal{'s' if stars - need > 1 else ''}: exactly {need} are starred")
		return {"ok": not left, "left": left, "missing": missing, "stars": stars, "needed": need}


# ---- what the tab shows ----

def tab(review, now=None):
	from lifeos.review import goal_week

	gp = GoalPlan(review)
	cyc = gp.cycle()
	stars = gp.stars()
	rows = [row(gp, g, stars) for g in gp.goals()]
	others = gp.others()
	score = None
	if cyc:
		c = frappe.get_doc("Life Cycle", cyc.name)
		score = journal_score(c)
	ready = gp.ready()
	planned = [r for r in rows if not r["plan"].get("skip") and (r["plan"].get("next_action") or "").strip()]
	return {"cycle": {"name": cyc.name, "title": cyc.title} if cyc else None, "rows": rows, "stars": stars, "needed": gp.needed(), "ready": ready,
		"others": {"n": len(others), "titles": [g.title for g in others[:2]], "rows": [{"goal": g.name, "title": g.title, "horizon": g.horizon} for g in others]},
		"capacity": goal_week.capacity(gp, now), "score": score, "target": cint(frappe.db.get_single_value("Life Settings", "score_target")) or 85,
		"glance": goal_week.glance(gp, now), "to_schedule": len(planned)}


def journal_score(cycle):
	from lifeos import cycles

	week = cycles.current_week(cycle)
	s = cycles.week_score(cycle.name, week)
	return {"week": week, "percent": s["percent"], "done": s["done"], "planned": s["planned"]}


def row(gp, g, stars):
	from lifeos.review import goal_week

	m = goal_week.mark_of(gp, g)
	prog = goal_week.progress_of(g)
	full = frappe.db.get_value("Life Goal", g.name, ["measure_kind", "measure", "start_value", "target_value", "done_when"], as_dict=True)
	return {"goal": g.name, "title": g.title, "horizon": g.horizon, "area": g.area, "in_cycle": g.name in gp.cycle_names(), "star": g.name in stars,
		"mark": m["mark"], "progress": prog, "plan": gp.plan(g.name), "needs_finish_line": not readings.has_finish_line(full),
		"readings": frappe.db.count("Life Goal Reading", {"goal": g.name, "status": "Suggested"}),
		"open_tasks": frappe.db.count("Life Task", {"goal": g.name, "status": ("in", list(OPEN)), "is_archived": 0})}


def detail(review, goal, now=None):
	"""A goal opened from the tab (board 32)."""
	from lifeos.review import goal_week

	gp = GoalPlan(review)
	g = next((x for x in gp.goals() + gp.others() if x.name == goal), None)
	if not g:
		frappe.throw(_("That goal is not in progress."), title=_("Goal is not in progress"))
	doc = frappe.get_doc("Life Goal", goal)
	doc.check_permission("read")
	r = row(gp, g, gp.stars())
	plan = r["plan"]
	minutes = cint(plan.get("minutes")) or weekplan.DEFAULT_MINUTES
	people = frappe.get_all("Life Person", filters={"space": gp.space, "relation": ("!=", "Self")}, pluck="full_name", order_by="full_name asc", limit=50)
	return {**r, "cycle_title": g.cycle_title, "area_name": frappe.db.get_value("Life Area", g.area, "area_name") if g.area else None,
		"finish_line": _finish_line(doc), "measure": {k: doc.get(k) for k in ("measure_kind", "done_when", "measure", "unit", "start_value", "target_value")},
		"tasks": frappe.get_all("Life Task", filters={"goal": goal, "status": ("in", list(OPEN)), "is_archived": 0}, fields=["name", "title"],
			order_by="creation asc", limit=50),
		"slots": goal_week.slots(gp, goal, minutes, now=now), "people": people, "planned_here": goal in gp.st["extra"] or r["in_cycle"]}


def _finish_line(doc):
	if doc.measure_kind == "Number":
		return f"{doc.measure} from {doc.start_value:,g} to {doc.target_value:,g}{(' ' + doc.unit) if doc.unit else ''}"
	return (doc.done_when or "").strip() or None


# ---- the plan-week skill's stars ----

def suggest_stars(gp):
	"""Ask the plan-week skill once for the three goals that matter most; kept as the review's star tip."""
	from lifeos.review import goal_week
	from lifeos.skills import call

	goals = [g for g in gp.goals() if g.name in gp.cycle_names()]
	if len(goals) <= STARS or gp.st.get("star_tip") is not None:
		return
	ids = {f"G{i + 1}": g for i, g in enumerate(goals[:30])}
	got = call.ask("plan-week", {"request": "stars", "goals": [{"goal": k, "title": g.title, "percent": goal_week.percent(gp, g)} for k, g in ids.items()]},
		space=gp.space)
	if not got:
		return
	picked = [ids[k].name for k in got.get("stars") or [] if k in ids][:STARS]
	gp.st["star_tip"] = picked if len(picked) == STARS else []
	gp.st["star_by"] = got.label
