"""Names shared by hooks, permissions and the index. No frappe imports here: hooks.py loads this early."""

# Every lifeos DocType that carries a `space` field.
SPACE_DOCTYPES = [
	"Life Area", "Life Person",
	"Life Inbox Item", "Life Proposal", "Life Task",
	"Life Cycle", "Life Goal", "Life Habit", "Life Habit Log",
	"Life Note", "Life Vault Document",
	"Life Chat Log", "Life Link", "Life Index", "Life Action Log",
	"Life Wiki Change", "Life Connection", "Life Source Setting",
	"Life Agent Config", "Life Agent Fact", "Life Agent Job", "Life Agent Change", "Life Agent Action",
	"Life Insight",
	"Life Goal Reading", "Life Exit",
	"Life Review", "Life Meeting Link", "Life Wiki Finding",
]

# DocTypes an agent never reads or writes (UX fixes, set 5): insights, and Ask's threads, which belong to one person.
NO_AGENT_DOCTYPES = ["Life Insight", "Life Ask Thread", "Life Ask Message", "Life AI Usage", "Life Exit",
	"Life Review", "Life Meeting Link", "Life Wiki Finding",
	"Life Agent Config", "Life Agent Fact", "Life Agent Job", "Life Agent Change", "Life Agent Action", "Life Mail Account", "Life Mail Search"]

# DocTypes that carry the organisation fields of section 4a.
ORG_DOCTYPES = [
	"Life Inbox Item", "Life Task", "Life Note", "Life Vault Document", "Life Chat Log",
]

# DocTypes written to Life Index: the organisation DocTypes.
INDEXED_DOCTYPES = [*ORG_DOCTYPES]

# Records a [[Title]] link can point to, with their title field. Order is the match priority.
LINKABLE = {
	"Life Note": "title", "Life Task": "title", "Life Person": "full_name",
	"Life Vault Document": "title", "Life Chat Log": "title", "Life Goal": "title",
}

ROLES = ["Life Admin", "Life User", "Life Agent"]
