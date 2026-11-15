# UX fixes, set 1: lists, panes and counts

Two patterns, applied across the app. Read `CLAUDE.md`, `STATUS.md` and `DECISIONS.md` first. Do not change the data model unless a fix below needs a new filter argument on an API method.

## Pattern 1: list, then pane

Data is shown as a list the owner can filter. Clicking a row opens the record in a pane over the list. The page does not change.

**`ListView` component.** One shared component used by every list screen.

- A filter bar on top. Filters are held in the URL query, so a filtered list can be linked to, reloaded and reached with the back button.
- A count of matching records beside the title. It always equals the number of rows the filters match, not the number loaded.
- Desktop: rows with aligned columns and a sort control. Phone: stacked rows, and the filter bar collapses into one Filters button that shows how many filters are active.
- Paged with Show more, 50 rows at a time. An empty state that names the active filters and offers Clear filters.
- The row that is open in the pane stays highlighted. The list keeps its scroll position when the pane closes.

**`RecordPane` component.** One shared pane that renders any record type.

- Desktop: slides in from the right, 520 px wide, 760 px for an inbox item under review. The list stays visible and usable beside it.
- Phone: a sheet that slides up from the bottom and covers the screen, with a close button and swipe down to close.
- The open record is in the URL as `?open=<type>:<name>`. Back closes the pane. Reloading the page reopens it.
- Esc closes. Up and down arrows, or j and k, move to the previous and next row with the pane open. Focus moves into the pane and returns to the row on close.
- A header with the record title, its area and project chips, and an Open full page button for records that have one.
- Content by type: task, inbox item (the review screen), note (reader, with Edit), vault document, project (summary and open tasks), goal, journal page, chat log, event, important date.
- `TaskPanel`, the vault panel and the calendar day panel move onto this component.

**Screens to convert.**

| Screen | Change |
| --- | --- |
| Inbox | `ListView` with filters: status, source type, area, date range. A row opens the review in the pane. `/inbox/:id` still works and shows the list with the pane open |
| Timeline | Rows open the pane for their record type instead of navigating away |
| Tasks | List and table views use `ListView`. Filters are written to the URL. Add a Due filter: overdue, today, this week, no date |
| Projects | Default to a list with filters: status, area. Keep cards as a second view. A row opens the project summary in the pane |
| Vault | `ListView` with filters: holder, type, expiry (expired, within 60 days, later, none) |
| Chats | `ListView` with filters: area, project, has open items, date range. Keep the group-by switch. A row opens the chat summary and its open items in the pane |
| Library | Add a list view beside the tree, with filters: area, project, tag. A row opens the note reader in the pane |
| Archive | `ListView` with filters: type, area. A row opens the record read-only in the pane, with Restore |
| Area page, Project page | Every row in every section opens the pane. No row navigates away |
| Today | Task, review, calendar and Coming up rows open the pane |
| Search palette | Enter opens the result in the pane over the current screen |

Full pages stay for deep work: the review screen, the note editor, the project page, the 12 Week Year grid. They are reached with Open full page, not by clicking a row.

## Pattern 2: every number is a door

Any count shown in the app is a link to the list that produced it, filtered to exactly those records. The list's count must equal the number that was clicked.

| Number | Goes to |
| --- | --- |
| Today, To review | Inbox, status To Review |
| Today, proposals waiting | Inbox, status To Review |
| Today, Due today | Tasks, Due: today and overdue |
| Today, overdue | Tasks, Due: overdue |
| Today, Open loops | Tasks, Open loops view |
| Today, week score | Journal, 12 Week Year, current week |
| Inbox row, "4 of 13 proposals" | That item in the pane, scrolled to its pending proposals |
| Area page header: projects, open tasks, notes, documents | Projects, Tasks, Library list, Vault, each filtered to that area |
| Project card and page, "4 of 10 tasks done" | Tasks, filtered to that project, Show done on |
| Section counts on area and project pages | The same list, filtered |
| Chats, open items count | Chats, has open items, same date range |
| Vault expiry badge on Today | Vault, expiry within 60 days |
| Weekly review: done, carried, archived this week | The matching filtered list |

Show pending proposals as "4 of 13 proposals pending" wherever an inbox item is listed.

## Checks

Add these to `tools/acceptance.mjs` and make them pass at 1440 px and 390 px.

- Clicking a row on Inbox, Timeline, Tasks, Projects, Vault, Chats, Library list and Archive opens a pane and the list is still in the page.
- With a pane open, the URL has `open=`. Back closes the pane. Reload reopens it.
- At 390 px the pane covers the screen and closes with its close button.
- For each row of the Pattern 2 table: the number clicked equals the count on the list it leads to.
- Filters on every `ListView` survive a reload.
- No horizontal scrolling at 390 px on any converted screen.

## Working rules

- Keep the look of the approved mockups. This set changes behaviour and layout, not colours or type.
- All existing tests must still pass. Add unit tests for any new API filter.
- Commit once per converted screen. Record deviations in `DECISIONS.md`. Add a "UX fixes, set 1" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_1_DONE` and commit.
