<template>
  <template v-if="d">
    <div class="chips">
      <span class="pl" :class="p.is_archived ? 'n' : p.status === 'Active' ? 'g' : 'n'">{{ p.is_archived ? `${p.status}, archived` : p.status === 'On Hold' ? 'On hold' : p.status }}</span>
      <span class="mt">{{ p.target_date ? 'Target ' + short(p.target_date, true) : 'No target date' }}</span>
    </div>
    <div v-if="p.outcome"><div class="lbl">Outcome</div><div>{{ p.outcome }}</div></div>
    <div><div class="lbl">Progress</div>
      <div style="display: flex; align-items: center; gap: 10px"><div class="br"><i :style="`width: ${p.tasks_total ? (100 * p.tasks_done) / p.tasks_total : 0}%`"></i></div>
        <RouterLink class="num" :to="doneLink(p)" data-door="project-tasks">{{ p.tasks_done }} of {{ p.tasks_total }} tasks done</RouterLink></div></div>
    <div class="chips mt">
      <RouterLink class="num" :to="{ path: '/tasks', query: { project: p.name, ...arch } }">{{ plural(d.counts.open_tasks, 'open task') }}</RouterLink> ·
      <RouterLink class="num" :to="{ path: '/library', query: { view: 'list', project: p.name, ...arch } }">{{ plural(d.counts.notes, 'note') }}</RouterLink> ·
      <RouterLink class="num" :to="{ path: '/vault', query: { project: p.name, ...arch } }">{{ plural(d.counts.documents, 'document') }}</RouterLink> ·
      <RouterLink class="num" :to="{ path: '/chats', query: { project: p.name, ...arch } }">{{ plural(d.counts.chats, 'chat') }}</RouterLink>
    </div>
    <section>
      <h2 class="sh">Open tasks</h2>
      <div class="cd list">
        <TaskRow v-for="t in d.tasks" :key="t.name" :task="t" :today="store.today" with-due :readonly="!writable" @toggle="toggle" @open="openRef('task:' + t.name)" />
        <Empty v-if="!d.tasks.length" title="No open tasks." hint="Add the next step on the project page." />
      </div>
    </section>
  </template>
</template>
<script setup>
// A project in the pane: the summary and its open tasks. The full page has the notes, documents and chats.
import { computed, onMounted, ref } from 'vue'
import TaskRow from '../TaskRow.vue'
import Empty from '../Empty.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { openRef } from '@/lib/pane'
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
