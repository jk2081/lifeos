import frappe
from frappe import _
from frappe.model.document import Document

SOURCE_DOCTYPES = ("Life Inbox Item", "Life Chat Log")
MAX_MD = 200000


class LifeNote(Document):
	def validate(self):
		from lifeos import permissions

		self.collection = self.collection or "My notes"
		if self.is_new() and not self.last_opened_on:
			self.last_opened_on = frappe.utils.today()  # a new note counts as opened the day it is made
		# agents write wiki pages through lifeos.api.wiki only (which logs every change); My notes pages are people's own
		agent = permissions.is_agent() and not frappe.flags.lifeos_app_write
		if agent and not frappe.flags.lifeos_wiki_api:
			frappe.throw(_("Agents change wiki pages with lifeos.api.wiki and propose notes; they cannot write notes directly."), frappe.PermissionError)
		if agent and (self.collection != "Wiki" or self.is_rules):
			frappe.throw(_("Agents cannot change My notes pages or the wiki's rules page."), frappe.PermissionError)
		if not self.is_new() and self.has_value_changed("collection") and agent:
			frappe.throw(_("Only a person can move a page between My notes and the wiki."), frappe.PermissionError)
		self.summary = " ".join((self.summary or "").split())[:500] or None
		if self.collection == "Wiki" and not self.summary and not frappe.flags.lifeos_wiki_summary_optional:
			frappe.throw(_("A wiki page needs a one-line summary."))
		if self.is_rules:
			if self.collection != "Wiki":
				frappe.throw(_("Only a wiki page can be the rules page."))
			other = frappe.db.get_value("Life Note", {"space": self.space, "is_rules": 1, "name": ["!=", self.name or ""]})
			if other:
				frappe.throw(_("This space already has a wiki rules page."))
		if len(self.content_md or "") > MAX_MD:
			frappe.throw(_("A page can hold at most {0} characters.").format(f"{MAX_MD:,}"))
		seen, rows = set(), []
		for r in self.get("sources") or []:
			if r.source_doctype not in SOURCE_DOCTYPES:
				frappe.throw(_("A page can cite inbox items and chat logs only."))
			key = (r.source_doctype, r.source_name)
			if key in seen:
				continue
			seen.add(key)
			space = frappe.db.get_value(r.source_doctype, r.source_name, "space")
			if not space:
				frappe.throw(_("{0} {1} does not exist.").format(r.source_doctype, r.source_name))
			if space != self.space:
				frappe.throw(_("A page can only cite sources from its own space."))
			rows.append(r)
		self.set("sources", rows)
