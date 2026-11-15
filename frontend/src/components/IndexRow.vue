<template>
  <Row :pane="ref_" :label="row.title || 'Untitled'" data-index-row @click="!ref_ && openRoute(row.route)">
    <div class="min-w-0 flex-1" data-row-main>
      <div class="break-words text-base-medium text-ink-gray-9">{{ row.title || 'Untitled' }}</div>
      <div class="text-sm text-ink-gray-6"><slot>{{ meta }}</slot><template v-if="row.pending"> ·
        <NumLink class="relative" :to="{ query: { ...$route.query, open: ref_, focus: 'pending' } }" data-door="row-pending">{{ row.pending }} of {{ row.proposals }} proposals pending</NumLink></template></div>
    </div>
    <slot name="pill"><Badge v-if="pill" :theme="pillTheme" :label="pill" /></slot>
  </Row>
</template>
<script setup>
// A row for a record from Life Index. Clicking it opens the record in the pane; the page does not change.
import { computed } from 'vue'
import { Badge } from 'frappe-ui'
import Row from './ui/Row.vue'
import NumLink from './ui/NumLink.vue'
import { short } from '@/lib/dates'
import { openRoute, refOf } from '@/lib/pane'

const props = defineProps({ row: Object, pill: String, pillTheme: { type: String, default: 'gray' }, showKind: Boolean, showArea: Boolean })
const KIND = { 'Task Done': 'Task completed', Inbox: 'Inbox item', 'Journal Page': 'Journal page', Document: 'Document' }
const ref_ = computed(() => refOf(props.row.ref_doctype, props.row.ref_name))
const meta = computed(() => {
  const r = props.row
  const parts = []
  if (props.showKind) parts.push(KIND[r.kind] || r.kind)
  if (props.showArea && r.area_name) parts.push(r.area_name)
  if (r.project_title) parts.push(r.project_title)
  parts.push(short(r.record_date))
  if (r.is_archived) parts.push('archived')
  return parts.join(' · ')
})
</script>
