<template>
  <template v-if="d">
    <PageHead :title="p.title" :crumb="{ to: `/areas/${p.area}`, label: p.area_name || 'Area', here: 'Project' }">
      <template #sub>
        <NumLink :to="door.tasks" data-door="project-open">{{ plural(d.counts.open_tasks, 'open task') }}</NumLink> ·
        <NumLink :to="door.notes" data-door="project-notes">{{ plural(d.counts.notes, 'note') }}</NumLink> ·
        <NumLink :to="door.documents" data-door="project-documents">{{ plural(d.counts.documents, 'document') }}</NumLink> ·
        <NumLink :to="door.chats" data-door="project-chats">{{ plural(d.counts.chats, 'chat') }}</NumLink>
      </template>
      <Badge :theme="!p.is_archived && p.status === 'Active' ? 'green' : 'gray'" :label="p.is_archived ? `${p.status}, archived` : p.status" />
      <template v-if="writable">
        <Button v-if="p.is_archived" variant="solid" label="Restore" @click="setStatus('Active')" />
        <template v-else>
          <Button :label="p.status === 'On Hold' ? 'Resume' : 'Put on hold'" @click="setStatus(p.status === 'On Hold' ? 'Active' : 'On Hold')" />
          <Button label="Drop" @click="askComplete('Dropped')" />
          <Button variant="solid" label="Complete" @click="askComplete('Done')" />
        </template>
      </template>
    </PageHead>
    <div class="page-body">
      <Card class="flex flex-col gap-3">
        <TextInput v-model="p.outcome" label="Outcome" :disabled="!writable" placeholder="What will be true when this is done" @change="saveField('outcome')" />
        <div class="form-grid">
          <DatePicker format="D MMM YYYY" v-model="p.target_date" label="Target date" clearable :disabled="!writable" @change="saveField('target_date')" />
          <div class="space-y-1.5"><div class="text-sm text-ink-gray-6">Progress</div><div class="flex h-8 items-center gap-2">
            <div class="min-w-0 flex-1"><Progress size="sm" :value="p.tasks_total ? Math.round((100 * p.tasks_done) / p.tasks_total) : 0" /></div>
            <NumLink class="text-sm" :to="doneLink(p)" data-door="project-tasks">{{ p.tasks_done }} of {{ p.tasks_total }} tasks done</NumLink></div></div>
        </div>
      </Card>
      <div class="cols">
        <div class="half">
          <section>
            <SectionHead :count="d.counts.open_tasks" :to="door.tasks">Tasks</SectionHead>
            <Card flush>
              <TaskRow v-for="t in d.tasks" :key="t.name" :task="t" :today="store.today" with-due :readonly="!writable" @toggle="toggle" />
              <Empty v-if="!d.tasks.length" title="No open tasks." hint="Add the next step below." />
              <Row v-if="writable && !p.is_archived"><TextInput v-model="quick" class="flex-1" placeholder="Add a task to this project" aria-label="Add a task" @keydown.enter="addTask" /></Row>
            </Card>
          </section>
          <section v-if="d.done_tasks.length">
            <SectionHead>Done</SectionHead>
            <Card flush><TaskRow v-for="t in d.done_tasks" :key="t.name" :task="t" :today="store.today" :readonly="!writable" @toggle="toggle" /></Card>
          </section>
        </div>
        <div class="half">
          <section>
            <SectionHead :count="d.counts.notes" :to="door.notes">Notes
              <template v-if="writable && !p.is_archived" #action><Button variant="ghost" size="sm" label="New note" @click="noteOpen = true" /></template>
            </SectionHead>
            <Card flush><IndexRow v-for="n in d.notes" :key="n.ref_name" :row="n">Added {{ short(n.record_date) }}</IndexRow>
              <Empty v-if="!d.notes.length" title="No notes." hint="Notes filed under this project show here." /></Card>
          </section>
          <section>
            <SectionHead :count="d.counts.documents" :to="door.documents">Documents</SectionHead>
            <Card flush><IndexRow v-for="n in d.documents" :key="n.ref_name" :row="n" pill="Vault">Added {{ short(n.record_date) }}</IndexRow>
              <Empty v-if="!d.documents.length" title="No documents." hint="Vault documents filed under this project show here." /></Card>
          </section>
          <section>
            <SectionHead :count="d.counts.chats" :to="door.chats">Chats</SectionHead>
            <Card flush><IndexRow v-for="c in d.chats" :key="c.ref_name" :row="c">{{ short(c.record_date) }} · {{ c.open_items ? `${c.open_items} open items` : 'no open items' }}</IndexRow>
              <Empty v-if="!d.chats.length" title="No chats." hint="AI chats logged under this project show here." /></Card>
          </section>
          <Backlinks doctype="Life Project" :name="p.name" />
        </div>
      </div>
    </div>
    <Dialog v-model:open="confirmOpen" :title="confirmStatus === 'Done' ? 'Complete this project?' : 'Drop this project?'" size="md"
      :actions="[{ label: 'Cancel', onClick: ({ close }) => close() },
        { label: confirmStatus === 'Done' ? 'Complete and archive' : 'Drop and archive', variant: 'solid', onClick: () => setStatus(confirmStatus) }]">
      <p class="text-base text-ink-gray-8">The project and <b class="font-semibold">{{ d.record_count }} record{{ d.record_count === 1 ? '' : 's' }}</b> filed under it (tasks, notes, documents, chats) move to the Archive.
        Nothing is deleted, and you can restore it from the Archive screen.</p>
    </Dialog>
    <NewRecord v-model="noteOpen" title="New note" action="Create note" :fields="[{ name: 'title', label: 'Title', required: true }]" :save="createNote" />
  </template>
  <div v-else-if="missing" class="page-body"><Card><Empty title="This project was not found." hint="It may belong to another space." /></Card></div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, DatePicker, Dialog, Progress, TextInput, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import IndexRow from '@/components/IndexRow.vue'
import Backlinks from '@/components/Backlinks.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db, optimistic, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'
import { doneLink, plural } from '@/lib/tasks'
import { onRecordChanged } from '@/lib/pane'

const props = defineProps({ id: String })
const router = useRouter()
const d = ref(null)
const missing = ref(false)
const quick = ref('')
const confirmOpen = ref(false)
const confirmStatus = ref('Done')
const noteOpen = ref(false)
const p = computed(() => d.value.project)
const writable = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write')
// every number on this page leads to the list it counts, filtered to this project
const door = computed(() => {
  const q = { project: p.value.name, ...(p.value.is_archived ? { archived: '1' } : {}) }
  return { tasks: { path: '/tasks', query: { ...q, view: 'list' } }, notes: { path: '/library', query: { view: 'list', ...q } },
    documents: { path: '/vault', query: q }, chats: { path: '/chats', query: q } }
})

async function load() {
  try {
    d.value = await api('projects.get', { project: props.id })
  } catch (e) {
    missing.value = true
  }
}
function askComplete(status) {
  confirmStatus.value = status
  confirmOpen.value = true
}
async function setStatus(status) {
  const res = await tryCall(() => api('projects.set_status', { project: p.value.name, status }))
  confirmOpen.value = false
  if (!res) return
  if (res.is_archived) toast.success(`Archived with ${res.archived_records} record${res.archived_records === 1 ? '' : 's'}. Restore it from Archive.`)
  else toast.success(`Project is ${status === 'On Hold' ? 'on hold' : status.toLowerCase()}.`)
  loadLookups(true)
  load()
}
async function saveField(field) {
  await tryCall(() => db.set('Life Project', p.value.name, { [field]: p.value[field] || null }))
}
function toggle(t) {
  const next = t.status === 'Done' ? 'Open' : 'Done'
  optimistic(() => {}, () => {}, () => api('tasks.set_status', { task: t.name, status: next })).then(load).catch(() => {})
}
async function addTask() {
  const text = quick.value.trim()
  if (!text) return
  quick.value = ''
  if (await tryCall(() => api('tasks.quick_add', { text, space: d.value.space, project: p.value.name }))) load()
}
async function createNote(v) {
  const note = await db.insert({ doctype: 'Life Note', space: d.value.space, area: p.value.area, project: p.value.name, title: v.title, content_md: '' })
  router.push(`/library/${note.name}?edit=1`)
}
onRecordChanged(load)
onMounted(load)
</script>
