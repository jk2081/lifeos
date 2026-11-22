"""Issue 58: the built-in Brain processes the captures no agent files itself, so process-capture is switched on.

Issue 28 shipped it off on every site (a site with an agent works the Inbox). The routing rule replaces that default: an agent keeps what it
files itself, everything else is the Brain's, and a capture is never left waiting. A site that already has the skill gets it switched on
once; the owner can switch it off again in Brain > Skills (the switch for an owner who wants agents to do everything)."""
import frappe


def execute():
	if frappe.db.exists("Life Skill", "process-capture"):
		frappe.db.set_value("Life Skill", "process-capture", "active", 1)
