"""Tests for people."""
import frappe

from lifeos.library import people
from lifeos.api import people as people_api, tasks, wiki
from lifeos.tests.base import AGENT, FAMILY, LifeTestCase, PRIVATE
from lifeos.tests.helpers import task


class TestPeople(LifeTestCase):
	def setUp(self):
		super().setUp()
		for dt in ("Life Note", "Life Person", "Life Task", "Life Inbox Item", "Life Chat Log"):
			frappe.db.delete(dt, {"space": PRIVATE})
		frappe.db.delete("Life Index", {"space": PRIVATE})

	def persons(self):
		return frappe.get_all("Life Person", filters={"space": PRIVATE}, pluck="full_name")

	def test_1_a_wiki_page_made_as_an_organisation_creates_or_links_a_life_person(self):
		self.as_user(AGENT)
		page = wiki.create_page(space=PRIVATE, title="i25 Mehi Motors Pvt Ltd", summary="Honda dealer", content_md="Our dealer.", about="Organisation")
		person = frappe.get_doc("Life Person", frappe.db.get_value("Life Note", page["name"], "person"))
		self.assertEqual((person.kind, person.full_name, person.wiki_page), ("Organisation", "i25 Mehi Motors Pvt Ltd", page["name"]))
		# a person already called that is linked, not duplicated
		self.as_user("Administrator")
		existing = self.make("Life Person", full_name="i25 Mr Rao", aliases="Rao ji, R. Rao").name
		self.as_user(AGENT)
		page2 = wiki.create_page(space=PRIVATE, title="Rao ji", summary="Our manager", content_md="x", about="Person")
		self.assertEqual(frappe.db.get_value("Life Note", page2["name"], "person"), existing)
		self.assertEqual(frappe.db.get_value("Life Person", existing, "wiki_page"), page2["name"])
		self.assertEqual(len(self.persons()), 2)
		self.assertRaises(frappe.ValidationError, wiki.create_page, space=PRIVATE, title="i25 other", summary="s", about="Dog")

	def test_2_the_patch_links_matching_pages_and_makes_no_duplicates(self):
		rao = self.make("Life Person", full_name="i25 Mr Rao").name
		a = self.make("Life Note", title="i25 Mr Rao", collection="Wiki", summary="Person · manager", content_md="x").name
		b = self.make("Life Note", title="i25 Kunal Industries Ltd", collection="Wiki", summary="A supplier", content_md="x").name
		c = self.make("Life Note", title="i25 Someone Unknown", collection="Wiki", summary="Person · a neighbour", content_md="x").name
		d = self.make("Life Note", title="i25 A concept", collection="Wiki", summary="An idea", content_md="x").name
		out = people.link_existing(PRIVATE)
		self.assertEqual((set(out["linked"]), set(out["created"])), ({a}, {b}))
		self.assertEqual([u[0] for u in out["undecided"]], [c])
		self.assertEqual(frappe.db.get_value("Life Note", a, "person"), rao)
		kunal = frappe.db.get_value("Life Note", b, "person")
		self.assertEqual(frappe.db.get_value("Life Person", kunal, "kind"), "Organisation")
		self.assertFalse(frappe.db.get_value("Life Note", d, "person"))
		before = sorted(self.persons())
		again = people.link_existing(PRIVATE)
		self.assertEqual((again["linked"], again["created"]), ([], []))
		self.assertEqual(sorted(self.persons()), before)

	def test_3_list_filters_by_kind_and_shows_the_line_and_the_last_mention(self):
		org = self.make("Life Person", full_name="i25 Acme Ltd", kind="Organisation").name
		self.make("Life Person", full_name="i25 Asha", kind="Person", organisation=org, role="Buyer")
		self.make("Life Note", title="i25 call", content_md="spoke to Asha today")
		rows = {r["title"]: r for r in people_api.list(space=PRIVATE)["rows"]}
		self.assertEqual(set(rows), {"i25 Acme Ltd", "i25 Asha"})
		self.assertEqual(rows["i25 Asha"]["line"], "Buyer · i25 Acme Ltd")
		self.assertEqual(rows["i25 Acme Ltd"]["people_count"], 1)
		self.assertEqual(rows["i25 Acme Ltd"]["letter"], "O")
		orgs = people_api.list(space=PRIVATE, kind="Organisation")
		self.assertEqual([r["title"] for r in orgs["rows"]], ["i25 Acme Ltd"])
		self.assertEqual(orgs["counts"], {"Person": 1, "Organisation": 1})
		self.assertEqual([r["title"] for r in people_api.list(space=PRIVATE, q="buyer")["rows"]], ["i25 Asha"])
		self.assertEqual(rows["i25 Asha"]["last"], None)  # the note names "Asha", not "i25 Asha"
		self.assertRaises(frappe.ValidationError, people_api.list, space=PRIVATE, kind="Dog")

	def test_4_a_person_page_lists_what_mentions_them_newest_first(self):
		asha = self.make("Life Person", full_name="Asha Rao", aliases="Ashu").name
		old = self.make("Life Note", title="i25 old note", content_md="met Asha Rao in May")
		frappe.db.set_value("Life Note", old.name, "creation", "2026-05-01 10:00:00")
		frappe.db.sql("update `tabLife Index` set record_date = '2026-05-01' where ref_name = %s", old.name)
		new = self.make("Life Note", title="i25 new note", content_md="Ashu sent the papers")
		self.make("Life Note", title="i25 Karaoke night", content_md="nothing about her")
		task = self.make("Life Task", title="i25 chase papers", status="Waiting", waiting_on="the bank", waiting_on_person=asha).name
		delegated = self.make("Life Task", title="i25 file return", delegated_to=asha).name
		page = people_api.get(asha)
		refs = [m["ref"] for m in page["mentioned"]]
		self.assertEqual(set(refs), {"note:" + new.name, "note:" + old.name, "task:" + task, "task:" + delegated})
		self.assertEqual(refs[-1], "note:" + old.name)
		dates = [m["date"] for m in page["mentioned"]]
		self.assertEqual(dates, sorted(dates, reverse=True))
		how = {m["name"]: m["how"] for m in page["mentioned"]}
		self.assertEqual((how[task], how[delegated]), ("Waiting on them", "Delegated to them"))
		self.assertEqual(page["mentioned_total"], 4)
		self.assertEqual(page["aliases"], ["Ashu"])

	def test_5_an_organisation_page_lists_its_people_and_the_wiki_text(self):
		wikipage = self.make("Life Note", title="i25 Acme", collection="Wiki", summary="Organisation · supplier", content_md="Acme makes tea chests.").name
		org = self.make("Life Person", full_name="i25 Acme", kind="Organisation", wiki_page=wikipage).name
		a = self.make("Life Person", full_name="i25 Asha", organisation=org, role="Buyer").name
		page = people_api.get(org)
		self.assertEqual([p["name"] for p in page["people"]], [a])
		self.assertEqual(page["text"], "Acme makes tea chests.")
		self.assertEqual(people_api.get(a)["organisation"]["name"], org)
		self.assertNotIn("note:" + wikipage, [m["ref"] for m in page["mentioned"]])  # its own page is not a mention

	def test_6_rules_a_person_cannot_be_an_organisations_organisation_or_cross_spaces(self):
		person = self.make("Life Person", full_name="i25 P").name
		self.assertRaises(frappe.ValidationError, self.make, "Life Person", full_name="i25 Q", organisation=person)
		org = self.make("Life Person", full_name="i25 Org", kind="Organisation").name
		self.assertRaises(frappe.ValidationError, self.make, "Life Person", space="Test Shared", full_name="i25 R", organisation=org)

	def test_7_a_task_can_wait_on_or_be_delegated_to_a_person(self):
		asha = self.make("Life Person", full_name="i25 Asha").name
		t = self.make("Life Task", title="i25 task").name
		out = tasks.update(t, {"status": "Waiting", "waiting_on_person": asha})
		self.assertEqual((out["waiting_on_person"], out["waiting_on"]), (asha, "i25 Asha"))
		self.assertEqual(tasks.update(t, {"delegated_to": asha})["delegated_to"], asha)
		other = self.make("Life Person", space="Test Shared", full_name="i25 Elsewhere").name
		self.assertRaises(frappe.ValidationError, tasks.update, t, {"delegated_to": other})

	def test_8_the_family_user_sees_nothing_of_the_private_space(self):
		self.make("Life Person", full_name="i25 Secret")
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, people_api.list, space=PRIVATE)
