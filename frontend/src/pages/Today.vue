<template>
  <template v-if="d">
    <PageHead :title="`${weekday(d.date, phone ? 3 : 0)}, ${long(d.date)}`">
      <template #sub><span data-today-sub>
        <template v-if="d.cycle && d.cycle.week">Week {{ d.cycle.week }} of {{ d.cycle.weeks }} · </template>
        <template v-else-if="d.cycle">{{ d.cycle.title }} {{ d.cycle.ended ? 'has ended' : 'has not started' }} · </template>
        {{ d.days_left }} day{{ d.days_left === 1 ? '' : 's' }} left<span class="max-md:hidden"> this week</span><span class="max-md:hidden" data-day-summary> · {{ plateCount }} thing{{ plateCount === 1 ? '' : 's' }} today, {{ meetingCount }} meeting{{ meetingCount === 1 ? '' : 's' }}</span></span>
      </template>
    </PageHead>

    <div class="page-body !gap-5">
      <!-- a rhythm that is due (UX fixes, set 6): at most one line, above the list, with Skip until its next occurrence -->
      <div v-if="d.banner" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-4 py-2.5" role="status"
        data-rhythm-banner :data-banner="d.banner.key">
        <span class="lucide-bell size-4 text-ink-gray-7" aria-hidden="true" />
        <RouterLink class="min-w-0 flex-1 text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="d.banner.to" data-banner-open>{{ d.banner.text }}</RouterLink>
        <Button size="sm" variant="solid" :label="d.banner.action" :route="d.banner.to" />
        <Button size="sm" variant="ghost" label="Skip" data-banner-skip @click="skipBanner" />
      </div>
      <!-- issue 102: the AI service is not answering (credit, the key or the provider), until a call works again -->
      <!-- issue 118: the waiting pile is never on Today; one line says when some of it is past its check-by date -->
      <div v-if="d.waiting_past?.count" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-4 py-2.5" role="status" data-waiting-past>
        <span class="min-w-0 flex-1 text-base text-ink-gray-9">{{ d.waiting_past.count }} waiting {{ d.waiting_past.count === 1 ? 'item is' : 'items are' }} past their check date · {{ d.waiting_past.names.join(', ') }}</span>
        <Button size="sm" label="Look now" :route="{ path: '/today/week', query: { view: 'review', tab: 'tasks' } }" data-waiting-look />
      </div>
      <div v-if="d.brain_off" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-5 border border-outline-amber-1 bg-surface-amber-1 px-4 py-2.5" role="status" data-brain-off>
        <span class="lucide-triangle-alert size-4 text-ink-amber-8" aria-hidden="true" />
        <span class="min-w-0 flex-1 text-base text-ink-gray-9">The Brain is off: {{ d.brain_off }}</span>
        <Button size="sm" label="Settings › AI" :route="{ path: '/settings', query: { tab: 'advanced' } }" data-brain-off-open />
      </div>
      <!-- set 7: what the rule for Inbox items left too long parked or discarded on its own, with Undo for seven days -->
      <div v-if="d.auto_inbox" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-4 py-2.5" role="status" data-auto-inbox>
        <span class="lucide-inbox size-4 text-ink-gray-7" aria-hidden="true" />
        <span class="min-w-0 flex-1 text-base text-ink-gray-9">{{ autoText }}</span>
        <Button size="sm" label="Undo" data-auto-inbox-undo @click="undoAuto" />
      </div>
      <!-- Needs you (issue 15): one line to Brain when something waits for a decision -->
      <RouterLink v-if="d.to_review.count > 0" to="/brain" class="flex items-center gap-3 rounded-5 border border-outline-violet-1 bg-surface-violet-1 px-4 py-3 hover:bg-surface-violet-2 focus-visible:focus-ring"
        data-needs-you :data-count="d.to_review.count">
        <span class="lucide-sparkles size-4 shrink-0 text-ink-violet-8" aria-hidden="true" />
        <span class="min-w-0 flex-1 text-base text-ink-gray-9"><span class="font-semibold" data-needs-you-count>{{ d.to_review.count }} need{{ d.to_review.count === 1 ? 's' : '' }} you</span>
          <span class="text-ink-gray-7 max-md:hidden"> · the Brain has {{ d.to_review.count === 1 ? 'a capture' : 'captures' }} waiting for your call</span></span>
        <span class="text-sm-medium text-ink-gray-8 max-md:hidden">Open Brain</span>
        <span class="lucide-chevron-right size-4 text-ink-gray-6" aria-hidden="true" />
      </RouterLink>

      <div class="grid grid-cols-1 gap-6 md:grid-cols-[minmax(0,1fr)_18.5rem]">
        <!-- Next: one list in a fixed order, the order written at the top -->
        <section class="md:col-start-1" data-next>
          <h2 class="mb-2 text-base font-semibold text-ink-gray-9">Today</h2>
          <Card flush class="!px-4">
            <template v-for="g in visibleGroups" :key="g.key">
              <div class="flex items-center gap-2 border-b border-outline-gray-1 pb-1.5 pt-3 text-xs font-semibold uppercase tracking-wide text-ink-gray-6" :data-next-group="g.key">
                <span>{{ g.label }} ·</span>
                <CountLink v-if="g.door" :count="g.door" tone="text-ink-gray-6" :aria-label="`${g.door.n} ${g.label.toLowerCase()}`" :count-key="'next:' + g.key" />
                <template v-else-if="g.key === 'today'"><span class="tabular-nums">{{ g.total }}</span></template>
                <span v-else class="tabular-nums">{{ g.total }}</span>
                <Button v-if="g.key === 'overdue' && g.total > 1 && canWrite() && overdueOpen" class="ml-auto !normal-case !tracking-normal" variant="ghost" size="sm" label="Move all to today" data-move-all @click="moveAllOpen = true" />
                <Button v-if="g.key === 'overdue'" :class="g.total > 1 && canWrite() && overdueOpen ? '' : 'ml-auto'" class="!normal-case !tracking-normal" variant="ghost" size="sm" :label="overdueOpen ? 'Fold' : 'Show'"
                  :aria-expanded="overdueOpen" data-overdue-toggle @click="overdueOpen = !overdueOpen" />
                <span v-if="g.key === 'today' && g.tasks.n" class="ml-auto font-normal normal-case tracking-normal max-md:hidden"><CountLink :count="g.tasks" :aria-label="`${g.tasks.n} tasks due today`" count-key="next:today-tasks">{{ g.tasks.n }} task{{ g.tasks.n === 1 ? '' : 's' }} due</CountLink></span>
              </div>
              <template v-for="r in g.shown" :key="r.type + r.name">
                <!-- an overdue or due task -->
                <Row v-if="!r.type || r.type === 'task'" :pane="'task:' + r.name" :label="r.title" class="group !items-center" data-next-row :data-why="r.why" data-task-row>
                  <Checkbox class="relative" :model-value="r.status === 'Done'" :disabled="!canWrite()" :aria-label="'Done: ' + r.title" @update:model-value="done(r)" />
                  <span v-if="!phone" class="w-14 shrink-0 text-sm tabular-nums text-ink-gray-7">{{ r.lead || '' }}</span>
                  <span v-if="r.why === 'Top three'" class="lucide-star size-4 shrink-0 text-ink-amber-9" role="img" aria-label="One of this week's top three" data-top-three />
                  <div class="min-w-0 flex-1">
                    <div class="break-words text-base text-ink-gray-9" :class="r._done && 'text-ink-gray-6 line-through'">{{ r.title }}</div>
                    <div class="flex min-w-0 items-center gap-1.5 text-sm text-ink-gray-6"><AreaGuess :task="r" :readonly="!canWrite()" /><span class="truncate">{{ taskLine(r) }}</span>
                      <RouterLink v-if="r.goal && r.goal_title" class="relative shrink-0 truncate text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="`/goals/${r.goal}`" data-task-goal-link>{{ r.goal_title }}</RouterLink></div>
                  </div>
                  <Dropdown v-if="r.why === 'Overdue' && canWrite()" :options="triage(r)"><Button class="relative md:opacity-0 md:focus-visible:opacity-100 md:group-hover:opacity-100" variant="ghost" size="sm"
                    icon="lucide-calendar-clock" :label="'Reschedule ' + r.title" data-triage /></Dropdown>
                  <Badge :theme="r.why === 'Overdue' ? 'red' : r.why === 'Top three' ? 'amber' : 'gray'" :label="phone && r.why === 'Due today' ? 'Today' : r.why" data-why />
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
              </template>
            </template>
            <p v-if="d.no_plan" class="py-2.5 text-sm text-ink-gray-6" data-no-plan :data-count="d.no_plan">{{ d.no_plan }} cycle goal{{ d.no_plan === 1 ? ' has' : 's have' }} nothing planned this week ·
              <RouterLink class="text-ink-blue-8 hover:underline focus-visible:focus-ring" to="/goals/cycles" data-no-plan-link>Plan</RouterLink></p>
            <div v-if="hidden > 0" class="py-2.5"><Button variant="ghost" class="!px-0 !text-ink-blue-8" :label="`${hidden} more`" data-next-more @click="showAll = true" /></div>
            <Empty v-if="!groups.length && onboarding.empty" title="Nothing here yet." data-today-empty>
              <p class="mt-1">Capture something with + Capture, or connect a source. Your tasks for the day will show up here.</p>
              <Button v-if="canWrite()" class="mt-3" variant="solid" icon-left="lucide-plus" label="Capture" data-today-capture @click="store.captureOpen = true" />
            </Empty>
            <Empty v-else-if="!groups.length" title="Nothing is next." hint="No overdue tasks, nothing due today and nothing planned for this week." />
          </Card>
        </section>
        <!-- the day's habits: one compact row of ticks with their names (issue 55) -->
        <section v-if="d.habits.length" class="md:col-start-1" data-today-habits>
          <h2 class="mb-2 flex items-baseline gap-2 text-base"><span class="font-semibold text-ink-gray-9">Habits</span>
            <span class="text-sm text-ink-gray-6" data-habit-count>{{ d.habits.filter((x) => x.done).length }} of {{ d.habits.length }} today</span></h2>
          <div class="flex flex-wrap gap-2">
            <Button v-for="x in d.habits" :key="x.habit" size="sm" :variant="x.done ? 'solid' : 'outline'" :disabled="!canWrite()" :label="x.title" :aria-pressed="x.done"
              :aria-label="`${x.title}, ${x.done ? 'done' : 'not done'} today`" :data-habit="x.habit" @click="toggleHabit(x)" />
          </div>
        </section>

        <!-- the right rail; on a phone it moves below Next -->
        <aside class="flex flex-col gap-5 md:col-start-2 md:row-span-2 md:row-start-1" data-rail>
          <section data-rail-today>
            <h2 class="mb-2 text-base font-semibold text-ink-gray-9">Meetings and time blocks</h2>
            <ol class="flex flex-col" aria-label="Today's events">
              <li v-for="e in railItems" :key="e.key" class="flex items-stretch gap-2.5" :data-rail-event="e.kind">
                <span class="w-12 shrink-0 pt-1.5 text-right text-sm tabular-nums" :class="e.kind === 'now' ? 'text-ink-red-8' : 'text-ink-gray-6'">{{ e.time }}</span>
                <div class="relative min-w-0 flex-1 border-l border-outline-gray-2 py-1 pl-2.5">
                  <span v-if="e.kind === 'now'" class="absolute -left-[5px] top-3 size-2 rounded-full bg-surface-red-7" aria-hidden="true" />
                  <Button v-if="e.kind === 'event'" class="!h-auto min-h-8 w-full !justify-start !whitespace-normal !bg-surface-blue-1 py-1.5 text-left !text-ink-blue-8" :label="e.title" @click="openRef('event:' + e.name)" />
                  <Button v-else-if="e.kind === 'task'" class="!h-auto min-h-8 w-full !justify-start !whitespace-normal !bg-surface-gray-2 py-1.5 text-left !text-ink-gray-9" icon-left="lucide-circle-check"
                    :label="e.title" data-rail-task @click="openRef('task:' + e.name)" />
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
              <span class="text-sm text-ink-gray-6">{{ d.rail.insights_total }} · <RouterLink class="text-ink-blue-8 hover:underline" :to="{ path: '/chat', query: { tab: 'insights' } }">see all</RouterLink></span></h2>
            <ul class="flex flex-col gap-1 text-sm text-ink-gray-6">
              <li v-for="i in d.rail.insights" :key="i.name" data-rail-insight>{{ i.title }}</li>
            </ul>
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
// Today (issue 55): tasks only. The Needs you line, the list (the top three, today, overdue folded, tasks planned this week under a
// goal of the cycle; never a goal or a lead action), the habits row, then the rail (events, this week, insights). A goal with nothing
// planned is one quiet line. The old Open band lives where each number counts. Someday items never appear.
import { todayData } from '@/data/today'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Badge, Button, Checkbox, Dialog, Dropdown, Skeleton, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import CountLink from '@/components/ui/CountLink.vue'
import Row from '@/components/ui/Row.vue'
import AreaGuess from '@/components/AreaGuess.vue'
import { optimistic, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { onboarding } from '@/lib/onboarding'
import { addDays, long, short, startOfWeek, weekday } from '@/lib/dates'
import { onRecordChanged, openRef, paneNav } from '@/lib/pane'
import { askScope, lensScope } from '@/lib/ask'

const router = useRouter()
const route = useRoute() // at=: a test site moves the banners' clock (site config lifeos_test_clock)
const phone = useMediaQuery('(max-width: 767px)')
const d = ref(null)
const showAll = ref(false)
const moveAllOpen = ref(false)
askScope(lensScope) // the lens's area, or everything in the space (set 6)

// Next: about 8 rows across the groups in order, then "N more"
// today's plate reads top three, today, overdue (folded until asked for), then the week's tasks under goals
const PLATE_ORDER = ['top', 'today', 'overdue', 'week']
const overdueOpen = ref(false)
// events are in the calendar beside the plate, not twice
const groups = computed(() => d.value.next.groups.map((g) => (g.key === 'today' ? { ...g, rows: g.rows.filter((r) => r.type !== 'event') } : g))
  .map((g) => (g.key === 'today' ? { ...g, total: g.rows.length } : g)).filter((g) => g.rows.length).sort((a, b) => PLATE_ORDER.indexOf(a.key) - PLATE_ORDER.indexOf(b.key)))
const overdueGroup = computed(() => d.value.next.groups.find((g) => g.key === 'overdue'))
const visibleGroups = computed(() => {
  let room = showAll.value ? Infinity : d.value.next.show
  return groups.value.map((g) => {
    if (g.key === 'overdue' && !overdueOpen.value) return { ...g, shown: [] }
    const shown = g.rows.slice(0, Math.max(room, 0))
    room -= shown.length
    return { ...g, shown }
  }).filter((g) => g.shown.length || g.key === 'overdue')
})
const plateCount = computed(() => (d.value.next.groups.find((g) => g.key === 'today')?.tasks?.n || 0) + d.value.next.groups.find((g) => g.key === 'top')?.rows.length)
const meetingCount = computed(() => d.value.rail.events.filter((e) => e.source !== 'task').length)
const hidden = computed(() => groups.value.filter((g) => g.key !== 'overdue' || overdueOpen.value).reduce((n, g) => n + g.rows.length, 0) - visibleGroups.value.reduce((n, g) => n + g.shown.length, 0))
// a guessed area shows as its own chip before the line (issue 13)
const taskLine = (r) => [!r.area_guessed && r.area_name, r.goal ? '' : r.goal_title, r.source_title && 'from ' + r.source_title, r.status === 'Waiting' && r.waiting_on && 'waiting on ' + r.waiting_on].filter(Boolean).join(' · ') || (r.area_guessed ? '' : 'Unfiled')
function duration(e) {
  if (e.all_day || !e.start || !e.end) return ''
  const m = Math.round((new Date(e.end.replace(' ', 'T')) - new Date(e.start.replace(' ', 'T'))) / 60000)
  return m <= 0 ? '' : m < 60 ? `${m} min` : `${Math.round(m / 6) / 10} h`
}

// the rail's timeline: events at their times, with a now marker between them
const nowTime = ref(new Date().toTimeString().slice(0, 5))
const railItems = computed(() => {
  const ev = d.value.rail.events.map((e) => ({ key: 'e' + e.name + e.start, kind: e.source === 'task' ? 'task' : 'event', name: e.name, title: e.title,
    time: e.all_day ? 'All day' : String(e.start || '').slice(11, 16) }))
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
  if (!res) return
  d.value = res
  paneNav.rows = res.next.groups.flatMap((g) => g.rows.map((r) => (r.type === 'event' ? 'event:' + r.name : !r.type || r.type === 'task' ? 'task:' + r.name : null)).filter(Boolean))
}
onRecordChanged(() => load())
async function done(t) {
  await optimistic(() => { t.status = 'Done'; t._done = true }, () => { t.status = 'Open'; t._done = false },
    () => todayData.tasks.set_status({ task: t.name, status: 'Done' })).catch(() => {})
  setTimeout(load, 700)
}
function triage(t) {
  const leave = (request, message) => async () => { if (await tryCall(request, message)) load() }
  const move = (label, date) => ({ label, onClick: leave(() => todayData.tasks.update({ task: t.name, values: { due_date: date } }), `Moved to ${long(date)}`) })
  return [move('Today', d.value.date), move('Tomorrow', addDays(d.value.date, 1)), move('Next week', addDays(startOfWeek(d.value.date), 7)),
    { label: 'Drop', onClick: leave(() => todayData.tasks.set_status({ task: t.name, status: 'Dropped' }), 'Dropped') }]
}
async function moveAll({ close }) {
  const out = await tryCall(() => todayData.tasks.reschedule_overdue({ space: store.space, to_date: d.value.date }))
  close()
  if (out) { toast.success(`${out.moved} task${out.moved === 1 ? '' : 's'} moved to today`); load() }
}
// ticking a 12 Week Year action records the week's tick; the week score follows
function toggleHabit(x) {
  optimistic(() => (x.done = !x.done), () => (x.done = !x.done),
    () => todayData.goals.toggle_habit({ habit: x.habit, date: d.value.date, done: x.done ? 1 : 0 })).catch(() => {})
}
let clock = null
onMounted(() => { load(); clock = setInterval(() => (nowTime.value = new Date().toTimeString().slice(0, 5)), 60000) })
onUnmounted(() => { paneNav.rows = []; clearInterval(clock) })
</script>
