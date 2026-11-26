"""Files put in the chat (issue 120).

Each file is uploaded private and loose, then comes here with the owner's message. It is read on this server first (`lifeos.library.extract`: text,
OCR, speech), before any model. Then:

- an ID document (PAN, Aadhaar, passport, licence, bank KYC), found by `idcards` patterns, is saved to the Vault with its holder, type, the last four
  characters and the expiry. The full number is not kept anywhere and the model is told only "PAN, Jai, ••••123F". When the page does not say whose card
  it is, the owner is asked once, with tappable answers (`answer_card`), and it is saved then.
- any other file becomes a capture (an inbox item), and the Brain files it as it files everything: a bill to Library with its date, a drawing to its
  company page. The model is given the file's text (cut short) so the chat can answer about it.

`process` returns what the model is told (`block`), the lines of the answer's Done list (`lines`), and the questions that wait (`pending`). Plumbing only:
what to do with a bill is the Brain's skill, not decided here.
"""
import json

import frappe
from frappe import _

from lifeos import permissions
from lifeos.ai import idcards
from lifeos.library import extract, files
from lifeos.web.pane_refs import ref_of

TEXT_FOR_MODEL = 6000  # characters of a file's text the model is given
MAX_FILES = 10


def loose_files(names) -> list:
	"""The File records the owner uploaded for this message: theirs, private and attached to nothing yet."""
	out = []
	for name in (names or [])[:MAX_FILES]:
		doc = frappe.get_doc("File", name)
		if doc.owner != frappe.session.user or not doc.is_private or doc.attached_to_doctype or doc.is_folder:
			raise frappe.PermissionError(_("That file is not yours to add."))
		out.append(doc)
	return out


def people_in(space: str, text: str) -> list[dict]:
	"""The people of the space whose name (or another name they go by) is written in `text`."""
	low = (text or "").lower()
	found = []
	for p in frappe.get_all("Life Person", filters={"space": space, "is_archived": 0}, fields=["name", "full_name", "aliases", "user"], limit=500):
		names = [p.full_name, *[a.strip() for a in (p.aliases or "").replace("\n", ",").split(",")]]
		if any(n and len(n) > 2 and n.lower() in low for n in names):
			found.append(p)
	return found


def holder_options(space: str) -> list[dict]:
	"""The answers offered when whose card it is cannot be told: the people of the space, the person the owner is first."""
	rows = frappe.get_all("Life Person", filters={"space": space, "is_archived": 0, "kind": ["!=", "Organisation"]}, fields=["name", "full_name", "user"], limit=12, order_by="modified desc")
	rows.sort(key=lambda r: r.user != frappe.session.user)
	return [{"label": r.full_name, "value": r.name} for r in rows]


def _line(kind, text, doctype=None, name=None) -> dict:
	return {"text": text, "kind": kind, "undo": None, "undone": 0, "doctype": doctype, "name": name, "pane": ref_of(doctype, name) if doctype and name else None}


def save_card(space: str, file_doc, card: dict, holder: str | None) -> dict:
	"""The Vault document for an ID card: type, holder, last four characters, expiry, and the file itself, private. Returns the Done line."""
	holder_name = frappe.db.get_value("Life Person", holder, "full_name") if holder else None
	title = f"{card['type']}, {holder_name}" if holder_name else card["type"]
	doc = frappe.get_doc({"doctype": "Life Vault Document", "space": space, "title": title, "doc_type": card["doc_type"], "holder": holder, "number_last4": card["last4"],
		"expiry_date": card.get("expiry")})
	doc.insert()
	content = files.read(file_doc)
	frappe.flags.lifeos_no_extract = True  # its text holds the full number: it is not read onto the record
	try:
		new = frappe.get_doc({"doctype": "File", "file_name": file_doc.file_name, "attached_to_doctype": "Life Vault Document", "attached_to_name": doc.name,
			"attached_to_field": "file", "is_private": 1, "content": content}).insert()
	finally:
		frappe.flags.lifeos_no_extract = False
	doc.db_set({"file": new.file_url, "extract_files": json.dumps([{"file": new.name, "file_name": new.file_name, "kind": None, "ok": False, "text": "", "by": None, "confidence": 0, "note": None}])},
		update_modified=False)
	frappe.delete_doc("File", file_doc.name, force=True, ignore_permissions=True)  # system: the loose upload was the person's own; its content now sits on the Vault document
	return _line("vault", _line_text(card, holder_name, True), "Life Vault Document", doc.name)


def _line_text(card, holder_name, saved) -> str:
	bits = [b for b in (holder_name, idcards.shown(card["last4"])) if b]
	if card.get("expiry"):
		bits.append(f"expires {frappe.utils.formatdate(card['expiry'], 'MMMM yyyy')}, reminder added")
	return f"{card['type']} ({', '.join(bits)})"


def save_capture(space: str, file_doc, message: str) -> dict:
	"""Any other file: a capture of its own for the Brain to file. Returns the Done line and the text read from it."""
	from lifeos.api import inbox

	kind = extract.kind_of(file_doc.file_name)
	item = inbox.create_item(title=file_doc.file_name[:140], source_type="Voice Note" if kind == "audio" else "Upload", space=space, instruction=(message or "")[:500] or None,
		source_system=None, intent="Process")
	content = files.read(file_doc)
	frappe.get_doc({"doctype": "File", "file_name": file_doc.file_name, "attached_to_doctype": "Life Inbox Item", "attached_to_name": item["name"], "is_private": 1, "content": content}).insert()
	frappe.delete_doc("File", file_doc.name, force=True, ignore_permissions=True)  # system: the loose upload was the person's own; its content now sits on the capture
	return _line("file", f"{file_doc.file_name}: sent to the Brain, which files it", "Life Inbox Item", item["name"])


def process(space: str, message: str, names) -> dict:
	"""Read each file, then save it where it belongs. Returns {block, lines, pending}."""
	permissions.require_space(space, write=True)
	block, lines, pending = [], [], []
	people = people_in(space, message)
	for f in loose_files(names):
		read = extract.read_file(f)
		card = idcards.detect(read["text"]) if read["text"] else None
		if card:
			who = [p.name for p in people_in(space, read["text"])] or [p.name for p in people]
			options = holder_options(space)
			if not who and len(options) <= 1:  # nobody to choose from: the card is the owner's, or has no holder
				who = [o["value"] for o in options] or [None]
			if len(who) == 1:
				line = save_card(space, f, card, who[0])
				lines.append(line)
				block.append(f"File “{f.file_name}”: an ID document, saved to the Vault: {line['text']}. Its number is not available to you; do not ask for it.")
			else:
				pending.append({"file": f.name, "file_name": f.file_name, "card": card, "options": options,
					"text": _("Whose {0} is this?").format(card["type"])})
				block.append(f"File “{f.file_name}”: an ID document ({card['type']}, {idcards.shown(card['last4'])}). Life OS is asking the owner whose it is; say nothing more about it.")
			continue
		line = save_capture(space, f, message)
		lines.append(line)
		text = (read["text"] or "")[:TEXT_FOR_MODEL]
		block.append(f"File “{f.file_name}”: sent to the Brain to file ({line['name']}). Its text, read here:\n{text}" if text else
			f"File “{f.file_name}”: sent to the Brain to file ({line['name']}). {read.get('note') or 'No text could be read from it.'}")
	return {"block": "\n\n".join(block), "lines": lines, "pending": pending}


def answer_card(space: str, pending: dict, holder: str) -> dict:
	"""The owner's tap on "Whose is this?": the card is saved with that holder. Returns the Done line."""
	permissions.require_space(space, write=True)
	if not frappe.db.exists("Life Person", {"name": holder, "space": space}):
		frappe.throw(_("That person is not in this space."), frappe.PermissionError, title=_("Person not found"))
	f = loose_files([pending["file"]])[0]
	return save_card(space, f, pending["card"], holder)
