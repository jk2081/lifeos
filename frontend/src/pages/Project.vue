<template>
  <template v-if="d">
    <PageHead :title="p.title" :crumb="{ to: `/areas/${p.area}`, label: p.area_name || 'Area', here: 'Project' }">
      <Badge :theme="!p.is_archived && p.status === 'Active' ? 'green' : 'gray'" :label="p.is_archived ? `${p.status}, archived` : p.status" />
      <template v-if="writable">
        <Button v-if="!p.is_archived" label="New note" @click="noteOpen = true" />
        <Button v-if="p.is_archived" variant="solid" label="Restore" @click="setStatus('Active')" />
        <template v-else>
          <Button :label="p.status === 'On Hold' ? 'Resume' : 'Put on hold'" @click="setStatus(p.status === 'On Hold' ? 'Active' : 'On Hold')" />
          <Button label="Drop" @click="askComplete('Dropped')" />
          <Button variant="solid" label="Complete" @click="askComplete('Done')" />
        </template>
      </template>
    </PageHead>
    <!-- the project's tabs (tab=) -->
    <TabBar class="flex-none" inset :tabs="tabs" :model-value="tab.current.value" label="Project sections" data-page-tabs @update:model-value="setTab" />
    <div v-show="tab.current.value === 'overview'" class="page-body" data-tab-panel="overview">
      <Card class="flex flex-col gap-3">
        <TextInput v-model="p.outcome" label="Outcome" :disabled="!writable" placeholder="What will be true when this is done" @change="saveField('outcome')" />
        <div class="form-grid">
          <DatePicker format="D MMM YYYY" v-model="p.target_date" label="Target date" clearable :disabled="!writable" @change="saveField('target_date')" />
          <div class="space-y-1.5"><div class="text-sm text-ink-gray-6">Progress</div><div class="flex h-8 items-center gap-2">
            <div class="min-w-0 flex-1"><Progress size="sm" :value="p.tasks_total ? Math.round((100 * p.tasks_done) / p.tasks_total) : 0" /></div>
            <NumLink class="text-sm" :to="doneLink(p)" data-door="project-tasks">{{ p.tasks_done }} of {{ p.tasks_total }} tasks done</NumLink></div></div>
        </div>
      </Card>
      <section>
        <SectionHead :count="d.tabs.tasks" :to="{ query: { tab: 'tasks' } }" door="project-overview-tasks">Open tasks</SectionHead>
        <Card flush>
          <TaskRow v-for="t in openTasks.slice(0, 5)" :key="t.name" :task="t" :today="store.today" with-due :readonly="!writable" @toggle="toggle" />
          <Empty v-if="!openTasks.length" title="No open tasks." hint="Add the next step below." />
          <Row v-if="writable && !p.is_archived"><TextInput v-model="quick" class="flex-1" placeholder="Add a task to this project" aria-label="Add a task" @keydown.enter="addTask" /></Row>
        </Card>
      </section>
    </div>
    <div :key="p.name" class="contents">
      <div v-if="tab.shown('tasks')" v-show="tab.current.value === 'tasks'" class="contents" data-tab-panel="tasks"><Tasks :embed="embed('tasks')" /></div>
      <div v-if="tab.shown('notes')" v-show="tab.current.value === 'notes'" class="contents" data-tab-panel="notes"><NotesList :embed="embed('notes')" /></div>
      <div v-if="tab.shown('documents')" v-show="tab.current.value === 'documents'" class="contents" data-tab-panel="documents"><Vault :embed="embed('documents')" /></div>
      <div v-if="tab.shown('chats')" v-show="tab.current.value === 'chats'" class="contents" data-tab-panel="chats"><Chats :embed="embed('chats')" /></div>
      <div v-if="tab.shown('links')" v-show="tab.current.value === 'links'" class="page-body" data-tab-panel="links"><Backlinks tab doctype="Life Project" :name="p.name" :reload="stamp" /></div>
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
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, DatePicker, Dialog, Progress, TextInput, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import NumLink from '@/components/ui/NumLink.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import TaskRow from '@/components/TaskRow.vue'
import TabBar from '@/components/TabBar.vue'
import Tasks from '@/pages/Tasks.vue'
import Vault from '@/pages/Vault.vue'
import Chats from '@/pages/Chats.vue'
import NotesList from '@/components/lists/NotesList.vue'
import Backlinks from '@/components/Backlinks.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api, db, optimistic, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { askScope } from '@/lib/ask'
import { loadLookups } from '@/lib/lookups'
import { doneLink } from '@/lib/tasks'
import { onRecordChanged } from '@/lib/pane'
import { useUrlTab } from '@/lib/tabs'

const props = defineProps({ id: String })
const route = useRoute()
const router = useRouter()
const stamp = ref(0)
const d = ref(null)
const missing = ref(false)
const quick = ref('')
const confirmOpen = ref(false)
const confirmStatus = ref('Done')
const noteOpen = ref(false)
const p = computed(() => d.value.project)
const writable = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write')
// The tabs. Each list tab is the main screen's list with this project fixed, its view remembered per tab across projects.
const TABS = [['overview', 'Overview'], ['tasks', 'Tasks'], ['notes', 'Notes'], ['documents', 'Documents'], ['chats', 'Chats'], ['links', 'Links']]
const NOUNS = { tasks: 'open tasks', notes: 'notes', documents: 'documents', chats: 'chats', links: 'linked records' }
const tabs = computed(() => TABS.map(([value, label]) => ({ value, label, count: value === 'overview' ? undefined : d.value?.tabs?.[value], noun: NOUNS[value] })))
const tab = useUrlTab('tab', tabs)
// a tab change keeps only the tab and the open record: the list query in the URL belongs to the tab that was open
function setTab(v) {
  if (v === tab.current.value) return
  router.push({ query: { tab: v === 'overview' ? undefined : v, open: route.query.open, ptab: route.query.ptab } })
}
// the Overview preview is Open and Doing, as the Tasks tab opens
const openTasks = computed(() => d.value.tasks.filter((t) => ['Open', 'Doing'].includes(t.status)))
function embed(t) {
  const path = route.path
  return { screen: 'project', space: d.value.space, fixed: { project: p.value.name, ...(p.value.is_archived ? { archived: '1' } : {}) }, writable: writable.value && !p.value.is_archived,
    active: (r) => r.path === path && (r.query.tab || 'overview') === t }
}

async function load() {
  try {
    d.value = await api('projects.get', { project: props.id })
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
watch(() => props.id, load)
// Ask from a project page: that project
askScope(() => (d.value ? { kind: 'project', label: d.value.project.title, doctype: 'Life Project', name: d.value.project.name } : { kind: 'space', label: 'Everything in this space' }))
</script>
