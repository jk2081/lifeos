<template>
  <template v-if="task">
  <template v-if="on('details')">
  <FormControl v-model="task.title" type="text" label="Title" :disabled="!writable" @change="save({ title: task.title })" />
  <div class="form-grid">
    <FormControl type="select" label="Status" :model-value="task.status" :options="STATUSES" :disabled="!writable" @update:model-value="setStatus" />
    <FormControl type="select" label="Priority" :model-value="task.priority || ''" :options="PRIORITY_OPTIONS" :disabled="!writable" @update:model-value="(v) => save({ priority: v || null })" />
    <DatePicker format="D MMM YYYY" label="Due date" :model-value="task.due_date || ''" clearable :disabled="!writable" @update:model-value="(v) => save({ due_date: v || null })" />
  </div>
  <TextInput v-if="task.status === 'Waiting' || askWaiting" ref="waitInput" v-model="task.waiting_on" label="Waiting on" placeholder="Who or what is this waiting on?" :disabled="!writable"
    @change="askWaiting ? setStatus('Waiting') : save({ waiting_on: task.waiting_on })" />
  <div v-if="peopleOptions.length > 1" class="form-grid" data-task-people>
    <FormControl v-if="task.status === 'Waiting' || task.waiting_on_person" type="select" label="Waiting on (person)" :model-value="task.waiting_on_person || ''" :options="peopleOptions" :disabled="!writable"
      data-task-waiting-person @update:model-value="pickWaiting" />
    <FormControl type="select" label="Delegated to" :model-value="task.delegated_to || ''" :options="peopleOptions" :disabled="!writable"
      data-task-delegated @update:model-value="(v) => save({ delegated_to: v || null })" />
  </div>
  <div><div class="mb-1.5 text-sm text-ink-gray-6">Filed under</div>
    <div class="flex flex-wrap items-center gap-2">
      <div class="contents" data-task-area><Pick :model-value="task.area" :options="areaOptions()" placeholder="area" :disabled="!writable" @update:model-value="(v) => save({ area: v })" /></div>
      <AreaGuess :task="task" :readonly="!writable" full @confirmed="(t) => { task = { ...task, ...t }; tell(); emit('changed', task) }" />
      <Badge v-for="a in task.also_in" :key="a" size="lg">also in {{ areaName(a) }}
        <template v-if="writable" #suffix><Button class="!size-4" size="sm" variant="ghost" icon="lucide-x" :label="'Remove also in ' + areaName(a)" @click="save({ also_in: task.also_in.filter((x) => x !== a) })" /></template></Badge>
      <Pick :model-value="null" :options="areaOptions().filter((o) => o.value !== task.area && !task.also_in.includes(o.value))" placeholder="also in"
        :clearable="false" :disabled="!writable" @update:model-value="(v) => save({ also_in: [...task.also_in, v] })" />
    </div>
  </div>
   <FormControl type="select" label="Goal" :model-value="task.goal || ''" :options="goalOptions" :disabled="!writable" @update:model-value="(v) => save({ goal: v || null })" />
  <div class="text-sm text-ink-gray-6">
    <div v-if="task.inbox_item">From <a class="text-ink-blue-8 hover:underline" href="#" @click.prevent="openRef('inbox:' + task.inbox_item)">{{ task.source_title || 'an inbox item' }}</a></div>
    <div v-if="safeSource" class="my-1"><Button size="sm" icon-left="lucide-external-link" :label="sourceLabel" data-open-source @click="openSource" /></div>
    <div>Created {{ short(task.creation, true) }}<span v-if="task.completed_on"> · closed {{ short(task.completed_on, true) }}</span></div>
  </div>
  <div v-if="writable || canRestore" class="flex flex-wrap items-center gap-2">
    <Button v-if="writable && OPEN.includes(task.status)" label="Carry to next month" icon-right="lucide-arrow-right" @click="carry" />
    <Button v-if="writable" label="Archive" @click="archive" />
    <Button v-if="canRestore && !isAgent" variant="ghost" theme="red" label="Delete" @click="remove" />
  </div>
  </template>
  <template v-if="on('notes')">
    <div class="flex items-center gap-2 text-sm text-ink-gray-6"><span class="text-sm-medium text-ink-gray-7">Notes</span><span v-if="writable" data-save-state aria-live="polite">{{ notesState }}</span></div>
    <LiveEditor v-model="task.notes_md" compact :space="task.space" :links="task.links || []" :readonly="!writable" doctype="Life Task" :docname="task.name"
      label="Task notes" placeholder="Notes. Type [[ to link a record, / for blocks." @update:model-value="queueNotes" @blur="saveNotes" />
  </template>
  <Backlinks v-if="on('links')" tab doctype="Life Task" :name="task.name" :items="links" />
  </template>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Badge, Button, DatePicker, FormControl, TextInput, dialog, toast } from 'frappe-ui'
import Pick from '@/components/Pick.vue'
import Backlinks from '@/components/Backlinks.vue'
import LiveEditor from '@/components/LiveEditor.vue'
import { safeUrl } from '@/lib/editor/livePreview'
import { loadBacklinks } from '@/lib/links'
import { openRef } from '@/lib/pane'
import { db, errorText, tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import AreaGuess from '@/components/AreaGuess.vue'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { OPEN, PRIORITIES } from '@/lib/tasks'
import { areaName, areaOptions, goalOptions as goalsByType, loadLookups, lookups } from '@/lib/lookups'

const props = defineProps({ name: String, type: String, tab: String })
const emit = defineEmits(['close', 'changed', 'meta', 'missing'])
const task = ref(null)
const askWaiting = ref(false)
const waitInput = ref(null)
const links = ref([])
// the pane's tabs: Details (all fields and filing), Notes, Links
const on = (t) => !props.tab || props.tab === t
const isAgent = false
const STATUSES = ['Open', 'Doing', 'Waiting', 'Done', 'Dropped', 'Carried', 'Someday']
// a Select has no empty row of its own: the dash is an option whose value is the empty string
const PRIORITY_OPTIONS = [{ label: '—', value: '' }, ...PRIORITIES.map((p) => ({ label: p, value: p }))]
// every goal in progress, grouped by type; a goal no longer in progress stays shown while the task points to it
const goalOptions = computed(() => {
  const opts = goalsByType()
  if (task.value?.goal && !opts.some((o) => o.value === task.value.goal)) opts.push({ label: task.value.goal_title || task.value.goal, value: task.value.goal })
  return opts
})
const canRestore = computed(() => store.spaces.find((s) => s.name === task.value?.space)?.access === 'Write')
// an archived task is shown read-only; Restore is in the pane header
const writable = computed(() => canRestore.value && !task.value?.is_archived)
function tell() {
  const t = task.value
  emit('meta', { title: t.title, area: t.area, area_name: t.area_name, goal: t.goal, goal_title: t.goal_title,
    sub: !t.area && !t.goal ? 'Unfiled' : t.status === 'Someday' ? 'On the Someday list' : '', archived: !!t.is_archived, canRestore: canRestore.value,
    someday: writable.value && OPEN.includes(t.status) ? { doctype: 'Life Task', name: t.name } : null,
    tabs: [{ value: 'details', label: 'Details' }, { value: 'notes', label: 'Notes' }, { value: 'links', label: 'Links', count: links.value.length, noun: 'linked records' }] })
}
// the people and organisations of the task's space, to pick for "waiting on" and "delegated to" (issue 25)
const peopleOptions = ref([{ label: '—', value: '' }])
async function loadPeople() {
  const rows = await itemData.people.options({ space: task.value.space })
  peopleOptions.value = [{ label: '—', value: '' }, ...rows.map((r) => ({ label: r.label, value: r.value }))]
}
function pickWaiting(v) {
  const who = peopleOptions.value.find((o) => o.value === v)
  save({ waiting_on_person: v || null, ...(v && !(task.value.waiting_on || '').trim() ? { waiting_on: who.label } : {}) })
}

async function load() {
  try {
    ;[task.value, links.value] = await Promise.all([itemData.tasks.get({ task: props.name }), loadBacklinks('Life Task', props.name)])
    tell()
    loadPeople().catch(() => {})
  } catch (e) {
    emit('missing')
  }
}
// the source of a task, such as the Gmail thread an email digest proposed it from (source_url)
const safeSource = computed(() => /^https?:/i.test(task.value?.source_url || '') ? safeUrl(task.value.source_url) : '')
const sourceLabel = computed(() => (/mail\.google\.com/i.test(safeSource.value) ? 'Open in Gmail' : 'Open source'))
function openSource() { window.open(safeSource.value, '_blank', 'noopener,noreferrer') }

// notes save by themselves a moment after typing stops, and when the editor loses focus; the text being typed is never replaced
const notesState = ref('Saved')
let notesTimer = null
let notesDirty = false
function queueNotes() {
  notesDirty = true
  notesState.value = 'Typing…'
  clearTimeout(notesTimer)
  notesTimer = setTimeout(saveNotes, 1500)
}
async function saveNotes() {
  clearTimeout(notesTimer)
  if (!notesDirty) return
  notesDirty = false
  notesState.value = 'Saving…'
  const text = task.value.notes_md
  try {
    const res = await itemData.tasks.update({ task: props.name, values: { notes_md: text } })
    task.value = { ...res, notes_md: task.value.notes_md }
    notesState.value = 'Saved'
    emit('changed', task.value)
  } catch (e) {
    notesState.value = 'Not saved'
    notesDirty = true
    toast.error(errorText(e))
  }
}
onBeforeUnmount(saveNotes)

async function save(values) {
  try {
    task.value = await itemData.tasks.update({ task: props.name, values })
    tell()
    emit('changed', task.value)
  } catch (e) {
    toast.error(errorText(e))
    load()
  }
}
async function setStatus(status) {
  if (status === 'Waiting' && !(task.value.waiting_on || '').trim()) {
    askWaiting.value = true
    await nextTick()
    waitInput.value?.focus()
    toast.info('Say who or what this is waiting on.')
    return
  }
  try {
    task.value = await itemData.tasks.set_status({ task: props.name, status, waiting_on: task.value.waiting_on })
    askWaiting.value = false
    tell()
    emit('changed', task.value)
  } catch (e) {
    toast.error(errorText(e))
    load()
  }
}
async function carry() {
  const res = await tryCall(() => itemData.tasks.carry_forward({ task: props.name }))
  if (res) {
    toast.success(`Carried into ${res.month}/${res.year}.`)
    emit('changed', null)
    emit('close')
  }
}
async function archive() {
  const res = await tryCall(() => itemData.archive.set({ doctype: 'Life Task', name: props.name, archived: task.value.is_archived ? 0 : 1 }),
    task.value.is_archived ? 'Restored.' : 'Archived.')
  if (res) {
    emit('changed', null)
    emit('close')
  }
}
function remove() {
  dialog.danger({ title: 'Delete task', message: 'Move this task to the trash? It can be restored from Archive, Trash, for 30 days.', onConfirm: doRemove })
}
async function doRemove() {
  if ((await tryCall(() => itemData.trash.delete({ doctype: 'Life Task', name: props.name }), 'Moved to the trash. Restore it from Archive, Trash, within 30 days.')) !== undefined) {
    emit('changed', null)
    emit('close')
  }
}
onMounted(() => {
  loadLookups()
  load()
})
</script>
