<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review :data-review-tab="tab" :data-review-name="r.head?.name || ''">
    <ReviewHeader v-if="r.head" :tab="tab" @go="go" @pause="pause" />
    <div v-if="!r.head" class="page-body"><Skeleton class="h-8 w-80" /><Skeleton class="h-64 w-full" /></div>
    <ReviewDone v-else-if="r.head.status === 'Locked'" />
    <component :is="COMPS[tab]" v-else :key="tab" @go="go" />
  </div>
</template>
<script setup>
// The weekly review (set 8): four numbered tabs in a fixed order, at /today/week?view=review&tab=…. It opens on the first
// unfinished tab; a tab ahead opens only when the tabs before it are done, except that Library never blocks. Everything is
// saved as it is done, so Pause simply leaves (to the Week's calendar) and opening the review again resumes it.
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Skeleton, toast } from 'frappe-ui'
import ReviewHeader from './ReviewHeader.vue'
import ReviewDone from './ReviewDone.vue'
import TabLibrary from './TabLibrary.vue'
import TabTasks from './TabTasks.vue'
import TabGoals from './TabGoals.vue'
import TabReflect from './TabReflect.vue'
import { provideReview, TABS } from '@/lib/review'

const COMPS = { library: TabLibrary, tasks: TabTasks, goals: TabGoals, reflect: TabReflect }
const route = useRoute()
const router = useRouter()
const r = provideReview()
const tab = computed(() => (TABS.some((t) => t.value === route.query.tab) ? route.query.tab : null))

// read only (a site that refuses writes), nothing can be done in a tab, so every tab can be looked at
const openable = (t) => r.readOnly || r.head?.openable[t]
function go(next) {
  const h = r.head
  if (!h || next === tab.value) return
  if (!openable(next)) {
    const before = TABS.filter((t) => t.value !== 'library' && TABS.indexOf(t) < TABS.findIndex((x) => x.value === next) && !h.done[t.value])
    toast.warning(`Finish ${before.map((t) => t.label).join(' and ')} first.`)
    return
  }
  router.push({ query: { ...route.query, view: 'review', tab: next } })
}
function pause() {
  router.push({ path: '/today/week', query: { ...route.query, view: 'calendar', tab: undefined } })
}
// a tab that is missing or not open yet becomes the first unfinished one
function settle() {
  const h = r.head
  if (!h) return
  // links to set 7's review steps open the tab that replaced them
  const old = { results: 'goals', reset: 'tasks', goals: 'goals', 'look-back': 'reflect' }[route.query.step]
  if (old && openable(old)) return router.replace({ query: { ...route.query, step: undefined, view: 'review', tab: old } })
  if (!tab.value || !openable(tab.value)) router.replace({ query: { ...route.query, view: 'review', tab: openable(h.first) ? h.first : 'library' } })
}
async function visit() {
  const h = r.head
  if (h?.name && h.status === 'Open' && tab.value === 'library' && !h.done.library && !r.readOnly) {
    try { await r.act('visit', { tab: 'library' }) } catch (e) { /* said by act */ }
  }
}
watch(tab, visit)
onMounted(async () => {
  await r.load()
  settle()
  visit()
})
</script>
