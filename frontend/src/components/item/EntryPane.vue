<template>
  <template v-if="e">
    <template v-if="e.kind === 'event'">
      <div><div class="mb-1 text-sm-medium text-ink-gray-7">When</div><div class="text-base text-ink-gray-8" data-event-when>{{ when }}</div></div>
      <div v-if="e.description"><div class="mb-1 text-sm-medium text-ink-gray-7">Details</div><div class="whitespace-pre-wrap text-base text-ink-gray-8">{{ e.description }}</div></div>
      <div class="text-sm text-ink-gray-6">{{ e.from_google ? 'From Google Calendar. Notes stay in Life OS.' : 'Kept on this site.' }}{{ e.repeats ? ' It repeats.' : '' }}{{ e.hidden ? ' Hidden in Life OS.' : '' }}</div>
      <!-- issue 99: notes are Frappe Comments on the Event; they are never written to Google -->
      <section data-event-notes>
        <div class="mb-1 text-sm-medium text-ink-gray-7">Notes</div>
        <div v-if="writable" class="mb-3 flex flex-col gap-2">
          <Textarea v-model="draft" :rows="2" placeholder="Add a note" aria-label="Add a note" data-note-box @keydown.meta.enter="addNote" @keydown.ctrl.enter="addNote" />
          <div><Button size="sm" variant="solid" label="Add note" :disabled="!draft.trim()" :loading="busy" data-note-add @click="addNote" /></div>
        </div>
        <ul class="flex flex-col gap-2">
          <li v-for="n in e.notes" :key="n.name" class="rounded-5 border border-outline-gray-2 px-3 py-2" data-note :data-agent="n.agent || undefined">
            <div class="whitespace-pre-wrap break-words text-base text-ink-gray-9">{{ n.text }}</div>
            <div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-gray-6">
              <span>{{ n.by }}</span><Badge v-if="n.agent" label="agent" /><span>{{ stamp(n.at) }}</span>
              <span class="flex-1" />
              <RouterLink v-if="n.task" class="text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="{ query: { ...route.query, open: 'task:' + n.task } }" data-note-task>Task made</RouterLink>
              <Button v-else-if="writable" size="sm" variant="ghost" label="Make a task" data-note-make-task @click="makeTask(n)" />
              <Button v-if="writable && !store.isAgent" size="sm" variant="ghost" label="Delete" :aria-label="'Delete note: ' + n.text" data-note-delete @click="removeNote(n)" />
            </div>
          </li>
        </ul>
        <EmptyState v-if="!e.notes.length" line="No notes yet. A note stays here, on this event, and is never sent to Google." data-notes-empty />
      </section>
    </template>
    <template v-else>
      <div><div class="mb-1 text-sm-medium text-ink-gray-7">Every year on</div><div class="text-base text-ink-gray-8">{{ e.day }} {{ MONTHS[e.month - 1] }}{{ e.year ? `, since ${e.year}` : '' }}</div></div>
      <div><div class="mb-1 text-sm-medium text-ink-gray-7">Kind</div><div class="text-base text-ink-gray-8">{{ e.date_kind }}{{ e.person_name ? ' · ' + e.person_name : '' }}</div></div>
    </template>
    <div v-if="writable" class="flex flex-wrap items-center gap-2">
      <!-- issue 100: a key date shows in Year and Month; the star corrects the Brain's judgement and teaches the key-date skill -->
      <Button v-if="e.kind === 'event'" icon-left="lucide-star" label="Key date" :variant="e.key_date ? 'solid' : 'subtle'" :aria-pressed="!!e.key_date" data-event-key @click="star" />
      <!-- an event from Google is hidden in Life OS, never deleted: nothing goes to Google (issue 99) -->
      <template v-if="e.kind === 'event' && e.from_google">
        <Button v-if="!e.hidden" label="Hide in Life OS" data-event-hide @click="hide(1)" />
        <Button v-else label="Show in Life OS" data-event-show @click="hide(0)" />
      </template>
      <Button v-else theme="red" label="Delete" data-event-delete @click="remove" />
    </div>
  </template>
</template>
<script setup>
import EmptyState from '@/components/ui/EmptyState.vue'
// An event or an important date in the pane. An event has Notes (Frappe Comments on it), Hide in Life OS when it came from Google, a Key date star, and
// Delete when it was made here. A repeat of a repeating event is `name@date` and has its own notes.
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { Badge, Button, Textarea, dialog } from 'frappe-ui'
import { tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { store } from '@/lib/store'
import { MONTHS, dateTime, eventWhen } from '@/lib/dates'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const route = useRoute()
const e = ref(null)
const draft = ref('')
const busy = ref(false)
const writable = computed(() => e.value?.space && store.spaces.find((s) => s.name === e.value.space)?.access === 'Write')
const when = computed(() => eventWhen(e.value.starts_on, e.value.ends_on, e.value.all_day))
const stamp = (at) => dateTime(at)
async function addNote() {
  const text = draft.value.trim()
  if (!text || busy.value) return
  busy.value = true
  const row = await tryCall(() => itemData.calendar.add_note({ event: e.value.name, text, occurrence: e.value.occurrence || undefined }))
  busy.value = false
  if (row) {
    e.value.notes.push(row)
    draft.value = ''
  }
}
async function makeTask(n) {
  const res = await tryCall(() => itemData.calendar.note_to_task({ note: n.name }), 'Task made.')
  if (res) {
    n.task = res.task
    emit('changed')
  }
}
function removeNote(n) {
  dialog.danger({ title: 'Delete note', message: 'Delete this note?', confirmLabel: 'Delete', onConfirm: async () => {
    if (await tryCall(() => itemData.calendar.delete_note({ note: n.name }), 'Deleted.') !== undefined) e.value.notes = e.value.notes.filter((x) => x.name !== n.name)
  } })
}
async function star() {
  const on = e.value.key_date ? 0 : 1
  if (await tryCall(() => itemData.calendar.set_key_date({ event: e.value.name, key: on }), on ? 'Marked as a key date.' : 'No longer a key date.') !== undefined) {
    e.value.key_date = !!on
    emit('changed')
  }
}
async function hide(on) {
  if (await tryCall(() => itemData.calendar.hide_event({ event: e.value.name, hidden: on }), on ? 'Hidden in Life OS.' : 'Shown again.') !== undefined) {
    e.value.hidden = !!on
    emit('changed')
    if (on) emit('close')
  }
}
function remove() {
  dialog.danger({ title: 'Delete event', message: `Delete “${e.value.title}”? This cannot be undone.`, confirmLabel: 'Delete', onConfirm: doRemove })
}
async function doRemove() {
  const ok = await tryCall(() => itemData.calendar.delete_event({ event: e.value.name }), 'Deleted.')  // an important date is a yearly Event
  if (ok !== undefined) {
    emit('changed')
    emit('close')
  }
}
onMounted(async () => {
  try {
    e.value = await itemData.calendar.entry({ kind: props.type, name: props.name })
    // no full page: an event has none of its own (issue 99)
    emit('meta', { title: e.value.title })
  } catch (err) {
    emit('missing')
  }
})
</script>
