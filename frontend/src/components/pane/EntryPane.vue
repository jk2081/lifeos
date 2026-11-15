<template>
  <template v-if="e">
    <template v-if="e.kind === 'event'">
      <div><div class="lbl">When</div><div>{{ when }}</div></div>
      <div v-if="e.description"><div class="lbl">Notes</div><div style="white-space: pre-wrap">{{ e.description }}</div></div>
      <div class="mt">{{ e.synced_to_google ? 'Pushed to Google Calendar.' : 'Kept on this site.' }}{{ e.repeats ? ' It repeats.' : '' }}</div>
    </template>
    <template v-else>
      <div><div class="lbl">Every year on</div><div>{{ e.day }} {{ MONTHS[e.month - 1] }}{{ e.year ? `, since ${e.year}` : '' }}</div></div>
      <div><div class="lbl">Kind</div><div>{{ e.date_kind }}{{ e.person_name ? ' · ' + e.person_name : '' }}</div></div>
    </template>
    <div v-if="writable" class="chips"><button class="bt s" type="button" style="color: var(--ink-red-9)" @click="remove">Remove</button></div>
  </template>
</template>
<script setup>
// An event or an important date in the pane.
import { computed, onMounted, ref } from 'vue'
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
async function remove() {
  if (!window.confirm(`Remove “${e.value.title}”?`)) return
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
    emit('meta', { title: e.value.title, fullPage: '/calendar' })
  } catch (err) {
    emit('missing')
  }
})
</script>
