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

	content = file_doc.get_content()
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


def attachments(doctype, name, exclude_field="preview_image"):
	"""Files attached to a record, with sizes."""
	rows = frappe.get_all(
		"File", filters={"attached_to_doctype": doctype, "attached_to_name": name},
		fields=["name", "file_name", "file_url", "file_size", "attached_to_field", "creation"], order_by="creation asc",
	)
	return [r for r in rows if r.attached_to_field != exclude_field]
