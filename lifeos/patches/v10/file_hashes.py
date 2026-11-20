"""Issue 7: give every stored file of a Life OS record its SHA-256, so a file sent again is found and linked instead of stored
twice. Files already duplicated stay as they are (merging them is issue 9). Safe to run again: rows with a hash are skipped."""
import hashlib

import frappe

from lifeos.constants import SPACE_DOCTYPES
from lifeos.install import make_file_fields

CHUNK = 1 << 20


def execute():
	make_file_fields()
	from lifeos import files

	for row in frappe.get_all("File", filters={"attached_to_doctype": ["in", SPACE_DOCTYPES], "is_folder": 0,
			"life_sha256": ["is", "not set"], "file_url": ["like", "/private/files/%"]}, pluck="name"):
		doc = frappe.get_doc("File", row)
		try:
			path = files.local_path(doc)
			digest = hashlib.sha256()
			with open(path, "rb") as fh:  # nosemgrep: frappe-security-file-traversal -- local_path keeps the path inside the site's files folders
				for block in iter(lambda: fh.read(CHUNK), b""):
					digest.update(block)
		except (OSError, frappe.PermissionError):
			continue  # missing on disk, or outside the files folders: left without a hash
		frappe.db.set_value("File", row, "life_sha256", digest.hexdigest(), update_modified=False)
