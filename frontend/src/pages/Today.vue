<template>
  <template v-if="d">
    <PageHead :title="`${weekday(d.date, phone ? 3 : 0)}, ${long(d.date)}`">
      <template #sub><span data-today-sub>
        <template v-if="d.cycle && d.cycle.week">Week {{ d.cycle.week }} of {{ d.cycle.weeks }} · </template>
        <template v-else-if="d.cycle">{{ d.cycle.title }} {{ d.cycle.ended ? 'has ended' : 'has not started' }} · </template>
        {{ d.days_left }} day{{ d.days_left === 1 ? '' : 's' }} left<span class="max-md:hidden"> this week</span></span>
      </template>
    </PageHead>

    <div class="page-body !gap-5">
      <!-- the Open band: everything still open, each number a door; amber when the stuck count is over the limit -->
      <section data-open-band :data-over-limit="band.over_limit || undefined">
        <h2 class="mb-2 flex flex-wrap items-baseline gap-x-2 text-base" data-band-head>
          <span class="font-semibold text-ink-gray-9">Open</span>
          <span class="text-sm text-ink-gray-6 max-md:hidden">everything still open in {{ store.space }} · each number opens its list</span>
          <span v-if="band.over_limit" class="text-sm text-ink-amber-9" data-band-amber> · <CountLink :count="band.stuck" tone="text-ink-amber-9 font-medium" count-key="band:stuck-head" /> tasks stuck<span class="max-md:hidden">, above your limit of {{ band.rules.stuck_limit }}</span></span>
          <Button class="ml-auto md:hidden" size="sm" :variant="band.over_limit ? 'subtle' : 'ghost'" :class="band.over_limit && '!bg-surface-amber-2 !text-ink-amber-9'" label="Reset" route="/reset" data-band-reset-phone />
        </h2>
        <!-- desktop: one row of tiles and the Reset button; phone: the four most important as a grid, the rest scroll sideways -->
        <div class="overflow-hidden rounded-5 border border-outline-gray-2 max-md:hidden" data-band-row>
          <div class="grid grid-cols-[repeat(5,minmax(0,1fr))_minmax(0,1.1fr)_minmax(0,1.25fr)_auto]">
            <Tile v-for="t in tiles" :key="t.key" :tile="t" class="border-r border-outline-gray-1" />
            <div class="flex items-center px-4" :class="band.over_limit ? 'bg-surface-amber-1' : ''">
              <Button :variant="band.over_limit ? 'solid' : 'subtle'" label="Reset" route="/reset" data-band-reset />
            </div>
          </div>
        </div>
        <div class="md:hidden" data-band-phone>
          <div class="grid grid-cols-2 gap-2">
            <Tile v-for="t in phoneMain" :key="t.key" :tile="t" class="rounded-5 border border-outline-gray-2" />
          </div>
          <div class="-mx-4 mt-2 flex gap-2 overflow-x-auto px-4 pb-1" data-band-scroll>
            <Tile v-for="t in phoneRest" :key="t.key" :tile="t" class="w-40 flex-none rounded-5 border border-outline-gray-2" />
          </div>
        </div>
      </section>

      <div class="grid gap-6 md:grid-cols-[minmax(0,1fr)_18.5rem]">
        <!-- Next: one list in a fixed order, the order written at the top -->
        <section data-next>
          <h2 class="mb-2 flex flex-wrap items-baseline gap-x-2 text-base"><span class="font-semibold text-ink-gray-9">Next</span>
            <span class="text-sm text-ink-gray-6 max-md:hidden">in this order: overdue, today, this week's 12 Week Year actions, then decisions</span></h2>
          <Card flush class="!px-4">
            <template v-for="g in visibleGroups" :key="g.key">
              <div class="flex items-center gap-2 border-b border-outline-gray-1 pb-1.5 pt-3 text-xs font-semibold uppercase tracking-wide text-ink-gray-6" :data-next-group="g.key">
                <span>{{ g.label }} ·</span>
                <CountLink v-if="g.door" :count="g.door" tone="text-ink-gray-6" :aria-label="`${g.door.n} ${g.label.toLowerCase()}`" :count-key="'next:' + g.key" />
                <template v-else-if="g.key === 'today'"><span class="tabular-nums">{{ g.total }}</span></template>
                <span v-else class="tabular-nums">{{ g.total }}</span>
                <Button v-if="g.key === 'overdue' && g.total > 1 && canWrite()" class="ml-auto !normal-case !tracking-normal" variant="ghost" size="sm" label="Move all to today" data-move-all @click="moveAllOpen = true" />
                <span v-if="g.key === 'today' && g.tasks.n" class="ml-auto font-normal normal-case tracking-normal max-md:hidden"><CountLink :count="g.tasks" :aria-label="`${g.tasks.n} tasks due today`" count-key="next:today-tasks">{{ g.tasks.n }} task{{ g.tasks.n === 1 ? '' : 's' }} due</CountLink></span>
              </div>
              <template v-for="r in g.shown" :key="r.type + r.name">
                <!-- an overdue or due task -->
                <Row v-if="!r.type || r.type === 'task'" :pane="'task:' + r.name" :label="r.title" class="group !items-center" data-next-row :data-why="r.why" data-task-row>
                  <Checkbox class="relative" :model-value="r.status === 'Done'" :disabled="!canWrite()" :aria-label="'Done: ' + r.title" @update:model-value="done(r)" />
                  <span v-if="!phone" class="w-14 shrink-0 text-sm tabular-nums text-ink-gray-7">{{ r.lead || '' }}</span>
                  <div class="min-w-0 flex-1">
                    <div class="break-words text-base text-ink-gray-9" :class="r._done && 'text-ink-gray-6 line-through'">{{ r.title }}</div>
                    <div class="truncate text-sm text-ink-gray-6">{{ taskLine(r) }}</div>
                  </div>
                  <Dropdown v-if="r.why === 'Overdue' && canWrite()" :options="triage(r)"><Button class="relative md:opacity-0 md:focus-visible:opacity-100 md:group-hover:opacity-100" variant="ghost" size="sm"
                    icon="lucide-calendar-clock" :label="'Reschedule ' + r.title" data-triage /></Dropdown>
                  <Badge :theme="r.why === 'Overdue' ? 'red' : 'gray'" :label="phone && r.why === 'Due today' ? 'Today' : r.why" data-why />
                </Row>
                <Row v-else-if="r.type === 'event'" :pane="'event:' + r.name" :label="r.title" class="!items-center" data-next-row data-why="Event">
                  <span class="w-5 shrink-0 md:hidden" />
                  <span v-if="!phone" class="w-[4.75rem] shrink-0 text-right text-sm tabular-nums text-ink-gray-7">{{ r.lead }}</span>
                  <div class="min-w-0 flex-1">
                    <div class="break-words text-base text-ink-gray-9">{{ r.title }}</div>
                    <div class="text-sm text-ink-gray-6">{{ phone ? r.lead + (duration(r) ? ' · ' + duration(r) : '') : 'Calendar' + (duration(r) ? ' · ' + duration(r) : '') }}</div>
                  </div>
                  <Badge label="Event" data-why />
                </Row>
                <Row v-else-if="r.type === 'action'" class="!items-center" data-next-row data-why="12WY" :data-action="r.name">
                  <Checkbox :model-value="r.count >= r.per_week" :disabled="!canWrite()" :aria-label="`Tick ${r.title}, ${r.count} of ${r.per_week} this week`" data-week-tick @update:model-value="tick(r)" />
                  <span v-if="!phone" class="w-14 shrink-0" />
                  <div class="min-w-0 flex-1">
                    <div class="break-words text-base text-ink-gray-9" :class="r.count >= r.per_week && 'text-ink-gray-6 line-through'">{{ r.title }}</div>
                    <div class="truncate text-sm text-ink-gray-6">{{ r.goal_title }} · {{ r.count }} of {{ r.per_week }} this week</div>
                  </div>
                  <Badge theme="blue" label="12WY" data-why />
                </Row>
                <Row v-else-if="r.type === 'insight'" :pane="r.evidence[0]?.ref || null" :label="r.title" class="flex-wrap !items-center" data-next-row :data-why="r.why" :data-insight="r.name">
                  <span v-if="!phone" class="w-[4.75rem] shrink-0" />
                  <div class="min-w-0 flex-[1_1_16rem]">
                    <div class="break-words text-base text-ink-gray-9">{{ r.title }}</div>
                    <div class="text-sm text-ink-gray-6">Insight · {{ r.based_on.replace(/^Based on /, 'based on ') }}</div>
                  </div>
                  <Badge :theme="KIND_THEME[r.kind] || 'gray'" :label="phone && r.kind === 'Waiting on you' ? 'Waiting' : r.kind" data-why />
                  <div v-if="canWrite() && !phone" class="relative flex items-center gap-1">
                    <Button v-for="(a, i) in r.actions.slice(0, 2)" :key="i" :variant="i === 0 ? 'subtle' : 'ghost'" :label="a.label" :data-insight-action="a.kind" @click="runAction(r, i)" />
                    <Button variant="ghost" label="Dismiss" data-insight-dismiss @click="dismiss(r)" />
                  </div>
                </Row>
              </template>
            </template>
            <div v-if="hidden > 0" class="py-2.5"><Button variant="ghost" class="!px-0 !text-ink-blue-8" :label="`${hidden} more`" data-next-more @click="showAll = true" /></div>
            <Empty v-if="!visibleGroups.length" title="Nothing is next." hint="No overdue tasks, nothing today, every action of the week ticked and no decision waiting." />
          </Card>
        </section>

        <!-- the right rail; on a phone it moves below Next -->
        <aside class="flex flex-col gap-5" data-rail>
          <section data-rail-today>
            <h2 class="mb-2 text-base font-semibold text-ink-gray-9">Today</h2>
            <ol class="flex flex-col" aria-label="Today's events">
              <li v-for="e in railItems" :key="e.key" class="flex items-stretch gap-2.5" :data-rail-event="e.kind">
                <span class="w-12 shrink-0 pt-1.5 text-right text-sm tabular-nums" :class="e.kind === 'now' ? 'text-ink-red-8' : 'text-ink-gray-6'">{{ e.time }}</span>
                <div class="relative min-w-0 flex-1 border-l border-outline-gray-2 py-1 pl-2.5">
                  <span v-if="e.kind === 'now'" class="absolute -left-[5px] top-3 size-2 rounded-full bg-surface-red-7" aria-hidden="true" />
                  <Button v-if="e.kind === 'event'" class="!h-auto min-h-8 w-full !justify-start !whitespace-normal !bg-surface-blue-1 py-1.5 text-left !text-ink-blue-8" :label="e.title" @click="openRef('event:' + e.name)" />
                  <span v-else class="block pt-0.5 text-sm text-ink-gray-6">{{ e.title }}</span>
                </div>
              </li>
            </ol>
            <div v-if="!d.rail.events.length" class="mt-1 text-sm text-ink-gray-6">Nothing on the calendar today.</div>
          </section>
          <section data-rail-week>
            <h2 class="mb-2 text-base font-semibold text-ink-gray-9">This week</h2>
            <Card flush class="!px-4">
              <Row v-for="w in d.rail.week" :key="w.kind + (w.name || w.title)" :pane="weekRef(w)" :label="w.title" class="!items-center">
                <span class="min-w-0 flex-1 break-words text-base text-ink-gray-8">{{ w.title }}</span>
                <Badge v-if="w.kind === 'vault'" theme="amber" :label="`${w.days} days`" />
                <span v-else class="text-sm tabular-nums text-ink-gray-6">{{ w.kind === 'review' ? `${w.day} ${w.time}` : short(w.date) }}</span>
              </Row>
            </Card>
          </section>
          <section v-if="d.rail.insights_total" data-rail-insights>
            <h2 class="mb-1 flex items-baseline gap-2 text-base"><span class="font-semibold text-ink-gray-9">Insights</span>
              <span class="text-sm text-ink-gray-6">{{ d.rail.insights_total }} more · <RouterLink class="text-ink-blue-8 hover:underline" :to="{ path: '/ask', query: { tab: 'insights' } }">see all</RouterLink></span></h2>
            <p class="text-sm text-ink-gray-6">{{ d.rail.insights.map((i) => i.title).join(' · ') }}</p>
          </section>
        </aside>
      </div>
    </div>
    <Dialog v-model:open="moveAllOpen" title="Move all overdue tasks to today?" size="sm"
      :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: `Move ${overdueGroup?.total || 0} to today`, variant: 'solid', onClick: moveAll }]">
      <p class="text-base text-ink-gray-8">Each overdue task gets today's date. Tasks you would rather drop or move further can be done one at a time.</p>
    </Dialog>
  </template>
  <div v-else class="page-body"><Skeleton class="h-24 w-full" /><Skeleton class="h-72 w-full" /></div>
</template>

<script setup>
// Today (UX fixes, set 5): three questions. What is open (the Open band, each number a door), what is next (one list in
// a fixed order: overdue, today, this week's 12 Week Year actions, decisions), and what is around it (today's events,
// this week's dates, the other insights). Someday items never appear.
import { computed, h, onMounted, onUnmounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { RouterLink, useRouter } from 'vue-router'
import { Badge, Button, Checkbox, Dialog, Dropdown, Skeleton, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import CountLink from '@/components/ui/CountLink.vue'
import Row from '@/components/ui/Row.vue'
import { api, errorText, optimistic, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { addDays, long, short, startOfWeek, weekday } from '@/lib/dates'
import { onRecordChanged, openRef, paneNav } from '@/lib/pane'
import { askScope } from '@/lib/ask'

const router = useRouter()
const phone = useMediaQuery('(max-width: 767px)')
const d = ref(null)
const showAll = ref(false)
const moveAllOpen = ref(false)
const KIND_THEME = { Stuck: 'red', 'Waiting on you': 'amber', Promise: 'amber', Someday: 'violet' }
askScope({ kind: 'space', label: 'Everything in this space' })

const band = computed(() => d.value.band)
// a tile: label, the big number (a door), the line under it (a door too, amber when it is a warning)
const tiles = computed(() => {
  const b = band.value
  const c = d.value.cycle
  const goalLine = b.goals_no_ticks.n ? { count: b.goals_no_ticks, text: 'with no ticks for 3 weeks' } : { count: b.goals_no_tasks, text: 'with no tasks' }
  return [
    { key: 'open', label: 'Open tasks', count: b.open_tasks, sub: { count: b.stuck, text: `untouched ${b.rules.stuck_after_days}+ days`, warn: b.stuck.n > 0 } },
    { key: 'projects', label: 'Projects', count: b.projects, pre: 'active · ', sub: { count: b.idle_projects, text: `idle ${b.rules.stuck_after_days}+ days` } },
    { key: 'goals', label: 'Goals', count: b.goals, pre: 'in progress · ', sub: goalLine },
    { key: 'inbox', label: 'Inbox', count: b.inbox, pre: 'to review · ', sub: { count: b.inbox_old, text: 'older than a week', warn: b.inbox_old.n > 0 } },
    { key: 'notes', label: 'Notes and sources', count: b.notes_sources, sub: { count: b.notes_unopened, text: 'notes not opened in 90 days' } },
    { key: 'week', label: c && c.week ? `Week ${c.week} of 12` : 'Week score', week: true },
    { key: 'habits', label: `Habits today · ${d.value.habits.filter((x) => x.done).length} of ${d.value.habits.length}`, habits: true },
  ]
})
const phoneMain = computed(() => tiles.value.filter((t) => ['open', 'inbox', 'week', 'habits'].includes(t.key)))
const phoneRest = computed(() => tiles.value.filter((t) => !['open', 'inbox', 'week', 'habits'].includes(t.key)))

const Tile = (props) => {
  const t = props.tile
  const box = 'flex min-w-0 flex-col gap-0.5 px-4 py-3'
  if (t.week) {
    const c = d.value.cycle
    const pct = c && c.week ? Math.round(c.score) : null
    return h('div', { class: box, 'data-tile': t.key }, [
      h('div', { class: 'truncate text-sm text-ink-gray-7' }, t.label),
      h('div', { class: 'flex items-baseline gap-2' }, [
        h(RouterLinkNum, { to: { path: '/journal' }, text: pct === null ? '—' : pct + '%', aria: `Week score ${pct}%` }),
        h('span', { class: 'text-sm text-ink-gray-6' }, phone.value ? `/ ${d.value.target}%` : `target ${d.value.target}%`)]),
      pct === null ? null : h('div', { class: 'relative mt-1.5 h-1.5 rounded-full bg-surface-gray-3', role: 'img', 'aria-label': `${pct}% of the ${d.value.target}% target`, 'data-score-bar': '' }, [
        h('div', { class: 'h-full rounded-full ' + (pct >= d.value.target ? 'bg-surface-green-7' : 'bg-surface-gray-9'), style: { width: Math.min(pct, 100) + '%' } }),
        h('div', { class: 'absolute -top-1 h-3.5 w-0.5 rounded-full bg-surface-blue-7', style: { left: `calc(${d.value.target}% - 1px)` }, 'aria-hidden': 'true' })]),
    ])
  }
  if (t.habits) {
    return h('div', { class: box, 'data-tile': t.key, 'data-today-habits': '' }, [
      h('div', { class: 'truncate text-sm text-ink-gray-7', 'data-habit-count': '' }, t.label),
      h('div', { class: 'mt-1 flex flex-wrap gap-1' }, d.value.habits.map((x) => h(Button, {
        class: '!size-6 !p-0 text-xs', variant: x.done ? 'solid' : 'outline', disabled: !canWrite(), 'aria-pressed': x.done, 'aria-label': `${x.title}, ${x.done ? 'done' : 'not done'} today`,
        tooltip: x.title, 'data-habit': x.habit, onClick: () => toggleHabit(x) }, () => x.title.charAt(0).toUpperCase()))),
    ])
  }
  return h('div', { class: box, 'data-tile': t.key }, [
    h('div', { class: 'truncate text-sm text-ink-gray-7' }, t.label),
    h(CountLink, { count: t.count, tone: 'text-2xl-semibold text-ink-gray-9', countKey: 'band:' + t.key }),
    h('div', { class: 'text-sm ' + (t.sub.warn ? 'text-ink-amber-9' : 'text-ink-gray-6') }, [
      phone.value ? null : t.pre || null,
      h(CountLink, { count: t.sub.count, tone: t.sub.warn ? 'text-ink-amber-9' : 'text-ink-gray-6', countKey: 'band:' + t.key + ':sub', ariaLabel: `${t.sub.count.n} ${t.sub.text}` }),
      ' ' + (phone.value && t.key === 'open' ? 'stuck' : t.sub.text)]),
  ])
}
Tile.props = ['tile']
const RouterLinkNum = (p) => h(RouterLink, { to: p.to, class: 'rounded-1 text-2xl-semibold tabular-nums text-ink-gray-9 hover:underline focus-visible:focus-ring', 'aria-label': p.aria, 'data-week-score': '' }, () => p.text)
RouterLinkNum.props = ['to', 'text', 'aria']

// Next: about 8 rows across the groups in order, then "N more"
const groups = computed(() => d.value.next.groups.filter((g) => g.rows.length))
const overdueGroup = computed(() => d.value.next.groups.find((g) => g.key === 'overdue'))
const visibleGroups = computed(() => {
  let room = showAll.value ? Infinity : d.value.next.show
  return groups.value.map((g) => {
    const shown = g.rows.slice(0, Math.max(room, 0))
    room -= shown.length
    return { ...g, shown }
  }).filter((g) => g.shown.length)
})
const hidden = computed(() => groups.value.reduce((n, g) => n + g.rows.length, 0) - visibleGroups.value.reduce((n, g) => n + g.shown.length, 0))
const taskLine = (r) => [r.area_name, r.project_title, r.source_title && 'from ' + r.source_title, r.status === 'Waiting' && r.waiting_on && 'waiting on ' + r.waiting_on].filter(Boolean).join(' · ') || 'Unfiled'
function duration(e) {
  if (e.all_day || !e.start || !e.end) return ''
  const m = Math.round((new Date(e.end.replace(' ', 'T')) - new Date(e.start.replace(' ', 'T'))) / 60000)
  return m <= 0 ? '' : m < 60 ? `${m} min` : `${Math.round(m / 6) / 10} h`
}

// the rail's timeline: events at their times, with a now marker between them
const nowTime = ref(new Date().toTimeString().slice(0, 5))
const railItems = computed(() => {
  const ev = d.value.rail.events.map((e) => ({ key: 'e' + e.name + e.start, kind: 'event', name: e.name, title: e.title, time: e.all_day ? 'All day' : String(e.start || '').slice(11, 16) }))
  const out = []
  let placed = false
  for (const e of ev) {
    if (!placed && e.time !== 'All day' && e.time > nowTime.value) { out.push({ key: 'now', kind: 'now', title: 'Now', time: nowTime.value }); placed = true }
    out.push(e)
  }
  if (!placed) out.push({ key: 'now', kind: 'now', title: 'Now', time: nowTime.value })
  return out
})
const weekRef = (w) => (w.kind === 'vault' ? 'vault:' + w.name : w.kind === 'important' ? 'date:' + w.name : null)

async function load() {
  const res = await tryCall(() => api('today.get', { space: store.space }))
  if (!res) return
  d.value = res
  paneNav.rows = res.next.groups.flatMap((g) => g.rows.map((r) => (r.type === 'event' ? 'event:' + r.name : !r.type || r.type === 'task' ? 'task:' + r.name : null)).filter(Boolean))
}
onRecordChanged(() => load())
async function done(t) {
  await optimistic(() => { t.status = 'Done'; t._done = true }, () => { t.status = 'Open'; t._done = false },
    () => api('tasks.set_status', { task: t.name, status: 'Done' })).catch(() => {})
  setTimeout(load, 700)
}
function triage(t) {
  const leave = (request, message) => async () => { if (await tryCall(request, message)) load() }
  const move = (label, date) => ({ label, onClick: leave(() => api('tasks.update', { task: t.name, values: { due_date: date } }), `Moved to ${long(date)}`) })
  return [move('Today', d.value.date), move('Tomorrow', addDays(d.value.date, 1)), move('Next week', addDays(startOfWeek(d.value.date), 7)),
    { label: 'Drop', onClick: leave(() => api('tasks.set_status', { task: t.name, status: 'Dropped' }), 'Dropped') }]
}
async function moveAll({ close }) {
  const out = await tryCall(() => api('tasks.reschedule_overdue', { space: store.space, to_date: d.value.date }))
  close()
  if (out) { toast.success(`${out.moved} task${out.moved === 1 ? '' : 's'} moved to today`); load() }
}
// ticking a 12 Week Year action records the week's tick; the week score follows
async function tick(a) {
  const c = d.value.cycle
  const before = a.count
  const next = before >= a.per_week ? 0 : before + 1
  try {
    await optimistic(() => (a.count = next), () => (a.count = before), async () => {
      const score = await api('journal.tick', { action: a.name, week: c.week, count: next })
      Object.assign(c, { done: score.done, planned: score.planned, score: score.percent })
    })
  } catch { /* told by optimistic */ }
}
function toggleHabit(x) {
  optimistic(() => (x.done = !x.done), () => (x.done = !x.done),
    () => api('journal.toggle_habit', { habit: x.habit, date: d.value.date, done: x.done ? 1 : 0 })).catch(() => {})
}
// an insight's buttons: nothing changes until clicked; a click calls the normal API and offers Undo where it can
async function runAction(r, i) {
  const a = r.actions[i]
  if (a.kind === 'open_reset') return router.push({ path: '/reset' })
  if (a.kind === 'open_list') return router.push(a.to)
  if (a.kind === 'open_record') return openRef(a.ref)
  try {
    const out = await api('insights.act', { insight: r.name, index: i })
    if (out.undo) toast.success(`${a.label}: done.`, { duration: 60000, action: { label: 'Undo', onClick: async () => { await api('reset.undo', { log: JSON.stringify(out.undo) }); await api('insights.restore', { insight: r.name }); load() } } })
    else toast.success(a.kind === 'make_task' ? 'Task made.' : 'Done.')
    load()
  } catch (e) { toast.error(errorText(e)) }
}
async function dismiss(r) {
  try {
    await api('insights.dismiss', { insight: r.name })
    toast.success('Dismissed. It will not come back unless something changes.', { duration: 60000, action: { label: 'Undo', onClick: async () => { await api('insights.restore', { insight: r.name }); load() } } })
    load()
  } catch (e) { toast.error(errorText(e)) }
}
let clock = null
onMounted(() => { load(); clock = setInterval(() => (nowTime.value = new Date().toTimeString().slice(0, 5)), 60000) })
onUnmounted(() => { paneNav.rows = []; clearInterval(clock) })
</script>
