"""File rules: lifeos attachments are private, and images on inbox items get one preview of at most 1600 px.

Issue 7: a file attached to a Life OS record is stored once per space, by its SHA-256 (`life_sha256`). Each record that
uses it has its own File row (the link), and all those rows share one `file_url`, so one copy sits on disk. The same bytes
in another space are stored again. An inbox item with an `external_id` keeps an earlier file of the same name as an earlier
version (`life_version_of` names the current row) instead of as a second attachment."""
import hashlib
import io
import mimetypes
import os

import frappe

from lifeos.constants import SPACE_DOCTYPES

PREVIEW_MAX = 1600
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")


def after_insert(doc, method=None):
	if not (doc.attached_to_doctype or "").startswith("Life ") or doc.is_folder:
		return
	if not doc.is_private:
		frappe.throw(frappe._("Files attached to Life OS records must be private."))
	if doc.attached_to_doctype != "Life Inbox Item" or frappe.flags.lifeos_making_preview:
		return
	if not doc.attached_to_field and keep_earlier_versions(doc):
		_drop_derived(doc.attached_to_name)
	from lifeos import sources

	sources.on_file_attached(doc)
	if not (doc.file_name or "").lower().endswith(IMAGE_EXT):
		return
	if frappe.db.get_value("Life Inbox Item", doc.attached_to_name, "preview_image"):
		return
	try:
		url = make_preview(doc)
	except Exception:
		frappe.log_error(title="Life OS preview failed")
		return
	if url:
		frappe.db.set_value("Life Inbox Item", doc.attached_to_name, "preview_image", url, update_modified=False)


def make_preview(file_doc):
	from PIL import Image, ImageOps

	content = read(file_doc)
	img = Image.open(io.BytesIO(content))
	img = ImageOps.exif_transpose(img)
	if max(img.size) <= PREVIEW_MAX and (file_doc.file_name or "").lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
		return file_doc.file_url  # small enough to show as it is
	img.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
	if img.mode not in ("RGB", "L"):
		img = img.convert("RGB")
	buf = io.BytesIO()
	img.save(buf, format="JPEG", quality=82)
	frappe.flags.lifeos_making_preview = True
	try:
		preview = frappe.get_doc({
			"doctype": "File", "file_name": os.path.splitext(file_doc.file_name)[0] + "-preview.jpg",
			"attached_to_doctype": file_doc.attached_to_doctype, "attached_to_name": file_doc.attached_to_name,
			"attached_to_field": "preview_image", "is_private": 1, "content": buf.getvalue(),
		}).insert(ignore_permissions=True)
	finally:
		frappe.flags.lifeos_making_preview = False
	return preview.file_url


def local_path(file_doc) -> str:
	"""The real path of a File record on disk, refused unless it lies inside the site's private or public files folder.
	Every read of an original goes through here, so a crafted file_url (`../`, a link out of the folder) reads nothing."""
	from frappe import _

	path = os.path.realpath(file_doc.get_full_path())
	for folder in (frappe.get_site_path("private", "files"), frappe.get_site_path("public", "files")):
		root = os.path.realpath(folder)
		if os.path.commonpath([path, root]) == root and path != root:
			return path
	frappe.throw(_("{0} is not a file of this site.").format(file_doc.file_url or file_doc.name), frappe.PermissionError)


def read(file_doc) -> bytes:
	"""The bytes of a File record, from inside the site's files folders only."""
	with open(local_path(file_doc), "rb") as fh:  # nosemgrep: frappe-security-file-traversal -- local_path keeps the path inside the site's files folders
		return fh.read()


def attachments(doctype, name, exclude_field=("preview_image", "thumbnail")):
	"""Files attached to a record, with sizes. The preview and thumbnail the app made are left out. Earlier versions are
	not listed on their own: each current file carries them in `versions`, newest first."""
	rows = frappe.get_all(
		"File", filters={"attached_to_doctype": doctype, "attached_to_name": name},
		fields=["name", "file_name", "file_url", "file_size", "attached_to_field", "creation", "life_version_of"],
		order_by="creation asc",
	)
	exclude = (exclude_field,) if isinstance(exclude_field, str) else tuple(exclude_field or ())
	current = [r for r in rows if r.attached_to_field not in exclude and not r.life_version_of]
	by_name = {r.name: r for r in current}
	for r in current:
		r.versions = []
	for r in reversed(rows):
		if r.life_version_of in by_name:
			by_name[r.life_version_of].versions.append(r)
	return current


# ---------- issue 7: one stored file per space, by content ----------

def sha256(content) -> str:
	if isinstance(content, str):
		content = content.encode()
	return hashlib.sha256(content).hexdigest()


def stored_bytes(file_name, content):
	"""The bytes Frappe will keep for an upload: a JPEG loses its EXIF data when the site says so (File.save_file)."""
	if isinstance(content, str):
		content = content.encode()
	if mimetypes.guess_type(file_name or "")[0] == "image/jpeg" and frappe.get_system_settings("strip_exif_metadata_from_uploaded_images"):
		from frappe.utils.image import strip_exif_data

		try:
			return strip_exif_data(content, "image/jpeg")
		except Exception:
			return content  # not a readable JPEG: Frappe's own save fails or keeps it as it is
	return content


def record_space(doctype, name):
	"""The space of the Life OS record a file is attached to, or None for anything else."""
	if doctype not in SPACE_DOCTYPES or not name:
		return None
	return frappe.db.get_value(doctype, name, "space")


def same_in_space(space, digest, is_private=1):
	"""A File row in this space whose stored bytes have this SHA-256, still on disk and readable by the user."""
	if not space or not digest:
		return None
	rows = frappe.get_all("File", filters={"life_sha256": digest, "is_private": is_private, "attached_to_doctype": ["in", SPACE_DOCTYPES]},
		fields=["name", "file_url", "content_hash", "file_size", "attached_to_doctype", "attached_to_name"], order_by="creation asc")
	for r in rows:
		if record_space(r.attached_to_doctype, r.attached_to_name) != space:
			continue
		doc = frappe.get_doc("File", r.name)
		if doc.exists_on_disk() and doc.has_permission("read"):
			return r
	return None


def same_on_record(doctype, name, digest, fieldname=None):
	"""The current File row on this record that holds these bytes, if any: the same file sent again is not attached twice."""
	if not digest:
		return None
	return frappe.db.get_value("File", {"attached_to_doctype": doctype, "attached_to_name": name, "life_sha256": digest,
		"attached_to_field": fieldname or ["is", "not set"], "life_version_of": ["is", "not set"]})


class LifeFile:
	"""Mixed into Frappe's File (hooks: extend_doctype_class). Changes only files attached to Life OS records."""

	def save_file(self, content=None, decode=False, ignore_existing_file_check=False, overwrite=False):
		if overwrite or ignore_existing_file_check or self.attached_to_doctype not in SPACE_DOCTYPES or self.is_remote_file:
			return super().save_file(content, decode, ignore_existing_file_check, overwrite)
		if self.file_url and self.exists_on_disk():
			# a new link to a file already stored (a proposal's record gets its inbox item's file)
			result = super().save_file(content, decode, ignore_existing_file_check, overwrite)
			self.life_sha256 = sha256(read(self))
			return result
		if content:
			self.content, self.decode = content, decode
		data = self.get_content()
		if not data:
			return super().save_file(None, False, ignore_existing_file_check, overwrite)
		data = stored_bytes(self.file_name, data)
		self.content, self._content, self.decode = data, data, False
		self.life_sha256 = sha256(data)
		# Frappe's own reuse looks across the whole site by MD5; ours stays inside the space, by SHA-256
		self.flags.ignore_duplicate_entry_error = True
		same = same_in_space(record_space(self.attached_to_doctype, self.attached_to_name), self.life_sha256, self.is_private)
		if same:
			self.file_url, self.content_hash = same.file_url, same.content_hash
			self.file_size = self.check_max_file_size()
			self.content_type = mimetypes.guess_type(self.file_name)[0]
			return {"file_name": self.file_name, "file_url": self.file_url}
		shown = self.file_name
		result = super().save_file(None, False, ignore_existing_file_check=True)
		self.file_name = shown  # the name it was sent with; the stored name (file_url) may carry a suffix
		return result

	def _delete_file_on_disk(self):
		"""Delete the stored copy only when no other File row points to it. Frappe's own check compares MD5s, which two
		spaces' copies of the same bytes share while their paths differ."""
		if self.attached_to_doctype not in SPACE_DOCTYPES or not self.file_url:
			return super()._delete_file_on_disk()
		shared = frappe.get_all("File", filters={"file_url": self.file_url, "name": ["!=", self.name]}, limit=1)
		self.delete_file_data_content(only_thumbnail=bool(shared))

	def on_trash(self):
		super().on_trash()
		if self.attached_to_doctype in SPACE_DOCTYPES and not self.life_version_of:
			_promote_latest_version(self.name)


def keep_earlier_versions(doc) -> bool:
	"""A new file on an inbox item with an external_id: an earlier current file of the same name with other bytes becomes an
	earlier version of it. Returns True when it did."""
	if not doc.life_sha256 or not frappe.db.get_value("Life Inbox Item", doc.attached_to_name, "external_id"):
		return False
	older = frappe.get_all("File", filters={"attached_to_doctype": "Life Inbox Item", "attached_to_name": doc.attached_to_name,
		"file_name": doc.file_name, "name": ["!=", doc.name], "attached_to_field": ["is", "not set"],
		"life_version_of": ["is", "not set"], "life_sha256": ["!=", doc.life_sha256]}, pluck="name")
	if not older:
		return False
	earlier = frappe.get_all("File", filters={"life_version_of": ["in", older]}, pluck="name")
	for name in older + earlier:
		frappe.db.set_value("File", name, "life_version_of", doc.name, update_modified=False)
	return True


def _promote_latest_version(name):
	"""The current file was removed: its newest earlier version becomes the current one."""
	earlier = frappe.get_all("File", filters={"life_version_of": name}, pluck="name", order_by="creation desc")
	if not earlier:
		return
	frappe.db.set_value("File", earlier[0], "life_version_of", None, update_modified=False)
	for other in earlier[1:]:
		frappe.db.set_value("File", other, "life_version_of", earlier[0], update_modified=False)


def _drop_derived(item):
	"""A new version replaced an original: the preview and thumbnail made from the old one go, so new ones are made."""
	originals = {f.file_url for f in attachments("Life Inbox Item", item)}
	for row in frappe.get_all("File", filters={"attached_to_doctype": "Life Inbox Item", "attached_to_name": item,
			"attached_to_field": ["in", ("preview_image", "thumbnail")]}, fields=["name", "file_url"]):
		if row.file_url not in originals:
			frappe.delete_doc("File", row.name, ignore_permissions=True, force=True)
	frappe.db.set_value("Life Inbox Item", item, {"preview_image": None, "thumbnail": None}, update_modified=False)


@frappe.whitelist(methods=["POST"])
def upload_file():
	"""Frappe's upload_file (hooks: override_whitelisted_methods), except that the same bytes sent again to the same Life OS
	record answer with the File already there instead of attaching a second copy."""
	from frappe import handler

	form = frappe.form_dict
	upload = frappe.request.files.get("file") if frappe.request else None
	if (form.doctype not in SPACE_DOCTYPES or not form.docname or not upload or form.get("chunk_index") is not None
			or form.method or form.optimize or form.get("library_file_name")):
		return handler.upload_file()
	handler.check_write_permission(form.doctype, form.docname)
	content = upload.stream.read()
	upload.stream.seek(0)
	same = same_on_record(form.doctype, form.docname, sha256(stored_bytes(upload.filename, content)), form.fieldname)
	if same:
		return frappe.get_doc("File", same)
	return handler.upload_file()
