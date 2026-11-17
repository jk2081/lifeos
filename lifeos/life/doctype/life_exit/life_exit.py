from frappe.model.document import Document


class LifeExit(Document):
	"""One record leaving the owner's plate (set 7): done, delegated, parked or discarded. Written only by the document hooks
	in lifeos/outbox.py; `reversed` is set when the record comes back."""
