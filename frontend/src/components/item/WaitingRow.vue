<template>
  <Row :pane="r.ref" :label="r.title" class="!items-center" :class="active && '!bg-surface-gray-2'" data-list-row data-waiting-row :data-active="active || undefined" :data-ref="r.ref" :data-group="r.group" :data-task="r.task" @click.capture="(e) => !e.target.closest('button, a') && $emit('open', r)">
    <Avatar :label="r.who || r.title" size="sm" theme="gray" aria-hidden="true" class="flex-none" />
    <div class="min-w-0 flex-1">
      <div class="break-words text-base text-ink-gray-9" data-waiting-title>{{ r.title }}</div>
      <div class="text-sm" :class="r.tone === 'warn' ? 'text-ink-amber-9' : 'text-ink-gray-6'" data-waiting-sub>{{ sub }}</div>
    </div>
    <Button v-if="r.action === 'confirm' || r.looks_done" class="relative" size="sm" variant="solid" label="Confirm" :aria-label="`Confirm: ${r.title}`" data-waiting-confirm :loading="busy" @click="act('confirm')" />
    <Button v-else-if="r.action === 'nudge'" class="relative" size="sm" label="Nudge" :aria-label="`Nudge ${r.who}`" data-waiting-nudge :loading="busy" @click="act('nudge')" />
    <Dropdown v-else-if="r.action === 'decide'" :options="decideOptions" placement="bottom-end">
      <Button class="relative" size="sm" label="Nudged twice" icon-right="lucide-chevron-down" data-waiting-decide :aria-label="`${r.who} was nudged twice: choose`" />
    </Dropdown>
  </Row>
</template>
<script setup>
// One row of the Waiting list (issue 130): the person (initials), what, the check date, how it went, and at most one action: Confirm on a reply that looks like the answer,
// Nudge on a late one, and after two nudges Wait a week · Take it back · Drop it. Nothing is sent from here: a nudge makes a draft or the WhatsApp link.
import { computed, ref } from 'vue'
import { Avatar, Button, Dropdown } from 'frappe-ui'
import Row from '@/components/ui/Row.vue'
import { confirmDone, nudge, nudgeDecide } from '@/lib/handoff'
import { short } from '@/lib/dates'

const props = defineProps({ r: Object, active: Boolean })
const emit = defineEmits(['open', 'changed'])
const busy = ref(false)
const sub = computed(() => {
  const r = props.r
  if (r.looks_done || r.group === 'looks_done') return r.note ? `${r.note} · ${r.who}` : r.who
  return [r.who, r.check_by ? `check by ${short(r.check_by)}` : '', r.how].filter(Boolean).join(' · ')
})
const decideOptions = [{ label: 'Wait a week', onClick: () => decide('week') }, { label: 'Take it back', onClick: () => decide('plate') }, { label: 'Drop it', onClick: () => decide('drop') }]
async function decide(to) { await nudgeDecide(props.r.task, to); emit('changed') }
async function act(what) {
  busy.value = true
  try { if (what === 'confirm') await confirmDone(props.r.task, props.r.title); else await nudge(props.r.task) } finally { busy.value = false }
  emit('changed')
}
</script>
