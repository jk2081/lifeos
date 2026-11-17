<template>
  <Alert v-if="total" theme="amber" :title="`${total} item${total === 1 ? '' : 's'} older than ${days} days ${total === 1 ? 'has a' : 'have'} suggested decision${total === 1 ? '' : 's'}`"
    description="Each says what to do with it and why: accept its proposals, park it as an idea, or discard it." data-old-items-banner :data-old-items-n="total">
    <template #actions><Button variant="solid" :label="`Review ${total}`" data-old-items-open @click="openBatch" /></template>
  </Alert>
  <Dialog v-model:open="open" :title="`Inbox items older than ${days} days`" size="3xl" data-old-items-dialog>
    <div class="flex flex-col gap-3">
      <p class="text-sm text-ink-gray-6">Tick the ones to act on, change any decision, then Confirm selected. Discarded items stay in the trash for 30 days.</p>
      <div class="flex items-center gap-2 border-b border-outline-gray-1 pb-2">
        <Checkbox :model-value="rows.length > 0 && chosen.size === rows.length" aria-label="Select all" @update:model-value="(v) => rows.forEach((r) => (v ? chosen.add(r.name) : chosen.delete(r.name)))" />
        <span class="text-sm text-ink-gray-7">{{ chosen.size }} of {{ rows.length }} selected</span>
      </div>
      <div class="flex max-h-[60vh] flex-col overflow-y-auto">
        <div v-for="r in rows" :key="r.name" class="flex flex-wrap items-start gap-3 border-b border-outline-gray-1 py-2.5 last:border-b-0" data-old-item :data-item="r.name">
          <Checkbox class="mt-0.5" :model-value="chosen.has(r.name)" :aria-label="'Select ' + r.title" @update:model-value="(v) => (v ? chosen.add(r.name) : chosen.delete(r.name))" />
          <div class="min-w-0 flex-[1_1_220px]">
            <div class="flex items-center gap-1.5 break-words text-base-medium text-ink-gray-9">
              <span v-if="r.sensitive" class="lucide-lock size-3.5 shrink-0 text-ink-gray-6" aria-label="Sensitive" />{{ r.title }}</div>
            <div class="text-sm text-ink-gray-6">{{ [r.received_on && 'came in ' + short(r.received_on.slice(0, 10), true), r.proposals.length ? `${r.proposals.length} proposal${r.proposals.length === 1 ? '' : 's'}` : 'nothing extracted'].filter(Boolean).join(' · ') }}</div>
            <div class="mt-1 text-sm text-ink-gray-8" data-old-item-reason>{{ r.reason }}</div>
          </div>
          <Select class="w-36" :model-value="r.decision" :options="DECISIONS" :aria-label="'Decision for ' + r.title" data-old-item-decision @update:model-value="(v) => (r.decision = v)" />
        </div>
        <Empty v-if="!rows.length" title="Nothing waiting." hint="Items older than the rule's days get a suggested decision each night." />
      </div>
    </div>
    <template #actions><div class="flex justify-end gap-2"><Button label="Close" @click="open = false" />
      <Button variant="solid" :label="`Confirm selected (${chosen.size})`" :disabled="!chosen.size" :loading="busy" data-old-items-confirm @click="confirmSelected" /></div></template>
  </Dialog>
</template>
<script setup>
// Inbox items left too long (set 7): the banner on the Inbox and the batch screen of suggested decisions. Confirm applies
// exactly the ticked items and toasts an Undo. ?decisions=1 (Reset's batch) opens it.
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Alert, Button, Checkbox, Dialog, Select, toast } from 'frappe-ui'
import Empty from '../Empty.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { short } from '@/lib/dates'

const emit = defineEmits(['changed'])
const DECISIONS = [{ label: 'Accept', value: 'Accept' }, { label: 'Park as an idea', value: 'Park' }, { label: 'Discard', value: 'Discard' }]
const route = useRoute()
const router = useRouter()
const total = ref(0)
const days = ref(7)
const rows = ref([])
const chosen = reactive(new Set())
const open = ref(false)
const busy = ref(false)
async function load() {
  if (store.isAgent) return
  const res = await tryCall(() => api('old_items.suggested', { space: store.space, area: store.lensArea || undefined, page_length: 500 }))
  if (!res) return
  total.value = res.total
  days.value = res.days
  rows.value = res.rows
  chosen.clear()
  res.rows.forEach((r) => chosen.add(r.name))
}
function openBatch() {
  open.value = true
}
watch(open, (v) => { if (!v && route.query.decisions) router.replace({ query: { ...route.query, decisions: undefined } }) })
async function confirmSelected() {
  busy.value = true
  try {
    const items = rows.value.filter((r) => chosen.has(r.name)).map((r) => ({ item: r.name, decision: r.decision }))
    const res = await api('old_items.apply', { items })
    open.value = false
    toast.success(`${res.done} item${res.done === 1 ? '' : 's'} dealt with.`, { action: { label: 'Undo', onClick: () => undo(res.undo) }, duration: 60000 })
    await load()
    emit('changed')
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}
async function undo(log) {
  if (await tryCall(() => api('old_items.undo', { log }), 'Undone')) { await load(); emit('changed') }
}
onMounted(async () => {
  await load()
  if (route.query.decisions) open.value = true
})
defineExpose({ load })
</script>
