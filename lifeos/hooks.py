app_name = "lifeos"
app_title = "Life OS"
app_publisher = "Jai Kejriwal"
app_description = "A personal operating system on Frappe"
app_email = "hello@example.com"
app_license = "mit"

from lifeos.constants import INDEXED_DOCTYPES, SEARCHED_DOCTYPES, SPACE_DOCTYPES

add_to_apps_screen = [
	{"name": "lifeos", "logo": "/assets/lifeos/icons/icon-192.png", "title": "Life OS", "route": "/life",
		"has_permission": "lifeos.permissions.has_app_permission"}
]

after_install = "lifeos.install.after_install"
after_migrate = "lifeos.install.after_migrate"

# issue 50: /life/sw.js is the phone app's service worker
page_renderer = ["lifeos.web.pwa.ServiceWorkerPage"]
website_route_rules = [{"from_route": "/life/<path:app_path>", "to_route": "life"}]

# Link search for the filing DocTypes: the current space and active records only (lifeos/web/queries.py)
standard_queries = {dt: "lifeos.web.queries.link_query" for dt in ("Life Area", "Life Habit", "Life Goal")}

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

# issue 86: a person's mail accounts and the searches made in them are theirs alone
for _dt in ("Life Mail Account", "Life Mail Search"):
	permission_query_conditions[_dt] = "lifeos.permissions.mail_query_conditions"
	has_permission[_dt] = "lifeos.permissions.mail_has_permission"

doc_events = {
	dt: {"validate": "lifeos.life.org.validate_common", "on_update": "lifeos.life.org.on_update", "on_trash": "lifeos.life.org.on_trash"}
	for dt in SPACE_DOCTYPES
}
# the Outbox (set 7): exits are written by these hooks only
for _dt in ("Life Task", "Life Goal", "Life Inbox Item", "Life Note"):
	for _event, _fn in (("on_update", "on_update"), ("after_insert", "after_insert"), ("on_trash", "on_trash")):
		_have = doc_events[_dt].get(_event)
		doc_events[_dt][_event] = [*([_have] if isinstance(_have, str) else _have or []), f"lifeos.brain.outbox.{_fn}"]
# set 8: a reading confirmed or rejected anywhere clears its finding in the weekly review
_have = doc_events["Life Goal Reading"].get("on_update")
doc_events["Life Goal Reading"]["on_update"] = [*([_have] if isinstance(_have, str) else _have or []), "lifeos.review.findings.reading_changed"]
doc_events["Event"] = {"validate": "lifeos.calendar.events.validate_event",
	"on_update": ["lifeos.review.gcal_write.event_updated", "lifeos.calendar.key_dates.after_save"],
	"on_trash": "lifeos.review.gcal_write.event_trashed"}
# issue 31: a goal block already written to Google follows its task
for _event, _fn in (("on_update", "task_updated"), ("on_trash", "task_trashed")):
	doc_events["Life Task"][_event] = [*([doc_events["Life Task"][_event]] if isinstance(doc_events["Life Task"][_event], str) else doc_events["Life Task"][_event]), f"lifeos.review.gcal_write.{_fn}"]
# issue 28: skills start from document events, in a background job (lifeos/skills/triggers.py)
doc_events["Life Inbox Item"]["after_insert"] = [*doc_events["Life Inbox Item"]["after_insert"], "lifeos.skills.triggers.capture_created"]
for _dt in ("Life Task", "Life Goal", "Life Note"):
	doc_events[_dt]["on_update"] = [*([doc_events[_dt]["on_update"]] if isinstance(doc_events[_dt]["on_update"], str) else doc_events[_dt]["on_update"]),
		"lifeos.skills.triggers.record_changed"]
# issue 111: a page that goes takes its links and pins with it
for _dt in ("Life Person", "Life Area"):
	_have = doc_events[_dt].get("on_trash")
	doc_events[_dt]["on_trash"] = [*([_have] if isinstance(_have, str) else _have or []), "lifeos.library.subjects.on_trash"]
# issue 54: the core card and the index are rebuilt when a record they are made from changes
for _dt in ("Life Note", "Life Person", "Life Goal", "Life Area", "Life Cycle", "Life Space", "Life Settings"):
	for _event in ("on_update", "after_insert", "on_trash"):
		_have = doc_events.setdefault(_dt, {}).get(_event)
		doc_events[_dt][_event] = [*([_have] if isinstance(_have, str) else _have or []), "lifeos.agents.context.changed"]
# issue 98: Frappe queues a saved record for Global Search and its scheduler writes the queue every 15 minutes; a job writes it at once
for _dt in SEARCHED_DOCTYPES:
	_have = doc_events.setdefault(_dt, {}).get("on_update")
	doc_events[_dt]["on_update"] = [*([_have] if isinstance(_have, str) else _have or []), "lifeos.library.globalsearch.index_soon"]
doc_events["File"] = {"after_insert": "lifeos.library.files.after_insert"}
# issue 32: an email read from the email-in mailbox becomes a capture
doc_events["Communication"] = {"on_update": "lifeos.brain.email_in.communication_received"}
# issue 7: a Life OS record's file is stored once per space by content, and the same file sent again is not attached twice
extend_doctype_class = {"File": ["lifeos.library.files.LifeFile"]}
override_whitelisted_methods = {"upload_file": "lifeos.library.files.upload_file", "frappe.handler.upload_file": "lifeos.library.files.upload_file",
	"frappe.integrations.doctype.connected_app.connected_app.callback": "lifeos.api.connections.oauth_callback"}
doc_events["User"] = {"validate": "lifeos.permissions.validate_user_roles"}
before_request = ["lifeos.permissions.no_desk_redirect", "lifeos.web.strict_get.before_request", "lifeos.web.gone_names.before_request"]

scheduler_events = {
	"daily": ["lifeos.library.archive.run_daily", "lifeos.api.wiki.refresh_all_health", "lifeos.library.trash.purge_old", "lifeos.library.wiki_check.run_weekly"],
	"cron": {"*/5 * * * *": ["lifeos.api.inbox.release_stale_claims", "lifeos.skills.triggers.run_due",
		"lifeos.skills.triggers.route_unclaimed"],
		# issue 86: the daily email digest (and the Sunday roll-up) is made at 07:00 site time; Gmail is searched live, never copied
		"0 7 * * *": ["lifeos.mail.digest.run_daily"],
		# issue 111: the briefs of pages with something new, after the digest has linked the day's mail; once a day each, within the month's cap
		"30 7 * * *": ["lifeos.library.briefs.run_daily", "lifeos.library.pins.purge_visits"],
		# insights: nightly at 06:00 site time (the owner's time zone is the site's, Asia/Kolkata)
		"0 6 * * *": ["lifeos.review.insights.run_nightly"],
		# set 7: Inbox items left too long, before the morning
		"30 5 * * *": ["lifeos.brain.old_inbox.run_nightly"]},
	# set 8: Google Calendar, read only, hourly
	"hourly": ["lifeos.review.gcal.sync_all", "lifeos.api.connections.clean_abandoned", "lifeos.updater.status.check_hourly"],
}

# the Outbox (set 7) is a record of what happened: an exit naming an area or a record never stops that area from being deleted
ignore_links_on_delete = ["Life Exit"]

fixtures = []

# Frappe Flow (issue 108): Ask's tools and the "Life OS" agent, for trying at /flow
flow_tools = [
	"lifeos.ai.flow.search",
	"lifeos.ai.flow.read_page",
	"lifeos.ai.flow.get_record",
	"lifeos.ai.flow.list_records",
	"lifeos.ai.flow.counts",
	"lifeos.ai.flow.cycle_state",
	"lifeos.ai.flow.timeline",
	"lifeos.ai.flow.mail_search",
	"lifeos.ai.flow.mail_thread",
	"lifeos.ai.flow.mail_list_threads",
	"lifeos.ai.flow.digests_read",
	"lifeos.ai.flow.save_attachment",
	"lifeos.ai.flow.create_page",
	"lifeos.ai.flow.update_page",
	"lifeos.ai.flow.add_person",
	"lifeos.ai.flow.save_note",
	"lifeos.ai.flow.make_task",
	"lifeos.ai.flow.add_event",
]
flow_agents = ["lifeos.ai.flow.agents"]
