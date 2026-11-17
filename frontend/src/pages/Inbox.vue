<template>
  <ListView ref="list" title="Inbox" noun="inbox items" screen="inbox" doctype="Life Inbox Item" :spec="SPEC" :tabs="TABS" :quick="['source_type', 'area']"
    :synthetic="SYNTHETIC" :hidden="HIDDEN" :fetch="fetch" :row-ref="(r) => 'inbox:' + r.name"
    :empty-title="EMPTY[list?.tab] || 'The Inbox is empty.'" empty-hint="Drop a file above or forward something to your agent. What it proposes waits here for you."
    @loaded="(res) => (pendingTotal = res.pending_total)">
    <template #sub>{{ store.space }} · drop anything here, an agent proposes, you approve<template v-if="pendingTotal"> ·
      <span data-lv-sum>{{ pendingTotal }}</span> proposal{{ pendingTotal === 1 ? '' : 's' }} pending in this list</template> ·
      <RouterLink class="text-ink-gray-7 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9" :to="{ path: '/library/captures', query: { status: 'done' } }" data-finished-link>Finished items are in Sources</RouterLink></template>
    <template #above>
      <!-- set 7: items left too long, with suggested decisions to confirm -->
      <OldItems @changed="list?.reload()" />
      <!-- The drop zone. Files wait here until Add to Inbox creates the item they belong to; then each is uploaded, private, to that item. -->
      <section v-if="canWrite()" class="rounded-5 border border-dashed p-4" :class="over ? 'border-outline-gray-5 bg-surface-gray-3' : 'border-outline-gray-3 bg-surface-gray-1'"
        data-dropzone @dragover.prevent="over = true" @dragleave.prevent="over = false" @drop.prevent="onDrop">
        <input ref="picker" type="file" multiple class="hidden" aria-label="Choose files" @change="onPick" />
        <div v-if="!files.length" class="flex flex-col gap-0.5 pb-3 pt-1.5">
          <b class="text-base-medium text-ink-gray-9">Drop files here</b>
          <span class="text-sm text-ink-gray-6">A journal photo, a voice note, a PDF, anything. Or
            <Button class="!inline-flex !h-auto !px-0 align-baseline !text-sm underline" size="sm" variant="ghost" label="choose files" @click="picker.click()" /></span>
        </div>
        <div v-else class="chips">
          <Badge v-for="(f, i) in files" :key="i" size="lg">{{ f.name }} <span class="text-ink-gray-6">{{ fileSize(f.size) }}</span>
            <template #suffix><Button class="!size-4" size="sm" variant="ghost" icon="lucide-x" :label="'Remove ' + f.name" @click="files.splice(i, 1)" /></template></Badge>
          <Button size="sm" variant="outline" icon-left="lucide-plus" label="more" @click="picker.click()" />
        </div>
        <div class="mt-2.5 flex flex-wrap gap-2">
          <TextInput v-model="instruction" class="min-w-64 flex-1" :placeholder="INTENT_HINT[intent]" aria-label="Instruction" @keydown.enter="add" />
          <TabButtons v-model="intent" :options="INTENTS" aria-label="What to do with it" data-intent />
          <Select v-model="sourceType" class="w-36" :options="SOURCES" aria-label="Kind" />
          <Button variant="solid" :loading="busy" loading-text="Adding…" :disabled="!files.length && !text.trim()" label="Add to Inbox" @click="add" />
        </div>
        <Textarea v-if="showText" v-model="text" class="mt-2" :rows="3" placeholder="Paste or type text to file" aria-label="Text to file" />
        <Button v-else class="-ml-2 mt-2" size="sm" variant="ghost" label="Or paste text instead" @click="showText = true" />
      </section>
    </template>
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
      <NumLink v-if="row.pending" class="relative" :to="{ query: { ...route.query, open: 'inbox:' + row.name, focus: 'pending' } }" data-door="inbox-row">{{ row.pending }} of {{ row.proposals }} proposals pending</NumLink>
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
          <NumLink v-if="row.pending" class="relative text-sm" :to="{ query: { ...route.query, open: 'inbox:' + row.name, focus: 'pending' } }">{{ row.pending }} of {{ row.proposals }} proposals pending</NumLink>
        </div>
        <Badge :theme="THEME[row.status]" :label="row.status === 'To Review' ? 'To review' : row.status" />
      </div>
      <Button v-if="row.status === 'Failed' && canWrite()" class="relative mt-2" size="sm" label="Retry" @click="retry(row)" />
    </template>
  </ListView>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Avatar, Badge, Button, Select, TabButtons, TextInput, Textarea, toast } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import OldItems from '@/components/inbox/OldItems.vue'
import NumLink from '@/components/ui/NumLink.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { canWrite, refreshCounts, store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { fileKind, fileSize, uploadFile } from '@/lib/upload'
import { loadLookups } from '@/lib/lookups'
import { saveView, savedView } from '@/lib/views'

const SOURCES = ['Upload', 'Journal Photo', 'Voice Note', 'Email', 'Email Digest', 'Chat', 'Message', 'Web']
// what the agent does with it: propose records (Process), write the wiki (Add to wiki), or only make it searchable (Just keep)
const INTENTS = [{ label: 'Process', value: 'Process' }, { label: 'Add to wiki', value: 'Add to wiki' }, { label: 'Just keep', value: 'Just keep' }]
const INTENT_HINT = { Process: 'What should the agent do? For example: summarise and pull out to-dos', 'Add to wiki': 'Anything the agent should know for the wiki (optional)',
  'Just keep': 'A note to keep with it (optional). It is made searchable; nothing is proposed' }
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
// old links to the Done and All tabs open Sources, where finished items are
if (['Done', 'all'].includes(route.query.status)) router.replace({ path: '/library/captures', query: { ...route.query, status: route.query.status === 'Done' ? 'done' : undefined } })
const intent = ref(savedView('inbox-intent')?.intent || 'Process')
watch(intent, (v) => saveView('inbox-intent', { intent: v }))
const picker = ref(null)
const files = ref([])
const instruction = ref('')
const sourceType = ref('Upload')
const text = ref('')
const showText = ref(false)
const over = ref(false)
const busy = ref(false)
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

function guessSource(list) {
  if (sourceType.value !== 'Upload' || !list.length) return
  const kinds = list.map((f) => fileKind(f.name))
  if (kinds.every((k) => k === 'audio')) sourceType.value = 'Voice Note'
  else if (kinds.every((k) => k === 'image') && /journal/i.test(instruction.value)) sourceType.value = 'Journal Photo'
}
function onDrop(e) {
  over.value = false
  files.value.push(...e.dataTransfer.files)
  guessSource(files.value)
}
function onPick(e) {
  files.value.push(...e.target.files)
  e.target.value = ''
  guessSource(files.value)
}

async function add() {
  if (busy.value || (!files.value.length && !text.value.trim())) return
  busy.value = true
  try {
    guessSource(files.value)
    const title = files.value.length ? (files.value.length === 1 ? files.value[0].name : `${files.value[0].name} and ${files.value.length - 1} more`) : text.value.trim().split('\n')[0].slice(0, 80)
    const item = await api('inbox.create_item', {
      title, source_type: files.value.length ? sourceType.value : (sourceType.value === 'Upload' ? 'Message' : sourceType.value),
      space: store.space, instruction: instruction.value, raw_text: text.value, intent: intent.value,
    })
    for (const f of files.value) await uploadFile(f, 'Life Inbox Item', item.name)
    toast.success(intent.value === 'Just keep' ? 'Added. The agent will make it searchable and file it in Sources.' : 'Added to the Inbox. An agent will pick it up.')
    files.value = []
    instruction.value = ''
    text.value = ''
    showText.value = false
    sourceType.value = 'Upload'
    if (route.query.status === 'Waiting') list.value.reload()
    else router.push({ query: { status: 'Waiting' } })
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}

async function fetch({ params: p, tab, filters, order_by, summary, start, page_length }) {
  const res = await api('inbox.list', { space: store.space, status: STATUS[tab] ? JSON.stringify(STATUS[tab]) : undefined,
    source_type: p.source_type, area: p.area, from_date: p.from, to_date: p.to, filters, order_by, summary, start, page_length })
  if (summary) return res
  refreshCounts()
  return { rows: res.items, total: res.total, pending_total: res.pending_total, tabs: res.tabs }
}
async function retry(it) {
  if (await tryCall(() => api('inbox.retry', { item: it.name }), 'Sent back to the agent.')) list.value.reload()
}
onMounted(loadLookups)
// New > Capture opens the Inbox ready to take text or files (UX fixes, set 6)
watch(() => route.query.capture, (on) => {
  if (!on) return
  showText.value = true
  router.replace({ query: { ...route.query, capture: undefined } })
  setTimeout(() => document.querySelector('[aria-label="Text to file"] textarea, textarea[aria-label="Text to file"]')?.focus(), 50)
}, { immediate: true })
</script>
