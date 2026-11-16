<template>
  <ListView ref="list" title="Sources" noun="sources" screen="sources" doctype="Life Index" :spec="SPEC" :tabs="TABS" :views="views" :quick="['area', 'project', 'status']"
    :virtual="VIRTUAL" :synthetic="SYNTHETIC" :hidden="HIDDEN" :fetch="fetch" :row-ref="(r) => r.ref" :row-key="(r) => r.ref" :row-label="(r) => r.title || 'Untitled'"
    :quiet="['open_items', 'archived']" :flag-labels="{ open_items: 'With open items', archived: 'Include archived' }" :group-by="groupBy" :empty-title="EMPTY[list?.tab] || 'No sources yet.'" :watch-keys="['view']" @loaded="(res) => (extra = res)"
    empty-hint="Everything captured lands here: files, voice notes, photos, pasted text, links, emails and AI chats. Add some from the Inbox.">
    <template #sub>Everything captured in {{ store.space }}, finished or not. The Inbox holds what is still to do.<template v-if="extra.with_open_items !== undefined"> ·
      <NumLink :to="{ query: { ...route.query, open_items: '1', open: undefined } }" data-door="chats-open">{{ extra.with_open_items }} with open items</NumLink></template></template>
    <template #actions>
      <Button v-if="canWrite() && selected.length" :label="`Set area (${selected.length})`" icon-left="lucide-folder-input" data-refile @click="refileOpen = true" />
    </template>

    <template #cell-title="{ row }">
      <div class="flex min-w-0 items-start gap-2">
        <Checkbox v-if="canWrite()" class="relative mt-0.5" :model-value="selected.includes(row.ref)" :aria-label="'Select ' + row.title" @update:model-value="(v) => select(row, v)" />
        <div class="min-w-0"><div class="break-words font-medium text-ink-gray-9">{{ row.title || 'Untitled' }}</div>
          <div class="text-sm text-ink-gray-6">{{ describe(row) }}</div></div>
      </div>
    </template>
    <template #cell-kind="{ row }"><span class="flex min-w-0 items-center gap-1.5 text-ink-gray-7" :data-kind="row.kind"><span :class="ICON[row.kind] || 'lucide-file'" class="size-4 flex-none" aria-hidden="true" /><span class="truncate">{{ KIND_LABEL[row.kind] || row.kind }}</span></span></template>
    <template #cell-record_date="{ row }"><span class="whitespace-nowrap text-ink-gray-6">{{ short(row.received) }}</span></template>
    <template #cell-area="{ row }"><span class="truncate text-ink-gray-7">{{ row.area_name || '' }}</span></template>
    <template #cell-project="{ row }"><span class="truncate text-ink-gray-7">{{ row.project_title || '' }}</span></template>
    <template #cell-_status="{ row }"><Badge :theme="STATUS_THEME[row.status]" :label="row.status" data-source-status /></template>
    <template #cell-_made="{ row }">
      <NumLink v-if="row.open_count" class="relative text-sm" :to="{ query: { ...route.query, open: row.ref, ptab: 'items' } }" data-door="chat-items">{{ row.open_count }} open item{{ row.open_count === 1 ? '' : 's' }}</NumLink>
      <span v-else class="text-sm" :class="row.made ? 'text-ink-gray-8' : 'text-ink-gray-6'" data-made>{{ row.made ? `${row.made} made` : '—' }}</span></template>
    <template #stack="{ row }">
      <div class="flex items-start gap-2.5">
        <span :class="ICON[row.kind] || 'lucide-file'" class="mt-1 size-4 flex-none text-ink-gray-7" aria-hidden="true" />
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title || 'Untitled' }}</div>
          <div class="text-sm text-ink-gray-6">{{ [KIND_LABEL[row.kind] || row.kind, short(row.received), row.area_name, row.made ? `${row.made} made` : ''].filter(Boolean).join(' · ') }}</div></div>
        <Badge :theme="STATUS_THEME[row.status]" :label="row.status" />
      </div>
    </template>
    <!-- the day view of the Chats tab (the chats report), and the feed rows of any view that lists by day -->
    <template #row="{ row }">
      <div class="flex items-start gap-2.5">
        <span :class="ICON[row.kind] || 'lucide-file'" class="mt-1 size-4 flex-none text-ink-gray-7" aria-hidden="true" />
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ row.title || 'Untitled' }}</div>
          <div class="text-sm text-ink-gray-6">{{ describe(row) }}</div></div>
        <span v-if="row.made" class="whitespace-nowrap text-sm text-ink-gray-7">{{ row.made }} made</span>
      </div>
    </template>
    <!-- the grid: thumbnails, not full images -->
    <template #body="{ rows, loaded }">
      <div v-if="rows.length" class="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(160px,1fr))] max-sm:[grid-template-columns:repeat(2,minmax(0,1fr))]" data-source-grid>
        <div v-for="r in rows" :key="r.ref" class="relative flex flex-col overflow-hidden rounded-5 border border-outline-gray-2 bg-surface-base hover:bg-surface-gray-1" data-row data-grid-card>
          <button type="button" class="absolute inset-0 z-10 rounded-5 focus-visible:focus-ring" :aria-label="r.title || 'Untitled'" :data-ref="r.ref" @click="openRef(r.ref)" />
          <div class="flex aspect-[4/3] items-center justify-center bg-surface-gray-2">
            <img v-if="r.thumbnail" class="size-full object-cover" :src="r.thumbnail" :alt="r.title" loading="lazy" data-thumb />
            <span v-else :class="ICON[r.kind] || 'lucide-file'" class="size-8 text-ink-gray-6" aria-hidden="true" />
          </div>
          <div class="min-w-0 px-2.5 py-2"><div class="truncate text-sm-medium text-ink-gray-9">{{ r.title || 'Untitled' }}</div>
            <div class="truncate text-sm text-ink-gray-6">{{ [short(r.received), r.area_name].filter(Boolean).join(' · ') }}</div></div>
        </div>
      </div>
      <Card v-else-if="loaded"><Empty :title="EMPTY[list?.tab] || 'No sources yet.'" hint="Photos and scans show here as thumbnails." /></Card>
    </template>
  </ListView>

  <Dialog v-model:open="refileOpen" :title="`Set the area of ${selected.length} source${selected.length === 1 ? '' : 's'}`"
    :actions="[{ label: 'Set area', variant: 'solid', onClick: refile }]">
    <template #default>
      <div class="flex flex-col gap-3" data-refile-dialog>
        <FormControl v-model="refileArea" type="select" label="Area" :options="[{ label: 'Unfiled', value: '' }, ...areaOptions()]" />
        <p class="text-sm text-ink-gray-6">A project that does not belong to the new area is taken off.</p>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
// Sources: the library of every capture, finished or not (UX fixes, set 4). Inbox items and chat logs, read from Life Index.
// Tabs by kind; List by default, a Grid of thumbnails on Photos (and as a view on All), and By day on Chats (the old chats report).
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button, Checkbox, Dialog, FormControl } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import NumLink from '@/components/ui/NumLink.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long, short, weekday } from '@/lib/dates'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'

const TABS = { key: 'tab', field: 'media_kind', label: 'Kind of source', items: [{ value: 'all', label: 'All' }, { value: 'chats', label: 'Chats' },
  { value: 'voice', label: 'Voice' }, { value: 'documents', label: 'Documents' }, { value: 'photos', label: 'Photos' }, { value: 'articles', label: 'Articles' },
  { value: 'email', label: 'Email' }, { value: 'text', label: 'Text' }] }
const SPEC = [
  { key: 'tab', field: 'media_kind', kind: 'value' },
  { key: 'area', field: 'area', kind: 'link', none: true }, { key: 'project', field: 'project', kind: 'link', none: true },
  { key: 'from', field: 'record_date', kind: 'from' }, { key: 'to', field: 'record_date', kind: 'to' },
  { key: 'status', field: 'status', kind: 'value' }, { key: 'intent', field: 'intent', kind: 'value' },
  { key: 'system', field: 'source_system', kind: 'value' }, { key: 'assistant', field: 'assistant', kind: 'value' },
  { key: 'open_items', kind: 'flag' }, // chats that still have an open item (the old Chats tab "With open items")
  { key: 'archived', kind: 'flag' },
]
const VIRTUAL = [
  { fieldname: 'area', label: 'Area', fieldtype: 'Link', options: 'Life Area' },
  { fieldname: 'project', label: 'Project', fieldtype: 'Link', options: 'Life Project' },
  { fieldname: 'status', label: 'Status', fieldtype: 'Select', options: 'In Inbox\nDone\nFailed' },
  { fieldname: 'intent', label: 'Intent', fieldtype: 'Select', options: 'Process\nAdd to wiki\nJust keep' },
  { fieldname: 'source_system', label: 'System', fieldtype: 'Data' },
  { fieldname: 'assistant', label: 'Assistant', fieldtype: 'Select', options: 'Claude\nChatGPT\nCodex\nClaude Code\nOther' },
  { fieldname: 'record_date', label: 'Received', fieldtype: 'Date' },
]
const HIDDEN = ['ref_name', 'search_text', 'also_in_csv', 'tags_csv', 'record_owner', 'thumbnail', 'vault_locked', 'collection', 'kind', 'ref_doctype']
const SYNTHETIC = [{ key: '_status', label: 'Status', width: '7.5rem', place: 'end' }, { key: '_made', label: 'Made from it', width: '7rem', place: 'end' }]
const ICON = { Chat: 'lucide-messages-square', Voice: 'lucide-mic', Document: 'lucide-file-text', Photo: 'lucide-image', Article: 'lucide-globe',
  Email: 'lucide-mail', 'Email Digest': 'lucide-mails', Text: 'lucide-text' }
const KIND_LABEL = { 'Email Digest': 'Email digest' }
const STATUS_THEME = { 'In Inbox': 'amber', Done: 'green', Failed: 'red' }
const EMPTY = { chats: 'No chats yet.', voice: 'No voice notes yet.', documents: 'No documents yet.', photos: 'No photos yet.', articles: 'No articles yet.',
  email: 'No emails yet.', text: 'No text yet.' }

const route = useRoute()
const list = ref(null)
const selected = ref([])
const extra = ref({})
const refileOpen = ref(false)
const refileArea = ref('')
// the view choices depend on the tab: Photos opens on the grid; Chats has the report by day
const views = computed(() => {
  const t = route.query.tab || 'all'
  if (t === 'photos') return [{ key: 'grid', label: 'Grid', mode: 'custom' }, { key: 'list', label: 'List', mode: 'table' }]
  if (t === 'chats') return [{ key: 'list', label: 'List', mode: 'table' }, { key: 'day', label: 'By day', mode: 'feed' }]
  if (t === 'all') return [{ key: 'list', label: 'List', mode: 'table' }, { key: 'grid', label: 'Grid', mode: 'custom' }]
  return []
})
const groupBy = (r) => (route.query.view === 'day' && !route.query.sort ? `${weekday(r.received)}, ${long(r.received, true)}` : '')

function describe(r) {
  const what = r.kind === 'Chat' ? r.assistant : r.source_system && r.source_system !== 'upload' ? `from ${r.source_system}` : ''
  return [KIND_LABEL[r.kind] || r.kind, what, r.intent && r.intent !== 'Process' ? r.intent : '', r.project_title].filter(Boolean).join(' · ')
}
function select(row, on) {
  selected.value = on ? [...new Set([...selected.value, row.ref])] : selected.value.filter((x) => x !== row.ref)
}
let shown = []
async function fetch({ params: p, tab, filters, order_by, summary, start, page_length }) {
  const res = await api('sources.list', { space: store.space, tab: tab || 'all', area: p.area, project: p.project, from_date: p.from, to_date: p.to,
    status: p.status, intent: p.intent, system: p.system, assistant: p.assistant, open_items: p.open_items ? 1 : 0, include_archived: p.archived ? 1 : 0, filters, order_by, summary, start, page_length })
  if (summary) return res
  const rows = res.sources.map((r) => ({ ...r, record_date: r.received }))
  shown = start ? [...shown, ...rows] : rows
  return { rows, total: res.total, tabs: res.tabs, with_open_items: res.with_open_items }
}
async function refile() {
  const sources = shown.filter((r) => selected.value.includes(r.ref)).map((r) => ({ doctype: r.doctype, name: r.name }))
  const res = await tryCall(() => api('sources.refile', { sources, area: refileArea.value }), 'Area set.')
  if (res) {
    refileOpen.value = false
    selected.value = []
    list.value.reload()
  }
}
onMounted(loadLookups)
</script>
