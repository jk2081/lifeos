"""Set 7: fill the Outbox for the last 12 weeks from the dates records already carry, so it is not empty on day one.

What is known exactly: a task's `completed_on`, a task's or goal's `someday_on`, a goal's `closed_on`, an inbox item's
`finished_on`, and the trash's deletion time. What is not: when a task became Waiting or Dropped, and when an idea was
brought back; those use the record's last change (`modified`), noted on the exit. Exits run once per record (a record that
already has one is skipped), so the patch can run again."""
import json

import frappe
from frappe.utils import add_days, get_datetime, getdate, today

from lifeos import outbox

WEEKS = 12


def execute():
	frappe.reload_doc("life", "doctype", "life_exit")
	add_indexes()
	since = add_days(getdate(today()), -7 * WEEKS)
	have = {(r.record_doctype, r.record_name) for r in frappe.get_all("Life Exit", fields=["record_doctype", "record_name"])}

	def put(dt, row, pile, on, note=None):
		if (dt, row.name) in have or not row.get("space"):
			return
		have.add((dt, row.name))
		area = row.get("area") if row.get("area") and frappe.db.get_value("Life Area", row.get("area"), "space") == row.space else None
		frappe.get_doc({"doctype": "Life Exit", "space": row.space, "area": area, "record_doctype": dt, "record_name": row.name,
			"title": (row.get("title") or row.name)[:140], "kind": outbox.KIND[dt], "pile": pile, "exited_on": get_datetime(on),
			"exited_by": row.get("modified_by") or row.get("owner"), "note": note}).insert(ignore_permissions=True, ignore_links=True)

	for t in frappe.get_all("Life Task", filters={"status": "Done", "completed_on": (">=", since)}, fields=["name", "space", "area", "title", "completed_on", "modified_by"]):
		put("Life Task", t, "Done", t.completed_on)
	for t in frappe.get_all("Life Task", filters={"status": "Someday", "someday_on": (">=", since)}, fields=["name", "space", "area", "title", "someday_on", "modified_by"]):
		put("Life Task", t, "Parked", t.someday_on)
	for t in frappe.get_all("Life Task", filters={"status": ("in", ["Waiting", "Dropped"]), "modified": (">=", since)},
			fields=["name", "space", "area", "title", "status", "waiting_on", "modified", "modified_by"]):
		t.doctype = "Life Task"
		pile = outbox.pile_of(t)
		if pile:
			put("Life Task", t, pile, t.modified, "Date of the task's last change: when it was " + ("delegated" if pile == "Delegated" else "dropped") + " was not recorded.")
	for g in frappe.get_all("Life Goal", filters={"closed_on": (">=", since)}, fields=["name", "space", "area", "title", "outcome", "closed_on", "is_someday", "modified_by"]):
		g.doctype = "Life Goal"
		g.is_someday = 0  # its close is what is dated here; a parked goal is handled below
		pile = outbox.pile_of(g)
		if pile:
			put("Life Goal", g, pile, g.closed_on)
	for g in frappe.get_all("Life Goal", filters={"is_someday": 1, "someday_on": (">=", since)}, fields=["name", "space", "area", "title", "someday_on", "modified_by"]):
		put("Life Goal", g, "Parked", g.someday_on)
	for i in frappe.get_all("Life Inbox Item", filters={"status": "Done", "finished_on": (">=", since)},
			fields=["name", "space", "area", "title", "status", "intent", "finished_on", "modified_by"]):
		doc = frappe._dict(i, doctype="Life Inbox Item")
		pile = outbox.pile_of(doc)
		if pile:
			put("Life Inbox Item", i, pile, i.finished_on)
	for i in frappe.get_all("Life Idea", filters={"status": "Brought Back", "modified": (">=", since)}, fields=["name", "space", "area", "title", "modified", "modified_by"]):
		put("Life Idea", i, "Done", i.modified, "Date of the idea's last change: when it was brought back was not recorded.")
	for d in frappe.get_all("Deleted Document", filters={"deleted_doctype": ("in", list(outbox.KIND)), "restored": 0, "creation": (">=", since)},
			fields=["deleted_doctype", "deleted_name", "data", "creation", "owner"]):
		try:
			data = frappe._dict(json.loads(d.data))
		except ValueError:
			continue
		data.name, data.modified_by = d.deleted_name, d.owner
		put(d.deleted_doctype, data, "Discarded", d.creation)


def add_indexes():
	frappe.db.add_index("Life Exit", ["space", "reversed", "exited_on", "pile"], "life_exit_period")
	frappe.db.add_index("Life Exit", ["record_doctype", "record_name", "reversed"], "life_exit_record")
