<template>
  <template v-if="d">
    <PageHead :title="d.area.area_name" :crumb="crumb">
      <template v-if="writable">
        <Button label="New project" @click="projectOpen = true" />
        <Button variant="solid" label="New note" @click="noteOpen = true" />
      </template>
    </PageHead>
    <!-- the area's tabs (tab=): Overview, then each kind of record as the full list for this area -->
    <TabBar class="flex-none" inset :tabs="tabs" :model-value="tab.current.value" label="Area sections" data-page-tabs @update:model-value="setTab" />
    <div v-show="tab.current.value === 'overview'" class="page-body" data-tab-panel="overview">
      <div v-if="d.sub_areas.length || d.area.parent" class="scroll-x">
        <TabButtons :model-value="d.area.name" :options="areaTabs" />
      </div>

      <section v-if="d.goals.length">
        <SectionHead :count="d.goals.length" :to="{ path: '/goals', query: { area: d.area.name } }" door="area-goals">Goals</SectionHead>
        <Card flush>
          <Row v-for="g in d.goals" :key="g.name" class="!items-center" :pane="'goal:' + g.name" :label="g.title">
            <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ g.title }}</div>
              <div class="text-sm text-ink-gray-6">{{ [g.goal_type, g.goal_type === '12 Week Year' ? g.cycle_title : g.target_date && 'by ' + short(g.target_date, true)].filter(Boolean).join(' · ') }}</div></div>
            <div class="flex w-48 items-center gap-2 max-md:w-28" data-goal-tasks>
              <template v-if="g.tasks_counted"><div class="min-w-0 flex-1"><Progress size="sm" :value="Math.round((100 * g.tasks_done) / g.tasks_counted)" /></div>
                <span class="whitespace-nowrap text-sm tabular-nums text-ink-gray-8">{{ g.tasks_done }} of {{ g.tasks_counted }}<span class="max-md:hidden"> tasks</span></span></template>
              <span v-else class="text-sm text-ink-gray-6">No tasks yet</span>
            </div>
            <span class="w-10 text-right tabular-nums text-ink-gray-8">{{ g.score === null || g.score === undefined ? '' : Math.round(g.score) + '%' }}</span>
          </Row>
        </Card>
      </section>

      <div class="cols">
        <div class="half">
          <section>
            <SectionHead :count="d.tabs.projects" :to="tabLink('projects')" door="area-overview-projects">Projects</SectionHead>
            <Card flush>
              <Row v-for="p in d.projects.slice(0, 5)" :key="p.name" class="!items-center" :pane="'project:' + p.name" :label="p.title">
                <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ p.title }}</div>
                  <div class="text-sm text-ink-gray-6">{{ p.status === 'On Hold' ? 'On hold · ' : '' }}{{ p.tasks_done }} of {{ p.tasks_total }} tasks done</div></div>
                <div class="w-24 max-md:w-16"><Progress size="sm" :value="p.tasks_total ? Math.round((100 * p.tasks_done) / p.tasks_total) : 0" /></div>
              </Row>
              <Empty v-if="!d.projects.length" title="No active projects." hint="A project is an outcome with an end. Add one with New project." />
            </Card>
          </section>
          <section>
            <SectionHead :count="d.tabs.tasks" :to="tabLink('tasks')" door="area-overview-tasks">Open tasks</SectionHead>
            <Card flush>
              <TaskRow v-for="t in d.tasks.slice(0, 5)" :key="t.name" :task="areaTask(t)" :today="store.today" with-due :readonly="!writable" @toggle="done" />
              <Empty v-if="!d.tasks.length" title="No open tasks." hint="Tasks filed under this area show here." />
              <Row v-if="writable"><TextInput v-model="quick" class="flex-1" placeholder="Add a task to this area" aria-label="Add a task" @keydown.enter="addTask" /></Row>
            </Card>
          </section>
        </div>
        <div class="half">
          <section>
            <SectionHead :count="d.tabs.timeline" :to="tabLink('timeline')" door="area-overview-timeline">Latest on the timeline</SectionHead>
            <Card flush>
              <IndexRow v-for="e in d.timeline.slice(0, 5)" :key="e.ref_name + e.kind" :row="e" show-kind />
              <Empty v-if="!d.timeline.length" title="Nothing captured yet." hint="Records filed under this area show here as they are captured." />
            </Card>
          </section>
          <section v-if="d.references.length">
            <SectionHead>References from other areas</SectionHead>
            <Card flush>
              <IndexRow v-for="n in d.references" :key="n.ref_name" :row="n" pill="Reference" pill-theme="blue">Lives in {{ n.area_name || 'another area' }} · also filed here</IndexRow>
            </Card>
          </section>
        </div>
      </div>
      <p class="text-sm text-ink-gray-6">Archived items are hidden here and listed under <RouterLink class="text-ink-blue-8 hover:underline" to="/archive">Archive</RouterLink>.</p>
    </div>
    <!-- each list loads when its tab is first opened and stays loaded while the page is open -->
    <div :key="d.area.name" class="contents">
      <div v-if="tab.shown('projects')" v-show="tab.current.value === 'projects'" class="contents" data-tab-panel="projects"><Projects :embed="embed('projects')" /></div>
      <div v-if="tab.shown('tasks')" v-show="tab.current.value === 'tasks'" class="contents" data-tab-panel="tasks"><Tasks :embed="embed('tasks')" /></div>
      <div v-if="tab.shown('notes')" v-show="tab.current.value === 'notes'" class="contents" data-tab-panel="notes"><NotesList :embed="embed('notes')" /></div>
      <div v-if="tab.shown('wiki')" v-show="tab.current.value === 'wiki'" class="contents" data-tab-panel="wiki"><NotesList :embed="embed('wiki')" collection="Wiki" /></div>
      <div v-if="tab.shown('documents')" v-show="tab.current.value === 'documents'" class="contents" data-tab-panel="documents"><Vault :embed="embed('documents')" /></div>
      <div v-if="tab.shown('chats')" v-show="tab.current.value === 'chats'" class="contents" data-tab-panel="chats"><Chats :embed="embed('chats')" /></div>
      <div v-if="tab.shown('timeline')" v-show="tab.current.value === 'timeline'" class="contents" data-tab-panel="timeline"><Timeline :embed="embed('timeline')" /></div>
    </div>
    <NewRecord v-model="projectOpen" title="New project" action="Add project" :fields="PROJECT_FIELDS" :save="createProject" @saved="load" />
    <NewRecord v-model="noteOpen" title="New note" action="Create note" :fields="[{ name: 'title', label: 'Title', required: true }]" :save="createNote" />
  </template>
  <div v-else-if="missing" class="page-body"><Card><Empty title="This area was not found." hint="It may belong to another space." /></Card></div>
</template>
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, Progress, TabButtons, TextInput } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import TabBar from '@/components/TabBar.vue'
import Tasks from '@/pages/Tasks.vue'
import Projects from '@/pages/Projects.vue'
import Vault from '@/pages/Vault.vue'
import Chats from '@/pages/Chats.vue'
import Timeline from '@/pages/Timeline.vue'
import NotesList from '@/components/lists/NotesList.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import IndexRow from '@/components/IndexRow.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db, optimistic, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { askScope } from '@/lib/ask'
import { short } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'
import { onRecordChanged } from '@/lib/pane'
import { useUrlTab } from '@/lib/tabs'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()
const d = ref(null)
const missing = ref(false)
const quick = ref('')
const projectOpen = ref(false)
const noteOpen = ref(false)
const parentSubs = ref([])
const PROJECT_FIELDS = [{ name: 'title', label: 'Title', required: true }, { name: 'outcome', label: 'Outcome', type: 'textarea', help: 'What will be true when this is done.' },
  { name: 'target_date', label: 'Target date', type: 'date' }]

const writable = computed(() => store.spaces.find((s) => s.name === d.value?.area.space)?.access === 'Write')
const crumb = computed(() => (d.value.area.parent
  ? { to: `/areas/${d.value.area.parent.name}`, label: d.value.area.parent.area_name, here: d.value.area.area_name }
  : { to: '/areas', label: 'Areas', here: d.value.area.area_name }))
const siblings = computed(() => (d.value.area.parent ? parentSubs.value : d.value.sub_areas))
// the sub-areas as a switch: All is the parent area, and each tab is a link to that area's own page
const areaTabs = computed(() => {
  const all = d.value.area.parent ? d.value.area.parent.name : d.value.area.name
  return [{ label: 'All', value: all, route: `/areas/${all}` }, ...siblings.value.map((s) => ({ label: s.area_name, value: s.name, route: `/areas/${s.name}` }))]
})
// The tabs. Each list tab is the main screen's list with this area fixed, its view remembered per tab across areas.
const TABS = [['overview', 'Overview'], ['projects', 'Projects'], ['tasks', 'Tasks'], ['notes', 'Notes'], ['wiki', 'Wiki'], ['documents', 'Documents'], ['chats', 'Chats'], ['timeline', 'Timeline']]
const NOUNS = { projects: 'projects', tasks: 'open tasks', notes: 'notes', wiki: 'wiki pages', documents: 'documents', chats: 'chats', timeline: 'records' }
const tabs = computed(() => TABS.map(([value, label]) => ({ value, label, count: value === 'overview' ? undefined : d.value?.tabs?.[value], noun: NOUNS[value] })))
const tab = useUrlTab('tab', tabs)
// A tab change keeps only the tab: the list query in the URL belongs to the tab that was open, and the list of the new
// tab puts back its own (ListView). The open record stays open.
function setTab(v) {
  if (v === tab.current.value) return
  router.push({ query: { tab: v === 'overview' ? undefined : v, open: route.query.open, ptab: route.query.ptab } })
}
const tabLink = (v) => ({ query: { tab: v } })
const here = () => route.path
function embed(t) {
  const path = here()
  return { screen: 'area', space: d.value.area.space, fixed: { area: d.value.area.name }, writable: writable.value,
    active: (r) => r.path === path && (r.query.tab || 'overview') === t }
}
// On an area page the area is known, so the row shows the project instead.
const areaTask = (t) => ({ ...t, area_name: t.project_title || 'No project', project_title: null, goal_title: null })

async function load() {
  try {
    d.value = await api('area.get', { area: props.id })
    missing.value = false
    if (d.value.area.parent) parentSubs.value = (await api('area.get', { area: d.value.area.parent.name })).sub_areas
  } catch (e) {
    missing.value = true
  }
}
function done(t) {
  optimistic(() => {}, () => {}, () => api('tasks.set_status', { task: t.name, status: 'Done' })).then(load).catch(() => {})
}
async function addTask() {
  const text = quick.value.trim()
  if (!text) return
  quick.value = ''
  if (await tryCall(() => api('tasks.quick_add', { text, space: d.value.area.space, area: d.value.area.name }))) load()
}
async function createProject(v) {
  await db.insert({ doctype: 'Life Project', space: d.value.area.space, area: d.value.area.name, status: 'Active', ...v })
  loadLookups(true)
}
async function createNote(v) {
  const note = await db.insert({ doctype: 'Life Note', space: d.value.area.space, area: d.value.area.name, title: v.title, content_md: '' })
  router.push(`/library/${note.name}?edit=1`)
}
onRecordChanged(load)
onMounted(load)
watch(() => props.id, load)
// Ask from an area page: that area and its sub-areas
askScope(() => (d.value ? { kind: 'area', label: d.value.area.area_name, doctype: 'Life Area', name: d.value.area.name } : { kind: 'space', label: 'Everything in this space' }))
</script>
