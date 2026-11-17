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
| Pre-step 6 | Frappe's official conventions, scan, audit and review | Next |

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

### Set 7: Moving forward

- Outbox: everything that leaves the plate (captures, tasks, goals), in four piles: Done, Delegated, Parked, Discarded. A flow line on Today's Open band ("This week: 64 in, 81 out") and the full Outbox as a Library tab.
- Old Inbox items: a setting. Default: after 7 days the assistant suggests a decision for each item, confirmed in batches. Options: auto-discard or auto-park after 14 days, with undo.
- Weekly review in Plan > Week: score, then Reset, then goal work. For each goal: next action, when, who, what is needed. Each becomes a task; if "who" is someone else, it is Delegated. Working hours as a setting.

- Goals say "Done when…": either a finish line (milestone goal) or a number (number goal: what is measured, start, target, current value). Every goal has one or the other; the assistant suggests which from the title, and a frequency suggests a habit instead.
- A goal can point to the longer goal it serves (for example a 12-week drainage goal serving a multi-year yield goal); each goal shows the goal it serves and the goals that serve it.
- Lead measures stay the goal's weekly actions: a tick, or an optional count per week ("4 times a week", ticked one at a time), each tick counting towards the week score.
- Current values of number goals: the assistant pre-fills a value it finds in captures, showing the source; the weekly review asks for confirmation, or for a value when nothing was found. Goals show the result against its target beside task completion.

### Set 8: Calendar

- Google Calendar, two-way, per person, through Frappe's integration.
- Goal-work tasks from the weekly review become private events in their own colour; moving one in Google Calendar moves the task. Suggested times stay within working hours and never overlap existing events. The assistant suggests each slot's length.
- Needs the owner's Google Cloud OAuth client.

### Set 9: Cost and the model gateway

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

### Set 10: People and sharing

- Members: Ruchi and others with their own logins; Shared and Family spaces; the lens shows spaces.
- Calendars per person, shared calendars visible in shared spaces.
- Sharing a single goal, note or capture.

### Set 11: Agent platform

Needs a decision first: what read, propose and act mean per kind of record, and which actions always need approval.

- People and agents registry: human or agent, sponsor, scope, rights, budget, last active, off switch.
- Assignments: tasks for people or agents; a Delegated view; results come back as proposals or finished tasks.
- Approvals queue in the Inbox.
- Agent Host on the server: creates, updates, pauses and retires Hermes profiles, each in its own container, from a form in Life OS. The current Hermes becomes the first registered profile.
- Skills library with approval of skills agents write; corrections sent back as lessons; scorecards; versions; clone.

### Parked: Coaching

Coach role (numbers only), cohort dashboard, setup template and first-week onboarding. Parked on 17 November 2026; not scheduled.

## Open decisions

1. The agents' permission model (before set 11).
