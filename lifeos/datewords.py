"""Quick add: read a date word at the start or end of a task title."""
import re
from datetime import date, timedelta

from frappe.utils import getdate, today

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
DAY_RE = r"(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(?:day|sday|nesday|urday)?"
MONTH_RE = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
PHRASE = (
	rf"(?:today|tod|tomorrow|tmrw|tmr|day after tomorrow|next week|next month|(?:next |this |on |by )?{DAY_RE}"
	rf"|in \d+ (?:day|days|week|weeks)|\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}(?:st|nd|rd|th)? {MONTH_RE}(?: \d{{4}})?|{MONTH_RE} \d{{1,2}}(?:st|nd|rd|th)?(?: \d{{4}})?)"
)
TAIL = re.compile(rf"^(?P<title>.+?)[\s,]+(?:due |by |on )?(?P<when>{PHRASE})$", re.I)
HEAD = re.compile(rf"^(?P<when>{PHRASE})[\s,:]+(?P<title>.+)$", re.I)


def _weekday(word):
	word = word.lower()[:3]
	return next(i for i, d in enumerate(DAYS) if d.startswith(word))


def _month(word):
	word = word.lower()[:3]
	return next(i + 1 for i, m in enumerate(MONTHS) if m.startswith(word))


def resolve(phrase, base=None):
	"""Turn a date phrase into a date, or None."""
	base = getdate(base or today())
	p = re.sub(r"^(on|by) ", "", phrase.lower().strip())
	if p in ("today", "tod"):
		return base
	if p in ("tomorrow", "tmrw", "tmr"):
		return base + timedelta(days=1)
	if p == "day after tomorrow":
		return base + timedelta(days=2)
	if p == "next week":
		return base + timedelta(days=7 - base.weekday())
	if p == "next month":
		return date(base.year + (base.month == 12), base.month % 12 + 1, 1)
	m = re.match(r"in (\d+) (day|week)s?$", p)
	if m:
		return base + timedelta(days=int(m.group(1)) * (7 if m.group(2) == "week" else 1))
	if re.match(r"\d{4}-\d{2}-\d{2}$", p):
		try:
			return getdate(p)
		except Exception:
			return None
	m = re.match(rf"(?:(next|this) )?({DAY_RE})$", p)
	if m:
		ahead = (_weekday(m.group(2)) - base.weekday()) % 7
		if ahead == 0:
			ahead = 7
		if m.group(1) == "next" and ahead < 7 - base.weekday():
			ahead += 7  # "next fri" said early in the week means the week after
		return base + timedelta(days=ahead)
	m = re.match(rf"(\d{{1,2}})(?:st|nd|rd|th)? ({MONTH_RE})(?: (\d{{4}}))?$", p) or None
	if m:
		day, month, year = int(m.group(1)), _month(m.group(2)), m.group(3)
	else:
		m = re.match(rf"({MONTH_RE}) (\d{{1,2}})(?:st|nd|rd|th)?(?: (\d{{4}}))?$", p)
		if not m:
			return None
		day, month, year = int(m.group(2)), _month(m.group(1)), m.group(3)
	try:
		d = date(int(year) if year else base.year, month, day)
	except ValueError:
		return None
	if not year and d < base:
		d = date(base.year + 1, month, day)
	return d


def parse(text, base=None):
	"""'Call Vivek tomorrow' -> ('Call Vivek', date). No date word -> (text, None)."""
	text = " ".join((text or "").split())
	for pattern in (TAIL, HEAD):
		m = pattern.match(text)
		if m:
			when = resolve(m.group("when"), base)
			if when:
				return m.group("title").strip(" ,"), when
	return text, None
