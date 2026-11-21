# Bug fix 1: the weekly review is blank and freezes navigation

## What the owner sees

On 18 November 2026, on the owner's site (`lifeos.localhost`, signed in as the owner, lens "Private · All of life"), opening **Plan > Week > Review** (`/plan/week?view=review`) shows the header and Plan's tabs but an empty body. The review's Previous week and Next week buttons, which it teleports into the header (`#jr-actions`), are missing. After that, clicking anything else in the app (sidebar links, Plan's tabs) changes the highlighted item but not the page: navigation is stuck until a full reload.

The browser console shows one error:

```
TypeError: Cannot read properties of null (reading 'emitsOptions')
    at XV (index-CnaDY5SG.js:5:20805)
    at B (index-CnaDY5SG.js:5:29611)
    at M (index-CnaDY5SG.js:5:29311)
    ...
```

Set 7's acceptance run passed on this screen. The owner's data differs from the test data: it holds goals migrated from projects in set 6, number and milestone goals from set 7, and real tasks, so the cause may depend on data. It may also depend on timing (the review's `<Teleport to="#jr-actions">` mounting before its target exists, or a child component throwing during render).

## What to do

1. **Reproduce first, on the owner's site and data.** Use Playwright against `http://localhost:18000/life/plan/week?view=review`, signed in as the owner (credentials in the git-ignored `.env`; never print them). Also try reaching the page by clicking Plan > Week > Review from Today, and with a hard reload on the URL. Build the front end in development mode if needed to get a readable stack trace and Vue's warnings. Do not change the owner's data to reproduce it; if a reproduction needs a specific record, copy it to the acceptance site.
2. **Find the root cause** and fix it there. Candidates to check, not conclusions: a child of the review (`KeyResults`, `GoalWork`, `Stat`, `CountLink`, `TaskRow`) throwing during render on real data (a null goal, a goal with no cycle, a migrated goal without fields set 7 expects, a reading without a source); the `Teleport` targets in the journal screens (`WeeklyReview`, `Goals`, `Month`, `Habits`, `WeekGrid`, `Pages`) resolving to nothing. If teleports are involved, use Vue 3.5's `<Teleport defer>` or pass the buttons through a slot instead, in all six screens.
3. **Stop one broken screen from freezing the app.** Add an error boundary around the routed page (an `onErrorCaptured` wrapper in the app shell, plus `app.config.errorHandler` and `router.onError`) so that when a screen fails to render:
   - the page shows a plain message ("This screen could not be shown.") with Reload and a short error reference, using frappe-ui components;
   - the sidebar, the lens, the header and navigation keep working, and leaving the screen clears the error;
   - the error is logged to the browser console with its full stack, and to Frappe's error log through a small whitelisted method (`methods=["POST"]`, typed, rate-limited, logged-in users only), without record contents.
   A failed lazy-loaded screen (a chunk that cannot be fetched after a rebuild) gets the same message with "A newer version of Life OS is available. Reload."
4. **Test what was missed.** Add an acceptance check that opens the weekly review on data shaped like the owner's: a goal migrated from a project, a number goal with a Suggested reading, a milestone goal without `done_when`, a goal with no cycle, a delegated task. Add a check that a screen forced to throw shows the error message and that navigation still works afterwards. Run the acceptance script against the owner's site once, read-only (opening screens, no writes), across every place and Plan and Library tab, and fix any other screen that fails there.

## Checks

- The weekly review renders on the owner's site with his data, at 1440 px and 390 px, with Previous week and Next week in the header.
- Navigation works after visiting the review and after a forced screen error.
- `./tools/scan.sh` reports zero findings; all unit tests pass; `node tools/acceptance.mjs` passes at both widths.

## Working rules

- Record the root cause and the fix in `DECISIONS.md` and add a "Bug fix 1" line to `STATUS.md`.
- Review the diff against `frappe-code-review` before finishing.
- When finished, create an empty file named `BUGFIX_1_DONE` and commit.
