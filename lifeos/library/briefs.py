"""The Brain's brief at the top of a page (issue 111): three to eight sentences written from everything linked to a subject, each pointing at its
sources by number. Plumbing only: which subjects have something new, the day's limit, the cap, what the model may see (never a sensitive or Vault
item) and where the answer is stored. What the brief says is the `write-brief` skill's judgment. The Brain writes nothing else on a page."""
import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, nowdate

from lifeos.ai import client
from lifeos.library import subjects

SKILL = "write-brief"
SOURCES_SHOWN = 12  # the newest sources the model reads
TEXT_CHARS = 500  # of each source: extracted text (#104 when it has landed), never a whole file
MAX_SENTENCES = 8
FIELDS = ("brief_md", "brief_sources", "brief_on")
CITE = re.compile(r"\[(\d+)\]")


def stale(doctype: str, name: str) -> bool:
	"""Something new was linked since the brief was written (or there is no brief yet and something is linked)."""
	last = subjects.last_linked(doctype, name)
	if not last:
		return False
	on = frappe.db.get_value(doctype, name, "brief_on")
	return not on or last > on


def readable(doctype: str, name: str) -> tuple[list, int]:
	"""(the sources the model may read, how many sensitive ones were left out). Sensitive and Vault items are counted, never shown."""
	items, _total = subjects.timeline(doctype, name, limit=60)
	hidden = sum(1 for e in items if e["sensitive"])
	shown = [e for e in items if not e["sensitive"]][:SOURCES_SHOWN]
	return shown, hidden


def _about(doctype: str, name: str) -> dict:
	if doctype == "Life Area":
		a = frappe.db.get_value("Life Area", name, ["area_name", "parent_area", "description"], as_dict=True)
		return {"name": a.area_name, "kind": "part", "area": frappe.db.get_value("Life Area", a.parent_area, "area_name") if a.parent_area else None, "description": a.description or ""}
	p = frappe.db.get_value("Life Person", name, ["full_name", "kind", "status", "organisation", "role", "aliases", "area"], as_dict=True)
	return {"name": p.full_name, "kind": "company" if p.kind == "Organisation" else "person", "status": p.status, "role": p.role,
		"organisation": frappe.db.get_value("Life Person", p.organisation, "full_name") if p.organisation else None,
		"also_called": subjects.split_aliases(p.aliases),
		"people": frappe.get_all("Life Person", filters={"organisation": name}, pluck="full_name", limit=20) if p.kind == "Organisation" else []}


def rewrite(doctype: str, name: str, force: bool = False) -> dict:
	"""Write the brief again. Returns {written: bool, reason, sources: n}. Not more than once a day unless `force`; not when nothing new was linked unless `force`; not
	when the AI is not set up or the month's cap is reached (the brief waits)."""
	if doctype not in subjects.SUBJECTS:
		frappe.throw(_("Only a person, a company or a part has a brief."), title=_("No brief here"))
	on = frappe.db.get_value(doctype, name, "brief_on")
	if not force and (not stale(doctype, name) or (on and getdate(on) >= getdate(nowdate()))):
		return {"written": False, "reason": "nothing new", "sources": 0}
	shown, hidden = readable(doctype, name)
	if not shown:
		return {"written": False, "reason": "nothing readable is linked", "sources": 0}
	try:
		client.check(f"Skill: {SKILL}")
	except client.NotSetUp:
		return {"written": False, "reason": "no AI key", "sources": 0}
	except client.CapReached as e:
		return {"written": False, "reason": str(e)[:200], "sources": 0, "capped": True}
	from lifeos.skills import call

	space = frappe.db.get_value(doctype, name, "space")
	data = {"about": _about(doctype, name), "sources": [{"n": i + 1, "kind": e["kind"], "date": e["date"], "title": e["title"], "text": (e["text"] or "")[:TEXT_CHARS]} for i, e in enumerate(shown)],
		"sensitive_sources_not_shown": hidden}
	answer = call.ask(SKILL, data, space)
	if not answer:
		return {"written": False, "reason": answer.reason or "no answer", "sources": 0}
	made = assemble(answer.get("sentences") or [], shown, hidden)
	if not made["sentences"]:
		return {"written": False, "reason": "the answer pointed at no source", "sources": 0}
	frappe.db.set_value(doctype, name, {"brief_md": made["md"], "brief_sources": json.dumps(made["sources"]), "brief_on": now_datetime()}, update_modified=False)
	return {"written": True, "sources": len(made["sources"]), "reason": None}


def assemble(sentences: list, shown: list, hidden: int) -> dict:
	"""The brief's text from the model's sentences: at most eight, each kept only when it points at a source that exists. Source numbers stay the model's."""
	out, cited = [], {}
	for s in sentences:
		numbers = [n for n in (s.get("sources") or []) if isinstance(n, int) and 1 <= n <= len(shown)]
		text = " ".join(str(s.get("text") or "").split())
		if not numbers or not text:
			continue
		text = CITE.sub("", text).strip()
		out.append(f"{text} " + "".join(f"[{n}]" for n in dict.fromkeys(numbers)))
		for n in numbers:
			e = shown[n - 1]
			cited[n] = {"n": n, "doctype": e["doctype"], "name": e["name"], "kind": e["kind"], "title": e["title"], "date": e["date"], "url": e.get("url"), "ref": e.get("ref")}
		if len(out) >= MAX_SENTENCES:
			break
	md = " ".join(out)
	if out and hidden:
		md += " " + (_("1 sensitive document is filed here.") if hidden == 1 else _("{0} sensitive documents are filed here.").format(hidden))
	return {"md": md, "sentences": out, "sources": [cited[n] for n in sorted(cited)]}


def read(doctype: str, name: str) -> dict | None:
	"""The stored brief: {md, sources, on, stale} or None when there is none."""
	row = frappe.db.get_value(doctype, name, list(FIELDS), as_dict=True)
	if not row or not row.brief_md:
		return None
	return {"md": row.brief_md, "sources": json.loads(row.brief_sources or "[]"), "on": str(row.brief_on) if row.brief_on else None, "stale": stale(doctype, name)}


def run_daily():
	"""Scheduled each day: write again the brief of every subject with something linked since it was written, at most once a day each, until the month's cap
	is reached. A brief costs one quick-model call and counts against the monthly cap; when the cap is reached the rest wait."""
	todo = []
	for dt in subjects.SUBJECTS:
		for name in frappe.get_all(dt, filters={"is_archived": 0} if dt == "Life Person" else {"is_archived": 0, "is_focus": 0}, pluck="name", limit=5000):  # system: the daily job reads every space
			if dt == "Life Area" and not frappe.db.get_value("Life Area", name, "parent_area"):
				continue
			if stale(dt, name):
				todo.append((dt, name))
	written = 0
	for dt, name in todo:
		try:
			res = rewrite(dt, name)
			frappe.db.commit()
		except Exception:  # noqa: BLE001 - one subject failing never stops the others
			frappe.db.rollback()
			frappe.log_error(title="Life OS brief failed")
			continue
		written += 1 if res["written"] else 0
		if res.get("capped") or res.get("reason") == "no AI key":
			break
	return written
