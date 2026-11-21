# Set 8: The weekly review, redesigned

Set 7's weekly review is one long report: the owner cannot see what it is made of or how to get through it. This set replaces it with a guided review in four numbered tabs, in a fixed order:

1. **Library**: what came in and what it means.
2. **Tasks**: the commitments already on the plate.
3. **Goals**: where they stand, then next week's plan.
4. **Reflect**: what went well, then Lock the week.

The review is opinionated. The assistant suggests first everywhere; the owner confirms or corrects. Every tab fits on one screen at 1440 × 900, whatever the amount of data. Detail opens in a drawer. Long lists become piles.

This set also adds **read-only Google Calendar**, because Library shows last week's meetings. Writing to the calendar stays in set 9.

**This set needs set 7 and bug fix 1.** If `UX_FIXES_7_DONE` or `BUGFIX_1_DONE` does not exist, write "Set 8 needs set 7 and bug fix 1 to be finished first" to `BUILD_BLOCKED` and change nothing.

Read `CLAUDE.md` (including "Frappe conventions"), `ROADMAP.md` (set 8), `STATUS.md`, `DECISIONS.md`, `frontend/COMPONENTS.md` and `agent/SKILL.md` first. Follow the Frappe skills in `.claude/skills/`, the components rule, the tab rules, the lens and the count rule (every number opens a list with exactly that many rows). Run `./tools/scan.sh` before every commit. Every screen must work at 390 px and 1440 px.

## The mockups

`mockups/set8/` holds the approved look; `mockups/set8/source/` the HTML it was rendered from (reference only, as with earlier sets). Example data is invented.

| File | Shows |
| --- | --- |
| `24-pile-pattern.png` | The pile pattern: Needs you, then Keep, Park in Someday, Let go. Its step bar is from an earlier draft; use the tabs from board 28 |
| `25-pile-drawer.png` | A pile opened in a drawer: settle one item, or the rest at once |
| `26-pile-accepted.png` | Back on the tab after a pile is accepted: the card in its done state |
| `28-review-library.png` | Tab 1, Library |
| `29-review-meeting.png` | A meeting opened from Library |
| `30-review-tasks.png` | Tab 2, Tasks |
| `31-review-goals.png` | Tab 3, Goals |
| `32-review-goal-drawer.png` | A goal opened from tab 3 |
| `33-review-reflect.png` | Tab 4, Reflect and Lock the week |

There is no mockup for the phone, the done screen or the drawers on a phone; build them from the rules below and screenshot them.

## 1. The review's shell and rules

### The review record

- New DocType **`Life Review`**: space, user, `kind` (Weekly for now; Monthly and 12 Weeks later), `period_start`, `period_end`, `status` (Open, Locked), `tab_state` (JSON: per tab, done or not, and the piles' state), `went_well` (Small Text), `do_differently` (Small Text), `locked_on`, `minutes_spent`, and the week's numbers stored at lock time (score, in, out, findings acted on and dismissed, items cleared, goals planned and skipped).
- **The period is "since the last locked review"**, not the last seven days. With no earlier review, it is the last seven days. If the period covers more than one week, the header says so: "Covers 9 to 22 November (you skipped last week)".
- One Open review per user and space at a time. Opening the review again resumes it where it was left. Everything is saved as it is done ("Saved as you go" in the header); Pause returns to Plan > Week.
- Existing review notes from set 7 and earlier stay readable: migrate each to a Locked `Life Review` with its note in `went_well`. Record anything that does not fit in `DECISIONS.md`.

### Tabs and moving through them

- Route: `/plan/week?view=review&tab=library|tasks|goals|reflect`. The Today rhythm banner and Plan > Week open the review on its first unfinished tab.
- Numbered tabs (board 28), each ticked when done. The owner can always go back. A tab ahead opens only when the tabs before it are done, except that Library never blocks: its footer button is always "Next: Tasks".
- What makes a tab done: Library, visiting it; Tasks, Needs you and every pile cleared; Goals, every goal in the current cycle has a next action or is skipped with a reason, and exactly three are starred; Reflect, Lock the week.
- The footer always has one primary button and one line saying what is left before it opens (boards 30 and 31).
- The header shows "About 35 minutes" and each tab a rough time when hovered (Library 10, Tasks 8, Goals 12, Reflect 5). No timer.

### The layout rule

Add to `frontend/COMPONENTS.md`, as a rule for every review and every future screen of this kind:

- **Nothing important below the fold.** At 1440 × 900 a review tab shows its whole state without scrolling the page. A list longer than fits is either a pile or folds into one line with a count ("4 other goals in progress · Plan any").
- **Drawers for detail.** A 520 px drawer from the right over a dimmed page (frappe-ui `Dialog` styled as a side sheet, or the library's drawer if `@framework/ui` has one). Header and footer stay put; only the list inside scrolls. Esc and the close button close it. On a phone it is a full-screen sheet.
- **The assistant decides first.** Each item carries the assistant's suggestion and a one-line reason. Only items it cannot decide are shown one by one, under **Needs you** (at most 5; any beyond 5 go into Keep with the reason "not sure").

### Piles (one component, used in Library and Tasks)

- Three piles side by side: **Keep**, **Park in Someday**, **Let go** (board 24). Each card shows its count, a line on what happens to its items, the first three items with a source tag (Inbox, Stuck, Waiting), "+ N more" and **Open pile**.
- **Open pile** opens the drawer (board 25): title with count, a line on what happens, source filters with counts, and each item with its source, area, age and the assistant's reason. Tapping Keep, Park or Let go on a row settles that item at once: the row becomes "Moved to Keep · Undo" or "Settled · Undo". The footer button applies the pile's decision to every item still in it ("Park all 17").
- Accepting closes the drawer and returns to the tab. The card shows its done state (board 26): tint, tick, "17 parked in Someday", what changed ("1 moved to Keep"), **See them** and **Undo**. An item moved to another pile joins that pile's count.
- Needs you rows settle the same way and collapse to one line with Undo. When all are settled, the section folds away.
- Undo of a pile reverses every exit it recorded in the Outbox.
- **How items are sorted.** With an API key and within the cap, the assistant sorts with a one-line reason per item (short model, batched). Without a key, use the rules from set 5's Reset and set 7's old-Inbox job: Inbox items with tasks or dates go to Keep, notes only to Park, nothing found to Let go; stuck tasks linked to a current cycle goal go to Needs you, others older than 60 days to Park, older than 120 days to Let go; waiting items asked more than 7 days ago to Keep as Chase.
- **What each decision does** uses the existing transitions, so the Outbox records them: Keep leaves the item as it is (for an Inbox item, accepts its proposals; for a waiting item marked Chase, creates a task "Chase <person>: <title>" due today); Park moves it to Someday; Let go drops the task, discards the Inbox item, or for a waiting item marks it answered.

### Findings: one record, shown wherever it belongs

The same finding can appear in several places (a promise is a revelation in Library and a follow-up in its meeting's drawer). Keep **one record** per finding and clear it everywhere when it is acted on or dismissed.

- Use set 5's **`Life Insight`** for findings; add the kinds this set needs if missing: Promise, Goal reading, Blocker, Keeps coming up, Not captured, Date, and a `meeting` link. Goal readings stay `Life Goal Reading` records (set 7); the insight links to the reading, and confirming it in either place confirms both.
- A finding leaves every list once acted on or dismissed. Dismissals keep their reason, as set 5 does, and guide the detector.

## 2. Reading Google Calendar

- Use Frappe's own Google Calendar integration (core `Google Calendar` and `Google Settings`, syncing into core `Event`, which already has `life_space`). **Read-only**: pull from Google on, push to Google off, for every calendar a user connects through Life OS. `lifeos/api/calendar.py` already reports `google_status`; build on it.
- Settings > Me gets **Calendar**: Connect Google Calendar (Frappe's OAuth flow), which calendars to read, last synced, Disconnect. The OAuth client ID and secret are entered by the owner in Google Settings himself; they are never written to the repo, logs or docs. If Google Settings is not configured, the screen says so and the review works without meetings.
- Sync the last 21 days and the next 14 days, hourly through Frappe's scheduler and when the review opens. Events are private to the user who connected the calendar, in his Private space, whatever the calendar's sharing.
- **Meetings that matter.** An event matters when it has at least one attendee whose email domain is not one of **your domains** (a new setting in Settings > Me, prefilled from the owner's own addresses), lasts 30 minutes or more, and is not a recurring event whose attendees are all from your domains. Events with no attendees do not matter. Each event can be marked "matters" or "doesn't matter" by hand, which overrides the rule. Store the result on the event (custom field `life_matters`, Check, with `life_matters_set_by` Rule or Owner).
- **Linking records to meetings.** New DocType **`Life Meeting Link`**: event, record type and name, `how` (Time, People, Both, Owner). A capture, voice note, email digest entry, chat log or note is linked when it was created during the meeting or within two hours after it, and when it names an attendee (email, or a `Life Person` matched by name or email). Time alone links only voice notes and captures made within 30 minutes after the end. The owner can link or unlink by hand in the meeting drawer.
- **Follow-ups.** With an API key and within the cap, the nightly insights job reads each meeting that matters with linked records and stores findings (Promise, Date) linked to the meeting. Meetings that matter with nothing linked produce one "Not captured" finding per review period, listing them.
- In tests and on the acceptance site, a fake calendar source (fixture events with attendees) replaces Google; the real integration is checked by hand with the owner after the set.

## 3. Tab 1: Library (boards 28 and 29)

- Heading "What came in, and what it means".
- **Last week's calendar strip:** the review period's days, each with its events. Meetings that matter are white cards with a mark: a filled green dot if something is linked or a follow-up was found, an empty orange ring if nothing was captured. Other events are grey and smaller. With no calendar connected, the strip is replaced by one line: "Connect Google Calendar to see last week's meetings here" (link to Settings > Me > Calendar).
- **A meeting opened** (board 29): title, time, attendees, area; **Linked to this meeting** (each opens its record; link and unlink by hand); **Follow-ups found** (each with its action: Make task, or for a date "Add as a dated task" (adding it to Google Calendar comes with set 9), and Not needed); **Anything to plan from this meeting?** (a line that becomes a task on Enter, linked to the meeting, with the goal it will link to suggested and changeable); ← and → move to the previous or next meeting that matters; **Done with this meeting**.
- **Came in** (left card): counts for the period by source: captures and voice notes, Claude and other chats, emails from people (email digest entries), notes changed, meetings that matter. Each count opens its list (count rule). The **Inbox** line underneath shows the piles' suggested split ("Accept 5 · Park 4 · Let go 2 · 0 need you") and **Review the piles**, which opens the pile drawer for Inbox items.
- **Revelations** (right card): at most five findings for the period, most useful first, each with its kind, text, source and one or two actions (board 28). Acted-on and dismissed ones leave the list; the count drops ("Revelations · 3 left"); when none are left: "Nothing left to look at". Without an API key, show only the rule-based findings and the line "The assistant is not set up, so revelations are limited".
- Precision matters more than recall. A finding is shown only with its source; when the detector is unsure, it leaves the finding out.

## 4. Tab 2: Tasks (board 30)

- Heading "Your commitments".
- **Left your plate:** the four Outbox piles for the period (Done, Delegated, Parked, Discarded), each opening its list, with "64 came in, 46 went out" and **Open the Outbox**. Read only. No flag on the difference.
- **Needs you** and the three **piles** for existing tasks only: stuck (no change for more than 30 days, as Reset defines it) and waiting on others. Items that came in during the period were handled in Library and do not appear here.
- Counter "N left to clear" with a bar; footer "Next: Goals", open when Needs you and every pile are cleared.

## 5. Tab 3: Goals (boards 31 and 32)

- Heading "Where your goals stand, and next week". Top right: the week's score against the target, and **goal work planned** against free working hours. The planned bar turns orange with "26 h planned, 22 h free" when over; Lock still works.
- **This 12 Week Year:** one row per goal in the current cycle, in the lens: star, name, mark (No ticks, Slipping, On track, from the week's ticks and progress), progress (number goals: current of target; milestone goals: tasks done of total), next action, when and length, who. "Needs a finish line" shows as a link on the row that opens the drawer at set 7's "Done when…" choice. A Suggested reading not yet confirmed shows as a link "1 reading to confirm".
- **Other goals in progress** fold into one line with a count and **Plan any**, which lists them in the drawer; planning one adds it to the rows.
- **Next action** is prefilled in this order: a task created in tabs 1 or 2 for this goal during this review, the goal's oldest open task, an assistant suggestion (within the cap), or empty. Time and length as set 7 built them, within working hours and without overlapping events (now including Google events) or other scheduled tasks.
- **Every cycle goal needs a next action before Lock, or "Skip this goal this week" with a reason** (a short text, required). Stars: **exactly three**, prefilled with the assistant's suggestion (or the three cycle goals furthest behind), required to go on.
- **The calendar** beside the list shows next week (working days) with existing events in grey and goal work in blue. It is a glance view: clicking a block opens that goal's drawer; **Open the full week** opens Plan > Week's calendar in a large view where blocks can be dragged.
- **A goal opened** (board 32): header with cycle, area, finish line, progress and mark; next action (with "other open tasks (N)" to pick one); when and length; **free slots that fit** as chips; who (Me, people from `Life Person`, someone else); what is needed; the top-three star; **Skip this goal this week** and **Save**.

## 6. Tab 4: Reflect and Lock (board 33)

- Heading "What did you learn this week?"
- **What went well?** (required, one line or more) and **What will you do differently?** (optional).
- **The week in numbers:** score against target, in and out, findings acted on and dismissed, items cleared, goals planned and skipped.
- **Last week's note played back:** if the previous review has a "do differently" line, show it. With an API key and within the cap, add one sentence checking it against this week's data where the data can answer it (for example, calls on Tuesdays from the calendar). Without a key, show only the line.
- **When you lock the week** (right card): the top three with their times; what Lock will do (tasks scheduled, tasks delegated, top three pinned to Today, the next review date from Settings > Rhythms); a note that calendar blocks come with set 9.
- **Lock the week** creates or updates each goal's task as set 7 does (`scheduled_at`, `duration_min`, notes, Waiting for someone else), marks the top three (new Check `is_top_three` and Date `top_three_week` on `Life Task`), stores the review's numbers and text, sets the review to Locked, and shows the **done screen**: "Week planned in N minutes", what was decided, the top three, **Go to Today** and **See the week**, and the next review date.
- **Today** shows the week's top three first in Next, with a star, until the next review is locked.

## 7. On a phone

- The tabs become a step bar: "Step 2 of 4 · Tasks", four segments, ticks on done ones.
- Library: the calendar strip becomes a list of the period's meetings that matter, grouped by day; Came in and Revelations stack.
- Piles stack vertically; drawers are full-screen sheets with the footer button always visible.
- Goals: one card per goal; the calendar opens from a button ("Next week") as a sheet.
- No screen scrolls sideways at 390 px.

## 8. Monthly and 12-week reviews

Build the shell (tabs, period, piles, drawers, Life Review) so that a Monthly and a 12 Weeks review can reuse it with their own tabs later. In this set they keep their current screens. Say in `ROADMAP.md` that they move to the shell in a later set.

## What must not change

- Set 7's data and rules: goals, readings, exits, the Outbox, scheduled tasks, working hours, the old-Inbox job.
- The 12-week scoring rules.
- Agents still never accept proposals, confirm readings, park, discard, delete or lock a review. They can create findings through the existing proposal and insight routes.
- Lens, sensitive-item and space rules. Sensitive items show with their lock and are never sent to the model unless the space allows it.
- Nothing is ever written to Google Calendar in this set.

## Checks

- `./tools/scan.sh` reports zero findings; all unit tests pass, with new tests for: the review period (first review, normal, skipped week), resume after pause, tab gates, pile sorting rules without a key, each pile decision and its exit and Undo, Chase creating a task, one finding cleared everywhere, meetings that matter (each part of the rule and the manual override), meeting links (time, people, both, manual), the next-action prefill order, exactly three stars, skip needs a reason, over-capacity, Lock (tasks, top three, numbers, status), the review-note migration, and that calendar sync never writes to Google.
- Add to `tools/acceptance.mjs`, at 1440 px and 390 px, cleaning up after itself, **on data shaped like the owner's** (as bug fix 1 required: migrated goals, number and milestone goals, Suggested readings, delegated tasks, Inbox items of every kind) plus fixture calendar events:
  - Open the review from Today's banner; it opens on Library; the header shows the period; going to Goals is not possible until Tasks is done.
  - Open a meeting that matters with a linked voice note; make a task from a follow-up; it leaves the meeting's drawer and the Revelations list.
  - Confirm a reading from Revelations; the goal row in tab 3 shows the new value.
  - Open the Park pile, move one item to Keep, park the rest; the card shows its done state; the Outbox counts match; Undo restores both.
  - Settle Needs you; Next: Goals opens.
  - Give every cycle goal a next action or a skip with a reason; star three; plan more than the free time and see the warning.
  - Pause and reopen: everything is where it was left.
  - Write what went well; Lock; the done screen shows; Today shows the top three first; the scheduled tasks show on Today and in Plan > Week.
  - No tab of the review scrolls the page at 1440 × 900 with the owner-shaped data; nothing scrolls sideways at 390 px.
- Run the acceptance script against the owner's site once, read-only (opening every review tab and drawer, no writes), as bug fix 1 did.
- Screenshot every new or changed screen at both widths, light and dark, compare with `mockups/set8/`, and fix what is wrong.

## Working rules

- Order: 1 shell, Life Review, layout rule and pile component; 2 Google Calendar reading, meetings that matter and links; 3 Library; 4 Tasks; 5 Goals; 6 Reflect, Lock and Today's top three; 7 phone; checks.
- Run the unit tests and the scan after each step, and the acceptance script after steps 3, 5 and 6; commit once per step.
- Remove set 7's review sections that this replaces (the old Look back with habits, open loops and check-in, and the stacked score, Reset and goal-work sections). Their routes redirect to the new tabs.
- Review the whole diff against `frappe-code-review` before finishing.
- Update `frontend/COMPONENTS.md` (layout rule, piles, drawers), `agent/SKILL.md` (finding kinds agents may create) and `ROADMAP.md` (set 8 done; monthly and 12-week reviews to follow).
- Record deviations in `DECISIONS.md`. Add a "Set 8: The weekly review" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_8_DONE` and commit.
