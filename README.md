# Life OS

A personal operating system on Frappe v16: inbox and review, tasks, calendar, a journal that mirrors a paper journal, areas and goals, a library, a vault, and a chat log. Agents capture and propose; the owner approves.

- The app is `lifeos`, served at `/life`. It needs Frappe Framework v16 and nothing else (no ERPNext). It installs beside Folio and touches none of its DocTypes.
- `docs/DIRECTION.md` is the target design; work comes from GitHub issues (`docs/BUILDING.md`). The original build spec is `docs/history/SPEC.md`. `DECISIONS.md` lists every default and every difference from it. `STATUS.md` says what works, what is stubbed and what is untested.
- This repository holds the owner's personal goals as seed data. Keep it private.

## Install on an existing bench

The bench must run Frappe v16 (built and tested on 16.56.0), with Node 20 or newer and yarn for the front-end build. The front end uses `@framework/ui`, Frappe's own Vue package, straight from `apps/frappe/ui` in the same bench (`link:../../frappe/ui`), so it can only be built with the app at `apps/lifeos` beside `apps/frappe`. After any Frappe update, rebuild the front end (`bench build --app lifeos`) and run `node tools/acceptance.mjs` before using the site.

```
cd ~/frappe-bench
bench get-app https://github.com/jk2081/lifeos.git      # also builds the front end
bench --site SITE install-app lifeos
bench --site SITE migrate
bench build --app lifeos                                 # only if get-app did not build
bench restart                                            # or restart bench start
```

Install creates the roles `Life Admin`, `Life User` and `Life Agent`, the spaces `Private` and `Shared` with the seven areas of life (Career, Health, Relationships, Money, Emotions, Mind, Environment; Career and Health on) and check-in dimensions, the `life_space` field on `Event`, and the database indexes. The user who runs the install (or `Administrator`) owns both spaces. Then:

```
# make yourself the owner, if you installed as Administrator
bench --site SITE execute lifeos.install.set_owner --kwargs "{'user': 'you@example.com'}"

# load the seed of section 11: the Oct to Dec 2026 cycle with its goals, the October plan, the habits
bench --site SITE execute lifeos.seed.load
bench --site SITE execute lifeos.seed.remove            # takes exactly those records out again

# set the site time zone to Asia/Kolkata in System Settings
```

Open `https://SITE/life`. On a phone, use Add to Home Screen to install it as an app.

**Family members.** Create the user in Frappe, then add them to a space under Life OS, Settings → Members. They get the role `Life User`. Make a space of their own for them in Members → Spaces.

**Agents.** Create one user per agent in Frappe, then add it to each space it should work in from Life OS: Settings → Members, **Add member**. If the user has no Life OS role yet, Add member offers agent access and gives it the role `Life Agent` when you confirm (never `Life User` or `Life Admin`). Agents start with Can view; they need Can edit to file captures and proposals. Generate its API key on the user record (Settings → People and agents → Agents links to it). Switch on MCP in System Settings (`Enable MCP`). The agent connects to `/api/v2/mcp` with `Authorization: token <key>:<secret>` and loads its instructions from Life OS: `lifeos.api.skills.get` with the name `lifeos` (and `lifeos-file-work`).

**Google Calendar.** Connect it in Settings > Me > Calendar (Frappe's Google Settings holds the OAuth client). Life OS reads your calendars; it writes only if you choose a calendar under "Write to Google Calendar" (off by default). Then an accepted Event proposal and a goal block from the weekly review are created in that calendar, private, with a link back to Life OS and no guests unless you add emails on the proposal; moving or deleting them in Life OS updates or deletes them in Google, and changes made in Google come back with the hourly read.

*Writing needs the Calendar scope (`https://www.googleapis.com/auth/calendar`) on the Google client, so reconnect after turning it on. A separate Google Cloud project for Life OS with only Calendar scopes is recommended.*

**Scheduler.** The archive job runs daily and stale inbox claims are released every five minutes, so the bench scheduler must be enabled.

### Other commands

| Command | Does |
| --- | --- |
| `bench --site SITE execute lifeos.index.rebuild` | Rebuilds `Life Index` from the records |
| `bench --site SITE execute lifeos.archive.run_daily` | Runs the archive job now |
| `bench --site SITE execute lifeos.demo.load` / `lifeos.demo.remove` | Example records for a test site: ticks, tasks, chats, notes. Not the owner's data |
| `bench --site SITE execute lifeos.loadtest.run` | Test sites only. Seeds 100,000 index rows in 50 spaces for 20 users, times the main reads, removes the rows |
| `bench --site SITE run-tests --app lifeos` | The test suite. Needs `allow_tests` on the site |
| `bench --site SITE execute lifeos.tools.tidy.run` | Reports duplicate files, old jobs and intent-refused items; changes nothing. See below |

### Tidy what was filed before November 2026

Files and jobs filed before issues 6 to 8 may hold the same file several times, a job's inputs beside its outputs, or an item Failed because its intent refused the proposals. The tidy command cleans these up. Run it yourself, in three steps:

1. **Dry run.** It only reports:

   ```
   bench --site SITE execute lifeos.tools.tidy.run
   ```

2. **Read the report.** It lists each duplicate file (the copy kept, the copies and the records that use them), each job with the files that look like inputs (a file also attached to another item, or one a reusable asset holds) and the ones that stay as outputs, and each Failed item it would put back to New. If a file listed as an input is really an output, do not apply; fix that item by hand first. Add `--kwargs "{'space': 'Private'}"` to look at one space.

3. **Apply.**

   ```
   bench --site SITE execute lifeos.tools.tidy.run --kwargs "{'apply': True}"
   ```

   It first takes a backup with files (as `bench backup --with-files`) and stops, changing nothing, if that fails. Then it keeps the oldest copy of each duplicate and points every record at it, removes the copies nothing uses any more, moves input files to reusable assets and links them from the job, and puts the Failed items back to New. Every change is written to `sites/SITE/logs/lifeos_tidy.log` and as a comment on the record it changed, and the run ends with a list of them. Running it again changes nothing. Nothing a record still uses is deleted, and no note, task or proposal is deleted at all.

## Setting up Life OS for a new person

Each person gets their own site. Whoever creates it does these steps once; nothing is loaded for the person (no seed, no demo data) and no password is typed on the command line.

```
cd ~/frappe-bench
bench new-site SITE --admin-password '<a long random password for the site admin>'   # the site's own admin, kept by whoever runs the site
bench --site SITE install-app lifeos
bench --site SITE migrate
bench build --app lifeos                                  # only if get-app did not build
bench --site SITE execute lifeos.install.new_owner --kwargs "{'email': 'person@example.com', 'full_name': 'Their Name'}"
```

`new_owner` makes the person's user with the roles `Life Admin` and `Life User` and makes them the owner of the space `Private`. It sets no password: Frappe sends its own welcome email, and the person chooses a password from the link in it. If the site cannot send email yet, the command says so and still makes the user; send a password reset link to them from the user's record (User → Actions) once outgoing email works. Run it again and nothing changes. Set up outgoing email in Frappe (Email Account) before running it if you want the welcome email to go.

What the person sees: a site with one space (Private, which is not mentioned anywhere), the seven areas of life with Career and Health on, the default rhythms, and no goals, tasks or captures. The first time they open `/life` a short guide of five screens opens: a welcome with the Sources → Brain → Plan picture, their name and time zone, their areas (and parts of an area, such as a business under Career), up to three things on their mind that become tasks with an area guessed for each, and a next step (connect email or calendar, or start using Today). Every screen can be skipped and the guide can be closed at any point; it does not come back. They land on Today, where the "Your setup" card shows level 1 of 6 and the next step. Until something is captured, Today, Brain, Goals and Library each say what will appear there and offer the one action that fills it.

To show the guide again (while the site is still empty), a System Manager opens Settings → Advanced → First-run guide.

## Try the pipeline without a model

`agent/fake_agent.py` uses the same methods a real agent would and returns canned results.

```
export LIFEOS_URL=https://SITE  LIFEOS_API_KEY=...  LIFEOS_API_SECRET=...
python3 agent/fake_agent.py          # claims and processes every New item, then stops
```

Drop a file in the Inbox, run it, and review what it proposes.

## Develop locally

The build used a small Docker stack, with the repo mounted into the bench as `apps/lifeos`.

```
docker compose -f docker/docker-compose.yml up -d
docker exec -d lifeos-bench bash -lc 'cd ~/frappe-bench && bench serve --port 8000'    # http://localhost:18000/life
docker exec lifeos-bench bash -lc 'cd ~/frappe-bench/apps/lifeos/frontend && yarn install && yarn build'   # rebuild the front end, inside the bench
scripts/test.sh                                   # the test suite, short summary
node tools/shot.mjs today=/life --widths 1440,390 # screenshots into screenshots/
node tools/acceptance.mjs                         # walks the acceptance list of SPEC.md section 13
```

`tools/` needs `npm install` once and Google Chrome. Test users come from `lifeos.devtools.setup_users`; their password is in the git-ignored `.env`.

| Path | What it is |
| --- | --- |
| `lifeos/` | The Frappe app: DocTypes in `lifeos/life/doctype`, rules in `lifeos/*.py`, API in `lifeos/api/`, tests in `lifeos/tests/` |
| `frontend/` | The single-page app: Vue 3, Vite, Tailwind, `frappe-ui` |
| `lifeos/skills/lifeos.md`, `agent/fake_agent.py` | The skill a real agent is served (`skills.get`), and the test agent |
| `mockups/` | The approved screen mockups |
| `scripts/gen_doctypes.py` | Regenerates the DocType JSON from one table |
| `scripts/run-issues.sh`, `docs/BUILDING.md`, `docs/ISSUE_RULES.md`, `CLAUDE.md` | How the app is built: GitHub issues, one at a time |

## API

Every method is whitelisted under `lifeos.api`, checks space membership before it reads or writes, and is called as `/api/method/lifeos.api.<module>.<method>` or through the MCP tool `call_method`. List methods take `start` and `page_length` and return at most 100 rows (the Library tree is the one exception, see `DECISIONS.md`). Methods that decide proposals, delete, or change spaces and settings are refused for `Life Agent`. Each method answers one HTTP method: reads are GET (arguments in the query string, lists and objects as JSON) and everything that changes something is POST; the list of GET methods is `frontend/src/lib/getMethods.json`. Over MCP, `call_method` picks the right one.

**`lifeos.api.archive`**

| Method | Arguments | Does |
| --- | --- | --- |
| `archive.set` | `doctype, name, archived=1` | Archive or restore one record. For a goal, the records filed under it follow. |
| `archive.restore` | `doctype, name` | Bring an archived record back. Restoring a goal restores the records archived with it. |
| `archive.list` | `space=None, area=None, start=0, page_length=50` | Archived records by area, newest first, plus archived goals. `tabs` in the answer counts the records of each type under the same filters. |

**`lifeos.api.area`**

| Method | Arguments | Does |
| --- | --- | --- |
| `area.get` | `area, include_archived=0` | An area page: sub-areas, open-ended goals, open tasks, reference notes, documents, recent chats with their open items, the last 20 timeline entries, the goals of the active cycle, and records from other areas that are also filed here. |
| `area.tree` | `space=None, include_archived=0, include_off=0` | Every area of a space with its parent and small counts, for the Areas screen and for pickers: each area of life followed by its parts. Areas that are off are left out unless `include_off=1`. |

**`lifeos.api.calendar`**

| Method | Arguments | Does |
| --- | --- | --- |
| `calendar.get` | `space=None, from_date=None, to_date=None` | Everything on the calendar between two dates (at most 100 days): events, important dates, tasks due and documents expiring. |
| `calendar.year` | `space=None, year=None` | The year view: important dates, all-day and multi-day events, vault expiry dates and the start and end of each 12 Week Year. |
| `calendar.add_event` | `space=None, subject=None, starts_on=None, ends_on=None, all_day=0, description=None` | Create a core Event in a space. It stays in Life OS; only accepted proposals and goal blocks are written to Google, when the person has chosen a calendar. |
| `calendar.delete_event` | `event` | Delete an event of a space the user can write to. |
| `calendar.add_important_date` | `space=None, title=None, day=None, month=None, year=None, kind='Birthday', person=None` | Add a birthday, anniversary or other date that repeats every year. |

**`lifeos.api.chats`**

| Method | Arguments | Does |
| --- | --- | --- |
| `chats.report` | `space=None, from_date=None, to_date=None, group_by='day', start=0, page_length=100` | Chat logs between two dates (default: the last seven days), grouped by day, area or goal, with their open items rolled up. The same records come back under each group_by. |
| `chats.log` | `space=None, title=None, date=None, url=None, assistant='Claude', summary_md=None, open_items=None, area=None, also_in=None` | Record an AI chat. Agents may call this directly: a chat log is a record of what happened, not a proposal. open_items is a list of strings. area and goal take a name or a title. |
| `chats.make_task` | `chat, row` | Turn an open item into a task. People only: an open item becomes a task only when the owner asks. |
| `chats.close_item` | `chat, row, reopen=0` | Close an open item without making a task, or open it again. |

**`lifeos.api.graph`**

| Method | Arguments | Does |
| --- | --- | --- |
| `graph.get` | `space=None, center=None` | Nodes and edges for the graph view. `center` is "DocType/name": the graph is then limited to two steps around that record. |

**`lifeos.api.inbox`**

| Method | Arguments | Does |
| --- | --- | --- |
| `inbox.create_item` | `title=None, source_type='Upload', space=None, raw_text=None, instruction=None, source_url=None` | Create an inbox item. Attach files afterwards with /api/method/upload_file (doctype, docname, is_private=1). |
| `inbox.claim_next` | `space=None` | Claim the oldest New item. Returns it with its file URLs and the filing context, or nothing. |
| `inbox.submit_result` | `item, transcript_md=None, summary_md=None, proposals=None` | Store the transcript, summary and proposals, and set the item To Review. Each proposal is {kind, preview, payload, confidence}. An invalid proposal is refused with a clear error; the rest are kept. |
| `inbox.fail_item` | `item, error=None` | Mark a claimed item Failed, with the reason. |
| `inbox.retry` | `item` | Send a Failed item back to New so an agent picks it up again. Pending proposals of the old attempt are removed. When the process-capture skill is on, it runs again. When the process-capture skill is on, it runs again. |
| `inbox.file_myself` | `item` | The owner takes a capture the Brain could not process: its pending proposals go, it is marked Done, and they file it by hand. People only. |
| `skills.list` / `skills.get` | `space=None` / `name, space=None` | Issue 28: the active skills for the caller's spaces with their version, and one skill's instructions. Agents are served `lifeos` and `lifeos-file-work` here. |
| `skills.run` | `skill, input` | Start a skill whose trigger is a Button on one record, in a background job. |
| `skills.overview`, `detail`, `run_log`, `save`, `create`, `set_active`, `rollback`, `accept_update`, `test`, `add_example`, `save_auto_file` | | Brain > Skills (people; changes are the owner's). |
| `inbox.list` | `space=None, status=None, include_archived=0, start=0, page_length=30` | Inbox items of a space, newest first, with proposal counts. `tabs` in the answer counts the items on each state tab (To Review, Waiting, Failed, Done, all) under the same filters. |
| `inbox.get` | `item` | One inbox item with its files, proposals and the choices for the filing chips. A job's item also has `inputs`, `job_chat` and `wiki_pages`. |
| `inbox.update_transcript` | `item, transcript_md` | Correct the transcript of an item, for example words marked [?]. |

**`lifeos.api.jobs`**

| Method | Arguments | Does |
| --- | --- | --- |
| `context.get` | `space=None, task=None, budget=1500` | The first call of a job (issue 54): the core card and the index; with `task`, the card, the matching index lines and the top pages' summaries within `budget` words. Sensitive pages are left out for an agent unless the space allows them. |
| `context.card` | `space=None` | The core card alone, as Settings, Rules shows it. |
| `context.decide` | `finding, choice` | People only: keep one fact of a wiki contradiction. |
| `jobs.file_job` | `job_id, space=None, title=None, area=None, goal=None, instruction=None, raw_text=None, inputs=None, outputs=None, transcript_md=None, summary_md=None, proposals=None, wiki=None, chat=None, source_system=None` | File a finished piece of work as one inbox item in one call (issue 8, the `lifeos-file-work` skill): outputs on the item, reusable inputs kept once each and linked as inputs, proposals waiting for the owner, wiki pages and a chat log citing the item. The same `job_id` again updates the job. All or nothing: an invalid part refuses the call and names the field. |

**`lifeos.api.journal`**

| Method | Arguments | Does |
| --- | --- | --- |
| `journal.grid` | `cycle=None, space=None` | The 12 Week Year grid of a cycle: goals, actions, ticks per week, week scores and the average. |
| `journal.tick` | `action, week, count` | Set the ticks of a goal action in a week. Returns that week's score. |
| `journal.week_score` | `cycle=None, week=None, space=None` | Done over planned for a week of a cycle. Defaults: the active cycle and its current week. |
| `journal.set_action_status` | `action, status` | Mark an action Done once and for all, Dropped, or Open again. |
| `journal.save_goal` | `goal=None, cycle=None, title=None, area=None, actions=None` | Create or change a goal and its actions. `actions` is a list of {name?, title, per_week}. |
| `journal.delete_goal` | `goal` |  |
| `journal.goals` | `space=None, area=None` | Every goal across every cycle, grouped by cycle: planned, active, then closed, newest first. |
| `goals.list` | `space=None, state='in_progress', horizon=None, area=None, cycle=None, target_from=None, target_to=None, start=0, page_length=50, filters=None, order_by=None, summary=None` | Goals of every type with `tasks_done`, `tasks_counted` and `score` (12 Week Year only), the state `tabs` and a `summary_line`. |
| `goals.create` | `title, horizon=None, space=None, area=None, target_date=None, cycle=None` | Create a goal. The horizon (Long term, Year, 12 weeks, Month) follows the target date and cycle when not given; Year and Month need a target date. Not for agents. |
| `goals.suggest_horizon` | `space=None, target_date=None, cycle=None` | The horizon the goal form sets from the date, and whether 12-week goals follow the quarter. |
| `goals.close` | `goal, outcome, result_note=None` | Set the outcome of a goal that is not a 12-week goal. Not for agents. |
| `goals.add_to_cycle` | `goal, cycle` | Move a goal into the active or a planned 12 Week Year, with its tasks. Not for agents. |
| `goals.picker` | `space=None` | Every goal in progress, ordered by type, for the goal picker on a task. |
| `goals.cycles` | `space=None` | The active and planned 12 Week Years of a space. |
| `journal.goal` | `goal` | A goal page: the goal, its actions, and its history across cycles through the carried_from chain. |
| `journal.close_cycle` | `cycle, outcomes=None` | Close an active cycle after its end date. `outcomes` is a list of {goal, outcome, result_note}. |
| `journal.plan_next_cycle` | `cycle, goals=None, title=None` | Create the next cycle, starting the Monday after this one ends, and carry the chosen goals with their open actions. |
| `journal.start_cycle` | `cycle` | Make a planned cycle the active one. |
| `journal.create_cycle` | `space=None, start_date=None, title=None` | Create the first cycle of a space. It starts on the given date, or next Monday. |
| `journal.month` | `space=None, year=None, month=None, create=0` | The plan of one month: goals, mindsweep, habits with their month so far, and the latest check-in. |
| `journal.save_month_goal` | `plan, row=None, title=None, status=None, area=None, delete=0, move=None` | Add, change, move (the priority order) or remove one Month goal of a month plan. |
| `journal.save_month_text` | `plan, mindsweep_md=None, projects_md=None` |  |
| `journal.carry_month_goal` | `plan, row` | Carry an open Month goal into next month. The old one is marked Carried. |
| `journal.make_task_from_goal` | `plan, row` | Create a Life Task filed under a Month goal. |
| `journal.habits` | `space=None, year=None, month=None` | The habit grid of one month: each tracked habit with its done days, count, target and percentage. |
| `journal.toggle_habit` | `habit, date=None, done=None` | Tick or untick a habit on a day. |
| `journal.habit_library` | `space=None` | Every habit ever tracked in a space. |
| `journal.set_month_habits` | `space=None, year=None, month=None, habits=None` | Set the habits tracked in one month. `habits` is an ordered list of {habit or title, days_per_week}. Other months are untouched. |
| `journal.habits_year` | `space=None, year=None` | Each habit's monthly percentage for the months of a year in which it was tracked. |
| `journal.checkins` | `space=None, start=0, page_length=30` | Check-ins of a space, newest first, with the dimensions and a series per dimension for the charts (midpoint of each range). |
| `journal.save_checkin` | `space=None, date=None, scores=None, reflection_md=None, name=None` | Create or change a check-in. Each score is {dimension, habits, situation, note}; a score is a number or a range such as 2-3. |
| `journal.pages` | `space=None, start=0, page_length=24` | Photographed journal pages by date, newest first. |
| `journal.page_detail` | `page` | One journal page: image, transcript, and the records created from the same inbox item. |
| `journal.save_page_transcript` | `page, transcript_md` |  |
| `journal.weekly_review` | `space=None, week_start=None` | Everything the weekly review gathers for one week (Monday to Sunday). |
| `journal.save_review_note` | `space=None, week_start=None, content_md=''` | Save the owner's notes for a week as a Life Note under the Reviews parent note. |

**`lifeos.api.library`**

| Method | Arguments | Does |
| --- | --- | --- |
| `library.tree` | `space=None, include_archived=0` | Every note of a space with what the tree needs: title, parent, area and goal. At most 100 per call would hide notes, so the tree returns light rows only and is capped at 2,000. |
| `library.get` | `note` | One note with its links resolved to current titles. |
| `library.save` | `note=None, space=None, title=None, content_md=None, area=None, parent_note=None, also_in=None` | Create or change a note. On save its [[Title]] links are parsed and stored in Life Link. |
| `library.versions` | `note` | Saved versions of a note, from Frappe's document versioning. |

**`lifeos.api.links`**

| Method | Arguments | Does |
| --- | --- | --- |
| `links.backlinks` | `doctype, name` | Records that link to this one with [[Title]], plus records tied to it by a field. |
| `links.suggest` | `space=None, text='', limit=12` | Records for the [[ picker: notes, tasks, people, vault documents, chat logs, goals whose title matches. |
| `links.outgoing` | `doctype, name` | The stored links of a record, with each target's current title, for rendering. |

**`lifeos.api.meta`**

| Method | Arguments | Does |
| --- | --- | --- |
| `meta.proposal_schema` |  | For each proposal kind: the allowed payload fields and an example. Call once before the first submission. |
| `meta.space_context` | `space=None` | Areas, people, habits, dimensions and active goals of a space, for filing proposals. `areas` holds the areas of life that are on, each followed by its parts; `areas_off` names those that are off. |

**`lifeos.api.review`**

| Method | Arguments | Does |
| --- | --- | --- |
| `review.decide` | `proposal, decision, payload=None` | Accept or reject one proposal. `payload` may carry edited values. People only. |
| `review.decide_all` | `item, decision` | Accept or reject every pending proposal of an item. A proposal that cannot be accepted stays pending, with its error. |
| `review.update_payload` | `proposal, payload` | Save edited values on a pending proposal without deciding it, for example a changed area chip. |

**`lifeos.api.search`**

| Method | Arguments | Does |
| --- | --- | --- |
| `search.query` | `text, limit=20, space=None, include_archived=0` | Search notes, tasks, inbox items (including transcripts), chat logs, journal pages and vault titles. Only records in spaces the user belongs to are returned. Archived records are left out unless asked for. |

**`lifeos.api.session`**

| Method | Arguments | Does |
| --- | --- | --- |
| `session.boot` |  | Who is logged in, which spaces they can use, and the settings the screens need. |
| `session.counts` | `space=None`, `area=None` | Small numbers for the sidebar, each with the list it opens, and `reviewed`: whether the user has locked a weekly review (Review then joins the sidebar). |

**`lifeos.api.settings`**

| Method | Arguments | Does |
| --- | --- | --- |
| `settings.get` | `space=None` | Everything the Settings screen shows for one space (each area with `goals`, its goals in progress; an area of life counts its parts' too); each space's `members` holds people and agents together, with `is_agent` and `kind` on each row, and `agents` lists every agent across spaces. |
| `settings.save` | `values` | Change Life Settings. Owner only. |
| `settings.save_item` | `kind, space=None, name=None, title=None, parent_area=None, relation=None, sort_order=None, is_archived=None, delete=0, with_children=1, colour=None, is_pinned=None, is_on=None, description=None, move_to=None, part_kind=None, is_focus=None, standard=None, principles=None, focuses=None` | Add, rename, reorder, nest, archive or restore one area, tag, dimension or habit of a space, or a person. Archiving sets `archived_on`. A new area is a part of `parent_area` (one of the seven areas of life) or of Career. The seven cannot be renamed or archived; `is_on` switches an area on or off. Only Life Admin changes areas. Archiving a part that holds open goals or tasks needs `move_to` (its area of life or another of its parts), where they are moved first. `delete=1` is not offered on the screen. Issue 57: `is_focus=1` makes the new area a focus under `parent_area` (a part or an area of life) with its `standard` and `principles`; `part_kind` (Company, Estate, Household, Other) offers that kind's focuses (`settings.focus_offers`), created when Use focuses is on. |
| `settings.create_space` | `space_name, owner_user=None, starter_areas=1` | Create a space, for example a private space for a family member. It gets the seven areas of life with Career and Health on; `starter_areas` adds the check-in dimensions. Owner only. |
| `settings.set_member` | `space, user, access=None, remove=0, grant_role=None` | Add a person or an agent to a space, change their access, or remove them; the one method for space access. Owner only. The user must already exist. Access defaults to `Write` for a person and `Read` for an agent. A user with no Life OS role is refused unless `grant_role` is `Life User` or `Life Agent`; a user who has a Life role keeps it, and `Life Admin` is never given. The space owner cannot be removed and keeps `Write`. |
| `settings.reorder` | `kind, names, parent_area=None` | Put the areas or check-in dimensions in this order in one call; for areas, moving one into `parent_area`'s list nests it there. Areas: Life Admin only. |
| `settings.area_open_work` | `area` | How many open goals and tasks a part holds, and where they can move when it is archived (its area of life, then its other parts). Life Admin only. |
| `settings.set_agent_vault` | `space, allowed` | Let agents open the documents of one space's Vault, or not. Off by default. Life Admin only. |
| `settings.find_users` | `txt='', space=None` | Users who can be added to a space, people and agents alike, each with its `kind` (`Person`, `Agent`, or none yet) and, with `space`, `is_member`. Life Admin only. |

**`lifeos.api.tasks`**

| Method | Arguments | Does |
| --- | --- | --- |
| `tasks.list` | `space=None, status='open', area=None, priority=None, goal=None, month_plan=None, include_archived=0, start=0, page_length=50` | Tasks of a space. status: open, done, all, or one status. Sorted by due date, then priority I first. `status=open_doing` leaves Waiting tasks out. `tabs` in the answer counts the tasks on each state tab (open = Open and Doing, loops, Waiting, Done, all) under the same filters. |
| `tasks.get` | `task` |  |
| `tasks.quick_add` | `text, space=None, area=None, goal=None, due_date=None, priority=None, month_plan=None` | Create a task from one line of text. A date word such as "tomorrow" or "fri" at the start or end sets the due date. |
| `tasks.set_status` | `task, status, waiting_on=None` | Change a task's status. Done fills completed_on. Waiting needs waiting_on. |
| `tasks.update` | `task, values` | Change fields of a task. Only task fields a person edits are accepted. |
| `tasks.confirm_area` | `task, area=None` | Confirm the area the Brain guessed for a task (a task saved without an area gets one, marked `area_guessed` with `area_confidence`), or move it to `area`. Either clears the mark; a move is kept as an area correction in `Life Action Log`. |
| `tasks.carry_forward` | `task` | Copy an open task into next month's plan, mark the old one Carried and set carried_from. |
| `tasks.open_loops` | `space=None, start=0, page_length=50` | Open tasks older than 14 days with no due date. |
| `tasks.decide_stale` | `task, decision` | The three buttons under Decide in the weekly review: do (due this week), carry, drop. |

**`lifeos.api.timeline`**

| Method | Arguments | Does |
| --- | --- | --- |
| `timeline.get` | `space=None, from_date=None, to_date=None, area=None, doctype=None, include_archived=0, start=0, page_length=50` | Every record by day, newest first: inbox items, tasks created and completed, notes, documents, chats, journal pages, check-ins. |

**`lifeos.api.today`**

| Method | Arguments | Does |
| --- | --- | --- |
| `today.get` | `space=None` | Tasks due or overdue, today's events, habits with today's state, items to review, the current week of the active cycle, the open loops count and expiring documents. |

**`lifeos.api.vault`**

| Method | Arguments | Does |
| --- | --- | --- |
| `vault.list` | `space=None, include_archived=0, start=0, page_length=100` | Vault documents of a space, grouped by holder, soonest expiry first. `tabs` in the answer counts all documents, those expiring within 60 days and the expired ones under the same filters. |
| `vault.get` | `document` |  |
| `vault.save` | `document=None, space=None, values=None` | Create or change a vault document. Only the last four characters of a number are ever stored. |
| `vault.set_file` | `document, file_url` | Point the document at a file already uploaded to it with upload_file. |
| `vault.add_person` | `space=None, full_name=None, relation=None` |  |
