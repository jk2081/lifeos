# UX fixes, set 2: move the front end onto frappe-ui

The front end uses frappe-ui 1.2.0 only for `Dialog`, `Dropdown` and `toast`. Buttons, inputs, selects, pills, tabs, the shell and the colour tokens are hand-written in `frontend/src/styles.css`. This set replaces them with frappe-ui components and tokens, so the app looks and behaves like Frappe's own apps and follows their design decisions.

Read `CLAUDE.md`, `STATUS.md` and `DECISIONS.md` first. Before using a component, read its source and types in `frontend/node_modules/frappe-ui/src/components/<Name>/`. Do not guess props.

## Rules

1. **A frappe-ui component wherever one exists.** No hand-written button, input, select, checkbox, switch, textarea, date picker, tab bar, badge, dialog, dropdown, tooltip, progress bar, avatar, tree, breadcrumb, file upload or loading state.
2. **frappe-ui tokens only.** Remove the Life OS colour variables (`--bg`, `--ink`, `--line`, `--accent` and the rest). Use the semantic Tailwind classes from the frappe-ui preset (`bg-surface-*`, `text-ink-gray-*`, `border-outline-gray-*` and their coloured variants). No hex colours in components or CSS, except inside the graph and chart drawing code, which read token values from CSS variables.
3. **frappe-ui scale.** Use its type sizes, spacing, radii, control heights, focus rings and shadows through the preset's Tailwind classes. Remove the custom `.bt`, `.inp`, `.ch`, `.pl`, `.cd`, `.ck`, `.sh`, `.mt` classes as each is replaced.
4. **Lucide icons** through frappe-ui's icon plugin. Remove `Ico.vue` and the hand-written SVG paths.
5. **Dark mode** through frappe-ui's colour scheme support only. Remove the `[data-theme]` variable block.
6. **No browser `prompt()` or `confirm()`.** Use frappe-ui dialogs.
7. **Our own components follow the same decisions.** Where frappe-ui has no component, build ours from its primitives and tokens, with the same sizes, radii, focus and hover treatment, so they are indistinguishable in style.

## Replace with frappe-ui

These components exist in frappe-ui 1.2.0 and must be used.

| Now | Use |
| --- | --- |
| `.bt` buttons (about 124 uses) | `Button` with its variants and sizes |
| `.inp` inputs, raw `<select>`, `<textarea>` (about 110 uses) | `FormControl`, `TextInput`, `Select`, `Combobox`, `MultiSelect`, `Textarea` |
| `.ck` checkboxes and toggles | `Checkbox`, `Switch` |
| Date inputs | `DatePicker` |
| `.pl` pills and `.ch` chips that only show state | `Badge` |
| `.ch` chips used as view or filter switches | `TabButtons` |
| Page tabs (Journal, Calendar) | `Tabs` |
| `PageHead.vue`, `.hd`, `.crumb` | `PageHeader`, `Breadcrumbs` |
| Sidebar and space switcher | `Sidebar` (and `DesktopShell` if it fits) |
| Phone tab bar | `MobileNav` (and `MobileShell` if it fits) |
| Phone sheet in `RecordPane` | `BottomSheet` |
| Progress bars | `Progress` |
| Library tree | `Tree` |
| Inbox drop zone and file inputs | `FileUploader` |
| Loading states | `Skeleton`, `LoadingIndicator`, `Spinner` |
| Hints on icon buttons | `Tooltip` |
| Keyboard hints, shortcut help | `KeyboardShortcut`, `KeyboardShortcutsDialog` |
| Person and agent markers ("filed by Hermes") | `Avatar` |
| Empty states and inline notices | `Alert` where it fits, otherwise `Empty.vue` restyled with tokens |
| `prompt()` and `confirm()` in Settings and elsewhere | `Dialog` |
| Search palette popover, pickers | `Popover`, `Combobox`, `Menu` |
| Settings screen | `SettingsDialog` if its layout fits, otherwise the page built from the form components above |

## Keep as ours, rebuilt on frappe-ui primitives and tokens

| Component | How |
| --- | --- |
| `ListView` | Rows from `ItemListRow` and the preset's list column utilities. Filter bar from `Select`, `Combobox`, `DatePicker`, `TabButtons`. Phone Filters button opens a `BottomSheet` |
| `RecordPane` | Desktop slide-over stays ours, styled with tokens and frappe-ui's dialog shadow and radius. Phone uses `BottomSheet`. Header buttons are `Button` |
| 12 Week Year grid, habit boxes, year calendar | Ours. Cells are `Button`-sized and use token colours for done, missed, current and future |
| Line chart, graph | Ours. Colours read from the token CSS variables so both themes work |
| Markdown reader and editor | Ours. Toolbar buttons are `Button`. Editor theme uses token variables |
| Review layout, month plan layout, check-in form | Ours for layout. Every control inside is frappe-ui |

## One behaviour change in this set: lists remember their filters

Today a list's filters survive a reload but are lost when the owner goes to another screen and comes back. Fix this in `ListView`, so every list gets it.

- `ListView` saves its current filters, sort and view (list, board, table, cards) each time they change, keyed by screen and space, in `localStorage`.
- Opening a list **with no query in the URL** (the sidebar, the phone tab bar, a `g` shortcut, the browser's Back to a bare route) restores the saved state and writes it into the URL.
- Opening a list **with a query in the URL** (a count link, a link from another record, a bookmark) uses exactly that query and ignores the saved state. It then becomes the saved state. Every count link must carry at least one query parameter so this rule holds; a link that means "everything" carries `all=1`.
- The open record (`open=`) is never saved or restored. Coming back to a list shows the list, not a pane.
- Because a remembered filter can hide records, the filter bar always shows when filters are active: the count of active filters and a Clear button, on desktop and on the phone's Filters button. Clear removes the filters and the saved state.
- Switching space uses that space's own saved state.
- Checks to add to `tools/acceptance.mjs`, at both widths: set a filter on Tasks, go to Today through the sidebar, come back through the sidebar, and the filter is still set and is in the URL. Click the Open loops number on Today and Tasks shows only open loops, whatever was saved. Clear removes it, and it stays cleared after leaving and returning.

## What must not change

- Behaviour, apart from the remembered filters above. Every screen, route, filter, pane, shortcut and count link works as it does now.
- Information on each screen. This set changes components and styling, not content or layout structure.
- The API and the data model.

The approved mockups remain the reference for layout and density. Where a frappe-ui token differs from a mockup colour, the token wins.

## Checks

- `node tools/acceptance.mjs` passes all items at 1440 px and 390 px, as before.
- `grep` finds none of these in `frontend/src`: `class="bt`, `class="inp`, `class="ck`, `window.prompt`, `window.confirm`, `<select`, a `#` hex colour outside the chart and graph files, `Ico.vue`.
- `frontend/src/styles.css` holds only the frappe-ui import, layout helpers, and the reading typeface. Aim for under 80 lines.
- Screenshot every screen at 1440 px and 390 px in light and dark, look at each, and fix anything broken: clipped text, misaligned controls, contrast below 4.5 to 1, horizontal scrolling.
- Add `frontend/COMPONENTS.md`: one table listing every component of ours that remains, why frappe-ui has no equivalent, and which frappe-ui primitives and tokens it uses. This is the rule book for future screens.

## Working rules

- Work in this order: tokens and theme, shell (sidebar, header, phone nav), form controls, buttons and badges, `ListView` and `RecordPane`, then screen by screen.
- Run the acceptance script after each step and commit once per step.
- All unit tests must still pass. Record deviations in `DECISIONS.md`. Add a "UX fixes, set 2" section to `STATUS.md` when finished, then create an empty file named `UX_FIXES_2_DONE` and commit.
