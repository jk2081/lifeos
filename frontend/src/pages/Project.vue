<template>
  <template v-if="d">
    <PageHead :title="p.title" :crumb="{ to: `/areas/${p.area}`, label: p.area_name || 'Area', here: 'Project' }">
      <template #sub>
        <RouterLink class="num" :to="door.tasks" data-door="project-open">{{ plural(d.counts.open_tasks, 'open task') }}</RouterLink> ·
        <RouterLink class="num" :to="door.notes" data-door="project-notes">{{ plural(d.counts.notes, 'note') }}</RouterLink> ·
        <RouterLink class="num" :to="door.documents" data-door="project-documents">{{ plural(d.counts.documents, 'document') }}</RouterLink> ·
        <RouterLink class="num" :to="door.chats" data-door="project-chats">{{ plural(d.counts.chats, 'chat') }}</RouterLink>
      </template>
      <span class="pl" :class="p.is_archived ? 'n' : p.status === 'Active' ? 'g' : 'n'">{{ p.is_archived ? `${p.status}, archived` : p.status }}</span>
      <template v-if="writable">
        <button v-if="p.is_archived" class="bt p" type="button" @click="setStatus('Active')">Restore</button>
        <template v-else>
          <button class="bt s" type="button" @click="setStatus(p.status === 'On Hold' ? 'Active' : 'On Hold')">{{ p.status === 'On Hold' ? 'Resume' : 'Put on hold' }}</button>
          <button class="bt s" type="button" @click="askComplete('Dropped')">Drop</button>
          <button class="bt p" type="button" @click="askComplete('Done')">Complete</button>
        </template>
      </template>
    </PageHead>
    <div class="bd">
      <div class="cd">
        <div class="field"><label class="lbl" for="pj-outcome">Outcome</label>
          <input id="pj-outcome" v-model="p.outcome" class="inp" :disabled="!writable" placeholder="What will be true when this is done" @change="saveField('outcome')" /></div>
        <div class="formgrid" style="margin-top: 10px">
          <div class="field"><label class="lbl" for="pj-target">Target date</label><input id="pj-target" v-model="p.target_date" type="date" class="inp" :disabled="!writable" @change="saveField('target_date')" /></div>
          <div class="field"><span class="lbl">Progress</span><div style="display: flex; align-items: center; gap: 8px; height: 32px">
            <div class="br"><i :style="`width: ${p.tasks_total ? (100 * p.tasks_done) / p.tasks_total : 0}%`"></i></div><RouterLink class="num" :to="doneLink(p)" data-door="project-tasks">{{ p.tasks_done }} of {{ p.tasks_total }} tasks done</RouterLink></div></div>
        </div>
      </div>
      <div class="cols">
        <div class="half">
          <section>
            <h2 class="sh">Tasks <RouterLink class="more num" :to="door.tasks">All {{ d.counts.open_tasks }} open</RouterLink></h2>
            <div class="cd list">
              <TaskRow v-for="t in d.tasks" :key="t.name" :task="t" :today="store.today" with-due :readonly="!writable" @toggle="toggle" @open="openRef('task:' + t.name)" />
              <Empty v-if="!d.tasks.length" title="No open tasks." hint="Add the next step below." />
              <div v-if="writable && !p.is_archived" class="rw"><input v-model="quick" class="inp" style="flex: 1" placeholder="Add a task to this project" aria-label="Add a task" @keydown.enter="addTask" /></div>
            </div>
          </section>
          <section v-if="d.done_tasks.length">
            <h2 class="sh">Done</h2>
            <div class="cd list"><TaskRow v-for="t in d.done_tasks" :key="t.name" :task="t" :today="store.today" :readonly="!writable" @toggle="toggle" @open="openRef('task:' + t.name)" /></div>
          </section>
        </div>
        <div class="half">
          <section>
            <h2 class="sh">Notes <RouterLink class="num" style="margin-left: 0" :to="door.notes">{{ d.counts.notes }}</RouterLink>
              <a v-if="writable && !p.is_archived" href="#" class="more" @click.prevent="noteOpen = true">New note</a></h2>
            <div class="cd list"><IndexRow v-for="n in d.notes" :key="n.ref_name" :row="n">Added {{ short(n.record_date) }}</IndexRow>
              <Empty v-if="!d.notes.length" title="No notes." hint="Notes filed under this project show here." /></div>
          </section>
          <section>
            <h2 class="sh">Documents <RouterLink class="num" style="margin-left: 0" :to="door.documents">{{ d.counts.documents }}</RouterLink></h2>
            <div class="cd list"><IndexRow v-for="n in d.documents" :key="n.ref_name" :row="n" pill="Vault">Added {{ short(n.record_date) }}</IndexRow>
              <Empty v-if="!d.documents.length" title="No documents." hint="Vault documents filed under this project show here." /></div>
          </section>
          <section>
            <h2 class="sh">Chats <RouterLink class="num" style="margin-left: 0" :to="door.chats">{{ d.counts.chats }}</RouterLink></h2>
            <div class="cd list"><IndexRow v-for="c in d.chats" :key="c.ref_name" :row="c">{{ short(c.record_date) }} · {{ c.open_items ? `${c.open_items} open items` : 'no open items' }}</IndexRow>
              <Empty v-if="!d.chats.length" title="No chats." hint="AI chats logged under this project show here." /></div>
          </section>
          <Backlinks doctype="Life Project" :name="p.name" />
        </div>
      </div>
    </div>
    <Dialog v-model="confirmOpen" :title="confirmStatus === 'Done' ? 'Complete this project?' : 'Drop this project?'" size="md">
      <p style="margin: 0">The project and <b>{{ d.record_count }} record{{ d.record_count === 1 ? '' : 's' }}</b> filed under it (tasks, notes, documents, chats) move to the Archive.
        Nothing is deleted, and you can restore it from the Archive screen.</p>
      <template #actions><div style="display: flex; gap: 8px; justify-content: flex-end">
        <button class="bt s" type="button" @click="confirmOpen = false">Cancel</button>
        <button class="bt p" type="button" @click="setStatus(confirmStatus)">{{ confirmStatus === 'Done' ? 'Complete and archive' : 'Drop and archive' }}</button></div></template>
    </Dialog>
    <NewRecord v-model="noteOpen" title="New note" action="Create note" :fields="[{ name: 'title', label: 'Title', required: true }]" :save="createNote" />
  </template>
  <div v-else-if="missing" class="bd"><div class="cd"><Empty title="This project was not found." hint="It may belong to another space." /></div></div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Dialog, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
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
import { onRecordChanged, openRef } from '@/lib/pane'

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
