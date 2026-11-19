"""Issue 1: people and agents in one place. Members lists agents too; one method sets space access; Add member's role rule."""
import frappe

from lifeos import devtools, permissions
from lifeos.api import settings
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase

NEWCOMER = "issue1-newcomer@lifeos.test"
NEW_AGENT = "issue1-agent@lifeos.test"


class TestMembers(LifeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		for u in (NEWCOMER, NEW_AGENT):
			devtools.make_user(u, u.split("@")[0], [])
			doc = frappe.get_doc("User", u)
			doc.flags.ignore_permissions = True
			doc.remove_roles(*settings.LIFE_ROLES)
		for space in (PRIVATE, SHARED):
			doc = frappe.get_doc("Life Space", space)
			for m in [m for m in doc.members if m.user in (NEWCOMER, NEW_AGENT)]:
				doc.remove(m)
			doc.save(ignore_permissions=True)
		self.as_user(OWNER)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for u in (NEWCOMER, NEW_AGENT):
			for space in frappe.get_all("Life Space Member", filters={"user": u, "parenttype": "Life Space"}, pluck="parent"):
				doc = frappe.get_doc("Life Space", space)
				for m in [m for m in doc.members if m.user == u]:
					doc.remove(m)
				doc.save(ignore_permissions=True)
			frappe.delete_doc("User", u, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def space(self, name=PRIVATE):
		return next(s for s in settings.get(space=PRIVATE)["spaces"] if s["name"] == name)

	def test_get_lists_agents_in_members_with_is_agent(self):
		sp = self.space()
		rows = {m["user"]: m for m in sp["members"]}
		self.assertIn(AGENT, rows)
		self.assertTrue(rows[AGENT]["is_agent"])
		self.assertEqual(rows[AGENT]["kind"], "Agent")
		self.assertFalse(rows[OWNER]["is_agent"])
		self.assertEqual(rows[OWNER]["kind"], "Owner")
		self.assertEqual(sp["members"][0]["user"], OWNER)
		self.assertEqual((sp["people_count"], sp["agent_count"]), (1, 1))
		shared = {m["user"]: m["kind"] for m in self.space(SHARED)["members"]}
		self.assertEqual(shared[FAMILY], "Person")

	def test_agents_view_comes_from_the_same_rows(self):
		got = settings.get(space=PRIVATE)
		card = next(a for a in got["agents"] if a["user"] == AGENT)
		reach = {r["space"]: r["access"] for r in card["spaces"]}
		for sp in got["spaces"]:
			row = next((m for m in sp["members"] if m["user"] == AGENT), None)
			self.assertEqual(reach[sp["name"]], row["access"] if row else None)
		# a change made for the Agents view shows in Members, and back
		settings.set_member(PRIVATE, AGENT, "Read")
		self.assertEqual(next(m for m in self.space()["members"] if m["user"] == AGENT)["access"], "Read")
		card = next(a for a in settings.get(space=PRIVATE)["agents"] if a["user"] == AGENT)
		self.assertEqual(next(r for r in card["spaces"] if r["space"] == PRIVATE)["access"], "Read")
		settings.set_member(PRIVATE, AGENT, "Write")

	def test_only_life_admin_changes_members(self):
		for user in (FAMILY, AGENT):
			self.as_user(user)
			self.assertRaises(frappe.PermissionError, settings.set_member, SHARED, FAMILY, "Read")
			self.assertRaises(frappe.PermissionError, settings.set_member, SHARED, OWNER, remove=1)
			self.assertRaises(frappe.PermissionError, settings.find_users, "lifeos")
		self.as_user(OWNER)
		self.assertEqual(next(m for m in self.space(SHARED)["members"] if m["user"] == FAMILY)["access"], "Write")

	def test_the_owner_cannot_be_removed_or_lose_edit(self):
		self.assertRaises(frappe.ValidationError, settings.set_member, PRIVATE, OWNER, remove=1)
		self.assertRaises(frappe.ValidationError, settings.set_member, PRIVATE, OWNER, "Read")
		self.assertIn(OWNER, [m["user"] for m in self.space()["members"]])

	def test_an_agent_is_added_with_view_access_and_appears_at_once(self):
		out = settings.set_member(PRIVATE, NEW_AGENT, grant_role="Life Agent")
		row = next(m for m in out["members"] if m["user"] == NEW_AGENT)
		self.assertEqual((row["access"], row["is_agent"], row["kind"]), ("Read", True, "Agent"))
		self.assertTrue(permissions.is_agent(NEW_AGENT))
		self.assertIn(NEW_AGENT, [a["user"] for a in settings.get(space=PRIVATE)["agents"]])
		# an existing agent keeps its role and gets Read by default
		settings.set_member(SHARED, NEW_AGENT)
		self.assertEqual(next(m for m in self.space(SHARED)["members"] if m["user"] == NEW_AGENT)["access"], "Read")

	def test_a_person_gets_edit_access_by_default(self):
		settings.set_member(PRIVATE, NEWCOMER, grant_role="Life User")
		row = next(m for m in self.space()["members"] if m["user"] == NEWCOMER)
		self.assertEqual((row["access"], row["kind"]), ("Write", "Person"))

	def test_no_role_is_refused_until_the_owner_chooses_one(self):
		self.assertRaises(frappe.ValidationError, settings.set_member, PRIVATE, NEWCOMER)
		self.assertNotIn(NEWCOMER, [m["user"] for m in self.space()["members"]])
		self.assertFalse(set(frappe.get_roles(NEWCOMER)) & set(settings.LIFE_ROLES))

	def test_this_screen_never_gives_an_agent_life_user_or_life_admin(self):
		self.assertRaises(frappe.PermissionError, settings.set_member, PRIVATE, NEWCOMER, grant_role="Life Admin")
		self.assertRaises(frappe.PermissionError, settings.set_member, SHARED, AGENT, grant_role="Life User")
		self.assertRaises(frappe.PermissionError, settings.set_member, SHARED, AGENT, grant_role="Life Admin")
		self.assertEqual(set(frappe.get_roles(AGENT)) & set(settings.LIFE_ROLES), {"Life Agent"})
		self.assertFalse(set(frappe.get_roles(NEWCOMER)) & set(settings.LIFE_ROLES))

	def test_an_agent_cannot_own_a_space(self):
		self.assertRaises(frappe.ValidationError, settings.create_space, "Issue 1 agent space", owner_user=AGENT)
		self.assertFalse(frappe.db.exists("Life Space", "Issue 1 agent space"))

	def test_find_users_lists_people_and_agents_with_their_kind(self):
		found = {r["name"]: r for u in (AGENT, FAMILY, NEWCOMER, "Administrator") for r in settings.find_users(u, space=PRIVATE)}
		self.assertEqual(found[AGENT]["kind"], "Agent")
		self.assertTrue(found[AGENT]["is_member"])
		self.assertEqual(found[FAMILY]["kind"], "Person")
		self.assertFalse(found[FAMILY]["is_member"])
		self.assertIsNone(found[NEWCOMER]["kind"])
		self.assertNotIn("Administrator", found)
