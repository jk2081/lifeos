<template>
  <PageHead :title="String(year)" :sub="sub">
    <Button :label="`‹ ${year - 1}`" data-year-prev @click="go(year - 1)" />
    <Button :label="`${year + 1} ›`" data-year-next @click="go(year + 1)" />
  </PageHead>
  <div class="page-body" data-year-view :data-year="year">
    <template v-if="d">
      <ViewLinks :links="LINKS" />
      <p class="text-sm text-ink-gray-6 max-md:hidden">Click a goal to open it, click a month to open Month. The red line is today.</p>

      <!-- the timeline: months across the top, a lane for the 12 Week Years, one for each area that is on, key dates and the weekly reviews -->
      <div class="overflow-hidden rounded-5 border border-outline-gray-2 max-md:hidden" data-year-timeline>
        <div class="grid grid-cols-[11rem_minmax(0,1fr)]">
          <div class="border-b border-outline-gray-1" />
          <div class="relative grid grid-cols-12 border-b border-outline-gray-1">
            <div v-for="(m, i) in MONTHS" :key="m" class="relative border-l border-outline-gray-1 px-2 py-2 text-xs font-semibold first:border-l-0"
              :class="i === todayMonth ? 'bg-surface-gray-9 text-ink-base' : 'bg-surface-gray-1 text-ink-gray-7'" :data-month-head="i + 1" :data-current="i === todayMonth || undefined">
              <button type="button" class="absolute inset-0 focus-visible:focus-ring" :aria-label="`Open ${m} ${year} in Month`" @click="openMonth(i)" />{{ m.slice(0, 3) }}</div>
          </div>

          <template v-for="row in rows" :key="row.key">
            <div class="flex min-w-0 flex-col justify-center border-b border-outline-gray-1 px-3 py-2" :data-lane="row.key">
              <div class="flex items-center gap-2 text-sm-medium text-ink-gray-9"><span v-if="row.dot" class="size-2 shrink-0 rounded-full" :class="row.dot" aria-hidden="true" /><span class="truncate">{{ row.label }}</span></div>
              <div v-if="row.sub" class="truncate text-xs text-ink-gray-6">{{ row.sub }}</div>
            </div>
            <div class="relative border-b border-outline-gray-1" :style="{ height: row.height + 'rem' }">
              <div class="pointer-events-none absolute inset-0 grid grid-cols-12" aria-hidden="true"><i v-for="m in 12" :key="m" class="border-l border-outline-gray-1 first:border-l-0" /></div>
              <!-- the 12 Week Years -->
              <template v-if="row.kind === 'cycles'">
                <div v-for="c in d.cycles" :key="c.name" class="absolute top-2 flex h-8 items-center justify-center truncate rounded-4 px-2 text-xs"
                  :class="c.status === 'Active' ? 'bg-surface-gray-9 font-medium text-ink-base' : 'bg-surface-gray-2 text-ink-gray-7'" :style="span(c.start, c.end)" data-cycle-bar :data-status="c.status">
                  {{ cycleLabel(c) }}</div>
              </template>
              <!-- the goals of an area: a bar across their dates, grey when finished, carried or dropped -->
              <template v-else-if="row.kind === 'lane'">
                <div v-for="g in row.goals" :key="g.name" class="absolute flex h-8 items-center overflow-hidden rounded-4 border-l-[3px] px-2 text-xs"
                  :class="g.grey ? 'border-outline-gray-3 bg-surface-gray-2 text-ink-gray-7' : tone(row.colour)" :style="{ ...span(g.start, g.end), top: 0.5 + g.track * 2.25 + 'rem' }" data-goal-bar :data-goal="g.name" :data-grey="g.grey || undefined">
                  <RouterLink class="absolute inset-0 focus-visible:focus-ring" :to="`/goals/${g.name}`" :aria-label="g.title" />
                  <span class="truncate">{{ g.label }}</span></div>
              </template>
              <!-- key dates as pins -->
              <template v-else-if="row.kind === 'pins'">
                <div v-for="(k, i) in d.key_dates" :key="k.kind + k.name + k.date" class="absolute flex max-w-[9rem] items-center gap-1 text-xs text-ink-gray-8" :style="{ left: pos(k.date) + '%', top: 0.5 + (i % 3) * 1.2 + 'rem' }"
                  data-pin :data-date="k.date">
                  <span class="size-2 shrink-0 rounded-full" :class="PIN[k.kind]" aria-hidden="true" /><span class="truncate">{{ k.title }}</span></div>
              </template>
              <!-- one tick for each weekly review -->
              <template v-else-if="row.kind === 'reviews'">
                <i v-for="w in d.reviews.weeks" :key="w.start" class="absolute top-4 h-4 w-0.5 rounded-full" :class="w.done ? 'bg-surface-blue-7' : w.future ? 'bg-surface-blue-3' : 'bg-surface-gray-4'"
                  :style="{ left: pos(w.start) + '%' }" data-review-tick :data-done="w.done || undefined" :data-start="w.start" />
              </template>
              <div v-if="showToday" class="pointer-events-none absolute inset-y-0 w-px bg-surface-red-5" :style="{ left: pos(d.today) + '%' }" data-today-line aria-hidden="true" />
            </div>
          </template>
        </div>
      </div>

      <!-- a phone: a list of months, each with the goals that run through it and its key dates -->
      <div class="flex flex-col gap-4 md:hidden" data-year-list>
        <section v-for="(m, i) in MONTHS" :key="m" :data-month-section="i + 1">
          <SectionHead><RouterLink class="hover:underline focus-visible:focus-ring" :to="monthTo(i)">{{ m }}</RouterLink><span v-if="i === todayMonth" class="text-ink-gray-6">· this month</span></SectionHead>
          <Card flush>
            <Row v-for="g in goalsIn(i)" :key="g.name" :pane="null" class="!items-center">
              <RouterLink class="min-w-0 flex-1 break-words text-base focus-visible:focus-ring" :class="g.grey ? 'text-ink-gray-7' : 'text-ink-blue-8'" :to="`/goals/${g.name}`">{{ g.label }}</RouterLink>
              <span class="text-sm text-ink-gray-6">{{ g.area }}</span>
            </Row>
            <Row v-for="k in pinsIn(i)" :key="k.kind + k.name + k.date" class="!items-center">
              <span class="size-2 shrink-0 rounded-full" :class="PIN[k.kind]" aria-hidden="true" /><span class="min-w-0 flex-1 break-words text-base text-ink-gray-8">{{ k.title }}</span>
              <span class="text-sm tabular-nums text-ink-gray-6">{{ short(k.date) }}</span>
            </Row>
            <Empty v-if="!goalsIn(i).length && !pinsIn(i).length" title="Nothing yet." />
          </Card>
        </section>
        <p class="text-sm text-ink-gray-6" data-reviews-phone>Weekly reviews: {{ d.reviews.done }} of {{ d.reviews.total }} done</p>
      </div>

      <div class="grid grid-cols-1 gap-4 md:grid-cols-3" data-year-cards>
        <Card data-card="so-far">
          <h2 class="mb-2 text-base font-semibold text-ink-gray-9">This year so far</h2>
          <p class="text-sm text-ink-gray-7">{{ d.summary.finished }} goal{{ d.summary.finished === 1 ? '' : 's' }} finished · {{ d.summary.carried }} carried over · {{ d.summary.dropped }} dropped</p>
          <p class="mt-1 text-sm text-ink-gray-7">{{ d.summary.average === null ? 'No 12 Week score yet.' : `Average 12-week score ${d.summary.average}%` }}</p>
        </Card>
        <Card data-card="next">
          <template v-if="d.next_cycle">
            <h2 class="mb-2 text-base font-semibold text-ink-gray-9">Next 12 Week Year starts {{ long(d.next_cycle.start) }}</h2>
            <p class="text-sm text-ink-gray-7">{{ planningText }}</p>
          </template>
          <template v-else>
            <h2 class="mb-2 text-base font-semibold text-ink-gray-9">The next 12 Week Year</h2>
            <p class="text-sm text-ink-gray-7">{{ year < thisYear ? 'This year is over.' : 'No 12 Week Year is running, so none is planned.' }}</p>
          </template>
        </Card>
        <Card v-if="d.insight" data-card="noticed">
          <h2 class="mb-2 flex items-center gap-1.5 text-base font-semibold text-ink-gray-9"><span class="lucide-sparkles size-4 text-ink-violet-8" aria-hidden="true" />The Brain noticed</h2>
          <p class="text-sm text-ink-gray-7">{{ d.insight.body || d.insight.title }}</p>
        </Card>
      </div>
    </template>
    <div v-else class="py-8 text-sm text-ink-gray-6">{{ failed ? 'The year could not be loaded.' : 'Loading…' }}</div>
  </div>
</template>
<script setup>
// Today > Year (issue 16): the year as a timeline. Months across the top with the current one marked and a line at today; a lane
// for the 12 Week Years with each cycle's score; a lane for each area that is on (a part gets its own row) with each goal as a bar
// across its dates, finished, carried and dropped ones in grey; key dates as pins; one tick for each weekly review; three cards.
// On a phone it is a list of months with their goals. `year=` is in the URL.
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import ViewLinks from './ViewLinks.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { onRecordChanged } from '@/lib/pane'
import { MONTHS, long, parse, short } from '@/lib/dates'

const route = useRoute()
const router = useRouter()
const LINKS = [{ label: '12 Week grid', to: { path: '/today/year', query: { view: 'cycle' } } }, { label: 'Goals across cycles', to: { path: '/today/year', query: { view: 'goals' } } }]
const thisYear = parse(store.today).getFullYear()
const year = computed(() => Number(route.query.year) || thisYear)
const d = ref(null)
const failed = ref(false)
async function load() {
  const res = await tryCall(() => api('calendar.year_plan', { space: store.space, year: year.value, area: store.lensArea || undefined }))
  failed.value = !res
  if (res) d.value = res
}
watch(year, () => { d.value = null; load() }, { immediate: true })
onRecordChanged(load)
const go = (y) => router.push({ path: route.path, query: { ...route.query, open: undefined, year: y === thisYear ? undefined : y } })

// where a date falls on the track: the share of the year, with every month the same width as the header's twelve columns
const pos = (date) => {
  const p = parse(date)
  const inYear = p.getFullYear() === year.value ? p : parse(`${year.value}-${p.getFullYear() < year.value ? '01-01' : '12-31'}`)
  return ((inYear.getMonth() + (inYear.getDate() - 1) / new Date(year.value, inYear.getMonth() + 1, 0).getDate()) / 12) * 100
}
const end = (date) => pos(date) + 100 / 12 / new Date(year.value, parse(date).getMonth() + 1, 0).getDate()
const span = (a, b) => ({ left: pos(a) + '%', width: Math.max(end(b) - pos(a), 1.5) + '%' })
const todayMonth = computed(() => (store.today.startsWith(String(year.value)) ? parse(store.today).getMonth() : -1))
const showToday = computed(() => todayMonth.value >= 0)
const openMonth = (i) => router.push(monthTo(i))
const monthTo = (i) => ({ path: '/today/month', query: { date: `${year.value}-${String(i + 1).padStart(2, '0')}-01` } })

const TONE = {
  blue: 'border-outline-blue-3 bg-surface-blue-2 text-ink-blue-9', green: 'border-outline-green-3 bg-surface-green-2 text-ink-green-8', amber: 'border-outline-amber-3 bg-surface-amber-2 text-ink-amber-9',
  red: 'border-outline-red-3 bg-surface-red-2 text-ink-red-8', violet: 'border-outline-violet-3 bg-surface-violet-2 text-ink-violet-8', teal: 'border-outline-teal-3 bg-surface-teal-2 text-ink-teal-8',
  orange: 'border-outline-orange-3 bg-surface-orange-2 text-ink-orange-8', pink: 'border-outline-pink-3 bg-surface-pink-2 text-ink-pink-8', cyan: 'border-outline-cyan-3 bg-surface-cyan-2 text-ink-cyan-8',
  gray: 'border-outline-gray-3 bg-surface-gray-2 text-ink-gray-8',
}
const DOT = { blue: 'bg-surface-blue-7', green: 'bg-surface-green-7', amber: 'bg-surface-amber-7', red: 'bg-surface-red-7', violet: 'bg-surface-violet-7', teal: 'bg-surface-teal-7',
  orange: 'bg-surface-orange-7', pink: 'bg-surface-pink-7', cyan: 'bg-surface-cyan-7', gray: 'bg-surface-gray-7' }
const PIN = { important: 'bg-surface-red-7', vault: 'bg-surface-amber-7', trip: 'bg-surface-blue-7', event: 'bg-surface-gray-7' }
const tone = (c) => TONE[c] || TONE.gray

const cycleLabel = (c) => {
  const a = MONTHS[parse(c.start).getMonth()].slice(0, 3), b = MONTHS[parse(c.end).getMonth()].slice(0, 3)
  const score = c.status === 'Active' ? ` · week ${c.week} of 12${c.score === null ? '' : ` · ${c.score}%`}` : c.score === null ? '' : ` · ${c.score}%`
  return `${a} to ${b}${score}`
}
// goals that overlap in time go on separate tracks of their lane, so no bar covers another
function lane(l) {
  const ends = []
  const goals = [...l.goals].sort((a, b) => a.start.localeCompare(b.start)).map((g) => {
    let track = ends.findIndex((e) => e < g.start)
    if (track < 0) track = ends.length
    ends[track] = g.end
    return { ...g, track }
  })
  return { key: 'area-' + l.area, kind: 'lane', label: l.name, sub: l.part_of ? `part of ${l.part_of}` : null, dot: l.part_of ? null : DOT[l.colour] || DOT.gray, colour: l.colour, goals,
    height: Math.max(ends.length, 1) * 2.25 + 0.75 }
}
// the lanes: the 12 Week Years, then one row for each area that is on, then key dates and the weekly reviews
const rows = computed(() => [
  { key: 'cycles', kind: 'cycles', label: '12 Week Years', sub: 'score per cycle', height: 3.25 },
  ...d.value.lanes.map((l) => lane(l)),
  { key: 'pins', kind: 'pins', label: 'Key dates', sub: 'deadlines, birthdays, events', height: 4 },
  { key: 'reviews', kind: 'reviews', label: 'Weekly reviews', sub: `${d.value.reviews.done} of ${d.value.reviews.total} done`, height: 3 },
])
const sub = computed(() => (d.value ? `${d.value.cycles.length} twelve-week year${d.value.cycles.length === 1 ? '' : 's'} · ${d.value.goal_count} goal${d.value.goal_count === 1 ? '' : 's'} · ${d.value.key_dates.length} key dates` : ' '))
const planningText = computed(() => {
  const n = d.value.next_cycle
  const opens = n.planning_opens <= store.today ? 'Planning is open now, in the weekly review.' : `Planning opens in the review on ${long(n.planning_opens)}.`
  return n.planned ? `It is planned. ${opens.replace('Planning is open now', 'Planning is open')}` : opens
})
// phone: the goals that run through a month, and its pins
const goalsIn = (i) => d.value.lanes.flatMap((l) => l.goals.filter((g) => g.start.slice(0, 7) <= `${year.value}-${String(i + 1).padStart(2, '0')}` && g.end.slice(0, 7) >= `${year.value}-${String(i + 1).padStart(2, '0')}`).map((g) => ({ ...g, area: l.name })))
const pinsIn = (i) => d.value.key_dates.filter((k) => parse(k.date).getMonth() === i)
</script>
