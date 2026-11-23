import frappe
from frappe import _
from frappe.model.document import Document


def split_aliases(text) -> list[str]:
	"""The other names of a person, from one per line or separated by commas."""
	seen, out = set(), []
	for part in (text or "").replace(",", "\n").splitlines():
		part = " ".join(part.split())
		if part and part.lower() not in seen:
			seen.add(part.lower())
			out.append(part)
	return out


class LifePerson(Document):
	def validate(self):
		self.kind = self.kind or "Person"
		self.aliases = "\n".join(split_aliases(self.aliases)) or None
		if self.organisation:
			if self.organisation == self.name:
				frappe.throw(_("A person cannot belong to themselves."), title=_("Person cannot belong to self"))
			kind, space = frappe.db.get_value("Life Person", self.organisation, ["kind", "space"]) or (None, None)
			if kind != "Organisation" or space != self.space:
				frappe.throw(_("The organisation must be a Life Person of kind Organisation in the same space."), title=_("Organisation not valid"))
		if self.kind == "Organisation" and self.organisation:
			frappe.throw(_("An organisation does not belong to another organisation."), title=_("Organisation cannot belong"))
		if self.kind == "Person" and not self.is_new() and frappe.db.exists("Life Person", {"organisation": self.name}):
			frappe.throw(_("Other people belong to this one, so it must stay an organisation."), title=_("Organisation has members"))
