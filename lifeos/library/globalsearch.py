"""What search covers (issue 98): Frappe's Global Search over the whole app.

`FIELDS` names the searched fields of each record type. `install()` marks them `in_global_search` (Property Setters, so the
DocType files stay as they are) and lists the record types in Global Search Settings; `setup()` runs it on every install and
migrate. Frappe keeps `__global_search` up to date on every save and delete; `rebuild()` fills it for records that already exist.
System records (logs, usage, prices, jobs, skill runs, settings rows) are not listed, so they are never searched.
"""
import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from lifeos.constants import SEARCHED_DOCTYPES

# record type -> (kind shown on a result, searched fields)
FIELDS = {
	"Life Task": ("Task", ["title", "notes_md"]),
	"Life Inbox Item": ("Capture", ["title", "raw_text", "transcript_md", "extracted_text"]),  # a photo or recording's transcript is the capture's text
	"Life Note": ("Note", ["title", "content_md"]),
	"Life Chat Log": ("Chat", ["title", "summary_md"]),
	"Event": ("Event", ["subject", "description", "location"]),
	"Life Goal": ("Goal", ["title", "done_when"]),
	"Life Cycle": ("Cycle", ["title"]),
	"Life Area": ("Area", ["area_name", "description"]),
	"Life Person": ("Person", ["full_name", "aliases", "notes_md"]),
	"Life Habit": ("Habit", ["title"]),
	"Life Review": ("Weekly review", ["went_well", "do_differently"]),
	"Life Insight": ("Insight", ["title", "body"]),
	"Life Ask Thread": ("Ask thread", ["title"]),
	"Life Vault Document": ("Vault document", ["title", "extracted_text"]),  # what a document says is read on this server (issue 104); a hit is opened with has_permission, so only who may open the document finds it. Life Index, which Ask reads, never holds it
	"Life Proposal": ("Needs you", ["preview"]),
	"Life Skill": ("Skill", ["title"]),
	"Life Source Setting": ("Source", ["source"]),
	"Comment": ("Comment", ["content"]),  # a match opens the record the comment is on
}
assert list(FIELDS) == SEARCHED_DOCTYPES  # hooks.py names the same list, without importing frappe
KIND = {dt: kind for dt, (kind, _fields) in FIELDS.items()}
# Global Search Settings refuses a record type of the Core module (Comment). Frappe still indexes its marked fields; only
# Frappe's own `search` reads the list, and ours does not.


def install():
	"""Mark the searched fields and list the record types in Global Search Settings. Safe to run again; other types an
	administrator listed are kept."""
	for doctype, (_kind, fields) in FIELDS.items():
		meta = frappe.get_meta(doctype)
		for df in meta.fields:
			want = 1 if df.fieldname in fields else 0
			if df.fieldtype in frappe.model.no_value_fields:
				continue
			if want or df.in_global_search:
				if bool(df.in_global_search) != bool(want):
					make_property_setter(doctype, df.fieldname, "in_global_search", want, "Check", validate_fields_for_doctype=False)
		frappe.clear_cache(doctype=doctype)
	settings = frappe.get_single("Global Search Settings")
	have = {r.document_type for r in settings.allowed_in_global_search}
	missing = [dt for dt in FIELDS if dt not in have and frappe.get_meta(dt).module != "Core"]
	if missing:
		for dt in missing:
			settings.append("allowed_in_global_search", {"document_type": dt})
		settings.flags.ignore_permissions = True  # system: install runs before any person has roles
		settings.save()
	frappe.cache.delete_value("doctypes_with_global_search")
	frappe.cache.hdel("global_search", "search_priorities")


def rebuild():
	"""Index the records that already exist (a patch, and `bench execute lifeos.library.globalsearch.rebuild`)."""
	from frappe.utils.global_search import rebuild_for_doctype, sync_global_search

	for doctype in FIELDS:
		rebuild_for_doctype(doctype)
	sync_global_search()


def index_soon(doc, method=None):
	"""A record was saved: once its transaction is committed, write Frappe's queue of records waiting for the search index in a background
	job (one job for the saves of one transaction). A search is a GET and cannot write, so the index is never written there."""
	if frappe.flags.in_test or frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch or frappe.flags.lifeos_index_job:
		return
	frappe.flags.lifeos_index_job = True
	frappe.db.after_commit.add(_enqueue)
	frappe.db.after_rollback.add(_forget)


def _forget():
	frappe.flags.lifeos_index_job = False


def _enqueue():
	_forget()
	frappe.enqueue("frappe.utils.global_search.sync_global_search", queue="short")
