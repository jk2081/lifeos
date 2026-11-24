<template>
  <ListView ref="list" title="Inbox" noun="inbox items" screen="inbox" doctype="Life Inbox Item" :spec="SPEC" :tabs="TABS" :quick="['source_type', 'area']"
    :synthetic="SYNTHETIC" :hidden="HIDDEN" :fetch="fetch" :row-ref="(r) => 'inbox:' + r.name"
    :empty-title="EMPTY[list?.tab] || 'The queue is empty.'" empty-hint="Anything you capture is read by the agent and shows here until it is decided."
    @loaded="(res) => (pendingTotal = res.pending_total)">
    <template #sub>{{ manySpaces ? `${store.space} · Everything` : 'Everything' }} the agent has not finished, and what it asks you<template v-if="pendingTotal"> ·
      <span data-lv-sum>{{ pendingTotal }}</span> proposal{{ pendingTotal === 1 ? '' : 's' }} pending in this list</template> ·
      <RouterLink class="text-ink-gray-7 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9" :to="{ path: '/brain/captures', query: { status: 'done' } }" data-finished-link>Finished items are in Captures</RouterLink></template>
    <template #cell-title="{ row }">
      <div class="min-w-0">
        <div class="break-words font-medium text-ink-gray-9">{{ row.title }}</div>
        <div class="flex flex-wrap items-center gap-1 text-sm text-ink-gray-6"><Avatar v-if="row.filed_by" size="xs" :label="row.filed_by" />{{ describe(row) }}</div>
        <div v-if="row.status === 'Failed' && row.error" class="text-sm text-ink-red-8">{{ row.error }}</div>
      </div>
    </template>
    <template #cell-area="{ row }"><span class="truncate text-ink-gray-6">{{ row.area_name || '' }}</span></template>
    <template #cell-received_on="{ row }"><span class="whitespace-nowrap text-ink-gray-6">{{ dateTime(row.received_on) }}</span></template>
    <template #cell-_proposals="{ row }">
      <CountLink v-if="row.pending" class="relative" :to="{ query: { ...route.query, open: 'inbox:' + row.name, focus: 'pending' } }" data-door="inbox-row">{{ row.pending }} of {{ row.proposals }} proposals pending</CountLink>
      <span v-else-if="row.proposals" class="text-sm text-ink-gray-6">{{ row.proposals }} proposal{{ row.proposals === 1 ? '' : 's' }}, all decided</span>
    </template>
    <template #cell-status="{ row }">
      <div class="flex items-center gap-2">
        <Button v-if="row.status === 'Failed' && canWrite()" class="relative" size="sm" label="Retry" @click="retry(row)" />
        <Badge :theme="THEME[row.status]" :label="row.status === 'To Review' ? 'To review' : row.status" />
      </div>
    </template>
    <template #stack="{ row }">
      <div class="flex items-start gap-2.5">
        <div class="min-w-0 flex-1">
          <div class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ describe(row) }}</div>
          <div v-if="row.status === 'Failed' && row.error" class="text-sm text-ink-red-8">{{ row.error }}</div>
          <CountLink v-if="row.pending" class="relative text-sm" :to="{ query: { ...route.query, open: 'inbox:' + row.name, focus: 'pending' } }">{{ row.pending }} of {{ row.proposals }} proposals pending</CountLink>
        </div>
        <Badge :theme="THEME[row.status]" :label="row.status === 'To Review' ? 'To review' : row.status" />
      </div>
      <Button v-if="row.status === 'Failed' && canWrite()" class="relative mt-2" size="sm" label="Retry" @click="retry(row)" />
    </template>
  </ListView>
</template>

<script setup>
import { brainData } from '@/data/brain'
import { manySpaces } from '@/lib/lens'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Avatar, Badge, Button } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import CountLink from '@/components/ui/CountLink.vue'
import { tryCall } from '@/lib/api'
import { canWrite, refreshCounts, store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'

// status=Waiting in the URL is two statuses, New and Processing: "waiting for the agent"
const STATUS = { 'To Review': ['To Review'], Waiting: ['New', 'Processing'], Failed: ['Failed'] }
// the state tabs, on status=. The first is the default; "Waiting for the agent" is the two statuses New and Processing
// The Inbox is a queue: what is not finished. Finished items are in Sources (status=Done and all go there).
const TABS = { key: 'status', field: 'status', label: 'Inbox state', items: [{ value: 'To Review', label: 'To review' }, { value: 'Waiting', label: 'Waiting for the agent' },
  { value: 'Failed', label: 'Failed' }] }
const EMPTY = { 'To Review': 'Nothing to review.', Waiting: 'Nothing is waiting for the agent.', Failed: 'Nothing has failed.' }
const SPEC = [
  { key: 'status', field: 'status', kind: 'preset', labels: { Waiting: 'Waiting for the agent', 'To Review': 'To review' },
    presets: { 'To Review': () => ['status', '=', 'To Review'], Waiting: () => ['status', 'in', ['New', 'Processing']], Failed: () => ['status', '=', 'Failed'], Done: () => ['status', '=', 'Done'] } },
  { key: 'source_type', field: 'source_type', kind: 'value' }, { key: 'area', field: 'area', kind: 'link' },
  { key: 'from', field: 'received_on', kind: 'from' }, { key: 'to', field: 'received_on', kind: 'to' },
]
const SYNTHETIC = [{ key: '_proposals', label: 'Proposals', width: '12rem', place: 'end' }]
const HIDDEN = ['raw_text', 'transcript_md', 'summary_md', 'preview_image', 'claimed_by', 'claimed_on']
const THEME = { 'To Review': 'amber', New: 'gray', Processing: 'blue', Failed: 'red', Done: 'green' }
const route = useRoute()
const router = useRouter()
// old links to the Done and All tabs open Brain > Activity, where finished items are
if (['Done', 'all'].includes(route.query.status)) router.replace({ path: '/brain/captures', query: { ...route.query, status: route.query.status === 'Done' ? 'done' : undefined } })
const list = ref(null)
const pendingTotal = ref(0)

function describe(it) {
  const parts = []
  if (it.status === 'To Review' || it.status === 'Done') {
    parts.push(it.has_transcript ? 'Transcribed' : it.has_summary ? 'Summary ready' : 'Processed')
  } else if (it.status === 'Processing') parts.push(`Being processed${it.processed_by ? ' by ' + it.processed_by : ''}`)
  else if (it.status === 'New') parts.push('Waiting for an agent')
  parts.push(`${it.source_type}${it.filed_by ? ', filed by ' + it.filed_by : ''}`)
  return parts.join(' · ')
}

async function fetch({ params: p, tab, filters, order_by, summary, start, page_length }) {
  const res = await brainData.inbox.list({ space: store.space, status: STATUS[tab] ? JSON.stringify(STATUS[tab]) : undefined,
    source_type: p.source_type, area: p.area, from_date: p.from, to_date: p.to, filters, order_by, summary, start, page_length })
  if (summary) return res
  refreshCounts()
  return { rows: res.items, total: res.total, pending_total: res.pending_total, tabs: res.tabs }
}
async function retry(it) {
  if (await tryCall(() => brainData.inbox.retry({ item: it.name }), 'Sent back to the agent.')) list.value.reload()
}
onMounted(loadLookups)
</script>
