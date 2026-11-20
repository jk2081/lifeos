"""Names shared by hooks, permissions and the index. No frappe imports here: hooks.py loads this early."""

# Every lifeos DocType that carries a `space` field.
SPACE_DOCTYPES = [
	"Life Area", "Life Project", "Life Tag", "Life Dimension", "Life Person",
	"Life Inbox Item", "Life Proposal", "Life Task", "Life Important Date",
	"Life Cycle", "Life Goal", "Life Month Plan", "Life Habit", "Life Habit Log",
	"Life Check-in", "Life Journal Page", "Life Note", "Life Vault Document",
	"Life Chat Log", "Life Link", "Life Index", "Life Action Log",
	"Life Wiki Change", "Life Connection",
	"Life Idea", "Life Insight",
	"Life Goal Reading", "Life Exit",
	"Life Review", "Life Meeting Link",
]

# DocTypes an agent never reads or writes (UX fixes, set 5): insights, and Ask's threads, which belong to one person;
# and projects, kept read-only after they became goals (set 6).
NO_AGENT_DOCTYPES = ["Life Insight", "Life Ask Thread", "Life Ask Message", "Life AI Usage", "Life Project", "Life Exit",
	"Life Review", "Life Meeting Link"]

# DocTypes that carry the organisation fields of section 4a.
ORG_DOCTYPES = [
	"Life Inbox Item", "Life Task", "Life Note", "Life Vault Document", "Life Chat Log", "Life Journal Page",
]

# DocTypes written to Life Index: the organisation DocTypes plus check-ins and month plans.
INDEXED_DOCTYPES = [*ORG_DOCTYPES, "Life Check-in", "Life Month Plan"]

# Records a [[Title]] link can point to, with their title field. Order is the match priority.
LINKABLE = {
	"Life Note": "title", "Life Task": "title", "Life Person": "full_name",
	"Life Vault Document": "title", "Life Chat Log": "title", "Life Goal": "title",
}

ROLES = ["Life Admin", "Life User", "Life Agent"]
