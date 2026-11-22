from frappe.model.document import Document


class LifeWikiFinding(Document):
	"""Two wiki pages (or two facts on one) that disagree, found by the weekly check. It waits in Brain > Needs you until the owner picks the
	fact to keep (lifeos/wiki_check.py). `options` is JSON: [{page, fact, source_doctype, source_name}]."""
