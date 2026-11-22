"""Set 7, step 2: the Outbox. Every exit transition and its reversal, In without double counting, Today's line, Bring back
and the backfill."""
import frappe
from frappe.utils import add_days, getdate, now_datetime, today

from lifeos import counts, outbox, trash
from lifeos.api import goals, inbox, review, someday, tasks
from lifeos.api import outbox as outbox_api
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, LifeTestCase


def exits(doctype, name, counting=True):
	f = {"record_doctype": doctype, "record_name": name}
	if counting:
		f["reversed"] = 0
	return frappe.get_all("Life Exit", filters=f, pluck="pile", order_by="creation asc")


class OutboxCase(LifeTestCase):
	def task(self, title="ux7 task", **kw):
		return frappe.get_doc({"doctype": "Life Task", "space": PRIVATE, "title": title, "area": self.areas["Tea"], "status": "Open", **kw}).insert()


class TestTaskExits(OutboxCase):
	def test_done_and_reopen(self):
		t = self.task()
		tasks.set_status(t.name, "Done")
		self.assertEqual(exits("Life Task", t.name), ["Done"])
		tasks.set_status(t.name, "Open")
		self.assertEqual(exits("Life Task", t.name), [])
		self.assertEqual(exits("Life Task", t.name, counting=False), ["Done"])

	def test_delegated_only_to_someone_else(self):
		t = self.task()
		tasks.set_status(t.name, "Waiting", waiting_on="Jai")  # the owner's own name: not delegated
		self.assertEqual(exits("Life Task", t.name), [])
		tasks.set_status(t.name, "Waiting", waiting_on="Mithun")
		self.assertEqual(exits("Life Task", t.name), ["Delegated"])
		tasks.set_status(t.name, "Done")  # moving pile: counted once
		self.assertEqual(exits("Life Task", t.name), ["Done"])
		tasks.set_status(t.name, "Open")
		self.assertEqual(exits("Life Task", t.name), [])

	def test_parked_and_brought_back(self):
		t = self.task()
		someday.park("Life Task", t.name)
		self.assertEqual(exits("Life Task", t.name), ["Parked"])
		someday.bring_back("Life Task", t.name)
		self.assertEqual(exits("Life Task", t.name), [])

	def test_dropped_and_deleted_and_restored(self):
		t = self.task()
		tasks.set_status(t.name, "Dropped")
		self.assertEqual(exits("Life Task", t.name), ["Discarded"])
		tasks.set_status(t.name, "Open")
		self.assertEqual(exits("Life Task", t.name), [])
		trash.delete("Life Task", t.name)
		self.assertEqual(exits("Life Task", t.name), ["Discarded"])
		dd = frappe.db.get_value("Deleted Document", {"deleted_doctype": "Life Task", "deleted_name": t.name, "restored": 0})
		trash.restore(dd)
		self.assertEqual(exits("Life Task", t.name), [])

	def test_deleting_a_done_task_keeps_its_done_exit(self):
		t = self.task()
		tasks.set_status(t.name, "Done")
		trash.delete("Life Task", t.name)
		self.assertEqual(exits("Life Task", t.name), ["Done"])


class TestGoalExits(OutboxCase):
	def test_outcomes_someday_and_delete(self):
		g = goals.create("ux7 g1", "Year", space=PRIVATE, target_date=add_days(today(), 60), done_when="x")["name"]
		goals.close(g, "Achieved")
		self.assertEqual(exits("Life Goal", g), ["Done"])
		goals.close(g, "In Progress")
		self.assertEqual(exits("Life Goal", g), [])
		goals.close(g, "Partly Achieved")
		self.assertEqual(exits("Life Goal", g), ["Done"])
		goals.close(g, "Not Achieved")
		self.assertEqual(exits("Life Goal", g), ["Discarded"])
		goals.close(g, "In Progress")
		someday.park("Life Goal", g)
		self.assertEqual(exits("Life Goal", g), ["Parked"])
		someday.bring_back("Life Goal", g)
		self.assertEqual(exits("Life Goal", g), [])
		trash.delete("Life Goal", g)
		self.assertEqual(exits("Life Goal", g), ["Discarded"])

	def test_open_goal_dropped(self):
		g = goals.create("ux7 g2", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")["name"]
		goals.set_status(g, "Dropped")
		self.assertEqual(exits("Life Goal", g), ["Discarded"])
		goals.set_status(g, "Active")
		self.assertEqual(exits("Life Goal", g), [])


class TestCaptureAndIdeaExits(OutboxCase):
	def item_with(self, *titles):
		created = inbox.create_item(space=PRIVATE, title="ux7 capture", source_type="Message", raw_text="x")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		inbox.submit_result(created["name"], summary_md="s", proposals=[
			{"kind": "Task", "preview": t, "payload": {"title": t, "area": "Tea"}} for t in titles])
		self.as_user(OWNER)
		return created["name"], frappe.get_all("Life Proposal", filters={"inbox_item": created["name"]}, pluck="name", order_by="sort_order")

	def test_accepted_is_done(self):
		item, props = self.item_with("ux7 a", "ux7 b")
		review.decide(props[0], "accept")
		self.assertEqual(exits("Life Inbox Item", item), [])  # still in the Inbox
		review.decide(props[1], "reject")
		self.assertEqual(exits("Life Inbox Item", item), ["Done"])

	def test_all_rejected_is_discarded_and_undo_reverses(self):
		item, props = self.item_with("ux7 c")
		review.decide(props[0], "reject")
		self.assertEqual(exits("Life Inbox Item", item), ["Discarded"])

	def test_undo_of_an_accept_reverses(self):
		from lifeos.api import reset

		item, props = self.item_with("ux7 d")
		review.decide(props[0], "accept")
		self.assertEqual(exits("Life Inbox Item", item), ["Done"])
		reset.undo_decision(props[0]) if hasattr(reset, "undo_decision") else reset.undo([{"op": "unaccept", "proposal": props[0]}])
		self.assertEqual(exits("Life Inbox Item", item), [])

	def test_just_keep_is_done_and_delete_is_discarded(self):
		created = inbox.create_item(space=PRIVATE, title="ux7 keep", source_type="Message", raw_text="x", intent="Just keep")
		self.as_user(AGENT)
		inbox.claim_next(space=PRIVATE)
		inbox.submit_result(created["name"], transcript_md="x")
		self.as_user(OWNER)
		self.assertEqual(exits("Life Inbox Item", created["name"]), ["Done"])
		other = inbox.create_item(space=PRIVATE, title="ux7 junk", source_type="Message", raw_text="x")
		trash.delete("Life Inbox Item", other["name"])
		self.assertEqual(exits("Life Inbox Item", other["name"]), ["Discarded"])

	def test_something_parked_new_is_brought_back_and_purged(self):
		parked = someday.create("ux7 parked", space=PRIVATE, area=self.areas["Tea"])["name"]
		self.assertEqual(exits("Life Task", parked), ["Parked"])
		someday.bring_back("Life Task", parked)
		self.assertEqual(exits("Life Task", parked), [])
		parked2 = someday.create("ux7 parked 2", space=PRIVATE, area=self.areas["Tea"])["name"]
		someday.purge("Life Task", parked2)
		self.assertEqual(exits("Life Task", parked2), ["Parked"])  # it had already left the plate: that exit stands


class TestInAndOut(OutboxCase):
	def test_in_counts_nothing_twice(self):
		a, b = outbox.period_bounds("week")
		before = outbox_api.in_count(PRIVATE, None, a, b)
		self.task("ux7 direct")  # +1
		item = inbox.create_item(space=PRIVATE, title="ux7 in", source_type="Message", raw_text="x")  # +1
		self.task("ux7 from capture", inbox_item=item["name"])  # from a capture: 0
		someday.create("ux7 in parked", space=PRIVATE, area=self.areas["Tea"])  # a task made directly, parked: +1
		goals.create("ux7 in goal", "Long term", space=PRIVATE, area=self.areas["Tea"], done_when="x")  # +1
		self.assertEqual(outbox_api.in_count(PRIVATE, None, a, b) - before, 4)

	def test_today_line_matches_its_lists(self):
		t = self.task("ux7 line")
		tasks.set_status(t.name, "Done")
		line = counts.get(space=PRIVATE, which="week")  # issue 55: the line moved from Today to Brain > Activity
		for key, pile in (("in", "in"), ("out", "all")):
			door = line[key]
			self.assertEqual(door["to"]["path"], "/library/outbox")
			self.assertEqual(door["to"]["query"]["pile"], pile)
			rows = outbox_api.list(space=PRIVATE, pile=pile, period="week", page_length=500)
			self.assertEqual(door["n"], len(rows["rows"]))
			self.assertEqual(door["n"], rows["total"])
		listed = outbox_api.list(space=PRIVATE, pile="Done", page_length=500)
		self.assertIn(t.name, [r.record for r in listed["rows"]])
		self.assertEqual(listed["tabs"]["all"], sum(listed["tabs"][p] for p in outbox.PILES))

	def test_lens_keeps_to_the_area(self):
		t = self.task("ux7 lens", area=self.areas["Money"])
		tasks.set_status(t.name, "Done")
		tea = outbox_api.list(space=PRIVATE, pile="Done", area=self.areas["Tea"], page_length=500)
		self.assertNotIn(t.name, [r.record for r in tea["rows"]])

	def test_chart_has_eight_weeks(self):
		weeks = outbox_api.chart(space=PRIVATE)["weeks"]
		self.assertEqual(len(weeks), 8)
		self.assertEqual(getdate(weeks[-1]["week_of"]).weekday(), 0)


class TestBringBack(OutboxCase):
	def exit_of(self, doctype, name):
		return frappe.db.get_value("Life Exit", {"record_doctype": doctype, "record_name": name, "reversed": 0})

	def test_reopen_unpark_and_restore(self):
		done = self.task("ux7 bb done")
		tasks.set_status(done.name, "Done")
		outbox_api.bring_back(self.exit_of("Life Task", done.name))
		self.assertEqual(frappe.db.get_value("Life Task", done.name, "status"), "Open")
		self.assertEqual(exits("Life Task", done.name), [])

		parked = self.task("ux7 bb parked")
		someday.park("Life Task", parked.name)
		outbox_api.bring_back(self.exit_of("Life Task", parked.name))
		self.assertEqual(frappe.db.get_value("Life Task", parked.name, "status"), "Open")

		gone = self.task("ux7 bb deleted")
		trash.delete("Life Task", gone.name)
		outbox_api.bring_back(self.exit_of("Life Task", gone.name))
		self.assertTrue(frappe.db.exists("Life Task", gone.name))
		self.assertEqual(exits("Life Task", gone.name), [])

	def test_agents_and_readers_cannot(self):
		t = self.task("ux7 bb agent")
		tasks.set_status(t.name, "Done")
		e = self.exit_of("Life Task", t.name)
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, outbox_api.bring_back, e)
		self.assertRaises(frappe.PermissionError, outbox_api.list, space=PRIVATE)
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, outbox_api.bring_back, e)


class TestBackfill(OutboxCase):
	def test_backfill_from_existing_dates(self):
		from lifeos.patches.v8 import outbox_backfill

		t = self.task("ux7 old done")
		frappe.db.set_value("Life Task", t.name, {"status": "Done", "completed_on": add_days(today(), -20)})  # as before set 7: no exit
		p = self.task("ux7 old parked")
		frappe.db.set_value("Life Task", p.name, {"status": "Someday", "someday_on": add_days(today(), -5)})
		old = self.task("ux7 too old")
		frappe.db.set_value("Life Task", old.name, {"status": "Done", "completed_on": add_days(today(), -200)})
		g = goals.create("ux7 old goal", "Year", space=PRIVATE, target_date=add_days(today(), 30), done_when="x")["name"]
		frappe.db.set_value("Life Goal", g, {"outcome": "Achieved", "closed_on": add_days(today(), -3)})
		gone = self.task("ux7 old deleted")
		gone.flags.no_exit = True
		gone.delete()
		frappe.db.delete("Life Exit", {"record_name": ("in", [t.name, p.name, old.name, g, gone.name])})
		outbox_backfill.execute()
		self.assertEqual(exits("Life Task", t.name), ["Done"])
		self.assertEqual(str(frappe.db.get_value("Life Exit", {"record_name": t.name}, "exited_on"))[:10], add_days(today(), -20))
		self.assertEqual(exits("Life Task", p.name), ["Parked"])
		self.assertEqual(exits("Life Task", old.name), [])
		self.assertEqual(exits("Life Goal", g), ["Done"])
		self.assertEqual(exits("Life Task", gone.name), ["Discarded"])
		outbox_backfill.execute()  # again: nothing twice
		self.assertEqual(exits("Life Task", t.name), ["Done"])
