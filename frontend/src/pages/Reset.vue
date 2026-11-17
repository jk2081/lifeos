<template>
  <PageHead title="Reset" :sub="sub">
  </PageHead>
  <div class="page-body" data-reset>
    <template v-if="d">
      <!-- the goal bar: open tasks against the goal, and what was decided in this session -->
      <Card class="flex flex-wrap items-center gap-x-8 gap-y-2" data-reset-goal>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-baseline gap-x-2.5"><span class="text-base-medium text-ink-gray-9">Goal: open tasks under {{ d.goal }}</span>
            <span class="text-sm text-ink-gray-6"><CountLink :count="d.open" count-key="reset:open" /> now · <span data-decided>{{ decidedCount }}</span> decided this session</span></div>
          <!-- the scale runs to the larger of the open count and the goal: the marker is the goal, the fill what was decided now -->
          <div class="relative mt-2 h-1.5 rounded-full bg-surface-gray-3" role="img" :aria-label="`${d.open.n} open tasks; the goal is under ${d.goal}; ${decidedCount} decided this session`" data-goal-bar>
            <div class="h-full rounded-full bg-surface-gray-9" :style="{ width: Math.min(100, (100 * decidedCount) / scale) + '%' }" />
            <div class="absolute -top-1 h-3.5 w-0.5 rounded-full bg-surface-blue-7" :style="{ left: `calc(${Math.min(100, (100 * d.goal) / scale)}% - 1px)` }" aria-hidden="true" />
          </div>
        </div>
        <p v-if="d.stuck.n" class="text-sm text-ink-gray-7 max-md:hidden">Most of the weight is old: <CountLink :count="d.stuck" count-key="reset:stuck" /> open tasks have not been touched for {{ d.rules.stuck_after_days }} days or more.</p>
      </Card>

      <TabBar v-if="phone" class="mt-3" :tabs="phoneTabs" :model-value="tab.current.value" label="Reset sections" @update:model-value="tab.set" />
      <div class="mt-4 grid grid-cols-1 gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,32rem)]">
        <section v-show="!phone || tab.current.value === 'batches'" data-reset-batches>
          <SectionHead class="max-md:hidden">Suggested batches <span class="ml-1 font-normal text-ink-gray-6">{{ shown.length }} batch{{ shown.length === 1 ? '' : 'es' }} · {{ shown.reduce((n, b) => n + b.count, 0) }} items</span></SectionHead>
          <div class="flex flex-col gap-3">
            <BatchCard v-for="b in shown" :key="b.key" :batch="b" :writable="writable" :phone="phone" :busy="busy === b.key" @apply="askApply" @review="review" @skip="skipped.push(b.key)" />
            <Card v-if="!shown.length"><Empty title="No batches to suggest." hint="Nothing is duplicated, old or waiting in a pile. Use One by one for the rest." /></Card>
            <Button v-if="!aiAsked && aiReady" class="self-start" icon-left="lucide-sparkles" label="Suggest more with AI" :loading="aiLoading" data-reset-ai @click="loadAI" />
          </div>
        </section>
        <div class="flex flex-col gap-6">
          <section v-show="!phone || tab.current.value === 'inventory'">
            <SectionHead class="max-md:hidden">Inventory <span class="ml-1 font-normal text-ink-gray-6">by how long untouched · click a number to open those items</span></SectionHead>
            <Inventory :inv="d.inventory" />
          </section>
          <section v-show="!phone || tab.current.value === 'one'" ref="oneSection">
            <div class="max-md:hidden"><SectionHead>One by one<span v-if="only" class="ml-1 font-normal text-ink-gray-6">· {{ only.title }} <Button size="sm" variant="ghost" label="Show all" @click="only = null" /></span></SectionHead></div>
            <OneByOne ref="obo" :space="store.space" :writable="writable" :phone="phone" :months="d.rules.someday_review_months" :only="only?.names || null" :keys="!phone || tab.current.value === 'one'"
              @decided="decidedCount++; refreshSoon()" />
          </section>
        </div>
      </div>
    </template>
    <div v-else class="flex flex-col gap-3"><Skeleton class="h-16 w-full" /><Skeleton class="h-64 w-full" /></div>
  </div>
</template>
<script setup>
// Reset (UX fixes, set 5): clear the backlog. The goal bar, suggested batches (rules, and up to three from the AI on
// request), the Inventory of counts and one-by-one decisions. On a phone, Batches, One by one and Inventory are tabs.
import { computed, onMounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { useRouter } from 'vue-router'
import { Button, Skeleton, dialog, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import TabBar from '@/components/TabBar.vue'
import Card from '@/components/ui/Card.vue'
import CountLink from '@/components/ui/CountLink.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import BatchCard from '@/components/reset/BatchCard.vue'
import Inventory from '@/components/reset/Inventory.vue'
import OneByOne from '@/components/reset/OneByOne.vue'
import { api, errorText } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { onRecordChanged } from '@/lib/pane'
import { useUrlTab } from '@/lib/tabs'
import { askScope } from '@/lib/ask'

const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const d = ref(null)
const busy = ref('')
const skipped = ref([])
const decidedCount = ref(0)
const only = ref(null)
const obo = ref(null)
const oneSection = ref(null)
const aiAsked = ref(false)
const aiLoading = ref(false)
const aiReady = ref(false)
const writable = computed(() => canWrite() && !store.isAgent)
const scale = computed(() => Math.max(d.value?.open.n || 0, d.value?.goal || 0, 1))
const shown = computed(() => (d.value?.batches || []).filter((b) => !skipped.value.includes(b.key)))
const sub = computed(() => `${store.space} · clear the backlog in batches or one by one · also the first step of your weekly review`)
const phoneTabs = computed(() => [{ value: 'batches', label: 'Batches', count: shown.value.length }, { value: 'one', label: 'One by one', count: d.value?.next?.left ?? undefined },
  { value: 'inventory', label: 'Inventory' }])
const tab = useUrlTab('tab', phoneTabs)
// Ask from here starts with the items on screen as its scope
askScope({ kind: 'items', label: 'Items on Reset', doctype: null, name: null, items: () => shown.value.flatMap((b) => b.items.slice(0, 40)) })

async function load(ai = aiAsked.value) {
  d.value = await api('reset.get', { space: store.space, ai: ai ? 1 : 0 })
}
let timer = null
function refreshSoon() { clearTimeout(timer); timer = setTimeout(() => load(), 600) }
async function loadAI() {
  aiLoading.value = true
  try { aiAsked.value = true; await load(true) } catch (e) { toast.error(errorText(e)) } finally { aiLoading.value = false }
}
function askApply(b) {
  if (b.action === 'review_someday') return router.push(b.review)
  dialog.confirm({
    title: `${b.action_label}?`,
    message: `This changes exactly the ${b.count} item${b.count === 1 ? '' : 's'} listed in “${b.title}”. You can undo it from the message that follows, for one minute.`,
    confirmLabel: b.action_label,
    onConfirm: () => apply(b),
  })
}
async function apply(b) {
  busy.value = b.key
  try {
    const res = await api('reset.apply_batch', { space: store.space, action: b.action, items: JSON.stringify(b.items.map((i) => ({ doctype: i.doctype, name: i.name }))) })
    decidedCount.value += res.done
    toast.success(`${b.action_label}: done for ${res.done}.`, { duration: 60000, action: { label: 'Undo', onClick: () => undo(res.undo, res.done) } })
    window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))
    await load()
    obo.value?.reload()
  } finally { busy.value = '' }
}
async function undo(log, n) {
  try {
    await api('reset.undo', { log: JSON.stringify(log) })
    decidedCount.value = Math.max(decidedCount.value - n, 0)
    toast.success('Undone.')
    window.dispatchEvent(new CustomEvent('lifeos-counts-stale'))
    await load()
    obo.value?.reload()
  } catch (e) { toast.error(errorText(e)) }
}
function review(b) {
  if (b.review) return router.push(b.review)
  const names = b.items.filter((i) => ['Life Task', 'Life Goal'].includes(i.doctype)).map((i) => i.name)
  if (!names.length) return router.push({ path: '/inbox', query: { status: 'To Review' } })
  only.value = { title: b.title, names }
  if (phone.value) tab.set('one')
  else oneSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
onRecordChanged(() => refreshSoon())
onMounted(async () => {
  await load()
  try { aiReady.value = (await api('ask.status', { space: store.space })).ready } catch (e) { aiReady.value = false }
})
</script>
