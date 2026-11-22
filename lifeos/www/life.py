import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.utils.quote((frappe.request.full_path or "/life").rstrip("?"))
		raise frappe.Redirect(302)
	context.boot = {"csrf_token": frappe.sessions.get_csrf_token(), "site_name": frappe.local.site}
	return context
