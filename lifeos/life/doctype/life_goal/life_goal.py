import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today

HORIZONS = ("Long term", "Year", "12 weeks", "Month")


def planning_in_quarters():
	return frappe.db.get_single_value("Life Settings", "planning_period") == "Quarters"


def derive_horizon(target_date=None, cycle=None, space=None, on=None):
	"""The horizon a goal falls in, from what the form knows: its cycle, or its target date. The owner may change it."""
	if cycle:
		return "12 weeks"
	if not target_date:
		return "Long term"
	day, now = getdate(target_date), getdate(on or today())
	if (day.year, day.month) == (now.year, now.month):
		return "Month"
	if planning_in_quarters():
		if day.year == now.year and (day.month - 1) // 3 == (now.month - 1) // 3:
			return "12 weeks"
	else:
		active = frappe.db.get_value("Life Cycle", {"space": space, "status": "Active"}, ["start_date", "end_date"], as_dict=True) if space else None
		if active and getdate(active.start_date) <= day <= getdate(active.end_date):
			return "12 weeks"
	return "Year" if day <= getdate(add_days(now, 366)) else "Long term"


def check_cycle_open(cycle, flags=None):
	if flags and flags.allow_closed:
		return
	if cycle and frappe.db.get_value("Life Cycle", cycle, "status") == "Closed":
		frappe.throw(_("A closed cycle is read-only."), title=_("Cycle already closed"))


class LifeGoal(Document):
	def before_validate(self):
		if self.cycle and not self.space:
			self.space = frappe.db.get_value("Life Cycle", self.cycle, "space")

	def validate(self):
		if not self.is_someday:
			self.someday_on = self.someday_review_on = None
		self.check_horizon()
		# closed_on: the day the outcome left In Progress
		if (self.outcome or "In Progress") == "In Progress":
			self.closed_on = None
		elif not self.closed_on:
			self.closed_on = today()
		# an open-ended goal carries what a project did (set 6): when it was completed and when it last moved
		self.completed_on = self.closed_on if (self.outcome or "In Progress") != "In Progress" else None
		if not self.flags.keep_touched:
			self.last_activity_on = today()
		if self.horizon != "Long term":
			self.on_hold = 0
		self.check_serves()
		self.check_measure()
		check_cycle_open(self.cycle, self.flags)
		for a in self.actions:
			a.per_week = max(1, int(a.per_week or 1))
			if a.status == "Done" and not a.done_on:
				a.done_on = today()
			if a.status != "Done":
				a.done_on = None

	def check_horizon(self):
		if not self.horizon:
			self.horizon = derive_horizon(self.target_date, self.cycle, self.space)
		if self.horizon == "12 weeks" and not self.cycle and not planning_in_quarters():
			self.cycle = frappe.db.get_value("Life Cycle", {"space": self.space, "status": "Active"}) if self.target_date else None
			if not self.cycle:
				frappe.throw(_("A 12-week goal belongs to a cycle."), title=_("Goal needs a cycle"))
		if self.horizon != "12 weeks" and self.cycle:
			frappe.throw(_("Only a 12-week goal belongs to a cycle. Use Add to a 12 Week Year to move it into one."), title=_("Goal cannot have a cycle"))
		if self.horizon in ("Year", "Month") and not self.target_date:
			frappe.throw(_("A {0} goal needs a target date.").format(_(self.horizon).lower()), title=_("Goal needs a target date"))
		if self.horizon != "12 weeks" and self.actions:
			frappe.throw(_("Weekly actions belong to 12-week goals."), title=_("Actions need a 12-week goal"))

	def check_measure(self):
		"""Key results (set 7): a milestone goal needs its finish line, a number goal its measure, start and target. The
		current value is the latest confirmed reading and is never typed."""
		from lifeos import readings

		if self.measure_kind != "Number":
			self.measure = self.unit = None
			self.start_value = self.target_value = None
		if self.is_new() and not self.flags.from_restore:
			self.current_value, self.current_on = 0, None
		readings.check_goal(self)

	def check_serves(self):
		"""A goal serves a longer goal of the same space, never itself and never in a loop."""
		if not self.serves:
			return
		if self.serves == self.name:
			frappe.throw(_("A goal cannot serve itself."), frappe.ValidationError, title=_("Goal cannot serve itself"))
		if frappe.db.get_value("Life Goal", self.serves, "space") != self.space:
			frappe.throw(_("A goal can only serve a goal of the same space."), frappe.ValidationError, title=_("Goal is in another space"))
		seen, cur = {self.name}, self.serves
		while cur:
			if cur in seen:
				frappe.throw(_("{0} already serves this goal, so this goal cannot serve it.").format(
					frappe.bold(frappe.db.get_value("Life Goal", self.serves, "title"))), frappe.ValidationError,
					title=_("Goals serve each other"))
			seen.add(cur)
			cur = frappe.db.get_value("Life Goal", cur, "serves")

	def on_update(self):
		# an open-ended goal that is finished archives itself and what is filed under it, as a project did
		from lifeos import archive

		before = self.get_doc_before_save()
		closed = (self.outcome or "In Progress") not in ("In Progress", "Carried")
		was_closed = before and (before.outcome or "In Progress") not in ("In Progress", "Carried")
		if self.horizon == "Long term" and closed and not was_closed and not self.is_archived and not self.flags.no_archive:
			archive.archive_goal(self)

	def on_trash(self):
		check_cycle_open(self.cycle, self.flags)
		frappe.db.delete("Life Action Log", {"goal": self.name})
		frappe.db.delete("Life Goal Reading", {"goal": self.name})
