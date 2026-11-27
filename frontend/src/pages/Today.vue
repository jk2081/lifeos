<template>
  <template v-if="d">
    <PageHead :title="`${weekday(date, phone ? 3 : 0)}, ${long(date, other)}`">
      <template #sub><span v-if="!other" data-today-sub>
        <template v-if="d.cycle && d.cycle.week">Week {{ d.cycle.week }} of {{ d.cycle.weeks }} · </template>
        <template v-else-if="d.cycle">{{ d.cycle.title }} {{ d.cycle.ended ? 'has ended' : 'has not started' }} · </template>
        {{ d.days_left }} day{{ d.days_left === 1 ? '' : 's' }} left<span class="max-md:hidden"> this week</span><span class="max-md:hidden" data-day-summary> · {{ meetingCount }} meeting{{ meetingCount === 1 ? '' : 's' }}</span></span>
        <span v-else data-today-sub>{{ date < store.today ? 'That day' : 'This day' }}</span>
      </template>
      <Button icon="lucide-chevron-left" label="Previous day" tooltip="Previous day" data-cal-prev @click="go(addDays(date, -1))" />
      <Button label="Today" data-cal-today @click="go(store.today)" />
      <Button icon="lucide-chevron-right" label="Next day" tooltip="Next day" data-cal-next @click="go(addDays(date, 1))" />
    </PageHead>

    <div class="page-body !gap-5">
      <!-- a rhythm that is due (UX fixes, set 6): at most one line, above the list, with Skip until its next occurrence -->
      <div v-if="d.banner && !other" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-4 py-2.5" role="status"
        data-rhythm-banner :data-banner="d.banner.key">
        <span class="lucide-bell size-4 text-ink-gray-7" aria-hidden="true" />
        <RouterLink class="min-w-0 flex-1 text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="d.banner.to" data-banner-open>{{ d.banner.text }}</RouterLink>
        <Button size="sm" variant="solid" :label="d.banner.action" :route="d.banner.to" />
        <Button size="sm" variant="ghost" label="Skip" data-banner-skip @click="skipBanner" />
      </div>
      <!-- issue 102: the AI service is not answering (credit, the key or the provider), until a call works again -->
      <!-- issue 118/130: the waiting pile is never on Today; one line says when some of it is late, and Look now opens the Waiting list -->
      <div v-if="d.waiting_past?.count && !other" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-4 py-2.5" role="status" data-waiting-past>
        <span class="min-w-0 flex-1 text-base text-ink-gray-9">{{ d.waiting_past.line }}</span>
        <Button size="sm" label="Look now" data-waiting-look @click="openRef('list:waiting-overdue')" />
      </div>
      <div v-if="d.brain_off && !other" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-5 border border-outline-amber-1 bg-surface-amber-1 px-4 py-2.5" role="status" data-brain-off>
        <span class="lucide-triangle-alert size-4 text-ink-amber-8" aria-hidden="true" />
        <span class="min-w-0 flex-1 text-base text-ink-gray-9">The Brain is off: {{ d.brain_off }}</span>
        <Button size="sm" label="Settings › AI" :route="{ path: '/settings', query: { tab: 'advanced' } }" data-brain-off-open />
      </div>
      <!-- set 7: what the rule for Inbox items left too long parked or discarded on its own, with Undo for seven days -->
      <div v-if="d.auto_inbox && !other" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-4 py-2.5" role="status" data-auto-inbox>
        <span class="lucide-inbox size-4 text-ink-gray-7" aria-hidden="true" />
        <span class="min-w-0 flex-1 text-base text-ink-gray-9">{{ autoText }}</span>
        <Button size="sm" label="Undo" data-auto-inbox-undo @click="undoAuto" />
      </div>
      <!-- issue 132: Overview is the work slice (cards and panels); Calendar is the time slice, with the ruler directly above it -->
      <Dashboard v-if="mode === 'overview'" view="day" />
      <template v-else>
        <Ruler />
        <DayTimeline :date="date" />
      </template>
    </div>
  </template>
  <div v-else class="page-body"><Skeleton class="h-24 w-full" /><Skeleton class="h-72 w-full" /></div>
</template>

<script setup>
// Today > Day (issues 55, 123 and 132): Overview is the dashboard (four cards, the top three and what needs you); Calendar is the day's one timeline under the ruler. Both are for
// any date (`date=`); the banners (a rhythm that is due, the AI service, the Inbox rule's parking) show on today.
import { todayData } from '@/data/today'
import { computed, onMounted, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button, Skeleton } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Dashboard from '@/components/today/Dashboard.vue'
import DayTimeline from '@/components/today/DayTimeline.vue'
import Ruler from '@/components/today/Ruler.vue'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { addDays, long, short, weekday } from '@/lib/dates'
import { openRef } from '@/lib/pane'
import { askScope, lensScope } from '@/lib/ask'
import { todayMode as mode } from '@/lib/todayMode'

const router = useRouter()
const route = useRoute() // at=: a test site moves the banners' clock (site config lifeos_test_clock)
const phone = useMediaQuery('(max-width: 767px)')
const d = ref(null)
askScope(lensScope) // the lens's area, or everything in the space (set 6)
const date = computed(() => (/^\d{4}-\d{2}-\d{2}$/.test(String(route.query.date || '')) ? route.query.date : store.today))
const other = computed(() => date.value !== store.today)
const meetingCount = computed(() => d.value.rail.events.filter((e) => e.source !== 'task').length)
const go = (to) => router.push({ path: route.path, query: { ...route.query, open: undefined, date: to === store.today ? undefined : to } })

const autoText = computed(() => {
  const a = d.value.auto_inbox
  const parts = [a.parked && `parked ${a.parked} in Someday`, a.discarded && `moved ${a.discarded} to the trash`].filter(Boolean)
  return `Inbox items older than ${a.days} days: ${parts.join(' and ')}. Undo until ${short(a.undo_until)}.`
})
async function undoAuto() {
  if (await tryCall(() => todayData.old_items.undo_auto({ space: store.space }), 'Back in the Inbox')) load()
}
async function skipBanner() {
  const occ = d.value.banner.occurrence
  d.value.banner = null
  await tryCall(() => todayData.today.skip_banner({ occurrence: occ }), 'Skipped until next time.')
  load()
}
async function load() {
  const res = await tryCall(() => todayData.today.get({ space: store.space, area: store.lensArea || undefined, at: route.query.at || undefined }))
  if (res) d.value = res
}
watch(() => store.space, load)
onMounted(load)
</script>
