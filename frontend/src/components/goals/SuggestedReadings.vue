<template>
  <div class="flex flex-col" data-suggested-readings>
    <Row v-for="r in rows" :key="r.name" class="!items-start" data-suggested-reading :data-reading="r.name">
      <div class="flex min-w-0 flex-1 flex-col gap-1">
        <div class="flex flex-wrap items-baseline gap-x-2">
          <span v-if="withGoal" class="text-base-medium text-ink-gray-9">{{ r.goal_title }}</span>
          <template v-if="editing !== r.name"><span class="text-base-medium tabular-nums text-ink-gray-9" data-reading-value>{{ fmt(r.value) }}{{ r.unit ? ' ' + r.unit : '' }}</span>
            <span class="text-sm text-ink-gray-6">on {{ short(r.date, true) }} · suggested by {{ BY[r.suggested_by] || r.suggested_by || 'the assistant' }}</span></template>
        </div>
        <div v-if="editing === r.name" class="flex flex-wrap items-end gap-2">
          <FormControl v-model="edit.value" class="w-32" type="number" label="Value" data-reading-edit-value />
          <DatePicker v-model="edit.date" class="w-40" format="D MMM YYYY" label="Date" />
        </div>
        <p v-if="r.excerpt" class="break-words text-sm text-ink-gray-7">“{{ r.excerpt }}”</p>
        <div v-if="r.source_name" class="relative"><Button size="sm" variant="ghost" icon-left="lucide-file-text" :label="r.source_title || 'Open the source'" data-reading-source
          @click="openSource(r)" /></div>
      </div>
      <div v-if="writable" class="relative flex shrink-0 flex-wrap justify-end gap-1.5 max-sm:flex-col">
        <template v-if="editing === r.name"><Button label="Cancel" @click="editing = ''" /><Button variant="solid" label="Confirm" data-reading-confirm-edited @click="confirmReading(r, edit)" /></template>
        <template v-else><Button label="Reject" data-reading-reject @click="reject(r)" /><Button label="Edit and confirm" data-reading-edit @click="startEdit(r)" />
          <Button variant="solid" label="Confirm" data-reading-confirm @click="confirmReading(r)" /></template>
      </div>
    </Row>
  </div>
</template>
<script setup>
// Suggested readings waiting for a person (set 7): Confirm, Edit and confirm, or Reject. Shared by the goal and the weekly review.
import { reactive, ref } from 'vue'
import { Button, DatePicker, FormControl } from 'frappe-ui'
import Row from '../ui/Row.vue'
import { tryCall } from '@/lib/api'
import { goalsData } from '@/data/goals'
import { short } from '@/lib/dates'
import { openRef, refOf } from '@/lib/pane'

defineProps({ rows: Array, writable: Boolean, withGoal: Boolean })
const emit = defineEmits(['changed'])
const BY = { Agent: 'an agent', Assistant: 'the assistant', Owner: 'you' }
const editing = ref('')
const edit = reactive({ value: '', date: '' })
const fmt = (v) => (Number.isInteger(Number(v)) ? String(Number(v)) : String(Number(Number(v).toFixed(2))))
function startEdit(r) {
  Object.assign(edit, { value: r.value, date: r.date })
  editing.value = r.name
}
async function confirmReading(r, values) {
  const res = await tryCall(() => goalsData.goals.confirm_reading({ reading: r.name, value: values ? values.value : undefined, date: values ? values.date : undefined }), 'Reading confirmed')
  if (res) { editing.value = ''; emit('changed', res) }
}
async function reject(r) {
  const res = await tryCall(() => goalsData.goals.reject_reading({ reading: r.name }), 'Reading rejected')
  if (res) emit('changed', res)
}
function openSource(r) {
  const ref_ = r.source_doctype === 'Life Inbox Item' ? `source:${r.source_name}` : refOf(r.source_doctype, r.source_name)
  if (ref_) openRef(ref_)
}
</script>
