<template>
  <ListView ref="list" title="Projects" noun="projects" screen="projects" doctype="Life Project" :spec="SPEC" :quick="['status', 'area']" :synthetic="SYNTHETIC"
    :views="VIEWS" :fetch="fetch" :row-ref="(r) => 'project:' + r.name" empty-title="No active projects."
    empty-hint="A project lives inside one area and holds tasks, notes, documents and chats. Add one with New project.">
    <template #sub>{{ route.query.status ? '' : 'Active and on hold, ' }}across areas in {{ store.space }}</template>
    <template #actions><Button v-if="canWrite()" variant="solid" icon-left="lucide-plus" label="New project" @click="newOpen = true" /></template>
    <template #cell-title="{ row }"><div class="min-w-0"><div class="break-words font-medium text-ink-gray-9">{{ row.title }}</div>
      <div v-if="row.outcome" class="text-sm text-ink-gray-6">Outcome: {{ row.outcome.replace(/^./, (c) => c.toLowerCase()) }}</div></div></template>
    <template #cell-area="{ row }"><RouterLink v-if="row.area" class="relative truncate text-ink-blue-8 hover:underline" :to="`/areas/${row.area}`">{{ row.area_name }}</RouterLink></template>
    <template #cell-_progress="{ row }">
      <div class="flex min-w-0 items-center gap-2"><div class="w-16 shrink-0"><Progress size="sm" :value="pct(row)" /></div>
        <NumLink class="relative truncate" :to="doneLink(row)" data-door="project-tasks">{{ row.tasks_done }} of {{ row.tasks_total }} tasks done</NumLink></div>
    </template>
    <template #cell-status="{ row }"><Badge :theme="theme(row)" :label="row.status === 'On Hold' ? 'On hold' : row.status" /></template>
    <template #stack="{ row }">
      <div class="flex items-start gap-2.5">
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ row.area_name }} · <NumLink class="relative" :to="doneLink(row)" data-door="project-tasks">{{ row.tasks_done }} of {{ row.tasks_total }} tasks done</NumLink></div></div>
        <Badge :theme="theme(row)" :label="row.status === 'On Hold' ? 'On hold' : row.status" />
      </div>
    </template>
    <template #body="{ rows }">
      <section v-for="g in groups(rows)" :key="g.area">
        <SectionHead><RouterLink class="font-semibold text-ink-gray-8 hover:underline" :to="`/areas/${g.area}`">{{ g.area_name }}</RouterLink></SectionHead>
        <div class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3"><ProjectCard v-for="p in g.projects" :key="p.name" :p="p" /></div>
      </section>
      <Card v-if="!rows.length && list && list.total === 0"><Empty title="No active projects." hint="A project lives inside one area and holds tasks, notes, documents and chats. Add one with New project." /></Card>
    </template>
  </ListView>
  <NewRecord v-model="newOpen" title="New project" action="Add project" :fields="FIELDS" :save="create" @saved="list.reload()" />
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button, Progress } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import ProjectCard from '@/components/ProjectCard.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { doneLink } from '@/lib/tasks'
import { areaOptions, loadLookups } from '@/lib/lookups'

const VIEWS = [{ key: 'list', label: 'List', mode: 'table' }, { key: 'cards', label: 'Cards', mode: 'custom' }]
const SPEC = [{ key: 'status', field: 'status', kind: 'value' }, { key: 'area', field: 'area', kind: 'link' }]
const SYNTHETIC = [{ key: '_progress', label: 'Progress', width: '15rem', place: 'end' }]
const route = useRoute()
const list = ref(null)
const newOpen = ref(false)
const FIELDS = computed(() => [{ name: 'title', label: 'Title', required: true }, { name: 'area', label: 'Area', required: true, options: areaOptions() },
  { name: 'outcome', label: 'Outcome', type: 'textarea', help: 'What will be true when this is done.' }, { name: 'target_date', label: 'Target date', type: 'date' }])
const pct = (p) => (p.tasks_total ? Math.round((100 * p.tasks_done) / p.tasks_total) : 0)
const theme = (p) => (p.status === 'Active' ? 'green' : p.status === 'On Hold' ? 'gray' : 'blue')
function groups(rows) {
  const by = new Map()
  for (const p of rows) {
    if (!by.has(p.area)) by.set(p.area, { area: p.area, area_name: p.area_name, projects: [] })
    by.get(p.area).projects.push(p)
  }
  return [...by.values()].sort((a, b) => (a.area_name || '').localeCompare(b.area_name || ''))
}
async function fetch({ params: p, filters, order_by, summary, start, page_length }) {
  const res = await api('projects.list', { space: store.space, status: p.status, area: p.area, filters, order_by, summary, start, page_length })
  return summary ? res : { rows: res.projects, total: res.total }
}
async function create(v) {
  await db.insert({ doctype: 'Life Project', space: store.space, status: 'Active', ...v })
  loadLookups(true)
}
onMounted(loadLookups)
</script>
