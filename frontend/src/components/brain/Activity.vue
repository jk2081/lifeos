<template>
  <ListView ref="list" title="Brain" sub="Everything it did, so you can trust it. Open any line to see what came of it." noun="captures" screen="brain-activity" doctype="Life Inbox Item"
    :spec="SPEC" :tabs="TABS" :quick="['source_type']" :only="['source_type']" :sortable="false" :groupable="false" mode="feed" :fetch="fetch" :row-ref="rowRef" :row-key="rowKey" :row-label="(r) => r.title"
    :group-by="dayLabel" empty-title="Nothing has come in yet." empty-hint="What you capture or connect, and what the Brain did with it, will show up here."
    :empty-action="writable ? { label: 'Chat', icon: 'lucide-message-square', click: () => openChat() } : null" @loaded="(res) => (extra = res)">
    <template #above>
      <div class="flex flex-col gap-4" data-activity :data-total="extra?.all ?? 0">
        <Card v-if="plate" data-plate>
          <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <SectionHead>Left the plate this week</SectionHead>
            <p class="text-sm text-ink-gray-6" data-flow><b class="text-ink-gray-9" data-flow-in>{{ plate.in }}</b> came in · <b class="text-ink-gray-9" data-flow-out>{{ plate.piles.all }}</b> left the plate</p>
          </div>
          <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <RouterLink v-for="p in plate.order" :key="p" :to="{ path: '/brain/outbox', query: { pile: p } }"
              class="rounded-5 border border-outline-gray-2 px-3 py-2 hover:bg-surface-gray-1 focus-visible:focus-ring" data-plate-pile :data-pile="p" :data-n="plate.piles[p]">
              <span class="block text-sm text-ink-gray-6">{{ p }}</span>
              <b class="text-xl-semibold tabular-nums text-ink-gray-9">{{ plate.piles[p] }}</b>
            </RouterLink>
          </div>
          <p class="mt-2 text-sm text-ink-gray-6"><RouterLink class="text-ink-blue-8 hover:underline" to="/brain/outbox" data-outbox-link>Open the Outbox</RouterLink> for the full list, other periods and Bring back.</p>
        </Card>
        <div v-if="extra?.new_rules?.length" class="flex flex-col gap-1 text-sm text-ink-gray-6" data-new-rules>
          <div v-for="nr in extra.new_rules" :key="nr.name" data-new-rule>New rule: {{ nr.words.replace(/^When /, '').replace(': ', ' → ') }} ·
            <RouterLink class="text-ink-blue-8 hover:underline" :to="{ path: '/settings', query: { tab: 'rules' } }" data-new-rule-change>Change</RouterLink></div>
        </div>
      </div>
    </template>

    <template #row="{ row: r }">
      <!-- issue 125: what an agent did for you, in the same list as the captures -->
      <div v-if="r.kind === 'assistant'" class="flex flex-col gap-1.5 md:flex-row md:items-start md:gap-3" data-activity-row data-assistant-row :data-action="r.name" :data-asked-by="r.asked_by">
        <span class="w-12 flex-none text-sm tabular-nums text-ink-gray-6">{{ time(r.received_on) }}</span>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <Badge theme="blue" :label="r.agent_name" data-assistant-name />
            <Button class="relative !h-auto !whitespace-normal break-words !px-0 text-left text-base-medium" variant="ghost" :aria-expanded="opened === r.name" :label="r.title" data-assistant-open
              @click="opened = opened === r.name ? '' : r.name" />
          </div>
          <div class="mt-0.5 text-sm text-ink-gray-6" data-assistant-who>{{ r.agent_name }} · {{ r.asked_by === 'owner' ? 'you asked' : 'its idea' }}<template v-if="r.undone"> · undone</template></div>
          <div v-if="r.status === 'Failed'" class="mt-0.5 text-sm text-ink-red-8" data-assistant-error><span aria-hidden="true">✦</span> {{ r.error || 'It did not work.' }}</div>
          <div v-if="opened === r.name" class="mt-2 flex flex-col gap-1.5 rounded-md bg-surface-gray-2 p-2 text-sm text-ink-gray-7" data-assistant-drawer>
            <p v-if="r.request" class="break-words" data-assistant-request><b class="text-ink-gray-9">You asked:</b> “{{ r.request }}”</p>
            <p v-if="r.draft" class="whitespace-pre-wrap break-words" data-assistant-draft><b class="text-ink-gray-9">What was sent:</b> {{ r.draft }}</p>
            <p v-if="r.result" class="break-words" data-assistant-result><b class="text-ink-gray-9">The answer:</b> {{ r.result }}</p>
          </div>
        </div>
        <div class="flex flex-none flex-wrap items-center gap-2 max-md:pl-14">
          <Badge :theme="r.status === 'Failed' ? 'red' : 'green'" :label="r.status === 'Failed' ? 'Failed' : r.undone ? 'Undone' : 'Done'" />
          <Button v-if="r.can_undo && writable" class="relative" size="sm" label="Undo" data-assistant-undo @click="undo(r)" />
        </div>
      </div>
      <div v-else class="flex flex-col gap-1.5 md:flex-row md:items-start md:gap-3" data-activity-row :data-item="r.item" :data-outcome-of="r.outcome" :data-source="r.source">
        <span class="w-12 flex-none text-sm tabular-nums text-ink-gray-6">{{ time(r.received_on) }}</span>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <Badge theme="gray" :label="r.source" data-row-source />
            <!-- issue 118: a row opens the item in the side pane, the list still beside it; Open full page is in the pane -->
            <span class="break-words text-base-medium text-ink-gray-9" :data-ref="'inbox:' + r.item" data-row-item>{{ r.title }}</span>
          </div>
          <div class="mt-0.5 text-sm text-ink-gray-6" data-row-what>
            {{ SAYS[r.outcome] }}<template v-if="r.filed_by"> · <span class="text-ink-gray-9" data-row-filed-by>Filed by {{ r.filed_by }}</span></template><template v-if="r.area_name"> under <span class="inline-flex items-center gap-1 text-ink-gray-9" data-row-area><span class="size-2 rounded-full" :class="dot(r.area)" aria-hidden="true" />{{ r.area_name }}</span></template><template v-if="r.goal_title"> · goal <span class="text-ink-gray-9" data-row-goal>{{ r.goal_title }}</span></template>
          </div>
          <div v-if="r.outcome === 'failed'" class="mt-0.5 text-sm text-ink-red-8" data-row-reason><span aria-hidden="true">✦</span> {{ r.error || 'The agent could not read it.' }}</div>
          <div v-if="r.made.length" class="relative mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm" data-row-made>
            <template v-for="m in r.made" :key="m.doctype + m.name">
              <RefLink v-if="madeRef(m)" :to="madeRef(m)" class="text-ink-blue-8 hover:underline" data-made-link>{{ m.kind }}: {{ m.title }}</RefLink>
              <RouterLink v-else :to="madeTo(m)" class="text-ink-blue-8 hover:underline" data-made-link>{{ m.kind }}: {{ m.title }}</RouterLink>
            </template>
          </div>
        </div>
        <div class="flex flex-none flex-wrap items-center gap-2 max-md:pl-14">
          <Badge :theme="THEME[r.outcome]" :label="LABEL[r.outcome]" data-row-outcome />
          <Button v-if="r.outcome === 'failed' && writable" class="relative" size="sm" label="Retry" data-retry @click="retry(r)" />
        </div>
      </div>
    </template>
  </ListView>
</template>
<script setup>
// Brain > Activity (issue 18): what came in and what the Brain did with it, newest first, by day. The shared list (ListView): the tabs are what was
// done, the filters are source, goal and the rest of the fields, all kept in the address. A failed capture says why and can be retried. This week's
// Outbox piles sit on top, with the flow line; the Outbox page keeps the full list, other periods and Bring back.
import { computed, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import RefLink from '@/components/ui/RefLink.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Card from '@/components/ui/Card.vue'
import { openChat } from '@/lib/ask'
import { tryCall } from '@/lib/api'
import { brainData } from '@/data/brain'
import { canWrite, store } from '@/lib/store'
import { lookups } from '@/lib/lookups'
import { dotClass } from '@/lib/lens'
import { iso, long, time, addDays } from '@/lib/dates'
import { refOfRoute } from '@/lib/pane'

const TABS = { key: 'outcome', field: 'outcome', label: 'What the Brain did', items: [{ value: 'all', label: 'All' }, { value: 'filed', label: 'Filed on its own' },
  { value: 'waiting', label: 'Waiting for you' }, { value: 'dropped', label: 'Dropped' }, { value: 'failed', label: 'Failed' }, { value: 'assistant', label: 'Assistant' }] }
const SPEC = [{ key: 'outcome', field: 'outcome', kind: 'value' }, { key: 'source', field: 'source_type', kind: 'value' }, { key: 'area', field: 'area', kind: 'link' }]
const LABEL = { filed: 'Filed', decided: 'You decided', waiting: 'Waiting for you', dropped: 'Dropped', failed: 'Failed', working: 'Reading' }
const THEME = { filed: 'green', decided: 'blue', waiting: 'amber', dropped: 'gray', failed: 'red', working: 'gray' }
const SAYS = { filed: 'Filed on its own', decided: 'Filed after your decision', waiting: 'Waiting for your decision', dropped: 'Let go',
  failed: 'Could not be read', working: 'Still with the agent' }
const list = ref(null)
const extra = ref(null)
const opened = ref('')
const writable = computed(() => canWrite() && !store.isAgent)
const plate = computed(() => extra.value?.plate)
const dot = (a) => dotClass((lookups.areas || []).find((x) => x.name === a))
// a record made from a capture opens in the Drawer where it has a layer; the rest go to their page
const madeRef = (m) => refOfRoute(m.route) || (m.route ? null : `inbox:${m.name}`)
const madeTo = (m) => m.route
const rowRef = (r) => (r.kind === 'assistant' ? null : 'inbox:' + r.item)
const rowKey = (r) => (r.kind === 'assistant' ? 'a' + r.name : r.item)
function dayLabel(r) {
  const day = String(r.received_on).slice(0, 10)
  const today = iso(new Date())
  return day === today ? 'Today' : day === addDays(today, -1) ? 'Yesterday' : long(day)
}

// What an agent did sits in the same list: it is added to the first page, and the later pages (which ListView asks for by how many rows it holds) skip those rows.
let assistantRows = 0
async function fetch({ params: p, tab, start, page_length }) {
  const outcome = tab && tab !== 'all' ? tab : undefined
  const first = !start
  const res = await brainData.brain.activity({ space: store.space, outcome, source: p.source, area: p.area, start: first ? 0 : start - assistantRows, page_length })
  if (first) assistantRows = (res.assistant || []).length
  const rows = first ? [...res.rows, ...(res.assistant || [])].sort((a, b) => String(b.received_on).localeCompare(String(a.received_on))) : res.rows
  const counts = { all: res.all, ...res.counts }
  return { ...res, rows, total: outcome === 'assistant' ? res.total : res.total + assistantRows, tabs: counts }
}
async function undo(r) {
  if (await tryCall(() => brainData.agentPage.undo({ request: r.name, space: store.space }), 'Undone.')) list.value.reload()
}
async function retry(r) {
  if (await tryCall(() => brainData.inbox.retry({ item: r.item }), 'Sent back to the agent.')) list.value.reload()
}
</script>
