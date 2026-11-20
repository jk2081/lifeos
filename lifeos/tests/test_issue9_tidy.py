"""Issue 9: the tidy command merges duplicate stored files, re-files old jobs and puts intent-refused items back to New."""
import os

import frappe
from frappe.core.doctype.file.utils import find_file_by_url
from frappe.core.doctype.file.utils import get_content_hash

from lifeos import files
from lifeos.api import inbox
from lifeos.tests.base import AGENT, OWNER, PRIVATE, SHARED, LifeTestCase
from lifeos.tools import tidy

DECK = b"issue 9 BTW standard deck"
PITCH = b"issue 9 Mehi Motors pitch"
NOTES = b"issue 9 Mehi brief notes"
REFUSAL = "submit_result refused: This item is to be kept only (intent Just keep). Send its text with no proposals."


def item(title, space=PRIVATE, **kw):
	return inbox.create_item(title=title, source_type="Upload", space=space, **kw)["name"]


def stored_twice(name, file_name, content, doctype="Life Inbox Item", hashed=True):
	"""A file stored the way it was before issue 7: its own copy on disk, whatever else holds the same bytes. Patch
	v10.file_hashes gave it its SHA-256 unless `hashed` is False."""
	stored = f"i9-{frappe.generate_hash(length=8)}-{file_name}"
	with open(frappe.get_site_path("private", "files", stored), "wb") as fh:
		fh.write(content)
	doc = frappe.get_doc({"doctype": "File", "file_name": file_name, "file_url": f"/private/files/{stored}", "is_private": 1,
		"attached_to_doctype": doctype, "attached_to_name": name})
	doc.flags.copy_from_existing_file = True
	doc.insert(ignore_permissions=True)
	frappe.db.set_value("File", doc.name, {"content_hash": get_content_hash(content), "file_size": len(content),
		"life_sha256": files.sha256(content) if hashed else None})
	return frappe.get_doc("File", doc.name)


def on_disk(url):
	return os.path.isfile(frappe.get_site_path(url.lstrip("/")))


def current(name):
	return frappe.get_all("File", filters={"attached_to_doctype": "Life Inbox Item", "attached_to_name": name,
		"attached_to_field": ["is", "not set"], "life_version_of": ["is", "not set"]}, fields=["name", "file_name", "file_url"])


class TestTidy(LifeTestCase):
	@classmethod
	def tearDownClass(cls):
		folder = frappe.get_site_path("private", "files")
		for name in os.listdir(folder):
			if name.startswith("i9-"):  # the copies seeded here; their rows are rolled back with the test
				os.remove(os.path.join(folder, name))
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.backups = []

	def tidy(self, apply=False, backup=None):
		return tidy.Tidy(apply=apply, spaces=[PRIVATE, SHARED], backup=backup or self.fake_backup).run()

	def fake_backup(self):
		self.backups.append(1)
		return ["fake-database.sql.gz", "fake-files.tar", "fake-private-files.tar"]

	def counts(self):
		disk = sorted(os.listdir(frappe.get_site_path("private", "files")))
		return {dt: frappe.db.count(dt) for dt in ("File", "Life Inbox Item", "Life Proposal", "Life Note", "Life Task", "Comment")} | {"disk": disk}

	def seed_duplicates(self, content=DECK):
		a, b = item("i9 Mehi deck"), item("i9 Arora deck")
		fa = stored_twice(a, "deck.txt", content)
		fb = stored_twice(b, "deck.txt", content)
		twin = stored_twice(b, "deck.txt", content, hashed=False)  # the same deck attached twice to one item
		other = stored_twice(item("i9 shared deck", space=SHARED), "deck.txt", content)  # another space keeps its own copy
		return a, b, fa, fb, twin, other

	def test_1_dry_run_reports_duplicates_and_changes_nothing(self):
		a, b, fa, fb, twin, _ = self.seed_duplicates()
		before = self.counts()
		report = self.tidy()
		self.assertFalse(report["applied"])
		groups = [g for g in report["duplicates"] if g["sha256"] == files.sha256(DECK)]
		self.assertEqual(len(groups), 1)  # one group per space with copies: the shared space has a single copy
		group = groups[0]
		self.assertEqual(group["keep"]["file_url"], fa.file_url)  # the oldest
		self.assertEqual({c["file_url"] for c in group["copies"]}, {fb.file_url, twin.file_url})
		self.assertIn(b, {r["name"] for c in group["copies"] for r in c["records"]})
		self.assertEqual([(t["name"], t["drop"]) for t in group["twins"]], [(b, twin.name)])
		self.assertEqual(self.counts(), before)
		self.assertEqual(self.backups, [])
		self.assertIn("Dry run", tidy.Tidy(spaces=[PRIVATE]).text(report))

	def test_2_apply_stores_each_file_once_and_every_record_still_opens_its_files(self):
		deck = DECK + b", merged"
		a, b, fa, fb, twin, other = self.seed_duplicates(deck)
		report = self.tidy(apply=True)
		self.assertTrue(report["applied"])
		self.assertEqual(self.backups, [1])
		rows = frappe.get_all("File", filters={"life_sha256": files.sha256(deck), "attached_to_name": ["in", [a, b]]},
			fields=["name", "file_url"])
		self.assertEqual({r.file_url for r in rows}, {fa.file_url})
		self.assertEqual(len(rows), 2)  # one row for each item: b's second row went
		self.assertFalse(frappe.db.exists("File", twin.name))
		for url in (fb.file_url, twin.file_url):
			self.assertFalse(on_disk(url))
		self.assertTrue(on_disk(fa.file_url) and on_disk(other.file_url))
		self.as_user(OWNER)
		for name in (a, b):
			shown = inbox._item_dict(frappe.get_doc("Life Inbox Item", name))["files"]
			self.assertEqual(len(shown), 1)
			opened = find_file_by_url(shown[0]["file_url"])  # what /private/files/... checks before it serves the file
			self.assertTrue(opened)
			self.assertEqual(files.read(opened), deck)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": b, "content": ["like", "Tidy:%"]}))

	def test_3_apply_moves_an_items_input_files_to_reusable_assets_and_keeps_its_outputs(self):
		asset = item("i9 BTW deck", intent="Just keep", source_system="hermes", external_id="i9-btw-standard-deck")
		stored_twice(asset, "BTW deck.txt", DECK)
		other_job = item("i9 Arora pitch", source_system="hermes", external_id="i9-arora")
		stored_twice(other_job, "brief notes.txt", NOTES)
		job = item("i9 Mehi Motors pitch", source_system="hermes", external_id="i9-mehi-motors")
		stored_twice(job, "BTW deck.txt", DECK)
		stored_twice(job, "brief notes.txt", NOTES)
		out = stored_twice(job, "Mehi pitch.txt", PITCH)
		report = self.tidy()
		found = next(j for j in report["jobs"] if j["item"] == job)
		self.assertEqual(sorted(f["file_name"] for f in found["inputs"]), ["BTW deck.txt", "brief notes.txt"])
		self.assertEqual([f["file_name"] for f in found["outputs"]], ["Mehi pitch.txt"])

		self.tidy(apply=True)
		doc = frappe.get_doc("Life Inbox Item", job)
		self.assertEqual([f.name for f in current(job)], [out.name])
		self.assertEqual(doc.job_id, "i9-mehi-motors")
		links = {r.label: r for r in doc.job_inputs}
		self.assertEqual(set(links), {"BTW deck.txt", "brief notes.txt"})
		self.assertEqual(links["BTW deck.txt"].asset, asset)  # the asset already kept
		made = links["brief notes.txt"].asset
		self.assertEqual(frappe.db.get_value("Life Inbox Item", made, ["intent", "external_id"]), ("Just keep", "brief-notes"))
		self.assertEqual(files.read(frappe.get_doc("File", current(made)[0].name)), NOTES)
		self.assertEqual(files.read(frappe.get_doc("File", current(asset)[0].name)), DECK)
		# the other job that had the notes is not a mixed job (no output), so it keeps its file
		self.assertEqual(len(current(other_job)), 1)

	def test_4_apply_puts_an_intent_refused_failed_item_back_to_new(self):
		refused = item("i9 refused deck", intent="Just keep", source_system="hermes", external_id="i9-refused")
		other = item("i9 other failure")
		frappe.db.set_value("Life Inbox Item", refused, {"status": "Failed", "error": REFUSAL})
		frappe.db.set_value("Life Inbox Item", other, {"status": "Failed", "error": "The PDF could not be read."})
		report = self.tidy()
		self.assertEqual([r["name"] for r in report["failed"]], [refused])
		self.tidy(apply=True)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", refused, ["status", "error"]), ("New", None))
		self.assertEqual(frappe.db.get_value("Life Inbox Item", other, "status"), "Failed")
		for name in frappe.get_all("Life Inbox Item", filters={"space": PRIVATE, "status": "New", "name": ["!=", refused]}, pluck="name"):
			frappe.db.set_value("Life Inbox Item", name, "status", "Done")  # so the claim below has only this one to take
		frappe.set_user(AGENT)
		self.assertEqual(inbox.claim_next(space=PRIVATE)["name"], refused)

	def test_5_apply_refuses_to_start_when_the_backup_fails(self):
		self.seed_duplicates()
		refused = item("i9 refused again")
		frappe.db.set_value("Life Inbox Item", refused, {"status": "Failed", "error": REFUSAL})
		before = self.counts()

		def broken():
			raise OSError("mysqldump: disk full")

		with self.assertRaises(tidy.TidyRefused):
			self.tidy(apply=True, backup=broken)
		self.assertEqual(self.counts(), before)
		self.assertEqual(frappe.db.get_value("Life Inbox Item", refused, "status"), "Failed")

	def test_6_running_apply_twice_changes_nothing_the_second_time(self):
		self.seed_duplicates(DECK + b", twice")
		job = item("i9 twice pitch", source_system="hermes")
		stored_twice(job, "deck.txt", DECK)
		stored_twice(job, "pitch.txt", PITCH + b", filed twice")
		refused = item("i9 twice refused")
		frappe.db.set_value("Life Inbox Item", refused, {"status": "Failed", "error": REFUSAL})
		first = self.tidy(apply=True)
		self.assertTrue(first["duplicates"] and first["jobs"] and first["failed"])
		before = self.counts()
		second = self.tidy(apply=True)
		self.assertEqual(second["summary"]["to_do"], 0)
		self.assertFalse(second["applied"])
		self.assertEqual(second["actions"], [])
		self.assertEqual(self.counts(), before)
		self.assertEqual(self.backups, [1])  # nothing to do: no second backup
