<template>
  <template v-if="d">
    <PageHead :title="d.area.area_name" :crumb="crumb">
      <template #sub>
        <NumLink :to="door.projects" data-door="area-projects">{{ plural(d.counts.projects, 'active project') }}</NumLink> ·
        <NumLink :to="door.tasks" data-door="area-tasks">{{ plural(d.counts.open_tasks, 'open task') }}</NumLink> ·
        <NumLink :to="door.notes" data-door="area-notes">{{ plural(d.counts.notes, 'note') }}</NumLink> ·
        <NumLink :to="door.documents" data-door="area-documents">{{ plural(d.counts.documents, 'document') }}</NumLink>
      </template>
      <template v-if="writable">
        <Button label="New project" @click="projectOpen = true" />
        <Button variant="solid" label="New note" @click="noteOpen = true" />
      </template>
    </PageHead>
    <div class="page-body">
      <div v-if="d.sub_areas.length || d.area.parent" class="scroll-x">
        <TabButtons :model-value="d.area.name" :options="areaTabs" />
      </div>

      <section>
        <SectionHead :count="d.counts.all_projects" :to="door.allProjects">Projects</SectionHead>
        <div v-if="d.projects.length" class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3"><ProjectCard v-for="p in d.projects" :key="p.name" :p="p" /></div>
        <Card v-else><Empty title="No active projects." hint="A project is an outcome with an end. Add one with New project." /></Card>
      </section>

      <section v-if="d.goals.length">
        <SectionHead>12 Week Year goals<template #action><Button variant="ghost" size="sm" label="Open grid" route="/journal" /></template></SectionHead>
        <Card flush>
          <Row v-for="g in d.goals" :key="g.name" class="!items-center" :pane="'goal:' + g.name" :label="g.title">
            <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ g.title }}</div><div class="text-sm text-ink-gray-6">{{ g.actions }} actions</div></div>
            <div class="w-40 max-md:w-20"><Progress size="sm" :value="Math.round(g.percent)" /></div><span class="w-10 text-right tabular-nums text-ink-gray-8">{{ Math.round(g.percent) }}%</span>
          </Row>
        </Card>
      </section>

      <div class="cols">
        <div class="half">
          <section>
            <SectionHead :count="d.counts.open_tasks" :to="door.tasks">Open tasks</SectionHead>
            <Card flush>
              <TaskRow v-for="t in d.tasks" :key="t.name" :task="areaTask(t)" :today="store.today" with-due :readonly="!writable" @toggle="done" />
              <Empty v-if="!d.tasks.length" title="No open tasks." hint="Tasks filed under this area show here." />
              <Row v-if="writable"><TextInput v-model="quick" class="flex-1" placeholder="Add a task to this area" aria-label="Add a task" @keydown.enter="addTask" /></Row>
            </Card>
          </section>
          <section>
            <SectionHead :count="d.counts.chats" :to="door.chats">Recent chats</SectionHead>
            <Card flush>
              <IndexRow v-for="c in d.chats" :key="c.ref_name" :row="c">
                {{ [short(c.record_date), c.project_title, c.open_items ? `${c.open_items} open item${c.open_items === 1 ? '' : 's'}` : 'no open items'].filter(Boolean).join(' · ') }}
              </IndexRow>
              <Empty v-if="!d.chats.length" title="No chats filed here." hint="When an agent logs an AI chat under this area, it shows here with its open items." />
            </Card>
          </section>
          <section>
            <SectionHead>Latest on the timeline<template #action><Button variant="ghost" size="sm" label="Timeline" :route="{ path: '/timeline', query: { area: d.area.name } }" /></template></SectionHead>
            <Card flush>
              <IndexRow v-for="e in d.timeline" :key="e.ref_name + e.kind" :row="e" show-kind />
              <Empty v-if="!d.timeline.length" title="Nothing captured yet." hint="The last 20 records filed under this area show here." />
            </Card>
          </section>
        </div>
        <div class="half">
          <section>
            <SectionHead :count="d.counts.reference_notes" :to="door.reference" door="area-reference">Reference notes</SectionHead>
            <Card flush>
              <IndexRow v-for="n in d.notes" :key="n.ref_name" :row="n">Added {{ short(n.record_date) }}</IndexRow>
              <Empty v-if="!d.notes.length" title="No reference notes." hint="A note with no project is reference material for its area. Add one with New note." />
            </Card>
          </section>
          <section>
            <SectionHead :count="d.counts.documents" :to="door.documents">Documents</SectionHead>
            <Card flush>
              <IndexRow v-for="n in d.documents" :key="n.ref_name" :row="n" pill="Vault">{{ [n.project_title, 'added ' + short(n.record_date)].filter(Boolean).join(' · ') }}</IndexRow>
              <Empty v-if="!d.documents.length" title="No documents." hint="Vault documents filed under this area show here." />
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
    <NewRecord v-model="projectOpen" title="New project" action="Add project" :fields="PROJECT_FIELDS" :save="createProject" @saved="load" />
    <NewRecord v-model="noteOpen" title="New note" action="Create note" :fields="[{ name: 'title', label: 'Title', required: true }]" :save="createNote" />
  </template>
  <div v-else-if="missing" class="page-body"><Card><Empty title="This area was not found." hint="It may belong to another space." /></Card></div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, Progress, TabButtons, TextInput } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import IndexRow from '@/components/IndexRow.vue'
import ProjectCard from '@/components/ProjectCard.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db, optimistic, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'
import { plural } from '@/lib/tasks'
import { onRecordChanged } from '@/lib/pane'

const props = defineProps({ id: String })
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
// every number on this page leads to the list it counts, filtered to this area and its sub-areas
const door = computed(() => {
  const area = d.value.area.name
  return {
    projects: { path: '/projects', query: { area, status: 'Active' } }, allProjects: { path: '/projects', query: { area, f: JSON.stringify([['status', 'in', ['Active', 'On Hold']], ['is_archived', '=', 0]]) } },
    tasks: { path: '/tasks', query: { area, view: 'list' } }, notes: { path: '/library', query: { view: 'list', area } },
    reference: { path: '/library', query: { view: 'list', area, project: 'none' } }, documents: { path: '/vault', query: { area } },
    chats: { path: '/chats', query: { area } },
  }
})
// On an area page the area is known, so the row shows the project instead.
const areaTask = (t) => ({ ...t, area_name: t.project_title || 'No project', project_title: null, goal_title: null })

async function load() {
  try {
    d.value = await api('area.get', { area: props.id })
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
</script>
