<template>
  <div class="rw rowlink" :class="{ on: ref_ && current && current.ref === ref_ }" tabindex="0" :data-ref="ref_" @click="open" @keydown.enter.self="open">
    <div class="grow">
      <div class="ttl">{{ row.title || 'Untitled' }}</div>
      <div class="mt"><slot>{{ meta }}</slot><template v-if="row.pending"> ·
        <a href="#" class="num" @click.prevent.stop="openRef(ref_, { focus: 'pending' })">{{ row.pending }} of {{ row.proposals }} proposals pending</a></template></div>
    </div>
    <slot name="pill"><span v-if="pill" class="pl" :class="pillClass">{{ pill }}</span></slot>
  </div>
</template>
<script setup>
// A row for a record from Life Index. Clicking it opens the record in the pane; the page does not change.
import { computed } from 'vue'
import { short } from '@/lib/dates'
import { current, openRef, openRoute, refOf } from '@/lib/pane'

const props = defineProps({ row: Object, pill: String, pillClass: { type: String, default: 'n' }, showKind: Boolean, showArea: Boolean })
const KIND = { 'Task Done': 'Task completed', Inbox: 'Inbox item', 'Journal Page': 'Journal page', Document: 'Document' }
const ref_ = computed(() => refOf(props.row.ref_doctype, props.row.ref_name))
function open(e) {
  if (e.target.closest && e.target.closest('a, button')) return
  ref_.value ? openRef(ref_.value) : openRoute(props.row.route)
}
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
