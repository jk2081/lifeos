"""The background job of a question that needs more than 3 pages of mail (issue 107)."""
import frappe
from frappe import _

from lifeos.ai import ask as engine
from lifeos.ai import client


def run_background(thread: str, message: str, question: str, scope: dict, history: list, client_id: str | None = None):
	"""The background job of a question that needs more than 3 pages of mail (issue 107): it reads page by page, tells the screen which, and writes the
	answer into the message the screen is waiting on."""
	from lifeos.api import ask as api

	user = frappe.session.user  # Frappe's job runner signs in the person who queued it
	space = frappe.db.get_value("Life Ask Thread", thread, "space")
	key = f"lifeos_ask_req:{user}:{client_id}" if client_id else None
	state = {"reading": None}

	def show(status="Working", text=""):
		if key:
			frappe.cache.set_value(key, {"status": status, "text": text, "thread": thread, "message": message, "reading": state["reading"], "background": 1}, expires_in_sec=3600)

	def progress(line):
		state["reading"] = line
		show()

	show()
	try:
		res = engine.answer(space, question, scope, history, None, background=True, progress=progress)
	except Exception as e:  # noqa: BLE001 - the message says what went wrong; the stack is logged
		if not isinstance(e, client.AIError):
			frappe.log_error(title="Life OS Ask failed")
		msg = api.fail(message, str(e) if isinstance(e, client.AIError) else _("Something went wrong while answering. It has been logged."))
		state["reading"] = None
		show("Error")
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- a background job: the answer must be saved before the screen's next poll
		return msg
	state["reading"] = None
	msg = api.complete(message, res)
	show("Done", msg.text or "")
	frappe.db.commit()  # nosemgrep: frappe-manual-commit -- a background job: the answer must be saved before the screen's next poll
