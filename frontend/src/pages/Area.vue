<template>
  <template v-if="d">
    <PageHead :title="d.area.area_name" :crumb="crumb" :sub="headSub">
      <template v-if="writable">
        <button class="bt s" type="button" @click="projectOpen = true">New project</button>
        <button class="bt p" type="button" @click="noteOpen = true">New note</button>
      </template>
    </PageHead>
    <div class="bd">
      <div v-if="d.sub_areas.length || d.area.parent" class="chips">
        <RouterLink class="ch" :class="{ on: !d.area.parent }" :to="`/areas/${d.area.parent ? d.area.parent.name : d.area.name}`">All</RouterLink>
        <RouterLink v-for="s in siblings" :key="s.name" class="ch" :class="{ on: s.name === d.area.name }" :to="`/areas/${s.name}`">{{ s.area_name }}</RouterLink>
      </div>

      <section>
        <h2 class="sh">Projects</h2>
        <div v-if="d.projects.length" class="pgrid"><ProjectCard v-for="p in d.projects" :key="p.name" :p="p" /></div>
        <div v-else class="cd"><Empty title="No active projects." hint="A project is an outcome with an end. Add one with New project." /></div>
      </section>

      <section v-if="d.goals.length">
        <h2 class="sh">12 Week Year goals <RouterLink to="/journal" class="more">Open grid</RouterLink></h2>
        <div class="cd list">
          <div v-for="g in d.goals" :key="g.name" class="rw" style="align-items: center">
            <div class="grow"><RouterLink class="ttl" :to="`/journal/goals/${g.name}`">{{ g.title }}</RouterLink><div class="mt">{{ g.actions }} actions</div></div>
            <div class="br" style="max-width: 160px"><i :style="`width: ${g.percent}%`"></i></div><span style="width: 40px; text-align: right">{{ Math.round(g.percent) }}%</span>
          </div>
        </div>
      </section>

      <div class="cols">
        <div class="half">
          <section>
            <h2 class="sh">Open tasks <RouterLink class="more" :to="`/tasks?area=${d.area.name}`">All {{ d.counts.open_tasks }}</RouterLink></h2>
            <div class="cd list">
              <TaskRow v-for="t in d.tasks" :key="t.name" :task="areaTask(t)" :today="store.today" with-due :readonly="!writable" @toggle="done" @open="openTask = t.name" />
              <Empty v-if="!d.tasks.length" title="No open tasks." hint="Tasks filed under this area show here." />
              <div v-if="writable" class="rw"><input v-model="quick" class="inp" style="flex: 1" placeholder="Add a task to this area" aria-label="Add a task" @keydown.enter="addTask" /></div>
            </div>
          </section>
          <section>
            <h2 class="sh">Recent chats <RouterLink class="more" to="/chats">Report</RouterLink></h2>
            <div class="cd list">
              <IndexRow v-for="c in d.chats" :key="c.ref_name" :row="c">
                {{ [short(c.record_date), c.project_title, c.open_items ? `${c.open_items} open item${c.open_items === 1 ? '' : 's'}` : 'no open items'].filter(Boolean).join(' · ') }}
              </IndexRow>
              <Empty v-if="!d.chats.length" title="No chats filed here." hint="When an agent logs an AI chat under this area, it shows here with its open items." />
            </div>
          </section>
          <section>
            <h2 class="sh">Latest on the timeline <RouterLink class="more" to="/timeline">Timeline</RouterLink></h2>
            <div class="cd list">
              <IndexRow v-for="e in d.timeline" :key="e.ref_name + e.kind" :row="e" show-kind />
              <Empty v-if="!d.timeline.length" title="Nothing captured yet." hint="The last 20 records filed under this area show here." />
            </div>
          </section>
        </div>
        <div class="half">
          <section>
            <h2 class="sh">Reference notes <RouterLink class="more" to="/library">All {{ d.counts.reference_notes }}</RouterLink></h2>
            <div class="cd list">
              <IndexRow v-for="n in d.notes" :key="n.ref_name" :row="n">Added {{ short(n.record_date) }}</IndexRow>
              <Empty v-if="!d.notes.length" title="No reference notes." hint="A note with no project is reference material for its area. Add one with New note." />
            </div>
          </section>
          <section>
            <h2 class="sh">Documents</h2>
            <div class="cd list">
              <IndexRow v-for="n in d.documents" :key="n.ref_name" :row="n" pill="Vault">{{ [n.project_title, 'added ' + short(n.record_date)].filter(Boolean).join(' · ') }}</IndexRow>
              <Empty v-if="!d.documents.length" title="No documents." hint="Vault documents filed under this area show here." />
            </div>
          </section>
          <section v-if="d.references.length">
            <h2 class="sh">References from other areas</h2>
            <div class="cd list">
              <IndexRow v-for="n in d.references" :key="n.ref_name" :row="n" pill="Reference" pill-class="b">Lives in {{ n.area_name || 'another area' }} · also filed here</IndexRow>
            </div>
          </section>
        </div>
      </div>
      <p class="mt" style="margin: 0">Archived items are hidden here and listed under <RouterLink to="/archive">Archive</RouterLink>.</p>
    </div>
    <TaskPanel v-if="openTask" :name="openTask" @close="openTask = null" @changed="load" />
    <NewRecord v-model="projectOpen" title="New project" action="Add project" :fields="PROJECT_FIELDS" :save="createProject" @saved="load" />
    <NewRecord v-model="noteOpen" title="New note" action="Create note" :fields="[{ name: 'title', label: 'Title', required: true }]" :save="createNote" />
  </template>
  <div v-else-if="missing" class="bd"><div class="cd"><Empty title="This area was not found." hint="It may belong to another space." /></div></div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import TaskPanel from '@/components/TaskPanel.vue'
import IndexRow from '@/components/IndexRow.vue'
import ProjectCard from '@/components/ProjectCard.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db, optimistic, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'

const props = defineProps({ id: String })
const router = useRouter()
const d = ref(null)
const missing = ref(false)
const openTask = ref(null)
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
const headSub = computed(() => {
  const c = d.value.counts
  const n = (x, w) => `${x} ${w}${x === 1 ? '' : 's'}`
  return [n(c.projects, 'active project'), n(c.open_tasks, 'open task'), n(c.notes, 'note'), n(c.documents, 'document')].join(' · ')
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
onMounted(load)
</script>
<style scoped>
.pgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
</style>
