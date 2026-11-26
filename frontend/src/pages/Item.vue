<template>
  <template v-if="item">
    <PageHead :title="item.title || 'Untitled'" :path="[{ label: 'Brain', to: '/brain' }, { label: 'Activity', to: '/brain/activity' }]">
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
          <Button v-if="item.area" size="sm" variant="outline" icon-left="lucide-folder" :label="item.area_name || 'Area'" :route="`/today?area=${item.area}`" data-item-area />
          <Button v-if="item.goal" size="sm" variant="outline" icon-left="lucide-target" :label="item.goal_title || item.goal" :route="`/goals/${item.goal}`" data-item-goal />
          <Badge :theme="STATUS[item.status]?.[1] || 'gray'" :label="STATUS[item.status]?.[0] || item.status" data-item-status />
        </div>
        <p v-if="item.source_type === 'Voice Note' && !item.transcript_md" class="-mt-2 text-sm text-ink-gray-6" data-item-untranscribed>Voice note, not transcribed yet</p>
        <Alert v-if="item.is_archived" title="This item is archived. It is shown read-only." />

        <TabBar :tabs="tabs" :model-value="ptab.current.value" label="Item sections" :level="1" data-item-tabs @update:model-value="ptab.set" />
        <ItemBody :item="item" :tab="ptab.current.value" :writable="writable" :reload-key="reloadKey" @tab="ptab.set" @reload="load" @decided="refresh" />
      </div>
    </div>
  </template>
  <template v-else-if="missing">
    <PageHead title="Not found" :path="[{ label: 'Brain', to: '/brain' }, { label: 'Activity', to: '/brain/activity' }]" />
    <div class="page-body"><Card data-item-missing><Empty title="Not found." hint="There is no such item, or it is in a space you cannot open." /></Card></div>
  </template>
  <div v-else class="page-body"><Skeleton class="h-40 w-full" /></div>
</template>
<script setup>
// Issue 10: one page per capture at /item/:id. What it is and where it came from, then its tabs (issue 118): Summary, the original,
// the decisions waiting and what came of it (with what is related). The proposal cards are the Review screen's own.
import { computed, onMounted, ref } from 'vue'
import { Alert, Badge, Button, Skeleton } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import TabBar from '@/components/TabBar.vue'
import ItemBody from '@/components/item/ItemBody.vue'
import { tryCall } from '@/lib/api'
import { itemTabs } from '@/lib/itemTabs'
import { useUrlTab } from '@/lib/tabs'
import { itemData } from '@/data/item'
import { store } from '@/lib/store'
import { dateTime } from '@/lib/dates'
import { decideAll as decideAllOf } from '@/lib/items'

const props = defineProps({ id: String })
const reloadKey = ref(0)
const item = ref(null)
const missing = ref(false)

// the source: the system it came through (Gmail, your assistant…), else the kind of capture
const SYSTEMS = { gmail: ['Gmail', 'lucide-mail'], hermes: ['Your assistant', 'lucide-bot'], openclaw: ['Another agent', 'lucide-bot'], claude: ['Claude', 'lucide-sparkles'],
  chatgpt: ['ChatGPT', 'lucide-sparkles'], telegram: ['Telegram', 'lucide-send'], whatsapp: ['WhatsApp', 'lucide-message-circle'],
  calendar: ['Calendar', 'lucide-calendar'], upload: ['Upload', 'lucide-upload'] }
const TYPES = { Upload: 'lucide-upload', 'Journal Photo': 'lucide-camera', 'Voice Note': 'lucide-mic', Email: 'lucide-mail', 'Email Digest': 'lucide-mail',
  Chat: 'lucide-message-square', Message: 'lucide-message-circle', Web: 'lucide-globe', Phone: 'lucide-smartphone' }
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
const tabs = computed(() => itemTabs(item.value))
const ptab = useUrlTab('tab', tabs)

const fetchItem = () => itemData.inbox.item_page({ item: props.id })
async function load() {
  try {
    item.value = await fetchItem()
  } catch (e) {
    missing.value = true
  }
  return item.value
}
// after a decision on a card: what came of it, the related records and the status come again; the cards keep their state
async function refresh() {
  const fresh = await tryCall(fetchItem)
  if (fresh) Object.assign(item.value, { came_of_it: fresh.came_of_it, related: fresh.related, status: fresh.status })
  reloadKey.value++
}
const decideAll = (decision) => decideAllOf(item.value, decision, load)
async function retry() {
  if (await tryCall(() => itemData.inbox.retry({ item: item.value.name }), 'Sent back to the agent.')) await load()
}

onMounted(load)
</script>
