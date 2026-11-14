# Life OS

A personal operating system on Frappe v16: inbox and review, tasks, calendar, a journal that mirrors a paper journal, areas and projects, a library, a vault, and a chat log. Agents capture and propose; the owner approves.

- The app is `lifeos`, served at `/life`. It needs Frappe Framework v16 and nothing else (no ERPNext). It installs beside Folio and touches none of its DocTypes.
- `SPEC.md` is the build spec. `DECISIONS.md` lists every default and every difference from it. `STATUS.md` says what works, what is stubbed and what is untested.
- This repository holds the owner's personal goals as seed data. Keep it private.

## Install on an existing bench

The bench must run Frappe v16 (built and tested on 16.56.0), with Node 20 or newer and yarn for the front-end build.

```
cd ~/frappe-bench
bench get-app https://github.com/jk2081/lifeos.git      # also builds the front end
bench --site SITE install-app lifeos
bench --site SITE migrate
bench build --app lifeos                                 # only if get-app did not build
bench restart                                            # or restart bench start
```

Install creates the roles `Life Admin`, `Life User` and `Life Agent`, the spaces `Private` and `Shared` with their areas and check-in dimensions, the `life_space` field on `Event`, and the database indexes. The user who runs the install (or `Administrator`) owns both spaces. Then:

```
# make yourself the owner, if you installed as Administrator
bench --site SITE execute lifeos.install.set_owner --kwargs "{'user': 'you@example.com'}"

# load the seed of section 11: the Oct to Dec 2026 cycle with its goals, the October plan, the habits
bench --site SITE execute lifeos.seed.load
bench --site SITE execute lifeos.seed.remove            # takes exactly those records out again

# set the site time zone to Asia/Kolkata in System Settings
```

Open `https://SITE/life`. On a phone, use Add to Home Screen to install it as an app.

**Family members.** Create the user in Frappe, then add them to a space under Life OS, Settings, Spaces and members. They get the role `Life User`. Create a space of their own for them in the same place.

**Agents.** Create one user per agent with only the role `Life Agent`, add it to the spaces it should work in, and generate its API key on the user record. Switch on MCP in System Settings (`Enable MCP`). The agent connects to `/api/v2/mcp` with `Authorization: token <key>:<secret>` and loads `agent/SKILL.md` as its instructions.

**Google Calendar.** Connect it in Frappe: Google Settings, then a Google Calendar record for your user. Life OS has no sync code of its own; events made in the app are core `Event` records, which Frappe pushes to Google.

**Scheduler.** The archive job runs daily and stale inbox claims are released every five minutes, so the bench scheduler must be enabled.

### Other commands

| Command | Does |
| --- | --- |
| `bench --site SITE execute lifeos.index.rebuild` | Rebuilds `Life Index` from the records |
| `bench --site SITE execute lifeos.archive.run_daily` | Runs the archive job now |
| `bench --site SITE execute lifeos.demo.load` / `lifeos.demo.remove` | Example records for a test site: ticks, tasks, chats, notes. Not the owner's data |
| `bench --site SITE execute lifeos.loadtest.run` | Test sites only. Seeds 100,000 index rows in 50 spaces for 20 users, times the main reads, removes the rows |
| `bench --site SITE run-tests --app lifeos` | The test suite. Needs `allow_tests` on the site |

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
cd frontend && npm install && npx vite build      # rebuild the front end
scripts/test.sh                                   # the test suite, short summary
node tools/shot.mjs today=/life --widths 1440,390 # screenshots into screenshots/
node tools/acceptance.mjs                         # walks the acceptance list of SPEC.md section 13
```

`tools/` needs `npm install` once and Google Chrome. Test users come from `lifeos.devtools.setup_users`; their password is in the git-ignored `.env`.

| Path | What it is |
| --- | --- |
| `lifeos/` | The Frappe app: DocTypes in `lifeos/life/doctype`, rules in `lifeos/*.py`, API in `lifeos/api/`, tests in `lifeos/tests/` |
| `frontend/` | The single-page app: Vue 3, Vite, Tailwind, `frappe-ui` |
| `agent/SKILL.md`, `agent/fake_agent.py` | Instructions for a real agent, and the test agent |
| `mockups/` | The approved screen mockups |
| `scripts/gen_doctypes.py` | Regenerates the DocType JSON from one table |
| `scripts/start-build.sh`, `START_PROMPT.md`, `CONTINUE_PROMPT.md`, `CLAUDE.md` | The unattended build that produced this app |

## API

Every method is whitelisted under `lifeos.api`, checks space membership before it reads or writes, and is called as `/api/method/lifeos.api.<module>.<method>` or through the MCP tool `call_method`. List methods take `start` and `page_length` and return at most 100 rows (the Library tree is the one exception, see `DECISIONS.md`). Methods that decide proposals, delete, or change spaces and settings are refused for `Life Agent`.

**`lifeos.api.archive`**

| Method | Arguments | Does |
| --- | --- | --- |
| `archive.set` | `doctype, name, archived=1` | Archive or restore one record. For a project, its records follow. |
| `archive.restore` | `doctype, name` | Bring an archived record back. Restoring a project restores the records archived with it. |
| `archive.list` | `space=None, area=None, start=0, page_length=50` | Archived records by area, newest first, plus archived projects. |

**`lifeos.api.area`**

| Method | Arguments | Does |
| --- | --- | --- |
| `area.get` | `area, include_archived=0` | An area page: sub-areas, active projects, open tasks, reference notes, documents, recent chats with their open items, the last 20 timeline entries, the goals of the active cycle, and records from other areas that are also filed here. |
| `area.tree` | `space=None, include_archived=0` | Every area of a space with its parent and small counts, for the Areas screen and for pickers. |

**`lifeos.api.calendar`**

| Method | Arguments | Does |
| --- | --- | --- |
| `calendar.get` | `space=None, from_date=None, to_date=None` | Everything on the calendar between two dates (at most 100 days): events, important dates, tasks due and documents expiring. |
| `calendar.year` | `space=None, year=None` | The year view: important dates, all-day and multi-day events, vault expiry dates and the start and end of each 12 Week Year. |
| `calendar.add_event` | `space=None, subject=None, starts_on=None, ends_on=None, all_day=0, description=None` | Create a core Event in a space. If the user has connected Google Calendar, the built-in integration pushes it there. |
| `calendar.delete_event` | `event` | Delete an event of a space the user can write to. |
| `calendar.add_important_date` | `space=None, title=None, day=None, month=None, year=None, kind='Birthday', person=None` | Add a birthday, anniversary or other date that repeats every year. |

**`lifeos.api.chats`**

| Method | Arguments | Does |
| --- | --- | --- |
| `chats.report` | `space=None, from_date=None, to_date=None, group_by='day', start=0, page_length=100` | Chat logs between two dates (default: the last seven days), grouped by day, area or project, with their open items rolled up. The same records come back under each group_by. |
| `chats.log` | `space=None, title=None, date=None, url=None, assistant='Claude', summary_md=None, open_items=None, area=None, project=None, tags=None, also_in=None` | Record an AI chat. Agents may call this directly: a chat log is a record of what happened, not a proposal. open_items is a list of strings. area, project and tags take a name or a title. |
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
| `inbox.retry` | `item` | Send a Failed item back to New so an agent picks it up again. Pending proposals of the old attempt are removed. |
| `inbox.list` | `space=None, status=None, include_archived=0, start=0, page_length=30` | Inbox items of a space, newest first, with proposal counts. |
| `inbox.get` | `item` | One inbox item with its files, proposals and the choices for the filing chips. |
| `inbox.update_transcript` | `item, transcript_md` | Correct the transcript of an item, for example words marked [?]. |

**`lifeos.api.journal`**

| Method | Arguments | Does |
| --- | --- | --- |
| `journal.grid` | `cycle=None, space=None` | The 12 Week Year grid of a cycle: goals, actions, ticks per week, week scores and the average. |
| `journal.tick` | `action, week, count` | Set the ticks of a goal action in a week. Returns that week's score. |
| `journal.week_score` | `cycle=None, week=None, space=None` | Done over planned for a week of a cycle. Defaults: the active cycle and its current week. |
| `journal.set_action_status` | `action, status` | Mark an action Done once and for all, Dropped, or Open again. |
| `journal.save_goal` | `goal=None, cycle=None, title=None, area=None, project=None, actions=None` | Create or change a goal and its actions. `actions` is a list of {name?, title, per_week}. |
| `journal.delete_goal` | `goal` |  |
| `journal.goals` | `space=None, area=None` | Every goal across every cycle, grouped by cycle: planned, active, then closed, newest first. |
| `journal.goal` | `goal` | A goal page: the goal, its actions, and its history across cycles through the carried_from chain. |
| `journal.close_cycle` | `cycle, outcomes=None` | Close an active cycle after its end date. `outcomes` is a list of {goal, outcome, result_note}. |
| `journal.plan_next_cycle` | `cycle, goals=None, title=None` | Create the next cycle, starting the Monday after this one ends, and carry the chosen goals with their open actions. |
| `journal.start_cycle` | `cycle` | Make a planned cycle the active one. |
| `journal.create_cycle` | `space=None, start_date=None, title=None` | Create the first cycle of a space. It starts on the given date, or next Monday. |
| `journal.month` | `space=None, year=None, month=None, create=0` | The plan of one month: goals, mindsweep, habits with their month so far, and the latest check-in. |
| `journal.save_month_goal` | `plan, row=None, title=None, priority=None, status=None, area=None, delete=0` | Add, change or remove one goal of a month plan. |
| `journal.save_month_text` | `plan, mindsweep_md=None, projects_md=None` |  |
| `journal.carry_month_goal` | `plan, row` | Carry an open month goal into next month's plan. The old one is marked Carried. |
| `journal.make_task_from_goal` | `plan, row` | Create a Life Task linked to a month goal. |
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
| `library.tree` | `space=None, include_archived=0` | Every note of a space with what the tree needs: title, parent, area and project. At most 100 per call would hide notes, so the tree returns light rows only and is capped at 2,000. |
| `library.get` | `note` | One note with its links resolved to current titles. |
| `library.save` | `note=None, space=None, title=None, content_md=None, area=None, project=None, parent_note=None, also_in=None, tag_ids=None` | Create or change a note. On save its [[Title]] links are parsed and stored in Life Link. |
| `library.versions` | `note` | Saved versions of a note, from Frappe's document versioning. |

**`lifeos.api.links`**

| Method | Arguments | Does |
| --- | --- | --- |
| `links.backlinks` | `doctype, name` | Records that link to this one with [[Title]], plus records tied to it by a field. |
| `links.suggest` | `space=None, text='', limit=12` | Records for the [[ picker: notes, tasks, people, vault documents, chat logs, goals and projects whose title matches. |
| `links.outgoing` | `doctype, name` | The stored links of a record, with each target's current title, for rendering. |

**`lifeos.api.meta`**

| Method | Arguments | Does |
| --- | --- | --- |
| `meta.proposal_schema` |  | For each proposal kind: the allowed payload fields and an example. Call once before the first submission. |
| `meta.space_context` | `space=None` | Areas, projects, tags, people, habits, dimensions and active goals of a space, for filing proposals. |

**`lifeos.api.projects`**

| Method | Arguments | Does |
| --- | --- | --- |
| `projects.list` | `space=None, include_done=0` | Every active project of a space, grouped by area. On hold projects are included; done ones on request. |
| `projects.get` | `project` | A project page: its tasks, notes, documents and chats. |
| `projects.completion_info` | `project` | How many records will move to the Archive when the project is completed. Shown in the confirm dialog. |
| `projects.set_status` | `project, status` | Change a project's status. Done or Dropped archives it at once with every record whose project points to it. |

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
| `session.counts` | `space=None` | Small numbers for the sidebar. |

**`lifeos.api.settings`**

| Method | Arguments | Does |
| --- | --- | --- |
| `settings.get` | `space=None` | Everything the Settings screen shows for one space. |
| `settings.save` | `values` | Change Life Settings. Owner only. |
| `settings.save_item` | `kind, space=None, name=None, title=None, parent_area=None, relation=None, sort_order=None, is_archived=None, delete=0` | Add, rename, reorder or remove one area, tag, dimension, habit or person of a space. |
| `settings.create_space` | `space_name, owner_user=None, starter_areas=1` | Create a space, for example a private space for a family member, with the starter areas. Owner only. |
| `settings.set_member` | `space, user, access='Write', remove=0` | Add a user to a space, change their access, or remove them. Owner only. The user must already exist. |

**`lifeos.api.tasks`**

| Method | Arguments | Does |
| --- | --- | --- |
| `tasks.list` | `space=None, status='open', area=None, project=None, tag=None, priority=None, goal=None, month_plan=None, include_archived=0, start=0, page_length=50` | Tasks of a space. status: open, done, all, or one status. Sorted by due date, then priority I first. |
| `tasks.get` | `task` |  |
| `tasks.quick_add` | `text, space=None, area=None, project=None, goal=None, due_date=None, priority=None, month_plan=None` | Create a task from one line of text. A date word such as "tomorrow" or "fri" at the start or end sets the due date. |
| `tasks.set_status` | `task, status, waiting_on=None` | Change a task's status. Done fills completed_on. Waiting needs waiting_on. |
| `tasks.update` | `task, values` | Change fields of a task. Only task fields a person edits are accepted. |
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
| `vault.list` | `space=None, include_archived=0, start=0, page_length=100` | Vault documents of a space, grouped by holder, soonest expiry first. |
| `vault.get` | `document` |  |
| `vault.save` | `document=None, space=None, values=None` | Create or change a vault document. Only the last four characters of a number are ever stored. |
| `vault.set_file` | `document, file_url` | Point the document at a file already uploaded to it with upload_file. |
| `vault.add_person` | `space=None, full_name=None, relation=None` |  |
