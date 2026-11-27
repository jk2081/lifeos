<template>
  <div class="flex flex-col" data-rule-list>
    <Row bare v-for="r in rules" :key="r.name" class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-3" data-rule-row :data-rule="r.name" :data-enabled="r.enabled" :data-builtin="r.builtin || ''">
      <div class="min-w-0 flex-[1_1_320px]">
        <div class="break-words text-base text-ink-gray-9" :class="!r.enabled && 'text-ink-gray-6 line-through'" data-rule-words>{{ r.words }}</div>
        <div class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-ink-gray-6">
          <span data-rule-used>used {{ r.used }} {{ r.used === 1 ? 'time' : 'times' }}<template v-if="r.last_used"> · last {{ r.last_used }}</template></span>
          <Badge v-if="r.all_sources" theme="gray" label="all sources" data-rule-all />
          <Badge v-if="r.builtin" theme="blue" label="built in" />
          <Badge v-else-if="r.made_by === 'Brain'" theme="gray" label="made by the Brain" />
          <Badge v-if="!r.enabled" theme="amber" label="off" data-rule-off />
        </div>
      </div>
      <Dropdown v-if="writable" :options="menu(r)"><Button label="Change" icon-right="lucide-chevron-down" data-rule-change /></Dropdown>
    </Row>
    <EmptyState v-if="!rules.length" :line="empty" data-rules-empty />
    <RuleDialog v-model:open="editing" :rule="current" :source="source" @saved="emit('changed')" />
  </div>
</template>
<script setup>
import EmptyState from '@/components/ui/EmptyState.vue'
import Row from '@/components/ui/Row.vue'
// Rules in plain words, each with one Change (edit, switch off or on, delete), used by Settings > Brain > Rules and a source's Rules tab (issue 117).
import { ref } from 'vue'
import { Badge, Button, Dropdown, toast } from 'frappe-ui'
import RuleDialog from '@/components/brain/RuleDialog.vue'
import { errorText } from '@/lib/api'
import { brainData } from '@/data/brain'

const props = defineProps({ rules: { type: Array, default: () => [] }, writable: Boolean, source: { type: String, default: '' }, empty: { type: String, default: 'No rules yet.' } })
const emit = defineEmits(['changed'])
const editing = ref(false)
const current = ref(null)

async function run(r, what) {
  try {
    await brainData.rules.change({ rule: r.name, what })
    toast.success(what === 'delete' ? 'Rule deleted.' : what === 'off' ? 'Switched off.' : 'Switched on.')
    emit('changed')
  } catch (e) {
    toast.error(errorText(e))
  }
}
const menu = (r) => [
  { label: 'Edit', icon: 'lucide-pencil', onClick: () => { current.value = r; editing.value = true } },
  r.enabled ? { label: 'Switch off', icon: 'lucide-toggle-left', onClick: () => run(r, 'off') } : { label: 'Switch on', icon: 'lucide-toggle-right', onClick: () => run(r, 'on') },
  ...(r.builtin ? [] : [{ label: 'Delete', icon: 'lucide-trash-2', onClick: () => run(r, 'delete') }]),
]
</script>
