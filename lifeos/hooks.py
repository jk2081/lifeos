app_name = "lifeos"
app_title = "Life OS"
app_publisher = "Jai Kejriwal"
app_description = "A personal operating system on Frappe"
app_email = "hello@example.com"
app_license = "mit"

from lifeos.constants import INDEXED_DOCTYPES, SPACE_DOCTYPES

add_to_apps_screen = [
	{"name": "lifeos", "logo": "/assets/lifeos/icons/icon-192.png", "title": "Life OS", "route": "/life",
		"has_permission": "lifeos.permissions.has_app_permission"}
]

after_install = "lifeos.install.after_install"
after_migrate = "lifeos.install.after_migrate"

website_route_rules = [{"from_route": "/life/<path:app_path>", "to_route": "life"}]

# Link search for the filing DocTypes: the current space and active records only (lifeos/queries.py)
standard_queries = {dt: "lifeos.queries.link_query" for dt in ("Life Area", "Life Tag", "Life Habit", "Life Dimension", "Life Goal")}

permission_query_conditions = {dt: "lifeos.permissions.query_conditions" for dt in SPACE_DOCTYPES}
permission_query_conditions["Life Space"] = "lifeos.permissions.space_query_conditions"
permission_query_conditions["Event"] = "lifeos.permissions.event_query_conditions"

permission_query_conditions["Life View State"] = "lifeos.permissions.view_state_query_conditions"

has_permission = {dt: "lifeos.permissions.has_permission" for dt in SPACE_DOCTYPES}
has_permission["Life Space"] = "lifeos.permissions.space_has_permission"
has_permission["Event"] = "lifeos.permissions.event_has_permission"
has_permission["Life View State"] = "lifeos.permissions.view_state_has_permission"
has_permission["File"] = "lifeos.permissions.file_has_permission"
# Ask's threads and messages belong to the person who asked; agents never read them (UX fixes, set 5)
for _dt in ("Life Ask Thread", "Life Ask Message"):
	permission_query_conditions[_dt] = "lifeos.permissions.ask_query_conditions"
	has_permission[_dt] = "lifeos.permissions.ask_has_permission"

doc_events = {
	dt: {"validate": "lifeos.org.validate_common", "on_update": "lifeos.org.on_update", "on_trash": "lifeos.org.on_trash"}
	for dt in SPACE_DOCTYPES
}
# the Outbox (set 7): exits are written by these hooks only
for _dt in ("Life Task", "Life Goal", "Life Inbox Item", "Life Idea"):
	for _event, _fn in (("on_update", "on_update"), ("after_insert", "after_insert"), ("on_trash", "on_trash")):
		_have = doc_events[_dt].get(_event)
		doc_events[_dt][_event] = [*([_have] if isinstance(_have, str) else _have or []), f"lifeos.outbox.{_fn}"]
# set 8: a reading confirmed or rejected anywhere clears its finding in the weekly review
_have = doc_events["Life Goal Reading"].get("on_update")
doc_events["Life Goal Reading"]["on_update"] = [*([_have] if isinstance(_have, str) else _have or []), "lifeos.review.findings.reading_changed"]
doc_events["Event"] = {"validate": "lifeos.events.validate_event", "on_update": "lifeos.review.gcal_write.event_updated",
	"on_trash": "lifeos.review.gcal_write.event_trashed"}
# issue 31: a goal block already written to Google follows its task
for _event, _fn in (("on_update", "task_updated"), ("on_trash", "task_trashed")):
	doc_events["Life Task"][_event] = [*([doc_events["Life Task"][_event]] if isinstance(doc_events["Life Task"][_event], str) else doc_events["Life Task"][_event]), f"lifeos.review.gcal_write.{_fn}"]
# issue 28: skills start from document events, in a background job (lifeos/skills/triggers.py)
doc_events["Life Inbox Item"]["after_insert"] = [*doc_events["Life Inbox Item"]["after_insert"], "lifeos.skills.triggers.capture_created"]
for _dt in ("Life Task", "Life Goal", "Life Note"):
	doc_events[_dt]["on_update"] = [*([doc_events[_dt]["on_update"]] if isinstance(doc_events[_dt]["on_update"], str) else doc_events[_dt]["on_update"]),
		"lifeos.skills.triggers.record_changed"]
doc_events["File"] = {"after_insert": "lifeos.files.after_insert"}
# issue 7: a Life OS record's file is stored once per space by content, and the same file sent again is not attached twice
extend_doctype_class = {"File": ["lifeos.files.LifeFile"]}
override_whitelisted_methods = {"upload_file": "lifeos.files.upload_file", "frappe.handler.upload_file": "lifeos.files.upload_file"}
doc_events["User"] = {"validate": "lifeos.permissions.validate_user_roles"}
before_request = ["lifeos.permissions.no_desk_redirect", "lifeos.strict_get.before_request"]

scheduler_events = {
	"daily": ["lifeos.archive.run_daily", "lifeos.api.wiki.refresh_all_health", "lifeos.trash.purge_old"],
	"cron": {"*/5 * * * *": ["lifeos.api.inbox.release_stale_claims", "lifeos.skills.triggers.run_due"],
		# insights: nightly at 06:00 site time (the owner's time zone is the site's, Asia/Kolkata)
		"0 6 * * *": ["lifeos.insights.run_nightly"],
		# set 7: Inbox items left too long, before the morning
		"30 5 * * *": ["lifeos.old_inbox.run_nightly"]},
	# set 8: Google Calendar, read only, hourly
	"hourly": ["lifeos.review.gcal.sync_all"],
}

# the Outbox (set 7) is a record of what happened: an exit naming an area or a record never stops that area from being deleted
ignore_links_on_delete = ["Life Exit"]

fixtures = []
