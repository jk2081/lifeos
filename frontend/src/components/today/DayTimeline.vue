<template>
  <!-- Day, Calendar: one timeline. All-day items first, then what has a time in order (events and tasks planned at a time), the now line, then the tasks due that day. -->
  <Card flush class="!px-4" data-day-timeline :data-date="date">
    <Row v-for="r in rows" :key="r.key" :pane="r.ref" :label="r.title" class="!items-center" data-tl-row :data-tl-kind="r.kind" :data-now="r.kind === 'now' || undefined">
      <span class="w-16 shrink-0 text-sm tabular-nums" :class="r.kind === 'now' ? 'text-ink-blue-8' : 'text-ink-gray-6'">{{ r.lead }}</span>
      <span class="min-w-0 flex-1 break-words text-base" :class="r.kind === 'now' ? 'text-ink-blue-8' : 'text-ink-gray-9'">{{ r.title }}</span>
      <Badge v-if="r.kind === 'due'" theme="orange" label="task" />
    </Row>
    <Empty v-if="data && !items.length" title="Nothing on this day." data-timeline-empty>
      <p class="mt-1">Events, tasks planned at a time, tasks due and key dates show here.</p>
      <Button v-if="canWrite()" class="mt-3" variant="solid" icon-left="lucide-message-square" label="Chat" data-timeline-chat @click="openChat()" />
    </Empty>
  </Card>
</template>
<script setup>
import { computed, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import Empty from '@/components/Empty.vue'
import { chipType, itemLabel, itemRef, useCalendarRange } from '@/lib/calRange'
import { canWrite, store } from '@/lib/store'
import { openChat } from '@/lib/ask'
import { time } from '@/lib/dates'

const props = defineProps({ date: String })
const { data, itemsOn } = useCalendarRange(computed(() => [props.date, props.date]))
const items = computed(() => itemsOn(props.date))
const nowTime = ref(new Date().toTimeString().slice(0, 5))
const hm = (it) => String(time(it.start) || '').slice(0, 5)
const rows = computed(() => {
  const make = (it, kind, lead) => ({ key: kind + itemRef(it) + (it.start || ''), kind, lead, title: itemLabel(it), ref: itemRef(it), at: lead })
  const due = items.value.filter((it) => chipType(it) === 'due').map((it) => make(it, 'due', 'Due'))
  const timed = items.value.filter((it) => chipType(it) !== 'due' && !it.all_day && it.start).map((it) => make(it, 'timed', hm(it))).sort((a, b) => a.at.localeCompare(b.at))
  const allDay = items.value.filter((it) => chipType(it) !== 'due' && (it.all_day || !it.start)).map((it) => make(it, 'allday', 'All day'))
  if (props.date === store.today) {
    const now = { key: 'now', kind: 'now', lead: nowTime.value, title: 'now', ref: null, at: nowTime.value }
    const i = timed.findIndex((r) => r.at > nowTime.value)
    timed.splice(i < 0 ? timed.length : i, 0, now)
  }
  return [...allDay, ...timed, ...due]
})
</script>
