from frappe.model.document import Document


class LifeChatLog(Document):
	def validate(self):
		from lifeos import sources

		sources.check_external_id(self)
