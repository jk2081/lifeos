<template>
  <Row :pane="paneRef" :label="record.title" :class="!paneRef && record.route && 'cursor-pointer'" @click="!paneRef && record.route && openRoute(record.route)">
    <span :class="ICONS[record.kind] || 'lucide-file'" class="mt-0.5 size-4 shrink-0 text-ink-gray-6" aria-hidden="true" />
    <div class="min-w-0 flex-1">
      <div class="break-words text-base-medium text-ink-gray-9">{{ record.title }}</div>
      <div class="text-sm text-ink-gray-6">{{ record.kind }}<template v-if="when"> · {{ when }}</template></div>
    </div>
    <Badge :theme="THEME[record.state] || 'gray'" :label="record.state" data-record-state />
  </Row>
</template>
<script setup>
// A record linked to an inbox item on the item page (issue 10): what was made from it or what cites it, with where it
// stands now. It opens in the record pane, or goes to its own page when it has no pane.
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import Row from '../ui/Row.vue'
import { openRoute, refOfRoute } from '@/lib/pane'
import { dateTime, short } from '@/lib/dates'

const props = defineProps({ record: Object })
const ICONS = { Task: 'lucide-square-check', Note: 'lucide-file-text', 'Wiki page': 'lucide-book-open', Date: 'lucide-cake', Event: 'lucide-calendar',
  Meeting: 'lucide-calendar', Chat: 'lucide-message-square', Goal: 'lucide-target', Document: 'lucide-lock' }
const THEME = { Done: 'green', Open: 'blue', Doing: 'blue', Waiting: 'amber', Achieved: 'green', 'In Progress': 'blue', Dropped: 'gray', Archived: 'gray' }
const paneRef = computed(() => props.record.ref || refOfRoute(props.record.route))
const when = computed(() => {
  const d = props.record.date
  if (!d) return ''
  return d.length > 10 ? dateTime(d) : (props.record.kind === 'Task' ? 'due ' : '') + short(d, true)
})
</script>
