"""Set 8, step 1: the review record and its piles. The period (first review, normal, skipped week), resume after a pause, the
tab gates, pile sorting without a key, each pile decision with its Outbox exit and Undo, Chase, and the review-note migration."""
import contextlib
import json

import frappe
from frappe.utils import add_days, getdate, now_datetime, today

from lifeos.api import weekly
from lifeos.review import piles
from lifeos.review.record import Review, period_text
from lifeos.tests.base import FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase
from lifeos.tests.test_ux5_ask import set_key
from lifeos.tests.test_ux7_old_inbox import OldCase


def lock(space, user, start, end):
	return frappe.get_doc({"doctype": "Life Review", "space": space, "user": user, "status": "Locked", "period_start": start,
		"period_end": end, "locked_on": now_datetime(), "title": "x", "tab_state": "{}"}).insert(ignore_permissions=True)


@contextlib.contextmanager
def tidy(decide):
	"""The tidy-backlog skill answering for the review's piles (model faked): `decide(item)` gives keep, park, drop or None (left out)."""
	from lifeos.ai import fake

	def answer(params):
		data = fake.asked(params)[1]
		if "items" not in data:  # another skill's request (the review also asks notice about meetings)
			return {"content": [{"type": "text", "text": json.dumps({"insights": [], "follow_ups": [], "readings": []})}]}
		rows = [{"item": i["item"], "decision": d, "reason": f"{d} by the skill", "chase": i["kind"] == "Waiting"} for i in data["items"] if (d := decide(i))]
		return {"content": [{"type": "text", "text": json.dumps({"decisions": rows})}]}

	was = frappe.db.get_value("Life Space", PRIVATE, "ask_enabled")
	frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", 1)
	set_key("sk-test-not-real")
	frappe.set_user(OWNER)  # set_key works as Administrator
	frappe.flags.lifeos_ai_backend = fake.ScriptedFake([answer] * 8)
	try:
		yield
	finally:
		frappe.flags.lifeos_ai_backend = None
		set_key("")
		frappe.set_user(OWNER)
		frappe.db.set_value("Life Space", PRIVATE, "ask_enabled", was)


class ReviewCase(OldCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Life Review", {"space": ("in", [PRIVATE, SHARED])})
		# only what each test makes is stuck or waiting
		frappe.db.sql("update `tabLife Task` set status='Done' where space=%s and status in ('Open', 'Doing', 'Waiting')", PRIVATE)
		frappe.db.sql("update `tabLife Inbox Item` set status='Done' where space=%s and status='To Review'", PRIVATE)

	def task(self, title, age=40, status="Open", waiting_on=None, goal=None, created_days=90):
		doc = self.make("Life Task", title=title, status=status, waiting_on=waiting_on, goal=goal)
		frappe.db.set_value("Life Task", doc.name, {"last_touched_on": add_days(today(), -age),
			"creation": add_days(now_datetime(), -created_days)}, update_modified=False)
		return doc.name

	def cycle_goal(self, title):
		cycle = frappe.db.get_value("Life Cycle", {"space": PRIVATE, "status": "Active"}) or self.make("Life Cycle", title="s8 cycle",
			start_date=add_days(today(), -14), end_date=add_days(today(), 69), status="Active").name
		return self.make("Life Goal", title=title, horizon="12 weeks", cycle=cycle)

	def ref(self, name, dt="Life Task"):
		return f"{dt}:{name}"


class TestPeriod(ReviewCase):
	def test_first_review_is_the_last_seven_days(self):
		start, end = Review.period(PRIVATE, OWNER, "2026-11-22")
		self.assertEqual((str(start), str(end)), ("2026-11-16", "2026-11-22"))
		self.assertEqual(period_text(start, end), "Week of 16 to 22 November")

	def test_since_the_last_locked_review(self):
		lock(PRIVATE, OWNER, "2026-11-09", "2026-11-15")
		start, end = Review.period(PRIVATE, OWNER, "2026-11-22")
		self.assertEqual(str(start), "2026-11-16")

	def test_a_skipped_week_is_said(self):
		lock(PRIVATE, OWNER, "2026-11-02", "2026-11-08")
		start, end = Review.period(PRIVATE, OWNER, "2026-11-22")
		self.assertEqual(str(start), "2026-11-09")
		self.assertEqual(period_text(start, end), "Covers 9 to 22 November (you skipped last week)")
		self.assertEqual(period_text("2026-10-28", "2026-11-03"), "Week of 28 October to 3 November")

	def test_one_open_review_and_its_owner_only(self):
		weekly.start(space=PRIVATE)
		weekly.start(space=PRIVATE)
		self.assertEqual(frappe.db.count("Life Review", {"space": PRIVATE, "user": OWNER, "status": "Open"}), 1)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Life Review", "space": PRIVATE, "user": OWNER, "period_start": today(), "period_end": today()}).insert()
		# another member of a shared space neither sees nor opens the owner's review
		weekly.start(space=SHARED)
		self.as_user(FAMILY)
		self.assertFalse(frappe.get_list("Life Review", filters={"space": SHARED, "user": OWNER}))
		self.assertIsNone(weekly.get(space=SHARED)["name"])


class TestResumeAndGates(ReviewCase):
	def test_read_before_the_first_change_writes_nothing(self):
		head = weekly.get(space=PRIVATE)
		self.assertIsNone(head["name"])
		self.assertEqual(head["first"], "library")
		self.assertEqual(frappe.db.count("Life Review", {"space": PRIVATE}), 0)

	def test_resume_after_pause_and_tab_gates(self):
		stuck = self.task("s8 stuck", age=70)
		self.cycle_goal("s8 resume goal")  # a goal to plan, so the Goals tab is not done by having nothing in it
		head = weekly.start(space=PRIVATE)
		self.assertTrue(head["openable"]["tasks"])  # Library never blocks
		self.assertFalse(head["openable"]["goals"])
		self.assertFalse(head["done"]["library"])
		weekly.visit(space=PRIVATE, tab="library")
		weekly.pile_settle(space=PRIVATE, key="tasks", ref=self.ref(stuck), decision="park")
		# pause: leave and come back; everything is where it was
		frappe.local.response = frappe._dict()
		head = weekly.start(space=PRIVATE)
		self.assertTrue(head["done"]["library"])
		self.assertTrue(head["done"]["tasks"])
		self.assertEqual(head["first"], "goals")
		got = weekly.pile_summary(space=PRIVATE, key="tasks")
		self.assertEqual(got["left"], 0)
		self.assertEqual(frappe.db.get_value("Life Task", stuck, "status"), "Someday")


class TestPiles(ReviewCase):
	def test_without_a_key_everything_waits_except_waiting_items(self):
		"""Issue 59: no rule parks or lets go of anything; Needs you holds it, and a waiting item is kept (chased after a week)."""
		set_key("")
		frappe.set_user(OWNER)
		goal = self.cycle_goal("s8 goal")
		names = {"goal": self.task("s8 serves", age=40, goal=goal.name), "old": self.task("s8 old", age=70), "ancient": self.task("s8 ancient", age=130),
			"chase": self.task("s8 asked", age=10, status="Waiting", waiting_on="Ruchi"),
			"wait": self.task("s8 just asked", age=3, status="Waiting", waiting_on="Ruchi"),
			"new": self.task("s8 came this week", age=40, created_days=1)}
		weekly.start(space=PRIVATE)
		items = {i["name"]: i for i in piles.PileSet(Review.find_open(PRIVATE, OWNER), "tasks").items()}
		for key in ("goal", "old", "ancient"):
			self.assertEqual(items[names[key]]["pile"], "needs")
		self.assertEqual((items[names["chase"]]["pile"], items[names["chase"]]["chase"]), ("keep", True))
		self.assertEqual((items[names["wait"]]["pile"], items[names["wait"]]["chase"]), ("keep", False))
		self.assertNotIn(names["new"], items)  # came in during the period: handled in Library
		self.assertTrue(all(i["reason"] for i in items.values()))
		self.assertIsNone(piles.PileSet(Review.find_open(PRIVATE, OWNER), "tasks").summary()["by"])
		task = self.old_item("s8 inbox task", ["Task"], age=2)
		got = {i["name"]: i["pile"] for i in piles.PileSet(Review.find_open(PRIVATE, OWNER), "inbox").items()}
		self.assertEqual(got[task], "needs")

	def test_the_skill_sorts_tasks_and_inbox_items_into_the_piles(self):
		"""I59.2: one skill, tidy-backlog, sorts the review's piles; what it leaves out waits under Needs you."""
		frappe.set_user(OWNER)
		goal = self.cycle_goal("s8 goal")
		names = {"goal": self.task("s8 serves", age=40, goal=goal.name), "keep": self.task("s8 recent", age=40),
			"park": self.task("s8 old", age=70), "letgo": self.task("s8 ancient", age=130)}
		task = self.old_item("s8 inbox task", ["Task"], age=2)
		note = self.old_item("s8 inbox note", ["Note"], age=2)
		empty = self.old_item("s8 inbox empty", age=3, status="New")
		table = {"s8 recent": "keep", "s8 old": "park", "s8 ancient": "drop", "s8 inbox task": "keep", "s8 inbox note": "park", "s8 inbox empty": "drop"}
		with tidy(lambda i: table.get(i["title"])):
			weekly.start(space=PRIVATE)
			items = {i["name"]: i for i in piles.PileSet(Review.find_open(PRIVATE, OWNER), "tasks").items()}
			got = {i["name"]: i["pile"] for i in piles.PileSet(Review.find_open(PRIVATE, OWNER), "inbox").items()}
		self.assertEqual(items[names["goal"]]["pile"], "needs")  # left out by the skill
		self.assertEqual([items[names[k]]["pile"] for k in ("keep", "park", "letgo")], ["keep", "park", "letgo"])
		self.assertEqual(items[names["park"]]["by"], "tidy-backlog v1")
		self.assertEqual((got[task], got[note], got[empty]), ("keep", "park", "letgo"))
		self.assertEqual(piles.PileSet(Review.find_open(PRIVATE, OWNER), "tasks").summary()["by"], "tidy-backlog v1")

	def test_needs_you_is_at_most_five(self):
		goal = self.cycle_goal("s8 goal 2")
		for i in range(7):
			self.task(f"s8 needs {i}", age=40 + i, goal=goal.name)
		weekly.start(space=PRIVATE)
		s = weekly.pile_summary(space=PRIVATE, key="tasks")
		self.assertEqual(s["needs_left"], 5)
		self.assertEqual(sum(1 for i in piles.PileSet(Review.find_open(PRIVATE, OWNER), "tasks").items() if i["reason"] == "Not sure; kept for now."), 2)

	def test_each_decision_its_exit_and_undo(self):
		keep, park, letgo = self.task("s8 k", age=40), self.task("s8 p", age=70), self.task("s8 l", age=130)
		weekly.start(space=PRIVATE)
		weekly.pile_settle(space=PRIVATE, key="tasks", ref=self.ref(keep), decision="keep")
		self.assertEqual(frappe.db.get_value("Life Task", keep, "status"), "Open")
		self.assertEqual(str(frappe.db.get_value("Life Task", keep, "last_touched_on")), today())
		weekly.pile_settle(space=PRIVATE, key="tasks", ref=self.ref(park), decision="park")
		weekly.pile_settle(space=PRIVATE, key="tasks", ref=self.ref(letgo), decision="letgo")
		self.assertEqual(self.exits(park), ["Parked"])
		self.assertEqual(self.exits(letgo), ["Discarded"])
		for name in (keep, park, letgo):
			weekly.pile_undo(space=PRIVATE, key="tasks", ref=self.ref(name))
		self.assertEqual([frappe.db.get_value("Life Task", n, "status") for n in (keep, park, letgo)], ["Open"] * 3)
		self.assertEqual(self.exits(park) + self.exits(letgo), [])
		self.assertEqual(str(frappe.db.get_value("Life Task", keep, "last_touched_on")), str(add_days(today(), -40)))
		# inbox items: accept, park as an idea, discard to the trash; each undone
		a, p, d = self.old_item("s8 a", ["Task"], age=2), self.old_item("s8 n", ["Note"], age=2), self.old_item("s8 e", age=3, status="New")
		for name, dec in ((a, "keep"), (p, "park"), (d, "letgo")):
			weekly.pile_settle(space=PRIVATE, key="inbox", ref=self.ref(name, "Life Inbox Item"), decision=dec)
		self.assertEqual(self.exits(a), ["Done"])
		self.assertEqual(self.exits(p), ["Parked"])
		self.assertEqual(self.exits(d), ["Discarded"])
		for name in (a, p, d):
			weekly.pile_undo(space=PRIVATE, key="inbox", ref=self.ref(name, "Life Inbox Item"))
		self.assertEqual([frappe.db.get_value("Life Inbox Item", n, "status") for n in (a, p, d)], ["To Review", "To Review", "New"])
		self.assertEqual(self.exits(a) + self.exits(p) + self.exits(d), [])

	def test_accept_a_pile_move_one_and_undo_both(self):
		one, two, three = (self.task(f"s8 park {i}", age=70 + i) for i in range(3))
		with tidy(lambda i: "park"):
			weekly.start(space=PRIVATE)
		weekly.pile_settle(space=PRIVATE, key="tasks", ref=self.ref(one), decision="keep")  # moved to Keep
		res = weekly.pile_accept(space=PRIVATE, key="tasks", pile="park")
		self.assertEqual(res["done"], 2)
		park = res["summary"]["piles"]["park"]
		self.assertTrue(park["done"])
		self.assertEqual(park["moved"], {"keep": 1})
		self.assertEqual(res["summary"]["piles"]["keep"]["count"], 1)
		self.assertEqual([frappe.db.get_value("Life Task", n, "status") for n in (one, two, three)], ["Open", "Someday", "Someday"])
		res = weekly.pile_undo(space=PRIVATE, key="tasks", pile="park")
		self.assertEqual(res["summary"]["piles"]["park"]["count"], 3)
		self.assertEqual(res["summary"]["left"], 3)
		self.assertEqual([frappe.db.get_value("Life Task", n, "status") for n in (one, two, three)], ["Open"] * 3)
		self.assertEqual(sum(len(self.exits(n)) for n in (one, two, three)), 0)

	def test_chase_creates_a_task_and_got_it_marks_answered(self):
		asked = self.task("s8 drainage photos", age=10, status="Waiting", waiting_on="Mr. Rao")
		answered = self.task("s8 blend query", age=10, status="Waiting", waiting_on="Mithun")
		weekly.start(space=PRIVATE)
		weekly.pile_settle(space=PRIVATE, key="tasks", ref=self.ref(asked), decision="keep", chase=1)
		chase = frappe.db.get_value("Life Task", {"space": PRIVATE, "title": "Chase Mr. Rao: s8 drainage photos"}, ["name", "due_date", "status"], as_dict=True)
		self.assertEqual((str(chase.due_date), chase.status), (today(), "Open"))
		weekly.pile_settle(space=PRIVATE, key="tasks", ref=self.ref(answered), decision="letgo")
		self.assertEqual(frappe.db.get_value("Life Task", answered, "status"), "Done")
		weekly.pile_undo(space=PRIVATE, key="tasks", ref=self.ref(asked))
		self.assertFalse(frappe.db.exists("Life Task", chase.name))
		self.assertFalse(frappe.db.exists("Life Exit", {"record_name": chase.name}))

	def test_agents_are_refused(self):
		from lifeos.tests.base import AGENT

		self.as_user(AGENT)
		for fn, kw in ((weekly.get, {}), (weekly.start, {}), (weekly.pile_accept, {"pile": "park"})):
			with self.assertRaises(frappe.PermissionError):
				fn(space=PRIVATE, **kw)
