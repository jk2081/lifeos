<template>
  <PageHead v-if="title" :title="title" :crumb="crumb" :count="loaded ? total : null">
    <template #sub><slot name="sub">{{ sub }}</slot></template>
    <slot name="actions" />
  </PageHead>
  <div class="bd lv">
    <slot name="above" />
    <div class="lv-bar">
      <slot name="bar" />
      <span v-if="!title && loaded" class="pl n" data-lv-count>{{ total }}</span>
      <button class="ch only-phone lv-fbtn" :class="{ on: showFilters }" type="button" :aria-expanded="showFilters" @click="showFilters = !showFilters">
        Filters<template v-if="active.length"> ({{ active.length }})</template>
      </button>
      <div class="lv-filters" :class="{ open: showFilters }">
        <template v-for="f in shown" :key="f.key">
          <label v-if="f.type === 'check'" class="mt lv-check"><input type="checkbox" class="ck" style="margin: 0" :checked="!!values[f.key]"
            :data-filter="f.key" @change="setFilter(f.key, $event.target.checked ? '1' : '')" /> {{ f.label }}</label>
          <label v-else-if="f.type === 'date'" class="lv-date"><span class="mt">{{ f.label }}</span>
            <input type="date" class="inp" :value="values[f.key]" :aria-label="f.label" :data-filter="f.key" @change="setFilter(f.key, $event.target.value)" /></label>
          <select v-else class="inp" :class="{ set: !!values[f.key] }" :value="values[f.key]" :aria-label="f.label" :data-filter="f.key" @change="setFilter(f.key, $event.target.value)">
            <option value="">{{ f.all || 'Any ' + f.label.toLowerCase() }}</option>
            <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
            <option v-if="values[f.key] && !f.options.some((o) => String(o.value) === values[f.key])" :value="values[f.key]">{{ f.label }}: {{ values[f.key] }}</option>
          </select>
        </template>
        <template v-if="sortable.length && !custom">
          <select class="inp lv-sort" :value="sort" aria-label="Sort by" data-sort @change="setSort($event.target.value, dir)">
            <option value="">Sort: {{ defaultSort || 'default' }}</option>
            <option v-for="c in sortable" :key="c.sort" :value="c.sort">Sort: {{ c.label }}</option>
          </select>
          <button v-if="sort" class="bt s ic" type="button" :aria-label="dir === 'desc' ? 'Descending. Switch to ascending' : 'Ascending. Switch to descending'"
            @click="setSort(sort, dir === 'desc' ? '' : 'desc')">{{ dir === 'desc' ? '↓' : '↑' }}</button>
        </template>
        <button v-if="active.length" class="bt t" type="button" data-clear @click="clearFilters">Clear filters</button>
      </div>
    </div>

    <slot v-if="custom" name="body" :rows="rows" :loaded="loaded" :reload="refresh" />
    <div v-else-if="rows.length" class="cd list lv-list" role="list">
      <div v-if="columns.some((c) => c.label)" class="lv-cells lv-head" :style="grid" aria-hidden="true">
        <span v-for="c in columns" :key="c.key" :class="{ r: c.align === 'right' }">
          <button v-if="c.sort" type="button" class="lv-th" @click="setSort(c.sort, sort === c.sort && dir !== 'desc' ? 'desc' : '')">{{ c.label }}<template v-if="sort === c.sort"> {{ dir === 'desc' ? '↓' : '↑' }}</template></button>
          <template v-else>{{ c.label }}</template>
        </span>
      </div>
      <template v-for="(row, i) in rows" :key="rowKey(row)">
        <div v-if="groupBy && groupBy(row) !== (i ? groupBy(rows[i - 1]) : undefined)" class="lv-group">{{ groupBy(row) }}</div>
        <div class="lv-row" :class="{ on: openRefNow === rowRef(row) }" role="listitem" tabindex="0" :data-ref="rowRef(row)"
          @click="click($event, row)" @keydown.enter.self="open(row)">
          <div class="lv-cells" :style="grid">
            <div v-for="c in columns" :key="c.key" class="lv-cell" :class="{ r: c.align === 'right', nw: c.nowrap }">
              <slot :name="'cell-' + c.key" :row="row">{{ row[c.key] }}</slot>
            </div>
          </div>
          <div class="lv-stack"><slot name="stack" :row="row">
            <div v-for="c in columns" :key="c.key"><slot :name="'cell-' + c.key" :row="row">{{ row[c.key] }}</slot></div>
          </slot></div>
        </div>
      </template>
    </div>
    <div v-if="loaded && !rows.length && !(custom && !active.length)" class="cd" data-lv-empty>
      <Empty v-if="active.length" :title="`No ${noun} match these filters.`">
        {{ active.map((f) => `${f.label}: ${labelOf(f)}`).join(' · ') }}.
        <div style="margin-top: 10px"><button class="bt s" type="button" @click="clearFilters">Clear filters</button></div>
      </Empty>
      <Empty v-else :title="emptyTitle || `No ${noun} yet.`" :hint="emptyHint" />
    </div>
    <div v-if="rows.length < total"><button class="bt s" type="button" data-more :disabled="loading" @click="load(true)">Show more ({{ total - rows.length }} left)</button></div>
    <slot name="below" />
  </div>
</template>

<script setup>
// The one list every list screen uses: a filter bar kept in the URL, a count of what the filters match,
// aligned and sortable columns on desktop, stacked rows on phones, 50 rows at a time, and rows that open the record pane.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHead from './PageHead.vue'
import Empty from './Empty.vue'
import { tryCall } from '@/lib/api'
import { current, openRef, onRecordChanged, paneNav } from '@/lib/pane'

const props = defineProps({
  title: String, sub: String, crumb: Object,
  noun: { type: String, default: 'records' },
  filters: { type: Array, default: () => [] }, // [{ key, label, type: 'select' | 'date' | 'check', options, all, quiet }]
  columns: { type: Array, default: () => [] }, // [{ key, label, width, sort, align, nowrap }]
  fetch: { type: Function, required: true }, // ({ filters, sort, dir, start, page_length }) => { rows, total }
  rowRef: { type: Function, default: () => null },
  rowKey: { type: Function, default: (r) => r.name },
  groupBy: { type: Function, default: null },
  watchKeys: { type: Array, default: () => [] }, // other query keys that change what is listed
  defaultSort: String, emptyTitle: String, emptyHint: String,
  pageSize: { type: Number, default: 50 },
  custom: Boolean, // the screen draws the rows itself (a board, cards) in the #body slot
})
const emit = defineEmits(['loaded'])
const route = useRoute()
const router = useRouter()
const rows = ref([])
const total = ref(0)
const loaded = ref(false)
const loading = ref(false)
const showFilters = ref(false)
let seq = 0

const values = computed(() => Object.fromEntries(props.filters.map((f) => [f.key, route.query[f.key] ? String(route.query[f.key]) : ''])))
const active = computed(() => props.filters.filter((f) => values.value[f.key]))
// a quiet filter is set by a link from a count; it shows in the bar only while it is on
const shown = computed(() => props.filters.filter((f) => !f.quiet || values.value[f.key]))
const sortable = computed(() => props.columns.filter((c) => c.sort))
const sort = computed(() => (route.query.sort ? String(route.query.sort) : ''))
const dir = computed(() => (route.query.dir === 'desc' ? 'desc' : ''))
const grid = computed(() => `grid-template-columns: ${props.columns.map((c) => c.width || 'minmax(0, 1fr)').join(' ')}`)
const openRefNow = computed(() => current.value?.ref)

function labelOf(f) {
  const v = values.value[f.key]
  if (f.type === 'check') return 'yes'
  return f.options?.find((o) => String(o.value) === v)?.label || v
}
function push(patch) {
  router.push({ query: { ...route.query, ...patch } })
}
const setFilter = (key, value) => push({ [key]: value || undefined })
const setSort = (s, d) => push({ sort: s || undefined, dir: s && d ? d : undefined })
const clearFilters = () => push(Object.fromEntries(props.filters.map((f) => [f.key, undefined])))

async function load(append = false) {
  const mine = ++seq
  loading.value = true
  const res = await tryCall(() => props.fetch({ filters: { ...values.value }, sort: sort.value, dir: dir.value,
    start: append ? rows.value.length : 0, page_length: props.pageSize }))
  if (mine !== seq) return
  loading.value = false
  if (!res) return
  rows.value = append ? [...rows.value, ...res.rows] : res.rows
  total.value = res.total
  loaded.value = true
  emit('loaded', res)
}
// Load again in place after a record changed, keeping as many rows as were on screen so the scroll position holds.
async function refresh() {
  const mine = ++seq
  const want = Math.max(rows.value.length, props.pageSize)
  let out = []
  let res = null
  while (out.length < want) {
    res = await tryCall(() => props.fetch({ filters: { ...values.value }, sort: sort.value, dir: dir.value, start: out.length,
      page_length: Math.min(100, want - out.length) }))
    if (!res || mine !== seq) return
    out = [...out, ...res.rows]
    if (!res.rows.length || out.length >= res.total) break
  }
  rows.value = out
  total.value = res.total
  loaded.value = true
  emit('loaded', res)
}
const open = (row) => openRef(props.rowRef(row))
function click(e, row) {
  if (e.target.closest('a, button, input, select, label, textarea')) return
  open(row)
}

watch(() => [...props.filters.map((f) => f.key), 'sort', 'dir', ...props.watchKeys].map((k) => route.query[k] || '').join('\u0001'), () => load())
watch(rows, () => (paneNav.rows = rows.value.map((r) => props.rowRef(r)).filter(Boolean)), { immediate: true })
onRecordChanged(refresh)
onMounted(() => load())
onUnmounted(() => (paneNav.rows = []))
defineExpose({ reload: refresh, rows, total })
</script>
