"""Issue 13: every task has an area. Give each task without one a guessed area by the goal, the capture, the rule match
or Career (no model calls), marked as guessed for the owner to confirm."""
import frappe

from lifeos import area_guess


def execute():
	frappe.flags.lifeos_no_area_ai = True
	try:
		filled = area_guess.fill_missing(use_ai=False)
	finally:
		frappe.flags.lifeos_no_area_ai = False
	if filled:
		print(f"Guessed an area for {filled} task(s) that had none.")
