"""Tab 2, Tasks (set 8): "Left your plate", the four Outbox piles for the review's period, read only. Each count opens the
Outbox on that pile and period, which lists exactly that many rows."""
from lifeos.api import outbox as outbox_api

PILES = ("Done", "Delegated", "Parked", "Discarded")
LINES = {"Done": "tasks and captures", "Delegated": "handed to others", "Parked": "moved to Someday", "Discarded": "let go"}


def left_your_plate(review):
	space, a, b = review.doc.space, str(review.doc.period_start), str(review.doc.period_end)

	def door(pile, label):
		n = outbox_api.total(space, pile, from_date=a, to_date=b)
		return {"n": int(n), "label": label, "to": {"path": "/library/outbox", "query": {"pile": pile, "from": a, "to": b}}}

	return {"piles": [{"pile": p, "line": LINES[p], **door(p, f"{p.lower()} in this review's period")} for p in PILES],
		"in": door("in", "came in"), "out": door("all", "went out"), "outbox": {"path": "/library/outbox", "query": {"pile": "all", "from": a, "to": b}}}
