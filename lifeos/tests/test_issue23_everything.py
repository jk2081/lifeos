"""Issue 23: Library > Everything. Notes, documents, people and chats in one list, each tab one kind, search and filters."""
import frappe

from lifeos.api import everything
from lifeos.tests.base import AGENT, PRIVATE, LifeTestCase


class TestEverything(LifeTestCase):
	def setUp(self):
		super().setUp()
		for dt in ("Life Note", "Life Vault Document", "Life Chat Log", "Life Person"):
			frappe.db.delete(dt, {"space": PRIVATE})
		frappe.db.delete("Life Index", {"space": PRIVATE})
		self.career = self.life["Career"]
		self.note = self.make("Life Note", title="i23 plain note", content_md="the zebrafruit idea", area=self.career).name
		self.wiki = self.make("Life Note", title="i23 Mehi Motors", collection="Wiki", summary="Organisation · Honda dealer", content_md="x").name
		self.page = self.make("Life Note", title="i23 wiki page", collection="Wiki", summary="A concept", content_md="x").name
		self.doc = self.make("Life Vault Document", title="i23 passport", doc_type="ID").name
		self.chat = self.make("Life Chat Log", title="i23 chat", assistant="Claude", date="2026-11-18", summary_md="s",
			open_items=[{"text": "do it", "status": "Open"}]).name
		self.person = self.make("Life Person", full_name="i23 Mr Rao", relation="Manager").name

	def refs(self, **kw):
		return [r["ref"] for r in everything.list(space=PRIVATE, **kw)["rows"]]

	def test_everything_shows_each_kind_with_its_letter_and_line(self):
		rows = {r["ref"]: r for r in everything.list(space=PRIVATE)["rows"]}
		self.assertEqual(rows["note:" + self.note]["letter"], "N")
		self.assertEqual(rows["note:" + self.wiki]["letter"], "P")
		self.assertIn("kept by the Brain", rows["note:" + self.wiki]["line"])
		self.assertEqual(rows["note:" + self.page]["letter"], "N")
		self.assertEqual(rows["vault:" + self.doc]["letter"], "D")
		self.assertIn("sensitive", rows["vault:" + self.doc]["line"])
		self.assertEqual(rows["chat:" + self.chat]["letter"], "C")
		self.assertEqual(rows["chat:" + self.chat]["line"], "Chat · Claude · 1 open item")
		self.assertEqual(rows["person:" + self.person]["line"], "Person · Manager")
		dates = [r["date"] for r in everything.list(space=PRIVATE)["rows"]]
		self.assertEqual(dates, sorted(dates, reverse=True))

	def test_each_tab_holds_only_its_kind(self):
		for tab, letter in (("notes", "N"), ("documents", "D"), ("people", "P"), ("chats", "C")):
			rows = everything.list(space=PRIVATE, tab=tab)["rows"]
			self.assertTrue(rows, tab)
			self.assertEqual({r["letter"] for r in rows}, {letter}, tab)
		self.assertIn("person:" + self.person, self.refs(tab="people"))
		self.assertIn("note:" + self.wiki, self.refs(tab="people"))
		self.assertNotIn("note:" + self.wiki, self.refs(tab="notes"))

	def test_search_finds_a_word_in_the_body_and_the_area_filter_narrows(self):
		self.assertEqual(self.refs(q="zebrafruit"), ["note:" + self.note])
		self.assertEqual(self.refs(q="50% off_"), [])
		self.assertEqual(self.refs(area=self.career), ["note:" + self.note])
		self.assertEqual(everything.list(space=PRIVATE, q="zebrafruit", area=self.life["Health"])["total"], 0)

	def test_a_closed_vault_hides_the_sensitive_document(self):
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		self.assertIn("vault:" + self.doc, self.refs())
		self.as_user(AGENT)
		self.assertNotIn("vault:" + self.doc, self.refs())
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 1)
		self.as_user(AGENT)
		self.assertIn("vault:" + self.doc, self.refs())
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)

	def test_a_bad_tab_is_refused(self):
		self.assertRaises(frappe.ValidationError, everything.list, space=PRIVATE, tab="nope")
