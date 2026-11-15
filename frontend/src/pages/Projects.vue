<template>
  <ListView ref="list" title="Projects" noun="projects" :filters="FILTERS" :columns="COLUMNS" :fetch="fetch" :row-ref="(r) => 'project:' + r.name"
    :watch-keys="['view']" :custom="view === 'cards'" default-sort="active first" empty-title="No active projects."
    empty-hint="A project lives inside one area and holds tasks, notes, documents and chats. Add one with New project.">
    <template #sub>{{ route.query.status ? '' : 'Active and on hold, ' }}across areas in {{ store.space }}</template>
    <template #actions>
      <div class="chips">
        <button v-for="v in ['list', 'cards']" :key="v" class="ch" :class="{ on: view === v }" type="button" :data-view="v" @click="setView(v)">{{ v === 'list' ? 'List' : 'Cards' }}</button>
      </div>
      <button v-if="canWrite()" class="bt p" type="button" @click="newOpen = true">New project</button>
    </template>
    <template #cell-title="{ row }"><div class="ttl">{{ row.title }}</div><div v-if="row.outcome" class="mt">Outcome: {{ row.outcome.replace(/^./, (c) => c.toLowerCase()) }}</div></template>
    <template #cell-area="{ row }"><RouterLink v-if="row.area" :to="`/areas/${row.area}`">{{ row.area_name }}</RouterLink></template>
    <template #cell-progress="{ row }">
      <div style="display: flex; align-items: center; gap: 8px"><div class="br" style="max-width: 70px"><i :style="`width: ${pct(row)}%`"></i></div>
        <RouterLink class="num" :to="doneLink(row)" data-door="project-tasks">{{ row.tasks_done }} of {{ row.tasks_total }} tasks done</RouterLink></div>
    </template>
    <template #cell-target_date="{ row }"><span class="mt">{{ row.target_date ? short(row.target_date, true) : '' }}</span></template>
    <template #cell-status="{ row }"><span class="pl" :class="pill(row)">{{ row.status === 'On Hold' ? 'On hold' : row.status }}</span></template>
    <template #stack="{ row }">
      <div style="display: flex; gap: 10px; align-items: flex-start">
        <div style="flex: 1; min-width: 0"><div class="ttl">{{ row.title }}</div>
          <div class="mt">{{ row.area_name }} · <RouterLink class="num" :to="doneLink(row)">{{ row.tasks_done }} of {{ row.tasks_total }} tasks done</RouterLink></div></div>
        <span class="pl" :class="pill(row)">{{ row.status === 'On Hold' ? 'On hold' : row.status }}</span>
      </div>
    </template>
    <template #body="{ rows }">
      <section v-for="g in groups(rows)" :key="g.area">
        <h2 class="sh"><RouterLink :to="`/areas/${g.area}`" style="margin: 0; color: inherit; font-weight: 600">{{ g.area_name }}</RouterLink></h2>
        <div class="pgrid"><ProjectCard v-for="p in g.projects" :key="p.name" :p="p" /></div>
      </section>
      <div v-if="!rows.length && list && list.total === 0" class="cd"><Empty title="No active projects." hint="A project lives inside one area and holds tasks, notes, documents and chats. Add one with New project." /></div>
    </template>
  </ListView>
  <NewRecord v-model="newOpen" title="New project" action="Add project" :fields="FIELDS" :save="create" @saved="list.reload()" />
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ListView from '@/components/ListView.vue'
import Empty from '@/components/Empty.vue'
import ProjectCard from '@/components/ProjectCard.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { doneLink } from '@/lib/tasks'
import { areaOptions, loadLookups } from '@/lib/lookups'

const route = useRoute()
const router = useRouter()
const list = ref(null)
const newOpen = ref(false)
const view = computed(() => (route.query.view === 'cards' ? 'cards' : 'list'))
const FILTERS = computed(() => [
  { key: 'status', label: 'Status', all: 'Active and on hold', options: [{ value: 'Active', label: 'Active' }, { value: 'On Hold', label: 'On hold' },
    { value: 'Done', label: 'Done' }, { value: 'Dropped', label: 'Dropped' }] },
  { key: 'area', label: 'Area', all: 'All areas', options: areaOptions() },
])
const COLUMNS = [{ key: 'title', label: 'Project', width: 'minmax(200px, 2fr)', sort: 'title' }, { key: 'area', label: 'Area', sort: 'area' },
  { key: 'progress', label: 'Progress', width: '230px' }, { key: 'target_date', label: 'Target', width: '100px', sort: 'target_date' },
  { key: 'status', label: 'Status', width: 'max-content', sort: 'status', align: 'right' }]
const FIELDS = computed(() => [{ name: 'title', label: 'Title', required: true }, { name: 'area', label: 'Area', required: true, options: areaOptions() },
  { name: 'outcome', label: 'Outcome', type: 'textarea', help: 'What will be true when this is done.' }, { name: 'target_date', label: 'Target date', type: 'date' }])
const pct = (p) => (p.tasks_total ? Math.round((100 * p.tasks_done) / p.tasks_total) : 0)
const pill = (p) => (p.status === 'Active' ? 'g' : p.status === 'On Hold' ? 'n' : 'b')
function groups(rows) {
  const by = new Map()
  for (const p of rows) {
    if (!by.has(p.area)) by.set(p.area, { area: p.area, area_name: p.area_name, projects: [] })
    by.get(p.area).projects.push(p)
  }
  return [...by.values()].sort((a, b) => (a.area_name || '').localeCompare(b.area_name || ''))
}
async function fetch({ filters: f, sort, dir, start, page_length }) {
  const res = await api('projects.list', { space: store.space, status: f.status || undefined, area: f.area || undefined, sort: sort || undefined, dir: dir || undefined,
    start, page_length })
  return { rows: res.projects, total: res.total }
}
const setView = (v) => router.push({ query: { ...route.query, view: v === 'cards' ? 'cards' : undefined } })
async function create(v) {
  await db.insert({ doctype: 'Life Project', space: store.space, status: 'Active', ...v })
  loadLookups(true)
}
onMounted(loadLookups)
</script>
<style scoped>
.pgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
</style>
