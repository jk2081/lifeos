<template>
  <PageHead title="Tasks" :sub="headSub">
    <div class="chips only-desktop">
      <button v-for="v in VIEWS" :key="v.key" class="ch" :class="{ on: view === v.key }" type="button" @click="setView(v.key)">{{ v.label }}</button>
    </div>
  </PageHead>
  <div class="bd">
    <div v-if="canWrite()" style="display: flex; gap: 8px">
      <input v-model="quick" class="inp" style="flex: 1" placeholder="Add a task and press Enter. A date word such as tomorrow or fri sets the due date."
        aria-label="Quick add" @keydown.enter="add" />
    </div>
    <div class="chips">
      <div class="chips only-phone" style="width: 100%">
        <button v-for="v in VIEWS" :key="v.key" class="ch" :class="{ on: view === v.key }" type="button" @click="setView(v.key)">{{ v.label }}</button>
      </div>
      <select v-model="f.area" class="inp" aria-label="Area" @change="load()"><option value="">All areas</option>
        <option v-for="o in areaOptions()" :key="o.value" :value="o.value">{{ o.label }}</option></select>
      <select v-model="f.project" class="inp" aria-label="Project" @change="load()"><option value="">All projects</option>
        <option v-for="p in lookups.projects" :key="p.name" :value="p.name">{{ p.title }}</option></select>
      <select v-if="lookups.tags.length" v-model="f.tag" class="inp" aria-label="Tag" @change="load()"><option value="">All tags</option>
        <option v-for="t in lookups.tags" :key="t.name" :value="t.name">#{{ t.tag_name }}</option></select>
      <select v-model="f.priority" class="inp" aria-label="Priority" @change="load()"><option value="">Any priority</option>
        <option v-for="p in PRIORITIES" :key="p" :value="p">{{ p }}</option><option value="none">No priority</option></select>
      <select v-if="lookups.goals.length" v-model="f.goal" class="inp" aria-label="Goal" @change="load()"><option value="">Any goal</option>
        <option v-for="g in lookups.goals" :key="g.name" :value="g.name">{{ g.title }}</option></select>
      <label v-if="view !== 'loops'" class="mt" style="display: flex; gap: 6px; align-items: center"><input v-model="showDone" type="checkbox" class="ck" style="margin: 0" @change="load()" /> Show done</label>
    </div>

    <template v-if="view === 'list' || view === 'loops'">
      <p v-if="view === 'loops'" class="mt" style="margin: 0">Open loops: open tasks older than 14 days with no due date. Give each a date, carry it, or drop it.</p>
      <section v-for="g in groups" :key="g.label">
        <h2 class="sh">{{ g.label }} <span class="mt" style="font-weight: 400">{{ g.tasks.length }}</span></h2>
        <div class="cd list">
          <TaskRow v-for="t in g.tasks" :key="t.name" :task="t" :today="today" :with-due="g.label !== 'Today'" :readonly="!canWrite()" @toggle="toggle" @open="openTask = t.name" />
        </div>
      </section>
      <div v-if="loaded && !tasks.length" class="cd">
        <Empty v-if="view === 'loops'" title="No open loops." hint="Open tasks older than 14 days with no due date gather here." />
        <Empty v-else title="No tasks here." hint="Type a title in the box above and press Enter, or accept a task proposal in the Inbox." />
      </div>
    </template>

    <div v-else-if="view === 'board'" class="board">
      <div v-for="col in BOARD" :key="col" class="col" @dragover.prevent @drop="drop(col)">
        <h2 class="sh">{{ col }} <span class="mt" style="font-weight: 400">{{ byStatus(col).length }}</span></h2>
        <div v-for="t in byStatus(col)" :key="t.name" class="cd card" draggable="true" @dragstart="dragging = t" @click="openTask = t.name">
          <div class="ttl" style="font-weight: 500">{{ t.title }}</div>
          <div class="mt">{{ taskMeta(t, today, { withDue: true }) }}</div>
          <div class="chips" style="margin-top: 6px" @click.stop>
            <span v-if="t.priority" class="pl n">{{ t.priority }}</span>
            <select class="inp mini" :value="t.status" aria-label="Move to" :disabled="!canWrite()" @change="move(t, $event.target.value)">
              <option v-for="s in BOARD" :key="s">{{ s }}</option></select>
          </div>
        </div>
        <div v-if="loaded && !byStatus(col).length" class="mt" style="padding: 8px 2px">Nothing {{ col.toLowerCase() }}.</div>
      </div>
    </div>

    <div v-else class="tblwrap"><div class="tblscroll">
      <table class="tbl">
        <thead><tr><th style="width: 28px"></th><th>Task</th><th>Status</th><th>Priority</th><th>Due</th><th>Area</th><th>Project</th><th>Goal</th></tr></thead>
        <tbody>
          <tr v-for="t in tasks" :key="t.name" style="cursor: pointer" @click="openTask = t.name">
            <td @click.stop><input class="ck" type="checkbox" :checked="t.status === 'Done'" :disabled="!canWrite()" :aria-label="'Done: ' + t.title" @change="toggle(t)" /></td>
            <td style="font-weight: 500; min-width: 220px">{{ t.title }}</td><td>{{ t.status }}</td><td>{{ t.priority }}</td>
            <td style="white-space: nowrap" :style="t.due_date && t.due_date < today && OPEN.includes(t.status) ? 'color: var(--r-ink)' : ''">{{ short(t.due_date, true) }}</td>
            <td>{{ t.area_name }}</td><td>{{ t.project_title }}</td><td>{{ t.goal_title }}</td>
          </tr>
        </tbody>
      </table></div>
      <Empty v-if="loaded && !tasks.length" style="padding: 18px 16px" title="No tasks here." hint="Type a title in the box above and press Enter." />
    </div>
    <div v-if="tasks.length < total"><button class="bt s" type="button" @click="load(true)">Show more ({{ total - tasks.length }} left)</button></div>
  </div>
  <TaskPanel v-if="openTask" :name="openTask" @close="closePanel" @changed="load()" />
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import TaskPanel from '@/components/TaskPanel.vue'
import { api, optimistic, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { OPEN, PRIORITIES, groupByDue, taskMeta } from '@/lib/tasks'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'

const VIEWS = [{ key: 'list', label: 'List' }, { key: 'board', label: 'Board' }, { key: 'table', label: 'Table' }, { key: 'loops', label: 'Open loops' }]
const BOARD = ['Open', 'Doing', 'Waiting', 'Done']
const route = useRoute()
const router = useRouter()
const view = ref(route.query.view || localStorage.getItem('lifeos-task-view') || 'list')
const f = reactive({ area: route.query.area || '', project: route.query.project || '', tag: '', priority: '', goal: route.query.goal || '' })
const tasks = ref([])
const total = ref(0)
const today = ref(store.today)
const loaded = ref(false)
const showDone = ref(false)
const quick = ref('')
const openTask = ref(route.query.open || null)
const dragging = ref(null)

const headSub = computed(() => `${total.value} ${view.value === 'loops' ? 'open loops' : showDone.value ? 'tasks' : 'open'} in ${store.space}`)
const groups = computed(() => (view.value === 'loops' ? (tasks.value.length ? [{ label: 'Open loops', tasks: tasks.value }] : []) : groupByDue(tasks.value, today.value)))
const byStatus = (s) => tasks.value.filter((t) => t.status === s)

async function load(append = false) {
  const args = { space: store.space, start: append ? tasks.value.length : 0, page_length: 100, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) }
  let res
  if (view.value === 'loops') res = await tryCall(() => api('tasks.open_loops', { space: store.space, start: args.start, page_length: 100 }))
  else res = await tryCall(() => api('tasks.list', { ...args, status: showDone.value || view.value === 'board' ? 'all' : 'open' }))
  if (!res) return
  let rows = res.tasks
  if (view.value === 'board') rows = rows.filter((t) => BOARD.includes(t.status) && (t.status !== 'Done' || !t.is_archived))
  tasks.value = append ? [...tasks.value, ...rows] : rows
  total.value = res.total
  today.value = res.today
  loaded.value = true
}
function setView(v) {
  view.value = v
  if (v !== 'loops') localStorage.setItem('lifeos-task-view', v)
  loaded.value = false
  load()
}
async function add() {
  const text = quick.value.trim()
  if (!text) return
  quick.value = ''
  const t = await tryCall(() => api('tasks.quick_add', { text, space: store.space, area: f.area || undefined, project: f.project || undefined, goal: f.goal || undefined }))
  if (t) load()
  else quick.value = text
}
function toggle(t) {
  const before = t.status
  const next = before === 'Done' ? 'Open' : 'Done'
  optimistic(() => (t.status = next), () => (t.status = before), () => api('tasks.set_status', { task: t.name, status: next }))
    .then(() => { if (!showDone.value && view.value !== 'board') setTimeout(() => load(), 500) }).catch(() => {})
}
function move(t, status) {
  if (status === t.status) return
  if (status === 'Waiting' && !t.waiting_on) {
    openTask.value = t.name
    return
  }
  const before = t.status
  optimistic(() => (t.status = status), () => (t.status = before), () => api('tasks.set_status', { task: t.name, status })).catch(() => {})
}
function drop(col) {
  if (dragging.value && canWrite()) move(dragging.value, col)
  dragging.value = null
}
function closePanel() {
  openTask.value = null
  if (route.query.open) router.replace({ query: { ...route.query, open: undefined } })
}
const onAdded = () => load()
onMounted(() => {
  loadLookups()
  load()
  window.addEventListener('lifeos-task-added', onAdded)
})
onUnmounted(() => window.removeEventListener('lifeos-task-added', onAdded))
</script>
<style scoped>
.board { display: grid; grid-template-columns: repeat(4, minmax(220px, 1fr)); gap: 16px; align-items: start; }
.col { background: var(--soft); border: 1px solid var(--line); border-radius: 10px; padding: 12px; min-height: 120px; display: flex; flex-direction: column; gap: 8px; }
.card { cursor: grab; padding: 10px 12px; }
.inp.mini { height: 26px; font-size: 12.5px; padding: 0 6px; border-radius: 6px; }
@media (max-width: 800px) { .board { grid-template-columns: 1fr; } .inp.mini { height: 36px; } }
</style>
