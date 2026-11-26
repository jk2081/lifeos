<template>
  <div class="flex flex-col gap-4" :data-item-tab="tab">
    <div v-if="tab === 'summary'" class="flex flex-col gap-4">
      <Alert v-if="item.status === 'Failed'" theme="red" title="Processing failed." :description="item.error" />
      <Alert v-else-if="item.status === 'New' || item.status === 'Processing'" :title="item.status === 'New' ? 'Waiting for the Brain.' : 'The Brain is reading this.'"
        description="Its summary and proposals show here when it is done." />
      <SummaryView :item="item" :writable="writable" @original="emit('tab', originalKey(item))" @changed="emit('reload')" />
    </div>

    <template v-else-if="tab === originalKey(item)">
      <p v-if="item.instruction" class="text-base text-ink-gray-8" data-item-instruction><span class="text-ink-gray-6">Your instruction:</span> “{{ item.instruction }}”</p>
      <FileView v-for="f in item.files" :key="f.file_url" :file="f" :preview="item.files.length === 1 ? item.preview_image : ''" />
      <Card v-if="item.raw_text" data-item-text><DigestView v-if="item.source_type === 'Email Digest'" :text="item.raw_text" /><Md v-else :text="item.raw_text" /></Card>
      <div v-if="safeLink"><Button icon-left="lucide-external-link" :label="/mail\.google\.com/.test(safeLink) ? 'Open in Gmail' : 'Open the original'" @click="openLink" /></div>
      <template v-if="item.job_id">
        <div class="text-sm-medium text-ink-gray-7">Made from</div>
        <Card flush>
          <Row v-for="i in item.inputs" :key="i.name" data-item-input>
            <div class="min-w-0 flex-1 break-words text-base">
              <a v-if="i.file" class="relative text-ink-blue-8 hover:underline" :href="i.file.file_url" target="_blank" rel="noopener">{{ i.name }}</a>
              <span v-else class="text-ink-gray-9">{{ i.name }}</span>
              <div v-if="i.asset" class="text-sm text-ink-gray-6">Kept once as
                <a href="#" class="relative text-ink-blue-8 underline" @click.prevent="openRoute(i.asset_route)">{{ i.asset_title || i.reusable_as }}</a></div>
            </div>
          </Row>
          <Empty v-if="!item.inputs.length" title="No inputs." hint="The agent filed no inputs with this work." />
        </Card>
      </template>
      <Card v-if="!item.files.length && !item.raw_text && !safeLink && !item.instruction"><Empty title="Nothing came with it." hint="This item arrived with no file, text or link." /></Card>
      <!-- "Add a transcript" lives with the original -->
      <div v-if="item.transcript_md || writable" data-item-transcript>
        <Button variant="ghost" size="sm" class="-ml-2" :icon-left="showTranscript ? 'lucide-chevron-down' : 'lucide-chevron-right'"
          :label="showTranscript ? 'Hide the transcript' : item.transcript_md ? 'Show the transcript' : 'Add a transcript'" :aria-expanded="showTranscript" data-item-transcript-toggle
          @click="showTranscript = !showTranscript" />
        <Card v-if="showTranscript" class="mt-2">
          <MdField v-model="item.transcript_md" :save="saveTranscript" :space="item.space" :readonly="!writable" label="Transcript"
            placeholder="Add a transcript if the original needs one." />
        </Card>
        <p v-if="showTranscript && (item.transcript_md || '').includes('[?]')" class="mt-2 text-sm text-ink-gray-6">Words marked [?] were hard to read. Edit the transcript to correct them.</p>
      </div>
    </template>

    <div v-else-if="tab === 'decisions'" class="flex flex-col gap-3" data-item-decisions>
      <ProposalCards :item="item" :writable="writable" only="pending" empty-title="Nothing waiting for you." :empty-hint="emptyDecisions" @decided="emit('decided')" />
      <p v-if="rejected" class="text-sm text-ink-gray-6" data-item-rejected>{{ rejected }} rejected.</p>
    </div>

    <div v-else-if="tab === 'came'" class="flex flex-col gap-4">
      <Card flush>
        <RecordRow v-for="m in item.came_of_it" :key="m.doctype + m.name" :record="m" data-came-of-it />
        <Empty v-if="!item.came_of_it.length" title="Nothing yet." hint="Tasks, notes, dates and events made from it are listed here." />
      </Card>
      <template v-for="g in relatedGroups" :key="g.key">
        <div v-if="g.rows.length" class="flex flex-col gap-1" :data-related="g.key">
          <div class="text-sm-medium text-ink-gray-7">{{ g.label }}</div>
          <Card flush><RecordRow v-for="r in g.rows" :key="r.doctype + r.name" :record="r" data-related-row /></Card>
        </div>
      </template>
      <Backlinks doctype="Life Inbox Item" :name="item.name" :reload="reloadKey" />
    </div>
  </div>
</template>
<script setup>
// What one inbox item holds, one tab at a time (issue 118): Summary, the original, Decisions, What came of it. The pane and the page both show it.
import { computed, ref } from 'vue'
import { Alert, Button } from 'frappe-ui'
import Backlinks from '@/components/Backlinks.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import MdField from '@/components/MdField.vue'
import DigestView from '@/components/DigestView.vue'
import FileView from '@/components/item/FileView.vue'
import ProposalCards from '@/components/item/ProposalCards.vue'
import RecordRow from '@/components/item/RecordRow.vue'
import SummaryView from '@/components/item/SummaryView.vue'
import { db } from '@/lib/api'
import { originalKey } from '@/lib/itemTabs'
import { openRoute } from '@/lib/pane'
import { safeUrl } from '@/lib/editor/livePreview'

const props = defineProps({ item: { type: Object, required: true }, tab: { type: String, default: 'summary' }, writable: Boolean, reloadKey: { type: Number, default: 0 } })
const emit = defineEmits(['tab', 'reload', 'decided'])
const showTranscript = ref(props.item.source_type === 'Voice Note' && !!props.item.transcript_md)
const rejected = computed(() => props.item.proposals.filter((p) => p.status === 'Rejected').length)
const emptyDecisions = computed(() => (props.item.status === 'New' || props.item.status === 'Processing' ? 'Proposals appear here once the Brain has read the item.' : 'Every proposal is decided.'))
const safeLink = computed(() => (/^https?:/i.test(props.item.source_url || '') ? safeUrl(props.item.source_url) : ''))
const relatedGroups = computed(() => [{ key: 'pages', label: 'Wiki pages and notes', rows: props.item.related?.pages || [] },
  { key: 'chats', label: 'Chat logs', rows: props.item.related?.chats || [] }, { key: 'meetings', label: 'Meetings', rows: props.item.related?.meetings || [] }])
const saveTranscript = (text) => db.set('Life Inbox Item', props.item.name, { transcript_md: text })
const openLink = () => window.open(safeLink.value, '_blank', 'noopener,noreferrer')
</script>
