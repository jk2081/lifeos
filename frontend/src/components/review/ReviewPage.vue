<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review :data-review-kind="kind" :data-review-tab="tab" :data-review-name="r.head?.name || ''">
    <ReviewHeader v-if="r.head" :tab="tab" :tabs="steps" :title="weekly ? 'Weekly review' : r.head.title" @go="go" @pause="pause" />
    <div v-if="r.notDue" class="page-body" data-review-not-due>
      <Empty :title="`No ${kind === 'monthly' ? 'monthly' : '12-week'} review is due.`" :hint="kind === 'monthly' ? 'It opens on your review day after a month ends, and stays until you lock it.' : 'It opens on the last day of a 12 Week Year, and stays until you lock it.'" />
    </div>
    <div v-else-if="!r.head" class="page-body"><Skeleton class="h-8 w-80" /><Skeleton class="h-64 w-full" /></div>
    <component :is="weekly ? ReviewDone : PeriodicDone" v-else-if="r.head.status === 'Locked'" />
    <component :is="COMPS[kind][tab]" v-else :key="tab" @go="go" />
  </div>
</template>
<script setup>
// The one review screen, for the weekly, the monthly and the 12-week review: four numbered steps in a fixed order, each open
// once the steps before it are done (the weekly review's Library never blocks). It opens on the first unfinished step.
// Everything is saved as it is done, so Pause simply leaves and opening the review again resumes it.
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Skeleton, toast } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
import ReviewHeader from '@/components/review/ReviewHeader.vue'
import ReviewDone from '@/components/review/ReviewDone.vue'
import PeriodicDone from '@/components/review/PeriodicDone.vue'
import TabLibrary from '@/components/review/WeeklyLibrary.vue'
import TabTasks from '@/components/review/WeeklyTasks.vue'
import TabGoals from '@/components/review/WeeklyGoals.vue'
import TabReflect from '@/components/review/WeeklyReflect.vue'
import TabLook from '@/components/review/PeriodicLook.vue'
import TabScore from '@/components/review/PeriodicScore.vue'
import TabDecide from '@/components/review/PeriodicDecide.vue'
import TabPlan from '@/components/review/PeriodicPlan.vue'
import TabPeriodicReflect from '@/components/review/PeriodicReflect.vue'
import { provideReview, TABS } from '@/lib/review'

const props = defineProps({ kind: { type: String, default: 'weekly' } })
const weekly = props.kind === 'weekly'
const COMPS = {
  weekly: { library: TabLibrary, tasks: TabTasks, goals: TabGoals, reflect: TabReflect },
  periodic: { look: TabLook, score: TabScore, decide: TabDecide, goals: TabDecide, plan: TabPlan, reflect: TabPeriodicReflect },
}
COMPS.monthly = COMPS['12-weeks'] = COMPS.periodic
const route = useRoute()
const router = useRouter()
const r = provideReview(props.kind)
const steps = computed(() => (weekly ? TABS : r.head?.tabs || []))
const tab = computed(() => (steps.value.some((t) => t.value === route.query.tab) ? route.query.tab : null))

// read only (a site that refuses writes), nothing can be done in a tab, so every tab can be looked at
const openable = (t) => r.readOnly || r.head?.openable[t]
// the address of a step: the weekly review lives in the Week's Review view, the others at /review?kind=…
const at = (next) => ({ query: { ...route.query, ...(weekly ? { view: 'review' } : { kind: props.kind }), tab: next } })
function go(next) {
  const h = r.head
  if (!h || next === tab.value) return
  if (!openable(next)) {
    const to = steps.value.findIndex((x) => x.value === next)
    const before = steps.value.filter((t, i) => i < to && !h.done[t.value] && (weekly ? t.value !== 'library' : i > 0))
    toast.warning(`Finish ${before.map((t) => t.label).join(' and ')} first.`)
    return
  }
  router.push(at(next))
}
function pause() {
  router.push(weekly ? { path: '/today/week', query: { ...route.query, view: 'calendar', tab: undefined } } : '/')
}
// a tab that is missing or not open yet becomes the first unfinished one
function settle() {
  const h = r.head
  if (!h) return
  // links to set 7's review steps open the tab that replaced them
  const old = weekly && { results: 'goals', reset: 'tasks', goals: 'goals', 'look-back': 'reflect' }[route.query.step]
  if (old && openable(old)) return router.replace({ query: { ...route.query, step: undefined, view: 'review', tab: old } })
  if (!tab.value || !openable(tab.value)) router.replace(at(openable(h.first) ? h.first : steps.value[0].value))
}
async function visit() {
  const h = r.head
  const first = steps.value[0]?.value
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
