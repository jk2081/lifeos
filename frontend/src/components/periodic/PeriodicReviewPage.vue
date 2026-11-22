<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review :data-review-kind="kind" :data-review-tab="tab" :data-review-name="r.head?.name || ''">
    <ReviewHeader v-if="r.head" :tab="tab" :tabs="r.head.tabs" :title="r.head.title" @go="go" @pause="pause" />
    <div v-if="r.notDue" class="page-body" data-review-not-due>
      <Empty :title="`No ${kind === 'monthly' ? 'monthly' : '12-week'} review is due.`" :hint="kind === 'monthly' ? 'It opens on your review day after a month ends, and stays until you lock it.' : 'It opens on the last day of a 12 Week Year, and stays until you lock it.'" />
    </div>
    <div v-else-if="!r.head" class="page-body"><Skeleton class="h-8 w-80" /><Skeleton class="h-64 w-full" /></div>
    <PeriodicDone v-else-if="r.head.status === 'Locked'" />
    <component :is="COMPS[tab]" v-else :key="tab" @go="go" />
  </div>
</template>
<script setup>
// The monthly and the 12-week review (issue 47), in the weekly review's shell: four numbered tabs in a fixed order, each open
// once the tabs before it are done. Everything is saved as it is done, so Pause leaves and opening Review resumes.
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Skeleton, toast } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
import ReviewHeader from '@/components/weekly/ReviewHeader.vue'
import PeriodicDone from './PeriodicDone.vue'
import TabLook from './TabLook.vue'
import TabScore from './TabScore.vue'
import TabDecide from './TabDecide.vue'
import TabPlan from './TabPlan.vue'
import TabReflect from './TabReflect.vue'
import { providePeriodic } from '@/lib/periodic'

const props = defineProps({ kind: String })
const COMPS = { look: TabLook, score: TabScore, decide: TabDecide, goals: TabDecide, plan: TabPlan, reflect: TabReflect }
const route = useRoute()
const router = useRouter()
const r = providePeriodic(props.kind)
const tab = computed(() => (r.head?.tabs.some((t) => t.value === route.query.tab) ? route.query.tab : null))

const openable = (t) => r.readOnly || r.head?.openable[t]
function go(next) {
  const h = r.head
  if (!h || next === tab.value) return
  if (!openable(next)) {
    const at = h.tabs.findIndex((t) => t.value === next)
    const before = h.tabs.filter((t, i) => i > 0 && i < at && !h.done[t.value])
    toast.warning(`Finish ${before.map((t) => t.label).join(' and ')} first.`)
    return
  }
  router.push({ query: { ...route.query, kind: props.kind, tab: next } })
}
function pause() { router.push('/') }
function settle() {
  const h = r.head
  if (h && (!tab.value || !openable(tab.value))) router.replace({ query: { ...route.query, kind: props.kind, tab: openable(h.first) ? h.first : h.tabs[0].value } })
}
async function visit() {
  const h = r.head
  const first = h?.tabs[0].value
  if (h?.name && h.status === 'Open' && tab.value === first && !h.done[first] && !r.readOnly) {
    try { await r.act('visit', { tab: first }) } catch (e) { /* said by act */ }
  }
}
watch(tab, visit)
onMounted(async () => {
  if (!(await r.load())) return
  settle()
  visit()
})
</script>
