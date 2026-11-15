# UX fixes, set 3: tabbed navigation, Settings, the sidebar and permissions

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

Settings is rebuilt, not just split. Today it shows six unrelated jobs at once in two columns, repeats three text buttons on every row, mixes personal and admin settings, and shows technical role names.

### Layout

A left menu with three groups. One section shows at a time, in a single column no wider than about 720 px. Use frappe-ui's settings layout if set 2 adopted it; otherwise `Tabs` in its vertical form. The open section is in the URL (`tab=`).

| Group | Sections |
| --- | --- |
| Me | Appearance, Default space, Weekly review |
| This space | Areas, Tags, Habits, Check-in dimensions, Archive rules, Archived |
| Admin | Spaces and members, Agents |

- **This space** has a space picker at the top of the group, defaulting to the current space. Every section under it names the space in its heading. Changing it here does not change the space in the sidebar.
- **Admin** shows only to a Life Admin.
- **Phone:** the menu is the first screen; tapping a section opens it full width with Back to return.

### Lists: areas, tags, habits, check-in dimensions

One shared component for all four.

- A row shows the name and a quiet count of what sits under it (areas: active records; tags: tagged records; habits: months it is used in; dimensions: check-ins that scored it). The count links to the matching list where one exists.
- **Reorder by dragging** a handle, where the list is ordered. Areas can also be dragged under another area to nest them, one level deep as today, and back out to the top level. Keyboard: with a row focused, Alt+Up and Alt+Down move it. On a phone, the row menu offers Move up, Move down and Move under.
- **Rename in place:** click the name, edit, Enter saves, Escape cancels.
- **One "…" menu per row** with Rename, Move under (areas), and Archive. No row of text buttons.
- **One "New …" button** at the top right of the section, opening a small dialog (name, and for an area, its parent).

### Archive, never delete

Nothing in these four lists is deleted from Settings. The only removal is **Archive**.

- Archiving an area asks for confirmation in a `Dialog` that states what happens: the area leaves the Areas screen, the pickers and the filters; its records are not changed and stay where they are, still findable through search, the Timeline and their own screens. If the area has sub-areas, they are archived with it and the dialog says how many.
- Archiving a tag, habit or dimension works the same way: it leaves the pickers, and past records that use it keep it.
- Keep the server behaviour for archiving as it is today. If the current code does something different from the description above (for example to the records under an archived area), keep the code's behaviour, make the dialog describe it accurately, and note it in `DECISIONS.md`.
- Remove the delete path for these four kinds from the Settings screen. The API method may keep it for agents and tests.

### Archived section

A separate section, under This space, listing everything archived from these lists, grouped as Areas, Tags, Habits, Check-in dimensions.

- A row shows the name, when it was archived, and the count of records still filed under it.
- **Restore** on each row puts it back where it was (an area returns under its old parent if that parent is active, otherwise at the top level). Restoring an area asks whether to restore the sub-areas that were archived with it.
- A link at the top, "Archived records are on the Archive screen", goes to `/archive`. This section is only for the headings themselves; archived tasks, notes and the rest stay on the Archive screen.
- If the archive date is not stored today, add it (`archived_on`) to these four DocTypes with a patch that leaves existing archived rows blank. This and the counts are the only data changes Settings needs.

### Spaces and members

- A list of spaces on the left of the section (or a `Select` on a phone); choosing one shows its members as rows: `Avatar`, name, email, access, and a "…" menu with Remove.
- Access is a `Select` reading **Can view** or **Can edit**. Do not show role names such as "Life Agent, Life Admin, Life User" anywhere.
- Hide the built-in Administrator account from every list.
- Agents are not shown here; they are in the Agents section.
- **Add member** opens a dialog with a user search (`Link` on User through our wrapper), not a free-text email box, plus the access choice.
- The owner of a space cannot be removed and shows an "Owner" badge.
- **New space** is a button opening a dialog (name, owner). The line about a new space starting with four areas becomes help text in that dialog.
- Removing a member asks for confirmation.

### Agents

Lists the agent users (Hermes, Claude and any other with the agent role): name, which spaces each can reach with what access, and when each last filed something if that is cheap to read from existing data. Access per space is changed here with the same Can view / Can edit control. No keys or secrets are shown or created on this screen.

### Plain settings: Appearance, Default space, Weekly review, Archive rules

- One setting per row: label, one line of help text, control on the right (stacked on a phone).
- **Appearance:** Light, Dark, System as `TabButtons`. Remove the theme buttons from the page header.
- **Weekly review:** review day, review time, score target.
- **Archive rules:** archive after (days), task is stale after (days), each with help text saying exactly what it does (for example which record types are never archived automatically).
- Each change saves on its own and confirms with a short "Saved" toast, or shows the error inline under the field and restores the old value.

## 6. Sidebar

Today the sidebar is 13 items in one flat list at equal weight. Rebuild it in groups, with the owner's areas in the middle. Use frappe-ui's `Sidebar` as adopted in set 2.

| Group | Items |
| --- | --- |
| Top | Space switcher. Under it, **Search** (with the ⌘K hint) and a **New** button side by side |
| (no heading) | Today, Inbox, Tasks, Calendar |
| Plan | Journal, Projects |
| Areas | Every active area of the current space, in its saved order, with sub-areas nested under their parent |
| Records | Notes, Vault, Chats, Timeline |
| Bottom, pinned | Archive, Settings |

- **Areas group.** Each area links to its area page. A parent with sub-areas has a chevron to expand it; clicking its name still opens the parent's page. The group heading "Areas" links to the all-areas screen (`/areas`). If a space has more than 12 top-level areas, show the first 12 and a "All areas" row. Archived areas do not show. The list updates at once when an area is added, renamed, reordered or archived in Settings.
- **Collapsible groups.** Plan, Areas and Records each collapse from their heading. Which groups and which parent areas are open is remembered per user, with the other view state from set 2. All open by default.
- **Active item.** Exactly one item is marked active. On an area page it is that area (and its parent is expanded). On a project page it is Projects. On `/areas` it is the Areas heading.
- **Counts.** Inbox keeps its count of items to review. Tasks gains a count of tasks due today or overdue, the same number as Today's "Due today". No other counts. Both update when the underlying number changes, without a reload.
- **New button.** Opens a small menu: Task (the existing quick add), Note, Project, Add to Inbox. The `n` shortcut still opens quick add for a task directly.
- **Rename Library to Notes.** This is a label change everywhere the word shows: sidebar, page title, breadcrumbs, empty states, search results, shortcut help, phone "More" list. The route stays `/library` and the DocType stays `Life Note`. **Vault keeps its name.**
- **Graph leaves the sidebar** and becomes a third view on the Notes screen, beside Tree and List. The route `/graph` keeps working and opens Notes on the Graph view. Its `g` shortcut, if it has one, still works.
- **Timeline** gains a `Tooltip` on its sidebar item: "Everything, by date".
- **Collapsed rail.** If frappe-ui's sidebar offers a collapsed icon-only state, enable it on desktop, remembered per user. In that state the Areas group shows one Areas icon that opens `/areas`.
- **Phone.** The bottom bar is unchanged: Today, Inbox, Tasks, Journal, More. "More" opens this same grouped list, full screen, with Search and New at the top. The Tasks tab shows the same count as the sidebar.
- **Access.** A member with view-only access sees no New button. Everyone sees only the areas of spaces they belong to.

## 7. Permissions: three small tightenings

The role design stays as it is: three roles (Life User, Life Admin, Life Agent) say what kind of user someone is, and space membership says which records they reach. Add no roles. These three items close gaps around that design.

### Agents and the Vault

- Add a check field to `Life Space`: `agents_can_read_vault`, off by default, with a patch that leaves it off for existing spaces.
- While it is off, an agent (a user for whom `is_agent` is true) cannot read any `Life Vault Document` in that space or any file attached to one. Enforce this on the server in every path: the DocType permission hooks and list queries, the `lifeos.api` methods, `Life Index` rows of kind Vault (search, Timeline, area and project pages, counts), backlinks, and the file download check. An agent gets the same answer as for a record that does not exist. Counts shown to an agent leave these rows out.
- An agent may still **propose** a vault document from an inbox item, because the owner accepts it. The agent cannot read it back after it is filed.
- While the switch is on, agents read Vault documents under the normal space rules.
- The switch is on the Agents section in Settings, one per space, with help text: "Let agents open documents in this space's Vault. Off by default." Only a Life Admin can change it.
- People are not affected by this switch.

### Desk access

- A user whose only Life roles are Life User or Life Agent cannot open the back-office screens at `/app`. The install already creates those two roles without desk access; confirm it holds on the test site for the family and agent test users, including when the user also has roles Frappe adds by default. If Frappe's own default roles give desk access, record what was found and the fix in `DECISIONS.md`.
- Such a user who goes to `/app` lands on `/life`.
- The agent's API and MCP access must keep working without desk access. Run the fake agent end to end to confirm.
- Do not give any Life role the System Manager role, and do not require it anywhere in the app.

### Agent accounts stay agents

- The code treats a user as an agent only when they have Life Agent and neither other Life role. Make the mix impossible: on saving a User, refuse the combination of Life Agent with Life User or Life Admin, with a clear message. Add a patch that reports (does not change) any existing user with the mix.
- The Agents and the Spaces and members sections in Settings never offer an action that would create the mix.

### Tests

Unit tests, run as the agent, family and owner test users:

- With the switch off, the agent cannot get, list, search, count or download a Vault document or its file, by any API method that returns records, and cannot see it in a Timeline, area or project result. With it on, the agent can. The owner and a family member with access are unaffected either way.
- The family user and the agent user are refused at `/app` and the agent's `claim_next` and `submit_result` still work.
- Saving a user with Life Agent plus Life User is refused.

## 8. Leave as they are

Today, Timeline, Areas, Library (now labelled Notes; Tree, List and Graph are a view switch), the Goal page, and everything inside the Journal tabs. Journal and Calendar already have tabs; check they meet the rules above (URL, phone scrolling, `[` and `]`) and change nothing else.

## What must not change

- No record, field, filter or action is removed. Everything on a screen today is still reachable, at most one tab away.
- The API and data model, apart from the tab counts added to list methods and the small additions the Settings and Permissions sections name.
- Space rules, the pane behaviour, count links, shortcuts and remembered views from sets 1 and 2.

## Checks

- `node tools/acceptance.mjs` passes everything from before at 1440 px and 390 px. Add, at both widths:
  - Area page: each tab opens, shows its count, and its list matches the main screen filtered by that area. Reload stays on the tab. Opening a row opens the pane without leaving the tab.
  - Project page: the same for its tabs.
  - Pane: each kind shows the tabs in the table above; `ptab=` survives a reload; a pane with one tab shows no tab bar.
  - Inbox, Tasks, Projects, Archive, Chats, Vault: each tab's count equals the number of rows it shows, with and without another filter applied. Every count link from Today and the Area page lands on the expected tab.
  - Tasks: Open loops is a tab, the layout switch has three options, and Board is not offered on Done.
  - Phone: the review screen and the journal page show tabs; at 1440 px they do not.
  - Settings: every section opens from the menu and from its URL. Rename, reorder and nest an area. Archive an area with a sub-area: both leave the Areas screen and the area pickers, their records are unchanged, and both appear under Archived. Restore brings them back in place. No Delete or Remove action exists for areas, tags, habits or dimensions. Add and remove a member through the dialogs. No role name and no Administrator row appears. A changed setting shows "Saved" and survives a reload. The family test user sees no Admin group.
  - Sidebar: the groups and items match the table in section 6. Each seeded area shows and opens its page, and is marked active there. Sub-areas expand under their parent. Collapsing a group survives leaving and reloading. The Tasks count equals Today's "Due today" number and drops by one when such a task is completed. New opens its menu and each entry works. "Library" appears nowhere in the interface; "Notes" opens `/library`. `/graph` opens the Graph view of Notes. Archiving an area in Settings removes it from the sidebar without a reload. The phone More list shows the same groups.
  - No screen scrolls sideways at 390 px; the tab row does.
- All unit tests pass, with new tests for the tab counts in each list method, including a member of another space seeing only their own counts.
- Screenshot every changed screen and each tab at both widths in light and dark, look at each, and fix anything broken.
- Update `frontend/COMPONENTS.md` with a "Tabs" section: the three patterns, which screens use which, and the URL rule.

## Working rules

- Work in this order: shared tab helpers and the URL rule, list state tabs (Tasks first), record pane, Area page, Project page, phone-only tabs, Settings (layout first, then the shared list component, archive and the Archived section, members and agents), the sidebar, permissions (section 7), then the check on Journal and Calendar.
- Run the acceptance script after each step and commit once per step.
- Record deviations in `DECISIONS.md`. Add a "UX fixes, set 3" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_3_DONE` and commit.
