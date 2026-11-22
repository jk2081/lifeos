<template>
  <template v-if="d">
    <PageHead :title="g.title" :crumb="{ to: '/goals', label: 'Goals', here: cyc ? cyc.title : g.horizon }" :sub="sub">
      <Badge :theme="themeOf(g)" :label="g.is_archived ? `${g.status}, archived` : g.status === 'On Hold' ? 'On hold' : g.status" data-goal-status />
      <Button v-if="cyc" label="Open grid" data-open-grid :route="`/goals/cycles?cycle=${cyc.name}`" />
      <Button v-if="writable && !g.is_archived" label="Edit" icon-left="lucide-pencil" data-goal-edit @click="editOpen = true" />
      <template v-if="writable && g.horizon !== '12 weeks'">
        <Button v-if="!g.is_archived" label="New note" @click="noteOpen = true" />
        <Button v-if="g.is_archived" variant="solid" label="Restore" data-goal-restore @click="setStatus('Active')" />
        <template v-else-if="g.horizon === 'Long term' && g.outcome === 'In Progress'">
          <Button :label="g.on_hold ? 'Resume' : 'Put on hold'" data-goal-hold @click="setStatus(g.on_hold ? 'Active' : 'On Hold')" />
          <Button label="Drop" @click="askComplete('Dropped')" />
          <Button variant="solid" label="Complete" data-goal-complete @click="askComplete('Done')" />
        </template>
        <Button v-else-if="g.outcome !== 'In Progress'" label="Reopen" @click="setStatus('Active')" />
      </template>
    </PageHead>
    <!-- the goal's tabs (tab=): Overview, then each kind of record filed under it as the main screen's list with the goal fixed -->
    <TabBar class="flex-none" inset :tabs="tabs" :model-value="tab.current.value" label="Goal sections" data-page-tabs @update:model-value="setTab" />
    <div v-show="tab.current.value === 'overview'" class="page-body" data-tab-panel="overview">
      <div class="cols">
        <div class="half">
          <Card class="flex flex-col gap-3" data-goal-overview>
            <GoalMeasure :g="g" :readings="d.readings" :suggested="d.suggested" :space="d.space" :writable="writable && !g.is_archived" @changed="changed" />
            <div class="form-grid">
              <FormControl v-if="g.horizon !== '12 weeks'" v-model="g.horizon" type="select" label="Horizon" :options="g.horizon === 'Long term' ? ['Long term', 'Year', 'Month'] : ['Year', 'Month']" :disabled="!writable" data-goal-horizon
                @update:model-value="saveField('horizon')" />
              <DatePicker v-if="g.horizon !== '12 weeks'" v-model="g.target_date" format="D MMM YYYY" label="Target date" clearable :disabled="!writable" @change="saveField('target_date')" />
              <div class="space-y-1.5"><div class="text-sm text-ink-gray-6">Progress</div><div class="flex h-8 items-center gap-2" data-goal-figure>
                <div class="min-w-0 flex-1"><Progress size="sm" :value="j.tasks_counted ? Math.round((100 * j.tasks_done) / j.tasks_counted) : 0" /></div>
                <NumLink class="text-sm" :to="{ path: '/goals/tasks', query: { goal: g.name, status: 'all', view: 'list', ...arch } }" data-door="goal-tasks">{{ j.tasks_done }} of {{ j.tasks_counted }} tasks done</NumLink></div>
                <div v-if="j.this_week" class="text-sm text-ink-gray-6" data-goal-week-ticks>Actions this week: {{ j.this_week.done }} of {{ j.this_week.planned }} ticks</div></div>
            </div>
            <!-- what this goal serves, and what serves it (a goal can point to the longer goal it serves) -->
            <div class="flex flex-wrap items-center gap-2" data-goal-serves>
              <span class="text-sm text-ink-gray-6">Serves</span>
              <Pick :model-value="g.serves || null" :options="servesOptions" placeholder="Choose a longer goal" :disabled="!writable" @update:model-value="(v) => saveServes(v)" />
              <NumLink v-if="g.serves" :to="{ path: `/goals/${g.serves}` }" class="text-sm">Open {{ g.serves_title }}</NumLink>
            </div>
            <div v-if="d.serves" class="flex items-center gap-2" data-goal-serves-progress>
              <div class="w-24 shrink-0"><Progress size="sm" :value="Math.round(d.serves.progress.percent || 0)" /></div>
              <span class="min-w-0 truncate text-sm text-ink-gray-6">{{ d.serves.title }}: {{ d.serves.progress.label }}</span>
            </div>
          </Card>
          <section v-if="d.served_by.length" data-goal-served-by>
            <SectionHead :count="d.served_by.length">Served by</SectionHead>
            <Card flush><Row v-for="s in d.served_by" :key="s.name" :pane="'goal:' + s.name" :label="s.title">
              <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ s.title }}</div>
                <div class="text-sm text-ink-gray-6" data-served-by-line>{{ [s.horizon === '12 weeks' ? s.cycle_title || '12 weeks' : s.horizon + ' goal', s.progress.label].filter(Boolean).join(' · ') }}</div></div>
              <div class="w-20 shrink-0 self-center max-md:w-12"><Progress size="sm" :value="Math.round(s.progress.percent || 0)" /></div>
              <Badge :theme="themeOf(s)" :label="s.status" /></Row></Card>
          </section>
          <section v-if="cyc" data-goal-actions><SectionHead>Actions</SectionHead>
            <Card flush><Row v-for="a in j.goal.actions" :key="a.name">
              <div class="min-w-0 flex-1"><div class="break-words text-base-medium" :class="a.status !== 'Open' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ a.title }}</div>
                <div class="text-sm text-ink-gray-6" data-action-line>{{ a.per_week }} a week<template v-if="j.this_week && a.status === 'Open'"> · {{ a.ticks[j.this_week.week] || 0 }} of {{ a.per_week }} this week</template> · {{ Object.values(a.ticks).reduce((x, y) => x + y, 0) }} ticks so far</div></div>
              <Badge v-if="a.status !== 'Open'" :theme="a.status === 'Done' ? 'green' : 'gray'" :label="a.status" /></Row>
              <Empty v-if="!j.goal.actions.length" title="No actions." hint="Use Edit to add the weekly actions." /></Card>
          </section>
          <section v-if="g.result_note"><SectionHead>Result</SectionHead><Card>{{ g.result_note }}</Card></section>
        </div>
        <div class="half">
          <section>
            <SectionHead :count="d.tabs.tasks" :to="{ query: { tab: 'tasks' } }" door="goal-overview-tasks">Open tasks</SectionHead>
            <Card flush>
              <TaskRow v-for="t in openTasks.slice(0, 6)" :key="t.name" :task="t" :today="store.today" with-due :readonly="!writable" @toggle="toggle" />
              <Empty v-if="!openTasks.length" title="No open tasks." hint="Add the next step below." />
              <Row v-if="writable && !g.is_archived && g.outcome === 'In Progress'"><TextInput v-model="quick" class="flex-1" placeholder="Add a task under this goal" aria-label="Add a task under this goal"
                data-goal-quick @keydown.enter="addTask" /></Row>
            </Card>
          </section>
          <section><SectionHead>Notes</SectionHead>
            <Card><MdField :model-value="g.notes_md || ''" :save="saveNotes" :space="d.space" :readonly="!writable" doctype="Life Goal" :docname="g.name" label="Notes on this goal"
              placeholder="Notes on this goal" /></Card>
          </section>
          <section v-if="cyc && j.history?.length"><SectionHead>History across cycles</SectionHead>
            <Card flush><Row v-for="h in j.history" :key="h.name" class="!items-center">
              <div class="min-w-0 flex-1"><RouterLink class="break-words text-base-medium hover:underline focus-visible:focus-ring" :class="h.name === g.name ? 'text-ink-gray-9' : 'text-ink-blue-8'" :to="`/goals/${h.name}`">{{ h.cycle_title }}</RouterLink>
                <div class="text-sm text-ink-gray-6">{{ h.cycle_status }}{{ h.result_note ? ' · ' + h.result_note : '' }}</div></div>
              <div class="w-24 shrink-0 max-md:w-12"><Progress size="sm" :value="Math.round(h.score)" /></div><span class="w-10 text-right tabular-nums">{{ Math.round(h.score) }}%</span>
              <Badge :label="h.outcome" /></Row></Card>
          </section>
        </div>
      </div>
    </div>
    <div :key="g.name" class="contents">
      <div v-if="tab.shown('tasks')" v-show="tab.current.value === 'tasks'" class="contents" data-tab-panel="tasks"><Tasks :embed="embed('tasks')" /></div>
      <div v-if="tab.shown('notes')" v-show="tab.current.value === 'notes'" class="contents" data-tab-panel="notes"><NotesList :embed="embed('notes')" collection="all" /></div>
      <div v-if="tab.shown('captures')" v-show="tab.current.value === 'captures'" class="contents" data-tab-panel="captures"><Sources :embed="embed('captures')" /></div>
      <div v-if="tab.shown('links')" v-show="tab.current.value === 'links'" class="page-body" data-tab-panel="links"><Backlinks tab doctype="Life Goal" :name="g.name" :reload="stamp" /></div>
    </div>
    <Dialog v-model:open="confirmOpen" :title="confirmStatus === 'Done' ? 'Complete this goal?' : 'Drop this goal?'" size="md"
      :actions="[{ label: 'Cancel', onClick: ({ close }) => close() },
        { label: confirmStatus === 'Done' ? 'Complete and archive' : 'Drop and archive', variant: 'solid', onClick: () => setStatus(confirmStatus) }]">
      <p class="text-base text-ink-gray-8">The goal and <b class="font-semibold">{{ d.record_count }} record{{ d.record_count === 1 ? '' : 's' }}</b> filed under it (tasks, notes, captures) move to the Archive.
        Nothing is deleted, and you can restore it from the Archive.</p>
    </Dialog>
    <GoalEditDialog v-if="writable" v-model="editOpen" :goal="g" :weekly-actions="j.goal?.actions || []" :space="d.space" @saved="changed" />
    <NewRecord v-model="noteOpen" title="New note" action="Create note" :fields="[{ name: 'title', label: 'Title', required: true }]" :save="createNote" />
  </template>
  <div v-else-if="missing" class="page-body"><Card><Empty title="This goal was not found." hint="It may belong to another space." /></Card></div>
</template>
<script setup>
// A goal's page (UX fixes, set 6): what a project page and a goal page each did. Every goal shows what it serves and what
// serves it; an open-ended goal (a project before set 6) is put on hold, completed or dropped here, and completing it
// archives it with what is filed under it. The tabs are the main screens' lists with this goal fixed.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, DatePicker, Dialog, FormControl, Progress, TextInput, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import Pick from '@/components/Pick.vue'
import MdField from '@/components/MdField.vue'
import TaskRow from '@/components/TaskRow.vue'
import TabBar from '@/components/TabBar.vue'
import Tasks from '@/pages/Tasks.vue'
import Sources from '@/pages/Sources.vue'
import NotesList from '@/components/lists/NotesList.vue'
import Backlinks from '@/components/Backlinks.vue'
import NewRecord from '@/components/NewRecord.vue'
import GoalMeasure from '@/components/goals/GoalMeasure.vue'
import GoalEditDialog from '@/components/goals/GoalEditDialog.vue'
import { api, db, optimistic, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { askScope } from '@/lib/ask'
import { loadLookups, lookups, parentOptions } from '@/lib/lookups'
import { onRecordChanged } from '@/lib/pane'
import { useUrlTab } from '@/lib/tabs'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()
const stamp = ref(0)
const d = ref(null) // goals.get
const j = ref(null) // journal.goal: tasks, actions and history across cycles
const missing = ref(false)
const quick = ref('')
const confirmOpen = ref(false)
const confirmStatus = ref('Done')
const noteOpen = ref(false)
const editOpen = ref(false)
const g = computed(() => d.value.goal)
// the goal's cycle: goals.get names it, journal.goal carries its grid row
const cyc = computed(() => d.value.cycle || j.value?.cycle || null)
const writable = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write' && !store.isAgent)
const arch = computed(() => (g.value.is_archived ? { archived: '1' } : {}))
const themeOf = (x) => (x.is_archived ? 'gray' : { Active: 'green', 'On Hold': 'amber', Done: 'blue', Someday: 'gray' }[x.status] || 'gray')
const sub = computed(() => [g.value.area_name, g.value.horizon === '12 weeks' ? '12 Week Year goal' : g.value.horizon + ' goal', g.value.target_date && 'by ' + short(g.value.target_date, true),
  g.value.serves_title && 'serves ' + g.value.serves_title, d.value.served_by.length && `served by ${d.value.served_by.length}`].filter(Boolean).join(' · '))
// a goal can serve any other goal in progress of the space, never itself
const servesOptions = computed(() => [{ label: 'None', value: '' },
  ...parentOptions(g.value),
  ...(g.value.serves && !(lookups.goals || []).some((x) => x.name === g.value.serves) ? [{ label: g.value.serves_title || g.value.serves, value: g.value.serves }] : [])])
// The tabs. Each list tab is the main screen's list with this goal fixed, its view remembered per tab across goals.
const TABS = [['overview', 'Overview'], ['tasks', 'Tasks'], ['notes', 'Notes'], ['captures', 'Captures'], ['links', 'Links']]
const NOUNS = { tasks: 'open tasks', notes: 'notes', captures: 'captures', links: 'linked records' }
const tabs = computed(() => TABS.map(([value, label]) => ({ value, label, count: value === 'overview' ? undefined : d.value?.tabs?.[value], noun: NOUNS[value] })))
const tab = useUrlTab('tab', tabs)
function setTab(v) {
  if (v === tab.current.value) return
  router.push({ query: { tab: v === 'overview' ? undefined : v, open: route.query.open, ptab: route.query.ptab } })
}
const openTasks = computed(() => (j.value?.tasks || []).filter((t) => ['Open', 'Doing', 'Waiting'].includes(t.status) && !t.is_archived))
function embed(t) {
  const path = route.path
  return { screen: 'goal', space: d.value.space, fixed: { goal: g.value.name, ...(g.value.is_archived ? { archived: '1' } : {}) }, writable: writable.value && !g.value.is_archived,
    active: (r) => r.path === path && (r.query.tab || 'overview') === t }
}
async function load() {
  try {
    ;[d.value, j.value] = await Promise.all([api('goals.get', { goal: props.id }), api('journal.goal', { goal: props.id })])
    stamp.value++
  } catch (e) {
    missing.value = true
  }
}
function askComplete(status) {
  confirmStatus.value = status
  confirmOpen.value = true
}
async function setStatus(status) {
  const res = await tryCall(() => api('goals.set_status', { goal: g.value.name, status }))
  confirmOpen.value = false
  if (!res) return
  if (res.is_archived) toast.success(`Archived with ${res.archived_records} record${res.archived_records === 1 ? '' : 's'}. Restore it from the Archive.`)
  else toast.success(`The goal is ${status === 'On Hold' ? 'on hold' : status === 'Active' ? 'in progress' : status.toLowerCase()}.`)
  loadLookups(true)
  load()
}
async function saveField(field) {
  await tryCall(() => api('goals.update', { goal: g.value.name, values: { [field]: g.value[field] || null } }))
}
async function saveServes(v) {
  if (await tryCall(() => api('goals.update', { goal: g.value.name, values: { serves: v || null } }), v ? 'Linked to the goal it serves' : 'No longer serves a goal')) load()
}
async function saveNotes(v) {
  await tryCall(() => api('goals.update', { goal: g.value.name, values: { notes_md: v } }))
}
function toggle(t) {
  const next = t.status === 'Done' ? 'Open' : 'Done'
  optimistic(() => {}, () => {}, () => api('tasks.set_status', { task: t.name, status: next })).then(load).catch(() => {})
}
async function addTask() {
  const text = quick.value.trim()
  if (!text) return
  quick.value = ''
  if (await tryCall(() => api('tasks.quick_add', { text, space: d.value.space, area: g.value.area || undefined, goal: g.value.name }))) load()
  else quick.value = text
}
async function createNote(v) {
  const note = await db.insert({ doctype: 'Life Note', space: d.value.space, area: g.value.area, goal: g.value.name, title: v.title, content_md: '' })
  router.push(`/library/${note.name}?edit=1`)
}
function changed() {
  load()
  loadLookups(true)
}
onRecordChanged(load)
onMounted(() => { load(); loadLookups() })
watch(() => props.id, load)
// Ask from a goal page: that goal and what is filed under it
askScope(() => (d.value ? { kind: 'goal', label: d.value.goal.title, doctype: 'Life Goal', name: d.value.goal.name } : { kind: 'space', label: 'Everything in this space' }))
</script>
