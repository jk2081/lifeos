<template>
  <template v-if="item">
    <PageHead v-if="page" :title="item.title" :path="[{ label: 'Brain', to: '/brain' }, { label: 'Needs you', to: '/brain' }]">
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
      <!-- in the pane the tab bar is the pane's own (ItemView, from the tabs this item says in its meta); on the full page it is here -->
      <TabBar v-if="page" :tabs="tabs" :model-value="ptab.current.value" label="Inbox item sections" :level="1" data-review-tabs @update:model-value="ptab.set" />
      <ItemBody :item="item" :tab="current" :writable="writable" :reload-key="reloadKey" @tab="setTab" @reload="load" @decided="afterDecide" />
      <p v-if="current === 'decisions'" class="text-sm text-ink-gray-6">Nothing here becomes a record until you accept it. The original is always kept.</p>
    </div>
  </template>
  <div v-else-if="missing && page" class="page-body"><Card><Empty title="This item was not found." hint="It may be in another space, or it was removed." /></Card></div>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Avatar, Button } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import TabBar from '@/components/TabBar.vue'
import ItemBody from '@/components/item/ItemBody.vue'
import { itemTabs } from '@/lib/itemTabs'
import { useUrlTab } from '@/lib/tabs'
import { tryCall } from '@/lib/api'
import { reviewData } from '@/data/review'
import { store } from '@/lib/store'
import { decideAll as decideAllOf } from '@/lib/items'
import { dateTime } from '@/lib/dates'
import { recordChanged } from '@/lib/pane'

// The review of one inbox item: the content of its record pane, and the full page at /inbox/:id/review. Open full page in the
// pane goes to the item page (/item/:id, issue 10).
const props = defineProps({ id: String, name: String, type: String, page: Boolean, tab: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
const route = useRoute()
const router = useRouter()
const itemName = computed(() => props.id || props.name)

const item = ref(null)
const missing = ref(false)
const reloadKey = ref(0)

const canRestore = computed(() => store.spaces.find((s) => s.name === item.value?.space)?.access === 'Write')
const writable = computed(() => canRestore.value && !item.value?.is_archived)
const pending = computed(() => item.value.proposals.filter((p) => p.status === 'Pending'))
// The tabs (issue 118): Summary, the original (Emails n, File, Transcript), Decisions n, What came of it n. In the pane the bar is the pane's own
// (ptab=, from the tabs this item says in its meta); on the full page it is here (tab=). A link to the pending proposals opens on Decisions.
const tabs = computed(() => itemTabs(item.value))
const ptab = useUrlTab('tab', tabs, { fallback: () => (route.query.focus === 'pending' ? 'decisions' : null) })
const current = computed(() => (props.page ? ptab.current.value : props.tab || 'summary'))
const setTab = (t) => (props.page ? ptab.set(t) : router.replace({ query: { ...route.query, ptab: t } }))
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

const metaOf = (it) => ({ tabs: itemTabs(it), title: it.title, area: it.area, area_name: it.area_name, goal: it.goal, goal_title: it.goal_title, sub: headSub.value,
  fullPage: `/item/${it.name}`, archived: !!it.is_archived, canRestore: canRestore.value, sensitive: { doctype: 'Life Inbox Item', name: it.name, on: !!it.is_sensitive } })
async function load() {
  try {
    emit('meta', metaOf((item.value = await reviewData.inbox.item_page({ item: itemName.value }))))
  } catch (e) {
    missing.value = true
    emit('missing')
  }
}

// after Accept or Reject on a card: what came of it, the counts on the tabs, the backlinks and the list behind the pane come again; the cards keep their state
async function afterDecide() {
  reloadKey.value++
  const fresh = await tryCall(() => reviewData.inbox.item_page({ item: item.value.name }))
  if (fresh) {
    Object.assign(item.value, { came_of_it: fresh.came_of_it, related: fresh.related, status: fresh.status })
    emit('meta', { ...metaOf(item.value) })
  }
  if (!props.page) recordChanged('inbox:' + item.value.name)
}

async function decideAll(decision) {
  if (!(await decideAllOf(item.value, decision, async () => (await load(), item.value)))) return
  afterDecide()
}

async function retry() {
  if (await tryCall(() => reviewData.inbox.retry({ item: item.value.name }), 'Sent back to the agent.')) {
    await load()
    if (!props.page) recordChanged('inbox:' + item.value.name)
  }
}

onMounted(load)
</script>
