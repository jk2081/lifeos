<template>
  <PageHead title="Inbox" :sub="headSub" />
  <div class="bd">
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

    <section>
      <div class="chips" style="margin-bottom: 12px">
        <button v-for="t in TABS" :key="t.key" class="ch" :class="{ on: tab === t.key }" type="button" @click="setTab(t.key)">
          {{ t.label }}<span v-if="count(t)" class="mt" :style="tab === t.key ? 'color: inherit; opacity: .7' : ''">&nbsp;{{ count(t) }}</span>
        </button>
      </div>
      <div class="cd list">
        <div v-for="it in items" :key="it.name" class="rw">
          <div class="grow">
            <RouterLink class="ttl" :to="`/inbox/${it.name}`">{{ it.title }}</RouterLink>
            <div class="mt">{{ describe(it) }}</div>
            <div v-if="it.status === 'Failed' && it.error" class="mt" style="color: var(--r-ink)">{{ it.error }}</div>
          </div>
          <button v-if="it.status === 'Failed' && canWrite()" class="bt s" type="button" @click="retry(it)">Retry</button>
          <span class="pl" :class="PILL[it.status]">{{ it.status === 'To Review' ? 'To review' : it.status }}</span>
        </div>
        <Empty v-if="loaded && !items.length" :title="EMPTY[tab][0]" :hint="EMPTY[tab][1]" />
        <div v-if="more" class="rw"><button class="bt s" type="button" @click="load(true)">Show more</button></div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { canWrite, refreshCounts, store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { fileKind, fileSize, uploadFile } from '@/lib/upload'

const SOURCES = ['Upload', 'Journal Photo', 'Voice Note', 'Email', 'Chat', 'Message', 'Web']
const TABS = [
  { key: 'review', label: 'To review', status: ['To Review'] },
  { key: 'waiting', label: 'Waiting for the agent', status: ['New', 'Processing'] },
  { key: 'failed', label: 'Failed', status: ['Failed'] },
  { key: 'done', label: 'Done', status: ['Done'] },
]
const PILL = { 'To Review': 'o', New: 'n', Processing: 'b', Failed: 'r', Done: 'g' }
const EMPTY = {
  review: ['Nothing to review.', 'When an agent has processed something you added, it shows here with its proposals.'],
  waiting: ['Nothing is waiting.', 'Drop a file above or forward something to your agent. It appears here until the agent picks it up.'],
  failed: ['Nothing has failed.', 'If an agent cannot process an item, it lands here with the reason and a Retry button.'],
  done: ['Nothing is done yet.', 'Items move here once every proposal has been accepted or rejected.'],
}

const router = useRouter()
const picker = ref(null)
const files = ref([])
const instruction = ref('')
const sourceType = ref('Upload')
const text = ref('')
const showText = ref(false)
const over = ref(false)
const busy = ref(false)
const tab = ref('review')
const items = ref([])
const totals = ref({})
const loaded = ref(false)
const more = ref(false)

const count = (t) => t.status.reduce((n, s) => n + (totals.value[s] || 0), 0)
const headSub = computed(() => `${store.space} · drop anything here, an agent proposes, you approve`)

function describe(it) {
  const parts = []
  if (it.status === 'To Review' || it.status === 'Done') {
    parts.push(it.has_transcript ? 'Transcribed' : it.has_summary ? 'Summary ready' : 'Processed')
    parts.push(`${it.proposals} proposal${it.proposals === 1 ? '' : 's'}`)
  } else if (it.status === 'Processing') parts.push(`Being processed${it.processed_by ? ' by ' + it.processed_by : ''}`)
  else if (it.status === 'New') parts.push('Waiting for an agent')
  else parts.push(it.source_type)
  parts.push(`${it.filed_by ? 'filed by ' + it.filed_by + ', ' : ''}${dateTime(it.received_on)}`)
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
    setTab('waiting')
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}

async function load(append = false) {
  const t = TABS.find((x) => x.key === tab.value)
  const res = await tryCall(() => api('inbox.list', { space: store.space, status: JSON.stringify(t.status), start: append ? items.value.length : 0, page_length: 30 }))
  if (!res) return
  items.value = append ? [...items.value, ...res.items] : res.items
  totals.value = res.totals
  more.value = res.items.length === 30
  loaded.value = true
  refreshCounts()
}
function setTab(key) {
  tab.value = key
  loaded.value = false
  load()
}
async function retry(it) {
  if (await tryCall(() => api('inbox.retry', { item: it.name }), 'Sent back to the agent.')) load()
}

onMounted(async () => {
  await load()
  if (!items.value.length && (totals.value.New || totals.value.Processing)) setTab('waiting')
})
</script>

<style scoped>
.drop { border: 1px dashed var(--line4); border-radius: 10px; padding: 16px; background: var(--soft); }
.drop.over { border-color: var(--accent); background: var(--b-bg); }
.drop-hint { display: flex; flex-direction: column; gap: 2px; padding: 6px 0 12px; }
.drop-form { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
</style>
