<template>
  <ListView ref="list" title="Chats" noun="chats" screen="chats" doctype="Life Chat Log" :spec="SPEC" :tabs="TABS" :flag-labels="{ archived: 'Include archived' }"
    :quiet="['archived']" :quick="['area', 'project', 'assistant']" :synthetic="SYNTHETIC" :hidden="['summary_md', 'url']" :fetch="fetch" :row-ref="(r) => 'chat:' + r.name"
    :group-by="groupLabel" :watch-keys="['group']" empty-title="No chats yet."
    empty-hint="Your agent logs each AI chat here with a summary and open items. Nothing needs review; open items become tasks only when you press Make task."
    @loaded="(res) => (extra = res)">
    <template #sub>AI chats in {{ store.space }}<template v-if="extra.with_open_items !== undefined"> ·
      <NumLink :to="{ query: { ...route.query, open_items: '1', open: undefined } }" data-door="chats-open">{{ extra.with_open_items }} with open items</NumLink></template></template>
    <template #bar>
      <span class="text-sm text-ink-gray-6">Listed by</span>
      <TabButtons :model-value="groupBy" :options="GROUPS" data-group @update:model-value="setGroup" />
    </template>
    <template #above>
      <div v-if="extra.by_area && extra.by_area.length" class="chips">
        <RouterLink v-for="c in extra.by_area" :key="c.area" class="rounded-full focus-visible:focus-ring" :to="{ query: { ...route.query, area: c.area, open: undefined } }" data-door="chats-area">
          <Badge size="lg">{{ c.area_name }}&nbsp;<span class="tabular-nums text-ink-blue-8">{{ c.count }}</span></Badge></RouterLink>
      </div>
    </template>
    <template #cell-title="{ row }"><div class="min-w-0"><div class="break-words font-medium text-ink-gray-9">{{ row.title }}</div>
      <div class="text-sm text-ink-gray-6">{{ [row.assistant, short(row.date), row.project_title].filter(Boolean).join(' · ') }}</div></div></template>
    <template #cell-area="{ row }"><RouterLink v-if="row.area" class="relative truncate text-ink-blue-8 hover:underline" :to="`/areas/${row.area}`">{{ row.area_name }}</RouterLink></template>
    <template #cell-_summary="{ row }"><div class="line-clamp-2 text-sm text-ink-gray-8">{{ plain(row.summary_md) }}</div></template>
    <template #cell-_open="{ row }"><Badge v-if="row.open_count" theme="amber" :label="`${row.open_count} open item${row.open_count === 1 ? '' : 's'}`" /><span v-else class="text-sm text-ink-gray-6">None</span></template>
    <template #stack="{ row }">
      <div class="flex items-start gap-2.5">
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ [row.assistant, short(row.date), row.area_name, row.project_title].filter(Boolean).join(' · ') }}</div>
          <div class="line-clamp-2 text-sm text-ink-gray-6">{{ plain(row.summary_md) }}</div></div>
        <Badge v-if="row.open_count" theme="amber" :label="`${row.open_count} open`" />
      </div>
    </template>
  </ListView>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, TabButtons } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import NumLink from '@/components/ui/NumLink.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { long, short, weekday } from '@/lib/dates'
import { loadLookups } from '@/lib/lookups'

const GROUPS = [{ label: 'Day', value: 'day' }, { label: 'Area', value: 'area' }, { label: 'Project', value: 'project' }]
const SPEC = [{ key: 'area', field: 'area', kind: 'link' }, { key: 'project', field: 'project', kind: 'link' },
  { key: 'from', field: 'date', kind: 'from' }, { key: 'to', field: 'date', kind: 'to' }, { key: 'archived', kind: 'flag' }]
// the state tabs, on open_items=. All is the default; open_items=1 is "With open items"
const TABS = { key: 'open_items', field: '_open_items', label: 'Chats', items: [{ value: 'all', label: 'All' }, { value: '1', label: 'With open items' }] }
const SYNTHETIC = [{ key: '_summary', label: 'Summary', width: 'minmax(0, 2fr)', place: 'end' }, { key: '_open', label: 'Open items', width: '8rem', align: 'right', place: 'end' }]
const route = useRoute()
const router = useRouter()
const list = ref(null)
const extra = ref({})
// the headings the chats are listed under: by day, area or project. It is part of the list's query, so it is remembered with it.
const groupBy = computed(() => (['day', 'area', 'project'].includes(route.query.group) ? route.query.group : 'day'))
const plain = (md) => String(md || '').replace(/[#*_`>\[\]]/g, '').replace(/\s+/g, ' ').trim()
function groupLabel(c) {
  if (route.query.sort) return ''
  if (groupBy.value === 'day') return `${weekday(c.date)}, ${long(c.date, true)}`
  return groupBy.value === 'area' ? c.area_name || 'No area' : c.project_title || 'No project'
}
async function fetch({ params: p, tab, filters, order_by, summary, start, page_length }) {
  const res = await api('chats.list', { space: store.space, area: p.area, project: p.project, open_items: tab === '1' ? 1 : 0, from_date: p.from, to_date: p.to,
    include_archived: p.archived ? 1 : 0, group_by: groupBy.value, filters, order_by, summary, start, page_length })
  const tabs = res.tabs && { all: res.tabs.all, 1: res.tabs.open }
  return summary ? { ...res, tabs } : { rows: res.chats, total: res.total, with_open_items: res.with_open_items, by_area: res.by_area, tabs }
}
const setGroup = (g) => router.push({ query: { ...route.query, group: g, sort: undefined, dir: undefined, all: undefined } })
onMounted(loadLookups)
</script>
