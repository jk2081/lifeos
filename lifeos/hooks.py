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
standard_queries = {dt: "lifeos.queries.link_query" for dt in ("Life Area", "Life Tag", "Life Habit", "Life Dimension", "Life Project")}

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
doc_events["Event"] = {"validate": "lifeos.events.validate_event"}
doc_events["File"] = {"after_insert": "lifeos.files.after_insert"}
doc_events["User"] = {"validate": "lifeos.permissions.validate_user_roles"}
before_request = ["lifeos.permissions.no_desk_redirect"]

scheduler_events = {
	"daily": ["lifeos.archive.run_daily", "lifeos.api.wiki.refresh_all_health", "lifeos.trash.purge_old"],
	"cron": {"*/5 * * * *": ["lifeos.api.inbox.release_stale_claims"],
		# insights: nightly at 06:00 site time (the owner's time zone is the site's, Asia/Kolkata)
		"0 6 * * *": ["lifeos.insights.run_nightly"]},
}

fixtures = []
