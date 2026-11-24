"""Issue 9: duplicate stored files. Files stored before issue 7 may hold the same bytes several times in one space, each under
its own path. The oldest copy still on disk is kept, every File row of the others is pointed at it, and the copies no File row
uses any more leave the disk. A record that held the same file twice keeps one File row."""
import hashlib
import os

import frappe

from lifeos.library import files
from lifeos.constants import SPACE_DOCTYPES

CHUNK = 1 << 20
TEXT_TYPES = ("Text", "Long Text", "Small Text", "Text Editor", "Markdown Editor", "HTML Editor", "Code", "JSON")
ATTACH_TYPES = ("Attach", "Attach Image")


class DuplicateFiles:
	def __init__(self, log, spaces):
		self.log, self.spaces = log, set(spaces)
		self._space_of = {}

	def find(self):
		"""Groups of File rows in one space with the same bytes, stored more than once or attached twice to one record."""
		groups = {}
		for row in self._rows():
			space = self._space(row)
			if space not in self.spaces:
				continue
			row.digest = row.life_sha256 or _hash_of(row.file_url)
			if row.digest:
				groups.setdefault((space, row.digest, row.is_private), []).append(row)
		out = []
		for (space, digest, _private), rows in groups.items():
			group = self._group(space, digest, rows)
			if group:
				out.append(group)
		return out

	def merge(self, group):
		"""Point every row at the kept copy, drop rows a record holds twice. Returns the copies that may leave the disk."""
		keep = group["keep"]
		for row in group["rows"]:
			if not row.life_sha256:
				frappe.db.set_value("File", row.name, "life_sha256", row.digest, update_modified=False)
		for copy in group["copies"]:
			if copy["used_in_text"]:
				continue
			for ref in copy["records"]:
				frappe.db.set_value("File", ref["file"], {"file_url": keep["file_url"], "content_hash": keep["content_hash"],
					"file_size": keep["file_size"]}, update_modified=False)
				self.log(ref["doctype"], ref["name"], f"File {ref['file']} now uses the stored copy {keep['file_url']} "
					f"instead of its duplicate {copy['file_url']}.")
			_rewrite_attach_fields(copy["file_url"], keep["file_url"])
		for twin in group["twins"]:
			self._drop_twin(twin)
		return [c["file_url"] for c in group["copies"] if not c["used_in_text"]]

	def remove_unused(self, urls):
		"""Delete stored copies that no File row points to any more."""
		removed = []
		for url in urls:
			if frappe.db.exists("File", {"file_url": url}):
				continue
			path = _path_of(url)
			if path and os.path.isfile(path):
				os.remove(path)
				removed.append(url)
				self.log(None, None, f"Removed the duplicate stored copy {url}.")
		return removed

	# ---------- finding ----------

	def _rows(self):
		return frappe.get_all("File", filters={"attached_to_doctype": ["in", SPACE_DOCTYPES], "is_folder": 0,
			"file_url": ["like", "%/files/%"]}, fields=["name", "file_name", "file_url", "content_hash", "file_size", "is_private",
			"attached_to_doctype", "attached_to_name", "attached_to_field", "life_sha256", "life_version_of", "creation"],
			order_by="creation asc, name asc")

	def _space(self, row):
		key = (row.attached_to_doctype, row.attached_to_name)
		if key not in self._space_of:
			self._space_of[key] = files.record_space(*key)
		return self._space_of[key]

	def _group(self, space, digest, rows):
		urls = list(dict.fromkeys(r.file_url for r in rows))  # oldest first
		keep_url = next((u for u in urls if _path_of(u) and os.path.isfile(_path_of(u))), None)
		if not keep_url:
			return None
		keep = next(r for r in rows if r.file_url == keep_url)
		copies = [{"file_url": u, "used_in_text": _used_in_text(u), "records": [_ref(r) for r in rows if r.file_url == u]}
			for u in urls if u != keep_url]
		left = {c["file_url"] for c in copies if c["used_in_text"]}
		twins = [t for t in _twins(rows) if t["drop_url"] not in left and t["keep_url"] not in left]
		if not copies and not twins:
			return None
		return {"space": space, "sha256": digest, "file_name": keep.file_name, "rows": rows,
			"keep": {"file": keep.name, "file_url": keep.file_url, "content_hash": keep.content_hash, "file_size": keep.file_size},
			"records": [_ref(r) for r in rows if r.file_url == keep_url], "copies": copies, "twins": twins}

	# ---------- merging ----------

	def _drop_twin(self, twin):
		"""A second current File row with the same bytes on one record: its versions and job inputs move to the first."""
		kept, extra = twin["keep"], twin["drop"]
		for name in frappe.get_all("File", filters={"life_version_of": extra}, pluck="name"):
			frappe.db.set_value("File", name, "life_version_of", kept, update_modified=False)
		for name in frappe.get_all("Life Job Input", filters={"file": extra}, pluck="name"):
			frappe.db.set_value("Life Job Input", name, "file", kept, update_modified=False)
		frappe.delete_doc("File", extra, ignore_permissions=True, force=True)  # system: developer, seed and maintenance tool; never reached by a person's request
		self.log(twin["doctype"], twin["name"], f"File {extra} was the same file as {kept} on this record; removed the second.")


def _ref(row):
	return {"doctype": row.attached_to_doctype, "name": row.attached_to_name, "file": row.name, "field": row.attached_to_field}


def _twins(rows):
	"""Current rows on one record and field that hold the same bytes: the first is kept."""
	seen, out = {}, []
	for row in rows:
		if row.life_version_of:
			continue
		key = (row.attached_to_doctype, row.attached_to_name, row.attached_to_field or "")
		if key in seen:
			first = seen[key]
			out.append({"doctype": key[0], "name": key[1], "keep": first.name, "keep_url": first.file_url, "drop": row.name,
				"drop_url": row.file_url})
		else:
			seen[key] = row
	return out


def _rewrite_attach_fields(old, new):
	"""Attach fields (a preview, a vault document's file) that name the old copy now name the kept one."""
	for doctype in SPACE_DOCTYPES:
		for field in frappe.get_meta(doctype).get("fields", {"fieldtype": ["in", ATTACH_TYPES]}):
			for name in frappe.get_all(doctype, filters={field.fieldname: old}, pluck="name"):
				frappe.db.set_value(doctype, name, field.fieldname, new, update_modified=False)


def _used_in_text(url):
	"""Records whose text names this stored copy, which would stop opening if it went: such a copy is left as it is."""
	used = []
	for doctype in SPACE_DOCTYPES:
		for field in frappe.get_meta(doctype).get("fields", {"fieldtype": ["in", TEXT_TYPES]}):
			used += [f"{doctype} {n}" for n in frappe.get_all(doctype, filters={field.fieldname: ["like", f"%{url}%"]}, pluck="name")]
	return used


def _path_of(url):
	"""The path of a stored copy inside the site's files folders, or None."""
	if not url or not url.startswith(("/private/files/", "/files/")):
		return None
	path = os.path.realpath(frappe.get_site_path(("public" + url) if url.startswith("/files/") else url.lstrip("/")))
	for folder in (frappe.get_site_path("private", "files"), frappe.get_site_path("public", "files")):
		root = os.path.realpath(folder)
		if os.path.commonpath([path, root]) == root and path != root:
			return path
	return None


def _hash_of(url):
	"""SHA-256 of a stored copy that has none yet (patch v10.file_hashes skipped it), or None when it cannot be read."""
	path = _path_of(url)
	if not path:
		return None
	digest = hashlib.sha256()
	try:
		with open(path, "rb") as fh:  # nosemgrep: frappe-security-file-traversal -- _path_of keeps the path inside the site's files folders
			for block in iter(lambda: fh.read(CHUNK), b""):
				digest.update(block)
	except OSError:
		return None
	return digest.hexdigest()
