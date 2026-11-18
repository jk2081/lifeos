# Life OS roadmap

Life OS keeps its owner moving forward: everything that lands on him goes in one place, becomes a few clear next steps, and the rest is let go. This file lists the build sets that take the app from where it is to the design agreed on 17 November 2026. Each set gets its own brief (`UX_FIXES_<n>.md`) written just before it runs, so it reflects what the previous set actually built.

## Where things stand

| Set | Scope | State |
| --- | --- | --- |
| Milestones 0 to 9 | The original build from `SPEC.md` | Done |
| 1 | Lists with a side pane; counts open their lists | Done |
| 2 | frappe-ui and `@framework/ui` components; remembered views | Done |
| 3 | Tabs, Settings, sidebar, permissions, goals outside the 12 Week Year | Done |
| 4 | Sources, the Wiki, the live-preview editor, streams, test-site clean-up | Done |
| 5 | Count rule, Someday, Reset, Today with Open and Next, AI client with spend cap, Ask from any screen, insights | Done |
| Pre-step 6 | Frappe's official conventions, scan, audit and review | Done |
| 6 | Simplify: four places, the lens, Projects into Goals, Library, Settings, rhythm banners (`UX_FIXES_6.md`) | Done |
| 7 | Moving forward: Outbox, old Inbox items, the weekly review's goal work, Done when (`UX_FIXES_7.md`) | Done |
| Bug fix 1 | Blank weekly review that froze navigation | Done |
| 8 | The weekly review, redesigned; reading the calendar (`UX_FIXES_8.md`) | Next |
| 9 | Calendar: writing goal blocks (see below) | |

## The target design in one paragraph

Four places (Today, Inbox, Plan, Library), four things (Goal, Task, Note, Capture), and a lens at the top of the sidebar that narrows everything to a space and an area. Ask on every screen. Plan holds the rhythms (Week, Month, 12 Weeks, Year) and the lists (Goals, Tasks, Someday). The weekly review runs score, Reset, then goal work for the coming week, which becomes tasks and private calendar slots. An Outbox shows what left the plate (Done, Delegated, Parked, Discarded). All model calls go through one gateway that tracks cost against a $30 monthly cap. People and agents are members of Life OS with a sponsor, scope and rights; agents are created from Life OS and run as Hermes profiles.

## The sets

### Pre-step 6: Frappe conventions

Bring the app up to Frappe's official conventions before restructuring it (brief: `PRE_STEP_6.md`).

- Fetch Frappe's official agent skills (`frappe-app-dev`, `frappe-code-review`, `code-style`, `ui-design`, `deep-app-audit`) into `.claude/skills/` at the start of every run; `CLAUDE.md` requires them from now on.
- A scan tool with Frappe's semgrep rules, run at the end of every set. Today's scan: 732 findings.
- Fix them: declared HTTP methods and type hints on every public method, parameterised SQL, no stray commits, no user switching in live code, safe file paths, translations.
- Run Frappe's deep app audit and code review over the whole app and fix what they confirm.
- No screen or feature changes.

### Set 6: Simplify

Restructure the app around the four places. No AI work.

- Sidebar: lens (space and area), + New, Today, Inbox, Plan, Library, pinned areas as lens shortcuts, Settings. Phone bar: Today, Inbox, Plan, Library, Ask.
- Plan tabs: Week, Month, 12 Weeks, Year, Goals, Tasks, Someday. Calendar views move into Week and Month; the Journal's content moves into these tabs.
- Library tabs: All, Notes, Captures, Timeline, Archive (with the trash). Sources become Captures. Wiki pages become notes with a "kept by the assistant" badge; Changes, Health and Rules become Library filters and views. Vault becomes a "sensitive" mark on captures and notes, keeping every Vault access rule. Graph becomes a view.
- Projects merge into Goals: every project becomes a goal of type Open; tasks point to the goal; project pages become goal pages.
- Area pages are replaced by the lens; Today, Plan, Library and Ask narrow to the selected area.
- Reset moves into Plan > Week (and stays reachable from Today's Open band). Ask leaves the sidebar; its history and insights sit behind the header box.
- Settings regrouped: Me; Your life (Areas, Rhythms, Habits, Check-ins, Reset rules, Tags); Assistant; People and agents; Data. New Rhythms section; one rhythm banner at a time on Today.
- Every old route redirects to its new home.
- Mockups: `mockups/set5/` boards 13 to 19 and the Simplify boards 20 to 22 (to be added to `mockups/set6/`).

### Pending from set 6

- **Remove Life Project.** Every project became an open-ended goal; the old DocType stays read-only and hidden so the migration can be checked (`migrated_to` on each project). Once the owner has checked it, a patch can drop the DocType and its table, and the old `project` columns left in the tables of Life Task, Note, Inbox Item, Chat Log, Journal Page, Vault Document, Idea, Goal and Index (`bench trim-tables`).
- **Drop the `project` aliases.** For one set, methods take `project` and map it to the goal it became, Someday proposals accept record type Project, and `connections.defaults` answers `default_project`. Set 7's brief did not include their removal, so they are still there; remove them in a later set and say so in `agent/SKILL.md`.

### Set 7: Moving forward (done, 18 November 2026)

Built as `UX_FIXES_7.md` describes; `STATUS.md` ("Set 7: Moving forward") says what works and `DECISIONS.md` what differs.

- Outbox: everything that leaves the plate (captures, tasks, goals), in four piles: Done, Delegated, Parked, Discarded. A flow line on Today's Open band ("This week: 64 in, 81 out") and the full Outbox as a Library tab.
- Old Inbox items: a setting. Default: after 7 days the assistant suggests a decision for each item, confirmed in batches. Options: auto-discard or auto-park after 14 days, with undo.
- Weekly review in Plan > Week: score, then Reset, then goal work. For each goal: next action, when, who, what is needed. Each becomes a task; if "who" is someone else, it is Delegated. Working hours as a setting.

- Goals say "Done when…": either a finish line (milestone goal) or a number (number goal: what is measured, start, target, current value). Every goal has one or the other; the assistant suggests which from the title, and a frequency suggests a habit instead.
- A goal can point to the longer goal it serves (for example a 12-week drainage goal serving a multi-year yield goal); each goal shows the goal it serves and the goals that serve it.
- Lead measures stay the goal's weekly actions: a tick, or an optional count per week ("4 times a week", ticked one at a time), each tick counting towards the week score.
- Current values of number goals: the assistant pre-fills a value it finds in captures, showing the source; the weekly review asks for confirmation, or for a value when nothing was found. Goals show the result against its target beside task completion.

### Set 8: The weekly review, redesigned (brief written, 18 November 2026)

The review built in set 7 reads as a long report with no guide. It is being redesigned from mockups before any brief is written (Life OS Screens canvas, boards 23 to 29 and those that follow). Agreed so far:

- Four numbered tabs, in a fixed order, each ticked off when done and open to going back: **1 Library** (what came in and what it means), **2 Tasks** (the commitments already on the plate), **3 Goals** (progress, then next week's plan), **4 Reflect** (what went well, then Lock the week).
- The assistant suggests first everywhere; the owner confirms or corrects. Every tab fits on one screen; detail opens in a drawer. Long lists are sorted into piles (Keep, Park in Someday, Let go) accepted as a pile from a drawer or one item at a time; only items the assistant cannot decide are shown one by one ("Needs you").
- Library shows last week's calendar. Only meetings that matter are marked (people from outside, 30 minutes or longer, not recurring internal check-ins): linked notes and follow-ups, or nothing captured. A meeting opens in a drawer with what is linked, follow-ups found, and "Anything to plan from this meeting?".
- Revelations: at most five, each with its source and one action (a promise with no task, a goal reading, a blocker, a topic that keeps coming up, meetings that matter with nothing captured). Acted-on revelations leave the list.
- To settle while designing: one finding shown in several places is cleared everywhere at once; a skipped week is covered by the next review; the monthly and 12-week reviews reuse the same tabs.
- **Reading Google Calendar (read-only, per person) moves into this set**, because Library needs last week's meetings. Writing to the calendar stays in set 9.

### Set 9: Calendar

- Google Calendar, two-way, per person, through Frappe's integration. Reading arrives in set 8; this set adds writing.
- Goal-work tasks from the weekly review become private events in their own colour; moving one in Google Calendar moves the task. Suggested times stay within working hours and never overlap existing events. The assistant suggests each slot's length.
- Needs the owner's Google Cloud OAuth client.

### Set 10: Cost and the model gateway

- A model gateway (LiteLLM) on the server; the Life OS AI client and every Hermes profile call models only through it, each with its own gateway key. Provider keys live only in the gateway.
- Caps in US dollars: $30 a month overall (setting), optional caps per caller.
- Settings > Assistant > Usage and cost: spend against the cap with a daily trend, by caller and by model, fixed monthly costs entered by hand (server, backups, subscriptions), the total cost to run Life OS, alerts at 50%, 80% and 100%.

### Go live (not a build set)

A checklist, done with the owner, before daily use:

1. Install Life OS on the VPS; nightly backups with a tested restore.
2. Connect Google Calendar for real.
3. Point Hermes at Life OS instead of Folio: email digest, chats digest, nightly chat log.
4. Move what matters from Folio.
5. Use it daily for two weeks and keep a list of every annoyance. That list becomes the next set.

### Set 11: People and sharing

- Members: Ruchi and others with their own logins; Shared and Family spaces; the lens shows spaces.
- Calendars per person, shared calendars visible in shared spaces.
- Sharing a single goal, note or capture.

### Set 12: Agent platform

Needs a decision first: what read, propose and act mean per kind of record, and which actions always need approval.

- People and agents registry: human or agent, sponsor, scope, rights, budget, last active, off switch.
- Assignments: tasks for people or agents; a Delegated view; results come back as proposals or finished tasks.
- Approvals queue in the Inbox.
- Agent Host on the server: creates, updates, pauses and retires Hermes profiles, each in its own container, from a form in Life OS. The current Hermes becomes the first registered profile.
- Skills library with approval of skills agents write; corrections sent back as lessons; scorecards; versions; clone.

### Parked: Coaching

Coach role (numbers only), cohort dashboard, setup template and first-week onboarding. Parked on 17 November 2026; not scheduled.

### Parked: framework gaps

Found when comparing Life OS with GTD, timeboxing, OKRs and Atomic Habits on 17 November 2026. Parked; revisit after two weeks of daily use.

- Time for life beyond goals: a habit gets an optional time and days; the weekly review offers private calendar slots for it alongside goal work.
- Doing the right thing for the moment: the assistant sets a size on each task it proposes (Quick, About an hour, Half a day); Next gets a "Quick wins" filter.
- Out of scope: distraction (phone, attention) and habit design (better suited to coaching).

## Open decisions

1. The agents' permission model (before set 12).
