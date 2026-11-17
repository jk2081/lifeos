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
| `LifeLink.vue` | `Link` | A picker for a Link field: area, project, person, goal, space |
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
| `ProjectCard.vue` | A project as a card | `Badge`, `Progress`, `NumLink` |
| `HabitBoxes.vue`, the 12 Week Year grid, habit month boxes, the year calendar | Purpose-built journal grids | `Button`-sized cells; `bg-surface-gray-9 text-ink-base` done, `bg-surface-gray-2` missed, `border-outline-gray-4` current, `text-ink-gray-4` future |
| `LineChart.vue`, the graph | Small SVG chart; Cytoscape canvas | token variables, `tokenColor()` |
| `SearchPalette.vue`, `QuickAdd.vue`, `Backlinks.vue` | App features | `CommandPalette` family, `Dialog`, `TextInput`, `Row` |

## How a list screen is written

A list screen is one `ListView` with a spec. `pages/Tasks.vue` and `pages/Vault.vue` are the reference.

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
| Tabs on a record or page | `tab=` | The area page (Overview, Projects, Tasks, Notes, Documents, Chats, Timeline), the project page (Overview, Tasks, Notes, Documents, Chats, Links), Settings (vertical, one section at a time), and on a phone only the review screen (Original, Transcript, Summary, Proposals) and the journal page (Page, Transcript). Journal and Calendar keep their path form (`/journal/habits`, `/calendar/year`) and answer `[` and `]` too |
| Tabs in the record pane | `ptab=`, so the pane and the page behind it do not collide. Changing it replaces the history entry; opening another record or closing the pane drops it (`lib/pane.js`) | Task (Details, Notes, Links), note (Note, Notes under this one, Links), wiki page (Page, Sources, Links, History), source (Original, Text, Summary, Made from this, Details), project (Overview, Tasks), goal (Actions, Tasks, History across cycles, Links; Tasks and Links for Annual and Open goals), chat (Summary, Open items, Links), journal page (Page, Transcript, Created from this page), vault document (Details, File), an inbox item on a phone. Day, entry and plain panes have none |
| State tabs on a list | the short parameter of the field the tabs are a preset on: `status=`, `type=`, `expiry=`, `open_items=`, `tab=` | Inbox, Tasks, Projects, Archive, Sources (by kind), Vault, Chats (inside area pages) |

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
- **Inside a page's tab** (the area and project pages) the state tabs are folded into the filter bar as one `Select` (`tabs-in-filter`), since there are no tabs inside tabs.
- The values in use: Goals `status=` in_progress (default), achieved, closed, all. Inbox `status=` To Review (default), Waiting, Failed (Done and all now open Sources). Sources `tab=` all (default), chats, voice, documents, photos, articles, email, text. The Wiki's page tabs are `tab=` pages (default), changes, health, rules. Tasks `status=` open (default), loops, Waiting, Done, all. Projects `status=` Active (default), On Hold, Done, Dropped, all. Archive `type=` all (default) and the six DocTypes. Chats `open_items=` all (default), 1. Vault `expiry=` all (default), soon, expired.

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

The list screens take `embed`: `{ screen: 'area', space, fixed: { area }, active: (route) => …, writable }`. `fixed` short parameters are set by the page and left out of the URL and the controls; `screen` keys the remembered view (`area-tasks`, shared across areas); `active` is a function of the route so the hidden lists ignore a URL that belongs to the open tab. The page's tab switch keeps only `tab=` and the open record. See `pages/Area.vue`.

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
