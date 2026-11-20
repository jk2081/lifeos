"""UX fixes, set 6: the lens. Every list method narrows to an area with its sub-areas, and to records that list the area
in "also in"; the counts and Today follow it."""
import json

import frappe
from frappe.utils import today

from lifeos import counts
from lifeos.api import archive, chats, goals, graph, inbox, journal, library, search, someday, sources, tasks, timeline, vault
from lifeos.api import today as today_api
from lifeos.api.utils import in_area
from lifeos.tests.base import PRIVATE, LifeTestCase


class TestLens(LifeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.parent = cls.life["Career"]  # issue 11: an area of life with its parts
		cls.sub = frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Lens Estate", "parent_area": cls.parent}).insert().name
		cls.other = cls.areas["Money"]

	def filed(self, doctype, title_field="title", **values):
		"""Three records: one in the sub-area, one in another area that lists the parent in "also in", one only elsewhere."""
		sub = self.make(doctype, **{title_field: f"lens {doctype} sub", "area": self.sub, **values})
		also = self.make(doctype, **{title_field: f"lens {doctype} also", "area": self.other, "also_in": [{"area": self.parent}], **values})
		out = self.make(doctype, **{title_field: f"lens {doctype} elsewhere", "area": self.other, **values})
		return sub.name, also.name, out.name

	def check(self, names, listed, label):
		sub, also, out = names
		self.assertIn(sub, listed, f"{label}: a record in a sub-area is in its parent area")
		self.assertIn(also, listed, f"{label}: a record listing the area in also-in is in it")
		self.assertNotIn(out, listed, f"{label}: a record of another area is not")

	def test_tasks(self):
		names = self.filed("Life Task", status="Open")
		res = tasks.list(space=PRIVATE, area=self.parent, page_length=100)
		self.check(names, [r.name for r in res["tasks"]], "tasks.list")
		self.assertEqual(res["total"], tasks.total(PRIVATE, status="open", area=self.parent))

	def test_inbox(self):
		names = self.filed("Life Inbox Item", status="To Review")
		res = inbox.list(space=PRIVATE, area=self.parent, page_length=100)
		self.check(names, [r.name for r in res["items"]], "inbox.list")

	def test_notes_and_sources(self):
		names = self.filed("Life Note", content_md="x")
		self.check(names, [r.name for r in library.list(space=PRIVATE, area=self.parent, page_length=100)["notes"]], "library.list")
		self.check(names, [n.name for n in library.tree(space=PRIVATE, area=self.parent)["notes"]], "library.tree")
		chat_names = self.filed("Life Chat Log", date=today())
		res = sources.list(space=PRIVATE, area=self.parent, tab="chats", page_length=100)
		self.check(chat_names, [r["name"] for r in res["sources"]], "sources.list")
		self.check(chat_names, [r.name for r in chats.list(space=PRIVATE, area=self.parent, page_length=100)["chats"]], "chats.list")
		res = timeline.get(space=PRIVATE, area=self.parent, page_length=200)
		self.check(names, [r.ref_name for d in res["days"] for r in d["entries"]], "timeline.get")

	def test_vault(self):
		names = self.filed("Life Vault Document", doc_type="Other")
		self.check(names, [r.name for r in vault.list(space=PRIVATE, area=self.parent, page_length=100)["documents"]], "vault.list")

	def test_goals_and_someday(self):
		sub = self.make("Life Goal", title="lens goal sub", goal_type="Open", area=self.sub)
		out = self.make("Life Goal", title="lens goal elsewhere", goal_type="Open", area=self.other)
		listed = [r.name for r in goals.list(space=PRIVATE, area=self.parent, page_length=100)["goals"]]
		self.assertIn(sub.name, listed)
		self.assertNotIn(out.name, listed)
		names = self.filed("Life Task", status="Open")
		for n in names:
			someday.park(doctype="Life Task", name=n)
		listed = [r.name for r in someday.list(space=PRIVATE, area=self.parent, page_length=100)["rows"]]
		self.check(names, listed, "someday.list")

	def test_archive(self):
		names = self.filed("Life Note", content_md="x")
		for n in names:
			frappe.db.set_value("Life Note", n, {"is_archived": 1, "archived_on": today()})
			frappe.get_doc("Life Note", n).save()
		res = archive.list(space=PRIVATE, area=self.parent, page_length=100)
		self.check(names, [r.ref_name for r in res["records"]], "archive.list")

	def test_search(self):
		names = self.filed("Life Note", content_md="zanzibarlens")
		res = search.query(text="zanzibarlens", space=PRIVATE, area=self.parent)
		self.check(names, [r.ref_name for r in res["results"]], "search.query")
		self.assertEqual(len(search.query(text="zanzibarlens", space=PRIVATE)["results"]), 3)

	def test_counts_and_today(self):
		names = self.filed("Life Task", status="Open", due_date=today())
		band = counts.open_band(PRIVATE, self.parent)
		self.assertEqual(band["open_tasks"]["to"]["query"]["area"], self.parent)
		self.assertEqual(band["open_tasks"]["n"], tasks.list(space=PRIVATE, area=self.parent, status="all",
			filters=band["open_tasks"]["to"]["query"]["f"], page_length=1)["total"])
		self.assertLess(band["open_tasks"]["n"], counts.open_band(PRIVATE)["open_tasks"]["n"])
		day = today_api.get(space=PRIVATE, area=self.parent)
		listed = [r.name for g in day["next"]["groups"] if g["key"] == "today" for r in g["rows"] if r.get("type") == "task"]
		self.check(names, listed, "today.get")
		self.assertEqual(next(g for g in day["next"]["groups"] if g["key"] == "today")["tasks"]["n"], len(listed))  # set 8: the top three come first
		side = counts.sidebar(PRIVATE, self.parent)
		self.assertEqual(side["tasks"]["to"]["query"]["area"], self.parent)

	def test_in_area_and_grid(self):
		names = self.filed("Life Task", status="Open")
		self.assertEqual(in_area(PRIVATE, self.parent, "Life Task", list(names)), set(names[:2]))
		self.assertEqual(in_area(PRIVATE, None, "Life Task", list(names)), set(names))
		g = graph.get(space=PRIVATE, area=self.parent)
		self.assertIsInstance(g["nodes"], list)
		self.assertIsNone(journal.grid(space=PRIVATE, area=self.parent)) if not frappe.db.exists("Life Cycle", {"space": PRIVATE}) else None

	def test_new_area_gets_a_colour(self):
		a = frappe.get_doc("Life Area", self.life["Mind"])  # issue 11: the seven come with their colours
		self.assertEqual(a.colour, "violet")
		b = frappe.get_doc({"doctype": "Life Area", "space": PRIVATE, "area_name": "Lens Colour Sub", "parent_area": a.name}).insert()
		self.assertEqual(b.colour, a.colour)
		json.dumps(a.as_dict(), default=str)
