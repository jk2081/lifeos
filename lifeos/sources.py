"""Sources (UX fixes, set 4): what kind of capture an inbox item is, original IDs from other systems, thumbnails."""
import io
import os
import shutil
import subprocess
import tempfile

import frappe
from frappe import _

from lifeos import files

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic")
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".flac", ".webm", ".amr")
DOC_EXT = (".pdf", ".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".txt", ".md", ".epub")
ARTICLE_EXT = (".html", ".htm", ".mhtml", ".webarchive")
BY_SOURCE_TYPE = {"Voice Note": "Voice", "Journal Photo": "Photo", "Email": "Email", "Email Digest": "Email Digest", "Web": "Article"}
THUMB_WIDTH = 480
OWN_FIELDS = ("preview_image", "thumbnail")  # files the app made from the original


def original_files(item_name):
	return [f for f in files.attachments("Life Inbox Item", item_name) if f.attached_to_field not in OWN_FIELDS]


def media_kind(source_type, file_names=(), source_url=None):
	"""Voice, Document, Photo, Article, Email, Email Digest or Text: from the source type, else from the first file."""
	if source_type in BY_SOURCE_TYPE:
		return BY_SOURCE_TYPE[source_type]
	for name in file_names:
		low = (name or "").lower()
		if low.endswith(AUDIO_EXT):
			return "Voice"
		if low.endswith(IMAGE_EXT):
			return "Photo"
		if low.endswith(ARTICLE_EXT):
			return "Article"
		if low.endswith(DOC_EXT) or "." in low:
			return "Document"
	if source_url and not file_names:
		return "Article"
	return "Text"


def set_media_kind(doc):
	names = [] if doc.is_new() else [f.file_name for f in original_files(doc.name)]
	doc.media_kind = media_kind(doc.source_type, names, doc.source_url)


def check_external_id(doc):
	"""An original ID is unique in a space for its system (an inbox item and a chat log are separate)."""
	if not doc.get("external_id"):
		doc.external_id = None
		return
	doc.external_id = doc.external_id.strip()[:255]
	doc.source_system = (doc.source_system or "").strip().lower()[:40] or None
	if not doc.source_system:
		frappe.throw(_("An external_id needs a source_system, for example gmail or claude."))
	other = frappe.db.get_value(doc.doctype, {"space": doc.space, "source_system": doc.source_system, "external_id": doc.external_id,
		"name": ["!=", doc.name or ""]})
	if other:
		frappe.throw(_("{0} already has {1} {2} from {3}.").format(doc.space, doc.doctype, doc.external_id, doc.source_system),
			frappe.DuplicateEntryError)


# ---------- thumbnails ----------

def make_thumbnail(file_doc):
	"""A copy about 480 px wide of a photo, or of a PDF's first page when pdftoppm is installed. Returns its URL or None."""
	low = (file_doc.file_name or "").lower()
	content = None
	if low.endswith(IMAGE_EXT) and not low.endswith(".heic"):
		content = files.read(file_doc)
	elif low.endswith(".pdf") and shutil.which("pdftoppm"):
		content = _pdf_first_page(files.read(file_doc))
	if not content:
		return None
	from PIL import Image, ImageOps

	img = ImageOps.exif_transpose(Image.open(io.BytesIO(content)))
	if img.width > THUMB_WIDTH:
		img = img.resize((THUMB_WIDTH, max(1, round(img.height * THUMB_WIDTH / img.width))))
	if img.mode not in ("RGB", "L"):
		img = img.convert("RGB")
	buf = io.BytesIO()
	img.save(buf, format="JPEG", quality=78)
	frappe.flags.lifeos_making_preview = True
	try:
		thumb = frappe.get_doc({
			"doctype": "File", "file_name": os.path.splitext(file_doc.file_name)[0] + "-thumb.jpg",
			"attached_to_doctype": file_doc.attached_to_doctype, "attached_to_name": file_doc.attached_to_name,
			"attached_to_field": "thumbnail", "is_private": 1, "content": buf.getvalue(),
		}).insert(ignore_permissions=True)
	finally:
		frappe.flags.lifeos_making_preview = False
	return thumb.file_url


def _pdf_first_page(pdf_bytes):
	with tempfile.TemporaryDirectory() as tmp:
		src = os.path.join(tmp, "in.pdf")
		with open(src, "wb") as fh:  # nosemgrep: frappe-security-file-traversal -- a fixed name in a temporary folder made here
			fh.write(pdf_bytes)
		try:
			subprocess.run(["pdftoppm", "-png", "-f", "1", "-l", "1", "-scale-to", str(THUMB_WIDTH * 2), src, os.path.join(tmp, "p")],
				check=True, timeout=60, capture_output=True)
		except Exception:
			return None
		pages = sorted(n for n in os.listdir(tmp) if n.startswith("p") and n.endswith(".png"))
		if not pages:
			return None
		with open(os.path.join(tmp, pages[0]), "rb") as fh:  # nosemgrep: frappe-security-file-traversal -- pdftoppm's own output in a temporary folder made here
			return fh.read()


def on_file_attached(file_doc):
	"""A new original on an inbox item: set its kind again and make a thumbnail if it has none."""
	item = file_doc.attached_to_name
	values = {}
	row = frappe.db.get_value("Life Inbox Item", item, ["source_type", "source_url", "thumbnail"], as_dict=True)
	if not row:
		return
	kind = media_kind(row.source_type, [f.file_name for f in original_files(item)], row.source_url)
	values["media_kind"] = kind
	if not row.thumbnail:
		try:
			url = make_thumbnail(file_doc)
		except Exception:
			frappe.log_error(title="Life OS thumbnail failed")
			url = None
		if url:
			values["thumbnail"] = url
	frappe.db.set_value("Life Inbox Item", item, values, update_modified=False)
	from lifeos import index

	index.update(frappe.get_doc("Life Inbox Item", item))
