<template>
  <ListView ref="list" title="Chats" noun="chats" :filters="FILTERS" :columns="COLUMNS" :fetch="fetch" :row-ref="(r) => 'chat:' + r.name" :group-by="groupLabel"
    :watch-keys="['group']" default-sort="newest first" empty-title="No chats yet."
    empty-hint="Your agent logs each AI chat here with a summary and open items. Nothing needs review; open items become tasks only when you press Make task."
    @loaded="(res) => (extra = res)">
    <template #sub>AI chats in {{ store.space }}<template v-if="extra.with_open_items !== undefined"> ·
      <RouterLink class="num" :to="{ query: { ...route.query, open_items: '1', open: undefined } }" data-door="chats-open">{{ extra.with_open_items }} with open items</RouterLink></template></template>
    <template #bar>
      <span class="mt">Group by</span>
      <button v-for="g in ['day', 'area', 'project']" :key="g" class="ch" :class="{ on: groupBy === g }" type="button" :data-group="g" @click="setGroup(g)">{{ g[0].toUpperCase() + g.slice(1) }}</button>
    </template>
    <template #above>
      <div v-if="extra.by_area && extra.by_area.length" class="chips">
        <RouterLink v-for="c in extra.by_area" :key="c.area" class="pl n" :to="{ query: { ...route.query, area: c.area, open: undefined } }" data-door="chats-area">{{ c.area_name }}&nbsp;<span>{{ c.count }}</span></RouterLink>
      </div>
    </template>
    <template #cell-title="{ row }"><div class="ttl">{{ row.title }}</div><div class="mt">{{ [row.assistant, short(row.date), row.project_title].filter(Boolean).join(' · ') }}</div></template>
    <template #cell-area="{ row }"><RouterLink v-if="row.area" :to="`/areas/${row.area}`">{{ row.area_name }}</RouterLink></template>
    <template #cell-summary="{ row }"><div class="clamp">{{ plain(row.summary_md) }}</div></template>
    <template #cell-open="{ row }"><span v-if="row.open_count" class="pl o">{{ row.open_count }} open item{{ row.open_count === 1 ? '' : 's' }}</span><span v-else class="mt">None</span></template>
    <template #stack="{ row }">
      <div style="display: flex; gap: 10px; align-items: flex-start">
        <div style="flex: 1; min-width: 0"><div class="ttl">{{ row.title }}</div>
          <div class="mt">{{ [row.assistant, short(row.date), row.area_name, row.project_title].filter(Boolean).join(' · ') }}</div>
          <div class="mt clamp">{{ plain(row.summary_md) }}</div></div>
        <span v-if="row.open_count" class="pl o">{{ row.open_count }} open</span>
      </div>
    </template>
  </ListView>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ListView from '@/components/ListView.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { long, short, weekday } from '@/lib/dates'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'

const route = useRoute()
const router = useRouter()
const list = ref(null)
const extra = ref({})
const groupBy = computed(() => (['day', 'area', 'project'].includes(route.query.group) ? route.query.group : localStorage.getItem('lifeos-chat-group') || 'day'))
const FILTERS = computed(() => [
  { key: 'area', label: 'Area', all: 'All areas', options: [...areaOptions(), { value: 'none', label: 'No area' }] },
  { key: 'project', label: 'Project', all: 'All projects', options: [...lookups.projects.map((p) => ({ value: p.name, label: p.title })), { value: 'none', label: 'No project' }] },
  { key: 'open_items', label: 'Has open items', type: 'check' },
  { key: 'from', label: 'From', type: 'date' }, { key: 'to', label: 'To', type: 'date' },
  { key: 'archived', label: 'Include archived', type: 'check', quiet: true },
])
const COLUMNS = [{ key: 'title', label: 'Chat', width: 'minmax(180px, 1.2fr)', sort: 'title' }, { key: 'area', label: 'Area', width: '130px' },
  { key: 'summary', label: 'Summary', width: 'minmax(0, 2fr)' }, { key: 'open', label: 'Open items', width: '120px', align: 'right' }]
const plain = (md) => String(md || '').replace(/[#*_`>\[\]]/g, '').replace(/\s+/g, ' ').trim()
function groupLabel(c) {
  if (route.query.sort) return null
  if (groupBy.value === 'day') return `${weekday(c.date)}, ${long(c.date, true)}`
  return groupBy.value === 'area' ? c.area_name || 'No area' : c.project_title || 'No project'
}
async function fetch({ filters: f, sort, dir, start, page_length }) {
  const res = await api('chats.list', { space: store.space, area: f.area || undefined, project: f.project || undefined, open_items: f.open_items ? 1 : 0,
    from_date: f.from || undefined, to_date: f.to || undefined, include_archived: f.archived ? 1 : 0, group_by: groupBy.value,
    sort: sort || undefined, dir: dir || undefined, start, page_length })
  return { rows: res.chats, total: res.total, with_open_items: res.with_open_items, by_area: res.by_area }
}
function setGroup(g) {
  localStorage.setItem('lifeos-chat-group', g)
  router.push({ query: { ...route.query, group: g, sort: undefined, dir: undefined } })
}
onMounted(loadLookups)
</script>
<style scoped>
.clamp { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--ink-gray-8); font-size: 13.5px; }
a.pl:hover { background: var(--outline-gray-2); }
</style>
