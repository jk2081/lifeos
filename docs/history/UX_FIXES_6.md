# Set 6: Simplify

Life OS has grown to about 25 places in its sidebar. A newcomer cannot tell where to start or where anything goes. This set rebuilds the app around **four places, four things and one lens**, without removing any capability.

- **Four places:** Today (what to do now), Inbox (what came in), Plan (where I am going), Library (what I have and know). Ask sits on every screen; Settings at the bottom.
- **Four things:** Goal, Task, Note, Capture. Projects become goals. Wiki pages are notes kept by the assistant. Vault documents and other sensitive items carry a "sensitive" mark. Someday and Archived are states.
- **One lens:** a space and area picker at the top of the sidebar that narrows every place, replacing the area pages.

**This set needs pre-step 6.** If `PRE_STEP_6_DONE` does not exist, write "Set 6 needs pre-step 6 to be finished first" to `BUILD_BLOCKED` and change nothing.

Read `CLAUDE.md` (including "Frappe conventions"), `ROADMAP.md`, `STATUS.md`, `DECISIONS.md`, `frontend/COMPONENTS.md`, `agent/SKILL.md` and `docs/conformance/README.md` first. Follow the Frappe skills in `.claude/skills/`, the three-layer component rule, the tab rules and the list-and-pane pattern from earlier sets. Run `./tools/scan.sh` before every commit; this set may not add findings.

**Mockups:** `mockups/set6/` (navigation map, sidebar with the lens open over Plan > Goals, Settings > Rhythms) and `mockups/set5/` (Today, Ask, Reset, Someday, phone screens). Where the set 5 mockups show the old long sidebar, the set 6 sidebar wins. Every screen must work at 390 px and 1440 px.

## 1. The lens

- A picker at the top of the sidebar showing the current **space** and **area**: "Private · All of life". Opening it lists the user's spaces, then "All of life" and every active area with sub-areas indented, then "Pin areas to the sidebar" and "Manage areas" (Settings > Areas).
- The lens is part of the URL (`space=` and `area=`) and remembered per user with the other view state. Choosing an area includes its sub-areas.
- **Every place narrows to the lens:** Today (Open band, Next, rail), Inbox, every Plan tab, every Library tab, counts in the sidebar, Search and Ask (its default scope becomes the lens). An item filed under the area or listing it in "also in" counts as in the area.
- When an area is selected, the page header shows it as a removable chip beside the title, so it is always clear the view is narrowed.
- **Pinned areas** sit in the sidebar under "Focus on an area" as one-click lens shortcuts, each with its colour dot, plus "All areas…". The owner pins and orders them in Settings > Areas. Default: the top-level areas.
- **Area pages go.** `/areas/:id` redirects to Today with that area in the lens. `/areas` redirects to Settings > Areas. The area overview's content (its goals, open tasks, latest activity) is what Today and Plan show under the lens.
- On a phone the lens is the title at the top of every screen; tapping it opens the same picker as a bottom sheet.

## 2. Navigation

**Sidebar** (`mockups/set6/21-sidebar-lens-plan.png`): lens; **+ New** (Capture, Task, Goal, Note); **Today**; **Inbox** with its count; **Plan**, which expands to its tabs; **Library**; "Focus on an area" with pinned areas; at the bottom **Settings** and the user with Help.

**Header on every screen:** the lens as a breadcrumb, the page title, and the "Search or ask anything" box (⌘K) from set 5. Ask's page (threads, insights) is reached from the box ("History") and from Today's insights line; it leaves the sidebar.

**Phone bottom bar:** Today, Inbox, Plan, Library, Ask. Ask opens the Ask sheet with the lens as scope. There is no "More" tab; Settings is reached from the lens sheet.

**Keyboard:** G then T, I, P or L goes to a place. Keep existing shortcuts that still make sense; list all in the shortcut help.

**Redirects:** every old route lands somewhere sensible with its query carried over: `/tasks` → Plan > Tasks, `/calendar/:view` → Plan > Week or Month, `/journal/*` → the matching Plan tab, `/goals` → Plan > Goals, `/projects` and `/projects/:id` → Plan > Goals (the goal the project became), `/someday` → Plan > Someday, `/reset` → Plan > Week at its Reset step, `/sources` and `/chats` → Library > Captures, `/wiki` → Library > Notes filtered to the assistant's notes, `/vault` → Library > Captures filtered to sensitive documents, `/graph` → Library > Notes, Graph view, `/timeline` → Library > Timeline, `/archive` → Library > Archive. Count links from Today, Reset and insights must still open lists with exactly that many rows.

## 3. Plan

Tabs, in this order, as in the mockup: **Week**, **Month**, **12 Weeks**, **Year** (the rhythms), then **Goals**, **Tasks**, **Someday** (the lists). Time tabs come first and are visually grouped apart from the list tabs.

| Tab | Holds | Taken from |
| --- | --- | --- |
| Week | This week's score; the weekly review (Reset first on review day); the week calendar with events and dated tasks | Journal > Weekly review, Calendar > Week and Agenda, Reset |
| Month | Month plan: focus, habits for the month, check-ins; the month calendar | Journal > Month, Habits, Check-ins, Calendar > Month |
| 12 Weeks | The cycle grid, its goals and weekly actions, close the cycle, plan the next | Journal > 12 Week Year |
| Year | The year calendar and goals across cycles | Calendar > Year, Journal > Goals |
| Goals | Every goal, list and pane, state tabs and filters as on the current Goals screen | Goals, Projects |
| Tasks | Every task, as on the current Tasks screen | Tasks |
| Someday | As on the current Someday screen | Someday |

- Reset stays a full screen reached from Plan > Week ("Reset" button and the review's first step) and from Today's Open band. It is not a tab.
- Journal pages (photos of the paper journal and their transcripts) are captures: they move to Library > Captures as a kind, and the 12 Week Year and month tabs link to the pages that fed them.
- Remove the Journal and Calendar screens once every part has a home; keep their components.

## 4. Projects become goals

A project is an open-ended goal with tasks. Merge them in one migration (a Frappe patch), keeping every record and link.

- **Goal gets** the project fields it lacks: `status` handling for open-ended goals (Active, On hold, Done, Dropped, mapped onto the goal's outcome and Someday fields), `notes_md`, `completed_on`, `last_activity_on`. Record the exact mapping in `DECISIONS.md`.
- **Goal gets `serves`** (Link to Life Goal): the longer goal this goal serves. It replaces `Life Goal.project`: a goal that belonged to a project now serves the goal that project became. Show "Serves …" on a goal and "Served by …" (a list) on the goal it serves. Prevent cycles.
- **Each project becomes a goal** of type Open with the same title, area, space, outcome text, target date, notes, archive and Someday state, and its dates. Store the new goal's name on the project (`migrated_to`) so the patch can be checked and rerun safely.
- **Every link to a project points to the new goal instead:** on Task, Note, Inbox Item, Chat Log, Journal Page, Vault Document, Idea, Connection defaults, Proposal targets, Index rows, Links, View State and anywhere else a scan of the code and DocType JSON finds. Prefer renaming each `project` field to `goal` where the meaning is "belongs to"; where renaming is not practical, change its Link target and label. Rebuild `Life Index` rows for every changed record.
- **Life Project** stays in the database for this set, hidden from the UI and agents, read-only, so the migration can be checked. Removing it is a later decision; note it in `ROADMAP.md`.
- **Agents:** proposals of record type Project create a goal of type Open. Methods that accept `project` also accept `goal`, and map `project` names through `migrated_to`, for one set; document both in `agent/SKILL.md` and update `fake_agent.py`.
- **Tests:** the migration on a copy of the seeded data: every project has a goal, every task, note and source that pointed at a project points at its goal, counts on Today and Plan are unchanged, and running the patch twice changes nothing.

## 5. Library

Tabs: **All**, **Notes**, **Captures**, **Timeline**, **Archive**. One list-and-pane pattern throughout, with filters: kind, written by (me or the assistant), sensitive, area (from the lens), date.

- **Notes** holds every note. Wiki pages are notes with a small "Kept by the assistant" badge. Views: List (default), Tree, Graph. The Wiki's Changes, Health and Rules become: a "Changes" view of the assistant's edits with diffs and undo; a "Health" view (orphans, broken links, missing sources); the rules page pinned at the top of the assistant's notes. Keep every wiki rule from set 4 (agents edit only assistant notes; Keep and Hand over between the two).
- **Captures** holds every source: uploads, voice notes, photos, documents, articles, email digests, chats, journal pages. Kinds as tabs or a kind filter, the photo grid as a view. Vault documents appear here as kind **Document**, marked sensitive, keeping their holder, last four characters, issue and expiry dates and reminders.
- **Timeline** is today's Timeline screen. **Archive** is today's Archive screen with its Trash tab.
- **Sensitive mark:** add `is_sensitive` to captures and notes. Vault documents are always sensitive. A sensitive item follows the Vault rules exactly: hidden from agents unless the space's agent switch allows it, sent to Ask only if the space's Ask switch allows it, shown with a lock icon. Rename the two switches "Agents may open sensitive items" and "Ask may read sensitive items". Anyone with edit access can mark an item sensitive; only the owner can unmark it.

## 6. Settings

Regroup as in `mockups/set6/22-settings-rhythms.png`, one section at a time, each setting with a line of help text, saving as it changes:

- **Me:** Profile, Appearance, Notifications, Shortcuts.
- **Your life:** Areas (including pinning to the sidebar), Rhythms, Habits, Check-ins, Reset rules, Tags.
- **Assistant:** Assistants (today's Agents section), Connections, Ask and AI (key, models, monthly cap, spend), Sensitive items (the two switches per space), Note rules (the rules page).
- **People and agents:** Spaces, Members.
- **Data:** Archive and trash, Import and export (today's chat import), Backups (what is backed up and when, read from site configuration; "Not set up on this site" when absent).

**Rhythms** (new): start of day; weekly review day and time; week starts on; month plan on or off; current cycle (read-only dates and week number), score target, break week between cycles. Move these settings here from wherever they live now, keeping their values.

## 7. Rhythm banners

Today shows at most one banner line, above the Open band, when a rhythm is due:

- Review day from the review time until done or skipped: "Your weekly review is ready" → Plan > Week, starting with Reset.
- First three days of a month, until the month plan exists: "Plan [Month]" → Plan > Month.
- Week 11 of a cycle, until the next cycle is planned: "Plan your next 12 weeks" → Plan > 12 Weeks.
- Week 12: "Close this cycle" → Plan > 12 Weeks.

Each has Skip, which hides it until the next occurrence. The order of precedence is the order above.

## What must not change

- No record, field value, link or history is lost. Every capability reachable today is reachable after this set, at most one level deeper.
- Space rules, sensitive-item rules, agent rules and the wiki rules.
- The Inbox review flow, Today's Open band and Next list, Ask, insights, Reset and Someday from set 5, apart from the lens and the moves above.

## Checks

- `./tools/scan.sh` reports zero findings.
- All unit tests pass, including the migration tests and new tests for the lens filter on each list method (an item filed under a sub-area appears under its parent area; an item in "also in" appears under that area).
- Rewrite `tools/acceptance.mjs` for the new structure, keeping every check's intent, at 1440 px and 390 px:
  - The sidebar and the phone bar show exactly the places above; G then T, I, P, L work.
  - Choosing an area in the lens narrows Today, Inbox, every Plan tab and every Library tab, and the counts match the rows; clearing it restores them; the lens survives a reload and is in the URL.
  - Every old route in section 2 lands on its new home with its filters.
  - A former project opens as a goal with its tasks; a goal shows what it serves and what serves it.
  - The assistant's notes show the badge; the Changes view diffs and undoes; Health lists orphans.
  - A Vault document appears in Captures, sensitive, with its expiry; the agent cannot read it while the switch is off.
  - Each rhythm banner appears on its day (move the clock in the test) and Skip hides it.
  - Settings sections each open from the menu and their URL; a changed Rhythms setting survives a reload.
  - No screen scrolls sideways at 390 px.
- Screenshot every place and Plan and Library tab at both widths in light and dark, compare with the mockups, and fix what differs or breaks.
- The fake agent runs end to end with the goal-based API.

## Working rules

- Order: 1 the lens (store, URL, list methods); 4 the Projects-to-Goals migration; 2 navigation and redirects; 3 Plan; 5 Library and the sensitive mark; 6 Settings; 7 rhythm banners; checks.
- Run the unit tests and the scan after each step, the acceptance script after steps 2, 3 and 5, and commit once per step.
- Update `frontend/COMPONENTS.md` (lens, places, Plan and Library tabs), `agent/SKILL.md` (goal-based API, sensitive items) and `ROADMAP.md` (set 6 done; Life Project removal pending).
- Record deviations in `DECISIONS.md`. Add a "Set 6: Simplify" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_6_DONE` and commit.
