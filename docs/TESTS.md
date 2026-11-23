# Tests by place

Unit tests are in `lifeos/tests/test_<place>.py` (run one with `scripts/test.sh test_goals`; the set-up several modules share is in `base.py` and `helpers.py`). Acceptance checks are in `tools/acceptance/<place>.mjs`, numbered by place (`TODAY.3`): `node tools/acceptance.mjs --only=TODAY` runs a place, `--only=TODAY.3` one check, `--part=today` a place with the clean-up (one job of CI). Every feature has at least one unit test and one acceptance check, listed here under its place. New tests go into the file of their place (`docs/ISSUE_RULES.md`); keep this page in step.

## Unit tests

| File | What it covers |
| --- | --- |
| `test_capture.py` | A capture arriving: items, claiming, results and review decisions, files stored once, re-filing, the item page, the phone's captures, email forwarded to the email-in address |
| `test_brain.py` | The Brain: who processes a capture, Needs you, Activity, Sources, old items, Reset (now Settings > Data), Someday, the wiki and its rules, chat imports, task areas |
| `test_skills.py` | The skills engine and every built-in skill: runner, examples, lessons, versions, the one gateway for model calls (cost and caps), Ask, insights |
| `test_goals.py` | Goals: cycles, the grid, habits, Month goals, goals serving goals, readings, edit and "Done when", focuses, horizons, Someday |
| `test_tasks.py` | Tasks: quick add, lists, filters and views, All tasks, No goal, the Outbox, tab counts |
| `test_today.py` | Today: tasks only, rhythm banners, the Week, Month and Year views |
| `test_review.py` | The weekly, monthly and 12-week reviews |
| `test_library.py` | Library: notes, the vault, search, the graph, Everything, files, the sensitive mark |
| `test_people.py` | People and organisations, the person page and its mentions |
| `test_settings.py` | The data model, areas, rhythms, the first run and the guide, the setup ladder, one space |
| `test_permissions.py` | Spaces and members, what each kind of user sees, every read refusing another space's records, the scan guard, no cache in `frappe.local`, input types, every `frappe.throw` titled, the conventions of every whitelisted method, navigation, the router, no old code left |
| `test_calendar.py` | The calendar, reading Google Calendar, writing events and goal blocks to it |
| `test_gmail.py` | Life OS reading Gmail: connect, fetch, triage, one capture per thread |
| `test_agents.py` | What an agent calls: `file_job`, the context card and index, the weekly wiki check |
| `test_load.py` | The load test at the size of section 4b |

## Skills

Every skill the app ships has a unit test, and `SETTINGS.38` opens Brain > Skills, finds the card of each built-in skill and runs Test on it: the recorded examples of the skills that have them must pass.

| Skill | Unit test | Acceptance |
| --- | --- | --- |
| `process-capture` | `test_brain.TestRouting`, `test_skills.TestExamples` | `SETTINGS.38` |
| `guess-area` | `test_brain` (task areas), `test_skills.TestNewSkillsExamples` | `SETTINGS.38` |
| `tidy-backlog` | `test_skills.TestTidyBacklog` | `SETTINGS.38` |
| `plan-week` | `test_skills.TestPlanWeek` | `SETTINGS.38` |
| `notice` | `test_skills.TestNotice` | `SETTINGS.38` |
| `define-goal` | `test_skills.TestDefineGoal` | `SETTINGS.38` |
| `reflect` | `test_review` (Reflect), `test_skills.TestNewSkillsExamples` | `SETTINGS.38` |
| `ask` | `test_skills.TestAnswer` | `SETTINGS.38` |
| `check-wiki` | `test_agents.TestWeeklyCheck` | `SETTINGS.38` |
| `triage-email` | `test_gmail.TestGmail` | `SETTINGS.38` |
| `improve-skill` | `test_skills.TestCorrections` | `SETTINGS.38` |
| `lifeos` | `test_skills.TestServing` | `SETTINGS.38` |
| `lifeos-file-work` | `test_skills.TestServing` | `SETTINGS.38` |

## Acceptance checks by place

### Today (`tools/acceptance/today.mjs`, 29 checks)

Day, Week, Month and Year, the numbers that open lists, Reset, rhythm banners, the first-run guide, Today's tasks.

Unit tests: `test_today.py` (Today's tasks, banners, the year, the week's goal work); `test_settings.py` (first run, the guide); `test_tasks.py` (counts, Reset, Someday)

- `TODAY.1` Log in, open /life, Today is filled from seed data
- `TODAY.2` Add a birthday and see it on the calendar this year and next
- `TODAY.3` Vault document expiring in 30 days shows a badge on Today
- `TODAY.4` every number is a door, and the list count equals the number clicked
- `TODAY.5` Today: no Open band, the list of tasks in order, the rail; Someday never shows; the amber dot on the Week's Reset button
- `TODAY.6` counts: every number on Today, Reset, Someday and the sidebar opens a list with exactly that many rows
- `TODAY.7` Insights: rules make Stuck, 12 Week Year and Habit insights from seeded data; a dismissed one does not return; a snoozed one returns after its date; at most 12 new a day
- `TODAY.8` Reset: each rule batch finds its seeded items; a batch changes exactly those and Undo reverts; one by one with the keys; Delete then Restore from the trash; stuck task…
- `TODAY.9` 390 px: a rhythm banner shows on Today on its day and Skip hides it
- `TODAY.10` Rhythm banners: the weekly review, Plan <month>, Plan your next 12 weeks and Close this cycle each show on Today on their day (the clock moved with at=); Skip hides ea…
- `TODAY.11` Week shows this week's calendar events and due tasks on the right days, and a day opens Day
- `TODAY.12` Month shows events and due tasks on the right dates; next and previous months work
- `TODAY.13` Year shows a bar for each goal in its area's lane, and one tick per weekly review with the right count
- `TODAY.14` an area that is off has no lane
- `TODAY.15` clicking a goal opens the goal; clicking a month opens Month
- `TODAY.16` Week, Month and Year have no sideways scroll
- `TODAY.17` the first visit opens the guide; skipping every step lands on Today and the guide does not return
- `TODAY.18` the guide shows one screen at a time and each screen fits the phone
- `TODAY.19` Today, Brain, Goals and Library on a fresh site each show their empty state with one action
- `TODAY.20` going through the guide sets the name and time zone, switches on a third area and turns three typed things into tasks with areas
- `TODAY.21` after the guide the ladder card shows level 1 and connect a source
- `TODAY.22` on an empty site Today shows its empty state and no Open band
- `TODAY.23` cycle goals with lead actions and no task this week are not rows on Today
- `TODAY.24` a task planned this week under a cycle goal shows with its goal, and ticking it records the lead action's tick
- `TODAY.25` with three cycle goals planned for nothing, one line says so and Plan opens Goals > Cycles
- `TODAY.26` the Open band is gone from Today; the habits row shows today's habits by name and ticks them
- `TODAY.27` no link on Today goes to an old route, and each opens where it says
- `TODAY.28` the order is Needs you, the list, habits, then the rail
- `TODAY.29` each moved number is in its new place with the count the old card had (All tasks, Goals, Library, Brain Activity)

### Brain (`tools/acceptance/brain.mjs`, 47 checks)

Capture and the Brain's filing, Needs you, Activity, Sources, the item page, jobs from agents, Ask, and the checks that need the records of the first photo capture.

Unit tests: `test_capture.py`; `test_brain.py`; `test_gmail.py`; `test_agents.py`

- `BRAIN.1` Journal photo: agent submits 5 proposals; accept 3, edit 1, reject 1; records link back; the journal page is a note in Library > Notes
- `BRAIN.2` PDF with "summarise and extract to-dos" gives tasks through review
- `LIBRARY.1` Note with a [[link]]: the target shows the backlink, both are in the graph
- `BRAIN.3` Search for a word in a transcript finds the inbox item
- `BRAIN.4` A second user who is only in Shared sees nothing from Private, on any screen or in search
- `BRAIN.5` At review, change the area with one tap and add a second: the record is under both areas in the lens
- `TODAY.4` Timeline shows everything captured on one day
- `BRAIN.6` Security: the family and agent users land on /life from /app; the agent works without desk access and cannot read a closed Vault
- `BRAIN.7` Security: the PWA manifest and icons are served; an agent cannot decide or delete
- `BRAIN.8` Ask: from Today, Today under an area, a goal page and a record pane, with the scope of the screen; citations open their records; Make task only when clicked; th…
- `BRAIN.9` Ask: with no key it says it is not set up; at the cap it refuses and shows the spend; the family user never gets a Private record; a Vault document is never sent while…
- `BRAIN.10` streams: chats.log twice with one external_id leaves one log; importing the Claude and ChatGPT fixtures creates the expected logs, and again creates and updates none
- `BRAIN.11` an Email Digest renders its sections and Open in Gmail buttons; the proposed reply task shows Open in Gmail
- `BRAIN.12` The fake agent runs end to end with the goal-based API: tasks it proposes are filed under the open-ended goal of their area
- `BRAIN.13` an item filed twice with the same file shows one attachment; with two versions it shows "2 versions" and opens the older one
- `BRAIN.14` a job filed (twice) with the fake agent is one item in the Inbox; its page shows Inputs, Outputs, the summary and the proposals
- `BRAIN.15` an item with a file, a summary, 2 waiting proposals and 1 accepted task shows every section right
- `BRAIN.16` accepting a proposal on the item page moves it to What came of it without a reload
- `BRAIN.17` the item page opens from the Inbox list, from Library and from search
- `BRAIN.18` a user without access to the item's space gets "Not found" rather than its content
- `BRAIN.19` the item page is one column with no sideways scroll
- `BRAIN.20` on an empty space Needs you says what will appear and offers + Capture
- `BRAIN.21` with 3 waiting captures (one with two possible areas) Needs you shows 3 rows with their best guesses and reasons
- `BRAIN.22` Keep accepts the proposal, the row leaves, and the record exists with the guessed area
- `BRAIN.23` picking the second of two area chips files it there
- `BRAIN.24` Drop discards it and it appears in the Outbox as Discarded
- `BRAIN.25` Done, file all files every row in one go
- `BRAIN.26` with more than 7 waiting, 7 show and the rest come in as rows are cleared
- `BRAIN.27` the two numbers match the captures of the last 24 hours
- `BRAIN.28` each row stacks at 390 px, with Keep, Change and Drop reachable and no sideways scroll
- `BRAIN.29` an agent's proposal with alt_area shows two area chips; picking the second files it in that area
- `BRAIN.30` a Reading proposal shows as Read later
- `BRAIN.31` a capture that failed is listed under Unfiled with Retry, never lost
- `BRAIN.32` on a space with nothing captured Activity says what will appear and offers + Capture
- `BRAIN.33` a capture filed on its own today shows under Today with its area and a link to the record
- `BRAIN.34` the source filter narrows the feed to that source
- `BRAIN.35` a failed capture shows its reason and Retry puts it back in the queue
- `BRAIN.36` the Outbox piles in Activity show the same numbers as the Outbox
- `BRAIN.37` the feed is one column and nothing scrolls sideways
- `BRAIN.38` with no source connected Sources says what will appear and offers Add a source
- `BRAIN.39` connected sources show with this week's counts, matching the captures in the database
- `BRAIN.40` switching Hermes off makes create_item from hermes fail with a clear message; switching it on again works
- `BRAIN.41` a Coming tile cannot be switched on
- `BRAIN.42` opening a source shows its default intent, area and goal, and saving changes what create_item uses
- `BRAIN.43` the cards sit in a grid and nothing scrolls sideways
- `BRAIN.44` Sources offers Connect Gmail, a connected mailbox shows its week's counts and "Processed by: the Brain", every card has a Processed by line
- `BRAIN.45` a capture the Brain could not process is in Needs you with Retry and File it myself; File it myself takes it out

### Goals (`tools/acceptance/goals.mjs`, 71 checks)

By area, All tasks, No goal, Cycles and the 12 Week Year, the goal page and its edit form, focuses, horizons, Someday.

Unit tests: `test_goals.py`; `test_tasks.py` (All tasks, No goal, task filters and views)

- `GOALS.1` Tick a habit at phone width and see the month count change
- `GOALS.2` Tick week cells in the 12 Week Year grid and see the week score change
- `GOALS.3` Carry an open October goal into November: the month card of Cycles shows it with where it came from
- `GOALS.4` Tea & Coffee in the lens: Plan and Library show its open-ended goals, tasks, notes and chats together
- `GOALS.5` Complete an open-ended goal: it and its records move to Archive. Restore it
- `GOALS.6` state tabs: each count equals the rows its tab shows, with and without another filter; links land on their tab
- `GOALS.7` a goal's page: each tab opens with its count, its list matches the main screen, reload stays, a row opens the pane in the tab
- `GOALS.8` goals of every type: task figure, archive keeps it, tabs, score blank, add to a cycle, family sees none
- `GOALS.9` Someday: a task, an open-ended goal with two tasks, a goal and an idea leave Today, Tasks and the Open counts and keep their creation dates; due for review after the d…
- `GOALS.10` ?area= narrows Today, Inbox, every Plan tab and every Library tab; each count matches its rows and the server; the chip and the URL show it; it survives a reload; clea…
- `GOALS.11` An open-ended goal opens with its tasks; a goal shows what it serves and what serves it, and cannot serve its own servant
- `GOALS.12` New goal asks "Done when…": a milestone goal and a number goal through the dialog; a frequency offers Make it a habit
- `GOALS.13` the fake agent submits a Reading; it waits in the weekly review; Confirm updates the goal's current value and result bar
- `GOALS.14` a 12-week goal serving a longer goal shows on both
- `GOALS.15` ticking a 4-a-week action once shows 1 of 4 and raises the week score
- `GOALS.16` completing, delegating, parking and dropping a task each add to the right Outbox pile; Bring back reverses; Brain > Activity's in and out match the Outbox lists
- `GOALS.17` goal work planned the way Lock the week plans it makes a scheduled task that shows on Today and in the week calendar, and a delegated one that shows as Waiting
- `GOALS.18` Inbox items left too long: on Suggest an old item gets a suggested decision and the batch confirms it; on Park and Discard the job acts and Today's Undo restores
- `GOALS.19` nothing in the goal dialog, readings, Outbox or old-items work scrolls sideways
- `GOALS.20` a quick-captured task shows its guessed area with ✦ and the confidence; one tap confirms it and the ✦ goes
- `GOALS.21` with no goals By area says what will appear and offers + Goal
- `GOALS.22` with eight goals over Career (two parts), Health, Money and Mind each appears under its area and part
- `GOALS.23` a goal's card shows its Done when, score, next action and open task count, matching the goal page
- `GOALS.24` an area that is off has no section; turning it on shows its goals
- `GOALS.25` + Goal in an empty area opens the new-goal form with that area set
- `GOALS.26` goal cards stack one to a row under area headings
- `GOALS.27` with no tasks All tasks says what will appear and offers a box to add one
- `GOALS.28` every open task appears once, under its area
- `GOALS.29` grouping by goal and by due date shows the same tasks
- `GOALS.30` quick add under Health creates a task in Health
- `GOALS.31` the Someday filter shows the tasks of the Someday page
- `GOALS.32` a task with a guessed area shows ✦
- `GOALS.33` a row has its task, goal and due date side by side
- `GOALS.34` with every task under a goal No goal says what will appear and offers a box to add one
- `GOALS.35` tasks without a goal are grouped by area; a task with a goal is not listed
- `GOALS.36` adding a task to a goal takes it off the list and it shows under that goal
- `GOALS.37` confirming a guessed area clears ✦
- `GOALS.38` Make it a goal creates one goal in that area with the tasks attached
- `GOALS.39` the tab count is the number of open tasks with no goal
- `GOALS.40` …
- `GOALS.41` Fine as is leaves the list and keeps the task without a goal
- `GOALS.42` a Month goal created with a parent 12-week goal shows under it on its page and in Goals > By area
- `GOALS.43` no screen shows a tag, a tag picker or Settings > Tags
- `GOALS.44` Cycles lists this month's Month goals in priority order, with the habits
- `GOALS.45` Goals shows four tabs, and Cycles opens at /life/goals/cycles
- `GOALS.46` the week bars show the scores of the grid, with this week marked "so far"
- `GOALS.47` ticking a lead action records the tick and the week's score so far changes
- `GOALS.48` each cycle goal shows its lead action and this week's ticks, as the goal page does
- `GOALS.49` Cycles lists the month goals in priority order with their status; a goal carried from last month says so
- `GOALS.50` a month goal marked Achieved shows Done on Cycles; its title opens the goal page
- `GOALS.51` on an empty space (an area with nothing in it) Cycles says what will appear and how to add it
- `GOALS.52` a closed cycle chosen from the picker is shown read-only
- `GOALS.53` a journal page is a note in Library > Notes and opens with its photo and its date
- `GOALS.54` the Month and Year headers link to Goals > Cycles
- `GOALS.55` two columns, the 12 Week Year beside the month goals
- `GOALS.56` Cycles on a space with no cycle shows what will appear and the one action
- `GOALS.57` the page of a 12 Week Year goal shows the cycle's name, Open grid and its actions with this week's ticks
- `GOALS.58` progress on a 12 Week Year goal shows this week's ticks and the tasks done
- `GOALS.59` Edit renames the goal; its task, note and cycle still show it under the new name
- `GOALS.60` Edit changes the goal's area to a part of Career; Goals > By area shows it there
- `GOALS.61` Edit adds a weekly action and retires another; the cycle grid and Goals > Cycles show the same
- `GOALS.62` the Edit form works one field after another, actions included, with no sideways scroll
- `GOALS.63` an existing goal without Done when shows "Done when is missing" with Add, and By area marks it
- `GOALS.64` Suggest with the assistant faked fills a finish line from the goal's title; with no key it shows two examples
- `GOALS.65` the setting is on on a new site and can be switched off in Settings
- `GOALS.66` Goals > By area shows each focus as a heading in its part, its annual goal first, then 12 Week Year goals, then part-level goals
- `GOALS.67` a focus with no active Annual goal shows "No annual goal" and + Annual goal; adding one clears it
- `GOALS.68` a focus page shows the standard, numbered principles (edit and reorder) and goals by horizon
- `GOALS.69` an existing Open goal shows To sort; Make it a focus creates the focus and an Annual goal holding the old goal's tasks
- `GOALS.70` Settings > Areas shows focuses under each part, with switches and + Add a focus
- `GOALS.71` focus headings and their goals stack on a phone and the focus page is one column

### Library (`tools/acceptance/library.mjs`, 38 checks)

Everything, Notes, Documents, People, Chats, files, search and the graph, and the list screens' panes, filters and remembered views.

Unit tests: `test_library.py`; `test_people.py`

- `LIBRARY.1` Security: rendered Markdown is sanitised
- `LIBRARY.2` a row opens a pane on every list screen and the list stays in the page
- `LIBRARY.3` the URL has open=, Back closes the pane, reload reopens it
- `LIBRARY.4` 390 px: the pane is a bottom sheet across the screen and closes with its close button
- `LIBRARY.5` 1440 px: pane widths, Esc, j and k, focus, Open full page, search opens in the pane
- `LIBRARY.6` filters on every ListView are in the URL and survive a reload
- `LIBRARY.7` no horizontal scrolling and no script errors on any converted screen
- `LIBRARY.8` a list remembers its view on every device, a link with a query wins, Clear clears
- `LIBRARY.9` the record pane shows the tabs of its kind; ptab= survives a reload; a pane with one tab has no tab bar
- `LIBRARY.10` no sideways scrolling and no script errors on the new screens
- `LIBRARY.11` intent: Just keep is in Library > Captures, not the Inbox, with text and no proposals; Add to wiki writes pages and leaves no wiki proposals
- `LIBRARY.12` Captures: each tab's count matches its rows; Photos shows thumbnails; Made from this lists the task and the assistant's note; /chats lands on the Chats tab
- `LIBRARY.13` editor: headings, bold, checklists and [[links]] render; Cmd-B; the / menu inserts a table; a pasted image shows; Show Markdown; no Edit or Done
- `LIBRARY.14` conflict: an agent edits the open page; typing then saving shows the conflict and nothing is lost
- `LIBRARY.15` wiki rules: the agent cannot edit My notes or the rules page; a stale version is a conflict; Undo restores and logs Reverted; Keep in My notes stops the agent
- `LIBRARY.16` Health lists a broken [[link]] and an orphan page
- `LIBRARY.17` Library's tabs are Everything, Notes, Documents, People and Chats; each opens from its tab and its path
- `LIBRARY.18` Library > Notes: the assistant's notes carry "Kept by the assistant" with the rules on top; Written by me leaves them out; the Changes view shows a diff and Undo resto…
- `LIBRARY.19` A Vault document is a capture of kind Document, marked sensitive, with its expiry; the agent cannot read it, nor a note marked sensitive, while the switch is off; only…
- `LIBRARY.20` on an empty space the Library says what will appear and offers + Capture; People says the same
- `LIBRARY.21` Everything shows notes, documents, people and chats together, newest first, with the right kind and line
- `LIBRARY.22` each tab shows only its kind
- `LIBRARY.23` search finds a note by a word in its body and the Area filter narrows the list
- `LIBRARY.24` a sensitive document shows 🔒 and opens for the owner; the agent, with the Vault closed, never gets it
- `LIBRARY.25` Trash and archive opens the old archive
- `LIBRARY.26` a row has its title, area and date side by side; the tabs fit
- `LIBRARY.27` a file used by two items is listed once, with both under Used in
- `LIBRARY.28` a file with 2 versions shows "2 versions" and opens either
- `LIBRARY.29` the type filter shows only slides when Slides is chosen
- `LIBRARY.30` a user who cannot see any record using a file does not see the file
- `LIBRARY.31` a row has its name, Used in and the buttons side by side
- `LIBRARY.32` with no files the screen says what will appear and offers + Capture; a search with no match says so
- `LIBRARY.33` People lists persons and organisations; filtering by kind works
- `LIBRARY.34` a person page lists the notes and tasks that mention them, newest first
- `LIBRARY.35` an organisation page lists its people
- `LIBRARY.36` the facts sit beside the text and mentions
- `LIBRARY.37` with no people the screen says what will appear and offers + Capture
- `LIBRARY.38` a photo of a journal page captured from the phone becomes a note with the photo, the transcript and its date; search finds it and its goal shows it

### Review (`tools/acceptance/review.mjs`, 23 checks)

The weekly review (Library, Tasks, Goals, Reflect and Lock), the monthly and 12-week reviews.

Unit tests: `test_review.py`

- `REVIEW.1` Archive job archives done tasks; a stale open task waits in the weekly review's list of stale tasks
- `REVIEW.2` the review screen shows tabs on a phone only
- `REVIEW.3` the review opens from Today's banner on Library, with its period in the header; Goals cannot open before Tasks is done
- `REVIEW.4` a meeting that matters with a linked voice note; a task made from its follow-up leaves the meeting's drawer and the Revelations list
- `REVIEW.5` a reading confirmed from Revelations shows its value on the goal's row in Goals
- `REVIEW.6` the Tasks tab lists each stale task once with Keep, Someday and Drop; each button does what it says; the Outbox counts match
- `REVIEW.7` every stale task decided (the empty list says what will appear here); Next: Goals opens
- `REVIEW.8` every cycle goal gets a next action or a skip with a reason; exactly three stars; more than the free time shows the warning
- `REVIEW.9` Pause and reopen: everything is where it was left; no tab scrolls the page at 1440 x 900 or sideways at 390
- `REVIEW.10` what went well; Lock; the done screen; Today shows the top three first; the scheduled tasks are on Today and in Plan > Week
- `REVIEW.11` the weekly review renders on data like the owner's (a goal migrated from a project, a number goal with a Suggested reading, a milestone goal without "done when", a goa…
- `REVIEW.12` a screen forced to fail shows "This screen could not be shown." with Reload and a reference, logs it, and navigation keeps working
- `REVIEW.13` every place, every Plan and Library tab and every view of Plan's rhythms opens by clicking, and navigation works afterwards
- `REVIEW.14` the monthly review's Look back shows the month's goals, habits and weekly scores
- `REVIEW.15` Decide: carry one goal and drop another with a reason; after Lock the plan holds the carried goal and the dropped one is dropped
- `REVIEW.16` the goals made in Plan are in the order given, and Goals > Cycles shows them
- `REVIEW.17` with no month to look back on, the monthly review says nothing is due
- `REVIEW.18` the 12-week review's Score shows the twelve weekly scores and the cycle view's average
- `REVIEW.19` Goals > Cycles offers the 12-week review, and there is no Close cycle pop-up (its link opens the review)
- `REVIEW.20` both reviews show numbered tabs, and nothing scrolls sideways
- `REVIEW.21` when a weekly and a monthly review are both due, Review shows the weekly first, then the monthly
- `REVIEW.22` a review left after step 2 resumes at step 2 with its decisions kept
- `REVIEW.23` deciding each goal and locking closes the cycle with cycles.close_cycle's score and makes the next cycle with the carried goals and their lead actions

### Settings (`tools/acceptance/settings.mjs`, 40 checks)

Profile, Areas, Rhythms, Members, Sources, Rules, Skills, Cost, the setup ladder, the calendar connection and the one-space site.

Unit tests: `test_settings.py`; `test_permissions.py` (who sees and changes what); `test_skills.py` (skills, lessons, the gateway and cost); `test_calendar.py` (Google Calendar read and write)

- `SETTINGS.1` Settings: every section from the menu and the URL, old links to their new homes, rename a tag and a part, archive a part (its open task moved) and restore it, members,…
- `SETTINGS.2` access: the family user sees no Private sources, pages or changes; the agent cannot see a source behind a Vault document while the switch is off
- `SETTINGS.3` an agent added with Add member shows in Members with its badge and in Agents; access changed in one view shows in the other; a user with no role is offered one
- `SETTINGS.4` Ask and agents' sensitive-item access switch from Spaces
- `SETTINGS.5` ?tab=agents and the old names land on Members; Rules and Advanced list no members or agents
- `SETTINGS.6` the area picker on a task shows the seven areas that are on with their parts indented, and no area that is off
- `SETTINGS.7` switching Money on shows it in the task area picker; off hides it; its goals come back when it is on again
- `SETTINGS.8` adding a part "CIS Board" under Career shows it in the list and in the pickers
- `SETTINGS.9` archiving a part with open tasks asks where to move them, and they end up there
- `SETTINGS.10` a Life User who is not Life Admin sees Settings > Areas read-only
- `SETTINGS.11` the screen matches the mockup: intro, one card of the seven, switches, On by default on Career and Health, parts with Edit, the footer
- `SETTINGS.12` the setup card shows the level and the next step, and links to How it works
- `SETTINGS.13` How it works marks the current level as next, and shows the flow
- `SETTINGS.14` dismissing the card hides it for that user, and Settings still reaches How it works
- `SETTINGS.15` Cost shows this month's spend by feature, matching the recorded calls
- `SETTINGS.16` Skills lists process-capture, Test shows pass for each example, saving an edit makes version 2
- `SETTINGS.17` a skill with no examples and no runs says what will appear
- `SETTINGS.18` with no lessons Needs you has no lessons section and the skill page says what will appear
- `SETTINGS.19` a lesson shows in Needs you and on the skill page; Edit then Accept saves the edited words
- `SETTINGS.20` removing an accepted lesson makes a new version without it
- `SETTINGS.21` Settings > Calendar lists the account's calendars and saves the one to write to
- `SETTINGS.22` the owner's menu is Profile, Calendar, Areas, Rhythms, Habits, Sources, Rules, Members in four groups, and Advanced at the bottom
- `SETTINGS.23` Rhythms holds the weekly review, old items, working hours and the 12 Week Year, and each saves the same setting
- `SETTINGS.24` Profile shows Look and Reminders, and the theme takes effect
- `SETTINGS.25` every old ?tab= value lands on its new place
- `SETTINGS.26` Members lists people and agents with filters and a Spaces view that still switches Ask and sensitive-item access
- `SETTINGS.27` Settings has no Tags page; Library's Trash and archive is where ?tab=tags goes
- `SETTINGS.28` a person who is not a Life Admin at level 1 sees Profile, Areas and Sources and the footer line; Rhythms appears at level 4
- `SETTINGS.29` a person who is not a Life Admin does not see Advanced; the owner's Advanced opens AI key and cost, Import and export and Backups
- `SETTINGS.30` the menu is the first screen on a phone and every page opens with Back
- `SETTINGS.31` on a one-space site no space picker, chip or Spaces view appears on any screen
- `SETTINGS.32` on a one-space site Ask is switched in Advanced and "Agents may open sensitive items" in Rules, and each takes effect
- `SETTINGS.33` a capture sent without a space on a one-space site lands in that space
- `SETTINGS.34` the sidebar has no lens and no pinned areas; ?area= on Goals and Library is that page's area filter
- `SETTINGS.35` on the acceptance site, which keeps two spaces, the space is picked in the … and Settings still shows Spaces
- `SETTINGS.36` Settings, Rules shows "What agents know about you" with the current card
- `SETTINGS.37` a contradiction in Needs you, once decided, leaves the page with the chosen fact and its source
- `SETTINGS.38` Skills: every built-in skill has its card, and Test passes the examples of each
- `SETTINGS.39` Settings > Data holds the Reset section; /today/reset lands on Today and says that page moved
- `SETTINGS.40` Settings > Sources shows the email-in address and the allowed senders, and the onboarding guide says nothing about forwarding

### Phone (`tools/acceptance/phone.mjs`, 24 checks)

The sidebar and bottom bar, the router, keyboard keys, the PWA, offline capture and sharing to Life OS.

Unit tests: `test_capture.py` (the phone's captures, sent once); `test_permissions.py` (navigation, the router's routes)

- `PHONE.1` navigation: the sidebar is the lens, Capture, Today, Brain, Goals, Library and Settings; the active item; the place tabs; the Brain count; the capture sheet and each o…
- `PHONE.2` a place's tabs: the path holds the tab, the view switch is in the URL, [ and ] move, the phone row scrolls
- `PHONE.3` no screen scrolls sideways: every place, Plan and Library tab and view, Settings section, a goal and a note page, with and without an area
- `PHONE.4` Keyboard: G then T, I, O or L opens a place; the older G letters open their new homes
- `PHONE.5` the sidebar shows + Capture, Today, Brain, Goals, Library and Settings, in that order, and no other place
- `PHONE.6` Review is hidden for a user who has never locked a review, and shown between Goals and Library after one is locked
- `PHONE.7` Brain shows the Needs you count, the same number as the Inbox count
- `PHONE.8` an old address lands on Today with the moved note, and every route of the router loads without an error
- `PHONE.9` Archive, Outbox, Graph, Timeline, Reset and Vault are reached from their new homes
- `PHONE.10` the bottom bar shows Today, Brain, the capture button, Goals and Library; capture opens the capture sheet
- `PHONE.11` tabs are routes: each tab has its own path, and reloading /life/goals/tasks lands on Goals > All tasks
- `PHONE.12` Today > Day shows today's tasks, the top three and the day's events from the calendar
- `PHONE.13` ticking a task on Today marks it done and updates the counts
- `PHONE.14` the Needs you line shows the waiting count and opens Brain > Needs you
- `PHONE.15` the switch moves to Week, Month and Year routes
- `PHONE.16` the layout matches the mockups (the plate with the calendar beside it), with no sideways scroll
- `PHONE.17` The manifest is valid and the service worker is registered (phone profile)
- `PHONE.18` The service worker's cache holds only static app files, never an /api/ response
- `PHONE.19` Posting to the share target with a photo and text opens the capture screen; Save makes one capture with the file
- `PHONE.20` Offline, two captures are queued ("2 waiting to send"); back online both are sent, once each
- `PHONE.21` Recording on + Capture (fake microphone) makes an audio capture marked not transcribed yet
- `PHONE.22` Logging out empties the offline queue
- `PHONE.23` The share target while logged out goes to login and sends nothing
- `PHONE.24` every route in the router loads without an error; an unknown address lands on Today with "That page moved"

### Tooling (`tools/acceptance/tooling.mjs`, 4 checks)

The test tools themselves: the setup switches, CI and the screenshots a failed check saves.

Unit tests: none: these check the tools, not the app

- `TOOLING.1` Without the switches the tooling uses the Docker bench, Chrome and .env; with them, a local bench, Playwright's Chromium and the environment
- `TOOLING.2` CI has an acceptance job that builds the front end, makes acceptance.localhost, serves it and runs every check
- `TOOLING.3` A failed check saves screenshots, and CI uploads them with the logs as an artifact
- `TOOLING.4` No password or key in the workflow file or in the logs a failed run uploads

### End of every run (`tools/acceptance/end.mjs`)

- `END.1` this run's records are removed from the acceptance site; `END.2` no test debris is left on `lifeos.localhost`; `END.3` Frappe's semgrep rules find nothing (`tools/scan.sh`).
