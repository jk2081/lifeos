"""Library > Files (issue 24): every stored file once, with where it is used.

Issue 7 stores a file once per space and gives each record that uses it its own File row, all with one `file_url`.
This groups those rows by `file_url`: one line per file, the records that use it under "Used in", the earlier versions
of it, and, for a reusable asset (an input that jobs link, as in `lifeos.api.jobs.file_job`), how many jobs used it.
Access follows the records: a record the user may not open (a Vault document, or a sensitive item, while the Vault
is closed to an agent) is left out of "Used in", and a file with no record left is not listed."""
import builtins
import os

import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.sources import agent_users
from lifeos.api.utils import descendants, page

TYPES = {
	"documents": (".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".numbers", ".pages", ".json", ".html"),
	"images": (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".svg"),
	"slides": (".ppt", ".pptx", ".key", ".odp", ".potx"),
	"audio": (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac", ".opus", ".amr"),
}
TYPE_LETTER = {"documents": "D", "images": "I", "slides": "S", "audio": "A", "other": "F"}
# the records whose files are listed, with the pane prefix each opens under
USERS = {"Life Inbox Item": "source:", "Life Note": "note:", "Life Vault Document": "vault:", "Life Chat Log": "chat:"}
ITEM = "Life Inbox Item"


def file_type(file_name: str) -> str:
	ext = os.path.splitext((file_name or "").lower())[1]
	return next((t for t, exts in TYPES.items() if ext in exts), "other")


def _records(space):
	"""Every current or earlier File row of the space, with the record it is attached to, as {file row: record}."""
	rows = []
	for dt in USERS:
		files = frappe.get_all("File", filters={"attached_to_doctype": dt, "is_folder": 0, "attached_to_field": ["not in", ("preview_image", "thumbnail")]},  # system: a File has no space; only files whose record the person can read (get_list below) are kept
			fields=["name", "file_name", "file_url", "file_size", "creation", "owner", "life_version_of", "attached_to_name"], order_by="creation asc")
		if not files:
			continue
		meta = frappe.get_meta(dt)
		fields = ["name", "space", meta.title_field or "name"] + [f for f in ("area", "source_system", "intent", "external_id", "is_sensitive") if meta.has_field(f)]
		recs = {r.name: r for r in frappe.get_list(dt, filters={"name": ["in", builtins.list({f.attached_to_name for f in files})], "space": space}, fields=fields)}
		for f in files:
			rec = recs.get(f.attached_to_name)
			if rec and f.file_url:
				f.doctype, f.record = dt, rec
				f.title = rec.get(meta.title_field or "name")
				rows.append(f)
	return rows


def _visible(doctype, name) -> bool:
	return permissions.file_has_permission(frappe._dict(attached_to_doctype=doctype, attached_to_name=name))


def _jobs_by_asset(asset_items):
	"""{asset item: [the items whose jobs used it]} from the jobs' input tables."""
	if not asset_items:
		return {}
	out = {}
	for asset, parent in frappe.db.sql("select asset, parent from `tabLife Job Input` where parenttype = 'Life Inbox Item' and asset in %s order by idx", (builtins.list(asset_items),)):
		out.setdefault(asset, [])
		if parent not in out[asset] and parent != asset:
			out[asset].append(parent)
	return out


def _group(rows):
	"""One group per stored copy: its current rows, and the earlier versions of those rows."""
	current = [r for r in rows if not r.life_version_of]
	by_row = {r.name: r for r in current}
	groups = {}
	for r in current:
		groups.setdefault(r.file_url, {"rows": [], "earlier": {}})["rows"].append(r)
	for r in rows:
		parent = by_row.get(r.life_version_of)
		if parent is not None and r.file_url != parent.file_url:
			groups[parent.file_url]["earlier"].setdefault(r.file_url, r)
	return groups


def _build(space, rows):
	groups = _group(rows)
	assets = {r.attached_to_name for g in groups.values() for r in g["rows"] if r.doctype == ITEM}
	jobs = _jobs_by_asset(assets)
	titles = {n: t for n, t in frappe.get_list(ITEM, filters={"name": ["in", builtins.list({j for js in jobs.values() for j in js})]}, fields=["name", "title"], as_list=True)} if jobs else {}
	agents = set(agent_users())
	out = []
	for url, g in groups.items():
		used, areas, systems, owners = [], [], set(), set()
		for r in g["rows"]:
			if not _visible(r.doctype, r.attached_to_name):
				continue
			ref = USERS[r.doctype] + r.attached_to_name
			if all(u["ref"] != ref for u in used):
				used.append({"ref": ref, "doctype": r.doctype, "name": r.attached_to_name, "title": r.title or r.attached_to_name})
			areas.append(r.record.get("area") or "")
			owners.add(r.owner)
			if r.doctype == ITEM:
				systems.add((r.record.get("source_system") or "").lower())
		if not used:
			continue
		job_items = []
		for r in g["rows"]:
			if r.doctype == ITEM:
				job_items += [j for j in jobs.get(r.attached_to_name, []) if j not in job_items]
		job_items = [j for j in job_items if _visible(ITEM, j)]
		for j in job_items:
			ref = "source:" + j
			if all(u["ref"] != ref for u in used):
				used.append({"ref": ref, "doctype": ITEM, "name": j, "title": titles.get(j) or j, "job": True})
		top = max(g["rows"], key=lambda r: str(r.creation))
		versions = sorted([top, *g["earlier"].values()], key=lambda r: str(r.creation), reverse=True)
		kind = file_type(top.file_name)
		out.append({
			"key": url, "name": top.file_name, "url": url, "size": top.file_size or 0, "type": kind, "letter": TYPE_LETTER[kind], "date": str(top.creation.date()),
			"_at": str(top.creation), "version_count": len(versions),
			"versions": [{"name": v.file_name, "url": v.file_url, "size": v.file_size or 0, "date": str(v.creation.date()), "current": v is top} for v in versions],
			"used_in": used, "reusable": bool(job_items), "jobs": len(job_items), "areas": [a for a in areas if a], "no_area": not any(areas),
			"systems": sorted(s for s in systems if s), "by_brain": bool(owners & agents), "by_me": bool(owners - agents),
		})
	return out


@frappe.whitelist(methods=["GET"])
def list(space: str | None = None, q: str | None = None, type: str | None = None, area: str | None = None, source: str | None = None,
		start: int | None = 0, page_length: int | None = 50):
	"""Every file of a space once, newest first, with where it is used.
	q: a word in the file's name. type: documents, images, slides, audio or other. area (with its parts, or "none"), source: me,
	brain (sent by an agent), or a system such as gmail.
	Each row has: name, url, size, type, letter, date, version_count, versions (newest first, each with a url), used_in (ref, title, job),
	reusable and jobs (how many jobs used it). `total` is what the filters match; `sources` lists the systems files came from."""
	space = permissions.resolve_space(space)
	start, page_length = page(start, page_length)
	type = (type or "").strip().lower()
	if type and type not in (*TYPES, "other"):
		frappe.throw(_("type must be one of: {0}.").format(", ".join((*TYPES, "other"))))
	rows = _build(space, _records(space))
	systems = sorted({s for r in rows for s in r["systems"]})
	q = (q or "").strip().lower()[:200]
	if q:
		rows = [r for r in rows if q in r["name"].lower()]
	if type:
		rows = [r for r in rows if r["type"] == type]
	if area == "none":
		rows = [r for r in rows if r["no_area"]]
	elif area:
		ids = set(descendants(space, area))
		rows = [r for r in rows if ids & set(r["areas"])]
	if source == "me":
		rows = [r for r in rows if r["by_me"]]
	elif source == "brain":
		rows = [r for r in rows if r["by_brain"]]
	elif source:
		rows = [r for r in rows if source.lower() in r["systems"]]
	rows.sort(key=lambda r: (r["date"], r["_at"], r["name"]), reverse=True)
	for r in rows:
		for k in ("_at", "areas", "no_area", "systems", "by_me"):
			r.pop(k, None)
	return {"space": space, "rows": rows[start:start + page_length], "total": len(rows), "start": start, "page_length": page_length, "sources": systems}
