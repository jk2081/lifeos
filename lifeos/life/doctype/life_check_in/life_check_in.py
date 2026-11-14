import re

import frappe
from frappe import _
from frappe.model.document import Document

RANGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:[-–—]|to)\s*(\d+(?:\.\d+)?)\s*$")


def parse_range(value):
	"""'2-3' -> (2.0, 3.0). '7' -> (7.0, 7.0). Blank -> (None, None)."""
	if value is None or value == "":
		return None, None
	if isinstance(value, (int, float)):
		return float(value), float(value)
	if isinstance(value, (list, tuple)) and len(value) == 2:
		return float(value[0]), float(value[1])
	m = RANGE_RE.match(str(value))
	if m:
		return float(m.group(1)), float(m.group(2))
	try:
		v = float(str(value).strip())
	except ValueError:
		frappe.throw(_("{0} is not a score or a range such as 2-3.").format(value), frappe.ValidationError)
	return v, v


class LifeCheckin(Document):
	def validate(self):
		seen = set()
		for row in self.scores:
			if row.dimension in seen:
				frappe.throw(_("A dimension is scored twice."))
			seen.add(row.dimension)
			for kind in ("habits", "situation"):
				low, high = row.get(f"{kind}_low"), row.get(f"{kind}_high")
				if low is None and high is None:
					continue
				low = high if low is None else low
				high = low if high is None or (high == 0 and low > 0) else high
				if low > high:
					low, high = high, low
				if not (0 <= low <= 10 and 0 <= high <= 10):
					frappe.throw(_("Scores are 0 to 10."), frappe.ValidationError)
				row.set(f"{kind}_low", low)
				row.set(f"{kind}_high", high)
