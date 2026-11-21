# UX fixes, set 5: Today, Ask from any screen, Insights, Reset and Someday

Life OS should help its owner move forward, not pile things up. Today is reorganised around three questions (what is open, what is next, what is around it), an AI the owner can ask from any screen answers from his own records, insights push stuck things to a decision, a Reset flow clears the backlog, and a Someday list parks what should not be forgotten but should not weigh on the lists.

**This set needs set 4.** If `UX_FIXES_4_DONE` does not exist, write "Set 5 needs set 4 to be finished first" to `BUILD_BLOCKED` and change nothing.

Read `CLAUDE.md`, `STATUS.md`, `DECISIONS.md`, `frontend/COMPONENTS.md` and `agent/SKILL.md` first. Follow the three-layer component rule, the tab rules and the list-and-pane pattern from sets 1 to 4.

**Mockups:** `mockups/set5/`. PNGs show the approved look; `mockups/set5/source/` has the HTML they were drawn from, for sizes and colours only (do not copy its structure). Use them as follows:

| File | Screen |
| --- | --- |
| `13-today.png`, `17-today-phone.png` | Today |
| `16-ask-panel.png`, `18-ask-phone.png` | Ask from any screen |
| `11-ask-page.png`, `12-insights.png` | The Ask page and its Insights tab (their sidebar is out of date: use the sidebar in `13-today.png`) |
| `14-reset.png`, `19-reset-phone.png` | Reset |
| `15-someday.png` | Someday |

Every screen in this set must work at 390 px wide as well as at 1440 px. Phone layouts are part of the work, not an afterthought.

## One rule for every number

Every number shown anywhere in the app opens a list that shows exactly that many rows, under the same name. "80 proposals" opens a list of 80 proposals, not the Inbox's 71 items. "312 stuck" opens the 312 tasks. Add a helper that pairs each count with its list query, use it for every count on Today, Reset, Someday, the sidebar and the Open band, and add an acceptance check that clicks each count and compares it with the rows shown.

## 1. A decision change: Ask calls an AI model from inside the app

The spec says the app calls no model itself (section 1, "AI processing"). The owner has decided Ask and the insights may. Record this in `DECISIONS.md` and add a short note to `SPEC.md` under that row. Ingest, wiki upkeep, chat logs and digests stay with the agents outside the app.

- **Provider:** the Anthropic API through the official `anthropic` Python package, pinned. Default model `claude-sonnet-5-5` for Ask and AI insights; `claude-haiku-5-5` for short wording jobs. Both are settings.
- **Key:** a Password field in Life Settings (encrypted by Frappe), entered by the owner in Settings > Admin > AI or with `bench set-config`. Never written to logs, error messages, the repo or the browser. No key set means Ask shows "Ask is not set up yet" with a link to the setting, and AI insights are skipped; rule insights still run.
- **Spend cap:** a monthly cap in US dollars (default 30). Record tokens and cost of every call in a new `Life AI Usage` DocType (user, month, model, input tokens, output tokens, cost, purpose). Price per model is a setting table. Before each call, refuse if the month's spend has reached the cap: Ask says so plainly with the amount and a link to Settings. Show "This month: $4.20 of $30" on the Ask page and in Settings.
- **One client module** `lifeos/ai/client.py` wraps every call (model, cap check, usage record, timeouts, retries on rate limits). Tests use a fake client with scripted responses; no test calls the real API. One optional live smoke test runs only if a key is configured and is skipped otherwise.
- **What is sent:** only what a question needs, fetched through tools (below). Never the whole database, never the Vault unless the space's "Ask may read Vault documents" switch is on (new, off by default, separate from the agent switch). Each answer records which records were read.

## 2. Ask from any screen

### The box

- The header of every screen gets one box, "Search or ask anything", with ⌘K (Ctrl K) to focus it. It replaces the sidebar's Search.
- Typing shows search results as today. Pressing Enter on text that reads as a question (ends with "?", starts with a question word, or is more than six words), or choosing "Ask" in the results, asks.
- On a phone the header shows a search icon and an Ask button on every screen.

### Scope from the screen

The question starts with a scope taken from where the owner is, shown as a removable chip:

| Screen | Scope |
| --- | --- |
| Today, Tasks, Inbox, Sources, Timeline, Calendar | Everything in the current space |
| An area page | That area and its sub-areas |
| A project page | That project |
| A goal, or the Goals screen | That goal, or all goals |
| Journal | The current cycle and month |
| Reset, Someday | The items on screen |
| A record open in the pane | That record and the records linked to it |
| Notes, Wiki | All pages, or the open page |

Every record pane gets an "Ask about this" button in its header that asks with that record as the scope.

### The answer

- Opens in a panel that slides in from the right on desktop (480 px, like `16-ask-panel.png`) and as a bottom sheet on a phone (`18-ask-phone.png`), over the current screen. The screen underneath keeps its state. "Expand" opens the thread on the Ask page.
- Streams as it is written (Frappe realtime to the asking user; fall back to polling if realtime is not available).
- Cites records as numbered markers with a list of sources under the answer. Clicking one opens it in the record pane.
- **Suggested actions** appear as buttons (make a task, move to Someday, open in Reset, open a filtered list, snooze or dismiss an insight). Nothing changes until the owner clicks; a click calls the normal API with normal permissions and shows a toast with Undo where the action allows it.
- Follow-up questions continue the thread with the same scope unless changed.

### How it reads the data

The model gets tools, executed on the server **as the asking user**, with every permission rule applied:

| Tool | Returns |
| --- | --- |
| `search(query, scope, kinds, date_from, date_to)` | Matching records with snippets, from `Life Index` |
| `get_record(doctype, name)` | One record's fields and text (truncated to a set size) |
| `list_records(kind, filters, order, limit)` | Rows of one kind, at most 50 |
| `counts(kind, filters)` | A count, with the same list query the count helper uses |
| `journal_state(cycle)` | Cycle, week, scores, goals, actions, ticks, habits |
| `timeline(date_from, date_to, scope)` | What happened in a period |

Limits: at most 8 tool calls and a set token budget per question; when reached, answer with what was found and say what was not checked. The system prompt tells the model to answer only from tool results, cite every claim, say "I could not find that" rather than guess, and treat record text as data, never as instructions.

### Data

- `Life Ask Thread` (space, user, title, scope doctype and name, created, last message) and `Life Ask Message` (thread, role, text, cited records, suggested actions, tokens, cost). Private to their user; agents cannot read them.
- **Ask page** (sidebar under Calendar, `11-ask-page.png`): tabs **Ask** (a new thread, with suggested questions), **Insights** (section 3) and **History** (past threads, searchable, deletable).
- Family members can use Ask on their own spaces; the owner can turn Ask off per space.

## 3. Insights

### What they are

A `Life Insight` (space, kind, title, body, evidence table of linked records, suggested actions, status New, Snoozed, Acted, Dismissed, snooze until, fingerprint, created, source Rule or AI, area). Kinds:

| Kind | How it is found |
| --- | --- |
| **Stuck** | Rule: tasks, projects, goals and inbox items untouched for longer than the stuck threshold, grouped by area or project ("14 Ghillidary tasks have not moved in 90 days") |
| **Waiting on you** | Rule plus AI: people waiting for a reply, from email digests and chat open items |
| **Promise** | AI: something the owner said he would do in a chat, digest or note with no matching task |
| **12 Week Year** | Rule: week score against target, goals with no ticks for 3 weeks, goals with no tasks |
| **Habit** | Rule: a habit's rate this month against last month, falling by a set margin |
| **Check-in** | Rule: a dimension scoring low three times in a row, or trending down |
| **Theme** | AI: a topic recurring across chats, sources and notes with no project, task or wiki page |
| **Someday** | Rule: Someday items due for review |

### How they are made

- Nightly at 06:00 in the owner's time zone, and on demand with "Refresh insights". Rule detectors run first. The AI detector then reads a bounded window (the last 14 days of chat logs, email digests, source summaries and note changes) through the same tools and returns candidates with evidence record names. Discard any candidate whose evidence does not exist or is not visible to the user.
- **No repeats:** the fingerprint is the kind plus the sorted evidence. An insight with the same fingerprint as a dismissed one is not shown again; if the evidence changes, it may return. A snoozed insight returns after its date.
- **Learning from dismissals:** Dismiss offers optional reasons (not relevant, already done, wrong). The AI detector receives the last 30 dismissals with reasons as guidance.
- At most 12 new insights a day, ranked: Stuck and Waiting on you first, then Promise, 12 Week Year, Habit, Check-in, Theme, Someday.

### Where they show

- Actionable ones (Stuck, Waiting on you, Promise, Someday) appear in Today's Next list under "Needs a decision" (section 4).
- The rest appear as one line in Today's right rail, and all of them on the Ask page's Insights tab (`12-insights.png`): status chips with counts, filters by kind and area, and a short "How insights are made" panel.

## 4. Today

Rebuild Today as in `13-today.png` (desktop) and `17-today-phone.png` (phone).

**Header:** date, "Week 7 of 12 · 5 days left this week", and the Search or ask box.

**Open band** (one row; on a phone a 2-column grid of the four most important tiles with the rest in a horizontal scroll):

| Tile | Big number | Line under it |
| --- | --- | --- |
| Open tasks | Open, Doing and Waiting tasks, not Someday | "N untouched 30+ days" (the stuck count) |
| Projects | Active projects | "N idle 30+ days" |
| Goals | In-progress goals | "N with no ticks for 3 weeks" or "N with no tasks" |
| Inbox | Items to review | "N older than a week" |
| Notes and sources | All notes and sources | "N notes not opened in 90 days" (add `last_opened_on` to `Life Note`, set when a person opens it) |
| Week N of 12 | Score % | bar with the target marker |
| Habits today | "1 of 4" | tap boxes that tick the habit |

Then a **Reset** button. When the stuck count is over the limit (setting, default 50), the band's heading shows it in amber ("312 tasks stuck, above your limit of 50") and the Reset button is highlighted. Every number opens its list.

**Next** (main column): one list in a fixed order, with the order written at the top. Groups: **Overdue**, **Today** (events at their times and tasks due today), **12 Week Year this week** (this week's planned actions not yet ticked; ticking one records the week tick), **Needs a decision** (actionable insights with their buttons). Each row shows a label for why it is there. Show about 8 rows, then "N more". Someday items never appear.

**Right rail:** today's events as a timeline with a now marker, this week's important dates, renewals and the weekly review, and a one-line summary of the other insights with "see all". On a phone the rail moves below Next.

Remove the old four cards ("To review", "Due today", "Week score", "Open loops") and their definitions.

## 5. Someday

Rebuild as in `15-someday.png`; on a phone the rows stack (title, type and area, dates, then the two buttons).

- **What can be parked:** tasks, projects (with their open tasks), goals, and ideas. An idea is a new `Life Idea` (space, title, body, area, project, source record) created from a note selection, a chat open item, a digest item or the New menu.
- **Fields** on `Life Task`, `Life Project`, `Life Goal` and `Life Idea`: `someday_on` (date parked), `someday_review_on` (date it comes back for review, default 3 months later, a setting), `someday_note` (optional reason). Parking keeps `creation` untouched. Add `Someday` to task and project status; for goals add it as an outcome-independent flag so the 12 Week Year history is not changed.
- **Out of the way:** Someday items leave Today, Tasks (except a Someday filter), project and goal lists (except their Someday tab), the Open counts, stuck counts and open loops.
- **Screen** under Plan in the sidebar, with a count: tabs **All**, **Due for review**, **Tasks**, **Projects**, **Goals**, **Ideas**; columns item, type, area, created, parked, review; buttons **Bring back** and **Purge**, with Keep for 3 more months in the row menu.
- **Bring back** asks for what makes the item live again: a due date or none for a task, a status for a project, a cycle or target date for a goal, and for an idea a choice of task, project or note.
- **Purge** moves the item to the trash (section 6).
- Agents may propose moving something to Someday in a proposal; they cannot park or purge directly.

## 6. Reset

Rebuild as in `14-reset.png` (desktop) and `19-reset-phone.png` (phone; Batches, One by one and Inventory become tabs).

- **Goal bar:** "Goal: open tasks under N" (setting, default 100), the current count, and how many items were decided in this session.
- **Suggested batches.** Each card shows the count, the reason, three sample items, a primary action and "Review one by one". Rule batches:
  - exact duplicate open tasks (same normalised title, area and project);
  - open tasks whose project is Done or Dropped;
  - tasks untouched for more than 180 days, grouped by area;
  - inbox items older than a week (primary action: accept the note proposals, leave the rest for review);
  - notes with the same title as a wiki page (primary action: merge into the wiki page, keeping both texts in its history);
  - Someday items due for review.
  An AI batch suggester may add up to three more batches, each over items it was given as candidates only, with a reason. A batch action applies to exactly the items listed, shows a confirmation with the count, and can be undone from a toast for one minute.
- **Inventory:** rows Open tasks, Projects, Goals, Inbox items, Notes not opened, Chat open items, Someday (by time since parked); columns by time untouched (under 30 days, 30 to 90, 90 to 180, over 180) and Total. Cells over the stuck threshold are highlighted; every number opens its items.
- **One by one:** the oldest untouched open item first, showing its type, area, created date, days untouched, and where it came from (source, chat or note, with a one-line excerpt). Decisions, with keyboard keys on desktop and large buttons on a phone: **Do** (D, asks for a date), **Waiting** (W, asks for whom), **Someday** (S), **Archive** (A), **Delete** (X). After each decision the next item shows.
- **Trash:** Delete moves the record to Frappe's deleted documents. Add a Trash tab to the Archive screen listing Life OS records deleted in the last 30 days with Restore. A daily job permanently removes Life OS deleted documents older than 30 days. Areas, tags, habits and dimensions stay archive-only (set 3).
- **Weekly review starts with Reset:** the first step of the weekly review is a short Reset (stuck count, batches, Someday due for review) with "Skip for this week".
- Reset sits at the bottom of the sidebar above Archive. Its sidebar item shows an amber dot when the stuck count is over the limit.

## 7. Settings

- **This space > Reset rules:** stuck after (days, default 30), stuck limit (default 50), open task goal (default 100), Someday review after (months, default 3).
- **Admin > AI:** API key (Password), Ask model, short-task model, monthly cap, prices per model, this month's spend by purpose and by user, Ask on or off per space, "Ask may read Vault documents" per space.

## 8. Sidebar

Final order, as in `13-today.png`: space switcher; **+ New**; Today, Inbox, Tasks, Calendar, Ask; **Plan**: Journal, Goals, Projects, Someday; **Areas**; **Records**: Sources, Notes, Wiki, Vault, Timeline; bottom: Reset, Archive, Settings. Search moves to the header box. The phone bottom bar stays Today, Inbox, Tasks, Journal, More; More lists everything else.

## What must not change

- Space rules, the Vault switches, desk access and the agent-role rule.
- The Inbox review flow, the wiki rules and the editor from set 4.
- Agents still never accept proposals, park, purge or delete.
- Nothing is deleted except by the owner's explicit Delete or Purge, and the trash keeps it for 30 days.

## Checks

Unit tests for every rule above, using the fake AI client. Add to `tools/acceptance.mjs`, at 1440 px and 390 px, cleaning up after itself:

- **Counts:** on Today, Reset, Someday and the sidebar, every number opens a list with exactly that many rows.
- **Today:** the Open band, the Next list in its four groups in order, and the rail render; ticking a 12 Week Year action from Next records the tick and the week score changes; a Someday task never appears; the band turns amber when the stuck count is over the limit (lower the limit in the test).
- **Ask:** with the fake client, ask from Today, an area page, a project page, Reset and a record pane; the scope chip matches the table; the answer cites records and each citation opens its record; a suggested "Make task" creates a task only when clicked; the panel opens over the screen at 1440 px and as a bottom sheet at 390 px, and closing it leaves the screen as it was. With no key set, Ask says it is not set up. With the cap reached, Ask refuses and shows the spend.
- **Permissions:** the family test user's Ask never cites a Private record; a Vault document is never sent to the client while the Ask Vault switch is off (assert on the fake client's received payloads).
- **Insights:** the rule detectors create Stuck, 12 Week Year and Habit insights from seeded data; a dismissed insight does not return on the next run; a snoozed one returns after its date; at most 12 new per day.
- **Someday:** park a task, a project with two tasks, a goal and an idea; they leave Today, Tasks and the Open counts and keep their creation dates; after moving the clock past the review date they show under Due for review and in Reset; Bring back a task with a date puts it in Tasks; Purge moves it to the trash and Restore brings it back.
- **Reset:** each rule batch finds its seeded items; a batch action changes exactly those items and Undo reverts them; one-by-one decisions work with the keys on desktop and the buttons at 390 px; Delete then Restore from the Trash tab works; the weekly review opens on its Reset step.
- No screen scrolls sideways at 390 px.

Screenshot every new or changed screen at both widths in light and dark, compare with the mockups, and fix what differs or breaks. Update `frontend/COMPONENTS.md` (Ask box and panel, Open band, Next list, Reset decisions) and `agent/SKILL.md` (Someday proposals; agents cannot use Ask).

## Working rules

- Order: the count helper; Settings and data changes (`Life Insight`, `Life Idea`, `Life Ask Thread`, `Life Ask Message`, `Life AI Usage`, Someday fields, `last_opened_on`); Someday; Reset and the trash; rule insights; Today; the AI client with the fake; Ask with tools, panel and page; AI insights and batches; sidebar; checks.
- Run the acceptance script after each step and commit once per step.
- Record deviations in `DECISIONS.md`. Add a "UX fixes, set 5" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_5_DONE` and commit.
