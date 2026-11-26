<template>
  <PageHead title="Brain" sub="Everything it did, so you can trust it. Open any line to see what came of it." />
  <div class="page-body flex max-w-6xl flex-col gap-4" data-activity :data-total="data?.all ?? 0">
    <Card v-if="plate" data-plate>
      <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 class="text-base-medium text-ink-gray-9">Left the plate this week</h2>
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

    <div v-if="data?.new_rules?.length" class="flex flex-col gap-1 text-sm text-ink-gray-6" data-new-rules>
      <div v-for="nr in data.new_rules" :key="nr.name" data-new-rule>New rule: {{ nr.words.replace(/^When /, '').replace(': ', ' → ') }} ·
        <RouterLink class="text-ink-blue-8 hover:underline" :to="{ path: '/settings', query: { tab: 'rules' } }" data-new-rule-change>Change</RouterLink></div>
    </div>

    <div class="flex flex-wrap items-center gap-2" data-activity-filters>
      <div class="flex flex-wrap gap-1.5" role="group" aria-label="What the Brain did">
        <button v-for="f in FILTERS" :key="f.value" type="button" class="rounded-full border px-3 py-1 text-sm focus-visible:focus-ring"
          :class="outcome === f.value ? 'border-ink-gray-9 bg-ink-gray-9 text-surface-base' : 'border-outline-gray-2 text-ink-gray-8 hover:bg-surface-gray-1'"
          :aria-pressed="outcome === f.value" :data-outcome="f.value || 'all'" @click="setQuery({ outcome: f.value })">
          {{ f.label }} <span class="tabular-nums" data-outcome-count>{{ count(f.value) }}</span></button>
      </div>
      <select class="h-7 w-44 rounded border border-outline-gray-2 bg-surface-base px-2 text-sm text-ink-gray-8 focus-visible:focus-ring" :value="source" aria-label="Source" data-activity-source
        @change="setQuery({ source: $event.target.value })"><option v-for="o in sourceOptions" :key="o.value" :value="o.value">{{ o.label }}</option></select>
      <select class="h-7 w-44 rounded border border-outline-gray-2 bg-surface-base px-2 text-sm text-ink-gray-8 focus-visible:focus-ring" :value="area" aria-label="Area" data-activity-area
        @change="setQuery({ area: $event.target.value })"><option v-for="o in areaFilter" :key="o.value" :value="o.value">{{ o.label }}</option></select>
    </div>

    <Card v-if="loaded && !rows.length" class="py-2" data-activity-empty>
      <Empty :title="data?.all ? 'Nothing matches these filters.' : 'Nothing has come in yet.'">
        <p class="mt-1">{{ data?.all ? 'Clear a filter to see the rest.' : 'What you capture or connect, and what the Brain does with it, will show up here.' }}</p>
        <Button v-if="writable && !data?.all" class="mt-3" variant="solid" icon-left="lucide-plus" label="Capture" data-activity-capture @click="store.captureOpen = true" />
      </Empty>
    </Card>

    <section v-for="g in groups" :key="g.day" class="flex flex-col gap-1.5" data-activity-day :data-day="g.day">
      <h2 class="text-sm-medium text-ink-gray-6">{{ g.label }}</h2>
      <Card flush>
        <div v-for="r in g.rows" :key="r.item" class="flex flex-col gap-1.5 border-b border-outline-gray-1 py-3 last:border-b-0 md:flex-row md:items-start md:gap-3"
          data-activity-row :data-item="r.item" :data-outcome-of="r.outcome" :data-source="r.source">
          <span class="w-12 flex-none text-sm tabular-nums text-ink-gray-6">{{ time(r.received_on) }}</span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <Badge theme="gray" :label="r.source" data-row-source />
              <!-- issue 118: a row opens the item in the side pane, the list still beside it; Open full page is in the pane -->
              <button type="button" class="break-words text-left text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :aria-label="`Open ${r.title}`" :data-ref="'inbox:' + r.item"
                data-row-item @click="openRef('inbox:' + r.item)">{{ r.title }}</button>
            </div>
            <div class="mt-0.5 text-sm text-ink-gray-6" data-row-what>
              {{ SAYS[r.outcome] }}<template v-if="r.filed_by"> · <span class="text-ink-gray-9" data-row-filed-by>Filed by {{ r.filed_by }}</span></template><template v-if="r.area_name"> under <span class="inline-flex items-center gap-1 text-ink-gray-9" data-row-area><span class="size-2 rounded-full" :class="dot(r.area)" aria-hidden="true" />{{ r.area_name }}</span></template><template v-if="r.goal_title"> · goal <span class="text-ink-gray-9" data-row-goal>{{ r.goal_title }}</span></template>
            </div>
            <div v-if="r.outcome === 'failed'" class="mt-0.5 text-sm text-ink-red-8" data-row-reason><span aria-hidden="true">✦</span> {{ r.error || 'The agent could not read it.' }}</div>
            <div v-if="r.made.length" class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm" data-row-made>
              <RouterLink v-for="m in r.made" :key="m.doctype + m.name" :to="madeTo(m)" class="text-ink-blue-8 hover:underline" data-made-link>{{ m.kind }}: {{ m.title }}</RouterLink>
            </div>
          </div>
          <div class="flex flex-none flex-wrap items-center gap-2 max-md:pl-14">
            <Badge :theme="THEME[r.outcome]" :label="LABEL[r.outcome]" data-row-outcome />
            <Button v-if="r.outcome === 'failed' && writable" size="sm" label="Retry" data-retry @click="retry(r)" />
          </div>
        </div>
      </Card>
    </section>

    <div v-if="(data?.total ?? 0) > rows.length" class="flex justify-center"><Button label="Show earlier" :loading="more" data-activity-more @click="loadMore" /></div>
  </div>
</template>
<script setup>
// Brain > Activity (issue 18): what came in and what the Brain did with it, newest first, by day. Filters: source, area and
// what was done. A failed capture says why and can be retried. This week's Outbox piles sit on top, with the flow line; the
// Outbox page keeps the full list, other periods and Bring back.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import { tryCall } from '@/lib/api'
import { brainData } from '@/data/brain'
import { canWrite, store } from '@/lib/store'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { dotClass } from '@/lib/lens'
import { iso, long, time, addDays } from '@/lib/dates'
import { onRecordChanged, openRef, paneNav } from '@/lib/pane'

const FILTERS = [{ value: '', label: 'All' }, { value: 'filed', label: 'Filed on its own' }, { value: 'waiting', label: 'Waiting for you' },
  { value: 'dropped', label: 'Dropped' }, { value: 'failed', label: 'Failed' }]
const LABEL = { filed: 'Filed', decided: 'You decided', waiting: 'Waiting for you', dropped: 'Dropped', failed: 'Failed', working: 'Reading' }
const THEME = { filed: 'green', decided: 'blue', waiting: 'amber', dropped: 'gray', failed: 'red', working: 'gray' }
const SAYS = { filed: 'Filed on its own', decided: 'Filed after your decision', waiting: 'Waiting for your decision', dropped: 'Let go',
  failed: 'Could not be read', working: 'Still with the agent' }
const route = useRoute()
const router = useRouter()
const data = ref(null)
const rows = ref([])
const loaded = ref(false)
const more = ref(false)
const writable = computed(() => canWrite() && !store.isAgent)
const plate = computed(() => data.value?.plate)
const outcome = computed(() => String(route.query.outcome || ''))
const source = computed(() => String(route.query.source || ''))
const area = computed(() => String(route.query.area || ''))
const sourceOptions = computed(() => [{ label: 'Every source', value: '' }, ...(data.value?.sources || []).map((s) => ({ label: s, value: s }))])
const areaFilter = computed(() => [{ label: 'Every area', value: '' }, ...areaOptions().map((o) => ({ label: o.label, value: o.value }))])
const dot = (a) => dotClass((lookups.areas || []).find((x) => x.name === a))
const count = (v) => (v ? data.value?.counts?.[v] ?? 0 : data.value?.all ?? 0)
const madeTo = (m) => m.route || `/item/${m.name}`

const groups = computed(() => {
  const today = iso(new Date())
  const out = []
  for (const r of rows.value) {
    const day = String(r.received_on).slice(0, 10)
    let g = out[out.length - 1]
    if (!g || g.day !== day) out.push((g = { day, label: day === today ? 'Today' : day === addDays(today, -1) ? 'Yesterday' : long(day), rows: [] }))
    g.rows.push(r)
  }
  return out
})

function setQuery(patch) {
  const q = { ...route.query, ...patch }
  for (const k of Object.keys(q)) if (!q[k]) delete q[k]
  router.push({ query: q })
}
const args = () => ({ space: store.space, outcome: outcome.value || undefined, source: source.value || undefined, area: area.value || undefined })
async function load() {
  const res = await tryCall(() => brainData.brain.activity(args()))
  if (res) { data.value = res; rows.value = res.rows }
  loaded.value = true
}
async function loadMore() {
  more.value = true
  const res = await tryCall(() => brainData.brain.activity({ ...args(), start: rows.value.length }))
  if (res) rows.value = [...rows.value, ...res.rows]
  more.value = false
}
async function retry(r) {
  if (await tryCall(() => brainData.inbox.retry({ item: r.item }), 'Sent back to the agent.')) await load()
}
// j and k step through these rows while the pane is open
watch(rows, () => { paneNav.rows = rows.value.map((r) => 'inbox:' + r.item) }, { immediate: true })
onUnmounted(() => (paneNav.rows = []))
onRecordChanged(load)
onMounted(async () => { await loadLookups(); await load() })
watch(() => [store.space, route.query.outcome, route.query.source, route.query.area, store.lensArea], load)
</script>
