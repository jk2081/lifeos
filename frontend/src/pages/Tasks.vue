<template>
  <ListView ref="list" title="Tasks" noun="tasks" :filters="FILTERS" :columns="columns" :fetch="fetch" :row-ref="(r) => 'task:' + r.name"
    :group-by="view === 'list' ? dueGroup : null" :watch-keys="['view']" :custom="view === 'board'" :sorts="SORTS" :no-head="view !== 'table'" default-sort="due date, then priority"
    :empty-title="view === 'loops' ? 'No open loops.' : 'No tasks here.'"
    :empty-hint="view === 'loops' ? 'Open tasks older than 14 days with no due date gather here.' : 'Type a title in the box above and press Enter, or accept a task proposal in the Inbox.'"
    @loaded="(res) => (today = res.today)">
    <template #sub>{{ view === 'loops' ? 'Open loops: open tasks older than 14 days with no due date. Give each a date, carry it, or drop it.' : `${store.space} · by due date, then priority` }}</template>
    <template #actions>
      <div class="chips only-desktop">
        <button v-for="v in VIEWS" :key="v.key" class="ch" :class="{ on: view === v.key }" type="button" :data-view="v.key" @click="setView(v.key)">{{ v.label }}</button>
      </div>
    </template>
    <template #above>
      <div v-if="canWrite()" style="display: flex; gap: 8px">
        <input v-model="quick" class="inp" style="flex: 1" placeholder="Add a task and press Enter. A date word such as tomorrow or fri sets the due date."
          aria-label="Quick add" @keydown.enter="add" />
      </div>
      <div class="chips only-phone">
        <button v-for="v in VIEWS" :key="v.key" class="ch" :class="{ on: view === v.key }" type="button" @click="setView(v.key)">{{ v.label }}</button>
      </div>
    </template>

    <template #cell-check="{ row }"><input class="ck" type="checkbox" :checked="row.status === 'Done'" :disabled="!canWrite()" :aria-label="'Done: ' + row.title" @change="toggle(row)" /></template>
    <template #cell-title="{ row }">
      <div class="ttl" :style="struck(row)">{{ row.title }}</div>
      <div v-if="view !== 'table'" class="mt">{{ taskMeta(row, today, { withDue: true }) }}</div>
    </template>
    <template #cell-pill="{ row }"><span v-if="taskPill(row, today)" class="pl" :class="taskPill(row, today).cls">{{ taskPill(row, today).text }}</span></template>
    <template #cell-due_date="{ row }"><span :style="row.due_date && row.due_date < today && OPEN.includes(row.status) ? 'color: var(--r-ink)' : ''">{{ short(row.due_date, true) }}</span></template>
    <template #stack="{ row }">
      <div style="display: flex; gap: 10px; align-items: flex-start">
        <input class="ck" type="checkbox" :checked="row.status === 'Done'" :disabled="!canWrite()" :aria-label="'Done: ' + row.title" @change="toggle(row)" />
        <div style="flex: 1; min-width: 0"><div class="ttl" :style="struck(row)">{{ row.title }}</div><div class="mt">{{ taskMeta(row, today, { withDue: true }) }}</div></div>
        <span v-if="taskPill(row, today)" class="pl" :class="taskPill(row, today).cls">{{ taskPill(row, today).shortText || taskPill(row, today).text }}</span>
      </div>
    </template>

    <template #body="{ rows, loaded }">
      <div class="board">
        <div v-for="col in BOARD" :key="col" class="col" @dragover.prevent @drop="drop(col)">
          <h2 class="sh">{{ col }} <RouterLink class="num" style="margin-left: 0" :to="{ query: { ...route.query, view: 'table', status: col, done: undefined, open: undefined } }">{{ boardCounts[col] ?? '' }}</RouterLink></h2>
          <div v-for="t in rows.filter((r) => r.status === col)" :key="t.name" class="cd card" :class="{ on: current && current.ref === 'task:' + t.name }" draggable="true" :data-ref="'task:' + t.name"
            tabindex="0" @dragstart="dragging = t" @click="openRef('task:' + t.name)" @keydown.enter.self="openRef('task:' + t.name)">
            <div class="ttl" style="font-weight: 500">{{ t.title }}</div>
            <div class="mt">{{ taskMeta(t, today, { withDue: true }) }}</div>
            <div class="chips" style="margin-top: 6px" @click.stop>
              <span v-if="t.priority" class="pl n">{{ t.priority }}</span>
              <select class="inp mini" :value="t.status" aria-label="Move to" :disabled="!canWrite()" @change="move(t, $event.target.value)">
                <option v-for="s in BOARD" :key="s">{{ s }}</option></select>
            </div>
          </div>
          <div v-if="loaded && !rows.some((r) => r.status === col)" class="mt" style="padding: 8px 2px">Nothing {{ col.toLowerCase() }}.</div>
        </div>
      </div>
    </template>
  </ListView>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ListView from '@/components/ListView.vue'
import { api, optimistic, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short, startOfWeek, addDays } from '@/lib/dates'
import { OPEN, PRIORITIES, taskMeta, taskPill } from '@/lib/tasks'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { current, openRef } from '@/lib/pane'

const VIEWS = [{ key: 'list', label: 'List' }, { key: 'board', label: 'Board' }, { key: 'table', label: 'Table' }, { key: 'loops', label: 'Open loops' }]
const BOARD = ['Open', 'Doing', 'Waiting', 'Done']
const route = useRoute()
const router = useRouter()
const list = ref(null)
const today = ref(store.today)
const quick = ref('')
const dragging = ref(null)
const boardCounts = ref({})
// the view is in the URL; with none there, the last one used
const view = computed(() => (VIEWS.some((v) => v.key === route.query.view) ? route.query.view : localStorage.getItem('lifeos-task-view') || 'list'))

const FILTERS = computed(() => [
  { key: 'area', label: 'Area', all: 'All areas', options: [...areaOptions(), { value: 'none', label: 'No area' }] },
  { key: 'project', label: 'Project', all: 'All projects', options: lookups.projects.map((p) => ({ value: p.name, label: p.title })) },
  ...(lookups.tags.length ? [{ key: 'tag', label: 'Tag', all: 'All tags', options: lookups.tags.map((t) => ({ value: t.name, label: '#' + t.tag_name })) }] : []),
  { key: 'priority', label: 'Priority', all: 'Any priority', options: [...PRIORITIES.map((p) => ({ value: p, label: p })), { value: 'none', label: 'No priority' }] },
  ...(lookups.goals.length ? [{ key: 'goal', label: 'Goal', all: 'Any goal', options: lookups.goals.map((g) => ({ value: g.name, label: g.title })) }] : []),
  { key: 'due', label: 'Due', all: 'Any due date', options: [{ value: 'overdue', label: 'Overdue' }, { value: 'today', label: 'Today' },
    { value: 'today,overdue', label: 'Today and overdue' }, { value: 'week', label: 'This week' }, { value: 'none', label: 'No date' }] },
  { key: 'status', label: 'Status', all: 'Any open status', quiet: view.value === 'board',
    options: ['Open', 'Doing', 'Waiting', 'Done', 'Dropped', 'Carried'].map((s) => ({ value: s, label: s })) },
  ...(view.value === 'loops' || view.value === 'board' ? [] : [{ key: 'done', label: 'Show done', type: 'check' }]),
  { key: 'archived', label: 'Include archived', type: 'check', quiet: true },
  { key: 'completed_from', label: 'Completed from', type: 'date', quiet: true }, { key: 'completed_to', label: 'Completed to', type: 'date', quiet: true },
])
const columns = computed(() => (view.value === 'table'
  ? [{ key: 'check', label: '', width: '22px' }, { key: 'title', label: 'Task', width: 'minmax(180px, 2fr)', sort: 'title' }, { key: 'status', label: 'Status', sort: 'status' },
    { key: 'priority', label: 'Priority', width: '70px', sort: 'priority' }, { key: 'due_date', label: 'Due', sort: 'due_date', nowrap: true },
    { key: 'area_name', label: 'Area' }, { key: 'project_title', label: 'Project' }, { key: 'goal_title', label: 'Goal' }]
  : [{ key: 'check', width: '22px' }, { key: 'title' }, { key: 'pill', width: 'max-content', align: 'right' }]))

const SORTS = [{ sort: 'due_date', label: 'Due date' }, { sort: 'priority', label: 'Priority' }, { sort: 'title', label: 'Title' }, { sort: 'status', label: 'Status' },
  { sort: 'creation', label: 'Created' }, { sort: 'completed_on', label: 'Completed' }]
const struck = (t) => (t.status === 'Done' || t.status === 'Dropped' ? 'text-decoration: line-through; color: var(--mut)' : '')
function dueGroup(t) {
  if (route.query.sort) return null
  const d = t.due_date
  if (!OPEN.includes(t.status)) return 'Closed'
  if (!d) return 'No date'
  if (d < today.value) return 'Overdue'
  if (d === today.value) return 'Today'
  return d <= addDays(startOfWeek(today.value), 6) ? 'This week' : 'Later'
}

function args(f) {
  return { space: store.space, area: f.area || undefined, project: f.project || undefined, tag: f.tag || undefined, priority: f.priority || undefined,
    goal: f.goal || undefined, due: f.due || undefined, include_archived: f.archived ? 1 : 0, completed_from: f.completed_from || undefined,
    completed_to: f.completed_to || undefined }
}
async function fetch({ filters: f, sort, dir, start, page_length }) {
  const base = args(f)
  let res
  if (view.value === 'board') {
    // the board shows the four columns; each column's count is the number of tasks with that status under the same filters
    res = await api('tasks.list', { ...base, status: f.status || 'all', start, page_length: 100 })
    res.tasks = res.tasks.filter((t) => BOARD.includes(t.status))
    const counts = await Promise.all(BOARD.map((s) => api('tasks.list', { ...base, status: s, page_length: 1 })))
    boardCounts.value = Object.fromEntries(BOARD.map((s, i) => [s, counts[i].total]))
    res.total = res.tasks.length
  } else {
    res = await api('tasks.list', { ...base, status: f.status || 'open', done: f.done && view.value !== 'loops' ? 1 : 0, loops: view.value === 'loops' ? 1 : 0,
      sort: sort || (view.value === 'loops' ? 'creation' : undefined), dir: dir || undefined, start, page_length })
  }
  return { rows: res.tasks, total: res.total, today: res.today }
}
function setView(v) {
  if (v !== 'loops') localStorage.setItem('lifeos-task-view', v)
  router.push({ query: { ...route.query, view: v, sort: undefined, dir: undefined } })
}
async function add() {
  const text = quick.value.trim()
  if (!text) return
  quick.value = ''
  const q = route.query
  const area = q.area && q.area !== 'none' ? q.area : undefined
  const t = await tryCall(() => api('tasks.quick_add', { text, space: store.space, area, project: q.project || undefined, goal: q.goal || undefined }))
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
  if (status === t.status) return
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
<style scoped>
.board { display: grid; grid-template-columns: repeat(4, minmax(220px, 1fr)); gap: 16px; align-items: start; }
.col { background: var(--soft); border: 1px solid var(--line); border-radius: 10px; padding: 12px; min-height: 120px; display: flex; flex-direction: column; gap: 8px; }
.card { cursor: grab; padding: 10px 12px; }
.card.on { border-color: var(--accent); background: var(--b-bg); }
.inp.mini { height: 26px; font-size: 12.5px; padding: 0 6px; border-radius: 6px; }
@media (max-width: 800px) { .board { grid-template-columns: 1fr; } .inp.mini { height: 36px; } }
</style>
