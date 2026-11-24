"""Shared test cases and helpers used by more than one test module."""
import contextlib
from datetime import timedelta
import io
import json
from unittest import mock

import frappe
from frappe.utils import add_days, get_datetime, now_datetime, today
from werkzeug.test import EnvironBuilder

from lifeos.library import files
from lifeos import permissions
from lifeos.ai import fake
from lifeos.api import inbox, settings, weekly
from lifeos.review import gcal
from lifeos.skills import runner, store
from lifeos.tests.base import AGENT, LifeTestCase, OWNER, PRIVATE, SHARED


def text(t):
	return {"type": "text", "text": t}


class AskCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		set_key("sk-test-not-real")
		frappe.db.delete("Life AI Usage")
		frappe.db.set_value("Life Space", PRIVATE, {"ask_enabled": 1, "ask_can_read_vault": 0})
		frappe.db.set_value("Life Space", SHARED, {"ask_enabled": 1, "ask_can_read_vault": 0})
		frappe.set_user(OWNER)

	def tearDown(self):
		frappe.flags.lifeos_ai_backend = None
		super().tearDown()

	def script(self, *responses):
		frappe.flags.lifeos_ai_backend = fake.ScriptedFake(responses)
		return frappe.flags.lifeos_ai_backend


def set_key(value):
	user = frappe.session.user
	frappe.set_user("Administrator")
	s = frappe.get_single("Life Settings")
	s.anthropic_api_key = value
	s.monthly_cap_usd = 30
	s.save()
	frappe.clear_cache(doctype="Life Settings")
	frappe.set_user(user)


class NoModel:
	"""A backend that fails the test if it is called."""

	calls = 0

	def run(self, params, on_text=None):
		NoModel.calls += 1
		raise AssertionError("the model was called")


SKILL = "process-capture"


def use(name, args, id="t1"):
	return {"content": [{"type": "tool_use", "id": id, "name": name, "input": args}], "stop_reason": "tool_use"}


def answer(summary="A summary.", transcript=""):
	return {"content": [{"type": "text", "text": json.dumps({"transcript_md": transcript, "summary_md": summary})}], "stop_reason": "end_turn"}


def task(title, area="Money", confidence=0.9, reason="It is a bill.", **extra):
	return use("propose", {"kind": "Task", "preview": title, "payload": {"title": title, "area": area}, "confidence": confidence, "reason": reason, **extra})


class SkillCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		set_key("sk-test-not-real")
		self.reset()
		frappe.db.set_value("Life Skill", SKILL, "active", 1)
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		frappe.db.set_single_value("Life Settings", "brain_auto_kinds", "[]")
		frappe.db.set_single_value("Life Settings", "brain_auto_threshold", 0.85)
		frappe.clear_cache(doctype="Life Settings")
		permissions.clear_cache()
		frappe.set_user(OWNER)

	def tearDown(self):
		frappe.flags.lifeos_ai_backend = None
		frappe.set_user("Administrator")
		self.reset()
		set_key("")
		frappe.db.delete("Life AI Usage")
		super().tearDown()

	def reset(self):
		"""The built-in skills as the app ships them, with no runs."""
		user = frappe.session.user
		frappe.set_user("Administrator")
		for dt in ("Life Skill Run", "Life Skill Version", "Life Skill Example"):
			frappe.db.delete(dt)
		frappe.db.delete("Life Skill")
		store.install()
		frappe.set_user(user)

	def script(self, *responses):
		frappe.flags.lifeos_ai_backend = fake.ScriptedFake(responses)
		return frappe.flags.lifeos_ai_backend

	def capture(self, text="The electricity bill of Rs 3,200 is due on 5 December.", **values):
		with mock.patch("frappe.enqueue"):
			item = frappe.get_doc({"doctype": "Life Inbox Item", "space": PRIVATE, "title": "Bill", "source_type": "Email", "raw_text": text,
				"status": "New", **values}).insert()
		frappe.db.delete("Life Skill Run")
		return item

	def process(self, item):
		log = runner.run(SKILL, {"doctype": "Life Inbox Item", "name": item.name, "space": item.space}, "Capture created")
		item.reload()
		return log


def upload(doctype, name, file_name, content):
	"""What /api/method/upload_file does for this request, through Life OS's override of it."""
	form = {"doctype": doctype, "docname": name, "is_private": "1"}
	had = getattr(frappe.local, "request", None)
	frappe.local.request = EnvironBuilder(method="POST", data={**form, "file": (io.BytesIO(content), file_name)}).get_request()
	frappe.local.form_dict = frappe._dict(form)
	try:
		return files.upload_file()
	finally:
		frappe.local.request = had
		frappe.local.form_dict = frappe._dict()


def item(title, space=PRIVATE, **kw):
	return inbox.create_item(title=title, source_type="Upload", space=space, **kw)["name"]


class OldCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		set_key("")
		frappe.set_user(OWNER)
		self.mode("Suggest", 7)
		# earlier items of this space are out of the way: only what each test makes is old
		frappe.db.sql("update `tabLife Inbox Item` set received_on = now() where space=%s", PRIVATE)

	def mode(self, mode, days):
		settings.save({"old_inbox_mode": mode, "old_inbox_days": days})
		frappe.clear_document_cache("Life Settings", "Life Settings")

	def old_item(self, title, kinds=(), age=10, status="To Review"):
		made = inbox.create_item(space=PRIVATE, title=title, source_type="Message", raw_text="x")
		if kinds or status == "To Review":
			frappe.db.set_value("Life Inbox Item", made["name"], {"status": "Processing", "claimed_by": AGENT, "claimed_on": now_datetime()})
			self.as_user(AGENT)
			inbox.submit_result(made["name"], summary_md="s", proposals=[
				{"kind": k, "preview": f"{title} {k} {i}", "payload": {"title": f"{title} {k} {i}", "area": "Tea"} if k != "Event" else
					{"subject": f"{title} {i}", "starts_on": f"{add_days(today(), 3)} 10:00:00"}} for i, k in enumerate(kinds)])
			self.as_user(OWNER)
		frappe.db.set_value("Life Inbox Item", made["name"], "received_on", add_days(now_datetime(), -age), update_modified=False)
		return made["name"]

	def exits(self, name):
		return frappe.get_all("Life Exit", filters={"record_name": name, "reversed": 0}, pluck="pile")


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


class GoalsCase(ReviewCase):
	def setUp(self):
		super().setUp()
		frappe.db.sql("update `tabLife Goal` set outcome='Achieved' where space=%s and outcome='In Progress'", PRIVATE)
		self.goals = [self.cycle_goal(f"s8 cycle goal {i}").name for i in range(4)]

	def tab(self):
		return weekly.goals(space=PRIVATE)

	def row(self, goal):
		return next(r for r in self.tab()["rows"] if r["goal"] == goal)


ME = "owner@lifeos.test"


def gevent(key, start, minutes, title, emails, recurring=False):
	start = get_datetime(start)
	return {"id": f"s8-{key}", "status": "confirmed", "summary": title, "start": {"dateTime": start.isoformat()},
		"end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat()},
		"attendees": [{"email": e, "displayName": e.split("@")[0].title()} for e in emails], **({"recurringEventId": "s8-rec"} if recurring else {})}


class CalCase(LifeTestCase):
	def setUp(self):
		super().setUp()
		set_key("")
		frappe.set_user(OWNER)
		frappe.db.sql("delete from `tabEvent` where life_space=%s", PRIVATE)
		frappe.db.delete("Life Meeting Link", {"space": PRIVATE})
		frappe.db.delete("Life Insight", {"space": PRIVATE})
		frappe.db.set_single_value("Life Settings", "own_domains", "lifeos.test")
		self.day = add_days(today(), -2)

	def tearDown(self):
		frappe.db.set_single_value("Life Settings", "own_domains", "")
		super().tearDown()

	def read(self, *events):
		for e in events:
			gcal.upsert(OWNER, PRIVATE, "primary", e)
		return {e["summary"]: frappe.db.get_value("Event", {"google_calendar_event_id": e["id"]}, ["name", "life_matters", "life_matters_set_by"], as_dict=True)
			for e in events}

	def capture(self, title, at, kind="Voice Note", text=""):
		doc = self.make("Life Inbox Item", title=title, source_type=kind, raw_text=text, status="Done")
		frappe.db.set_value("Life Inbox Item", doc.name, "received_on", at, update_modified=False)
		return doc.name


class Keyed(LifeTestCase):
	"""A site with a key, and a model the test supplies."""

	def setUp(self):
		super().setUp()
		set_key("sk-test-not-real")
		frappe.set_user(OWNER)

	def tearDown(self):
		frappe.flags.lifeos_ai_backend = None
		frappe.set_user("Administrator")
		set_key("")
		super().tearDown()


def find(text, **kwargs):
	"""`search.query` after the records the test saved are written to the search index (in use a job does it; a search is a GET and cannot)."""
	from frappe.utils.global_search import sync_global_search

	from lifeos.api import search

	sync_global_search()
	return search.query(text, **kwargs)


# ---------- issue 104: files to read on this server ----------

def text_pdf(words):
	"""A one-page PDF whose text layer holds `words` (written by hand: Helvetica, one line)."""
	content = f"BT /F1 18 Tf 72 720 Td ({words}) Tj ET".encode()
	objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
		b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
		b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content), b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
	out, offsets = b"%PDF-1.4\n", []
	for i, body in enumerate(objects, 1):
		offsets.append(len(out))
		out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
	start = len(out)
	out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
	return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, start)


def printed_png(lines, size=44):
	"""A photo-like image of printed text (white page, black letters)."""
	from PIL import Image, ImageDraw, ImageFont

	font = ImageFont.load_default(size=size)
	img = Image.new("RGB", (1500, 120 * len(lines) + 80), "white")
	draw = ImageDraw.Draw(img)
	for i, line in enumerate(lines):
		draw.text((50, 50 + i * 110), line, fill="black", font=font)
	buf = io.BytesIO()
	img.save(buf, format="PNG")
	return buf.getvalue()


def scanned_pdf(lines):
	"""A PDF that is only a picture of printed text, with no text layer."""
	from PIL import Image

	img = Image.open(io.BytesIO(printed_png(lines, size=60))).convert("L")
	buf = io.BytesIO()
	img.save(buf, format="PDF", resolution=150)
	return buf.getvalue()


def scribble_png():
	"""Handwriting-like marks no printed-text reader can make words of: random strokes."""
	import random

	from PIL import Image, ImageDraw

	rng = random.Random(7)
	img = Image.new("RGB", (900, 500), "white")
	draw = ImageDraw.Draw(img)
	for _i in range(60):
		draw.line([(rng.randint(0, 900), rng.randint(0, 500)) for _j in range(4)], fill=(rng.randint(0, 90),) * 3, width=rng.randint(2, 5))
	buf = io.BytesIO()
	img.save(buf, format="PNG")
	return buf.getvalue()


def speech_wav():
	"""A recording of one spoken sentence about paying the electricity bill on Friday."""
	import os

	with open(os.path.join(os.path.dirname(__file__), "fixtures", "speech.wav"), "rb") as fh:  # nosemgrep: frappe-security-file-traversal -- a fixture of this repository
		return fh.read()
