"""Settings > Me > Calendar (set 8): connect Google Calendar through Frappe's own OAuth flow, choose which calendars to read,
see when it last read, and disconnect. Read only: nothing is ever written to Google. People only."""
import frappe
from frappe import _

from lifeos import permissions
from lifeos.api.utils import parse
from lifeos.review import gcal


def _person():
	permissions.require_login()
	if permissions.is_agent():
		frappe.throw(_("Calendars are connected by people."), frappe.PermissionError)
	return frappe.session.user


@frappe.whitelist(methods=["GET"])
def state():
	"""Whether Google Settings is configured, whether this user is connected, which calendars are read, last synced, your domains."""
	return gcal.state(_person())


@frappe.whitelist(methods=["POST"])
def connect():
	"""Start Frappe's OAuth flow for this user's calendar (read by Life OS only). Returns {"url"} to open."""
	user = _person()
	if not gcal.configured():
		frappe.throw(_("Google is not set up on this site. The owner enters the OAuth client in Google Settings first."))
	return gcal.connect(user)


@frappe.whitelist(methods=["POST"])
def disconnect():
	return gcal.disconnect(_person())


@frappe.whitelist(methods=["GET"])
def calendars():
	"""The user's calendars on Google (a read), to choose which ones Life OS reads."""
	user = _person()
	acc = gcal.account(user)
	if not frappe.conf.get("lifeos_fake_calendar") and not (acc and acc.enable):
		return {"calendars": []}
	return {"calendars": gcal.source_for(acc).calendars(), "read": gcal.read_ids(acc) if acc else ["primary"]}


@frappe.whitelist(methods=["POST"])
def set_read(ids: str | list):
	ids = parse(ids, []) or []
	return gcal.set_read(_person(), ids if isinstance(ids, list) else [])


@frappe.whitelist(methods=["POST"])
def sync():
	"""Read now: the last 21 days and the next 14."""
	user = _person()
	n = gcal.sync_user(user)
	return {"read": n, **gcal.state(user)}
