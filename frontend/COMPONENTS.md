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
| `Md.vue`, `MdEditor.vue` | Markdown with `[[links]]`, sanitised; a CodeMirror editor | `prose` classes of the preset, `.read` typeface, toolbar of `Button`s, token variables in the editor theme |
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
| Tabs on a record or page | `tab=` | (area page, project page and Settings, in later steps of set 3). Journal and Calendar keep their path form (`/journal/habits`) |
| Tabs in the record pane | `ptab=`, so the pane and the page behind it do not collide. Changing it replaces the history entry; opening another record or closing the pane drops it (`lib/pane.js`) | (the record pane, in a later step of set 3) |
| State tabs on a list | the short parameter of the field the tabs are a preset on: `status=`, `type=`, `expiry=`, `open_items=` | Inbox, Tasks, Projects, Archive, Chats, Vault |

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
- The values in use: Inbox `status=` To Review (default), Waiting, Failed, Done, all. Tasks `status=` open (default), loops, Waiting, Done, all. Projects `status=` Active (default), On Hold, Done, Dropped, all. Archive `type=` all (default) and the six DocTypes. Chats `open_items=` all (default), 1. Vault `expiry=` all (default), soon, expired.

## Checks

```
docker exec lifeos-bench bash -lc 'cd ~/frappe-bench/apps/lifeos/frontend && node scripts/check-sfc.mjs'      # compiles every file, icon names, removed patterns
docker exec lifeos-bench bash -lc 'cd ~/frappe-bench/apps/lifeos/frontend && node scripts/check-singletons.mjs' # one copy of vue, frappe-ui, reka-ui
cd frontend && node --test tests/*.test.js                                                                     # the URL mapping
node tools/screens.mjs                                                                                         # from the repo root: screenshots, overflow, script errors, contrast
```
