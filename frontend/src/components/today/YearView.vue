<template>
  <PageHead title="Year" :sub="sub">
    <Button icon="lucide-chevron-left" label="Back one cycle" tooltip="Back one cycle" data-year-prev @click="go(shift - 1)" />
    <Button label="Today" data-year-today @click="go(0)" />
    <Button icon="lucide-chevron-right" label="Forward one cycle" tooltip="Forward one cycle" data-year-next @click="go(shift + 1)" />
  </PageHead>
  <div class="page-body" data-year-view :data-shift="shift">
    <Dashboard view="year" />
    <template v-if="d">
      <!-- the cycles around today: columns across, a row for the score, one for each area that is on, key dates by week, weekly reviews -->
      <div ref="wrap" class="relative max-md:hidden" data-year-timeline>
        <div class="overflow-hidden rounded-5 border border-outline-gray-2">
          <div class="grid grid-cols-[10rem_minmax(0,1fr)]">
            <div class="border-b border-outline-gray-1" />
            <div class="relative grid grid-cols-4 border-b border-outline-gray-1">
              <div v-for="(c, i) in d.columns" :key="c.start" class="flex min-w-0 flex-col px-3 py-2 text-xs" :class="[i > 0 && 'border-l border-outline-gray-1', c.when === 'current' ? 'bg-surface-gray-3' : 'bg-surface-gray-1']"
                :data-col="i + 1" :data-current="c.when === 'current' || undefined">
                <span class="truncate text-sm font-semibold text-ink-gray-9">{{ c.label }}</span>
                <span class="truncate text-ink-gray-6">{{ range(c) }}</span>
              </div>
            </div>

            <template v-for="row in rows" :key="row.key">
              <div class="flex min-w-0 flex-col justify-center border-b border-outline-gray-1 px-3 py-2" :data-lane="row.key">
                <div class="flex items-center gap-2 text-sm-medium text-ink-gray-9"><span v-if="row.dot" class="size-2 shrink-0 rounded-full" :class="row.dot" aria-hidden="true" /><span class="truncate">{{ row.label }}</span></div>
                <div v-if="row.sub" class="truncate text-xs text-ink-gray-6">{{ row.sub }}</div>
              </div>
              <div :ref="row.kind === 'keys' ? (el) => (keyTrack = el) : undefined" class="relative border-b border-outline-gray-1" :style="{ height: row.height + 'rem' }">
                <div class="pointer-events-none absolute inset-0 grid grid-cols-4" aria-hidden="true">
                  <i v-for="(c, i) in d.columns" :key="c.start" :class="[i > 0 && 'border-l border-outline-gray-1', c.when === 'current' && 'bg-surface-gray-1']" />
                </div>

                <!-- the score of each cycle -->
                <div v-if="row.kind === 'scores'" class="absolute inset-0 grid grid-cols-4">
                  <div v-for="c in d.columns" :key="c.start" class="flex items-center justify-center px-2 text-sm tabular-nums" data-score :data-when="c.when">
                    <span v-if="c.when === 'current' && d.kind === 'cycle'" class="text-ink-gray-9">on track <b class="font-semibold">{{ c.score === null ? '–' : c.score + '%' }}</b></span>
                    <span v-else-if="c.when === 'future'" class="text-ink-gray-6">plan</span>
                    <b v-else class="font-semibold text-ink-gray-9">{{ c.score === null ? '–' : c.score + '%' }}</b>
                  </div>
                </div>

                <!-- the goals of an area: a bar across the cycle each belongs to; a small square marks a deadline -->
                <template v-else-if="row.kind === 'lane'">
                  <template v-if="row.empty">
                    <div class="absolute inset-0 flex items-center gap-3 px-3 text-sm text-ink-gray-7" data-year-empty>
                      <span class="min-w-0 truncate">No goals yet. Plan a 12 Week Year to see them here.</span>
                      <Button size="sm" variant="solid" label="Plan" data-year-plan @click="router.push('/goals/cycles')" />
                    </div>
                  </template>
                  <template v-else>
                    <div v-for="g in row.goals" :key="g.name" class="absolute flex h-8 items-center overflow-hidden rounded-4 border-l-[3px] px-2 text-xs"
                      :class="g.grey ? 'border-outline-gray-3 bg-surface-gray-2 text-ink-gray-7' : tone(row.colour)" :style="{ ...span(g.start, g.end), top: 0.5 + g.track * 2.25 + 'rem' }" data-goal-bar :data-goal="g.name" :data-grey="g.grey || undefined">
                      <RefLink class="absolute inset-0 focus-visible:focus-ring" :to="`goal:${g.name}`" :aria-label="g.title" />
                      <span class="truncate">{{ g.label }}</span></div>
                    <i v-for="g in row.goals.filter((x) => x.deadline)" :key="g.name + 'd'" class="pointer-events-none absolute size-2.5 -translate-x-1/2 rounded-[2px] bg-surface-red-7"
                      :style="{ left: pos(g.deadline < g.start ? g.start : g.deadline > g.end ? g.end : g.deadline) + '%', top: 0.5 + g.track * 2.25 + 1 - 0.3125 + 'rem' }" :title="`${g.title} is due ${long(g.deadline)}`" data-goal-deadline :data-date="g.deadline" />
                    <div v-for="i in row.planNext" :key="i" class="absolute inset-y-0 flex w-1/4 items-center justify-center" :style="{ left: (i - 1) * 25 + '%' }">
                      <RouterLink class="rounded-4 border border-dashed border-outline-gray-3 px-3 py-1 text-xs text-ink-blue-8 hover:bg-surface-gray-2 focus-visible:focus-ring" to="/goals/cycles" data-year-plan-next>+ Plan next cycle</RouterLink>
                    </div>
                  </template>
                </template>

                <!-- key dates: one dot a week, with a count; a lone date shows its title when there is room -->
                <template v-else-if="row.kind === 'keys'">
                  <template v-for="k in keyDots" :key="k.start">
                    <button type="button" class="absolute top-1/2 flex -translate-y-1/2 items-center justify-center rounded-full bg-surface-red-7 text-[10px] font-semibold leading-none text-ink-white focus-visible:focus-ring"
                      :style="{ left: k.x - dot / 2 + 'px', width: dot + 'px', height: dot + 'px' }" :aria-label="`${k.count} key date${k.count === 1 ? '' : 's'} in the week of ${long(k.start)}`" :aria-expanded="open === k.start"
                      data-key-dot :data-count="k.count" :data-week="k.start" @click="toggle(k, $event)">{{ dot >= 14 && k.count > 1 ? k.count : '' }}</button>
                    <span v-if="k.label" class="pointer-events-none absolute top-1/2 -translate-y-1/2 truncate text-xs text-ink-gray-8" :style="{ left: k.label.left + 'px', width: k.label.width + 'px' }" data-key-label>{{ k.items[0].title }}</span>
                  </template>
                  <span v-if="!d.key_weeks.length" class="absolute inset-0 flex items-center px-3 text-xs text-ink-gray-6" data-key-none>No key dates in these cycles.</span>
                </template>

                <!-- one tick for each weekly review since setup -->
                <template v-else-if="row.kind === 'reviews'">
                  <i v-for="w in d.reviews.weeks" :key="w.start" class="absolute top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full" :class="w.done ? 'bg-surface-blue-7' : w.future ? 'bg-surface-blue-3' : 'bg-surface-gray-4'"
                    :style="{ left: pos(w.start) + '%' }" data-review-tick :data-done="w.done || undefined" :data-start="w.start" />
                </template>
                <div v-if="showToday" class="pointer-events-none absolute inset-y-0 w-px bg-surface-red-5" :style="{ left: pos(d.today) + '%' }" data-today-line aria-hidden="true" />
              </div>
            </template>
          </div>
        </div>
        <!-- the key dates of one week -->
        <div v-if="openWeek" ref="pop" class="absolute z-20 w-72 max-w-full rounded-5 border border-outline-gray-2 bg-surface-white p-2 shadow-lg" :style="{ top: popAt.top + 'px', left: popAt.left + 'px' }"
          role="dialog" :aria-label="`Key dates, week of ${long(openWeek.start)}`" data-key-popover @keydown.esc="open = null">
          <div class="px-2 pb-1 pt-0.5 text-xs font-semibold text-ink-gray-6">Week of {{ long(openWeek.start) }} · {{ openWeek.count }} key date{{ openWeek.count === 1 ? '' : 's' }}</div>
          <button v-for="it in openWeek.items" :key="it.ref + it.date" type="button" class="flex w-full items-baseline gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-surface-gray-2 focus-visible:focus-ring" data-key-item @click="openItem(it)">
            <span class="w-14 shrink-0 text-xs tabular-nums text-ink-gray-6">{{ short(it.date) }}</span><span class="min-w-0 flex-1 break-words text-ink-gray-9">{{ it.title }}</span>
          </button>
        </div>
      </div>

      <!-- a phone: each cycle as a list, with its goals and its key dates -->
      <div class="flex flex-col gap-4 md:hidden" data-year-list>
        <Card v-if="!d.goal_count" data-year-empty-phone>
          <p class="text-sm text-ink-gray-7">No goals yet. Plan a 12 Week Year to see them here.</p>
          <Button class="mt-2" size="sm" variant="solid" label="Plan" data-year-plan @click="router.push('/goals/cycles')" />
        </Card>
        <section v-for="(c, i) in d.columns" :key="c.start" :data-col-section="i + 1" :data-current="c.when === 'current' || undefined">
          <SectionHead>{{ c.label }}<span class="text-ink-gray-6">· {{ range(c) }}</span></SectionHead>
          <Card flush>
            <Row :pane="null" class="!items-center"><span class="min-w-0 flex-1 text-sm text-ink-gray-6">Score</span><span class="text-sm font-semibold tabular-nums text-ink-gray-9">{{ scoreText(c) }}</span></Row>
            <Row v-for="g in goalsIn(c)" :key="g.name" :pane="null" class="!items-center">
              <RefLink class="min-w-0 flex-1 break-words text-base focus-visible:focus-ring" :class="g.grey ? 'text-ink-gray-7' : 'text-ink-blue-8'" :to="`goal:${g.name}`">{{ g.label }}</RefLink>
              <span class="text-sm text-ink-gray-6">{{ g.area }}</span>
            </Row>
            <Row v-for="k in keysIn(c)" :key="k.ref + k.date" class="!items-center" :pane="k.ref" :label="k.title">
              <span class="size-2 shrink-0 rounded-full bg-surface-red-7" aria-hidden="true" /><span class="min-w-0 flex-1 break-words text-base text-ink-gray-8">{{ k.title }}</span>
              <span class="text-sm tabular-nums text-ink-gray-6">{{ short(k.date) }}</span>
            </Row>
            <Row v-if="d.kind === 'cycle' && i === firstFuture && !goalsIn(c).length" :pane="null" class="!items-center">
              <RouterLink class="text-sm text-ink-blue-8 focus-visible:focus-ring" to="/goals/cycles">+ Plan next cycle</RouterLink>
            </Row>
          </Card>
        </section>
        <p class="text-sm text-ink-gray-6" data-reviews-phone>Weekly reviews: {{ d.reviews.done }} of {{ d.reviews.total }} since setup</p>
      </div>
    </template>
    <div v-else class="py-8 text-sm text-ink-gray-6">{{ failed ? 'The year could not be loaded.' : 'Loading…' }}</div>
  </div>
</template>
<script setup>
import RefLink from '@/components/ui/RefLink.vue'
// Today > Year (issues 16 and 100): the cycles around today. Four columns (the last cycle, this one, the next and the one after; quarters
// when no 12 Week Year is running), today as a red line, ‹ › one cycle at a time and Today to come back (`shift=` is in the URL). Rows: the
// score of each cycle; one row for each area that is on, each goal a bar across the cycle it belongs to and its deadline a small square;
// key dates as one dot a week with a count (a lone date names itself when there is room, a tap lists the week's); the weekly reviews
// since setup. A phone gets each cycle as a list.
import { computed, ref, watch } from 'vue'
import { onClickOutside, useElementSize } from '@vueuse/core'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Dashboard from './Dashboard.vue'
import PageHead from '@/components/PageHead.vue'
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import { todayData } from '@/data/today'
import { tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { onRecordChanged, openRef } from '@/lib/pane'
import { MONTHS, addDays, long, parse, short } from '@/lib/dates'

const route = useRoute()
const router = useRouter()
const shift = computed(() => Number(route.query.shift) || 0)
const d = ref(null)
const failed = ref(false)
const open = ref(null)
async function load() {
  const res = await tryCall(() => todayData.calendar.year_plan({ space: store.space, shift: shift.value || undefined, area: store.lensArea || undefined }))
  failed.value = !res
  if (res) d.value = res
}
watch(shift, () => { open.value = null; load() }, { immediate: true })
onRecordChanged(load)
const go = (n) => router.push({ path: route.path, query: { ...route.query, open: undefined, shift: n || undefined } })

// where a date falls across the four equal columns; a date between two cycles sits at the start of the later one
const DAY = 86400000
function pos(date) {
  const t = parse(date).getTime()
  const cols = d.value.columns
  for (let i = 0; i < cols.length; i++) {
    const s = parse(cols[i].start).getTime(), e = parse(cols[i].end).getTime() + DAY
    if (t < s) return i * 25
    if (t < e) return (i + (t - s) / (e - s)) * 25
  }
  return 100
}
const span = (a, b) => ({ left: pos(a) + '%', width: Math.max(pos(addDays(b, 1)) - pos(a), 1.5) + '%' })
const showToday = computed(() => d.value.today >= d.value.columns[0].start && d.value.today <= d.value.columns[d.value.columns.length - 1].end)
const fmt = (date) => { const p = parse(date); return `${p.getDate()} ${MONTHS[p.getMonth()].slice(0, 3)}` }
const range = (c) => `${fmt(c.start)} – ${fmt(c.end)} ${parse(c.end).getFullYear()}`
const scoreText = (c) => (c.when === 'future' ? 'plan' : c.when === 'current' && d.value.kind === 'cycle' ? `on track ${c.score === null ? '–' : c.score + '%'}` : c.score === null ? '–' : c.score + '%')
const sub = computed(() => (!d.value ? ' ' : d.value.kind === 'cycle' ? 'The cycles around today' : 'No 12 Week Year is running, so these are quarters.'))

const TONE = {
  blue: 'border-outline-blue-3 bg-surface-blue-2 text-ink-blue-9', green: 'border-outline-green-3 bg-surface-green-2 text-ink-green-8', amber: 'border-outline-amber-3 bg-surface-amber-2 text-ink-amber-9',
  red: 'border-outline-red-3 bg-surface-red-2 text-ink-red-8', violet: 'border-outline-violet-3 bg-surface-violet-2 text-ink-violet-8', teal: 'border-outline-teal-3 bg-surface-teal-2 text-ink-teal-8',
  orange: 'border-outline-orange-3 bg-surface-orange-2 text-ink-orange-8', pink: 'border-outline-pink-3 bg-surface-pink-2 text-ink-pink-8', cyan: 'border-outline-cyan-3 bg-surface-cyan-2 text-ink-cyan-8',
  gray: 'border-outline-gray-3 bg-surface-gray-2 text-ink-gray-8',
}
const DOT = { blue: 'bg-surface-blue-7', green: 'bg-surface-green-7', amber: 'bg-surface-amber-7', red: 'bg-surface-red-7', violet: 'bg-surface-violet-7', teal: 'bg-surface-teal-7',
  orange: 'bg-surface-orange-7', pink: 'bg-surface-pink-7', cyan: 'bg-surface-cyan-7', gray: 'bg-surface-gray-7' }
const tone = (c) => TONE[c] || TONE.gray

// goals that overlap in time go on separate tracks of their row, so no bar covers another
const touches = (g, c) => g.start <= c.end && g.end >= c.start
const firstFuture = computed(() => d.value.columns.findIndex((c) => c.when === 'future'))
function lane(l, first) {
  const ends = []
  const goals = [...l.goals].sort((a, b) => a.start.localeCompare(b.start)).map((g) => {
    let track = ends.findIndex((e) => e < g.start)
    if (track < 0) track = ends.length
    ends[track] = g.end
    return { ...g, track }
  })
  // the first future cycle with no goal of this area in it offers to be planned
  const planNext = d.value.kind === 'cycle' && firstFuture.value >= 0 && !goals.some((g) => touches(g, d.value.columns[firstFuture.value])) ? [firstFuture.value + 1] : []
  const empty = first && !d.value.goal_count
  return { key: 'area-' + l.area, kind: 'lane', label: l.name, sub: l.part_of ? `part of ${l.part_of}` : null, dot: l.part_of ? null : DOT[l.colour] || DOT.gray, colour: l.colour, goals, planNext: empty ? [] : planNext,
    empty, height: empty ? 3.25 : Math.max(ends.length, 1) * 2.25 + (planNext.length && !ends.length ? 1 : 0.75) }
}
const rows = computed(() => [
  { key: 'scores', kind: 'scores', label: d.value.kind === 'cycle' ? 'Score per cycle' : 'Score', height: 3 },
  ...(d.value.lanes.length ? d.value.lanes.map((l, i) => lane(l, i === 0)) : [{ key: 'area-none', kind: 'lane', label: 'Goals', goals: [], planNext: [], empty: true, height: 3.25 }]),
  { key: 'keys', kind: 'keys', label: 'Key dates', sub: 'by week', height: 3.25 },
  { key: 'reviews', kind: 'reviews', label: 'Weekly reviews', sub: `${d.value.reviews.done} of ${d.value.reviews.total} since setup`, height: 3 },
])

// key dates: a dot for each week at the middle of the week. The dot shrinks to fit when the screen is narrow, and a lone date's title
// is written beside its dot only where it fits between its neighbours, so no two labels overlap.
const keyTrack = ref(null)
const { width: trackW } = useElementSize(keyTrack)
const dot = computed(() => Math.max(8, Math.min(18, (trackW.value / (d.value.columns.length * 12)) - 2)))
const keyDots = computed(() => {
  const w = trackW.value
  const dots = d.value.key_weeks.map((k) => ({ ...k, x: (pos(addDays(k.start, 3)) / 100) * w, label: null }))
  let taken = -Infinity
  dots.forEach((k, i) => {
    if (k.count !== 1 || !w) return
    const left = k.x + dot.value / 2 + 4
    const limit = Math.min(i + 1 < dots.length ? dots[i + 1].x - dot.value / 2 - 4 : w, w - 2)
    const room = Math.min(Math.ceil(k.items[0].title.length * 6.3) + 4, 150, limit - left)
    if (left >= taken + 4 && room >= 60) {
      k.label = { left, width: room }
      taken = left + room
    }
  })
  return dots
})
const wrap = ref(null)
const pop = ref(null)
const popAt = ref({ top: 0, left: 0 })
const openWeek = computed(() => d.value?.key_weeks.find((k) => k.start === open.value))
function toggle(k, ev) {
  if (open.value === k.start) { open.value = null; return }
  const box = wrap.value.getBoundingClientRect(), at = ev.currentTarget.getBoundingClientRect()
  popAt.value = { top: at.bottom - box.top + 6, left: Math.max(0, Math.min(at.left - box.left + at.width / 2 - 144, box.width - 288)) }
  open.value = k.start
}
onClickOutside(pop, () => { open.value = null }, { ignore: ['[data-key-dot]'] })
function openItem(it) {
  open.value = null
  openRef(it.ref)
}

// phone: what falls in one cycle
const goalsIn = (c) => d.value.lanes.flatMap((l) => l.goals.filter((g) => touches(g, c)).map((g) => ({ ...g, area: l.name })))
const keysIn = (c) => d.value.key_weeks.flatMap((k) => k.items).filter((k) => k.date >= c.start && k.date <= c.end)
</script>
