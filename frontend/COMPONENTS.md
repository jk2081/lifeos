# Front-end components: the rule book

Life OS builds its front end the way Frappe builds its own apps. Read this before adding or changing a screen.

## The three layers

Use the first layer that has what you need.

1. **frappe-ui** (pinned at 1.2.0) for basic controls, the shell, icons and tokens. Import from `frappe-ui`, and list parts from `frappe-ui/list`.
2. **`@framework/ui`** for anything that knows about a DocType: list controls, link fields, record fields, file upload. It is Frappe's own Vue package, compiled from `apps/frappe/ui` of the bench. **Only files under `src/framework/` import it.** Screens import those wrappers.
3. **Our own components** only where neither library has one. They are built from frappe-ui primitives and tokens, so they look the same.

Parts under `frappe-ui/experimental` can change in any release. **Only `src/experimental/index.js` imports them.**

Before using a library component, read its source and types: `node_modules/frappe-ui/src/components/<Name>/` (each has `types.ts` and a `.md` guide), `node_modules/frappe-ui/src/molecules/list/`, or `apps/frappe/ui/src/components/<Name>/`. Do not guess props.

## Rules

- **No hand-written control.** No raw `<button>`, `<input>`, `<select>`, `<textarea>`, checkbox, switch, date input, tab bar, badge, dialog, dropdown, tooltip, progress bar, avatar, tree or breadcrumb. The one exception is a `<button class="absolute inset-0">` that makes a whole row clickable (see Rows).
- **Tokens only.** Colours, type, radii, shadows and focus rings come from the frappe-ui preset's Tailwind classes. No hex colours, no `rgb()`, no colour variables of our own. Drawing code (the line chart, the graph) reads token variables such as `var(--ink-blue-7)`; a canvas library gets `tokenColor('--ink-blue-7')` from `lib/tokens.js`.
- **4.5 to 1 for all text.** `styles.css` points three library text colours at darker tokens (`text-ink-gray-5`, and the amber and blue subtle `Badge`). Do not use `text-ink-gray-5` or lighter for text of our own. `node tools/screens.mjs` measures every screen in both themes.
- **No `<style>` blocks with colours or sizes of our own.** Use Tailwind classes in the template. A scoped `<style>` is acceptable only for geometry that classes cannot say (a grid template built from data, an SVG).
- **Lucide icons** by name: `icon="lucide-plus"` on a component, or `<span class="lucide-plus size-4" aria-hidden="true" />`. `node scripts/check-sfc.mjs` checks that every name exists.
- **Dark mode** is frappe-ui's: `useColorScheme()` stamps `data-theme` on `<html>`. Never branch on the theme in a component; token classes switch by themselves.
- **No `prompt()` or `confirm()`.** Use `Dialog`, or frappe-ui's imperative `dialog.confirm({ title, message, onConfirm })`, `dialog.danger(...)` and `dialog.prompt({ title, fields, onConfirm })` (`import { dialog } from 'frappe-ui'`).
- **Phones.** The shell switches at `md` (768 px). Use `max-md:` and `md:` classes; the list controls collapse into a Filters button below `sm` (640 px).

### Token classes in use

| Purpose | Class |
| --- | --- |
| Page and card background | `bg-surface-base` |
| Tinted panel, hover | `bg-surface-gray-1` |
| Filled chip, pressed, the open row | `bg-surface-gray-2`, `bg-surface-gray-3` |
| Main text, headings | `text-ink-gray-8`, `text-ink-gray-9` |
| Secondary text | `text-ink-gray-6` (never lighter for text: `ink-gray-5` fails 4.5 to 1) |
| Links, numbers that are doors | `text-ink-blue-8` |
| Warnings and errors in text | `text-ink-amber-9`, `text-ink-red-8` |
| Borders | `border-outline-gray-1` (rows), `border-outline-gray-2` (cards, controls) |
| Type | `text-sm` (13 px, secondary), `text-base` (14 px), `text-base-medium`, `text-lg-semibold`, `text-xl`, `text-3xl-semibold` |
| Radius | `rounded-4` (8 px, controls), `rounded-5` (10 px, cards), `rounded-full` |
| Shadow | `shadow-lg`, `shadow-2xl` (overlays only) |
| Focus | automatic on focusable elements; `focus-visible:focus-ring` on our own |

### What replaced what

| Before | Now |
| --- | --- |
| `.bt.p`, `.bt.s`, `.bt.t`, `.bt.ic` | `Button` with `variant="solid"`, default (`subtle`), `variant="ghost"`, and `icon="lucide-…"` with a `label` for the accessible name |
| `.inp`, `<select>`, `<textarea>` | `FormControl` (`type="text"`, `"select"`, `"textarea"`, `"number"`), `TextInput`, `Select`, `Textarea`. `Select` takes `:options` as strings or `{ label, value }` |
| `<input type="date">` | `DatePicker` (`v-model` is `'YYYY-MM-DD'`, `clearable`) |
| `.ck` | `Checkbox` (`v-model` or `:model-value` with `@update:model-value`), `Switch` for a setting |
| `.pl.g/.b/.o/.r/.n` | `Badge` with `theme="green"`, `"blue"`, `"amber"`, `"red"`, `"gray"` |
| `.ch` as a view switch | `TabButtons` (`v-model`, `:options="[{ label, value }]"`) |
| `.ch` that only shows state | `Badge` |
| `.ch` that picks a value | `Pick.vue` (a `Dropdown` on a `Button`) or `LifeLink` |
| `.tb` page tabs | `TabBar.vue` (see Tabs below) |
| `PageHead`, `.hd`, `.crumb` | `PageHead.vue`: frappe-ui `PageHeader`, `PageHeaderTitle` and `Breadcrumbs` |
| `.bd` | `<div class="page-body">` |
| `.cd`, `.cd.list` | `Card`, `<Card flush>` |
| `.sh` | `SectionHead` (with `:count` and `:to` for a count that is a door) |
| `.rw`, `.rowlink` | `Row` (with `:pane="ref"` to open the record pane) |
| `.mt` | `text-sm text-ink-gray-6` |
| `.ttl` | `text-base-medium text-ink-gray-9` |
| `a.num` | `NumLink` |
| `.st` in `.stats` | `Stat` inside `<div class="stats">` |
| `.br` progress | `Progress` |
| `.empty` | `Empty.vue` inside a `Card`; `Alert` for a notice with an action |
| `Ico.vue` | Lucide names |
| `.only-phone`, `.only-desktop` | `md:hidden`, `max-md:hidden` |
| `.lbl` + control | the control's own `label` prop |
| Loading text | `Skeleton`, `LoadingIndicator` |

## Wrappers under `src/framework/` (the only importers of `@framework/ui`)

| Wrapper | Wraps | Used for |
| --- | --- | --- |
| `useLifeListView.js` | `useListView`, `useDoctypeMeta`, `parseFilters`, `getFilterableFields`, `parseOrderBy`, `serializeGroupBy` | One list's state: filters, sort, columns, quick-filter fields, group by. Adds virtual filter fields, the saved layout, and the grouped request for our list methods |
| `LifeFilter.vue` | `Filter` | The advanced filter popover |
| `LifeQuickFilter.vue` | `QuickFilter` | The always-visible strip of one-tap filters; same conditions as `LifeFilter` |
| `LifeSortBy.vue` | `SortBy` | Sort |
| `LifeGroupBy.vue`, `LifeGroupTable.vue` | `GroupBy`, `GroupByTable` | Group a list into one summary row per value |
| `LifeColumnSettings.vue` | `ColumnSettings` | Columns of the table view, with Reset |
| `columnResize.js` | `useColumnResize`, `directionFor`, `nextSort` from the experimental `List` | Drag-resize and header sort, written into the same columns |
| `LifeLink.vue` | `Link` | A picker for a Link field: area, person, goal, space |
| `LifeFormLayout.vue` | `FormLayout`, `buildLayoutFromMeta`, `useDoctypeMeta` | A form of plain DocType fields drawn from the DocType's meta, bound to our own values object and saved through `lifeos.api` (the vault document form) |

Wrapper for `frappe-ui/experimental`: `src/experimental/index.js` re-exports the `CommandPalette` family (the search palette).

## Our own components

| Component | Why neither library has it | Built from |
| --- | --- | --- |
| `ListView.vue` | The wrapper every list screen uses. It owns the view switch, the URL form of the filters (`lib/filterUrl.js`), the open row and the remembered state (`lib/views.js`). The libraries give the parts, not this composition | `frappe-ui/list` (`List`, `ListHeader`, `ListHeaderCellSort`, `ListGroup`, `ListRow`, `ListCell`), `TabButtons`, `Checkbox`, `Badge`, `Button`, `BottomSheet`, `Skeleton`, and the `Life*` wrappers |
| `RecordPane.vue`, `pane/PaneBody.vue` | A slide-over that keeps the list usable beside it. frappe-ui has `Dialog` (modal) and `BottomSheet` (phones) | Desktop: an `aside` with `bg-surface-base`, `border-outline-gray-2`, `shadow-2xl`. Phone: `BottomSheet`. Header: `Button`. Notice: `Alert` |
| `PageHead.vue` | A thin composition, so every screen has the same header | `PageHeader`, `PageHeaderTitle`, `Breadcrumbs`, `Badge` |
| `ui/Card.vue` | frappe-ui has no card | `rounded-5 border border-outline-gray-2 bg-surface-base` |
| `ui/SectionHead.vue`, `ui/NumLink.vue` | A section heading whose count links to the list it counts | `text-sm-medium text-ink-gray-7`, `text-ink-blue-8` |
| `ui/Row.vue`, `TaskRow.vue`, `IndexRow.vue` | Rows of mixed content inside a section card, opening the pane | The stretched-button pattern of frappe-ui's list guide, `Checkbox`, `Badge` |
| `ui/Stat.vue` | A number with a label | `Card`, `text-3xl-semibold` |
| `Empty.vue` | Empty states that say what belongs here | token text classes |
| `ScreenBoundary.vue`, `ScreenErrorMessage.vue` (bug fix 1) | The error boundary around the routed page: a screen that fails shows "This screen could not be shown." with Reload and a reference; the rest of the app keeps working (`lib/screenError.js`) | `Card`, `Button` |
| `Pick.vue` | One-tap change of a filing value | `Dropdown`, `Button` |
| `FileAttach.vue` | Attach one private file to a record, in one step | frappe-ui `FileUploader`, `Button`, `ErrorMessage` |
| `NewRecord.vue` | A small create dialog driven by a field list | `Dialog`, `FormControl`, `DatePicker`, `LifeLink` |
| `Md.vue` | Markdown with `[[links]]`, sanitised, for reading | `prose` classes of the preset, `.read` typeface |
| `LiveEditor.vue` (with `lib/editor/livePreview.js` and `lib/editor/commands.js`) | The Markdown editor: one pane, formatted as you type. frappe-ui's `TextEditor` is a rich-text (HTML) editor; notes are Markdown with `[[links]]` | CodeMirror 6 with decorations (see "The editor" below), toolbar of `Button`s, `FileUploader` for images, token variables in `styles.css` (`.lv-editor`) |
| `NoteEditor.vue` | A note or wiki page ready to write in: title, the filing as one line with a `Popover` of pickers, the editor, autosave with a quiet "Saved", and the conflict dialog | `TextInput`, `Popover`, `Pick`, `Dialog`, `DiffView` |
| `MdField.vue` | A Markdown field that saves by itself (transcripts) | `LiveEditor` |
| `DiffView.vue` | A readable line diff of two Markdown texts (wiki changes, conflicts). Uses the `diff` package (`diffLines`, BSD-3-Clause) | token classes `bg-surface-green-2`/`red-2` with `text-ink-green-9`/`red-9`, a `+`/`−` mark and screen-reader text, so colour is never the only cue |
| `ChangeView.vue` | One wiki change: who, when, why, the source, the diff, and Undo (with the "changed since" choice) | `Alert`, `Badge`, `Button`, `DiffView` |
| `DigestView.vue` | An email digest as headed lists, each item's Gmail link an "Open in Gmail" button | `Md`, `Button` |
| The Sources grid (in `pages/Sources.vue`, `ListView`'s `#body` slot) | Thumbnails of photos and scans as cards; the server's 480 px thumbnail, never the full image | `rounded-5 border-outline-gray-2` cards with the stretched-button pattern, `aspect-[4/3]` image, a Lucide icon when there is no thumbnail |
| `HabitBoxes.vue`, the 12 Week Year grid, habit month boxes, the year calendar | Purpose-built journal grids | `Button`-sized cells; `bg-surface-gray-9 text-ink-base` done, `bg-surface-gray-2` missed, `border-outline-gray-4` current, `text-ink-gray-4` future |
| `LineChart.vue`, the graph | Small SVG chart; Cytoscape canvas | token variables, `tokenColor()` |
| `SearchPalette.vue`, `QuickAdd.vue`, `Backlinks.vue` | App features | `CommandPalette` family, `Dialog`, `TextInput`, `Row` |
| `goals/DoneWhen.vue` (set 7) | "Done when…": a finish line or a number, Suggest, and the habit check, in every place a goal's measure is set | `TabButtons`, `FormControl`, `Button`, `Alert` |
| `goals/NewGoalDialog.vue` | New goal with its measure (Plan > Goals and the New menu) | `Dialog`, `FormControl`, `DatePicker`, `DoneWhen` |
| `goals/GoalsByArea.vue` (issue 20) | Goals > By area: sections of cards, not a list: the sections, parts, drag order and empty states are this screen's own | `Card`, `Progress`, `Badge`, `Button`, `TabButtons`, `Select`; the stretched-link pattern; native drag events for the order |
| `goals/GoalsAllTasks.vue` (issue 21) | Goals > All tasks: tasks grouped by area (then part), goal or due date, with a quick add in each group; the grouping, filters and rows are this screen's own | `Card`, `Badge`, `Button`, `Checkbox`, `TextInput`, `AreaGuess`; native task rows (not `ListView`) |
| `goals/GoalsNoGoal.vue` (issue 22) | Goals > No goal: goal-less tasks by area with Area, Fine as is, Add to goal, and Make it a goal per group; its own rows, not `ListView` | `Card`, `Alert`, `Button`, `Checkbox`, `Dropdown`, `AreaGuess` |
| `library/LibraryEverything.vue` (issue 23) | Library > Everything and People: one list of notes, documents, people and chats with a kind letter, a line, area and goal, date; search box and Area, Goal and Source filters in the address | `PageHead`, `Card`, `Empty`, `Badge`, `Button`, `TextInput`, native `select`; `openRef` for the pane |
| `goals/GoalMeasure.vue`, `goals/ResultBar.vue`, `goals/ReadingChart.vue`, `goals/SuggestedReadings.vue` | A goal's key result on its page and pane: the result bar, the chart of confirmed readings, readings to confirm, a reading by hand, Mark achieved | `Progress`, `Badge`, `Alert`, `FormControl`, `DatePicker`, `Row`; the chart is SVG with token variables |
| `outbox/InOutChart.vue`, `pages/Outbox.vue` | Library > Outbox: four piles, All out and Came in as state tabs, the period switch, the 8-week chart, Bring back | `ListView`, `TabButtons`, `Badge`, `Button`; SVG bars with token variables |
| `inbox/OldItems.vue` | The Inbox's banner of old items and its batch screen of suggested decisions | `Alert`, `Dialog`, `Checkbox`, `Select` |
| `settings/MemberRow.vue` (issue 1) | **The one row for a member of a space, person or agent**: avatar, name, email, a kind badge (Owner green, Person gray, Agent blue), access (Can view, Can edit; the owner always Can edit) and Remove. Settings > People and agents > Members lists only these; do not build another member row | `Avatar`, `Badge`, `Select`, `Dropdown`, `Button` |
| `settings/AreasSection.vue` (issue 12) | Settings > Your life > Areas: one card of the seven areas of life (the ones that are on first) with an On/Off `Switch` (left of the name; on the right on a phone), the goal count, "On by default" on Career and Health, the parts of each area that is on with Edit, "+ Add a part of <area>", the part dialog (name, description, colour, Archive) and the archive dialog that asks where open goals and tasks go. Read-only unless Life Admin | `Switch`, `Badge`, `Button`, `Dialog`, `TextInput`, `Select`, `ErrorMessage` |
| `settings/AddMemberDialog.vue` (issue 1) | Add member: a server search over every user (`settings.find_users`) with each one's kind, the access that fits (Can edit for a person, Can view for an agent), and the role offer for a user with no Life OS role | `Dialog`, `Combobox` (server search, as its guide says), `Badge`, `TabButtons`, `Select` |

## How a list screen is written

A list screen is one `ListView` with a spec. `pages/Tasks.vue` and `pages/Sources.vue` are the reference.

```vue
<ListView title="Vault" noun="documents" screen="vault" doctype="Life Vault Document" :spec="SPEC"
  :quick="['doc_type', 'holder', 'area']" :synthetic="[{ key: '_badge', label: '', width: '9rem', align: 'right' }]"
  :fetch="fetch" :row-ref="(r) => 'vault:' + r.name">
  <template #cell-title="{ row }">…</template>   <!-- a table cell, by field name -->
  <template #stack="{ row }">…</template>        <!-- the same row on a phone -->
</ListView>
```

- `screen` is the key the view is remembered under. `doctype` is whose fields the controls offer; a cross-type list uses `Life Index`.
- `spec` lists the short URL parameters (`status=`, `area=`, `due=`) and the field each stands for. `lib/filterUrl.js` maps them to filter conditions and back; conditions with no short form go in `f=`. Kinds: `value`, `link` (with `none`), `from`, `to`, `preset`, `flag`.
- `fetch({ params, filters, order_by, fields, summary, start, page_length, view })` calls the screen's `lifeos.api` method. `params` are the short parameters by name; pass `filters`, `order_by`, `fields` and `summary` straight through. Return `{ rows, total }`, or the method's answer when `summary` is set. **Lists never call `frappe.client.get_list`**: the `lifeos.api` methods apply the space rules and validate every field name.
- Views: `:views="[{ key, label, mode }]"` with mode `table` (columns from `ColumnSettings`, cells in `#cell-<field>`), `feed` (the `#row` slot) or `custom` (the `#body` slot, for a board or cards).
- Columns default to the DocType's `in_list_view` fields. A column the screen draws itself is a synthetic column whose key starts with `_`.

### Rows

A row that opens the pane is a static row with a stretched `<button class="absolute inset-0">` as its first child; `ListView` and `Row` do this for you. Anything inside the row that handles its own click (a link, a `Checkbox`, a `Button`) needs the class `relative` to sit above it.

### Count links

Every number that leads to a list is a `NumLink` (or `SectionHead` with `:to`) and **carries at least one query parameter**, so the list shows exactly that and not a remembered view. A link that means "everything" carries `all=1`.

### Remembered views

`ListView` saves, per user, screen and space: the list's query (filters, sort, view), customised columns, the quick-filter fields and the grouping. Opening a list with no query restores it into the URL; opening with a query uses exactly that query, then saves it. The open record (`open=`) is never saved. Nothing else needs doing in a screen.

## Tabs

Frappe organises information with tabs in three ways, and so does Life OS. All three are one component, `components/TabBar.vue` (frappe-ui `Tabs`, `TabList` and `TabTrigger`, with a count after each label), with its state from `lib/tabs.js`. `TabButtons` is only for small view switches (List, Board, Table).

| Pattern | Where the open tab lives | Used by |
| --- | --- | --- |
| Tabs on a record or page | `tab=` | The goal page (Overview, Tasks, Notes, Captures, Links), Settings (vertical, one section at a time), and on a phone only the review screen (Original, Transcript, Summary, Proposals) |
| A place's tabs | the path | Plan (`/plan/week` … `/plan/someday`) and Library (`/library`, `/library/notes` …). The place provides them and `PageHead` draws them under the header of whichever screen is open there (see "The four places" below) |
| Tabs in the record pane | `ptab=`, so the pane and the page behind it do not collide. Changing it replaces the history entry; opening another record or closing the pane drops it (`lib/pane.js`) | Task (Details, Notes, Links), note (Note, Notes under this one, Links), the assistant's note (Page, Sources, Links, History), source (Original, Text, Summary, Made from this, Details), goal (Actions, Tasks, History across cycles, Links; Tasks and Links for Annual and Open goals), chat (Summary, Open items, Links), journal page (Page, Transcript, Created from this page), vault document (Details, File), an inbox item on a phone. Day, entry and plain panes have none |
| State tabs on a list | the short parameter of the field the tabs are a preset on: `status=`, `type=`, `expiry=`, `open_items=`, `tab=` | Inbox, Tasks, Goals, Someday, Archive, Captures and All (by kind) |

**The URL rule.** The open tab is always in the URL, so reload, Back, Forward and a copied link return to it. The first tab is the default and adds nothing to the URL.

```vue
<TabBar :tabs="[{ value: 'overview', label: 'Overview' }, { value: 'tasks', label: 'Tasks', count: 12 }]" :model-value="tab.current.value" label="Area sections" @update:model-value="tab.set" />
```
```js
import { useUrlTab } from '@/lib/tabs'
const tab = useUrlTab('tab', TABS)             // page tabs; useUrlTab('ptab', TABS, { replace: true }) in the pane, with :level="2" on its TabBar
// tab.current: the open tab. tab.set(value): open one. tab.shown(value): true once the tab has been opened.
```

- **Counts.** A tab that holds a list shows its count as a quiet number after the label; pass `count` on the tab. Zero still shows. Counts come in one call with the screen.
- **Load a tab when it is first opened.** Render a tab's content with `v-if="tab.shown('tasks')"` and `v-show="tab.current.value === 'tasks'"`: it loads on first opening and stays loaded while the screen is open.
- **Phones.** `TabBar` is one row that scrolls sideways inside itself and brings the open tab into view; tabs are 44 px high below `md`. It never wraps and has no overflow menu. Pass `inset` when the bar sits outside `.page-body`.
- **Keys.** Arrow keys move between tabs (the component's own). `[` and `]` open the previous and next tab from anywhere on the page: `App.vue` calls `stepTab()` from `lib/tabs.js`, which goes to the pane's bar (`level` 2) while the pane is open and to the page's otherwise.
- **No tabs inside tabs**, except the pane's own tabs over a page that has tabs. **A tab never hides the only way to do something**: primary actions stay in the page header.

### State tabs on a list

A state tab is a preset on one field. Give `ListView` a `tabs` prop and return the counts from `fetch`:

```js
const TABS = { key: 'status', field: 'status', label: 'Task state',
  items: [{ value: 'open', label: 'Open' }, { value: 'loops', label: 'Open loops' }, { value: 'Waiting', label: 'Waiting' }, { value: 'Done', label: 'Done' }, { value: 'all', label: 'All' }] }
async function fetch({ params, tab, filters, ... }) {            // `tab` is the open tab's value
  const res = await api('tasks.list', { status: tab === 'open' ? 'open_doing' : ..., ... })
  return { rows: res.tasks, total: res.total, tabs: res.tabs }   // tabs: { open: 12, loops: 3, Waiting: 1, Done: 40, all: 60 }
}
```

- `key` is the short URL parameter and `field` the field it stands for. The first item is the default (no parameter; its own value in the URL also selects it). One item has the value `all`.
- The tab **replaces that field's control**: leave the field out of `quick`. It is still in the Filter popover. A URL value that is not a tab (`status=Dropped`), or a condition on the field made in the Filter, selects **All** and shows as a condition in the filter bar. A condition that equals a tab (`Status = Done`) selects that tab instead.
- A tab is not counted as a filter, Clear keeps it, and it is saved with the remembered view like the rest of the query.
- **Counts respect the other filters.** Each list method returns `tabs`, computed in one query (`lifeos.api.utils.tab_counts`) under every filter but the tab's own field. `ListView` exposes `tab` and `tabCounts`.
- **Inside a page's tab** (the goal page) the state tabs are folded into the filter bar as one `Select` (`tabs-in-filter`), since there are no tabs inside tabs.
- The values in use: Goals `status=` in_progress (default), achieved, closed, someday, all. Inbox `status=` To Review (default), Waiting, Failed (Done and all open Library > Captures). Captures `tab=` all (default), chats, voice, documents (with the sensitive documents of the Vault), photos, pages (journal pages), articles, email, text; All adds notes. Tasks `status=` open (default), loops, Waiting, Done, Someday, all. Someday `tab=` all, due, tasks, goals, ideas. Archive `type=` all (default), the DocTypes and trash.

## Checks

```
docker exec lifeos-bench bash -lc 'cd ~/frappe-bench/apps/lifeos/frontend && node scripts/check-sfc.mjs'      # compiles every file, icon names, removed patterns
docker exec lifeos-bench bash -lc 'cd ~/frappe-bench/apps/lifeos/frontend && node scripts/check-singletons.mjs' # one copy of vue, frappe-ui, reka-ui
cd frontend && node --test tests/*.test.js                                                                     # the URL mapping
node tools/screens.mjs                                                                                         # from the repo root: screenshots, overflow, script errors, contrast
```

### Pane tabs

A pane says its tabs in the meta it emits: `emit('meta', { title, …, tabs: [{ value, label, count, noun }] })`. `PaneBody` draws the bar (level 2) under the header and passes the open one as the `tab` prop; draw each part with `v-if="on('notes')"` where `on = (t) => !props.tab || props.tab === t`. Leave out a tab that can never be filled for this record; keep one that is empty but can be filled, with an empty state. One tab left means no bar. A count that opens a pane on a tab writes `ptab=` beside `open=`.

### A list inside a page's tab

The list screens take `embed`: `{ screen: 'goal', space, fixed: { goal }, active: (route) => …, writable }`. `fixed` short parameters are set by the page and left out of the URL and the controls; `screen` keys the remembered view (`goal-tasks`, shared across goals); `active` is a function of the route so the hidden lists ignore a URL that belongs to the open tab. The page's tab switch keeps only `tab=` and the open record. A list with `fixed` ignores the lens: it lists what is filed under the record. See `pages/Goal.vue`.

## The editor

`components/LiveEditor.vue` is the only Markdown editor (notes, wiki pages, journal transcripts, task notes, inbox transcripts). `/life/dev/editor` (owner only, not in the sidebar) shows it on a sample note with every element.

- **One pane, no modes.** CodeMirror 6 with `@codemirror/lang-markdown` (GFM). `lib/editor/livePreview.js` is one `StateField` of decorations, rebuilt when the text, the selection, the focus or the parse changes: headings at size, bold, italic, strike, inline code, bullets as dots, checklists as boxes you click, links as links, `[[links]]` as chips, images inline, rules, quotes, code blocks, and tables as tables (a block widget). The Markdown marks of a line show only while the cursor is on that line; a table shows as text while the cursor is inside it. A `StateField` and not a view plugin, because block widgets (the table) must come from state.
- **Following links.** A `[[link]]` chip opens its record in the pane on click. A web link opens with Cmd or Ctrl held, or on a click while the editor does not have focus.
- **Sanitising.** Nothing typed can run script: chips, images and links are DOM built with `textContent` and checked URLs (`safeUrl`: http, https, mailto, a path, a fragment); the table widget is markdown-it with raw HTML off, then DOMPurify, as `Md.vue`.
- **Typeface and column.** The reading typeface of `.read` (17 px serif, headings in the interface font), in a column of at most 720 px, centred. "Show Markdown" (the `raw` prop, in the page's ⋯ menu) switches to the plain text in a monospace face.
- **Toolbar** above the text (bold, italic, heading, lists, checklist, link, `[[`, image). On a phone, while the editor has focus, it is fixed above the keyboard (`visualViewport`).
- **Keys.** ⌘B, ⌘I, ⌘K (link), ⌘⇧7 and ⌘⇧8 (lists), Tab and Shift-Tab indent. `/` at the start of a line opens a menu of blocks; `[[` the record picker (`links.suggest`).
- **Images** pasted, dropped or chosen with the toolbar upload as private files attached to the record (`doctype`, `docname` props) and are inserted as `![name](/private/files/…)`.
- **Saving** is the caller's: `NoteEditor` and `MdField` save a moment after typing stops and on blur, with a quiet "Saved". `NoteEditor` sends the `version` it started from; a conflict opens "This page changed while you were editing" with View changes, Keep mine and Reload.

## UX fixes, set 5: counts, Today, Ask, Reset

### Count doors

Every number on Today, Reset, Someday, the sidebar and the weekly review's Reset step comes from the count helper (`lifeos/counts.py`): `{ n, to: { path, query }, label }`, where `n` is worked out by calling the same list method, with the same arguments, that the screen at `to` calls. Show it with `components/ui/CountLink.vue` (`:count`, optional `count-key` and `tone`), never by formatting a number and building a link by hand. It carries `data-count-door`, `data-count-n` and `data-count-label`, which the acceptance check U.31 clicks and compares with the rows shown. A count with no condition of its own carries `all=1`, so a remembered view cannot change what the list shows. Ask's `counts` tool returns the same objects.

### The Search or ask box

`components/ask/AskBox.vue` sits in every page header (through `PageHead`): on desktop one outline button, "Search or ask anything" with ⌘K, that opens the search palette; on a phone a search icon and a solid Ask button. In the palette, Enter on text that reads as a question (`lib/ask.js` `isQuestion`: ends with "?", starts with a question word, or is more than six words) or the "Ask" row asks. The sidebar has no Search item.

### The Ask panel

`components/ask/AskPanel.vue`, mounted once in `App.vue` and driven by the `ask` store in `lib/ask.js` (`startAsk(question, scope)`, `askAbout(doctype, name, title)`). Desktop: a 480 px panel from the right over the screen; phone: frappe-ui `BottomSheet` at 82 dvh. The screen underneath is not navigated; closing leaves it as it was. The scope is taken from the route (`scopeFromRoute`, the table of the brief) and shown as a removable chip (`data-ask-scope`); every record pane has "Ask about this" (`data-pane-ask`) in its header. `AskThread.vue` renders a thread: the answer as Markdown with numbered citation chips (`data-ask-cite`, opening the record in the pane), the sources list, and suggested actions (`data-ask-action`), which call the normal API only when clicked and toast an Undo where the action has one. `AskComposer.vue` is the text box with Send. Answers stream: the screen polls `ask.progress` with its own id while the answer is written (the server also publishes each piece as a `lifeos_ask` realtime event to the asking user; see `DECISIONS.md`). "Expand" opens the thread on the Ask page (`/ask?thread=`).

### The Open band and the Next list (Today)

Both live in `pages/Today.vue` and read `today.get`. The band (`data-open-band`) is one row of `Stat`-like tiles at 1440 px; on a phone the four most important tiles are a 2-column grid and the rest scroll sideways. Every big number and every line under it is a `CountLink`. When the stuck count is over the limit the heading turns amber (`data-over-limit`) and the Reset button becomes solid. The Next list (`data-next`) is one list in the fixed order written at its top: Overdue, Today, 12 Week Year this week, Needs a decision (`data-next-group`); each row has a label for why it is there (`data-why`); about 8 rows show, then "N more". A 12 Week Year row ticks through `journal.tick`. The rail (`data-rail`) moves below Next on a phone.

### Reset decisions

`pages/Reset.vue` with `components/reset/BatchCard.vue`, `Inventory.vue` and `OneByOne.vue`. On a phone, Batches, One by one and Inventory are `TabBar` tabs (`tab=`); on desktop they are one page. A batch action asks for confirmation (`dialog.confirm`) with the exact count, applies to exactly the listed names, and toasts Undo for one minute. One by one shows the oldest untouched item with Do (D, asks for a date), Waiting (W, asks for whom), Someday (S), Archive (A) and Delete (X): keys on desktop (ignored while typing in a field), large buttons on a phone (`data-obo`). Delete moves the record to the trash (Frappe's Deleted Document), restorable from the Archive's Trash tab for 30 days.

## UX fixes, set 6: the lens, the four places, Plan and Library

### The lens

`lib/lens.js` holds the space and area every place narrows to. It is `space=` and `area=` on every URL: a router guard adds them to any navigation that has none, and a URL that names them (a copied link, Back) sets the lens. It is remembered per user in the view state `lens` (no space). Change it only with `setLens({ space, area })` or `clearArea()`, which empty the state first so the guard does not put the old area back.

- **The picker** is frappe-ui's `SidebarHeader` with the menu from `components/lens/lensMenu.js` (spaces, All of life, every active area with sub-areas indented and a colour dot, "Pin areas to the sidebar", "Manage areas"). On a phone the lens is the title bar at the top of every screen (`App.vue`, `data-lens-bar`), and tapping it opens `components/lens/LensSheet.vue`, which also holds Settings, the shortcuts and Log out.
- **The header** (`PageHead`) shows the lens as its breadcrumb and, while an area is chosen, a removable chip beside the title (`data-lens-chip`).
- **Lists** need nothing: `ListView` treats `area=` as the lens. A list whose spec has an `area` entry passes the lens's area to its list method, and the area leaves its controls, its remembered view and its Clear. A list with `fixed` ignores the lens.
- **Other screens** pass `store.lensArea` to their method (`today.get`, `calendar.get`, `journal.grid`, `journal.month`, `library.tree`, `graph.get`, `search.query`). The page component is keyed on the lens, so a new lens mounts the screen again; no screen watches it.
- **Area colours** are frappe-ui surface tokens, chosen with `dotClass(area)`; never write a colour class from data.

### The four places

The sidebar (`components/AppSidebar.vue`) is the lens, + New, Today, Inbox, Plan (open to its tabs), Library, "Focus on an area" with the pinned areas, then Settings and the user with Help. The phone's bar is Today, Inbox, Plan, Library and Ask. `lib/nav.js` lists the places, Plan's and Library's tabs and the G shortcuts (`GO`).

A place's tabs are paths (`/plan/goals`, `/library/notes`). The place page (`pages/Plan.vue`, `pages/LibraryPlace.vue`) provides `placeTabs` (`{ tabs, current, label, set }`) and renders the screen of the open tab; that screen's `PageHead` draws the tabs under its header (`data-place-tabs`), so each screen keeps its own title, count and actions. Plan's tabs carry `group` (time, lists): `TabBar` puts a gap between groups.

### Plan

- **Rhythm tabs** (Week, Month, 12 Weeks, Year) are `components/plan/PlanRhythm.vue`: a view switch (`view=`, `TabButtons`) between the journal's screens (`components/journal/*`, which teleport their buttons into `#jr-actions` in the header) and the calendar (`components/plan/Calendar.vue`, with `place` and `switch-options`). Week: Review, Calendar, Agenda, with `WeekScore` above the calendar and the Reset button. Month: Plan, Habits, Check-ins, Calendar. 12 Weeks: the cycle grid. Year: Calendar, Goals across cycles.
- **List tabs** are the Goals, Tasks and Someday screens as before.
- **A goal's page** is `/plan/goals/<id>` (`pages/Goal.vue`): what a project page and a goal page each had, with "Serves" and "Served by". Reset is `/plan/reset`.

### Library

- **All** and **Captures** are `pages/Sources.vue` (`place`), over `sources.list` (`scope`, `sensitive`, `by`). Kinds are state tabs; Photos and All keep the grid. Vault documents show as Documents with their holder, number and expiry; "Add document" is on the Documents tab.
- **Notes** is the notes list with "Written by" (`by=me|assistant`), the "Kept by the assistant" badge and the rules pinned above the assistant's notes; its views (`view=`) are List, Tree, Graph, Changes and Health (`NOTES_VIEWS`).
- **Timeline** and **Archive** (with Trash) are as before.
- **Sensitive items** carry `lucide-lock` (`data-sensitive-lock`). The pane header's lock button marks and unmarks (`meta.sensitive`), through `library.set_sensitive`.

### Today's rhythm banner

At most one line above the Open band (`data-rhythm-banner`), from `today.get`'s `banner`, with its action and Skip (`today.skip_banner`).

## Set 7: Moving forward

### Key results

- **One editor for a goal's measure**: `goals/DoneWhen.vue`, bound to a reactive object from `lib/goals.js` (`emptyMeasure`, `measureProblem`, `measureArgs`). New goal, the 12 Weeks Add goal, the goal page and pane ("Change how it is measured") and the weekly review's "Needs a finish line" all use it, so the rule and its messages are the same everywhere. A title or finish line that reads as a frequency shows "This looks like a habit" (`data-habit-hint`) with Make it a habit (`goals.make_habit`).
- **A number goal's result** is `goals/ResultBar.vue` from the `progress` object every goal method returns (`readings.summary`: kind, percent, label, start, current, target, unit, current_on). No reading yet is `current_on` empty: Frappe stores floats as never null.
- **Readings waiting** are `goals/SuggestedReadings.vue` (Confirm, Edit and confirm, Reject; `data-reading`), on the goal and in the weekly review.

### The Outbox

- `pages/Outbox.vue` is a `ListView` over `outbox.list` with state tabs on `pile=` (Done, Delegated, Parked, Discarded, all, in) and the period on `period=` (week, month, 12weeks) as `TabButtons` in the bar. Its rows open the record's pane while the record exists; Bring back (`data-outbox-bring-back`) is the only action.
- Today's line under the Open band (`data-inout`) is two `CountLink`s from `counts.outbox`, opening the Outbox on `pile=in` and `pile=all`.

### The weekly review

Replaced in set 8 by `components/weekly/` (see "Set 8: the weekly review" below). The goal cards and key-results step of set 7 are gone; readings to confirm are Goal reading revelations in Library and links on the goal rows in Goals.

### Scheduled tasks

A task with `scheduled_at` shows at its time in Today's Next (why "Scheduled") and on the rail's timeline (`data-rail-task`), and on the calendar as a timed item for `duration_min`.

### Inbox items left too long

The Inbox's `#above` slot starts with `inbox/OldItems.vue`: an amber `Alert` (`data-old-items-banner`) and a `Dialog` batch (`data-old-item`, Confirm selected with an Undo toast). `?decisions=1` opens the batch; Reset's batch with action `review_inbox_decisions` routes there. What the rule parked or discarded on its own is one line on Today (`data-auto-inbox`) with Undo for seven days; it is separate from the rhythm banner, which stays one line.

- **Buttons in a header from inside a screen** go through `<Teleport defer to="#jr-actions">`, never a plain `Teleport`: frappe-ui's `PageHeader` is itself a deferred teleport, so the target exists only after the render that mounts it (bug fix 1).

## Set 8: the weekly review

### The layout rule (every review, and every future screen of this kind)

- **Nothing important below the fold.** At 1440 × 900 a review tab shows its whole state without scrolling the page. A list longer than fits is either a pile or folds into one line with a count ("4 other goals in progress · Plan any").
- **Drawers for detail.** A 520 px drawer from the right over a dimmed page: `components/ui/Drawer.vue`. Header and footer stay put; only the list inside scrolls. Esc and the close button close it. On a phone it is a full-screen sheet. Neither library has a side sheet (frappe-ui's `Dialog` is centred, `@framework/ui` has none), so the drawer is built on reka-ui's Dialog parts exactly as frappe-ui builds its own `BottomSheet`: focus is trapped and given back, it is announced as a dialog, Esc closes it.
- **The assistant decides first.** Each item carries the assistant's suggestion and a one-line reason. Only items it cannot decide are shown one by one, under **Needs you** (at most 5; any beyond 5 go into Keep with the reason "not sure").
- **One primary button in a footer** (`weekly/ReviewFooter.vue`), with one line saying what is left before it opens. The footer is sticky at the bottom of the screen (above the tab bar on a phone).

### The review's components (`components/weekly/`)

| Component | What it is | Built from |
| --- | --- | --- |
| `ReviewPage.vue` | The review at `/plan/week?view=review&tab=…`: loads the header (`weekly.get`, then `weekly.start`, which resumes or starts it; a site that refuses writes keeps the unsaved review), opens the first unfinished tab, refuses a tab ahead whose tabs before it are not done (Library never blocks), Pause | `Skeleton`, `toast` |
| `ReviewHeader.vue` | Title, period ("Week of 16 to 22 November", or "Covers … (you skipped last week)"), numbered tabs ticked when done (a step bar "Step 2 of 4 · Tasks" on a phone), "About 35 minutes · saved as you go", Pause | `PageHeader`, `Tabs`, `TabList`, `TabTrigger` (`#prefix` for the number or tick), `Button` |
| `ReviewFooter.vue` | Back, the line of what is left, the one primary button | `Button` |
| `piles/PileBoard.vue` | Needs you and the three piles for one key (`inbox` in Library, `tasks` in Tasks); owns the pile drawer | `NeedsYou`, `PileCard`, `PileDrawer` |
| `piles/NeedsYou.vue` | Rows the assistant could not decide, with three choices worded for the source (Accept, Park, Discard; This week, Someday, Drop; Chase, Got it, Keep waiting); a settled row is one line with Undo; the section folds away when all are settled | `Card`, `Button` |
| `piles/PileCard.vue` | A pile: count, what happens to its items, the first three with a source tag, "+ N more · see all and change", Open pile; done: tint, tick, "17 parked in Someday", what moved, See them and Undo | `Card`, `Badge`, `Button` |
| `piles/PileDrawer.vue` | A pile opened: what happens, source filters with counts, each row with source, area, age and reason, Keep, Park and Let go settling it at once ("Moved to Keep · Undo"), and the footer that applies the pile's decision to the rest ("Park all 17") | `Drawer`, `TabButtons`, `Badge`, `Button` |

`lib/review.js` holds the review's shared state (`provideReview`, `useReview`): `head` (period, tabs done and openable, the first unfinished tab), `act(method, args)` (a POST to `lifeos.api.weekly`, which saves at once and returns the new header) and `read(method, args)` (a GET). Every tab reloads what it shows when `version` changes.

### The tabs

| Component | What it is | Built from |
| --- | --- | --- |
| `TabLibrary.vue` with `library/CalendarStrip.vue`, `library/MeetingDrawer.vue`, `library/FindingRow.vue` | Tab 1 (boards 28, 29): the period's days with meetings that matter marked (a list by day on a phone; one line to Settings when no calendar), Came in with each count a `CountLink` (meetings open a list in a drawer), the Inbox piles' split and Review the piles, the Revelations ("N left"; "Nothing left to look at"; the line when the assistant is not set up). A meeting opened: linked records (Open, Unlink, Link a record), follow-ups found, a line that becomes a task on Enter under the goal shown, the "matters" switch, ← → and Done with this meeting | `Card`, `Button` (`variant="outline"` for a meeting that matters), `CountLink`, `Badge`, `TextInput`, `Select`, `Switch`, `Dropdown`, `Drawer` |
| `TabTasks.vue` | Tab 2 (board 30): "N left to clear" with a bar, Left your plate (the four Outbox piles for the review's period, each a `CountLink` to Library > Outbox with `from=` and `to=`; in and out; Open the Outbox), then `PileBoard` for stuck and waiting tasks | `Progress`, `Card`, `CountLink`, `PileBoard` |
| `TabGoals.vue` with `goals/GoalDrawer.vue`, `goals/WeekGlance.vue` | Tab 3 (boards 31, 32): the week's score against the target, goal work planned against free hours (amber when over), one row per cycle goal (star, mark, progress, next action, when and length, who; "needs a finish line" and "N readings to confirm" open the drawer), "N other goals in progress · Plan any" in one line, and next week at a glance (a "Next week" sheet on a phone). The drawer: the finish line (`DoneWhen`) when missing, readings to confirm (`SuggestedReadings`), next action with "other open tasks (N)", when and length, free slots as chips, who, what is needed, the top-three star, Skip this goal this week (a reason is required) and Save | `Card`, `Badge`, `Progress`, `Button`, `FormControl`, `DateTimePicker`, `Checkbox`, `Alert`, `Drawer`; the glance places blocks by time with `:style` (geometry only) |
| `TabReflect.vue`, `ReviewDone.vue` | Tab 4 (board 33): what went well (required) and what to do differently, saved as typed; the week in numbers; last week's line played back; what Lock will do. The done screen: "Week planned in N minutes", what was decided, the top three, Go to Today, See the week, the next review | `FormControl`, `Card`, `Button` |

Each tab ends with `ReviewFooter`. A tab's footer line says what is left before its button opens (the server's `ready.left` on Goals).

### Today's top three

After Lock, the week's three starred goal tasks (`is_top_three`) are the first group of Today's Next (`data-next-group="top"`), each with a star (`data-top-three`), until the next review is locked.

### Outbox periods

Library > Outbox also takes a review's period as `from=` and `to=` (shown as a fourth choice, "Review period"), so the review's counts open lists with exactly those rows.

