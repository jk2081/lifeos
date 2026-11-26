"""Issue 119: Chat runs on Flow. Each Ask thread keeps its name, area and scope; its messages become a read-only note on the thread (`transcript`), so
nothing the owner asked before is lost, and the `Life Ask Message` table is dropped."""
import json

import frappe

TABLE = "tabLife Ask Message"


def execute():
	if frappe.db.table_exists("Life Ask Message"):
		move_messages()
	frappe.db.delete("DocType", {"name": "Life Ask Message"})
	frappe.db.sql_ddl(f"drop table if exists `{TABLE}`")  # nosemgrep: frappe-semgrep-rules.rules.frappe-using-db-sql -- the table of a DocType that no longer exists


def move_messages():
	"""Every thread with messages gets them as JSON [{id, role, text, at}], oldest first (those a thread already holds from an assistant's channel are kept)."""
	m = frappe.qb.DocType("Life Ask Message")
	rows = frappe.qb.from_(m).select(m.name, m.thread, m.role, m.text, m.creation, m.status).where(m.status == "Done").orderby(m.creation).run(as_dict=True)  # nosemgrep: frappe-semgrep-rules.rules.frappe-missing-permission-check -- a one-off patch moves every user's threads
	by_thread = {}
	for r in rows:
		if r.text:
			by_thread.setdefault(r.thread, []).append({"id": r.name, "role": r.role, "text": r.text, "at": str(r.creation)[:19]})
	for thread, msgs in by_thread.items():
		if not frappe.db.exists("Life Ask Thread", thread):
			continue
		held = frappe.db.get_value("Life Ask Thread", thread, "transcript")
		kept = frappe.parse_json(held) if held else []
		have = {k.get("id") for k in kept}
		merged = sorted(kept + [x for x in msgs if x["id"] not in have], key=lambda x: x["at"])
		frappe.db.set_value("Life Ask Thread", thread, "transcript", json.dumps(merged), update_modified=False)
