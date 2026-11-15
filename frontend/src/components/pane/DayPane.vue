<template>
  <Card flush>
    <Row v-for="(it, i) in items" :key="i" :pane="REF[it.source] + ':' + it.name" :label="it.label || it.title" data-day-item>
      <span class="w-16 flex-none tabular-nums text-ink-gray-7">{{ it.all_day ? 'All day' : time(it.start) }}</span>
      <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ it.label || it.title }}</div>
        <div class="text-sm text-ink-gray-6">{{ SOURCE[it.source] }}<template v-if="it.multi_day"> · {{ short(it.date) }} to {{ short(it.end_date) }}</template></div></div>
    </Row>
    <Empty v-if="loaded && !items.length" title="Nothing on this day." hint="Add an event or an important date below." />
  </Card>
  <div v-if="canWrite()" class="flex flex-wrap items-center gap-2">
    <Button label="Add important date" @click="add('date')" />
    <Button variant="solid" label="Add event" @click="add('event')" />
  </div>
</template>
<script setup>
// One day of the calendar in the pane. Each entry opens its own record.
import { onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import Empty from '../Empty.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long, short, time, weekday } from '@/lib/dates'
import { onRecordChanged } from '@/lib/pane'

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
