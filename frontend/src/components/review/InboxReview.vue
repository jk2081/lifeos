<template>
  <template v-if="item">
    <PageHead v-if="page" :title="item.title" :crumb="{ to: '/brain', label: 'Brain', here: item.source_type }">
      <template #sub><span class="flex flex-wrap items-center gap-1">{{ headParts.text }}<template v-if="headParts.who"> · {{ headParts.verb }}
        <Avatar size="xs" :label="headParts.who" />{{ headParts.who }}</template></span></template>
      <template v-if="pending.length && writable">
        <Button label="Reject all" @click="decideAll('reject')" />
        <Button variant="solid" :label="`Accept all ${pending.length} pending`" @click="decideAll('accept')" />
      </template>
      <Button v-else-if="item.status === 'Failed' && writable" variant="solid" label="Retry" @click="retry" />
    </PageHead>
    <div v-else-if="writable && (pending.length || item.status === 'Failed')" class="flex flex-wrap items-center justify-end gap-2">
      <template v-if="pending.length">
        <Button label="Reject all" @click="decideAll('reject')" />
        <Button variant="solid" :label="`Accept all ${pending.length} pending`" @click="decideAll('accept')" />
      </template>
      <Button v-else variant="solid" label="Retry" @click="retry" />
    </div>

    <div :class="page ? 'page-body' : 'flex flex-col gap-4'">
      <Alert v-if="item.status === 'Failed'" theme="red" title="Processing failed." :description="item.error" />
      <Alert v-else-if="item.status === 'New' || item.status === 'Processing'" :title="item.status === 'New' ? 'Waiting for an agent.' : 'An agent is processing this.'"
        description="The summary and proposals show here when it is done." />
      <!-- below 640 px the four parts are tabs; wider screens show them side by side -->
      <TabBar v-if="phone" :tabs="phoneTabs" :model-value="ptab.current.value" label="Inbox item parts" :level="page ? 1 : 2" data-review-tabs @update:model-value="ptab.set" />
      <div class="cols">
        <div class="half">
          <section v-show="part('original')" data-review-original>
            <SectionHead :data-review-outputs="item.job_id ? '' : undefined">{{ item.job_id ? 'Outputs' : 'Original' }}</SectionHead>
            <div v-if="!item.files.length && !item.raw_text" class="grid min-h-[120px] place-items-center rounded-5 border border-dashed border-outline-gray-3 bg-surface-gray-1 text-base text-ink-gray-6"><span>{{ item.job_id ? 'No output was attached.' : 'No file was attached.' }}</span></div>
            <FileView v-for="f in item.files" :key="f.file_url" class="mb-3" :file="f" :preview="item.files.length === 1 ? item.preview_image : ''" />
            <Card v-if="item.raw_text" class="mt-2"><DigestView v-if="item.source_type === 'Email Digest'" :text="item.raw_text" /><Md v-else :text="item.raw_text" /></Card>
          </section>
          <!-- Issue 8: a piece of work filed with one call lists what it was made from apart from what was made -->
          <section v-if="item.job_id" v-show="part('original')" data-review-inputs>
            <SectionHead>Inputs</SectionHead>
            <Card v-if="!item.inputs.length"><Empty title="No inputs." hint="The agent filed no inputs with this work." /></Card>
            <ul v-else class="flex flex-col gap-2">
              <li v-for="i in item.inputs" :key="i.name" class="min-w-0 rounded-5 border border-outline-gray-1 px-3 py-2" data-review-input>
                <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-base">
                  <a v-if="i.file" class="break-all text-ink-blue-8 hover:underline" :href="i.file.file_url" target="_blank" rel="noopener">{{ i.name }}</a>
                  <span v-else class="break-all text-ink-gray-9">{{ i.name }}</span>
                  <span v-if="i.file?.file_size" class="text-sm text-ink-gray-6">{{ fileSize(i.file.file_size) }}</span>
                  <Badge v-if="i.asset" label="Reusable" />
                </div>
                <div v-if="i.asset" class="mt-1 text-sm text-ink-gray-6">Kept once as
                  <a href="#" class="text-ink-blue-8 underline" @click.prevent="openRoute(i.asset_route)">{{ i.asset_title || i.reusable_as }}</a></div>
                <FileVersions v-if="i.file" :file="i.file" />
              </li>
            </ul>
            <p v-if="item.wiki_pages.length || item.job_chat" class="mt-3 flex flex-wrap gap-x-2 gap-y-1 text-sm text-ink-gray-6" data-review-filed-with>
              <span>Filed with it:</span>
              <a v-for="w in item.wiki_pages" :key="w.name" href="#" class="text-ink-blue-8 underline" @click.prevent="openRoute(w.route)">{{ w.title }}</a>
              <a v-if="item.job_chat" href="#" class="text-ink-blue-8 underline" @click.prevent="openRoute(item.job_chat.route)">{{ item.job_chat.title }}</a>
            </p>
          </section>
          <Card v-if="phone && part('transcript') && !item.transcript_md && !writable"><Empty title="No transcript." /></Card>
          <section v-if="(item.transcript_md || writable) && part('transcript')">
            <SectionHead>Transcript</SectionHead>
            <Card>
              <MdField v-model="item.transcript_md" :save="saveTranscript" :space="item.space" :readonly="!writable" label="Transcript"
                placeholder="Add a transcript if the original needs one." />
            </Card>
            <p v-if="(item.transcript_md || '').includes('[?]')" class="mt-2 text-sm text-ink-gray-6">Words marked [?] were hard to read. Edit the transcript to correct them.</p>
          </section>
        </div>

        <div class="half">
          <Card v-if="phone && part('summary') && !item.summary_md"><Empty title="No summary." hint="The agent adds a summary when it processes the item." /></Card>
          <section v-if="item.summary_md && part('summary')">
            <SectionHead>Summary</SectionHead>
            <Card><Md :text="item.summary_md" /></Card>
          </section>
          <section v-show="part('proposals')">
            <SectionHead ref="proposalsHead" data-proposals>Proposals<template v-if="item.proposals.length"> · {{ countsLine }}</template></SectionHead>
            <ProposalCards :item="item" :writable="writable" :empty-hint="item.status === 'To Review' || item.status === 'Done' ? 'The agent found nothing to file from this item.' : 'Proposals appear here once an agent has processed the item.'"
              @decided="afterDecide" />
            <p class="mt-3 text-sm text-ink-gray-6">Nothing here becomes a record until you accept it. The original is always kept.</p>
          </section>
          <Backlinks v-show="part('proposals')" doctype="Life Inbox Item" :name="item.name" :reload="reloadKey" />
        </div>
      </div>
    </div>

  </template>
  <div v-else-if="missing && page" class="page-body"><Card><Empty title="This item was not found." hint="It may be in another space, or it was removed." /></Card></div>
</template>
<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Alert, Avatar, Badge, Button } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Md from '@/components/Md.vue'
import MdField from '@/components/MdField.vue'
import DigestView from '@/components/DigestView.vue'
import FileVersions from '@/components/FileVersions.vue'
import ProposalCards from '@/components/item/ProposalCards.vue'
import FileView from '@/components/item/FileView.vue'
import Empty from '@/components/Empty.vue'
import Backlinks from '@/components/Backlinks.vue'
import TabBar from '@/components/TabBar.vue'
import { useMediaQuery } from '@vueuse/core'
import { useUrlTab } from '@/lib/tabs'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { decideAll as decideAllOf } from '@/lib/items'
import { dateTime } from '@/lib/dates'
import { fileSize } from '@/lib/upload'
import { openRoute, recordChanged } from '@/lib/pane'

// The review of one inbox item: the content of its record pane, and the full page at /inbox/:id/review. Open full page in the
// pane goes to the item page (/item/:id, issue 10).
const props = defineProps({ id: String, name: String, type: String, page: Boolean })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const route = useRoute()
const itemName = computed(() => props.id || props.name)
const proposalsHead = ref(null)

const item = ref(null)
const missing = ref(false)
const reloadKey = ref(0)

const canRestore = computed(() => store.spaces.find((s) => s.name === item.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !item.value?.is_archived)
const pending = computed(() => item.value.proposals.filter((p) => p.status === 'Pending'))
// Phone only: Original (Files for a job, issue 8), Transcript, Summary, Proposals as tabs (tab= on the page, ptab= in the pane). It opens on
// Proposals while some are pending, otherwise on Summary.
const phone = useMediaQuery('(max-width: 639px)')
const phoneTabs = computed(() => !item.value ? [] : [{ value: 'original', label: item.value.job_id ? 'Files' : 'Original' }, { value: 'transcript', label: 'Transcript' },
  { value: 'summary', label: 'Summary' }, { value: 'proposals', label: 'Proposals', count: item.value.proposals.length, noun: 'proposals' }])
// the opening tab is decided once, so accepting the last proposal does not move the screen to another tab
let opening = null
const ptab = useUrlTab(props.page ? 'tab' : 'ptab', phoneTabs, { replace: !props.page,
  fallback: () => opening || (opening = item.value ? (pending.value.length ? 'proposals' : 'summary') : null) })
const part = (t) => !phone.value || ptab.current.value === t
const countsLine = computed(() => {
  const by = (s) => item.value.proposals.filter((p) => p.status === s).length
  return [[by('Pending'), 'pending'], [by('Accepted'), 'accepted'], [by('Rejected'), 'rejected']].filter(([n]) => n).map(([n, l]) => `${n} ${l}`).join(', ')
})
// the line under the title: when it came in, the instruction, and the person or agent who handled it
const headParts = computed(() => {
  const it = item.value
  const parts = [`${it.source_type === 'Upload' ? 'Uploaded' : 'Received'} ${dateTime(it.received_on)}`]
  if (it.instruction) parts.push(`instruction: "${it.instruction}"`)
  const out = { text: parts.join(' · '), verb: '', who: '' }
  if (it.processed_by && it.status !== 'New') Object.assign(out, { verb: 'processed by', who: it.processed_by })
  else if (it.filed_by) Object.assign(out, { verb: 'filed by', who: it.filed_by })
  return out
})
const headSub = computed(() => [headParts.value.text, headParts.value.who && `${headParts.value.verb} ${headParts.value.who}`].filter(Boolean).join(' · '))

async function load() {
  try {
    const it = (item.value = await api('inbox.get', { item: itemName.value }))
    emit('meta', { title: it.title, area: it.area, area_name: it.area_name, goal: it.goal, goal_title: it.goal_title, sub: headSub.value,
      fullPage: `/item/${it.name}`, archived: !!it.is_archived, canRestore: canRestore.value,
      sensitive: { doctype: 'Life Inbox Item', name: it.name, on: !!it.is_sensitive } })
  } catch (e) {
    missing.value = true
    emit('missing')
  }
}

// after Accept or Reject on a card: the backlinks below and the list behind the pane reload
function afterDecide() {
  reloadKey.value++
  if (!props.page) recordChanged('inbox:' + item.value.name)
}

async function decideAll(decision) {
  if (!(await decideAllOf(item.value, decision, async () => (await load(), item.value)))) return
  afterDecide()
}

async function retry() {
  if (await tryCall(() => api('inbox.retry', { item: item.value.name }), 'Sent back to the agent.')) {
    await load()
    if (!props.page) recordChanged('inbox:' + item.value.name)
  }
}
async function saveTranscript(text) {
  await api('inbox.update_transcript', { item: item.value.name, transcript_md: text })
}

onMounted(async () => {
  load().then(async () => {
    // a link from "4 of 13 proposals pending" lands on the pending proposals
    if (route.query.focus !== 'pending' || !item.value) return
    await nextTick()
    const head = proposalsHead.value?.$el
    const first = head?.parentElement.querySelector('[data-proposal="Pending"]') || head
    first?.scrollIntoView({ block: 'start' })
  })
})
</script>
