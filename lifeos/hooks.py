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

permission_query_conditions = {dt: "lifeos.permissions.query_conditions" for dt in SPACE_DOCTYPES}
permission_query_conditions["Life Space"] = "lifeos.permissions.space_query_conditions"
permission_query_conditions["Event"] = "lifeos.permissions.event_query_conditions"

permission_query_conditions["Life View State"] = "lifeos.permissions.view_state_query_conditions"

has_permission = {dt: "lifeos.permissions.has_permission" for dt in SPACE_DOCTYPES}
has_permission["Life Space"] = "lifeos.permissions.space_has_permission"
has_permission["Event"] = "lifeos.permissions.event_has_permission"
has_permission["Life View State"] = "lifeos.permissions.view_state_has_permission"

doc_events = {
	dt: {"validate": "lifeos.org.validate_common", "on_update": "lifeos.org.on_update", "on_trash": "lifeos.org.on_trash"}
	for dt in SPACE_DOCTYPES
}
doc_events["Event"] = {"validate": "lifeos.events.validate_event"}
doc_events["File"] = {"after_insert": "lifeos.files.after_insert"}

scheduler_events = {
	"daily": ["lifeos.archive.run_daily"],
	"cron": {"*/5 * * * *": ["lifeos.api.inbox.release_stale_claims"]},
}

fixtures = []
