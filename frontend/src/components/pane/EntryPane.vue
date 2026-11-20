<template>
  <template v-if="e">
    <template v-if="e.kind === 'event'">
      <div><div class="mb-1 text-sm-medium text-ink-gray-7">When</div><div class="text-base text-ink-gray-8">{{ when }}</div></div>
      <div v-if="e.description"><div class="mb-1 text-sm-medium text-ink-gray-7">Notes</div><div class="whitespace-pre-wrap text-base text-ink-gray-8">{{ e.description }}</div></div>
      <div class="text-sm text-ink-gray-6">{{ e.synced_to_google ? 'From Google Calendar.' : 'Kept on this site.' }}{{ e.repeats ? ' It repeats.' : '' }}</div>
    </template>
    <template v-else>
      <div><div class="mb-1 text-sm-medium text-ink-gray-7">Every year on</div><div class="text-base text-ink-gray-8">{{ e.day }} {{ MONTHS[e.month - 1] }}{{ e.year ? `, since ${e.year}` : '' }}</div></div>
      <div><div class="mb-1 text-sm-medium text-ink-gray-7">Kind</div><div class="text-base text-ink-gray-8">{{ e.date_kind }}{{ e.person_name ? ' · ' + e.person_name : '' }}</div></div>
    </template>
    <div v-if="writable" class="flex flex-wrap items-center gap-2"><Button theme="red" label="Remove" @click="remove" /></div>
  </template>
</template>
<script setup>
// An event or an important date in the pane.
import { computed, onMounted, ref } from 'vue'
import { Button, dialog } from 'frappe-ui'
import { api, db, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { MONTHS, long, time } from '@/lib/dates'

const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const e = ref(null)
const writable = computed(() => e.value?.space && store.spaces.find((s) => s.name === e.value.space)?.access === 'Write')
const when = computed(() => {
  const v = e.value
  const a = v.starts_on, b = v.ends_on
  if (v.all_day) return b && b.slice(0, 10) !== a.slice(0, 10) ? `${long(a, true)} to ${long(b, true)}` : `${long(a, true)}, all day`
  return `${long(a, true)}, ${time(a)}${b ? ' to ' + time(b) : ''}`
})
function remove() {
  dialog.danger({ title: 'Remove', message: `Remove “${e.value.title}”?`, confirmLabel: 'Remove', onConfirm: doRemove })
}
async function doRemove() {
  const ok = e.value.kind === 'event' ? await tryCall(() => api('calendar.delete_event', { event: e.value.name }), 'Removed.')
    : await tryCall(() => db.delete('Life Important Date', e.value.name), 'Removed.')
  if (ok !== undefined) {
    emit('changed')
    emit('close')
  }
}
onMounted(async () => {
  try {
    e.value = await api('calendar.entry', { kind: props.type, name: props.name })
    emit('meta', { title: e.value.title, fullPage: '/today/week?view=calendar' })
  } catch (err) {
    emit('missing')
  }
})
</script>
