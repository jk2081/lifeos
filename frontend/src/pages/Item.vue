<template>
  <template v-if="item">
    <PageHead :title="item.title || 'Untitled'" :crumb="{ to: '/brain', label: 'Brain', here: 'Item' }">
      <template #sub>
        <span class="flex flex-wrap items-center gap-x-1.5 gap-y-1" data-item-head>
          <span class="inline-flex items-center gap-1" data-item-source><span :class="source.icon" class="size-4" aria-hidden="true" />{{ source.label }}</span>
          <span aria-hidden="true">·</span><span data-item-when>{{ dateTime(item.received_on) }}</span>
          <span aria-hidden="true">·</span><span data-item-space>{{ item.space_name }}</span>
          <template v-if="item.is_sensitive"><span aria-hidden="true">·</span>
            <span class="inline-flex items-center gap-1" data-sensitive-lock><span class="lucide-lock size-3.5" aria-hidden="true" />Sensitive</span></template>
        </span>
      </template>
      <template v-if="pending.length && writable">
        <Button label="Reject all" @click="decideAll('reject')" />
        <Button variant="solid" :label="`Accept all ${pending.length}`" @click="decideAll('accept')" />
      </template>
      <Button v-else-if="item.status === 'Failed' && writable" variant="solid" label="Retry" @click="retry" />
    </PageHead>

    <div class="page-body">
      <div class="mx-auto flex w-full max-w-[860px] flex-col gap-6" data-item-page>
        <div v-if="item.area || item.goal || item.status !== 'Done'" class="-mt-2 flex flex-wrap items-center gap-2" data-item-chips>
          <Button v-if="item.area" size="sm" variant="outline" icon-left="lucide-folder" :label="item.area_name || 'Area'" :route="`/areas/${item.area}`" data-item-area />
          <Button v-if="item.goal" size="sm" variant="outline" icon-left="lucide-target" :label="item.goal_title || item.goal" :route="`/goals/${item.goal}`" data-item-goal />
          <Badge :theme="STATUS[item.status]?.[1] || 'gray'" :label="STATUS[item.status]?.[0] || item.status" data-item-status />
        </div>
        <Alert v-if="item.is_archived" title="This item is archived. It is shown read-only." />

        <ItemSection name="came-in" title="What came in" :phone="phone" :open="!phone">
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
        </ItemSection>

        <ItemSection name="brain" title="What the Brain made of it" :phone="phone">
          <Alert v-if="item.status === 'Failed'" theme="red" title="Processing failed." :description="item.error" />
          <Alert v-else-if="item.status === 'New' || item.status === 'Processing'" :title="item.status === 'New' ? 'Waiting for the Brain.' : 'The Brain is reading this.'"
            description="Its summary and proposals show here when it is done." />
          <Card v-if="item.summary_md" data-item-summary><Md :text="item.summary_md" /></Card>
          <Card v-else-if="item.status !== 'New' && item.status !== 'Processing'"><Empty title="No summary." hint="The Brain adds a summary when it reads the item." /></Card>
          <div v-if="item.transcript_md || writable" data-item-transcript>
            <Button variant="ghost" size="sm" class="-ml-2" :icon-left="showTranscript ? 'lucide-chevron-down' : 'lucide-chevron-right'"
              :label="showTranscript ? 'Hide the transcript' : item.transcript_md ? 'Show the transcript' : 'Add a transcript'" :aria-expanded="showTranscript" data-item-transcript-toggle
              @click="showTranscript = !showTranscript" />
            <Card v-if="showTranscript" class="mt-2">
              <MdField v-model="item.transcript_md" :save="saveTranscript" :space="item.space" :readonly="!writable" label="Transcript"
                placeholder="Add a transcript if the original needs one." />
            </Card>
          </div>
        </ItemSection>

        <ItemSection name="decisions" title="Decisions" :count="pending.length" :phone="phone">
          <ProposalCards :item="item" :writable="writable" only="pending" empty-title="Nothing waiting for you."
            :empty-hint="emptyDecisions" @decided="refresh" />
          <p v-if="rejected" class="text-sm text-ink-gray-6" data-item-rejected>{{ rejected }} rejected.</p>
        </ItemSection>

        <ItemSection name="came-of-it" title="What came of it" :count="item.came_of_it.length" :phone="phone">
          <Card flush>
            <RecordRow v-for="m in item.came_of_it" :key="m.doctype + m.name" :record="m" data-came-of-it />
            <Empty v-if="!item.came_of_it.length" title="Nothing yet." hint="Tasks, notes, dates and events you accept from its proposals are listed here." />
          </Card>
        </ItemSection>

        <ItemSection name="related" title="Related" :count="relatedCount" :phone="phone" :open="!phone">
          <template v-for="g in relatedGroups" :key="g.key">
            <div v-if="g.rows.length" class="flex flex-col gap-1" :data-related="g.key">
              <div class="text-sm-medium text-ink-gray-7">{{ g.label }}</div>
              <Card flush><RecordRow v-for="r in g.rows" :key="r.doctype + r.name" :record="r" data-related-row /></Card>
            </div>
          </template>
          <Card v-if="!relatedCount"><Empty title="Nothing related yet." hint="Wiki pages and chat logs that cite this item, and the meeting it belongs to, show here." /></Card>
        </ItemSection>
      </div>
    </div>
  </template>
  <template v-else-if="missing">
    <PageHead title="Not found" :crumb="{ to: '/brain', label: 'Brain', here: 'Item' }" />
    <div class="page-body"><Card data-item-missing><Empty title="Not found." hint="There is no such item, or it is in a space you cannot open." /></Card></div>
  </template>
  <div v-else class="page-body"><Skeleton class="h-40 w-full" /></div>
</template>
<script setup>
// Issue 10: one page per capture at /item/:id. What it is and where it came from, what came in, what the Brain made of it,
// the decisions waiting, what came of it and what is related. The proposal cards are the Review screen's own.
import { computed, onMounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Alert, Badge, Button, Skeleton } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import MdField from '@/components/MdField.vue'
import DigestView from '@/components/DigestView.vue'
import FileView from '@/components/item/FileView.vue'
import ItemSection from '@/components/item/ItemSection.vue'
import ProposalCards from '@/components/item/ProposalCards.vue'
import RecordRow from '@/components/item/RecordRow.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { decideAll as decideAllOf } from '@/lib/items'
import { openRoute } from '@/lib/pane'
import { safeUrl } from '@/lib/editor/livePreview'

const props = defineProps({ id: String })
const phone = useMediaQuery('(max-width: 767px)')
const item = ref(null)
const missing = ref(false)
const showTranscript = ref(false)

// the source: the system it came through (Gmail, Hermes…), else the kind of capture
const SYSTEMS = { gmail: ['Gmail', 'lucide-mail'], hermes: ['Hermes', 'lucide-bot'], openclaw: ['OpenClaw', 'lucide-bot'], claude: ['Claude', 'lucide-sparkles'],
  chatgpt: ['ChatGPT', 'lucide-sparkles'], telegram: ['Telegram', 'lucide-send'], whatsapp: ['WhatsApp', 'lucide-message-circle'],
  calendar: ['Calendar', 'lucide-calendar'], upload: ['Upload', 'lucide-upload'] }
const TYPES = { Upload: 'lucide-upload', 'Journal Photo': 'lucide-camera', 'Voice Note': 'lucide-mic', Email: 'lucide-mail', 'Email Digest': 'lucide-mail',
  Chat: 'lucide-message-square', Message: 'lucide-message-circle', Web: 'lucide-globe' }
const STATUS = { New: ['Waiting for the Brain', 'gray'], Processing: ['Being read', 'blue'], 'To Review': ['Needs you', 'amber'], Done: ['Done', 'green'], Failed: ['Failed', 'red'] }
const source = computed(() => {
  const it = item.value
  const sys = String(it.source_system || '').toLowerCase()
  const known = SYSTEMS[sys] || SYSTEMS[sys.split(/[-_ ]/)[0]]
  if (known) return { label: known[0], icon: known[1] }
  if (sys) return { label: sys.replace(/^./, (c) => c.toUpperCase()), icon: 'lucide-plug' }
  if (it.filed_by_agent && it.filed_by) return { label: it.filed_by, icon: 'lucide-bot' }
  return { label: it.source_type || 'Upload', icon: TYPES[it.source_type] || 'lucide-inbox' }
})

const writable = computed(() => store.spaces.find((s) => s.name === item.value?.space)?.access === 'Write' && !item.value?.is_archived)
const pending = computed(() => item.value.proposals.filter((p) => p.status === 'Pending'))
const rejected = computed(() => item.value.proposals.filter((p) => p.status === 'Rejected').length)
const emptyDecisions = computed(() => (item.value.status === 'New' || item.value.status === 'Processing'
  ? 'Proposals appear here once the Brain has read the item.' : 'Every proposal is decided.'))
const safeLink = computed(() => (/^https?:/i.test(item.value?.source_url || '') ? safeUrl(item.value.source_url) : ''))
const relatedGroups = computed(() => [{ key: 'pages', label: 'Wiki pages and notes', rows: item.value.related.pages },
  { key: 'chats', label: 'Chat logs', rows: item.value.related.chats }, { key: 'meetings', label: 'Meetings', rows: item.value.related.meetings }])
const relatedCount = computed(() => relatedGroups.value.reduce((n, g) => n + g.rows.length, 0))

const fetchItem = () => api('inbox.item_page', { item: props.id })
async function load() {
  try {
    item.value = await fetchItem()
    document.title = `${item.value.title || 'Item'} · Life OS`
  } catch (e) {
    missing.value = true
  }
  return item.value
}
// after a decision on a card: what came of it, the related records and the status come again; the cards keep their state
async function refresh() {
  const fresh = await tryCall(fetchItem)
  if (fresh) Object.assign(item.value, { came_of_it: fresh.came_of_it, related: fresh.related, status: fresh.status })
}
const decideAll = (decision) => decideAllOf(item.value, decision, load)
async function retry() {
  if (await tryCall(() => api('inbox.retry', { item: item.value.name }), 'Sent back to the agent.')) await load()
}
const saveTranscript = (text) => api('inbox.update_transcript', { item: item.value.name, transcript_md: text })
const openLink = () => window.open(safeLink.value, '_blank', 'noopener,noreferrer')

onMounted(load)
</script>
