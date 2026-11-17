<template>
  <ListView ref="list" :title="embed ? null : 'Tasks'" noun="tasks" :screen="embed ? embed.screen + '-tasks' : 'tasks'" :fixed="embed?.fixed" :active="embed ? embed.active : true" :tabs-in-filter="!!embed"
    doctype="Life Task" :spec="SPEC" :flag-labels="FLAGS" :quiet="['archived']" :quick="QUICK" :virtual="VIRTUAL"
    :synthetic="SYNTHETIC" :views="views" :tabs="TABS" :fetch="fetch" :row-ref="(r) => 'task:' + r.name" :group-by="dueGroup"
    :empty-title="EMPTY[tab] || 'No tasks here.'"
    :empty-hint="tab === 'loops' ? 'Open tasks older than 14 days with no due date gather here.' : tab === 'open' ? 'Type a title in the box above and press Enter, or accept a task proposal in the Inbox.' : ''"
    @loaded="(res) => (today = res.today)">
    <template #sub><span data-tasks-sub>{{ tab === 'loops' ? 'Open loops: open tasks older than 14 days with no due date. Give each a date, carry it, or drop it.' : `${store.space} · by due date, then priority` }}</span></template>
    <template #above>
 <div v-if="embed && tab === 'loops'" class="text-sm text-ink-gray-6" data-tasks-sub>Open loops: open tasks older than 14 days with no due date. Give each a date, carry it, or drop it.</div>
      <TextInput v-if="embed ? embed.writable : canWrite()" v-model="quick" size="md" placeholder="Add a task and press Enter. A date word such as tomorrow or fri sets the due date."
        aria-label="Quick add" @keydown.enter="add" />
    </template>

    <!-- list and open loops: one row per task -->
    <template #row="{ row }">
      <div class="flex items-start gap-2.5">
        <Checkbox class="relative mt-0.5" :model-value="row.status === 'Done'" :disabled="!canWrite()" :aria-label="'Done: ' + row.title" @update:model-value="toggle(row)" />
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium" :class="struck(row)">{{ row.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ taskMeta(row, today, { withDue: true }) }}</div></div>
        <Badge v-if="taskPill(row, today)" :theme="taskPill(row, today).theme"><span class="max-md:hidden">{{ taskPill(row, today).text }}</span>
          <span class="md:hidden">{{ taskPill(row, today).shortText || taskPill(row, today).text }}</span></Badge>
      </div>
    </template>
    <!-- table -->
    <template #cell-_check="{ row }"><Checkbox class="relative" :model-value="row.status === 'Done'" :disabled="!canWrite()" :aria-label="'Done: ' + row.title" @update:model-value="toggle(row)" /></template>
    <template #cell-title="{ row }"><span class="break-words font-medium" :class="struck(row)">{{ row.title }}</span></template>
    <template #cell-due_date="{ row }"><span class="whitespace-nowrap" :class="row.due_date && row.due_date < today && OPEN.includes(row.status) ? 'text-ink-red-8' : ''">{{ short(row.due_date, true) }}</span></template>
    <template #cell-goal="{ row }"><span class="truncate">{{ row.goal_title }}</span></template>
    <template #stack="{ row }">
      <div class="flex items-start gap-2.5">
        <Checkbox class="relative mt-0.5" :model-value="row.status === 'Done'" :disabled="!canWrite()" :aria-label="'Done: ' + row.title" @update:model-value="toggle(row)" />
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium" :class="struck(row)">{{ row.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ taskMeta(row, today, { withDue: true }) }}</div></div>
        <Badge v-if="taskPill(row, today)" :theme="taskPill(row, today).theme" :label="taskPill(row, today).shortText || taskPill(row, today).text" />
      </div>
    </template>

    <!-- board -->
    <template #body="{ rows, loaded }">
      <div class="grid items-start gap-4" :class="board.length === 2 ? 'md:grid-cols-2' : 'md:grid-cols-4'" data-board>
        <div v-for="col in board" :key="col" class="flex min-h-28 flex-col gap-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 p-3" :data-column="col" @dragover.prevent @drop="drop(col)">
          <SectionHead :count="boardCounts[col] ?? null" :to="{ query: { ...route.query, view: 'table', status: col, done: undefined, open: undefined } }">{{ col }}</SectionHead>
          <div v-for="t in rows.filter((r) => r.status === col)" :key="t.name" class="relative cursor-grab rounded-4 border bg-surface-base px-3 py-2.5 hover:bg-surface-gray-1"
            :class="isOpen(t) ? 'border-outline-gray-4 !bg-surface-gray-3' : 'border-outline-gray-2'" draggable="true" data-row :data-active="isOpen(t) || undefined" @dragstart="dragging = t">
            <button type="button" class="absolute inset-0 rounded-4 focus-visible:focus-ring" :aria-label="t.title" :data-ref="'task:' + t.name" @click="openRef('task:' + t.name)" />
            <div class="break-words text-base-medium text-ink-gray-9">{{ t.title }}</div>
            <div class="text-sm text-ink-gray-6">{{ taskMeta(t, today, { withDue: true }) }}</div>
            <div class="mt-1.5 flex flex-wrap items-center gap-2">
              <Badge v-if="t.priority" :label="t.priority" />
              <Select class="relative w-28" size="sm" :model-value="t.status" :options="BOARD" aria-label="Move to" :disabled="!canWrite()" @update:model-value="(v) => move(t, v)" />
            </div>
          </div>
          <div v-if="loaded && !rows.some((r) => r.status === col)" class="px-0.5 py-2 text-sm text-ink-gray-6">Nothing {{ col.toLowerCase() }}.</div>
        </div>
      </div>
    </template>
  </ListView>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Checkbox, Select, TextInput } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { api, optimistic, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short, startOfWeek, addDays } from '@/lib/dates'
import { OPEN, taskMeta, taskPill } from '@/lib/tasks'
import { loadLookups } from '@/lib/lookups'
import { current, openRef } from '@/lib/pane'
import { DUE_PRESETS, parseWire } from '@/lib/filterUrl'

// the layout switch. The board is offered on the Open and All tabs only; on the other tabs a remembered board falls back to the list
const VIEWS = [{ key: 'list', label: 'List', mode: 'feed' }, { key: 'board', label: 'Board', mode: 'custom' }, { key: 'table', label: 'Table', mode: 'table' }]
// the state tabs, on the short parameter status=. "Open" is Open and Doing. A status that is not a tab (status=Dropped) shows under All as a filter
const TABS = { key: 'status', field: 'status', label: 'Task state', items: [{ value: 'open', label: 'Open' }, { value: 'loops', label: 'Open loops' },
  { value: 'Waiting', label: 'Waiting' }, { value: 'Done', label: 'Done' }, { value: 'Someday', label: 'Someday' }, { value: 'all', label: 'All' }] }
const EMPTY = { loops: 'No open loops.', Waiting: 'Nothing is waiting.', Done: 'No done tasks here.', Someday: 'No tasks are parked on the Someday list.' }
const BOARD = ['Open', 'Doing', 'Waiting', 'Done']
// the short URL parameters of this list, as the count links write them (lib/filterUrl.js)
const SPEC = [
  { key: 'area', field: 'area', kind: 'link' }, { key: 'goal', field: 'goal', kind: 'link' }, { key: 'tag', field: 'tag', kind: 'value' },
  { key: 'priority', field: 'priority', kind: 'link' },
  { key: 'due', field: 'due_date', kind: 'preset', label: 'Due', presets: DUE_PRESETS, labels: { overdue: 'overdue', today: 'today', 'today,overdue': 'today and overdue', week: 'this week', none: 'no date' } },
  { key: 'status', field: 'status', kind: 'value' },
  { key: 'completed_from', field: 'completed_on', kind: 'from' }, { key: 'completed_to', field: 'completed_on', kind: 'to' },
  { key: 'archived', kind: 'flag' },
]
const FLAGS = { archived: 'Include archived' }
const QUICK = ['area', 'goal', 'priority', 'due_date']
const VIRTUAL = [{ fieldname: 'tag', label: 'Tag', fieldtype: 'Link', options: 'Life Tag' }]
const SYNTHETIC = [{ key: '_check', label: '', width: '2rem', place: 'start' }]
// Inside a record page's tab (the goal page): { screen, fixed: { goal }, active(route) }
const props = defineProps({ embed: { type: Object, default: null } })
const route = useRoute()
const router = useRouter()
const list = ref(null)
const today = ref(store.today)
const quick = ref('')
const dragging = ref(null)
const boardCounts = ref({})
const view = computed(() => list.value?.view || 'list')
const tab = computed(() => list.value?.tab || 'open')
const views = computed(() => (['open', 'all'].includes(tab.value) ? VIEWS : VIEWS.filter((v) => v.key !== 'board')))
const board = computed(() => (tab.value === 'open' ? ['Open', 'Doing'] : BOARD))

// Links from before the tabs: view=loops was a layout and is now the Open loops tab; done=1 added closed tasks to the open ones.
watch(() => [route.query.view, route.query.done], ([v, done]) => {
  if ((v !== 'loops' && !done) || (props.embed && !props.embed.active(route))) return
  const query = { ...route.query, done: undefined }
  if (v === 'loops') Object.assign(query, { view: undefined, status: 'loops' })
  else if (!query.status) query.f = JSON.stringify([...parseWire(query.f).filter((w) => w[0] !== 'status'), ['status', '!=', 'Carried']])
  router.replace({ query })
}, { immediate: true })

const struck = (t) => (t.status === 'Done' || t.status === 'Dropped' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9')
const isOpen = (t) => current.value?.ref === 'task:' + t.name
// the list view groups by due date while it is in its own order
function dueGroup(t) {
  if (view.value !== 'list' || tab.value === 'loops' || route.query.sort) return ''
  const d = t.due_date
  if (!OPEN.includes(t.status)) return 'Closed'
  if (!d) return 'No date'
  if (d < today.value) return 'Overdue'
  if (d === today.value) return 'Today'
  return d <= addDays(startOfWeek(today.value), 6) ? 'This week' : 'Later'
}

async function fetch({ params: p, tab: t, filters, order_by, fields, summary, start, page_length, view: v }) {
  const base = { space: props.embed?.space || store.space, area: p.area, tag: p.tag, priority: p.priority, goal: p.goal, due: p.due,
    include_archived: p.archived ? 1 : 0, completed_from: p.completed_from, completed_to: p.completed_to, filters }
  // what each tab asks the server for; under All a status that is not a tab (status=Dropped) is passed as it is
  const status = t === 'open' ? 'open_doing' : t === 'loops' ? 'open' : t === 'all' ? p.status || 'all' : t
  if (v === 'board' && !summary) {
    // the board shows its columns; each column's count is the number of tasks with that status under the same filters
    const cols = t === 'open' ? ['Open', 'Doing'] : BOARD
    const res = await api('tasks.list', { ...base, status, start, page_length: 100 })
    const tasks = res.tasks.filter((x) => cols.includes(x.status))
    const counts = await Promise.all(cols.map((s) => (status !== 'all' && status !== 'open_doing' && status !== s ? { total: 0 } : api('tasks.list', { ...base, status: s, page_length: 1 }))))
    boardCounts.value = Object.fromEntries(cols.map((s, i) => [s, counts[i].total]))
    // the heading counts what the columns hold, so it agrees with the column counts; Show more brings the next cards
    return { rows: tasks, total: counts.reduce((n, c) => n + c.total, 0), today: res.today, tabs: res.tabs }
  }
  const res = await api('tasks.list', { ...base, status, loops: t === 'loops' ? 1 : 0,
    order_by: order_by || (t === 'loops' ? 'creation asc' : undefined), fields, summary, start, page_length })
  return summary ? res : { rows: res.tasks, total: res.total, today: res.today, tabs: res.tabs }
}
async function add() {
  const text = quick.value.trim()
  if (!text) return
  quick.value = ''
  const q = { ...route.query, ...(props.embed?.fixed || {}) }
  const area = q.area && q.area !== 'none' ? q.area : undefined
  const t = await tryCall(() => api('tasks.quick_add', { text, space: props.embed?.space || store.space, area, goal: q.goal && q.goal !== 'none' ? q.goal : undefined }))
  if (t) list.value.reload()
  else quick.value = text
}
function toggle(t) {
  const before = t.status
  const next = before === 'Done' ? 'Open' : 'Done'
  optimistic(() => (t.status = next), () => (t.status = before), () => api('tasks.set_status', { task: t.name, status: next }))
    .then(() => setTimeout(() => list.value?.reload(), 500)).catch(() => {})
}
function move(t, status) {
  if (!status || status === t.status) return
  if (status === 'Waiting' && !t.waiting_on) return openRef('task:' + t.name) // the pane asks who or what it waits on
  const before = t.status
  optimistic(() => (t.status = status), () => (t.status = before), () => api('tasks.set_status', { task: t.name, status }))
    .then(() => list.value?.reload()).catch(() => {})
}
function drop(col) {
  if (dragging.value && canWrite()) move(dragging.value, col)
  dragging.value = null
}
onMounted(loadLookups)
</script>
