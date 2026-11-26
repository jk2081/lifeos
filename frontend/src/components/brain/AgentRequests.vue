<template>
  <Card v-if="rows.length" flush data-agent-requests>
    <div v-for="r in rows" :key="r.name" class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2.5 border-b border-outline-gray-1 py-3 last:border-b-0" data-agent-request :data-request="r.name">
      <div class="min-w-0 flex-[1_1_320px]">
        <div class="flex flex-wrap items-center gap-2">
          <Badge theme="gray" :label="r.agent_name" data-request-agent />
          <Badge theme="blue" :label="r.action_label" />
          <span class="break-words text-base-medium text-ink-gray-9" data-request-title>{{ r.title }}</span>
        </div>
        <p class="mt-1 break-words text-sm text-ink-gray-7" data-request-who :data-asked-by="r.asked_by">{{ r.asked_by === 'owner' ? `You asked: “${r.request}”` : `${r.agent_name} suggests` }}</p>
        <p v-if="r.draft" class="mt-1 whitespace-pre-wrap break-words rounded-md bg-surface-gray-2 p-2 text-sm text-ink-gray-7" data-request-draft>{{ r.draft }}</p>
      </div>
      <div v-if="writable" class="flex items-center gap-2">
        <Button variant="solid" label="Approve" :disabled="busy.has(r.name)" data-request-approve @click="decide(r, 'approve')" />
        <Button label="No" :disabled="busy.has(r.name)" data-request-no @click="decide(r, 'no')" />
      </div>
    </div>
  </Card>
</template>

<script setup>
// What an agent waits to do until you say so (issue 85): the draft, with Approve and No. The same rows are in Needs you and on the agent's page.
import { computed, reactive } from 'vue'
import { Badge, Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import { tryCall } from '@/lib/api'
import { brainData } from '@/data/brain'
import { canWrite, store } from '@/lib/store'

defineProps({ rows: { type: Array, default: () => [] } })
const emit = defineEmits(['changed'])
const busy = reactive(new Set())
const writable = computed(() => canWrite() && !store.isAgent)

async function decide(r, decision) {
  busy.add(r.name)
  const res = await tryCall(() => brainData.agentPage.decide({ request: r.name, decision, space: store.space }), decision === 'approve' ? 'Approved' : 'Said no')
  busy.delete(r.name)
  if (res) emit('changed')
}
</script>
