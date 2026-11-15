# UX fixes, set 3: tabbed navigation

Frappe organises information with tabs in three ways: tabs on a record, tabs on a list that split it by state, and tabs on a page with sub-screens. This set applies the same three patterns to Life OS.

**This set needs set 2.** If `UX_FIXES_2_DONE` does not exist, stop: write "Set 3 needs set 2 to be finished first" to `BUILD_BLOCKED` and change nothing.

Read `CLAUDE.md`, `STATUS.md`, `DECISIONS.md` and `frontend/COMPONENTS.md` first. Follow the three-layer rule from set 2: frappe-ui, then `@framework/ui` through our wrappers, then our own.

## Rules for every tab bar

1. **Components.** frappe-ui `Tabs` for record tabs and page tabs. For list tabs use the same component in its tab-bar form above the list. `TabButtons` stays for small view switches (List, Board, Table) only. Read the component source before use; do not guess props.
2. **The open tab is in the URL.** Page and record-page tabs use a `tab=` query parameter (Journal and Calendar keep their existing path form). Tabs inside the record pane use `ptab=`, so the pane and the page behind it do not collide. Reload, Back, Forward and a copied link all return to the same tab. The first tab is the default and adds nothing to the URL.
3. **Counts on tabs** wherever the tab holds a list, shown as a quiet number after the label. A tab with zero still shows, with 0.
4. **Load a tab when it is first opened**, not all at once. Keep it loaded while the screen stays open. Counts come in one call with the screen.
5. **Phone.** One row that scrolls sideways, with the active tab scrolled into view. No wrapping to two rows and no hidden overflow menu. Touch targets at least 44 px high.
6. **Keyboard and screen readers.** Arrow keys move between tabs, as the component provides. Existing shortcuts keep working. Add `[` and `]` for previous and next tab on the page, and list them in the shortcut help.
7. **No tabs inside tabs**, with one allowed case: the record pane has its own tabs while the page behind it has tabs.
8. **A tab never hides the only way to do something.** Primary actions stay in the page header, not inside one tab.

## 1. Record pages

### Area page

Tabs: **Overview**, **Projects**, **Tasks**, **Notes**, **Documents**, **Chats**, **Timeline**.

- **Overview** keeps the page readable at a glance: the sub-area chips, 12 Week Year goals for this area, and a short preview (up to five rows) of active projects, open tasks, and the latest on the timeline. Each preview heading links to its tab.
- **Each other tab is the full list for this area, in place**, using our `ListView` with the area fixed and hidden from its filters. Filters, sort, layouts, the remembered view and the record pane work as on the main screens. The remembered view is saved per tab, shared across areas (the Tasks tab remembers one view for all areas, separate from the main Tasks screen).
- Projects tab shows active and on hold by default, with the same state tabs as the Projects screen (section 2) folded into its filter, not a second tab row.
- Notes tab holds reference notes and project notes, with a filter for "reference only".
- The count links in the page header go away; their numbers are the tab counts. Links elsewhere in the app that point to a main screen filtered by area keep working.
- Quick add for a task stays, at the top of the Tasks tab and in the Overview task preview.

### Project page

Tabs: **Overview**, **Tasks**, **Notes**, **Documents**, **Chats**, **Links**.

- **Overview**: outcome, target date, progress, and a preview of up to five open tasks with quick add.
- **Tasks**: the full list for this project, open by default, with done tasks reachable through the list's state tabs folded into its filter.
- **Links**: what `Backlinks` shows today.
- Status buttons (Put on hold, Drop, Complete, Restore) stay in the header.

## 2. Record pane

The pane gets tabs under its title. Keep the header (title, status badge, actions, close) outside the tabs. Tabs by kind:

| Kind | Tabs |
| --- | --- |
| Task | Details (all fields, filed under), Notes, Links |
| Note | Note (the Markdown), Notes under this one (only if any), Links |
| Project (in the pane) | Overview, Tasks |
| Goal | Actions, Tasks, History across cycles, Links. Result note shows at the top of Actions |
| Chat | Summary, Open items, Links |
| Journal page | Page, Transcript, Created from this page |
| Vault document | Details, File |
| Inbox item | Section 4 below |
| Day, entry and plain panes | No tabs. They are short |

- Add an **Activity** tab only where set 2 adopted `ActivityTimeline` for that kind. Do not build history from scratch in this set.
- A tab whose content is empty and can never be filled for this record (for example "Notes under this one" on a note with no children) is left out. A tab that is empty but can be filled stays.
- If a pane has one tab left after these rules, show no tab bar.
- Opening a record from a count such as "3 open items" opens the pane on the matching tab (`ptab=`), as the `focus` option does today for proposals.

## 3. List screens: state tabs

A row of tabs above the filter bar splits the list by state. A state tab is a preset filter on one field. It replaces that field's control in the filter bar, so there are never two controls for the same thing.

| Screen | Tabs (first is the default) |
| --- | --- |
| Inbox | To review, Waiting for the agent, Failed, Done, All |
| Tasks | Open, Open loops, Waiting, Done, All |
| Projects | Active, On hold, Done, Dropped, All |
| Archive | All, Tasks, Notes, Chats, Documents, Inbox items, Journal pages |
| Chats | All, With open items |
| Vault | All, Expiring soon, Expired |

- **Tasks.** "Open" means Open and Doing. "Open loops" keeps its current definition and its explanatory line. The layout switch (List, Board, Table) becomes a separate `TabButtons` control and no longer contains Open loops. Board is offered only on the Open and All tabs; on other tabs fall back to List.
- **Counts on each tab respect the other active filters** (area, project, dates and the rest), so the numbers always match what the tab would show. Add this to each list's API method as one extra result, computed in one query per screen, not one per tab.
- **URL.** The tab uses the existing short parameter for that field (for example `status=`), so every count link from sets 1 and 2 lands on the right tab with no change. A URL value that matches no tab (for example two statuses at once) selects All and shows the condition in the filter bar.
- **Remembered view.** The tab is part of the saved view for the screen. The rule from set 2 is unchanged: a URL with a query wins and becomes the saved state.
- **Vault** "Expiring soon" uses the same 60-day window as today's expiry filter.

## 4. Phone-only tabs

Below 640 px wide, two side-by-side layouts become tabs. Desktop keeps them side by side.

- **Review an inbox item:** Original, Transcript, Summary, Proposals. It opens on Proposals when there are pending ones, otherwise on Summary. The Accept all and Reject all actions stay visible on every tab.
- **Journal page:** Page, Transcript.

## 5. Settings

Tabs down the left on desktop and across the top on a phone: **Spaces and members**, **Review and archive**, **Areas**, **Tags**, **Check-in dimensions**, **Habits**. Use frappe-ui's settings layout if set 2 adopted it; otherwise `Tabs` in its vertical form. The theme buttons stay in the header.

## 6. Leave as they are

Today, Timeline, Areas, Graph, Library (Tree and List stay a view switch), the Goal page, and everything inside the Journal tabs. Journal and Calendar already have tabs; check they meet the rules above (URL, phone scrolling, `[` and `]`) and change nothing else.

## What must not change

- No record, field, filter or action is removed. Everything on a screen today is still reachable, at most one tab away.
- The API and data model, apart from the tab counts added to list methods.
- Space rules, the pane behaviour, count links, shortcuts and remembered views from sets 1 and 2.

## Checks

- `node tools/acceptance.mjs` passes everything from before at 1440 px and 390 px. Add, at both widths:
  - Area page: each tab opens, shows its count, and its list matches the main screen filtered by that area. Reload stays on the tab. Opening a row opens the pane without leaving the tab.
  - Project page: the same for its tabs.
  - Pane: each kind shows the tabs in the table above; `ptab=` survives a reload; a pane with one tab shows no tab bar.
  - Inbox, Tasks, Projects, Archive, Chats, Vault: each tab's count equals the number of rows it shows, with and without another filter applied. Every count link from Today and the Area page lands on the expected tab.
  - Tasks: Open loops is a tab, the layout switch has three options, and Board is not offered on Done.
  - Phone: the review screen and the journal page show tabs; at 1440 px they do not.
  - Settings: each tab opens and saves as before.
  - No screen scrolls sideways at 390 px; the tab row does.
- All unit tests pass, with new tests for the tab counts in each list method, including a member of another space seeing only their own counts.
- Screenshot every changed screen and each tab at both widths in light and dark, look at each, and fix anything broken.
- Update `frontend/COMPONENTS.md` with a "Tabs" section: the three patterns, which screens use which, and the URL rule.

## Working rules

- Work in this order: shared tab helpers and the URL rule, list state tabs (Tasks first), record pane, Area page, Project page, phone-only tabs, Settings, then the check on Journal and Calendar.
- Run the acceptance script after each step and commit once per step.
- Record deviations in `DECISIONS.md`. Add a "UX fixes, set 3" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_3_DONE` and commit.
