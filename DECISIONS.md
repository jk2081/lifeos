# Decisions

Every place where the build chose a default, or differs from `SPEC.md`, with the reason.

## Defaults from section 15

| Question | Default used |
| --- | --- |
| Cycle start date | 5 October 2026, the first Monday of October 2026. Ends 27 December 2026 |
| Unclear journal items | Seeded as written, with `[?]`: "Generic promotion [?]" and "Read three books [?]" |
| Weekly review time | Sunday 18:00, in `Life Settings` |
| Priority codes | Stored as written (I to IV). Lists sort I first, blank last |
| Family or product | One family on one site. No tenant field |
| Folio | Left where it is. `lifeos` reads and writes no Folio DocType |

## Build environment

- **Docker stack.** `docker/docker-compose.yml` starts three containers: `lifeos-bench` (image `frappe/bench`), `lifeos-db` (MariaDB 11.8) and `lifeos-redis`. Volumes and the network are also prefixed `lifeos-`. Host ports are 18000 (web) and 19000 (socketio). The bench lives in the `lifeos-bench-home` volume, outside the repo.
- **Frappe version.** The bench runs Frappe 16.56.0, the same as the live site.
- **The repo is the app.** The repo root is the Frappe app root (`pyproject.toml`, `lifeos/`), so `bench get-app` works on it. The front end is in `frontend/` at the repo root, which is `lifeos/frontend` when the repo is cloned as `apps/lifeos`. This is the layout other `frappe-ui` apps use.
- **Front-end build during this run.** The repo is bind-mounted into the container and the front end is built on the host with Node 24, because `node_modules` holds platform-specific binaries. On a real bench, `bench build --app lifeos` runs the same `yarn build`.
- **Built assets are not committed.** `lifeos/public/frontend/` and `lifeos/www/life.html` are produced by the build, as in other `frappe-ui` apps.
- **Test users.** `lifeos.devtools.setup_users` creates three users on the test site. Their password is generated into the git-ignored `.env`.

## Differences from the spec

- **Permissions apply to the owner too.** `Life Admin` can manage every `Life Space` and its members, but sees records only in spaces he is a member of, as section 3 says for every user. The `Administrator` account is not restricted.
- **`Life Area` is a plain parent link, not a Frappe nested set.** The tree is small and per space, and a nested set would add `lft`/`rgt` upkeep for no gain. A loop check runs on save.
- **Area is not forced on direct creation.** Section 4a says area is required once a record leaves the Inbox. Accepting a proposal requires an area. Quick add and direct API creation allow a blank area, so quick add stays one text box; such records show as Unfiled.
- **`Life Task.status` has one more value, `Carried`.** Section 7 says carry forward marks the old task `Carried`, but the status list in section 4 lacks it.
- **Extra fields.** These were needed to implement rules in the spec:
  - `Life Month Plan Habit.tracked_from` and `tracked_until`: the days a habit counts in that month (section 8, habits added or removed mid-month).
  - `Life Month Plan Goal.carried_from`: the row a carried goal came from.
  - `Life Goal Action.done_on`: the day an action was marked Done, so later weeks stop counting it.
  - `Life Cycle.final_score`, `closed_on` and `Life Goal.final_score`: stored by Close cycle.
  - `Life Inbox Item.finished_on` (for the archive rule) and `preview_image` (the 1600 px preview).
  - `Life Project.is_archived`, `archived_on`.
  - `space` on `Life Proposal`, `Life Link`, `Life Index`, `Life Action Log` and `Life Habit Log`, so the same permission hooks cover them.
  - `inbox_item` on records a proposal can create, so every created record links back to its source.
  - `Life Index.status` and `record_owner`, so list screens need no second query.
- **A completed task has two index rows.** The Timeline must show tasks both when created and when completed, so a Done task gets a second `Life Index` row of kind `Task Done`, dated `completed_on`. Search ignores that row.
- **Events.** Core `Event` shows a record to other users only when `event_type` is Public, and controller hooks can only narrow access. So every event with a `life_space` is saved as Public, and the lifeos hooks narrow it to the members of that space. Events without a `life_space` behave exactly as in core.
- **Time zone.** Dates are stored and shown in the site time zone. The test site is set to Asia/Kolkata; the live site should have the same System Setting.
- **Text size.** The mockups use 14 px interface text on desktop and 15 px on phones. The app follows the mockups for interface text; all long reading text (notes, transcripts, summaries) is 15 px or larger.
- **Two seed commands.** `lifeos.seed.load` loads exactly the seed in section 11. `lifeos.seed.load_demo` adds example ticks, tasks, chats and notes so the screens can be checked against the mockups; it is not the owner's data and has its own remove command.
- **Journal pages do not need an area.** Accepting a Task, Note or Vault Document proposal requires an area. A Journal Page is a record by date and often spans areas, so its area is optional.
- **Area page and tasks.** The area and project pages read `Life Index` for every cross-type list. Their open-task lists read `Life Task` directly, since they show due date, priority and project, which the index does not hold.
- **An area page includes its sub-areas.** The Tea & Coffee page shows records filed under Ghatia, Ghillidary and so on, with chips to narrow to one sub-area, as in the mockup.
- **Quick add reads a date word only at the start or end of the title.** "Buy sun screen" and "Fix the Monday report" stay as typed.
- **Week score rules.** A dropped action is not planned in any week. An action marked Done counts as planned up to the week it was finished and not after. Ticks above `per_week` do not count. The cycle average is the mean of the week scores up to the current week.
- **Ticks and dates.** `journal.tick(action, week, count)` keeps one `Life Action Log` row per action per week, dated today when the week is the current one, else the last day of a past week or the first day of a future one. Unique on action and date as the spec asks.
- **Close cycle default outcome.** A goal still In Progress with no outcome given is stored as Not Achieved.
- **Charts.** Check-in charts are small SVG line charts written for this app (two series on one 0 to 10 axis, colours checked for colour-blind separation in both themes). `frappe-ui` charts would add the whole of ECharts for eight sparklines.
- **Habit targets.** A habit's month target is its tracked days so far, scaled by `days_per_week / 7` and rounded. The percentage is capped at 100.
- **Deleting events.** Core `Event` lets only its creator delete it. `calendar.delete_event` lets any person with Write access to the event's space delete it (never an agent), so the owner can remove an event an agent filed. It checks read permission and space membership itself before deleting.
- **Calendar range.** `calendar.get` returns at most 100 days per call. The year view has its own method, which returns only the entries the year pages show.
- **Week view.** The week view lists each day's items in seven columns. It is not an hour grid; Google Calendar remains the place for that.
- **Links: both rules kept.** Section 4b says links point to records and a rename needs no rewrite; section 9 and the tests say a rename updates the link text. The app does both: `Life Link` stores the target record, rendering shows the target's current title, and a rename also rewrites `[[Old]]` to `[[New]]` in the Markdown of records that point to it.
- **Ambiguous titles.** When two records in a space share a title, the picker inserts `[[Title#id]]`, which pins the link to one record.
- **Link targets.** A link can point to notes, tasks, people, vault documents and chat logs as the spec says, and also to goals and projects.
- **Open items become tasks only for people.** `chats.make_task` is refused for agents, in line with section 5.
- **Library tree size.** `library.tree` returns up to 2,000 light rows so the tree is complete; this is the one list method above the 100-row cap.
- **Graph library.** Cytoscape.js (MIT, actively maintained) draws the graph. Linked records are laid out with its built-in force layout; records with no link yet sit in rows underneath so their labels do not overlap.
- **Graph colours.** Notes, people, goals and vault documents each have a colour, checked for colour-blind separation in both themes. Tasks, chats and projects join the graph only when a link touches them, and share one neutral colour. Every node carries its title, so colour is never the only cue.
- **Search covers journal pages too.** `search.query` searches every `Life Index` row: notes, tasks, inbox items with their transcripts, chat logs, vault documents, journal page transcripts, check-in reflections and month plans.
