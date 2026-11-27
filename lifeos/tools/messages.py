"""Messages Chat writes to a person (issue 150): drafted first, sent only when the owner says so.

A draft is a Frappe `Communication` that has not gone: `delivery_status` is "Scheduled", it is about the Life Person it is for and its timeline links
name the records it concerns (the tasks it reports on), so it shows in their timelines. Sending sends it through Google's act `email.send` with
`asked_by: owner` and the owner's words (`lifeos.agents.acts.request`, as a hand-off's Send does) and sets it "Sent". The channel is a word
(`CHANNELS`); WhatsApp is added there when it comes. The words of a message are the model's; this module is the record, the check and the send.
"""
import frappe
from frappe import _
from lifeos import permissions

CHANNELS = {"email": "Email"}  # channel -> Communication's medium
DRAFT, SENT = "Scheduled", "Sent"


def find_person(space: str, query: str):
	"""The one Life Person a name (or a company's name) means in the space; the owner is asked which when two fit."""
	q = " ".join((query or "").split()).lower()
	if not q:
		frappe.throw(_("Say who the message is for."), title=_("Person is missing"))
	rows = frappe.get_all("Life Person", filters={"space": space, "is_archived": 0}, fields=["name", "full_name", "aliases", "organisation", "role"], limit=5000)
	org = {r.name: (r.full_name or "") for r in rows}
	exact, partial = [], []
	for r in rows:
		names = [(r.full_name or "").lower(), *[a.strip().lower() for a in (r.aliases or "").replace("\n", ",").split(",") if a.strip()]]
		company = org.get(r.organisation, "").lower()
		if q in names or (company and q == company):
			exact.append(r)
		elif any(q in n for n in names) or (company and q in company):
			partial.append(r)
	found = exact or partial
	if not found:
		frappe.throw(_("There is no one called {0} in Life OS. Add them first, with their email.").format(query), title=_("No such person"))
	if len(found) > 1:
		frappe.throw(_("{0} could mean: {1}. Ask the owner which.").format(query, "; ".join(f"{r.full_name}" + (f" ({org[r.organisation]})" if org.get(r.organisation) else "") for r in found[:6])),
			title=_("Which person?"))
	return frappe.get_doc("Life Person", found[0].name)


def _words(text: str) -> str:
	text = (text or "").strip()
	if not text:
		frappe.throw(_("A message needs words."), title=_("Message is empty"))
	return text


def draft(space: str, person: str, text: str, channel: str = "email", about: list | None = None, subject: str | None = None) -> dict:
	"""Save a draft for `person` and send nothing. `about` is [(doctype, name)] of the records it concerns. Returns the card."""
	space = permissions.resolve_space(space, write=True)
	channel = (channel or "email").lower()
	if channel not in CHANNELS:
		frappe.throw(_("Messages go by {0} for now.").format(", ".join(CHANNELS)), title=_("Channel not available"))
	who = find_person(space, person)
	text = _words(text)
	links = []
	for doctype, name in about or []:
		doc = permissions.get_doc_checked(doctype, name, "read")
		if doc.get("space") and doc.space != space:
			frappe.throw(_("That record is in another space."), title=_("Record is in another space"))
		links.append({"link_doctype": doctype, "link_name": name, "link_title": (doc.get("title") or doc.get("full_name") or name)[:140]})
	subject = " ".join((subject or "").split())[:140] or (links[0]["link_title"] if links else _("A quick note"))
	comm = frappe.get_doc({"doctype": "Communication", "communication_type": "Communication", "sent_or_received": "Sent", "communication_medium": CHANNELS[channel],
		"delivery_status": DRAFT, "subject": subject, "content": text, "recipients": who.email or "", "sender": frappe.db.get_value("User", frappe.session.user, "email"),
		"user": frappe.session.user, "reference_doctype": "Life Person", "reference_name": who.name, "timeline_links": links}).insert(ignore_permissions=True)  # system: a note of what is drafted, for a person the owner can write to (checked above)
	return card(comm.name)


def _draft(name: str, write: bool = True):
	"""The draft `name` (the owner's own, not yet gone), and the person it is for."""
	if not name or not frappe.db.exists("Communication", name):
		frappe.throw(_("That draft is gone."), title=_("No draft"))
	comm = frappe.get_doc("Communication", name)
	if comm.reference_doctype != "Life Person" or comm.user != frappe.session.user:
		frappe.throw(_("That is not one of your drafts."), frappe.PermissionError, title=_("Not your draft"))
	who = permissions.get_doc_checked("Life Person", comm.reference_name, "write" if write else "read")
	return comm, who


def latest(space: str) -> str | None:
	"""The newest draft of the owner's that has not gone, for "send it"."""
	for name in frappe.get_all("Communication", filters={"user": frappe.session.user, "delivery_status": DRAFT, "reference_doctype": "Life Person", "sent_or_received": "Sent"},
			pluck="name", order_by="creation desc", limit=20):
		if frappe.db.get_value("Life Person", frappe.db.get_value("Communication", name, "reference_name"), "space") == space:
			return name
	return None


def card(name: str) -> dict:
	"""A draft as the answer shows it: {name, to, address, channel, subject, body, status, about}; status is Draft, Sent or Sending."""
	comm, who = _draft(name, write=False)
	return {"name": comm.name, "person": who.name, "to": who.full_name, "address": comm.recipients or "", "channel": next((k for k, v in CHANNELS.items() if v == comm.communication_medium), "email"),
		"subject": comm.subject, "body": comm.content, "status": "Draft" if comm.delivery_status == DRAFT else comm.delivery_status,
		"needs_address": not comm.recipients, "about": [l.link_name for l in comm.timeline_links if l.link_doctype != "Contact"]}


def edit(name: str, text: str | None = None, address: str | None = None) -> dict:
	"""Change a draft's words, or give the address it goes to (saved to the person too)."""
	comm, who = _draft(name)
	if comm.delivery_status != DRAFT:
		frappe.throw(_("That message has gone; it cannot be changed."), title=_("Already sent"))
	if text is not None:
		comm.content = _words(text)
	address = (address or "").strip()
	if address:
		address = frappe.utils.validate_email_address(address, throw=True)
		comm.recipients = address
		if not who.email:
			frappe.db.set_value("Life Person", who.name, "email", address)
	comm.save(ignore_permissions=True)  # system: the owner's own draft; the person's write check is above
	return card(comm.name)


def drop(name: str) -> dict:
	"""Delete a draft that has not gone."""
	comm, _who = _draft(name)
	if comm.delivery_status != DRAFT:
		frappe.throw(_("That message has gone; it cannot be dropped."), title=_("Already sent"))
	frappe.delete_doc("Communication", comm.name, ignore_permissions=True, force=True)  # system: the owner's own draft; the person's write check is above
	return {"dropped": name}


def line_of(who_name: str, subject: str) -> str:
	return _("Emailed {0}: {1}").format(who_name, subject)


def send(name: str, text: str | None = None, owner_message: str | None = None, not_after=None) -> dict:
	"""Send the draft now: the owner pressed Send or said yes. It goes out once (a second call does nothing). `not_after` is a time: a draft written after it is
	refused (Chat may not write and send in one turn). Returns {sent, already, line, card}."""
	from lifeos.agents import acts, limits
	from lifeos.tools import work

	comm, who = _draft(name)
	if text:
		edit(name, text)
	space = who.space
	limits.claim_owner(space)  # a family member cannot say the owner asked
	if not_after and frappe.utils.get_datetime(comm.creation) >= frappe.utils.get_datetime(not_after):
		frappe.throw(_("The owner has not said yet to send it. Ask: Send it?"), title=_("Not asked yet"))
	if comm.delivery_status != DRAFT:
		return {"sent": False, "already": True, "line": None, "card": card(name)}
	if comm.communication_medium != CHANNELS["email"]:
		frappe.throw(_("Only email can be sent for now."), title=_("Channel not available"))
	if not comm.recipients:
		frappe.throw(_("{0} has no email yet. Ask the owner for the address.").format(who.full_name), title=_("No email address"))
	if frappe.db.get_value("Communication", comm.name, "delivery_status", for_update=True) != DRAFT:  # a second Send waits for the first, then finds it gone
		return {"sent": False, "already": True, "line": None, "card": card(name)}
	params = {"to": comm.recipients, "subject": comm.subject or _("A quick note"), "body": comm.content}
	got = acts.request(space, work.CHAT_AGENT, "email.send", params, "owner", owner_message or _("Send the message to {0}").format(who.full_name))
	done = got["status"] == "done"
	if done:
		frappe.db.set_value("Communication", comm.name, "delivery_status", SENT)
	if got["status"] == "failed":
		frappe.throw(got.get("error") or _("The email was not sent."), title=_("Not sent"))
	return {"sent": done, "already": False, "waiting": got.get("action") if got["status"] == "waiting" else None,
		"line": {"text": line_of(who.full_name, comm.subject), "undo": None, "kind": "message", "doctype": "Communication", "name": comm.name, "pane": None, "undone": 0} if done else None,
		"card": card(name)}

