"""Issue 7: a file is stored once per space, by its SHA-256, and an item filed again keeps earlier versions of its file."""
import io
import os

import frappe
from frappe.core.doctype.file.utils import find_file_by_url
from werkzeug.test import EnvironBuilder

from lifeos import files, trash
from lifeos.api import inbox
from lifeos.tests.base import FAMILY, OWNER, PRIVATE, SHARED, LifeTestCase

DECK = b"issue 7 standard deck, version one"


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


def rows(doctype, name):
	return frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name, "attached_to_field": ["is", "not set"]},
		fields=["name", "file_url", "life_sha256", "life_version_of"])


def on_disk(file_url):
	return os.path.exists(frappe.get_site_path(file_url.lstrip("/")))


class TestFilesOnce(LifeTestCase):
	def test_1_same_bytes_twice_in_one_space_is_one_stored_file_linked_to_both(self):
		a, b = item("i7 deck for Mehi"), item("i7 deck for Arora")
		fa = upload("Life Inbox Item", a, "BTW standard deck.txt", DECK)
		fb = upload("Life Inbox Item", b, "BTW standard deck.txt", DECK)
		self.assertNotEqual(fa.name, fb.name)  # one link per record
		self.assertEqual(fa.file_url, fb.file_url)  # one stored copy
		self.assertTrue(on_disk(fa.file_url))
		self.assertEqual(fa.life_sha256, files.sha256(DECK))
		self.assertEqual(frappe.db.count("File", {"life_sha256": files.sha256(DECK)}), 2)
		self.assertEqual(len({r.file_url for r in frappe.get_all("File", filters={"life_sha256": files.sha256(DECK)}, fields=["file_url"])}), 1)
		# the same file sent again to the same item is not attached a second time
		again = upload("Life Inbox Item", a, "BTW standard deck.txt", DECK)
		self.assertEqual(again.name, fa.name)
		self.assertEqual(len(rows("Life Inbox Item", a)), 1)
		self.assertEqual(len(inbox._item_dict(frappe.get_doc("Life Inbox Item", a))["files"]), 1)

	def test_2_same_bytes_in_two_spaces_are_stored_separately(self):
		a, b = item("i7 private copy"), item("i7 shared copy", space=SHARED)
		fa = upload("Life Inbox Item", a, "i7 scan.txt", DECK + b" two spaces")
		fb = upload("Life Inbox Item", b, "i7 scan.txt", DECK + b" two spaces")
		self.assertEqual(fa.life_sha256, fb.life_sha256)
		self.assertNotEqual(fa.file_url, fb.file_url)
		self.assertTrue(on_disk(fa.file_url) and on_disk(fb.file_url))

	def test_3_refiling_with_a_changed_file_of_the_same_name_keeps_one_current_file_and_one_earlier_version(self):
		ext = {"source_system": "hermes", "external_id": "i7-btw-standard-deck"}
		name = item("i7 BTW standard deck", **ext)
		first = upload("Life Inbox Item", name, "BTW standard deck.txt", DECK)
		self.assertEqual(item("i7 BTW standard deck", **ext), name)  # filed again: the same item
		second = upload("Life Inbox Item", name, "BTW standard deck.txt", DECK + b", version two")
		listed = files.attachments("Life Inbox Item", name)
		self.assertEqual([f.name for f in listed], [second.name])
		self.assertEqual([v.name for v in listed[0].versions], [first.name])
		self.assertEqual(frappe.db.get_value("File", first.name, "life_version_of"), second.name)
		self.assertEqual(files.read(frappe.get_doc("File", second.name)), DECK + b", version two")
		self.assertEqual(files.read(frappe.get_doc("File", first.name)), DECK)
		self.assertEqual(second.file_name, "BTW standard deck.txt")  # the name it was sent with, though stored under another
		shown = inbox._item_dict(frappe.get_doc("Life Inbox Item", name))["files"]
		self.assertEqual((len(shown), len(shown[0]["versions"])), (1, 1))
		# an item without an external_id keeps both as attachments
		plain = item("i7 plain item")
		upload("Life Inbox Item", plain, "notes.txt", b"one")
		upload("Life Inbox Item", plain, "notes.txt", b"two")
		self.assertEqual(len(files.attachments("Life Inbox Item", plain)), 2)

	def test_4_deleting_one_of_two_records_that_share_a_file_leaves_the_file_for_the_other(self):
		a = self.make("Life Note", title="i7 note one", content_md="x")
		b = self.make("Life Note", title="i7 note two", content_md="y")
		fa = upload("Life Note", a.name, "i7 shared.txt", DECK + b" shared")
		fb = upload("Life Note", b.name, "i7 shared.txt", DECK + b" shared")
		self.assertEqual(fa.file_url, fb.file_url)
		trash.delete("Life Note", a.name)
		frappe.db.after_commit.run()  # the disk is cleaned after the commit
		self.assertFalse(frappe.db.exists("File", fa.name))
		self.assertTrue(frappe.db.exists("File", fb.name))
		self.assertTrue(on_disk(fb.file_url))
		self.assertEqual(files.read(frappe.get_doc("File", fb.name)), DECK + b" shared")
		# the last record using it goes: so does the stored copy, though another space holds the same bytes
		other = upload("Life Inbox Item", item("i7 shared bytes elsewhere", space=SHARED), "i7 shared.txt", DECK + b" shared")
		trash.delete("Life Note", b.name)
		frappe.db.after_commit.run()
		self.assertFalse(on_disk(fb.file_url))
		self.assertTrue(on_disk(other.file_url))

	def test_5_a_user_who_cannot_see_either_record_cannot_download_the_file(self):
		a, b = item("i7 private one"), item("i7 private two")
		fa = upload("Life Inbox Item", a, "i7 private.txt", DECK + b" private")
		upload("Life Inbox Item", b, "i7 private.txt", DECK + b" private")
		self.as_user(OWNER)
		self.assertTrue(find_file_by_url(fa.file_url))
		self.as_user(FAMILY)  # not a member of the private space
		self.assertIsNone(find_file_by_url(fa.file_url))
		self.assertFalse(frappe.get_doc("File", fa.name).has_permission("read"))
		# the same bytes uploaded in a space the family member can see get their own copy, not a door to the private one
		mine = upload("Life Inbox Item", item("i7 family copy", space=SHARED), "i7 private.txt", DECK + b" private")
		self.assertNotEqual(mine.file_url, fa.file_url)
		self.assertIsNone(find_file_by_url(fa.file_url))
