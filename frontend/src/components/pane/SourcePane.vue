<template>
  <template v-if="s">
    <!-- Original: the thing as it arrived -->
    <section v-if="on('original')" class="flex flex-col gap-3" data-source-original>
      <div v-if="locked"><Alert title="This source made a Vault document." description="It follows the Vault's access, so it is not shown here." /></div>
      <template v-else>
        <template v-for="f in s.files" :key="f.file_url">
          <audio v-if="fileKind(f.file_name) === 'audio'" class="w-full" controls preload="metadata" :src="f.file_url" :aria-label="f.file_name" />
          <img v-else-if="fileKind(f.file_name) === 'image'" class="max-h-[70vh] w-full rounded-4 border border-outline-gray-2 object-contain" :src="s.preview_image || f.file_url" :alt="f.file_name" />
          <iframe v-else-if="fileKind(f.file_name) === 'pdf'" class="h-[70vh] w-full rounded-4 border border-outline-gray-2" :src="f.file_url" :title="f.file_name" />
          <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6"><span class="lucide-paperclip size-4" aria-hidden="true" />
            <a class="text-ink-blue-8 hover:underline" :href="f.file_url" target="_blank" rel="noopener noreferrer">{{ f.file_name }}</a><span>{{ fileSize(f.file_size) }}</span></div>
        </template>
        <Card v-if="s.raw_text"><DigestView v-if="s.source_type === 'Email Digest'" :text="s.raw_text" /><Md v-else :text="s.raw_text" read /></Card>
        <div v-if="safeLink"><Button icon-left="lucide-external-link" :label="/mail\.google\.com/.test(safeLink) ? 'Open in Gmail' : 'Open the original'" @click="openLink" /></div>
        <Card v-if="!s.files.length && !s.raw_text && !safeLink"><Empty title="Nothing to show." hint="This source arrived with no file, text or link." /></Card>
      </template>
    </section>
    <!-- Text: the transcript or extracted text, editable by people -->
    <section v-if="on('text')" data-source-text>
      <MdField v-if="writable || s.transcript_md" v-model="s.transcript_md" :save="saveText" :space="s.space" :readonly="!writable" label="Transcript or extracted text"
        placeholder="The agent puts the transcript or extracted text here." />
      <Card v-else><Empty title="No text yet." hint="The agent extracts the text (transcript, OCR, PDF text) when it processes the source." /></Card>
    </section>
    <section v-if="on('summary')" data-source-summary>
      <Card><Md v-if="s.summary_md" :text="s.summary_md" /><Empty v-else title="No summary." hint="The agent adds a summary when it processes the source." /></Card>
    </section>
    <section v-if="on('made')" data-source-made>
      <Card flush>
        <Row v-for="m in made" :key="m.doctype + m.name" :pane="refOfRoute(m.route)" :label="m.title" :class="!refOfRoute(m.route) && 'cursor-pointer'" @click="!refOfRoute(m.route) && openRoute(m.route)" data-made-row>
          <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ m.title }}</div><div class="text-sm text-ink-gray-6">{{ m.kind }}</div></div></Row>
        <Empty v-if="!made.length" title="Nothing made from this yet." hint="Records accepted from its proposals, and wiki pages that cite it, are listed here." />
      </Card>
    </section>
    <section v-if="on('details')" class="flex flex-col gap-3" data-source-details>
      <dl class="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1.5 text-base">
        <template v-for="d in details" :key="d[0]"><dt class="text-ink-gray-6">{{ d[0] }}</dt><dd class="min-w-0 break-words text-ink-gray-8">{{ d[1] }}</dd></template>
      </dl>
      <div v-if="s.status !== 'Done'"><Button label="Open in the Inbox" icon-left="lucide-inbox" @click="openRef('inbox:' + s.name)" /></div>
    </section>
  </template>
</template>
<script setup>
// A source in the pane (UX fixes, set 4): Original, Text, Summary, Made from this and Details. A source a Vault document was
// made from follows Vault access: the server hides it from agents while the switch is off.
import { computed, onMounted, ref } from 'vue'
import { Alert, Button } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import Md from '../Md.vue'
import MdField from '../MdField.vue'
import DigestView from '../DigestView.vue'
import Empty from '../Empty.vue'
import { api } from '@/lib/api'
import { store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { fileKind, fileSize } from '@/lib/upload'
import { openRef, openRoute, refOfRoute } from '@/lib/pane'
import { safeUrl } from '@/lib/editor/livePreview'

const props = defineProps({ name: String, type: String, tab: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const on = (t) => !props.tab || props.tab === t
const s = ref(null)
const made = ref([])
const locked = ref(false)
const writable = computed(() => store.spaces.find((x) => x.name === s.value?.space)?.access === 'Write' && !store.isAgent)
const safeLink = computed(() => (/^https?:/i.test(s.value?.source_url || '') ? safeUrl(s.value.source_url) : ''))
const STATUS = { New: 'In Inbox, waiting for the agent', Processing: 'In Inbox, being processed', 'To Review': 'In Inbox, to review', Done: 'Done', Failed: 'Failed' }
const details = computed(() => [
  ['Kind', s.value.media_kind === 'Email Digest' ? 'Email digest' : s.value.media_kind || s.value.source_type],
  ['Received', dateTime(s.value.received_on)], ['Status', STATUS[s.value.status] || s.value.status], ['Intent', s.value.intent || 'Process'],
  ...(s.value.source_system ? [['From', s.value.source_system]] : []), ...(s.value.external_id ? [['Original ID', s.value.external_id]] : []),
  ...(s.value.filed_by ? [['Filed by', s.value.filed_by]] : []), ...(s.value.processed_by ? [['Processed by', s.value.processed_by]] : []),
  ...(s.value.instruction ? [['Instruction', s.value.instruction]] : []),
])
function openLink() { window.open(safeLink.value, '_blank', 'noopener,noreferrer') }
async function saveText(text) { await api('inbox.update_transcript', { item: s.value.name, transcript_md: text }) }
onMounted(async () => {
  try {
    const [item, m] = await Promise.all([api('inbox.get', { item: props.name }), api('sources.made_from', { doctype: 'Life Inbox Item', name: props.name })])
    s.value = item
    made.value = m
    emit('meta', { title: item.title, area: item.area, area_name: item.area_name, goal: item.goal, goal_title: item.goal_title,
      sub: [item.media_kind === 'Email Digest' ? 'Email digest' : item.media_kind, dateTime(item.received_on)].filter(Boolean).join(' · '),
      archived: !!item.is_archived, canRestore: writable.value,
      tabs: [{ value: 'original', label: 'Original' }, { value: 'text', label: 'Text' }, { value: 'summary', label: 'Summary' },
        { value: 'made', label: 'Made from this', count: m.length, noun: 'records' }, { value: 'details', label: 'Details' }] })
  } catch (e) {
    emit('missing')
  }
})
</script>
