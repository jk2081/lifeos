<template>
  <ListView ref="list" title="Inbox" noun="inbox items" :filters="FILTERS" :columns="COLUMNS" :fetch="fetch" :row-ref="(r) => 'inbox:' + r.name"
    default-sort="newest first" empty-title="The Inbox is empty." empty-hint="Drop a file above or forward something to your agent. What it proposes waits here for you."
    @loaded="(res) => (pendingTotal = res.pending_total)">
    <template #sub>{{ store.space }} · drop anything here, an agent proposes, you approve<template v-if="pendingTotal"> ·
      <span data-lv-sum>{{ pendingTotal }}</span> proposal{{ pendingTotal === 1 ? '' : 's' }} pending in this list</template></template>
    <template #above>
    <section v-if="canWrite()">
        <div class="drop" :class="{ over }" @dragover.prevent="over = true" @dragleave.prevent="over = false" @drop.prevent="onDrop">
          <input ref="picker" type="file" multiple style="display: none" @change="onPick" />
          <div v-if="!files.length" class="drop-hint">
            <b>Drop files here</b>
            <span class="mt">A journal photo, a voice note, a PDF, anything. Or <a href="#" @click.prevent="picker.click()">choose files</a>.</span>
          </div>
          <div v-else class="chips">
            <span v-for="(f, i) in files" :key="i" class="ch sm">{{ f.name }} <span class="mt">{{ fileSize(f.size) }}</span>
              <a href="#" aria-label="Remove" @click.prevent="files.splice(i, 1)">×</a></span>
            <a href="#" class="ch sm add" @click.prevent="picker.click()">+ more</a>
          </div>
          <div class="drop-form">
            <input v-model="instruction" class="inp" style="flex: 1 1 260px" placeholder="What should the agent do? For example: summarise and pull out to-dos"
              @keydown.enter="add" />
            <select v-model="sourceType" class="inp" aria-label="Kind">
              <option v-for="s in SOURCES" :key="s" :value="s">{{ s }}</option>
            </select>
            <button class="bt p" type="button" :disabled="busy || (!files.length && !text.trim())" @click="add">{{ busy ? 'Adding…' : 'Add to Inbox' }}</button>
          </div>
          <textarea v-if="showText" v-model="text" class="inp" rows="3" style="width: 100%; margin-top: 8px" placeholder="Paste or type text to file"></textarea>
          <a v-else href="#" class="mt" style="display: inline-block; margin-top: 8px" @click.prevent="showText = true">Or paste text instead</a>
        </div>
      </section>
    </template>
    <template #cell-title="{ row }">
      <div class="ttl">{{ row.title }}</div>
      <div class="mt">{{ describe(row) }}</div>
      <div v-if="row.status === 'Failed' && row.error" class="mt" style="color: var(--ink-red-9)">{{ row.error }}</div>
    </template>
    <template #cell-area="{ row }"><span class="mt">{{ row.area_name || '' }}</span></template>
    <template #cell-received_on="{ row }"><span class="mt">{{ dateTime(row.received_on) }}</span></template>
    <template #cell-proposals="{ row }">
      <a v-if="row.pending" href="#" class="num" data-door="inbox-row" @click.prevent="openRef('inbox:' + row.name, { focus: 'pending' })">{{ row.pending }} of {{ row.proposals }} proposals pending</a>
      <span v-else-if="row.proposals" class="mt">{{ row.proposals }} proposal{{ row.proposals === 1 ? '' : 's' }}, all decided</span>
    </template>
    <template #cell-status="{ row }">
      <button v-if="row.status === 'Failed' && canWrite()" class="bt s" type="button" style="margin-right: 8px" @click="retry(row)">Retry</button>
      <span class="pl" :class="PILL[row.status]">{{ row.status === 'To Review' ? 'To review' : row.status }}</span>
    </template>
    <template #stack="{ row }">
      <div style="display: flex; gap: 10px; align-items: flex-start">
        <div style="flex: 1; min-width: 0">
          <div class="ttl">{{ row.title }}</div>
          <div class="mt">{{ describe(row) }}</div>
          <div v-if="row.status === 'Failed' && row.error" class="mt" style="color: var(--ink-red-9)">{{ row.error }}</div>
          <a v-if="row.pending" href="#" class="num mt" @click.prevent="openRef('inbox:' + row.name, { focus: 'pending' })">{{ row.pending }} of {{ row.proposals }} proposals pending</a>
        </div>
        <span class="pl" :class="PILL[row.status]">{{ row.status === 'To Review' ? 'To review' : row.status }}</span>
      </div>
      <button v-if="row.status === 'Failed' && canWrite()" class="bt s" type="button" style="margin-top: 8px" @click="retry(row)">Retry</button>
    </template>
  </ListView>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { canWrite, refreshCounts, store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { fileKind, fileSize, uploadFile } from '@/lib/upload'
import { areaOptions, loadLookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'

const SOURCES = ['Upload', 'Journal Photo', 'Voice Note', 'Email', 'Chat', 'Message', 'Web']
// "Waiting for the agent" is two statuses: New and Processing
const STATUS = { 'To Review': ['To Review'], Waiting: ['New', 'Processing'], Failed: ['Failed'], Done: ['Done'] }
const FILTERS = computed(() => [
  { key: 'status', label: 'Status', all: 'Any status', options: [{ value: 'To Review', label: 'To review' }, { value: 'Waiting', label: 'Waiting for the agent' },
    { value: 'Failed', label: 'Failed' }, { value: 'Done', label: 'Done' }] },
  { key: 'source_type', label: 'Source', all: 'Any source', options: SOURCES.map((s) => ({ value: s, label: s })) },
  { key: 'area', label: 'Area', all: 'All areas', options: [...areaOptions(), { value: 'none', label: 'No area' }] },
  { key: 'from', label: 'From', type: 'date' }, { key: 'to', label: 'To', type: 'date' },
])
const COLUMNS = [
  { key: 'title', label: 'Item', sort: 'title' }, { key: 'area', label: 'Area', width: '120px' },
  { key: 'received_on', label: 'Received', width: '110px', sort: 'received_on' }, { key: 'proposals', label: 'Proposals', width: '190px' },
  { key: 'status', label: 'Status', width: 'max-content', sort: 'status', align: 'right', nowrap: true },
]
const PILL = { 'To Review': 'o', New: 'n', Processing: 'b', Failed: 'r', Done: 'g' }
const route = useRoute()
const router = useRouter()
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
      space: store.space, instruction: instruction.value, raw_text: text.value,
    })
    for (const f of files.value) await uploadFile(f, 'Life Inbox Item', item.name)
    toast.success('Added to the Inbox. An agent will pick it up.')
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

async function fetch({ filters: f, sort, dir, start, page_length }) {
  const res = await api('inbox.list', { space: store.space, status: f.status ? JSON.stringify(STATUS[f.status] || [f.status]) : undefined,
    source_type: f.source_type || undefined, area: f.area || undefined, from_date: f.from || undefined, to_date: f.to || undefined,
    sort: sort || undefined, dir: dir || undefined, start, page_length })
  refreshCounts()
  return { rows: res.items, total: res.total, pending_total: res.pending_total }
}
async function retry(it) {
  if (await tryCall(() => api('inbox.retry', { item: it.name }), 'Sent back to the agent.')) list.value.reload()
}
onMounted(loadLookups)
</script>

<style scoped>
.drop { border: 1px dashed var(--outline-gray-3); border-radius: 10px; padding: 16px; background: var(--surface-gray-1); }
.drop.over { border-color: var(--ink-blue-8); background: var(--surface-blue-2); }
.drop-hint { display: flex; flex-direction: column; gap: 2px; padding: 6px 0 12px; }
.drop-form { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
</style>
