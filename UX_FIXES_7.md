# Set 7: Moving forward

Life OS is judged by what it clears off the owner's plate and what it gets done. This set adds the three pieces that make forward movement visible and planned:

- **Key results:** every goal says how you will know it is done, and number goals show their result against a target.
- **The Outbox:** a record of everything that leaves the plate, in four piles, and an in-and-out line on Today.
- **The weekly review's goal step:** for each goal, the next action, when, who and what is needed, turned into scheduled tasks.

It also adds firm handling of Inbox items left too long.

**This set needs set 6.** If `UX_FIXES_6_DONE` does not exist, write "Set 7 needs set 6 to be finished first" to `BUILD_BLOCKED` and change nothing.

Read `CLAUDE.md` (including "Frappe conventions"), `ROADMAP.md`, `STATUS.md`, `DECISIONS.md`, `frontend/COMPONENTS.md` and `agent/SKILL.md` first. Follow the Frappe skills in `.claude/skills/`, the components rule, the tab rules, the lens and the count rule (every number opens a list with exactly that many rows). Run `./tools/scan.sh` before every commit. Every screen must work at 390 px and 1440 px.

## 1. Key results

### "Done when…" on every goal

- Add to `Life Goal`: `measure_kind` (Select: Milestone, Number). For Number: `measure` (Data, what is measured, for example "Ghillidary yield"), `unit` (Data, for example "kg/ha"), `start_value`, `target_value`, `current_value` (Float), `current_on` (Date). `done_when` (already there) holds the finish line for a milestone goal.
- **Rule for new goals and for edits of a goal's type or measure:** a milestone goal needs `done_when`; a number goal needs `measure`, `start_value` and `target_value`. Existing goals without either are not blocked from saving; they appear in the weekly review under "Needs a finish line" until set.
- **Direction** comes from start and target (weight 84 → 78 goes down). **Progress** is (current − start) / (target − start), clamped to 0 to 100%. A number goal is offered "Mark achieved" when the current value reaches the target; it is not closed automatically.
- **The goal dialog** asks "Done when…" with two choices, A finish line and A number. A **Suggest** button asks the assistant (set 5's AI client, short model, within the spend cap) to propose the kind and, for a number, the measure, unit and target from the title and notes. Without an API key, Suggest uses simple rules (a number and unit in the title suggests Number) or is hidden.
- **Frequencies are habits:** if the title or "done when" reads as a frequency ("daily", "every", "N times a week"), show "This looks like a habit" with **Make it a habit**, which creates the habit in the current month plan and does not create the goal.

### Readings and their history

- New DocType **`Life Goal Reading`**: space, goal, `date`, `value`, `source_doctype`/`source_name` (the capture, chat log or note it came from, optional), `excerpt` (Small Text, the words the value was read from), `status` (Suggested, Confirmed, Rejected), `confirmed_by`, `confirmed_on`. `current_value` and `current_on` always equal the latest Confirmed reading.
- **The assistant pre-fills readings:**
  - Agents: a new proposal kind **Reading** (goal, value, date, excerpt, source) in `submit_result`. Unlike other proposals, a Reading does not wait in the Inbox: it is stored as a Suggested reading for the weekly review. Document it in `agent/SKILL.md`; add it to `fake_agent.py`.
  - In the app: the nightly insights job also looks through the last 7 days of captures and chat logs for values matching a number goal's measure, and stores them as Suggested readings with the excerpt. Only with an API key and within the cap; skip silently otherwise.
- **The owner confirms** Suggested readings in the weekly review (section 3) or from the goal's pane, can edit the value before confirming, or reject it. He can also add a reading by hand at any time.
- **The goal pane** shows, for a number goal: the result bar (start, current, target, unit, with the date of the current value), a small chart of confirmed readings, and the Suggested ones waiting. For every goal: task completion as today.

### Goals serving goals

`serves` exists from set 6. Show it fully:
- A goal shows **Serves** (with that goal's progress) and **Served by** (each serving goal with its kind, progress and cycle).
- Plan > Goals can group by the goal served.
- The 12 Weeks tab shows, beside each cycle goal, the longer goal it serves.

### Lead measures

Weekly actions are the lead measures. They already have `per_week`. Confirm and, if needed, fix: an action with `per_week` greater than 1 is ticked one at a time (on Today's Next and in the 12-week grid), shows "2 of 4 this week", and each tick counts towards the week score. No other numbers on actions.

## 2. The Outbox

### What counts as leaving

New DocType **`Life Exit`**: space, area, `record_doctype`, `record_name`, `title`, `kind` (Capture, Task, Goal, Idea), `pile` (Done, Delegated, Parked, Discarded), `on` (Datetime), `by` (User), `reversed` (Check), `reversed_on`. Written by document hooks on these transitions, and nowhere else:

| Record | Done | Delegated | Parked | Discarded |
| --- | --- | --- | --- | --- |
| Task | Status becomes Done | Status becomes Waiting with someone other than the owner in `waiting_on` | Moved to Someday | Status becomes Dropped, or deleted |
| Goal | Outcome Achieved or Partly Achieved | — | Moved to Someday | Outcome Not Achieved or Dropped, or deleted |
| Capture (inbox item) | Leaves the Inbox with at least one accepted proposal, or as Just keep | — | Parked as an idea in Someday | Every proposal rejected with nothing kept, or deleted |
| Idea | Brought back as a task, goal or note | — | (ideas start parked) | Purged |

- When an exit is undone (a task reopened, an item brought back from Someday, restored from the trash), mark that exit `reversed`; it no longer counts.
- **In** for a period: captures received, plus tasks, goals and ideas created directly (not from a capture, so nothing is counted twice).
- Backfill with a patch for the last 12 weeks from existing dates (`completed_on`, `someday_on`, closed goals, the trash), so the Outbox is not empty on day one. Record what could not be reconstructed in `DECISIONS.md`.

### Where it shows

- **Today's Open band** gets a line: "This week: 64 in, 81 out". Each number opens its list (the captures and records that came in; the Outbox for this week).
- **Library > Outbox** (a new tab after Captures): tabs **Done**, **Delegated**, **Parked**, **Discarded** with counts for the chosen period (default this week; this month and 12 weeks as choices), and an 8-week chart of in against out. Rows show the item, its kind, area, when and the pile. Row action: **Bring back** where the record allows (reopen a task, bring back from Someday, restore from the trash), which reverses the exit.
- The Outbox is a record, not a place to work: no bulk actions beyond Bring back.
- Respects the lens and space rules; sensitive items show with their lock.

## 3. The weekly review

Plan > Week's review becomes three steps, then the look back that exists today.

1. **Score and results.**
   - This week's 12-week score and the target.
   - **Readings to confirm:** every Suggested reading, with its excerpt and source link: Confirm, Edit and confirm, Reject.
   - **Needs a finish line:** goals with neither a finish line nor a number, each with the "Done when…" choice inline.
   - For each number goal with no reading in the last 14 days: "Where is [measure] now?" with a value box and Skip.
2. **Reset**, as built in set 5.
3. **Goal work for the coming week.** One card per active goal in the lens (the current cycle's goals first, then other In Progress goals not on hold), each with:
   - **Next action:** pre-filled with the goal's oldest open task, or a suggestion from the assistant (within the cap), editable.
   - **When:** a suggested slot within working hours that does not overlap events or other scheduled tasks, editable; or "No set time".
   - **Length:** suggested by the assistant from the action (30, 60 or 90 minutes; without a key, 60), editable.
   - **Who:** Me (default), or a person (from Life Person, or typed).
   - **What is needed:** a short note.
   - **Add** creates or updates the task under the goal: `scheduled_at`, `duration_min` (new fields on Life Task), the note in `notes_md`. If "who" is someone else, the task becomes Waiting with `waiting_on` set, which records a Delegated exit. **Skip** leaves the goal for this week.
   - A footer adds up the planned time and compares it with the free working time in the week: "Planned 9 h of goal work; 22 h free in working hours."
4. **Look back:** habits, done, open loops, decide, latest check-in and the review note, as today.

Scheduled tasks show at their time on Today (in Next's Today group and on the rail's timeline) and in Plan > Week's calendar. Writing them to Google Calendar is set 8.

**Working hours:** add to Settings > Your life > Rhythms: working days, start and end time (default Monday to Saturday, 09:00 to 19:00).

## 4. Inbox items left too long

In Settings > Your life > Reset rules, add **"Inbox items not dealt with"**: one of

- **Suggest decisions after N days** (default, N = 7),
- **Park them after N days** (N = 14; parked as ideas in Someday),
- **Discard them after N days** (N = 14; moved to the trash, restorable for 30 days).

How it works:
- A nightly job looks at items To review (and New items not claimed) older than N days.
- **Suggest:** for each, store a suggested decision with a one-line reason: Accept the proposals as they are, Park as an idea, or Discard. Use the assistant within the cap; without a key use rules (items with tasks or dates: Accept; notes only: Park; nothing extracted: Discard). The Inbox shows a banner "12 items older than 7 days have suggested decisions" opening a batch screen: each item with its decision and reason, checkboxes, Confirm selected, change any one. Also add this batch to Reset's suggested batches.
- **Park or Discard:** the job acts, records the exit, and Today's banner line says what it did with an Undo for 7 days.
- Items Waiting for the agent and Failed items are never acted on automatically.

## What must not change

- Goals keep their data; no goal is reclassified without the owner's action.
- The 12-week scoring rules, apart from counted actions scoring per tick.
- Agents still never accept proposals, confirm readings, park, discard or delete.
- Lens, sensitive-item and space rules.

## Checks

- `./tools/scan.sh` reports zero findings; all unit tests pass, with new tests for: the goal rule, progress in both directions, readings and `current_value`, every exit transition and its reversal, In without double counting, the backfill, the old-Inbox job in all three modes, slot suggestion within working hours without overlaps, and Delegated tasks.
- Add to `tools/acceptance.mjs`, at 1440 px and 390 px, cleaning up after itself:
  - Create a milestone goal and a number goal through the dialog; a frequency title offers Make it a habit.
  - The fake agent submits a Reading; it appears in the weekly review; confirming updates the goal's current value and result bar.
  - A 12-week goal serving a longer goal shows on both.
  - Ticking a "4 per week" action once shows "1 of 4" and raises the week score.
  - Completing, delegating, parking and dropping a task each add to the right Outbox pile; Bring back reverses it; Today's in-and-out numbers match their lists.
  - The weekly review's goal step creates a scheduled task that shows on Today and in the week calendar, and a delegated one that shows as Waiting.
  - With the setting on Suggest, an old Inbox item gets a suggested decision and the batch confirms it; on Park and Discard the job acts and Undo restores.
  - No screen scrolls sideways at 390 px.
- Screenshot every new or changed screen at both widths, light and dark, and fix what is wrong.

## Working rules

- Order: 1 key results (fields, dialog, readings, pane, serves, counted actions); 2 the Outbox (exits, hooks, backfill, Today line, Library tab); 3 working hours and the weekly review; 4 old Inbox items; checks.
- Run the unit tests and the scan after each step and the acceptance script after steps 2 and 3; commit once per step.
- Update `frontend/COMPONENTS.md`, `agent/SKILL.md` (Reading proposals) and `ROADMAP.md` (set 7 done).
- Record deviations in `DECISIONS.md`. Add a "Set 7: Moving forward" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_7_DONE` and commit.
