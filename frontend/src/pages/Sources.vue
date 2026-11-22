<template>
  <ListView ref="list" :title="embed ? null : place === 'all' ? 'All' : 'Captures'" noun="sources" :screen="embed ? embed.screen + '-captures' : screen" :fixed="embed?.fixed" :active="embed ? embed.active : true"
    :tabs-in-filter="!!embed" doctype="Life Index" :spec="SPEC" :tabs="TABS" :views="views" :quick="['area', 'goal', 'status']"
    :virtual="VIRTUAL" :synthetic="SYNTHETIC" :hidden="HIDDEN" :fetch="fetch" :row-ref="(r) => r.ref" :row-key="(r) => r.ref" :row-label="(r) => r.title || 'Untitled'"
    :quiet="['open_items', 'archived']" :flag-labels="{ sensitive: 'Sensitive only', open_items: 'With open items', archived: 'Include archived' }" :group-by="groupBy" :empty-title="EMPTY[list?.tab] || 'No sources yet.'" :watch-keys="['view', 'by']" @loaded="(res) => (extra = res)"
    empty-hint="Everything captured lands here: files, voice notes, photos, pasted text, links, emails and AI chats. Add some from the Inbox.">
    <template #sub>{{ place === 'all' ? 'Every note and capture' : 'Everything captured' }}{{ inSpace }}, finished or not. The Inbox holds what is still to do.<template v-if="extra.with_open_items !== undefined"> ·
      <NumLink :to="{ query: { ...route.query, open_items: '1', open: undefined } }" data-door="chats-open">{{ extra.with_open_items }} with open items</NumLink></template></template>
    <template #actions>
      <Select v-if="!embed" class="w-48" :model-value="route.query.by || ''" :options="WRITTEN_BY" aria-label="Written by" data-captures-by
        @update:model-value="(v) => router.push({ query: { ...route.query, by: v || undefined } })" />
      <!-- a sensitive document with its holder, number and expiry (the Vault before set 6) -->
      <Button v-if="canWrite() && !embed && list?.tab === 'documents'" variant="solid" icon-left="lucide-plus" label="Add document" data-add-document @click="openRef('vault:new')" />
      <Button v-if="canWrite() && selected.length" :label="`Set area (${selected.length})`" icon-left="lucide-folder-input" data-refile @click="refileOpen = true" />
    </template>

    <template #cell-title="{ row }">
      <div class="flex min-w-0 items-start gap-2">
        <Checkbox v-if="canWrite()" class="relative mt-0.5" :model-value="selected.includes(row.ref)" :aria-label="'Select ' + row.title" @update:model-value="(v) => select(row, v)" />
        <div class="min-w-0"><div class="flex flex-wrap items-center gap-1.5 break-words font-medium text-ink-gray-9"><Lock v-if="row.sensitive" />{{ row.title || 'Untitled' }}
          <Badge v-if="row.by_assistant && row.kind === 'Note'" size="sm" theme="blue" label="Kept by the assistant" /><Badge v-if="row.expiry" size="sm" :theme="row.expiry.state === 'expired' ? 'red' : 'amber'"
            :label="row.expiry.state === 'expired' ? 'Expired' : `Expires in ${row.expiry.days} days`" data-expiry-badge /></div>
          <div class="text-sm text-ink-gray-6">{{ describe(row) }}</div></div>
      </div>
    </template>
    <template #cell-kind="{ row }"><span class="flex min-w-0 items-center gap-1.5 text-ink-gray-7" :data-kind="row.kind"><span :class="ICON[row.kind] || 'lucide-file'" class="size-4 flex-none" aria-hidden="true" /><span class="truncate">{{ KIND_LABEL[row.kind] || row.kind }}</span></span></template>
    <template #cell-record_date="{ row }"><span class="whitespace-nowrap text-ink-gray-6">{{ short(row.received) }}</span></template>
    <template #cell-area="{ row }"><span class="truncate text-ink-gray-7">{{ row.area_name || '' }}</span></template>
    <template #cell-goal="{ row }"><span class="truncate text-ink-gray-7">{{ row.goal_title || '' }}</span></template>
    <template #cell-_status="{ row }"><Badge :theme="STATUS_THEME[row.status]" :label="row.status" data-source-status /></template>
    <template #cell-_made="{ row }">
      <NumLink v-if="row.open_count" class="relative text-sm" :to="{ query: { ...route.query, open: row.ref, ptab: 'items' } }" data-door="chat-items">{{ row.open_count }} open item{{ row.open_count === 1 ? '' : 's' }}</NumLink>
      <span v-else class="text-sm" :class="row.made ? 'text-ink-gray-8' : 'text-ink-gray-6'" data-made>{{ row.made ? `${row.made} made` : '—' }}</span></template>
    <template #stack="{ row }">
      <div class="flex items-start gap-2.5">
        <span :class="ICON[row.kind] || 'lucide-file'" class="mt-1 size-4 flex-none text-ink-gray-7" aria-hidden="true" />
        <div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-1.5 break-words text-base-medium text-ink-gray-9"><Lock v-if="row.sensitive" />{{ row.title || 'Untitled' }}</div>
          <div class="text-sm text-ink-gray-6">{{ [KIND_LABEL[row.kind] || row.kind, vaultLine(row), short(row.received), row.area_name, row.made ? `${row.made} made` : ''].filter(Boolean).join(' · ') }}</div></div>
        <Badge :theme="STATUS_THEME[row.status]" :label="row.status" />
      </div>
    </template>
    <!-- the day view of the Chats tab (the chats report), and the feed rows of any view that lists by day -->
    <template #row="{ row }">
      <div class="flex items-start gap-2.5">
        <span :class="ICON[row.kind] || 'lucide-file'" class="mt-1 size-4 flex-none text-ink-gray-7" aria-hidden="true" />
        <div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-1.5 break-words text-base-medium text-ink-gray-9"><Lock v-if="row.sensitive" />{{ row.title || 'Untitled' }}</div>
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
        <p class="text-sm text-ink-gray-6">A goal that does not belong to the new area is taken off.</p>
      </div>
    </template>
  </Dialog>
</template>
<script setup>
import { inSpace } from '@/lib/lens'
// Sources: the library of every capture, finished or not (UX fixes, set 4). Inbox items and chat logs, read from Life Index.
// Tabs by kind; List by default, a Grid of thumbnails on Photos (and as a view on All), and By day on Chats (the old chats report).
import { computed, h, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Checkbox, Dialog, FormControl, Select } from 'frappe-ui'
import { WRITTEN_BY } from '@/lib/nav'
import ListView from '@/components/ListView.vue'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import NumLink from '@/components/ui/NumLink.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long, short, weekday } from '@/lib/dates'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'

const KINDS = [{ value: 'all', label: 'All' }, { value: 'chats', label: 'Chats' },
  { value: 'voice', label: 'Voice' }, { value: 'documents', label: 'Documents' }, { value: 'photos', label: 'Photos' }, { value: 'pages', label: 'Journal pages' },
  { value: 'articles', label: 'Articles' }, { value: 'email', label: 'Email' }, { value: 'text', label: 'Text' }]
const SPEC = [
  { key: 'tab', field: 'media_kind', kind: 'value' },
  { key: 'area', field: 'area', kind: 'link', none: true }, { key: 'goal', field: 'goal', kind: 'link', none: true },
  { key: 'from', field: 'record_date', kind: 'from' }, { key: 'to', field: 'record_date', kind: 'to' },
  { key: 'status', field: 'status', kind: 'value' }, { key: 'intent', field: 'intent', kind: 'value' },
  { key: 'system', field: 'source_system', kind: 'value' }, { key: 'assistant', field: 'assistant', kind: 'value' },
  { key: 'open_items', kind: 'flag' }, // chats that still have an open item (the old Chats tab "With open items")
  { key: 'sensitive', kind: 'flag' }, // sensitive items only: Vault documents and what is marked sensitive (set 6)
  { key: 'archived', kind: 'flag' },
]
const VIRTUAL = [
  { fieldname: 'area', label: 'Area', fieldtype: 'Link', options: 'Life Area' },
  { fieldname: 'goal', label: 'Goal', fieldtype: 'Link', options: 'Life Goal' },
  { fieldname: 'status', label: 'Status', fieldtype: 'Select', options: 'In Inbox\nDone\nFailed' },
  { fieldname: 'intent', label: 'Intent', fieldtype: 'Select', options: 'Process\nAdd to wiki\nJust keep' },
  { fieldname: 'source_system', label: 'System', fieldtype: 'Data' },
  { fieldname: 'assistant', label: 'Assistant', fieldtype: 'Select', options: 'Claude\nChatGPT\nCodex\nClaude Code\nOther' },
  { fieldname: 'record_date', label: 'Received', fieldtype: 'Date' },
]
const HIDDEN = ['ref_name', 'search_text', 'also_in_csv', 'record_owner', 'thumbnail', 'vault_locked', 'collection', 'kind', 'ref_doctype']
const SYNTHETIC = [{ key: '_status', label: 'Status', width: '7.5rem', place: 'end' }, { key: '_made', label: 'Made from it', width: '7rem', place: 'end' }]
const ICON = { Chat: 'lucide-messages-square', Voice: 'lucide-mic', Document: 'lucide-file-text', Photo: 'lucide-image', Article: 'lucide-globe',
  Email: 'lucide-mail', 'Email Digest': 'lucide-mails', Text: 'lucide-text', 'Journal page': 'lucide-notebook-pen', Note: 'lucide-file-text' }
const KIND_LABEL = { 'Email Digest': 'Email digest' }
const STATUS_THEME = { 'In Inbox': 'amber', Done: 'green', Failed: 'red' }
// a sensitive item carries a lock (UX fixes, set 6)
const Lock = () => h('span', { class: 'lucide-lock size-3.5 flex-none text-ink-gray-6', role: 'img', 'aria-label': 'Sensitive', 'data-sensitive-lock': '' })
// a Vault document as a capture: its holder, the last four characters and its expiry
const vaultLine = (r) => (r.doctype === 'Life Vault Document' ? [r.doc_type, r.holder_name, r.number_last4 && 'ending ' + r.number_last4,
  r.expiry_date && 'expires ' + short(r.expiry_date, true)].filter(Boolean).join(' · ') : '')
const EMPTY = { notes: 'No notes yet.', pages: 'No journal pages yet.', chats: 'No chats yet.', voice: 'No voice notes yet.', documents: 'No documents yet.', photos: 'No photos yet.', articles: 'No articles yet.',
  email: 'No emails yet.', text: 'No text yet.' }

// inside a record page's tab (the goal page): { screen, space, fixed: { goal }, active(route), writable }
const props = defineProps({ embed: { type: Object, default: null }, place: { type: String, default: 'captures' },
  screen: { type: String, default: 'sources' } }) // the remembered view's name: Library > Documents and Chats keep their own
// Library > All adds the notes as a kind (UX fixes, set 6)
const TABS = computed(() => ({ key: 'tab', field: 'media_kind', label: 'Kind', items: props.place === 'all' && !props.embed
  ? [KINDS[0], { value: 'notes', label: 'Notes' }, ...KINDS.slice(1)] : KINDS }))
const route = useRoute()
const router = useRouter()
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
  return [KIND_LABEL[r.kind] || r.kind, what, vaultLine(r), r.intent && r.intent !== 'Process' ? r.intent : '', r.goal_title].filter(Boolean).join(' · ')
}
function select(row, on) {
  selected.value = on ? [...new Set([...selected.value, row.ref])] : selected.value.filter((x) => x !== row.ref)
}
let shown = []
async function fetch({ params: p, tab, filters, order_by, summary, start, page_length }) {
  const res = await api('sources.list', { space: props.embed?.space || store.space, scope: props.place === 'all' && !props.embed ? 'all' : 'captures',
    sensitive: p.sensitive ? 1 : 0, by: props.embed ? undefined : route.query.by || undefined, tab: tab || 'all', area: p.area, goal: p.goal, from_date: p.from, to_date: p.to,
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
