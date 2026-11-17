<template>
  <div class="flex min-w-0 flex-col" data-note-editor :data-note="note.name">
    <div class="mx-auto w-full max-w-[720px]">
      <TextInput v-if="full && writable" v-model="note.title" variant="ghost" class="lv-title" aria-label="Title" data-note-title @update:model-value="queue" />
      <h2 v-else-if="full" class="read !text-2xl font-semibold !leading-tight text-ink-gray-9">{{ note.title }}</h2>
      <!-- filing as one line; it opens a small popover with the pickers -->
      <div class="mt-1 flex flex-wrap items-center gap-x-2 pl-1 text-sm text-ink-gray-6">
        <Popover v-if="writable" v-model:open="filingOpen" align="start">
          <template #trigger="{ open }">
            <Button variant="ghost" size="sm" class="!-ml-2 !h-auto !min-h-6 !whitespace-normal !text-left !font-normal !text-ink-gray-7" :label="filingLine"
              :aria-expanded="open" data-filing-line @click="loadNotes">{{ filingLine }}</Button>
          </template>
          <div class="flex w-72 flex-col gap-3 p-3" data-filing-popover>
            <div class="flex flex-col gap-1"><span class="text-sm-medium text-ink-gray-7">Area</span>
              <Pick :model-value="note.area" :options="areaOptions()" placeholder="area" @update:model-value="(v) => saveMeta({ area: v || '' })" /></div>
            <div class="flex flex-col gap-1"><span class="text-sm-medium text-ink-gray-7">Goal</span>
              <Pick :model-value="note.goal" :options="goalPick" placeholder="no goal" @update:model-value="(v) => saveMeta({ goal: v || '' })" /></div>
            <div class="flex flex-col gap-1"><span class="text-sm-medium text-ink-gray-7">Under the note</span>
              <Pick :model-value="note.parent_note" :options="parentOptions" placeholder="no parent note" @update:model-value="(v) => saveMeta({ parent_note: v || '' })" /></div>
            <div class="flex flex-col gap-1"><span class="text-sm-medium text-ink-gray-7">Also in</span>
              <div class="flex flex-wrap gap-1.5">
                <Button v-for="a in note.also_in" :key="a" size="sm" :label="areaName(a)" icon-right="lucide-x" tooltip="Remove" @click="saveMeta({ also_in: note.also_in.filter((x) => x !== a) })" />
                <Pick :model-value="null" :options="areaOptions().filter((o) => o.value !== note.area && !note.also_in.includes(o.value))" placeholder="another area" :clearable="false"
                  @update:model-value="(v) => saveMeta({ also_in: [...note.also_in, v] })" />
              </div></div>
          </div>
        </Popover>
        <span v-else data-filing-line>{{ filingLine }}</span>
        <span v-if="writable" class="text-ink-gray-6" data-save-state aria-live="polite">{{ saveState }}</span>
      </div>
    </div>
    <LiveEditor ref="editor" v-model="note.content_md" class="mt-2" :space="note.space" :links="note.links" :raw="raw" :readonly="!writable"
      doctype="Life Note" :docname="note.name" :compact="!full" label="Note text" @update:model-value="queue" @blur="flush" />

    <Dialog v-model:open="conflictOpen" title="This page changed while you were editing" size="2xl">
      <template #default>
        <div data-conflict>
        <p class="text-base text-ink-gray-8">Someone else (an agent, or you on another device) saved this page after you opened it. Your text is not saved yet and is still here.</p>
        <div v-if="showDiff && conflict" class="mt-3"><div class="mb-1 text-sm text-ink-gray-6">From the saved page to your text:</div>
          <DiffView :before="conflict.content_md" :after="note.content_md" /></div>
        </div>
      </template>
      <template #actions>
        <div class="flex flex-wrap justify-end gap-2">
          <Button :label="showDiff ? 'Hide changes' : 'View changes'" data-conflict-diff @click="showDiff = !showDiff" />
          <Button label="Reload" data-conflict-reload @click="reloadTheirs" />
          <Button variant="solid" label="Keep mine" data-conflict-keep @click="keepMine" />
        </div>
      </template>
    </Dialog>
  </div>
</template>
<script setup>
// One note or wiki page, ready to write in: the title (on the full page), the filing as one line, and the editor.
// It saves by itself a moment after typing stops, with a quiet "Saved". Each save sends the version it started from;
// when the page changed meanwhile nothing is overwritten and a dialog offers View changes, Keep mine and Reload.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Button, Dialog, Popover, TextInput } from 'frappe-ui'
import LiveEditor from './LiveEditor.vue'
import DiffView from './DiffView.vue'
import Pick from './Pick.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaName, areaOptions, loadLookups, lookups } from '@/lib/lookups'

const props = defineProps({ note: { type: Object, required: true }, full: Boolean, raw: Boolean, readonly: Boolean })
const emit = defineEmits(['saved'])
const note = props.note
const editor = ref(null)
const saveState = ref('Saved')
const filingOpen = ref(false)
const conflictOpen = ref(false)
const conflict = ref(null)
const showDiff = ref(false)
const allNotes = ref([])
let timer = null
let dirty = false
let saving = null

const writable = computed(() => !props.readonly && !note.is_archived && store.spaces.find((s) => s.name === note.space)?.access === 'Write')
const filingLine = computed(() => [note.area_name || 'Unfiled', note.goal_title || 'no goal',
  note.parent_title && 'in ' + note.parent_title, ...(note.also_in || []).map((a) => 'also in ' + areaName(a)),
  note.modified && 'edited ' + short(note.modified, true)].filter(Boolean).join(' · '))
const goalPick = computed(() => [{ label: 'No goal', value: '' }, ...(lookups.goals || []).map((g) => ({ value: g.name, label: `${g.goal_type} · ${g.title}` })),
  ...(note.goal && !(lookups.goals || []).some((g) => g.name === note.goal) ? [{ value: note.goal, label: note.goal_title || note.goal }] : [])])
const parentOptions = computed(() => allNotes.value.filter((n) => n.name !== note.name && n.parent_note !== note.name).map((n) => ({ value: n.name, label: n.title })))

async function loadNotes() {
  loadLookups()
  if (!allNotes.value.length) allNotes.value = (await tryCall(() => api('library.tree', { space: note.space })))?.notes || []
}

function queue() {
  if (!writable.value) return
  dirty = true
  saveState.value = 'Typing…'
  clearTimeout(timer)
  timer = setTimeout(flush, 1500) // autosave a moment after typing stops
}
async function flush(force = false) {
  clearTimeout(timer)
  if (saving) await saving
  if (!dirty || conflictOpen.value) return
  dirty = false
  saveState.value = 'Saving…'
  const body = { note: note.name, title: note.title, content_md: note.content_md, base_version: force ? undefined : note.version }
  saving = tryCall(() => api('library.save', body))
  const res = await saving
  saving = null
  if (!res) { saveState.value = 'Not saved'; dirty = true; return }
  if (res.conflict) {
    dirty = true
    conflict.value = res.current
    showDiff.value = false
    conflictOpen.value = true
    saveState.value = 'Not saved'
    return
  }
  Object.assign(note, { links: res.links, modified: res.modified, version: res.version, title: res.title })
  saveState.value = 'Saved'
  emit('saved', res)
}
async function keepMine() {
  conflictOpen.value = false
  dirty = true
  note.version = conflict.value?.version
  await flush()
}
function reloadTheirs() {
  conflictOpen.value = false
  dirty = false
  Object.assign(note, conflict.value)
  saveState.value = 'Saved'
}
async function saveMeta(values) {
  await flush()
  const res = await tryCall(() => api('library.save', { note: note.name, ...values }))
  if (res) {
    Object.assign(note, res)
    emit('saved', res)
  }
}
watch(() => note.name, () => { saveState.value = 'Saved' })
onBeforeUnmount(() => flush())
// the selected text, for "Selection to Someday" (an idea made from part of a note)
function selection() {
  const v = editor.value?.view?.()
  if (!v) return ''
  const r = v.state.selection.main
  return v.state.sliceDoc(r.from, r.to)
}
defineExpose({ flush, focus: () => editor.value?.focus(), selection })
</script>
