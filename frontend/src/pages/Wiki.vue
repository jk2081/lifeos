<template>
  <PageHead :title="section ? 'Notes' : 'Wiki'">
    <template #sub>{{ section ? "The assistant's notes" : 'Pages an agent writes from your sources' }}, in {{ store.space }}. Every change the assistant makes is logged and can be undone.</template>
    <TabButtons v-if="section" :model-value="section" :options="NOTES_VIEWS" data-library-views />
    <TabButtons v-else-if="active === 'pages'" model-value="list" :options="VIEWS" data-wiki-views />
    <Button v-if="canWrite()" variant="solid" icon-left="lucide-plus" label="New page" data-new-wiki-page @click="newOpen = true" />
  </PageHead>
  <TabBar v-if="!section" inset :tabs="TABS" :model-value="active" label="Wiki sections" data-wiki-tabs @update:model-value="tab.set" />

  <!-- Pages -->
  <div v-if="shown('pages') && counts.rules" v-show="active === 'pages'">
    <ListView ref="pagesList" :title="null" noun="pages" screen="wiki" doctype="Life Note" :spec="PAGE_SPEC" :virtual="PAGE_VIRTUAL" :hidden="PAGE_HIDDEN"
      :quick="['title', 'area']" :synthetic="PAGE_SYNTHETIC" :fetch="fetchPages" :row-ref="(r) => 'note:' + r.name" :active="(r) => (r.query.tab || 'pages') === 'pages'"
      empty-title="No wiki pages yet." empty-hint="Add something to the Inbox with Add to wiki, and the agent writes pages from it. Or make one with New page.">
      <template #cell-title="{ row }"><div class="min-w-0"><div class="break-words font-medium text-ink-gray-9">{{ row.title }}<Badge v-if="row.is_rules" class="ml-2" theme="blue" label="Rules" /></div>
        <div class="line-clamp-1 text-sm text-ink-gray-6">{{ row.summary }}</div></div></template>
      <template #cell-area="{ row }"><span class="truncate text-ink-gray-7">{{ row.area_name || '' }}</span></template>
      <template #cell-_sources="{ row }"><span class="text-sm" :class="row.sources_count ? 'text-ink-gray-8' : 'text-ink-gray-6'">{{ row.sources_count || '—' }}</span></template>
      <template #cell-_updated="{ row }"><span class="whitespace-nowrap text-ink-gray-6">{{ short(row.modified, true) }}</span></template>
      <template #stack="{ row }"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
        <div class="text-sm text-ink-gray-6">{{ [row.summary, row.area_name, row.sources_count ? `${row.sources_count} source${row.sources_count === 1 ? '' : 's'}` : 'no sources', 'updated ' + short(row.modified, true)].filter(Boolean).join(' · ') }}</div></template>
    </ListView>
  </div>

  <!-- Changes -->
  <div v-if="shown('changes')" v-show="active === 'changes'">
    <ListView ref="changesList" :title="null" noun="changes" screen="wiki-changes" doctype="Life Wiki Change" :spec="CHANGE_SPEC" :virtual="CHANGE_VIRTUAL" :hidden="CHANGE_HIDDEN"
      :quick="['note', 'changed_by', 'changed_on']" :synthetic="CHANGE_SYNTHETIC" :fetch="fetchChanges" :row-ref="(r) => 'change:' + r.name" :row-label="(r) => r.note_title"
      :active="(r) => section === 'changes' || r.query.tab === 'changes'" :group-by="(r) => (r.changed_on ? long(r.changed_on.slice(0, 10), true) : '')" :groupable="false"
      empty-title="No changes yet." empty-hint="Each time a page is created, edited, undone or moved, a change is listed here.">
      <template #cell-note="{ row }"><div class="min-w-0"><div class="break-words font-medium text-ink-gray-9">{{ row.note_title }}</div>
        <div class="line-clamp-1 text-sm text-ink-gray-6">{{ row.change_note || '' }}</div></div></template>
      <template #cell-change_type="{ row }"><Badge :theme="row.reverted ? 'gray' : CHANGE_THEME[row.change_type]" :label="row.reverted ? row.change_type + ', undone' : row.change_type" /></template>
      <template #cell-changed_by="{ row }"><span class="truncate text-ink-gray-7">{{ row.by }}<template v-if="row.by_agent"> (agent)</template></span></template>
      <template #cell-changed_on="{ row }"><span class="whitespace-nowrap text-ink-gray-6">{{ dateTime(row.changed_on) }}</span></template>
      <template #cell-_source="{ row }"><span class="truncate text-sm text-ink-gray-7">{{ row.source_title || '' }}</span></template>
      <template #stack="{ row }"><div class="break-words text-base-medium text-ink-gray-9">{{ row.note_title }}</div>
        <div class="text-sm text-ink-gray-6">{{ [row.change_type + (row.reverted ? ', undone' : ''), row.by + (row.by_agent ? ' (agent)' : ''), dateTime(row.changed_on), row.source_title].filter(Boolean).join(' · ') }}</div>
        <div v-if="row.change_note" class="text-sm text-ink-gray-7">{{ row.change_note }}</div></template>
    </ListView>
  </div>

  <!-- Health -->
  <div v-if="shown('health')" v-show="active === 'health'" class="page-body" data-wiki-health>
    <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6">
      <span v-if="health">Checked {{ dateTime(health.computed_on) }} · {{ health.pages }} pages</span>
      <Button size="sm" icon-left="lucide-refresh-cw" label="Check now" :loading="healthBusy" data-health-refresh @click="loadHealth(1)" />
    </div>
    <template v-if="health">
      <section v-if="health.reports.length" data-health-reports><SectionHead>Reports from the agent</SectionHead>
        <Card flush><Row v-for="r in health.reports" :key="r.name" :pane="'note:' + r.name" :label="r.title"><div class="min-w-0 flex-1"><div class="text-base-medium text-ink-gray-9">{{ r.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ r.summary }}</div></div></Row></Card></section>
      <section data-health="orphans"><SectionHead :count="health.orphans.length">Orphans: no other page links to these</SectionHead>
        <Card flush><Row v-for="p in health.orphans" :key="p.name" :pane="'note:' + p.name" :label="p.title"><div class="text-base text-ink-gray-9">{{ p.title }}</div></Row>
          <Empty v-if="!health.orphans.length" title="No orphans." hint="Every page is linked from another one." /></Card></section>
      <section data-health="broken"><SectionHead :count="health.broken.length">Broken links</SectionHead>
        <Card flush><Row v-for="(b, i) in health.broken" :key="i" class="flex-wrap !items-center">
          <div class="min-w-0 flex-1"><div class="text-base text-ink-gray-9">[[{{ b.link }}]]</div><div class="text-sm text-ink-gray-6">in {{ b.page_title }}</div></div>
          <Button v-if="canWrite()" size="sm" label="Create this page" data-create-page @click="createFromLink(b.link)" />
          <Button size="sm" variant="ghost" label="Open the page" @click="openRef('note:' + b.page)" /></Row>
          <Empty v-if="!health.broken.length" title="No broken links." hint="Every [[link]] leads to a page." /></Card></section>
      <section v-if="health.ambiguous.length" data-health="ambiguous"><SectionHead :count="health.ambiguous.length">Ambiguous links: more than one page has this title</SectionHead>
        <Card flush><Row v-for="(b, i) in health.ambiguous" :key="i" :pane="'note:' + b.page" :label="b.page_title"><div class="text-base text-ink-gray-9">[[{{ b.link }}]] <span class="text-sm text-ink-gray-6">in {{ b.page_title }}</span></div></Row></Card></section>
      <section data-health="no_sources"><SectionHead :count="health.no_sources.length">Pages without sources</SectionHead>
        <Card flush><Row v-for="p in health.no_sources" :key="p.name" :pane="'note:' + p.name" :label="p.title"><div class="text-base text-ink-gray-9">{{ p.title }}</div></Row>
          <Empty v-if="!health.no_sources.length" title="Every page cites a source." /></Card></section>
      <section data-health="duplicates"><SectionHead :count="health.duplicates.length">Near-duplicate titles</SectionHead>
        <Card flush><Row v-for="(g, i) in health.duplicates" :key="i" class="flex-wrap !items-center"><div class="flex flex-wrap gap-2">
          <Button v-for="p in g" :key="p.name" size="sm" :label="p.title" @click="openRef('note:' + p.name)" /></div></Row>
          <Empty v-if="!health.duplicates.length" title="No near-duplicates." hint="No two pages share a title once case and punctuation are ignored." /></Card></section>
    </template>
    <div v-else class="flex flex-col gap-3"><Skeleton v-for="i in 4" :key="i" class="h-9 w-full rounded-4" /></div>
  </div>

  <!-- Rules -->
  <div v-if="shown('rules')" v-show="active === 'rules'" class="page-body" data-wiki-rules>
    <p class="mx-auto w-full max-w-[720px] text-sm text-ink-gray-6">The agent reads this page before writing. People edit it; agents cannot.</p>
    <NoteEditor v-if="rules" :key="rules.name" :note="rules" />
  </div>

  <NewRecord v-model="newOpen" title="New wiki page" action="Create page" :fields="NEW_FIELDS" :save="create" />
</template>
<script setup>
// The Wiki (UX fixes, set 4): Pages, Changes, Health and Rules. A page opens in the pane and on the full page as notes do.
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button, Skeleton, TabButtons } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import TabBar from '@/components/TabBar.vue'
import ListView from '@/components/ListView.vue'
import NoteEditor from '@/components/NoteEditor.vue'
import NewRecord from '@/components/NewRecord.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { dateTime, long, short } from '@/lib/dates'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { useUrlTab } from '@/lib/tabs'
import { NOTES_VIEWS } from '@/lib/nav'
import { onRecordChanged, openRef } from '@/lib/pane'

const router = useRouter()
const counts = ref({})
const TABS = computed(() => [{ value: 'pages', label: 'Pages', count: counts.value.pages }, { value: 'changes', label: 'Changes', count: counts.value.changes },
  { value: 'health', label: 'Health', count: counts.value.health_issues ?? undefined }, { value: 'rules', label: 'Rules' }])
const tab = useUrlTab('tab', TABS)
// In Library > Notes (UX fixes, set 6) the assistant's Changes, Health and Rules are views of the notes: `section` picks one
const props = defineProps({ section: { type: String, default: '' } })
const active = computed(() => props.section || tab.current.value)
const shown = (v) => (props.section ? props.section === v : tab.shown(v))
const VIEWS = [{ label: 'List', value: 'list' }, { label: 'Graph', value: 'graph', route: { path: '/library/notes', query: { by: 'assistant', view: 'graph', collection: 'Wiki' } } }]

const PAGE_SPEC = [{ key: 'area', field: 'area', kind: 'link', none: true }, { key: 'goal', field: 'goal', kind: 'link', none: true }]
const PAGE_VIRTUAL = []
const PAGE_HIDDEN = ['content_md', 'inbox_item', 'collection', 'is_rules', 'parent_note', 'sources', 'tags', 'also_in', 'archive_reason']
const PAGE_SYNTHETIC = [{ key: '_sources', label: 'Sources', width: '6rem', align: 'right', place: 'end' }, { key: '_updated', label: 'Updated', width: '8rem', place: 'end' }]
async function fetchPages({ params: p, filters, order_by, summary, start, page_length }) {
  const res = await api('wiki.pages', { space: store.space, area: p.area, goal: p.goal, filters, order_by, summary, start, page_length })
  return summary ? res : { rows: res.pages, total: res.total }
}

const CHANGE_SPEC = [{ key: 'page', field: 'note', kind: 'link' }, { key: 'by', field: 'changed_by', kind: 'link' }, { key: 'source', field: 'source_name', kind: 'value' },
  { key: 'from', field: 'changed_on', kind: 'from' }, { key: 'to', field: 'changed_on', kind: 'to' }]
const CHANGE_VIRTUAL = []
const CHANGE_HIDDEN = ['before_md', 'after_md', 'reverts', 'source_doctype', 'space']
const CHANGE_SYNTHETIC = [{ key: '_source', label: 'Source', width: 'minmax(0, 1fr)', place: 'end' }]
const CHANGE_THEME = { Created: 'green', Edited: 'blue', Reverted: 'amber', 'Moved to My notes': 'gray', 'Moved to Wiki': 'gray' }
async function fetchChanges({ params: p, filters, order_by, summary, start, page_length }) {
  const res = await api('wiki.changes', { space: store.space, note: p.page, by: p.by, source: p.source, from_date: p.from, to_date: p.to, filters, order_by, summary, start, page_length })
  return summary ? res : { rows: res.changes, total: res.total }
}

const health = ref(null)
const healthBusy = ref(false)
async function loadHealth(refresh = 0) {
  healthBusy.value = true
  const res = await tryCall(() => api('wiki.health', { space: store.space, refresh }))
  healthBusy.value = false
  if (res) {
    health.value = res
    counts.value = { ...counts.value, health_issues: res.orphans.length + res.broken.length + res.no_sources.length + res.duplicates.length }
  }
}
const rules = ref(null)
async function loadRules() { rules.value = await tryCall(() => api('library.get', { note: counts.value.rules })) }
async function loadOverview() {
  const res = await tryCall(() => api('wiki.overview', { space: store.space }))
  if (res) counts.value = { ...counts.value, ...res, health_issues: res.health_issues ?? counts.value.health_issues }
}

const newOpen = ref(false)
const NEW_FIELDS = computed(() => [{ name: 'title', label: 'Title', required: true }, { name: 'summary', label: 'Summary, one line', required: true },
  { name: 'area', label: 'Area', options: areaOptions() }])
async function create(v) {
  const res = await api('wiki.create_page', { space: store.space, title: v.title, summary: v.summary, area: v.area || undefined, content_md: '' })
  router.push(`/library/${res.name}`)
}
async function createFromLink(title) {
  const res = await tryCall(() => api('wiki.create_page', { space: store.space, title, summary: title, content_md: '' }), 'Page created.')
  if (res) { await loadHealth(1); openRef('note:' + res.name) }
}

watch(() => active.value, (t) => {
  if (t === 'health' && !health.value) loadHealth(0)
  if (t === 'rules' && !rules.value && counts.value.rules) loadRules()
}, { immediate: true })
watch(() => counts.value.rules, (r) => { if (r && active.value === 'rules' && !rules.value) loadRules() })
watch(() => store.space, () => { health.value = null; rules.value = null; loadOverview() })
onRecordChanged?.(() => loadOverview())
onMounted(() => { loadLookups(); loadOverview() })
</script>
