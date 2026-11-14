import frappe

from lifeos import permissions
from lifeos.tests.base import AGENT, FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase


class TestSpacePermissions(LifeTestCase):
	def setUp(self):
		super().setUp()
		self.private_note = self.make("Life Note", title="Private note about tea", content_md="secret garden")
		self.shared_note = self.make("Life Note", space=SHARED, title="Shared shopping note")

	def test_member_can_list_and_read(self):
		names = frappe.get_list("Life Note", pluck="name", limit=0)
		self.assertIn(self.private_note.name, names)
		self.assertIn(self.shared_note.name, names)

	def test_outsider_cannot_list(self):
		self.as_user(FAMILY)
		names = frappe.get_list("Life Note", pluck="name", limit=0)
		self.assertNotIn(self.private_note.name, names)
		self.assertIn(self.shared_note.name, names)
		self.assertNotIn(PRIVATE, frappe.get_list("Life Space", pluck="name", limit=0))
		self.assertEqual(frappe.get_list("Life Area", filters={"space": PRIVATE}, pluck="name"), [])
		self.assertEqual(frappe.get_list("Life Index", filters={"space": PRIVATE}, pluck="name"), [])

	def test_outsider_cannot_read(self):
		self.as_user(FAMILY)
		doc = frappe.get_doc("Life Note", self.private_note.name)
		self.assertFalse(doc.has_permission("read"))
		self.assertRaises(frappe.PermissionError, doc.check_permission, "read")
		self.assertRaises(frappe.PermissionError, permissions.get_doc_checked, "Life Note", self.private_note.name)
		self.assertRaises(frappe.PermissionError, frappe.client.get, "Life Note", self.private_note.name)

	def test_outsider_cannot_write_or_create(self):
		self.as_user(FAMILY)
		doc = frappe.get_doc("Life Note", self.private_note.name)
		doc.title = "Taken over"
		self.assertRaises(frappe.PermissionError, doc.save)
		new = frappe.get_doc({"doctype": "Life Note", "space": PRIVATE, "title": "Sneaked in"})
		self.assertRaises(frappe.PermissionError, new.insert)
		self.assertRaises(frappe.PermissionError, permissions.require_space, PRIVATE)

	def test_outsider_cannot_delete(self):
		self.as_user(FAMILY)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Life Note", self.private_note.name)

	def test_read_only_member_cannot_write(self):
		frappe.set_user("Administrator")
		space = frappe.get_doc("Life Space", SHARED)
		for m in space.members:
			if m.user == FAMILY:
				m.access = "Read"
		space.save()
		try:
			self.as_user(FAMILY)
			doc = frappe.get_doc("Life Note", self.shared_note.name)
			self.assertTrue(doc.has_permission("read"))
			doc.title = "Changed"
			self.assertRaises(frappe.PermissionError, doc.save)
			self.assertRaises(frappe.PermissionError, permissions.require_space, SHARED, True)
		finally:
			frappe.set_user("Administrator")
			space.reload()
			for m in space.members:
				if m.user == FAMILY:
					m.access = "Write"
			space.save()

	def test_record_cannot_move_space(self):
		self.private_note.space = SHARED
		self.assertRaises(frappe.ValidationError, self.private_note.save)

	def test_user_without_spaces_sees_nothing(self):
		from lifeos import devtools

		devtools.make_user("stranger@lifeos.test", "Stranger", ["Life User"])
		self.as_user("stranger@lifeos.test")
		self.assertEqual(frappe.get_list("Life Note", pluck="name"), [])
		self.assertEqual(frappe.get_list("Life Space", pluck="name"), [])


class TestAgentLimits(LifeTestCase):
	def test_agent_can_create_and_edit(self):
		self.as_user(AGENT)
		note = self.make("Life Note", title="Filed by Hermes")
		self.assertEqual(note.owner, AGENT)
		note.content_md = "more"
		note.save()

	def test_agent_cannot_delete(self):
		note = self.make("Life Note", title="Keep me")
		task = self.make("Life Task", title="Keep me too")
		self.as_user(AGENT)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Life Note", note.name)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Life Task", task.name)
		self.assertTrue(frappe.db.exists("Life Note", note.name))

	def test_agent_cannot_change_spaces_or_members(self):
		self.as_user(AGENT)
		space = frappe.get_doc("Life Space", PRIVATE)
		space.append("members", {"user": FAMILY, "access": "Write"})
		self.assertRaises(frappe.PermissionError, space.save)
		new = frappe.get_doc({"doctype": "Life Space", "space_name": "Agent Space"})
		self.assertRaises(frappe.PermissionError, new.insert)
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "Life Space", SHARED)

	def test_agent_cannot_write_settings(self):
		self.as_user(AGENT)
		settings = frappe.get_doc("Life Settings")
		settings.score_target = 10
		self.assertRaises(frappe.PermissionError, settings.save)

	def test_family_user_cannot_change_spaces(self):
		self.as_user(FAMILY)
		space = frappe.get_doc("Life Space", SHARED)
		space.append("members", {"user": "stranger@lifeos.test", "access": "Write"})
		self.assertRaises(frappe.PermissionError, space.save)

	def test_owner_admin_can_manage_spaces(self):
		space = frappe.get_doc({"doctype": "Life Space", "space_name": "Anya's space", "owner_user": FAMILY}).insert()
		self.assertIn(FAMILY, [m.user for m in space.members])
		self.as_user(FAMILY)
		self.assertIn("Anya's space", permissions.user_spaces())
