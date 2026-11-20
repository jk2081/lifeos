<template>
  <PageHead :title="title" :sub="sub">
    <Button icon="lucide-chevron-left" label="Previous week" tooltip="Previous week" data-cal-prev @click="step(-1)" />
    <Button label="This week" data-cal-today @click="go(store.today)" />
    <Button icon="lucide-chevron-right" label="Next week" tooltip="Next week" data-cal-next @click="step(1)" />
  </PageHead>
  <div class="page-body" data-week-view :data-week-start="first">
    <ViewLinks :links="LINKS" />
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-gray-6" data-legend>
      <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-surface-gray-3"></i>meetings</span>
      <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-surface-blue-3"></i>goal work</span>
      <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-surface-red-3"></i>due dates</span>
    </div>
    <div class="grid grid-cols-1 gap-5 md:grid-cols-[minmax(0,1fr)_18.5rem]">
      <div class="grid min-w-0 grid-cols-7 items-start gap-2 max-md:grid-cols-1" data-week-grid>
        <Card v-for="day in days" :key="day" class="flex min-h-48 min-w-0 flex-col gap-1.5 !p-2 max-md:min-h-0" :data-day="day" :data-today="day === store.today || undefined">
          <Button class="!justify-start" :variant="day === store.today ? 'solid' : 'ghost'" :label="`${weekday(day, 3)} ${parse(day).getDate()}`" :aria-label="`Open ${long(day)} in Day`"
            data-open-day @click="openDay(day)" />
          <div v-for="(it, i) in itemsOn(day)" :key="i" class="relative cursor-pointer rounded px-1.5 py-1 text-sm [overflow-wrap:anywhere]" :class="chipClass(it)" data-week-item :data-source="it.source">
            <button type="button" class="absolute inset-0 rounded focus-visible:focus-ring" :aria-label="itemLabel(it)" :data-ref="itemRef(it)" @click="openRef(itemRef(it))" />
            <span v-if="!it.all_day" class="tabular-nums opacity-80">{{ time(it.start) }}</span> {{ itemLabel(it) }}
          </div>
          <div v-if="!itemsOn(day).length" class="text-sm text-ink-gray-6 max-md:hidden">Nothing</div>
        </Card>
      </div>
      <aside class="flex min-w-0 flex-col gap-4" data-week-side>
        <Card data-week-focus>
          <h2 class="mb-2 text-base font-semibold text-ink-gray-9">The week's focus</h2>
          <template v-if="plan">
            <div v-if="plan.score" class="mb-3" data-week-score>
              <div class="flex items-baseline gap-2"><span class="text-2xl-semibold tabular-nums text-ink-gray-9">{{ Math.round(plan.score.percent) }}%</span>
                <span class="text-sm text-ink-gray-6">week {{ plan.score.week }} of {{ plan.score.weeks }} · target {{ plan.target }}%</span></div>
              <Progress class="mt-1.5" size="sm" :value="Math.min(Math.round(plan.score.percent), 100)" />
            </div>
            <p v-else class="mb-3 text-sm text-ink-gray-6">This week is not in a 12 Week Year, so it has no score.</p>
            <Row v-for="t in plan.top" :key="t.name" :pane="'task:' + t.name" :label="t.title" class="!items-center">
              <span class="lucide-star size-3.5 shrink-0 text-ink-amber-8" aria-hidden="true" /><span class="min-w-0 flex-1 break-words text-base text-ink-gray-9">{{ t.title }}</span>
            </Row>
            <p v-if="!plan.top.length" class="text-sm text-ink-gray-6">No top three chosen yet. The weekly review sets them.</p>
          </template>
        </Card>
        <Card data-week-goals>
          <h2 class="mb-2 text-base font-semibold text-ink-gray-9">Goals this week</h2>
          <template v-if="plan">
            <Row v-for="g in plan.goals" :key="g.goal" class="!items-center" data-goal-block>
              <RouterLink class="relative min-w-0 flex-1 break-words text-base text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="`/goals/${g.goal}`">{{ g.title }}</RouterLink>
              <span class="text-sm tabular-nums text-ink-gray-6">{{ hours(g.minutes) }}</span>
            </Row>
            <p v-if="!plan.goals.length" class="text-sm text-ink-gray-6">No time planned for a goal yet. Plan a task at a time and it shows here.</p>
          </template>
        </Card>
      </aside>
    </div>
  </div>
</template>
<script setup>
// Today > Week (issue 16): seven days with what is on each (meetings, goal work, due tasks, important dates), the week's focus
// and score, and the goal work planned by goal. A day opens in Day; an item opens in the record pane. The cursor is `date=`.
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button, Progress } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import ViewLinks from './ViewLinks.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { chipClass, itemLabel, itemRef, openDay, useCalendarRange } from '@/lib/calRange'
import { onRecordChanged, openRef } from '@/lib/pane'
import { MONTHS, addDays, long, parse, startOfWeek, time, weekday } from '@/lib/dates'

const route = useRoute()
const router = useRouter()
const LINKS = [{ label: 'Weekly review', to: { path: '/today/week', query: { view: 'review' } } }, { label: 'Agenda', to: { path: '/today/week', query: { view: 'agenda' } } }]
// Settings > Rhythms: the week starts on Monday or Sunday
const first = computed(() => { const d = startOfWeek(route.query.date || store.today); return store.settings?.week_starts_on === 'Sunday' ? addDays(d, -1) : d })
const days = computed(() => Array.from({ length: 7 }, (_, i) => addDays(first.value, i)))
const { itemsOn } = useCalendarRange(computed(() => [first.value, addDays(first.value, 6)]))
const plan = ref(null)
async function loadPlan() {
  const res = await tryCall(() => api('calendar.week_plan', { space: store.space, week_start: first.value, area: store.lensArea || undefined }))
  if (res) plan.value = res
}
watch(first, loadPlan, { immediate: true })
onRecordChanged(loadPlan)

const hours = (m) => `${Math.round(m / 6) / 10} h`
const title = computed(() => {
  const a = parse(first.value), b = parse(addDays(first.value, 6))
  return a.getMonth() === b.getMonth() ? `${a.getDate()} to ${b.getDate()} ${MONTHS[b.getMonth()]}` : `${a.getDate()} ${MONTHS[a.getMonth()]} to ${b.getDate()} ${MONTHS[b.getMonth()]}`
})
const sub = computed(() => [plan.value?.score ? `Week ${plan.value.score.week} of the 12 Week Year` : 'Not in a 12 Week Year', plan.value?.goal_minutes ? `${hours(plan.value.goal_minutes)} of goal work planned` : null].filter(Boolean).join(' · ') || ' ')
const go = (date) => router.push({ path: route.path, query: { ...route.query, open: undefined, date: date === store.today ? undefined : date } })
const step = (n) => go(addDays(first.value, 7 * n))
</script>
