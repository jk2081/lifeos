import calendar

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


def plan_name(space, year, month):
	return f"{space}-{int(year):04d}-{int(month):02d}"


class LifeMonthPlan(Document):
	def autoname(self):
		self.name = plan_name(self.space, self.year, self.month)

	def before_insert(self):
		if not self.habits and not self.flags.no_habit_copy:
			self.copy_habits_from_previous()

	def copy_habits_from_previous(self):
		year, month = int(self.year), int(self.month)
		py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
		prev = plan_name(self.space, py, pm)
		if not frappe.db.exists("Life Month Plan", prev):
			return
		rows = frappe.get_all(
			"Life Month Plan Habit", filters={"parent": prev, "parenttype": "Life Month Plan"},
			fields=["habit", "days_per_week", "sort_order", "tracked_until"], order_by="sort_order asc, idx asc",
		)
		for r in rows:
			if r.tracked_until:  # removed during last month
				continue
			self.append("habits", {"habit": r.habit, "days_per_week": r.days_per_week, "sort_order": r.sort_order})

	def validate(self):
		self.year, self.month = int(self.year or 0), int(self.month or 0)
		if not 1 <= self.month <= 12:
			frappe.throw(_("Month must be 1 to 12."))
		if self.name and self.name != plan_name(self.space, self.year, self.month) and not self.is_new():
			frappe.throw(_("The year and month of a plan cannot be changed."))
		first = getdate(f"{self.year}-{self.month:02d}-01")
		last = first.replace(day=calendar.monthrange(self.year, self.month)[1])
		seen = set()
		for i, h in enumerate(self.habits):
			if h.habit in seen:
				frappe.throw(_("A habit is listed twice in this month."))
			seen.add(h.habit)
			h.days_per_week = min(7, max(1, int(h.days_per_week or 7)))
			if not h.sort_order:
				h.sort_order = i + 1
			if not h.tracked_from:
				# a habit added mid-month counts from the day it was added
				now = getdate(today())
				h.tracked_from = now if (not self.is_new() and first <= now <= last) else first
			if getdate(h.tracked_from) < first:
				h.tracked_from = first
			if h.tracked_until and getdate(h.tracked_until) > last:
				h.tracked_until = last
