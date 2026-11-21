# UX fixes, set 2: build the front end the way Frappe builds its own apps

The front end uses frappe-ui 1.2.0 only for `Dialog`, `Dropdown` and `toast`. Buttons, inputs, selects, pills, tabs, the shell, the list filters and the colour tokens are hand-written. This set moves the app onto three layers, in this order of preference:

1. **frappe-ui** for basic controls, the shell and tokens.
2. **`@framework/ui`** for anything that knows about a DocType: list controls, link fields, record fields, activity, file upload. This is Frappe's own Vue package. It ships inside Frappe 16.56 at `apps/frappe/ui` and is the base Frappe is building its next Desk on.
3. **Our own components** only where neither has one (the journal screens, the pane, the graph). These follow the same design decisions.

Read `CLAUDE.md`, `STATUS.md` and `DECISIONS.md` first. Then read, in the bench: `apps/frappe/ui/README.md`, `CONTEXT.md`, `PHILOSOPHY.md`, `src/components/ListView/USAGE.md` and the ADRs under `docs/adr/`. Before using any component, read its source and types (`frontend/node_modules/frappe-ui/src/components/<Name>/` or `apps/frappe/ui/src/components/<Name>/`). Do not guess props.

## Step 0: prove `@framework/ui` works here, before anything else

`@framework/ui` is not on npm. It is raw source, version 0.0.0, linked by relative path from the bench, and it can change with any Frappe update. Do this first and stop to decide before going further.

1. Link it as its README says: `"@framework/ui": "link:../../frappe/ui"` in `frontend/package.json`, the `paths` entries if TypeScript is used, and its Vite plugin (`@framework/ui/vite`) in `vite.config.js` alongside the frappe-ui plugin.
2. The path must resolve in both places the front end is built: this repo mounted into the Docker bench, and a normal bench where the app sits at `apps/lifeos` (the live site, through `bench build --app lifeos`). From now on the front end is built **inside the bench container**, not on the host. If the mounted repo breaks the relative link, fix the mount or the link so one `package.json` works in both. Update the build commands in `STATUS.md` and `README.md`.
3. Build a throwaway page with `useListView('Life Task')`, `Filter`, `QuickFilter`, `SortBy`, `GroupBy` and `ColumnSettings`, and the same against `Life Index`. Confirm: the bundle builds, there is one copy of Vue and of frappe-ui, the controls render and produce wire filters, and they work at 390 px wide.
4. Check its peer requirement (`frappe-ui >= 1.0.0-rc.1`) against our pinned 1.2.0. If a newer frappe-ui is needed, move to the exact version Frappe's own `ui/` tests against and pin it.

**If step 0 fails** and cannot be fixed in a reasonable effort, do not force it. Record why in `DECISIONS.md`, and carry out the rest of this set with frappe-ui only: build the list controls from frappe-ui primitives (and try `frappe-ui/experimental/ListView` for rows) behind the same wrapper described below, so `@framework/ui` can be dropped in later.

**If it works**, record in `DECISIONS.md` the Frappe version it was proven on, and add a line to `STATUS.md` under upgrade notes: after any Frappe update, rebuild the front end and run the acceptance script before using the site.

## Rules

1. **A library component wherever one exists**, frappe-ui first, then `@framework/ui`. No hand-written button, input, select, checkbox, switch, textarea, date picker, tab bar, badge, dialog, dropdown, tooltip, progress bar, avatar, tree, breadcrumb, file upload, loading state, filter builder, sort control or link picker.
2. **`@framework/ui` only through our wrappers.** Import it only inside files under `frontend/src/framework/` (for example `LifeFilter.vue`, `LifeLink.vue`, `useLifeListView.js`). Screens import the wrappers. If Frappe changes the package, only that folder changes.
3. **frappe-ui tokens only.** Remove the Life OS colour variables (`--bg`, `--ink`, `--line`, `--accent` and the rest). Use the semantic Tailwind classes from the frappe-ui preset (`bg-surface-*`, `text-ink-gray-*`, `border-outline-gray-*` and their coloured variants). No hex colours in components or CSS, except inside the graph and chart drawing code, which read token values from CSS variables.
4. **frappe-ui scale.** Use its type sizes, spacing, radii, control heights, focus rings and shadows through the preset's Tailwind classes. Remove the custom `.bt`, `.inp`, `.ch`, `.pl`, `.cd`, `.ck`, `.sh`, `.mt` classes as each is replaced.
5. **Lucide icons** through frappe-ui's icon plugin. Remove `Ico.vue` and the hand-written SVG paths.
6. **Dark mode** through frappe-ui's colour scheme support only. Remove the `[data-theme]` variable block.
7. **No browser `prompt()` or `confirm()`.** Use frappe-ui dialogs.
8. **Our own components follow the same decisions.** Read frappe-ui's `PHILOSOPHY.md` (naming, `v-model`, slots, styling). Where neither library has a component, build ours from frappe-ui primitives and tokens, with the same sizes, radii, focus and hover treatment, so they are indistinguishable in style.

## Replace with frappe-ui

These components exist in frappe-ui 1.2.0 and must be used.

| Now | Use |
| --- | --- |
| `.bt` buttons (about 124 uses) | `Button` with its variants and sizes |
| `.inp` inputs, raw `<select>`, `<textarea>` (about 110 uses) | `FormControl`, `TextInput`, `Select`, `Combobox`, `MultiSelect`, `Textarea` |
| `.ck` checkboxes and toggles | `Checkbox`, `Switch` |
| Date inputs | `DatePicker` |
| `.pl` pills and `.ch` chips that only show state | `Badge` |
| `.ch` chips used as view switches | `TabButtons` |
| Page tabs (Journal, Calendar) | `Tabs` |
| `PageHead.vue`, `.hd`, `.crumb` | `PageHeader`, `Breadcrumbs` |
| Sidebar and space switcher | `Sidebar` (and `DesktopShell` if it fits) |
| Phone tab bar | `MobileNav` (and `MobileShell` if it fits) |
| Phone sheet in `RecordPane` | `BottomSheet` |
| Progress bars | `Progress` |
| Library tree | `Tree` |
| Loading states | `Skeleton`, `LoadingIndicator`, `Spinner` |
| Hints on icon buttons | `Tooltip` |
| Keyboard hints, shortcut help | `KeyboardShortcut`, `KeyboardShortcutsDialog` |
| Person and agent markers ("filed by Hermes") | `Avatar` |
| Empty states and inline notices | `Alert` where it fits, otherwise `Empty.vue` restyled with tokens |
| `prompt()` and `confirm()` in Settings and elsewhere | `Dialog` |
| Search palette popover, pickers | `frappe-ui/experimental/CommandPalette` if it can be fed from our search method, otherwise `Popover`, `Combobox`, `Menu` |
| Calendar month and week views | `frappe-ui/experimental/Calendar` if it can show our event types and open the pane on click, otherwise ours. The year view stays ours |
| Settings screen | `SettingsDialog` if its layout fits, otherwise the page built from the form components above |

Parts under `frappe-ui/experimental` may change. Import them through a wrapper of ours too, and pin frappe-ui exactly.

## Replace with `@framework/ui`

| Now | Use |
| --- | --- |
| Hand-written filter bar in `ListView` | `Filter` (advanced conditions) and `QuickFilter` (the always-visible strip), bound to the same conditions |
| Hand-written sort menus | `SortBy` |
| Group headers and group pickers | `GroupBy` |
| Table view column choices | `ColumnSettings`, with drag-resize bound to the same columns |
| List state held in each screen | `useListView(doctype)`, one per list, through `useLifeListView` |
| Pickers for area, project, person, goal, space and any other Link field | `Link` |
| Field controls in `RecordPane` and in create dialogs | `FormLayout` and its field components where the pane shows plain DocType fields. Keep our layout where the pane is purpose-built (review, journal page, Markdown body) |
| Inbox drop zone and file inputs | `FileUpload` (falls back to frappe-ui `FileUploader` if it cannot upload as private files attached to the right record) |
| Record history and comments in the pane | `ActivityTimeline`, if it reads from standard Frappe versions and comments without extra back-end work. Otherwise leave as is |

Notes for the list work:

- **Fetching stays ours.** `useListData` calls `frappe.client.get_list` directly. Our lists must keep going through the `lifeos.api` methods, because those apply the space rules and read cross-type lists from `Life Index`. Take `view.filters.wire` and `view.sort.orderBy` from `useListView` and pass them to our methods. Extend those methods to accept a standard Frappe filter list and `order_by` and validate every field name against the DocType's meta on the server. Use `useListData` only where a list is a plain single-DocType read and the result is identical, permissions included.
- **Cross-type lists** (Timeline, Area, Archive) use `useListView('Life Index')`. The filterable fields are then the index's own columns, which is the intent.
- **Views.** List, board, table and cards remain a view switch on our `ListView`. Board and cards rows stay ours. For list and table rows, try `@framework/ui/experimental/List`, then `frappe-ui/experimental/ListView`, and keep ours only if neither supports the selected-row state the pane needs and the phone row layout.
- **Phone.** Below 640 px the quick-filter strip collapses into a Filters button with the count of active filters, opening the same controls in a `BottomSheet`.
- **Existing URLs keep working.** The count links and filters from set 1 use short query parameters (`status=`, `area=`, `due=` and so on). Keep these as the URL form. Add one mapping module that turns them into filter conditions and back, with unit tests. Conditions that have no short form go in a single `f=` parameter.

## Keep as ours, rebuilt on the primitives and tokens

| Component | How |
| --- | --- |
| `ListView` | Stays as the wrapper every list screen uses. It owns the view switch, the URL mapping, the pane selection and the remembered state. Everything inside it comes from the two libraries as listed above |
| `RecordPane` | Desktop slide-over stays ours, styled with tokens and frappe-ui's dialog shadow and radius. Phone uses `BottomSheet`. Header buttons are `Button` |
| 12 Week Year grid, habit boxes, year calendar | Ours. Cells are `Button`-sized and use token colours for done, missed, current and future |
| Line chart, graph | Ours. Colours read from the token CSS variables so both themes work |
| Markdown reader and editor | Ours. Toolbar buttons are `Button`. Editor theme uses token variables |
| Review layout, month plan layout, check-in form | Ours for layout. Every control inside is from the libraries |

## Behaviour change in this set: lists remember their view, on every device

Today a list's filters survive a reload but are lost when the owner goes to another screen and comes back. Fix this once, in `ListView`.

- **What is saved.** The `useListView` snapshot (filters, sort, columns, quick-filter fields, group by) plus our view switch (list, board, table, cards). One saved state per user, per screen, per space.
- **Where.** On the server, so the phone and the laptop agree. Add one small DocType, `Life View State` (user, screen, space, state as JSON), with two methods in `lifeos.api`: read all of the user's states in one call at start-up, and save one. A user can read and write only their own rows. Agents cannot. Keep a copy in `localStorage` so a list opens instantly, and let the server copy win when it arrives. Save with a short debounce (about one second) and never block the screen on it. This is the one permitted addition to the data model in this set; add unit tests for the permission rule.
- **Opening a list with no query in the URL** (the sidebar, the phone tab bar, a `g` shortcut, Back to a bare route) restores the saved state and writes it into the URL.
- **Opening a list with a query in the URL** (a count link, a link from another record, a bookmark) uses exactly that query and ignores the saved filters. It then becomes the saved state. Saved columns and view still apply. Every count link must carry at least one query parameter so this rule holds; a link that means "everything" carries `all=1`.
- **The open record** (`open=`) is never saved or restored. Coming back to a list shows the list, not a pane.
- **A remembered filter can hide records**, so the list always shows when filters are active: the count of active filters and a Clear button, on desktop and on the phone's Filters button. Clear removes the filters and saves the cleared state. Columns have their own Reset in `ColumnSettings`.
- **Switching space** uses that space's own saved state.
- **Checks to add to `tools/acceptance.mjs`**, at both widths: set a filter on Tasks, go to Today through the sidebar, come back through the sidebar, and the filter is still set and is in the URL. Open a second browser context as the same user and Tasks shows the same filter. Click the Open loops number on Today and Tasks shows only open loops, whatever was saved. Clear removes it, and it stays cleared after leaving and returning. The family test user sees none of the owner's saved states.

## What must not change

- Behaviour, apart from the remembered views above and the richer filter, sort, group and column controls that come with the library. Every screen, route, existing filter, pane, shortcut and count link works as it does now.
- Information on each screen. This set changes components and styling, not content or layout structure.
- The API and the data model, apart from `Life View State` and the list methods accepting standard filters. Space rules are still enforced on the server for every read.

The approved mockups remain the reference for layout and density. Where a frappe-ui token differs from a mockup colour, the token wins.

## Checks

- `node tools/acceptance.mjs` passes all items at 1440 px and 390 px, as before, plus the new ones.
- All unit tests pass, with new tests for the URL mapping, `Life View State` permissions and server-side validation of filter field names.
- `grep` finds none of these in `frontend/src`: `class="bt`, `class="inp`, `class="ck`, `window.prompt`, `window.confirm`, `<select`, a `#` hex colour outside the chart and graph files, `Ico.vue`, and no import of `@framework/ui` outside `frontend/src/framework/`.
- `frontend/src/styles.css` holds only the frappe-ui import, layout helpers, and the reading typeface. Aim for under 80 lines.
- A fresh `yarn install` and build inside the bench container succeeds from a clean checkout, and `bench build --app lifeos` succeeds.
- Screenshot every screen at 1440 px and 390 px in light and dark, look at each, and fix anything broken: clipped text, misaligned controls, contrast below 4.5 to 1, horizontal scrolling.
- Add `frontend/COMPONENTS.md`: the three-layer rule, one table of every wrapper under `frontend/src/framework/` and what it wraps, and one table of every component of ours that remains, why neither library has an equivalent, and which primitives and tokens it uses. This is the rule book for future screens.

## Working rules

- Work in this order: step 0, tokens and theme, shell (sidebar, header, phone nav), form controls, buttons and badges, `ListView` with the library controls and remembered views, `RecordPane`, then screen by screen.
- Run the acceptance script after each step and commit once per step.
- Record deviations in `DECISIONS.md`, including each library component that was tried and not adopted, with the reason. Add a "UX fixes, set 2" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_2_DONE` and commit.
