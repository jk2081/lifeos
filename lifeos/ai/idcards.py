"""ID documents, recognised on this server by patterns (issue 120). A model is never asked.

A file the owner puts in the chat is read first (`lifeos.library.extract`). Its text is looked at here: a PAN, an Aadhaar number, a passport, a driving
licence or a bank KYC form is found by its number's shape and the words printed next to it. Only the type, the last four characters, the holder and the
expiry leave this module; the full number is never returned, stored or sent to a model. `mask` hides such numbers in any text that is about to go to a model.
"""
import re
from datetime import date

PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
AADHAAR = re.compile(r"(?<![\d])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![\d])")
PASSPORT = re.compile(r"\b[A-PR-WY][0-9]{7}\b")
LICENCE = re.compile(r"\b[A-Z]{2}[ -]?\d{2}[ -]?(?:19|20)\d{2}\d{7}\b")
ACCOUNT = re.compile(r"(?<![\d])\d{9,18}(?![\d])")

# type, number pattern, words that must be on the page (so a phone number or an invoice number is not taken for a card), the Vault's document type
KINDS = (
	("PAN", PAN, re.compile(r"INCOME\s*TAX|PERMANENT\s*ACCOUNT|\bPAN\b", re.I), "ID"),
	("Aadhaar", AADHAAR, re.compile(r"AADHAAR|AADHAR|UIDAI|UNIQUE\s*IDENTIFICATION|आधार", re.I), "ID"),
	("Passport", PASSPORT, re.compile(r"PASSPORT|REPUBLIC\s*OF\s*INDIA", re.I), "Travel"),
	("Driving licence", LICENCE, re.compile(r"DRIVING\s*LICEN[CS]E|TRANSPORT", re.I), "ID"),
	("Bank KYC", ACCOUNT, re.compile(r"\bKYC\b|KNOW\s*YOUR\s*CUSTOMER|IFSC|ACCOUNT\s*(?:NO|NUMBER)", re.I), "Other"),
)
EXPIRY = re.compile(r"(?:date\s*of\s*expiry|expiry(?:\s*date)?|valid\s*(?:up\s*to|till|until)|validity)\D{0,25}(\d{1,2})[/.\- ](\d{1,2})[/.\- ](\d{4})", re.I)
HINT = {"PAN": "Permanent Account Number", "Aadhaar": "Aadhaar", "Passport": "passport", "Driving licence": "driving licence", "Bank KYC": "KYC"}


def _digits(value: str) -> str:
	return re.sub(r"[ -]", "", value)


def expiry_of(text: str) -> str | None:
	"""The expiry date printed on the card (day first, as Indian documents print it), as YYYY-MM-DD; None when there is none or it is not a date."""
	m = EXPIRY.search(text or "")
	if not m:
		return None
	try:
		return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
	except ValueError:
		return None


def detect(text: str) -> dict | None:
	"""The ID document the text is, or None. Returns {type, doc_type, last4, expiry}: never the number."""
	text = text or ""
	for kind, pattern, words, doc_type in KINDS:
		if not words.search(text):
			continue
		for m in pattern.finditer(text):
			number = _digits(m.group(0))
			return {"type": kind, "doc_type": doc_type, "last4": number[-4:], "expiry": expiry_of(text)}
	return None


def mask(text: str) -> str:
	"""`text` with every PAN, Aadhaar, passport and licence number hidden, for anything that is about to go to a model."""
	text = text or ""
	for pattern in (PAN, AADHAAR, LICENCE):
		text = pattern.sub(lambda m: "••••" + _digits(m.group(0))[-4:], text)
	return text


def shown(last4: str) -> str:
	return "••••" + last4 if last4 else ""
