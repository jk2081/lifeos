<template>
  <template v-if="d">
    <div class="flex flex-wrap items-center gap-2">
      <Badge :theme="!p.is_archived && p.status === 'Active' ? 'green' : 'gray'" :label="p.is_archived ? `${p.status}, archived` : p.status === 'On Hold' ? 'On hold' : p.status" />
      <span class="text-sm text-ink-gray-6">{{ p.target_date ? 'Target ' + short(p.target_date, true) : 'No target date' }}</span>
    </div>
    <div v-if="p.outcome"><div class="mb-1 text-sm-medium text-ink-gray-7">Outcome</div><div class="text-base text-ink-gray-8">{{ p.outcome }}</div></div>
    <div><div class="mb-1 text-sm-medium text-ink-gray-7">Progress</div>
      <div class="flex items-center gap-2.5"><div class="min-w-0 flex-1"><Progress size="sm" :value="p.tasks_total ? Math.round((100 * p.tasks_done) / p.tasks_total) : 0" /></div>
        <NumLink class="text-sm" :to="doneLink(p)" data-door="project-tasks">{{ p.tasks_done }} of {{ p.tasks_total }} tasks done</NumLink></div></div>
    <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6">
      <NumLink :to="{ path: '/tasks', query: { project: p.name, ...arch } }">{{ plural(d.counts.open_tasks, 'open task') }}</NumLink> ·
      <NumLink :to="{ path: '/library', query: { view: 'list', project: p.name, ...arch } }">{{ plural(d.counts.notes, 'note') }}</NumLink> ·
      <NumLink :to="{ path: '/vault', query: { project: p.name, ...arch } }">{{ plural(d.counts.documents, 'document') }}</NumLink> ·
      <NumLink :to="{ path: '/chats', query: { project: p.name, ...arch } }">{{ plural(d.counts.chats, 'chat') }}</NumLink>
    </div>
    <section>
      <SectionHead>Open tasks</SectionHead>
      <Card flush>
        <TaskRow v-for="t in d.tasks" :key="t.name" :task="t" :today="store.today" with-due :readonly="!writable" @toggle="toggle" />
        <Empty v-if="!d.tasks.length" title="No open tasks." hint="Add the next step on the project page." />
      </Card>
    </section>
  </template>
</template>
<script setup>
// A project in the pane: the summary and its open tasks. The full page has the notes, documents and chats.
import { computed, onMounted, ref } from 'vue'
import { Badge, Progress } from 'frappe-ui'
import Card from '../ui/Card.vue'
import NumLink from '../ui/NumLink.vue'
import SectionHead from '../ui/SectionHead.vue'
import TaskRow from '../TaskRow.vue'
import Empty from '../Empty.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { doneLink, plural } from '@/lib/tasks'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const d = ref(null)
const p = computed(() => d.value.project)
const canRestore = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !p.value.is_archived)
const arch = computed(() => (p.value.is_archived ? { archived: '1' } : {}))
async function load() {
  try {
    d.value = await api('projects.get', { project: props.name })
    emit('meta', { title: p.value.title, area: p.value.area, area_name: p.value.area_name, fullPage: `/projects/${p.value.name}`,
      archived: !!p.value.is_archived, canRestore: canRestore.value })
  } catch (e) {
    emit('missing')
  }
}
async function toggle(t) {
  if (await tryCall(() => api('tasks.set_status', { task: t.name, status: t.status === 'Done' ? 'Open' : 'Done' }))) {
    await load()
    emit('changed')
  }
}
onMounted(load)
</script>
