<template>
  <div class="cd list">
    <div v-for="(it, i) in items" :key="i" class="rw rowlink" data-day-item @click="openRef(REF[it.source] + ':' + it.name)">
      <span class="when">{{ it.all_day ? 'All day' : time(it.start) }}</span>
      <div class="grow"><div class="ttl">{{ it.label || it.title }}</div><div class="mt">{{ SOURCE[it.source] }}<template v-if="it.multi_day"> · {{ short(it.date) }} to {{ short(it.end_date) }}</template></div></div>
    </div>
    <Empty v-if="loaded && !items.length" title="Nothing on this day." hint="Add an event or an important date below." />
  </div>
  <div v-if="canWrite()" class="chips">
    <button class="bt s" type="button" @click="add('date')">Add important date</button>
    <button class="bt p" type="button" @click="add('event')">Add event</button>
  </div>
</template>
<script setup>
// One day of the calendar in the pane. Each entry opens its own record.
import { onMounted, ref } from 'vue'
import Empty from '../Empty.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long, short, time, weekday } from '@/lib/dates'
import { onRecordChanged, openRef } from '@/lib/pane'

const SOURCE = { event: 'Event', important: 'Important date', task: 'Task due', vault: 'Vault document' }
const REF = { event: 'event', important: 'date', task: 'task', vault: 'vault' }
const props = defineProps({ name: String, type: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const items = ref([])
const loaded = ref(false)
async function load() {
  const res = await tryCall(() => api('calendar.get', { space: store.space, from_date: props.name, to_date: props.name }))
  items.value = res ? res.items : []
  loaded.value = true
}
// the Calendar screen owns the two dialogs
const add = (kind) => window.dispatchEvent(new CustomEvent('lifeos-calendar-add', { detail: { kind, date: props.name } }))
onRecordChanged(load)
onMounted(() => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(props.name)) return emit('missing')
  emit('meta', { title: `${weekday(props.name)}, ${long(props.name, true)}` })
  load()
})
</script>
<style scoped>
.when { width: 64px; flex: none; font-variant-numeric: tabular-nums; color: var(--ink-gray-7); }
</style>
