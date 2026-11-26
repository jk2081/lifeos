import frappe
from frappe import _
from frappe.model.document import Document


class LifeRule(Document):
	def validate(self):
		for field in ("sender", "domain", "source", "attachment_type"):
			self.set(field, (self.get(field) or "").strip().lower().lstrip("@" if field == "domain" else "") or None)
		for field in ("item_kind", "title_words"):
			self.set(field, ", ".join(w.strip() for w in (self.get(field) or "").replace("\n", ",").split(",") if w.strip()) or None)
		if not self.builtin and not any(self.get(f) for f in ("sender", "domain", "source", "item_kind", "title_words", "attachment_type")):
			frappe.throw(_("A rule needs something to match: a sender, a domain, a source, a kind, words in the title or an attachment."), title=_("Rule has no condition"))
		if self.no_area:
			self.area = None
		if self.area and frappe.db.get_value("Life Area", self.area, "space") != self.space:
			frappe.throw(_("That area is not in this space."), title=_("Area is in another space"))
		if self.action == "File" and self.file_as in ("Note", "Report", "Task") and not self.area:
			frappe.throw(_("A rule that files a {0} needs an area or a part.").format(self.file_as.lower()), title=_("Rule needs an area"))
		if self.action == "File" and not (self.area or self.no_area or self.never_page):
			frappe.throw(_("Say where to file it: an area or part, or no area."), title=_("Rule needs a place"))
		if self.action == "Link" and not self.never_page and not (self.page_doctype and self.page):
			frappe.throw(_("A link rule needs a page to link to."), title=_("Rule needs a page"))
		if self.action != "File":
			self.file_as = None
