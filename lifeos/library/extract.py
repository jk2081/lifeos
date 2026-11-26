"""Read files locally before any model sees them (issue 104).

Every original attached to a capture or a Vault document is read here, on this server, and the words are written on the record:
`extracted_text`, `extracted_by`, `extract_confidence` (0 to 100), `extract_note` and `needs_closer_read`. `extract_files` keeps
the result of each file, so a file is read once. A background job on the `long` queue does it when the file arrives
(`file_attached`); a skill run that starts first reads what is not read yet (`ensure`) before it builds its request.

A tool that is not installed is skipped with a line in `extract_note` (never a crash). The model is asked only for what this cannot
read: `weak` files, whose confidence is under `Life Settings.extract_min_confidence`, or that gave nothing.

| File | Read with | `extracted_by` |
| --- | --- | --- |
| PDF with a text layer | pypdf | pypdf |
| PDF without text | OCRmyPDF (Tesseract) | ocrmypdf |
| Image | RapidOCR | rapidocr |
| Word, Excel | python-docx, openpyxl | docx, xlsx |
| Audio | faster-whisper (small, CPU) | whisper |
"""
import json
import os
import shutil
import subprocess
import tempfile

import frappe
from frappe import _

from lifeos.library import files

MAX_BYTES = 50 * 1024 * 1024
MAX_AUDIO_SECONDS = 60 * 60
TEXT_PER_PAGE = 20  # characters a page must hold to count as a text page
DEFAULT_MIN_CONFIDENCE = 60
TEXT_CAP = 200_000  # characters kept on a record
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic")
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".flac", ".webm", ".amr")
LANGUAGES = ("eng", "hin", "ben")  # the packs OCRmyPDF uses when they are installed
DOCTYPES = ("Life Inbox Item", "Life Vault Document")
WHISPER_MODEL = "small"
_engines = {}  # the loaded OCR engine and speech model, kept for the life of the worker


class Skipped(Exception):
	"""A file that is not read, with the line to write on the record."""


def min_confidence() -> int:
	value = frappe.db.get_single_value("Life Settings", "extract_min_confidence")
	return int(value) if value else DEFAULT_MIN_CONFIDENCE


def kind_of(file_name: str) -> str | None:
	low = (file_name or "").lower()
	if low.endswith(".pdf"):
		return "pdf"
	if low.endswith(IMAGE_EXT):
		return "image"
	if low.endswith((".docx",)):
		return "docx"
	if low.endswith((".xlsx", ".xlsm")):
		return "xlsx"
	if low.endswith(AUDIO_EXT):
		return "audio"
	return None


# ---------- the readers: each returns (text, by, confidence 0-100) or raises Skipped ----------

def read_pdf(path):
	from pypdf import PdfReader

	try:
		pages = [(p.extract_text() or "").strip() for p in PdfReader(path).pages]
	except Exception as e:
		raise Skipped(_("The PDF could not be opened: {0}").format(str(e)[:120]))
	if pages and sum(len(p) for p in pages) >= TEXT_PER_PAGE * len(pages) * 0.5:
		return "\n\n".join(pages), "pypdf", 95
	return read_scanned_pdf(path)


def installed_languages() -> str:
	tesseract = shutil.which("tesseract")
	have = set()
	if tesseract:
		out = subprocess.run([tesseract, "--list-langs"], capture_output=True, text=True, timeout=30, check=False).stdout.split()
		have = set(out)
	return "+".join(code for code in LANGUAGES if code in have) or "eng"


def read_scanned_pdf(path):
	if not (shutil.which("tesseract") and shutil.which("ocrmypdf")):
		raise Skipped(_("Install tesseract-ocr and ocrmypdf to read scanned PDFs."))
	with tempfile.TemporaryDirectory() as work:
		sidecar, out = os.path.join(work, "text.txt"), os.path.join(work, "searchable.pdf")
		done = subprocess.run(["ocrmypdf", "--force-ocr", "--sidecar", sidecar, "-l", installed_languages(), "--output-type", "pdf", "--jobs", "1", path, out],
			capture_output=True, text=True, timeout=1500, check=False)
		if done.returncode != 0 or not os.path.exists(sidecar):
			raise Skipped(_("OCRmyPDF could not read it: {0}").format((done.stderr or "").strip()[-120:]))
		with open(sidecar, encoding="utf-8", errors="replace") as fh:  # nosemgrep: frappe-security-file-traversal -- the sidecar is a fixed name in a temporary folder this function made
			text = fh.read().strip()
	return text, "ocrmypdf", readable_share(text)


def readable_share(text) -> int:
	"""A stand-in for Tesseract's own score (OCRmyPDF does not return one): the share of words that are plain words (letters, maybe
	one mark at the end), scaled down for a very short text. Rubbish from a bad scan is mostly symbols and single letters."""
	words = (text or "").split()
	if not words:
		return 0
	plain = sum(1 for w in words if len(w.strip(".,;:!?()\"'-")) >= 2 and w.strip(".,;:!?()\"'-").replace("-", "").replace("'", "").isalnum())
	share = plain / len(words)
	return round(100 * share * min(1.0, len(words) / 8))


def read_image(path):
	try:
		from rapidocr_onnxruntime import RapidOCR
	except ImportError:
		raise Skipped(_("Install rapidocr-onnxruntime to read photos."))
	from PIL import Image, ImageOps

	try:
		with Image.open(path) as img:
			img = ImageOps.exif_transpose(img).convert("RGB")
			png = os.path.join(os.path.dirname(path), "ocr-input.png")
			img.save(png)
	except Exception:
		raise Skipped(_("The image could not be opened."))
	engine = _engines.get("rapidocr") or _engines.setdefault("rapidocr", RapidOCR())
	rows, _elapsed = engine(png)
	if not rows:
		return "", "rapidocr", 0
	weight = sum(max(len(r[1]), 1) for r in rows)
	score = sum(float(r[2]) * max(len(r[1]), 1) for r in rows) / weight
	return "\n".join(r[1] for r in rows), "rapidocr", round(100 * score)


def read_docx(path):
	try:
		import docx
	except ImportError:
		raise Skipped(_("Install python-docx to read Word files."))
	try:
		doc = docx.Document(path)
	except Exception:
		raise Skipped(_("The Word file could not be opened."))
	lines = [p.text for p in doc.paragraphs if p.text.strip()]
	for table in doc.tables:
		lines += ["\t".join(c.text.strip() for c in row.cells) for row in table.rows]
	return "\n".join(lines), "docx", 100


def read_xlsx(path):
	from openpyxl import load_workbook

	try:
		book = load_workbook(path, read_only=True, data_only=True)
	except Exception:
		raise Skipped(_("The spreadsheet could not be opened."))
	lines = []
	for sheet in book.worksheets:
		lines.append(f"# {sheet.title}")
		for row in sheet.iter_rows(values_only=True):
			cells = ["" if v is None else str(v) for v in row]
			if any(cells):
				lines.append("\t".join(cells))
			if sum(len(x) for x in lines) > TEXT_CAP:
				break
	book.close()
	return "\n".join(lines), "xlsx", 100


def audio_seconds(path):
	ffprobe = shutil.which("ffprobe")
	if not ffprobe:
		raise Skipped(_("Install ffmpeg to read audio."))
	out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60, check=False).stdout.strip()
	try:
		return float(out)
	except ValueError:
		raise Skipped(_("The audio could not be read."))


def decoded(path):
	"""The audio as 16 kHz mono samples, decoded by ffmpeg (faster-whisper's own decoder, PyAV, is not used: its newer releases changed the
	call faster-whisper makes)."""
	import numpy

	out = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-nostdin", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
		capture_output=True, timeout=1800, check=False)
	if out.returncode != 0 or not out.stdout:
		raise Skipped(_("The audio could not be decoded."))
	return numpy.frombuffer(out.stdout, dtype=numpy.float32)


def read_audio(path):
	try:
		from faster_whisper import WhisperModel
	except ImportError:
		raise Skipped(_("Install faster-whisper to turn speech into text."))
	if audio_seconds(path) > MAX_AUDIO_SECONDS:
		raise Skipped(_("Skipped: audio over 60 minutes."))
	model = _engines.get("model") or _engines.setdefault("model", WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8"))
	segments, _info = model.transcribe(decoded(path), vad_filter=True)
	rows = [s for s in segments if s.text.strip()]
	text = " ".join(s.text.strip() for s in rows)
	if not rows:
		return "", "whisper", 0
	import math

	score = sum(math.exp(s.avg_logprob) * (1 - s.no_speech_prob) for s in rows) / len(rows)
	return text, "whisper", round(100 * score)


READERS = {"pdf": read_pdf, "image": read_image, "docx": read_docx, "xlsx": read_xlsx, "audio": read_audio}


def read_file(file_doc) -> dict:
	"""Read one File. Returns {file, file_name, kind, ok, text, by, confidence, note}; never raises for a file that cannot be read."""
	kind = kind_of(file_doc.file_name)
	out = {"file": file_doc.name, "file_name": file_doc.file_name, "kind": kind, "ok": False, "text": "", "by": None, "confidence": 0, "note": None}
	if not kind:
		return out
	if (file_doc.file_size or 0) > MAX_BYTES:
		out["note"] = _("Skipped: {0} is over 50 MB.").format(file_doc.file_name)
		return out
	try:
		path = files.local_path(file_doc)
		with tempfile.TemporaryDirectory() as work:
			copy = os.path.join(work, "input" + os.path.splitext(file_doc.file_name or "")[1].lower())
			shutil.copyfile(path, copy)  # the readers work on a copy, in a folder of their own
			text, by, confidence = READERS[kind](copy)
	except Skipped as e:
		out["note"] = str(e)
		return out
	except Exception:
		frappe.log_error(title="Life OS could not read a file")
		out["note"] = _("{0} could not be read.").format(file_doc.file_name)
		return out
	text = (text or "").strip()
	out.update({"text": text[:TEXT_CAP], "by": by, "confidence": max(0, min(100, int(confidence))), "ok": bool(text)})
	if not text:
		out["note"] = _("Nothing readable was found in {0}.").format(file_doc.file_name)
	return out


# ---------- the record ----------

def entries(doc) -> dict:
	"""The saved results of a record's files, by File name."""
	try:
		return {e["file"]: e for e in json.loads(doc.get("extract_files") or "[]")}
	except ValueError:
		return {}


def originals(doctype, name):
	rows = files.attachments(doctype, name)
	return [f for f in rows if f.attached_to_field not in ("preview_image", "thumbnail")]


def is_weak(entry, floor=None) -> bool:
	"""True when a model must look at the file: it gave no words, or fewer than the floor's share of them could be trusted."""
	return entry.get("kind") is not None and (not entry.get("ok") or entry.get("confidence", 0) < (floor if floor is not None else min_confidence()))


def run(doctype: str, name: str, force: bool = False):
	"""Read the files of one record that are not read yet, and write the text on the record. Returns the entries."""
	if doctype not in DOCTYPES or not frappe.db.exists(doctype, name):
		return {}
	doc = frappe.get_doc(doctype, name)
	have = {} if force else entries(doc)
	current = {}
	for row in originals(doctype, name):
		current[row.name] = have.get(row.name) or read_file(frappe.get_doc("File", row.name))
	floor = min_confidence()
	listed = [e for e in current.values() if e.get("kind")]
	good = [e for e in listed if e["ok"]]
	notes = [e["note"] for e in listed if e.get("note")]
	values = {
		"extracted_text": "\n\n".join(f"{e['file_name']}\n{e['text']}" if len(listed) > 1 else e["text"] for e in good)[:TEXT_CAP] or None,
		"extracted_by": ", ".join(dict.fromkeys(e["by"] for e in good)) or None,
		"extract_confidence": min((e["confidence"] for e in good), default=0),
		"extract_note": "\n".join(dict.fromkeys(notes))[:1000] or None,
		"needs_closer_read": 1 if any(is_weak(e, floor) for e in listed) else 0,
		"extract_files": json.dumps([{k: v for k, v in e.items()} for e in current.values()], ensure_ascii=False),
	}
	if doc.get("extracted_text") == values["extracted_text"] and doc.get("extract_files") == values["extract_files"]:
		return current
	frappe.db.set_value(doctype, name, values, update_modified=False)
	doc.update(values)
	after_read(doc)
	return current


def after_read(doc):
	"""The text is searchable: the capture's search text and Global Search. A Vault document is searched by Global Search only, which
	asks `has_permission` of each hit; its text is not written to Life Index, which Ask reads."""
	from frappe.utils.global_search import sync_global_search, update_global_search

	from lifeos.library import globalsearch, index

	if doc.doctype == "Life Inbox Item":
		index.update(doc)
	update_global_search(doc)  # the values were written without a save, so Frappe's own hook did not queue the record
	globalsearch.index_soon(doc)
	if frappe.flags.in_test or getattr(frappe.local, "request", None):
		return
	sync_global_search()  # in the background job: write the queue now, so the text is found as soon as it is read, not after a second job


def ensure(doctype, name):
	"""What a model run needs: the files of the record read, now, if the job has not yet. Returns the entries by File name."""
	if doctype not in DOCTYPES:
		return {}
	doc = frappe.get_doc(doctype, name)
	have = entries(doc)
	if all(f.name in have for f in originals(doctype, name)):
		return have
	return {e["file"]: e for e in run(doctype, name).values()}


def file_attached(file_doc, method=None):
	"""A File was attached to a capture or a Vault document: read it in a background job (the long queue). In a test, a test calls `run`."""
	if file_doc.attached_to_doctype not in DOCTYPES or file_doc.is_folder or file_doc.attached_to_field in ("preview_image", "thumbnail"):
		return
	if kind_of(file_doc.file_name) is None or frappe.flags.lifeos_no_extract or frappe.flags.in_test and not frappe.flags.lifeos_extract_in_test:
		return  # lifeos_no_extract: an ID card saved to the Vault from the chat, whose text holds the full number (issue 120)
	frappe.enqueue("lifeos.library.extract.run", queue="long", timeout=3600, enqueue_after_commit=True,
		doctype=file_doc.attached_to_doctype, name=file_doc.attached_to_name)


def of_item(item) -> dict:
	"""What an agent claiming a capture is told of the local reading: the text, how it was read, whether a closer read is needed, and
	whether some file is not read yet."""
	have = entries(item)
	return {"extracted_text": item.get("extracted_text"), "extracted_by": item.get("extracted_by"), "extract_confidence": item.get("extract_confidence"),
		"extract_note": item.get("extract_note"), "needs_closer_read": bool(item.get("needs_closer_read")),
		"extraction_pending": any(f.name not in have and kind_of(f.file_name) for f in originals("Life Inbox Item", item.name))}
