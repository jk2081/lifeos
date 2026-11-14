<template>
  <div class="rw">
    <div class="grow">
      <RouterLink class="ttl" :to="row.route">{{ row.title || 'Untitled' }}</RouterLink>
      <div class="mt"><slot>{{ meta }}</slot></div>
    </div>
    <slot name="pill"><span v-if="pill" class="pl" :class="pillClass">{{ pill }}</span></slot>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { short } from '@/lib/dates'

const props = defineProps({ row: Object, pill: String, pillClass: { type: String, default: 'n' }, showKind: Boolean, showArea: Boolean })
const KIND = { 'Task Done': 'Task completed', Inbox: 'Inbox item', 'Journal Page': 'Journal page', Document: 'Document' }
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
