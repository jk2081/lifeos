"""The record pane's reference for a record ("task:<name>"), as the front end's lib/pane.js reads it (UX fixes, set 5:
insight evidence and Ask's citations open in the pane)."""

PANE_TYPES = {
	"Life Task": "task", "Life Inbox Item": "source", "Life Note": "note", "Life Vault Document": "vault",
	"Life Goal": "goal", "Life Idea": "idea", "Life Journal Page": "page", "Life Chat Log": "chat", "Event": "event",
	"Life Important Date": "date", "Life Check-in": "checkin", "Life Month Plan": "month",
}


def ref_of(doctype, name):
	t = PANE_TYPES.get(doctype)
	return f"{t}:{name}" if t else None
