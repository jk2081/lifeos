<template>
  <PageHead v-if="title" :title="title" :crumb="crumb" :count="loaded && !grouped ? total : null">
    <template #sub><slot name="sub">{{ sub }}</slot></template>
    <TabButtons v-if="views.length" class="max-md:hidden" :model-value="view" :options="viewOptions" data-views @update:model-value="setView" />
    <slot name="actions" />
  </PageHead>
  <div class="page-body" data-list :data-screen="screen" :data-view="view">
    <slot name="above" />
    <TabButtons v-if="views.length" class="md:hidden" :model-value="view" :options="viewOptions" @update:model-value="setView" />

    <!-- State tabs: one field's presets, above the filter bar. They take the place of that field's quick filter. -->
    <TabBar v-if="tabs && !tabsInFilter" class="-mb-3" :tabs="tabItems" :model-value="tab" :label="tabs.label || 'State'" data-state-tabs @update:model-value="setTab" />

    <!-- The controls. Wide screens: a strip of quick filters with Filter, Sort, Group and Columns beside it.
         Below 640 px: one Filters button with the count of active filters, opening the same controls in a sheet. -->
    <div class="flex flex-wrap items-center gap-2" data-lv-bar>
      <slot name="bar" />
      <!-- inside a record page's tab the state tabs are folded into the filter bar as one control: no tabs inside tabs -->
      <Select v-if="tabs && tabsInFilter" class="w-48" :model-value="tab" :options="tabOptions" :aria-label="tabs.label || 'State'" data-state-select @update:model-value="setTab" />
      <Badge v-if="!title && loaded && !grouped" size="lg" :label="total" data-lv-count />
      <template v-if="!phone">
        <div class="min-w-40 flex-1" data-quick-filters><LifeQuickFilter :list="list" /></div>
        <template v-if="!list.view.quickFilter.customizing.value">
          <Checkbox v-for="f in shownFlags" :key="f.key" :label="f.label" :model-value="!!flagValues[f.key]" :data-flag="f.key" @update:model-value="(v) => setFlag(f.key, v)" />
          <LifeFilter :list="list" align="end" />
          <LifeSortBy :list="list" />
          <LifeGroupBy v-if="groupable" :list="list" />
          <LifeColumnSettings v-if="mode === 'table'" :list="list" />
          <Button v-if="list.view.quickFilter.canCustomize.value" icon="lucide-sliders-horizontal" label="Choose the quick filters" tooltip="Choose the quick filters"
            @click="list.view.quickFilter.customizing.value = true" />
        </template>
      </template>
      <Button v-else icon-left="lucide-list-filter" :label="activeN ? `Filters (${activeN})` : 'Filters'" :variant="activeN ? 'outline' : 'subtle'" data-filters-button @click="sheet = true" />
      <template v-if="activeN">
        <Badge v-if="!phone" theme="blue" size="lg" :label="`${activeN} filter${activeN === 1 ? '' : 's'} on`" data-active-filters />
        <Button variant="ghost" label="Clear" icon-left="lucide-x" data-clear @click="clearFilters" />
      </template>
    </div>
    <BottomSheet v-if="phone" v-model:open="sheet" title="Filters">
      <div class="flex flex-col gap-4 px-4 pb-6" data-filter-sheet>
        <LifeQuickFilter :list="list" />
        <Checkbox v-for="f in shownFlags" :key="f.key" :label="f.label" :model-value="!!flagValues[f.key]" :data-flag="f.key" @update:model-value="(v) => setFlag(f.key, v)" />
        <div class="flex flex-wrap gap-2">
          <LifeFilter :list="list" align="start" />
          <LifeSortBy :list="list" />
          <LifeGroupBy v-if="groupable" :list="list" />
        </div>
        <div class="flex gap-2">
          <Button v-if="activeN" class="flex-1" size="md" label="Clear filters" data-clear @click="clearFilters" />
          <Button class="flex-1" size="md" variant="solid" :label="loaded ? `Show ${total} ${noun}` : 'Show'" @click="sheet = false" />
        </div>
      </div>
    </BottomSheet>

    <Card v-if="grouped" flush class="!px-1" data-lv-groups>
      <LifeGroupTable :list="list" :rows="groupRows" :totals="groupTotals" :loading="loading" />
    </Card>
    <slot v-else-if="mode === 'custom'" name="body" :rows="rows" :loaded="loaded" :reload="refresh" />
    <Card v-else-if="rows.length" flush class="!px-1" data-lv-rows>
      <List :columns="tracks" class="list-row-px-3">
        <ListHeader v-if="mode === 'table'" class="group max-md:!hidden">
          <div v-for="c in columns" :key="c.fieldname" class="relative flex min-w-0" :class="c.align === 'right' ? 'justify-end' : ''">
            <ListHeaderCellSort v-if="c.sortable" class="min-w-0" :direction="directionFor(sorts, c.fieldname)" :align="c.align === 'right' ? 'end' : 'start'"
              :data-sort="c.fieldname" @click="list.view.sort.by.value = nextSort(sorts, c.fieldname)">{{ c.label }}</ListHeaderCellSort>
            <ListHeaderCell v-else class="min-w-0">{{ c.label }}</ListHeaderCell>
            <!-- the drag handle of @framework/ui's own list: drag to resize, double-click to go back to automatic -->
            <span class="absolute inset-y-0 -right-2 flex w-2 cursor-col-resize items-center justify-center"
              @pointerdown.stop.prevent="resize.startResize(c, $event)" @dblclick.stop.prevent="resize.resetColumn(c)">
              <span class="h-4 border-l border-outline-gray-2 opacity-0 transition-opacity group-hover:opacity-100" :class="{ 'opacity-100': resize.resizingFieldname.value === c.fieldname }" />
            </span>
          </div>
        </ListHeader>
        <ListGroup v-for="g in groups" :key="g.key" :label="g.label || undefined">
          <ListRow v-for="row in g.rows" :key="rowKey(row)" class="cursor-pointer sm:rounded-[10px]" :class="isOpen(row) ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-1'"
            data-row :data-active="isOpen(row) || undefined">
            <!-- the whole-row target; links and controls inside a row carry the class `relative` to sit above it -->
            <button type="button" class="absolute inset-0 sm:rounded-[10px] focus-visible:focus-ring" :aria-label="rowLabel(row)" :data-ref="rowRef(row)" @click="open(row)" />
            <template v-if="mode === 'table'">
              <ListCell v-for="c in columns" :key="c.fieldname" class="py-2.5 text-base text-ink-gray-8 max-md:!hidden" :class="c.align === 'right' ? 'justify-end' : ''" :data-cell="c.fieldname">
                <slot :name="'cell-' + c.fieldname" :row="row" :column="c"><span class="truncate">{{ display(row, c) }}</span></slot>
              </ListCell>
              <ListCell class="py-2.5 md:!hidden">
                <div class="min-w-0 flex-1"><slot name="stack" :row="row">
                  <div class="text-base-medium text-ink-gray-9">{{ rowLabel(row) }}</div>
                  <div class="text-sm text-ink-gray-6">{{ columns.slice(1).map((c) => display(row, c)).filter(Boolean).join(' · ') }}</div>
                </slot></div>
              </ListCell>
            </template>
            <ListCell v-else class="py-2.5"><div class="min-w-0 flex-1"><slot name="row" :row="row" /></div></ListCell>
          </ListRow>
        </ListGroup>
      </List>
    </Card>
    <Card v-if="!grouped && loaded && !rows.length && !(mode === 'custom' && !activeN)" data-lv-empty>
      <Empty v-if="activeN" :title="`No ${noun} match these filters.`">
        {{ activeText }}.
        <div class="mt-2.5"><Button label="Clear filters" @click="clearFilters" /></div>
      </Empty>
      <Empty v-else :title="emptyTitle || `No ${noun} yet.`" :hint="emptyHint" />
    </Card>
    <div v-if="!loaded" class="flex flex-col gap-3 py-2" aria-busy="true"><Skeleton v-for="i in 5" :key="i" class="h-9 w-full rounded-4" /></div>
    <div v-if="!grouped && rows.length < total"><Button :loading="loading" :label="`Show more (${total - rows.length} left)`" data-more @click="load(true)" /></div>
    <slot name="below" />
  </div>
</template>

<script setup>
// The one list every list screen uses. It owns the view switch, the URL form of the filters, the row that is open in the
// pane, and the remembered state. Everything inside it comes from the two libraries: frappe-ui's list parts for the rows,
// and @framework/ui's Filter, QuickFilter, SortBy, GroupBy and ColumnSettings (through src/framework) for the controls.
//
// The URL is the single source of truth for what is listed. Controls write to it; a change of the URL fetches.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { Badge, BottomSheet, Button, Checkbox, Select, Skeleton, TabButtons } from 'frappe-ui'
import { List, ListCell, ListGroup, ListHeader, ListHeaderCell, ListHeaderCellSort, ListRow } from 'frappe-ui/list'
import PageHead from './PageHead.vue'
import TabBar from './TabBar.vue'
import Empty from './Empty.vue'
import Card from './ui/Card.vue'
import LifeFilter from '@/framework/LifeFilter.vue'
import LifeQuickFilter from '@/framework/LifeQuickFilter.vue'
import LifeSortBy from '@/framework/LifeSortBy.vue'
import LifeGroupBy from '@/framework/LifeGroupBy.vue'
import LifeGroupTable from '@/framework/LifeGroupTable.vue'
import LifeColumnSettings from '@/framework/LifeColumnSettings.vue'
import { useLifeListView } from '@/framework/useLifeListView'
import { directionFor, nextSort, useLifeColumnResize } from '@/framework/columnResize'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { lookups } from '@/lib/lookups'
import { dateTime, short } from '@/lib/dates'
import { current, openRef, onRecordChanged, paneNav } from '@/lib/pane'
import { activeCount, canonical, filtersToQuery, orderByToQuery, parseWire, queryToFilters, queryToOrderBy, queryToRequest } from '@/lib/filterUrl'
import { saveView, savedView, viewsLoaded, whenViewsLoaded } from '@/lib/views'

const props = defineProps({
  title: String, sub: String, crumb: Object,
  noun: { type: String, default: 'records' },
  screen: { type: String, required: true }, // the key the view is remembered under: 'tasks'
  doctype: { type: String, required: true }, // whose fields the controls offer: 'Life Task', or 'Life Index' for a cross-type list
  spec: { type: Array, default: () => [] }, // the short URL parameters of this list (see lib/filterUrl.js)
  flagLabels: { type: Object, default: () => ({}) }, // { done: 'Show done' }: switches of kind 'flag', shown as checkboxes; the rest show only while on
  quiet: { type: Array, default: () => [] }, // flags that show only while they are on (set by a count link)
  quick: { type: Array, default: () => [] }, // the fields of the quick-filter strip until the person chooses others
  virtual: { type: Array, default: () => [] }, // filter fields with no column behind them, resolved by the server from a short parameter
  synthetic: { type: Array, default: () => [] }, // table columns the screen draws itself: { key: '_badge', label, width, align, place }
  hidden: { type: Array, default: () => [] }, // fields not offered in the filter
  // state tabs: { key: 'status', field: 'status', label, items: [{ value, label }] }. The first item is the default and is not
  // written to the URL; one item has the value 'all'. `key` is the short URL parameter, `field` the field it is a preset on.
  tabs: { type: Object, default: null },
  views: { type: Array, default: () => [] }, // [{ key, label, mode }] with mode 'table' (columns), 'feed' (the #row slot) or 'custom' (the #body slot)
  mode: { type: String, default: 'table' }, // the mode when there is no view switch
  groupable: { type: Boolean, default: true },
  fetch: { type: Function, required: true }, // ({ params, filters, order_by, fields, summary, start, page_length, view }) => { rows, total } or { summary }
  rowRef: { type: Function, default: () => null },
  rowKey: { type: Function, default: (r) => r.name },
  rowLabel: { type: Function, default: (r) => r.title || r.name },
  groupBy: { type: Function, default: null }, // (row) => the heading its rows are listed under
  watchKeys: { type: Array, default: () => [] }, // other query keys that change what is listed
  emptyTitle: String, emptyHint: String,
  pageSize: { type: Number, default: 50 },
  // A list inside a record page's tab (the area page): `fixed` are short parameters the page sets and the person cannot
  // change ({ area }), left out of the URL and the controls. `active` is false while another tab is open: the list then
  // keeps what it shows and ignores the URL, which belongs to the open tab; on its return it puts its own query back.
  fixed: { type: Object, default: null },
  active: { type: [Boolean, Function], default: true }, // or (route) => boolean, so it turns with the same URL change as the tab
  tabsInFilter: Boolean, // show the state tabs as a control in the filter bar (a list inside a page's tab)
})
const emit = defineEmits(['loaded'])
const route = useRoute()
const router = useRouter()
const phone = useMediaQuery('(max-width: 639px)')
// The lens (lib/lens.js) owns `area=`: a list whose spec has an area filter takes the lens's area, and the area is left
// out of its controls, its remembered view and its Clear (UX fixes, set 6). A list inside a record page's tab (`fixed`)
// lists what is filed under that record, whatever the lens.
const hasArea = props.spec.some((e) => e.key === 'area')
const lensKey = hasArea && !props.fixed ? 'area' : null
const fixedKeys = [...new Set([...(props.fixed ? Object.keys(props.fixed) : []), ...(hasArea ? ['area'] : [])])]
const fixedFields = props.spec.filter((e) => fixedKeys.includes(e.key)).map((e) => e.field)
const list = useLifeListView(props.doctype, { virtual: props.virtual.filter((v) => !fixedFields.includes(v.fieldname)), synthetic: props.synthetic, hidden: [...props.hidden, ...fixedFields] })
// the query this list reads: the URL while it is the open tab, what it last saw while another tab is open
const isActive = computed(() => (typeof props.active === 'function' ? !!props.active(route) : props.active))
let last = {}
let stash = null // this list's own query when its tab was left
const Q = computed(() => {
  if (!isActive.value) return last
  // back on this tab with no list query in the URL: the list's own query, which the URL is given at once (below)
  if (stash && Object.keys(stash).length && !Object.keys(canonical(route.query, spec.value, keep.value)).length) last = { ...route.query, ...stash }
  else last = route.query
  return last
})
const resize = useLifeColumnResize(list)
const rows = ref([])
const total = ref(0)
const loaded = ref(false)
const loading = ref(false)
const sheet = ref(false)
const groupRows = ref([])
const groupTotals = ref(null)
let seq = 0
let touched = false // the person has changed something on this screen since it opened

// ---- the view switch ----
const viewOptions = computed(() => props.views.map((v) => ({ label: v.label, value: v.key })))
const view = computed(() => {
  const q = Q.value.view
  if (props.views.some((v) => v.key === q)) return q
  return props.views[0]?.key || ''
})
const mode = computed(() => props.views.find((v) => v.key === view.value)?.mode || props.mode)
const keep = computed(() => [...(props.views.length ? ['view'] : []), ...(props.tabs && !props.spec.some((e) => e.key === props.tabs.key) ? [props.tabs.key] : []), ...props.watchKeys])
function setView(v) {
  touched = true
  router.push({ query: { ...route.query, view: v, all: undefined } })
}

// ---- state tabs ----
// The tab is the value of one short parameter (status=Done). No value, or the first tab's, is the first tab. A value that
// is not a tab, or a condition on the same field made in the Filter, selects All and shows as a condition in the filter bar.
const tabValues = computed(() => (props.tabs ? props.tabs.items.map((t) => t.value) : []))
const spec = computed(() => props.spec.filter((e) => !fixedKeys.includes(e.key)).map((e) => (props.tabs && e.key === props.tabs.key ? { ...e, skip: tabValues.value } : e)))
const tabRaw = computed(() => (props.tabs && Q.value[props.tabs.key] ? String(Q.value[props.tabs.key]) : ''))
const tab = computed(() => {
  if (!props.tabs) return ''
  if (parseWire(Q.value.f).some((w) => w[0] === props.tabs.field)) return 'all'
  if (!tabRaw.value) return tabValues.value[0]
  return tabValues.value.includes(tabRaw.value) ? tabRaw.value : 'all'
})
const tabCounts = ref(null)
// A value that is not a tab (status=Dropped) shows under All: All then counts what it shows
const offTab = computed(() => !!tabRaw.value && !tabValues.value.includes(tabRaw.value))
const tabItems = computed(() => (props.tabs ? props.tabs.items.map((t) => ({ ...t, noun: props.noun,
  count: !tabCounts.value ? undefined : t.value === 'all' && offTab.value && tab.value === 'all' && !grouped.value ? total.value : tabCounts.value[t.value] ?? 0 })) : []))
const tabOptions = computed(() => tabItems.value.map((t) => ({ value: t.value, label: t.count === undefined ? t.label : `${t.label} (${t.count})` })))
const tabParam = (v) => (v === tabValues.value[0] ? undefined : v)
function setTab(v) {
  const rest = parseWire(Q.value.f).filter((w) => w[0] !== props.tabs.field)
  push({ [props.tabs.key]: tabParam(v), f: rest.length ? JSON.stringify(rest) : undefined })
}
// the filter part of a query made by the controls keeps the tab, unless a condition on the tab's field takes its place
function controlsQuery(wire, flags) {
  const q = filtersToQuery(wire, flags, spec.value, store.today)
  if (props.tabs && q[props.tabs.key] === undefined && !wire.some((w) => w[0] === props.tabs.field) && tabValues.value.includes(tabRaw.value)) q[props.tabs.key] = tabRaw.value
  return q
}

// ---- filters: the URL, the controls, and what the server is asked ----
const flagSpec = computed(() => props.spec.filter((e) => e.kind === 'flag'))
const flagValues = computed(() => queryToFilters(Q.value, spec.value, store.today).flags)
const shownFlags = computed(() => flagSpec.value.filter((e) => props.flagLabels[e.key] && (!props.quiet.includes(e.key) || flagValues.value[e.key]))
  .map((e) => ({ key: e.key, label: props.flagLabels[e.key] })))
const activeN = computed(() => activeCount(Q.value, spec.value))
const sorts = computed(() => list.view.sort.by.value)
const grouped = computed(() => !!list.summary.value)
const key = (w) => JSON.stringify([...w].map((x) => JSON.stringify(x)).sort())
const urlWire = () => queryToFilters(Q.value, spec.value, store.today).wire

// the active filters in words, for the empty state: "Type: Medical · Expiry: Expired"
const activeText = computed(() => {
  const parts = []
  for (const e of spec.value) {
    const v = Q.value[e.key] ? String(Q.value[e.key]) : ''
    if (!v || e.skip?.includes(v)) continue
    if (e.kind === 'flag') parts.push(props.flagLabels[e.key] || e.key)
    else parts.push(`${e.label || list.field(e.field)?.label || e.key}: ${e.labels?.[v] || nameOf(e.field, v)}`)
  }
  for (const [field, op, value] of queryToRequest(Q.value, spec.value).filters) {
    parts.push(`${list.field(field)?.label || field} ${op} ${Array.isArray(value) ? value.join(', ') : value}`)
  }
  return parts.join(' · ')
})
function nameOf(field, value) {
  if (value === 'none') return 'none'
  const hit = lookups.areas.find((a) => a.name === value) || (lookups.goals || []).find((x) => x.name === value) || (lookups.people || []).find((x) => x.name === value)
  return hit ? hit.area_name || hit.title || hit.full_name : value
}

function push(patch) {
  touched = true
  router.push({ query: { ...route.query, ...patch, all: undefined } })
}
const setFlag = (k, on) => push({ [k]: on ? '1' : undefined })
// Goals > No goal is this list with goal=none; clearing keeps that, or the address would become the screen of issue 22 and the cleared state would never be saved
const clearFilters = () => push({ ...controlsQuery([], {}), ...(props.screen === 'tasks-no-goal' ? { goal: 'none' } : {}) })

// URL -> controls. Skipped when the controls already say the same thing, so an edit in the Filter popover is not reset under the cursor.
function applyUrl() {
  if (!list.ready.value) return
  const wire = urlWire()
  if (key(wire) !== key(list.wire.value)) list.setWire(wire)
  const order = queryToOrderBy(Q.value)
  if (order !== list.orderBy.value) list.setOrderBy(order)
}
// controls -> URL
watch(() => [key(list.wire.value), list.orderBy.value], () => {
  if (!list.ready.value) return
  const patch = {}
  if (key(list.wire.value) !== key(urlWire())) Object.assign(patch, controlsQuery(list.wire.value, flagValues.value))
  if (list.orderBy.value !== queryToOrderBy(Q.value)) Object.assign(patch, orderByToQuery(list.orderBy.value))
  if (Object.keys(patch).length) push(patch)
})

// ---- columns of the table view ----
const columns = computed(() => list.view.columns.shown.value.map((c) => {
  const syn = props.synthetic.find((s) => s.key === c.fieldname)
  const meta = list.fieldMeta(c.fieldname)
  const numeric = meta && ['Int', 'Float', 'Currency', 'Percent'].includes(meta.fieldtype)
  return { ...c, sortable: !syn, align: syn?.align || (numeric ? 'right' : 'left'), width: c.width || syn?.width }
}))
const tracks = computed(() => {
  if (mode.value !== 'table') return ['minmax(0, 1fr)']
  const wide = columns.value.map((c, i) => resize.drafts[c.fieldname] || c.width || (i === 0 ? 'minmax(0, 2fr)' : 'minmax(0, 1fr)'))
  return { base: ['minmax(0, 1fr)'], md: wide.length ? wide : ['minmax(0, 1fr)'] }
})
// columns the table shows that the list method does not return by itself
const extraFields = computed(() => (mode.value === 'table' ? list.view.columns.shown.value.map((c) => c.fieldname).filter((f) => !f.startsWith('_')) : []))

function display(row, c) {
  const f = c.fieldname
  const v = row[f]
  const type = list.fieldMeta(f)?.fieldtype
  if (type === 'Link' || f === 'area' || f === 'goal') return row[f + '_name'] ?? row[f + '_title'] ?? row[f + '_label'] ?? v ?? ''
  if (type === 'Date') return v ? short(v, true) : ''
  if (type === 'Datetime' || f === 'creation' || f === 'modified') return v ? dateTime(v) : ''
  if (type === 'Check') return v ? 'Yes' : 'No'
  return v ?? ''
}

// ---- rows ----
const groups = computed(() => {
  const out = []
  for (const row of rows.value) {
    const label = props.groupBy ? props.groupBy(row) || '' : ''
    const last = out[out.length - 1]
    if (last && last.label === label) last.rows.push(row)
    else out.push({ label, key: `${out.length}:${label}`, rows: [row] })
  }
  return out
})
const isOpen = (row) => !!current.value && current.value.ref === props.rowRef(row)
const open = (row) => openRef(props.rowRef(row))

function request(start, page_length) {
  const { params: own, filters } = queryToRequest(Q.value, spec.value)
  const params = { ...own, ...(props.fixed || {}), ...(lensKey && Q.value.area ? { area: String(Q.value.area) } : {}) }
  return { params, tab: tab.value, filters: filters.length ? filters : undefined, order_by: queryToOrderBy(Q.value) || undefined,
    fields: extraFields.value.length ? extraFields.value : undefined, start, page_length, view: view.value, query: Q.value }
}
async function load(append = false) {
  const mine = ++seq
  loading.value = true
  if (grouped.value) {
    const res = await tryCall(() => props.fetch({ ...request(0, 100), summary: list.summary.value }))
    if (mine !== seq) return
    loading.value = false
    if (!res) return
    if (res.tabs) tabCounts.value = res.tabs
    groupRows.value = res.summary?.rows || []
    groupTotals.value = res.summary?.totals || null
    loaded.value = true
    return
  }
  const res = await tryCall(() => props.fetch(request(append ? rows.value.length : 0, props.pageSize)))
  if (mine !== seq) return
  loading.value = false
  if (!res) return
  rows.value = append ? [...rows.value, ...res.rows] : res.rows
  total.value = res.total
  if (res.tabs) tabCounts.value = res.tabs
  loaded.value = true
  emit('loaded', res)
}
// Load again in place after a record changed, keeping as many rows as were on screen so the scroll position holds.
async function refresh() {
  if (grouped.value) return load()
  const mine = ++seq
  const want = Math.max(rows.value.length, props.pageSize)
  let out = []
  let res = null
  while (out.length < want) {
    res = await tryCall(() => props.fetch(request(out.length, Math.min(100, want - out.length))))
    if (!res || mine !== seq) return
    out = [...out, ...res.rows]
    if (!res.rows.length || out.length >= res.total) break
  }
  rows.value = out
  total.value = res.total
  if (res.tabs) tabCounts.value = res.tabs
  loaded.value = true
  emit('loaded', res)
}

// ---- remembered state: one per user, screen and space, kept on the server (lib/views.js) ----
const listQuery = () => canonical(Q.value, spec.value, keep.value)
const hasQuery = () => Object.keys(listQuery()).length > 0 || Q.value.all === '1'
function remember() {
  const layout = { ...list.layout.value }
  // the quick-filter fields are saved only once the person has chosen their own
  if (!quickReady || JSON.stringify(layout.quick) === JSON.stringify(props.quick)) delete layout.quick
  saveView(props.screen, { query: listQuery(), ...layout })
}
// Opening the list with no query restores the saved one and writes it into the URL. With a query, the list shows exactly
// that, and the saved view switch still applies. The open record is never saved or restored.
function restore(saved, { late = false } = {}) {
  if (!saved) return
  if (!late) list.restoreLayout(saved)
  const { area: _lens, ...q } = saved.query || {} // a view saved before the lens may hold an area: the lens decides that now
  // Goals > No goal opens with goal=none already in the address; that alone is not a query of the person's
  const implied = props.screen === 'tasks-no-goal' && Object.keys(listQuery()).length === 1 && Q.value.goal === 'none' && Q.value.all !== '1'
  if (implied || !hasQuery()) {
    if (Object.keys(q).length) router.replace({ query: { ...route.query, ...q } })
  } else if (!Q.value.view && q.view && props.views.some((v) => v.key === q.view)) {
    router.replace({ query: { ...route.query, view: q.view } })
  }
}
const initial = savedView(props.screen)
let quickReady = false // the strip shows the screen's own fields, or the saved ones
restore(initial)
if (!viewsLoaded()) whenViewsLoaded(() => { if (!touched) restore(savedView(props.screen)) })

const fetchKey = computed(() => JSON.stringify([listQuery(), list.summary.value, extraFields.value, mode.value, lensKey && Q.value.area]))
watch(fetchKey, () => load())
watch(() => JSON.stringify(listQuery()), () => { applyUrl(); if (viewsLoaded()) remember() })
watch(() => JSON.stringify(list.layout.value), () => { if (list.ready.value && viewsLoaded()) remember() })
watch(() => list.ready.value, (ok) => {
  if (!ok) return
  // a state tab takes the place of its field in the strip, also in a strip saved before the tabs existed
  const quick = ((savedView(props.screen) || initial)?.quick || []).filter((f) => f !== props.tabs?.field)
  const own = (props.quick || []).filter((f) => !fixedFields.includes(f))
  if (quick.length || own.length) list.setQuickFields(quick.length ? quick.filter((f) => !fixedFields.includes(f)) : own)
  quickReady = true
  applyUrl()
}, { immediate: true })
watch(rows, () => { if (isActive.value) paneNav.rows = rows.value.map((r) => props.rowRef(r)).filter(Boolean) }, { immediate: true })
// leaving and coming back to this list's tab
watch(isActive, (on) => {
  if (!on) {
    stash = canonical(last, spec.value, keep.value)
    return
  }
  paneNav.rows = rows.value.map((r) => props.rowRef(r)).filter(Boolean)
  const own = canonical(Q.value, spec.value, keep.value)
  if (Object.keys(own).length && !Object.keys(canonical(route.query, spec.value, keep.value)).length) router.replace({ query: { ...route.query, ...own } })
  stash = null
})
onRecordChanged(() => isActive.value && refresh())
onMounted(() => {
  load()
  if (viewsLoaded() && hasQuery()) remember()
})
onUnmounted(() => (paneNav.rows = []))
defineExpose({ reload: refresh, rows, total, view, mode, tab, tabCounts })
</script>
