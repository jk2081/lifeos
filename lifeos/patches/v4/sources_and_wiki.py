"""UX fixes, set 4: existing rows stay valid under the new fields.
- every note is a My notes page; every inbox item has the intent Process and a kind of source;
- inbox items that a Vault document was made from are marked, so they follow Vault access;
- the index is rebuilt, so it carries the new columns and the longer search text."""
import frappe


def execute():
	from lifeos import index, sources

	frappe.db.sql("update `tabLife Note` set collection = 'My notes' where ifnull(collection, '') = ''")
	frappe.db.sql("update `tabLife Inbox Item` set intent = 'Process' where ifnull(intent, '') = ''")
	for item in frappe.get_all("Life Inbox Item", fields=["name", "source_type", "source_url"]):
		names = [f.file_name for f in sources.original_files(item.name)]
		frappe.db.set_value("Life Inbox Item", item.name, "media_kind", sources.media_kind(item.source_type, names, item.source_url),
			update_modified=False)
	for vault, item in frappe.db.sql("select name, inbox_item from `tabLife Vault Document` where ifnull(inbox_item, '') != ''"):
		frappe.db.set_value("Life Inbox Item", item, "vault_document", vault, update_modified=False)
	index.ensure_indexes()
	index.rebuild()
