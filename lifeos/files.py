"""File rules: lifeos attachments are private, and images on inbox items get one preview of at most 1600 px."""
import io
import os

import frappe

PREVIEW_MAX = 1600
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")


def after_insert(doc, method=None):
	if not (doc.attached_to_doctype or "").startswith("Life ") or doc.is_folder:
		return
	if not doc.is_private:
		frappe.throw("Files attached to Life OS records must be private.")
	if doc.attached_to_doctype != "Life Inbox Item" or frappe.flags.lifeos_making_preview:
		return
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
	"""Files attached to a record, with sizes. The preview and thumbnail the app made are left out."""
	rows = frappe.get_all(
		"File", filters={"attached_to_doctype": doctype, "attached_to_name": name},
		fields=["name", "file_name", "file_url", "file_size", "attached_to_field", "creation"], order_by="creation asc",
	)
	exclude = (exclude_field,) if isinstance(exclude_field, str) else tuple(exclude_field or ())
	return [r for r in rows if r.attached_to_field not in exclude]
