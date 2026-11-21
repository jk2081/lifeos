"""Issue 24: Library > Files. Every stored file once, with where it is used, its versions, filters and the records' access."""
import base64

import frappe

from lifeos.api import files as files_api
from lifeos.api import jobs
from lifeos.tests.base import AGENT, FAMILY, PRIVATE, LifeTestCase
from lifeos.tests.test_issue7_files import item, upload

SLIDES = b"issue 24 slides"


class TestFilesList(LifeTestCase):
	def rows(self, **kw):
		return files_api.list(space=PRIVATE, **kw)["rows"]

	def by_name(self, name, **kw):
		return [r for r in self.rows(**kw) if r["name"] == name]

	def test_1_a_file_used_by_two_items_is_listed_once_with_both(self):
		a, b = item("i24 first user"), item("i24 second user")
		upload("Life Inbox Item", a, "i24 shared deck.pptx", SLIDES)
		upload("Life Inbox Item", b, "i24 shared deck.pptx", SLIDES)
		got = self.by_name("i24 shared deck.pptx")
		self.assertEqual(len(got), 1)
		self.assertEqual({u["name"] for u in got[0]["used_in"]}, {a, b})
		self.assertEqual(files_api.list(space=PRIVATE, q="i24 shared")["total"], 1)

	def test_2_a_file_with_two_versions_lists_both(self):
		it = item("i24 versions", external_id="i24-versions", source_system="claude")
		upload("Life Inbox Item", it, "i24 report.txt", b"one")
		upload("Life Inbox Item", it, "i24 report.txt", b"two, newer")
		got = self.by_name("i24 report.txt")
		self.assertEqual(len(got), 1)
		self.assertEqual(got[0]["version_count"], 2)
		self.assertEqual(len({v["url"] for v in got[0]["versions"]}), 2)
		self.assertTrue(got[0]["versions"][0]["current"] and got[0]["versions"][0]["url"] == got[0]["url"])

	def test_3_the_type_filter_holds_only_that_type(self):
		it = item("i24 types")
		for n, b in (("i24 a.pptx", b"s"), ("i24 b.txt", b"d"), ("i24 c.png", b"i"), ("i24 d.mp3", b"a")):
			upload("Life Inbox Item", it, n, b)
		for t, n in (("slides", "i24 a.pptx"), ("documents", "i24 b.txt"), ("images", "i24 c.png"), ("audio", "i24 d.mp3")):
			names = [r["name"] for r in self.rows(type=t)]
			self.assertIn(n, names)
			self.assertTrue(all(files_api.file_type(x) == t for x in names), (t, names))
		self.assertRaises(frappe.ValidationError, files_api.list, space=PRIVATE, type="video")

	def test_4_a_file_only_a_closed_vault_document_uses_is_not_listed_for_the_agent(self):
		frappe.db.set_value("Life Space", PRIVATE, "agents_can_read_vault", 0)
		doc = self.make("Life Vault Document", title="i24 passport", doc_type="ID").name
		upload("Life Vault Document", doc, "i24 passport.txt", b"passport")
		it = item("i24 plain")
		upload("Life Inbox Item", it, "i24 both.txt", b"both")
		upload("Life Vault Document", doc, "i24 both.txt", b"both")
		self.assertEqual(len(self.by_name("i24 passport.txt")), 1)
		self.as_user(AGENT)
		self.assertEqual(self.by_name("i24 passport.txt"), [])
		both = self.by_name("i24 both.txt")
		self.assertEqual([u["name"] for u in both[0]["used_in"]], [it])

	def test_5_a_user_outside_the_space_cannot_list_its_files(self):
		upload("Life Inbox Item", item("i24 private"), "i24 private.txt", b"private")
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, files_api.list, space=PRIVATE)

	def test_6_a_reusable_asset_shows_how_many_jobs_used_it(self):
		inputs = [{"name": "i24 BTW deck.txt", "file": base64.b64encode(b"i24 btw deck").decode(), "reusable_as": "i24-btw-deck"}]
		for k in (1, 2):
			jobs.file_job(job_id=f"i24-job-{k}", space=PRIVATE, title=f"i24 job {k}", raw_text="x", inputs=inputs, outputs=[])
		got = self.by_name("i24 BTW deck.txt")
		self.assertEqual(len(got), 1)
		self.assertTrue(got[0]["reusable"])
		self.assertEqual(got[0]["jobs"], 2)

	def test_7_the_area_and_source_filters_narrow_the_list(self):
		it = item("i24 area", area=self.life["Career"])
		upload("Life Inbox Item", it, "i24 career.txt", b"career")
		upload("Life Inbox Item", item("i24 no area"), "i24 loose.txt", b"loose")
		self.assertEqual([r["name"] for r in self.rows(area=self.life["Career"], q="i24 ")], ["i24 career.txt"])
		self.assertEqual([r["name"] for r in self.rows(area="none", q="i24 loose")], ["i24 loose.txt"])
		self.assertEqual(len(self.rows(source="brain", q="i24 career")), 0)
