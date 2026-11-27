<template>
  <PageHead :title="title" :sub="sub">
    <Button icon="lucide-chevron-left" label="Previous week" tooltip="Previous week" data-cal-prev @click="step(-1)" />
    <Button label="Today" data-cal-today @click="go(store.today)" />
    <Button icon="lucide-chevron-right" label="Next week" tooltip="Next week" data-cal-next @click="step(1)" />
    <WeekMenu />
  </PageHead>
  <div ref="root" class="page-body" data-week-view :data-week-start="first">
    <Dashboard v-if="mode === 'overview'" view="week" />
    <ViewLinks v-if="mode === 'overview'" :links="LINKS" />
    <template v-else>
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-gray-6" data-legend>
        <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-surface-gray-3"></i>meetings</span>
        <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-surface-blue-3"></i>goal work</span>
        <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3 rounded-sm bg-surface-red-3"></i>due dates</span>
      </div>
      <Ruler />
      <div class="flex min-w-0 flex-col gap-2">
        <WeekBars :days="days" :items="data?.items" />
        <div class="grid min-w-0 items-start gap-2" :class="tight ? 'grid-cols-1' : 'grid-cols-7 max-md:grid-cols-1'" data-week-grid :data-stacked="tight ? 1 : 0">
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
      </div>
    </template>
  </div>
</template>
<script setup>
// Today > Week (issues 16 and 132): Overview is the dashboard; Calendar is the ruler and the seven days with what is on each (meetings, goal work, due tasks, important dates), the full
// width. A day opens in Day; an item opens in the record pane. The cursor is `date=`. The week's score and goal work are Overview's (Goals by area).
import { todayData } from '@/data/today'
import { computed, ref, watch } from 'vue'
import { useElementSize } from '@vueuse/core'
import { useRoute, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Dashboard from './Dashboard.vue'
import Ruler from './Ruler.vue'
import ViewLinks from './ViewLinks.vue'
import WeekBars from './WeekBars.vue'
import WeekMenu from './WeekMenu.vue'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { chipClass, isBar, itemLabel, itemRef, openDay, useCalendarRange } from '@/lib/calRange'
import { onRecordChanged, openRef } from '@/lib/pane'
import { todayMode as mode } from '@/lib/todayMode'
import { addDays, dayRange, long, parse, startOfWeek, time, weekday } from '@/lib/dates'

const route = useRoute()
// The week fits its own width, not the window's: with Chat or the record pane beside it the page can be narrow on a laptop.
// Under 760 px the days stack (as on a phone) instead of breaking words letter by letter.
const root = ref(null)
const { width } = useElementSize(root)
const tight = computed(() => width.value > 0 && width.value < 760)
const router = useRouter()
const LINKS = [{ label: 'Weekly review', to: { path: '/today/week', query: { view: 'review' } } }, { label: 'Agenda', to: { path: '/today/week', query: { view: 'agenda' } } }]
// Settings > Rhythms: the week starts on Monday or Sunday
const first = computed(() => { const d = startOfWeek(route.query.date || store.today); return store.settings?.week_starts_on === 'Sunday' ? addDays(d, -1) : d })
const days = computed(() => Array.from({ length: 7 }, (_, i) => addDays(first.value, i)))
const { data, itemsOn: allOn } = useCalendarRange(computed(() => [first.value, addDays(first.value, 6)]))
const itemsOn = (day) => allOn(day).filter((it) => !isBar(it))  // a multi-day all-day event is a bar above the days
const plan = ref(null)
async function loadPlan() {
  const res = await tryCall(() => todayData.calendar.week_plan({ space: store.space, week_start: first.value, area: store.lensArea || undefined }))
  if (res) plan.value = res
}
watch(first, loadPlan, { immediate: true })
onRecordChanged(loadPlan)

const hours = (m) => `${Math.round(m / 6) / 10} h`
const title = computed(() => dayRange(first.value, addDays(first.value, 6)))
const sub = computed(() => [plan.value?.score ? `Week ${plan.value.score.week} of the 12 Week Year` : 'Not in a 12 Week Year', plan.value?.goal_minutes ? `${hours(plan.value.goal_minutes)} of goal work planned` : null].filter(Boolean).join(' · ') || ' ')
const go = (date) => router.push({ path: route.path, query: { ...route.query, open: undefined, date: date === store.today ? undefined : date } })
const step = (n) => go(addDays(first.value, 7 * n))
</script>
