from frappe.model.document import Document


class LifeSkill(Document):
	def validate(self):
		from lifeos.skills import store

		store.validate(self)  # the fixed lists: trigger, event, schedule, output, tier, tools
