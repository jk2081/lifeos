<template>
  <ListView ref="list" title="Outbox" :path="[{ label: 'Brain', to: '/brain' }]" noun="records" screen="outbox" doctype="Life Exit" :spec="SPEC" :tabs="TABS" :quick="['kind']" :synthetic="SYNTHETIC"
    :hidden="HIDDEN" :fetch="fetch" :row-ref="rowRef" :row-label="(r) => r.title" :groupable="false" :watch-keys="['period', 'from', 'to']"
    :empty-title="EMPTY[tab] || 'Nothing left the plate in this period.'" empty-hint="Done, delegated, parked and discarded records show here, with when they left." @loaded="loaded">
    <template #sub><span data-outbox-sub>{{ manySpaces ? `${store.space} · What` : 'What' }} left your plate {{ PERIOD_LABEL[period] }}{{ range ? ` (${range})` : '' }}<span class="max-md:hidden"> · a record, not a place to work</span></span></template>
    <template #bar><TabButtons :model-value="period" :options="periods" data-outbox-period @update:model-value="setPeriod" /></template>
    <template #above>
      <Card v-if="chart.length" data-outbox-chart-card><InOutChart :weeks="chart" /></Card>
    </template>
    <template #cell-title="{ row }"><div class="flex min-w-0 items-center gap-1.5">
      <span v-if="row.sensitive" class="lucide-lock size-3.5 shrink-0 text-ink-gray-6" aria-label="Sensitive" data-sensitive-lock />
      <span class="break-words font-medium" :class="row.exists === false ? 'text-ink-gray-6' : 'text-ink-gray-9'">{{ row.title }}</span></div></template>
    <template #cell-kind="{ row }"><span class="text-ink-gray-7">{{ row.kind }}</span></template>
    <template #cell-pile="{ row }"><Badge :theme="THEME[row.pile] || 'gray'" :label="row.pile === 'In' ? 'Came in' : row.pile" data-outbox-pile /></template>
    <template #cell-_area="{ row }"><span class="truncate">{{ row.area_name }}</span></template>
    <template #cell-exited_on="{ row }"><span class="tabular-nums text-ink-gray-7">{{ dateTime(row.on) }}</span></template>
    <template #cell-_back="{ row }"><Button v-if="row.can_bring_back && canWrite()" class="relative" size="sm" label="Bring back" data-outbox-bring-back @click="bringBack(row)" /></template>
    <template #stack="{ row }">
      <div class="flex items-start gap-2.5" data-outbox-row>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5"><span v-if="row.sensitive" class="lucide-lock size-3.5 shrink-0 text-ink-gray-6" aria-label="Sensitive" />
            <span class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</span></div>
          <div class="text-sm text-ink-gray-6">{{ [row.kind, row.area_name, dateTime(row.on)].filter(Boolean).join(' · ') }}</div>
        </div>
        <Badge :theme="THEME[row.pile] || 'gray'" :label="row.pile === 'In' ? 'Came in' : row.pile" />
        <Button v-if="row.can_bring_back && canWrite()" class="relative" size="sm" label="Bring back" data-outbox-bring-back @click="bringBack(row)" />
      </div>
    </template>
  </ListView>
</template>
<script setup>
import { todayData } from '@/data/today'
import { manySpaces } from '@/lib/lens'
// Library > Outbox (set 7): what left the plate in a period, in four piles, and what came in; an 8-week chart of in against
// out. The only action is Bring back, where the record allows it (reopen, back from Someday, restore from the trash).
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, TabButtons } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import Card from '@/components/ui/Card.vue'
import InOutChart from '@/components/outbox/InOutChart.vue'
import { tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { dateTime, short } from '@/lib/dates'
import { onRecordChanged, refOf } from '@/lib/pane'
import { askScope } from '@/lib/ask'

const TABS = { key: 'pile', field: 'pile', label: 'Outbox pile', items: [{ value: 'Done', label: 'Done' }, { value: 'Delegated', label: 'Delegated' },
  { value: 'Parked', label: 'Parked' }, { value: 'Discarded', label: 'Discarded' }, { value: 'all', label: 'All out' }, { value: 'in', label: 'Came in' }] }
const EMPTY = { Done: 'Nothing was done in this period.', Delegated: 'Nothing was delegated in this period.', Parked: 'Nothing was parked in this period.',
  Discarded: 'Nothing was discarded in this period.', in: 'Nothing came in during this period.' }
const SPEC = [{ key: 'pile', field: 'pile', kind: 'value' }, { key: 'area', field: 'area', kind: 'link' }, { key: 'kind', field: 'kind', kind: 'value', label: 'Kind' }]
const SYNTHETIC = [{ key: '_area', label: 'Area', width: '10rem', place: 'end' }, { key: '_back', label: '', width: '8rem', align: 'right', place: 'end' }]
const HIDDEN = ['record_doctype', 'record_name', 'exited_by', 'reversed', 'reversed_on', 'note', 'area', 'space']
const PERIODS = [{ label: 'This week', value: 'week' }, { label: 'This month', value: 'month' }, { label: '12 weeks', value: '12weeks' }]
const PERIOD_LABEL = { week: 'this week', month: 'this month', '12weeks': 'in the last 12 weeks', custom: 'in the review\'s period' }
const THEME = { Done: 'green', Delegated: 'blue', Parked: 'amber', Discarded: 'gray', In: 'gray' }
const route = useRoute()
const router = useRouter()
const list = ref(null)
const chart = ref([])
const range = ref('')
const tab = computed(() => list.value?.tab || 'Done')
// set 8: a review's period comes as from= and to= (its days), shown as a fourth choice while it is open
const custom = computed(() => (route.query.from && route.query.to ? { from: String(route.query.from), to: String(route.query.to) } : null))
const period = computed(() => (custom.value ? 'custom' : ['week', 'month', '12weeks'].includes(route.query.period) ? route.query.period : 'week'))
const periods = computed(() => (custom.value ? [...PERIODS, { label: 'Review period', value: 'custom' }] : PERIODS))
const rowRef = (r) => (r.exists === false ? null : r.doctype === 'Life Inbox Item' ? `source:${r.record}` : refOf(r.doctype, r.record))
function setPeriod(v) {
  if (v === 'custom') return
  router.push({ query: { ...route.query, period: v === 'week' ? undefined : v, from: undefined, to: undefined, open: undefined } })
}
async function fetch({ params: p, tab: t, filters, start, page_length }) {
  const [res, c] = await Promise.all([todayData.outbox.list({ space: store.space, pile: t, period: custom.value ? undefined : period.value, area: p.area,
    filters: filters?.length ? filters : undefined, from_date: custom.value?.from, to_date: custom.value?.to, start, page_length }), start ? null : todayData.outbox.chart({ space: store.space, area: p.area })])
  if (c) chart.value = c.weeks
  return { rows: res.rows, total: res.total, tabs: res.tabs, from: res.from, to: res.to }
}
function loaded(res) {
  range.value = res?.from ? `${short(res.from)} to ${short(res.to)}` : ''
}
async function bringBack(r) {
  if (await tryCall(() => todayData.outbox.bring_back({ exit: r.name }), `${r.title} is back`)) list.value?.reload()
}
onRecordChanged(() => list.value?.reload())
askScope({ kind: 'space', label: 'Everything in this space' })
</script>
