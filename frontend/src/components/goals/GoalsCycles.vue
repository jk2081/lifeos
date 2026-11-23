<template>
  <PageHead title="Goals" sub="Cycles: the 12 Week Year and this month's goals, in one place.">
    <Button v-if="writable" variant="solid" icon-left="lucide-plus" label="Goal" data-new-goal @click="newOpen = true" />
  </PageHead>
  <div class="page-body" data-cycles :data-loaded="loaded ? 1 : 0">
   <Card v-for="r in reviewsDue" :key="r.kind" tint class="flex max-w-[1400px] flex-wrap items-center gap-3 !p-3" data-review-due :data-review-kind="r.kind">
     <span class="min-w-0 flex-1 text-base text-ink-gray-9">{{ r.text }}<span v-if="r.detail" class="text-ink-gray-6"> · {{ r.detail }}</span></span>
     <Button variant="solid" label="Start the review" :route="{ path: '/review', query: { kind: r.kind } }" data-review-start />
   </Card>
   <div class="grid max-w-[1400px] items-start gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
    <!-- left: the 12 Week Year -->
    <Card class="flex min-w-0 flex-col gap-4 !p-4 md:!p-5" data-cycle-card>
      <template v-if="g">
        <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 class="text-lg-semibold text-ink-gray-9" data-cycle-title>12 Week Year · {{ range }}</h2>
          <span class="text-sm text-ink-gray-6" data-cycle-line>{{ line }}</span>
          <div class="ml-auto flex items-center gap-2">
            <Dropdown v-if="g.cycles.length > 1" :options="cycleOptions"><Button size="sm" variant="ghost" :label="g.cycle.title" icon-right="lucide-chevron-down" data-cycle-picker /></Dropdown>
            <Button size="sm" variant="ghost" class="!text-ink-blue-8" label="Cycle goals" data-cycle-goals @click="goalsOpen = true" />
          </div>
        </div>
        <p v-if="closed" class="rounded-5 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-7" data-cycle-closed>This cycle is closed: the scores are final and it is read-only.</p>

        <div data-week-bars-scroll>
          <ol class="flex items-end gap-2 max-md:gap-0.5" aria-label="Weekly scores">
            <li v-for="w in g.weeks" :key="w.week" class="flex min-w-0 flex-1 flex-col items-center gap-1" :data-week-bar="w.week" :data-week-state="state(w.week)"
              :data-score="state(w.week) === 'future' ? '' : Math.round(w.percent)">
              <span class="h-4 max-w-full truncate text-xs tabular-nums text-ink-gray-6 max-md:text-[10px]">{{ state(w.week) === 'now' ? 'so far' : state(w.week) === 'past' ? pct(w.percent) : '' }}</span>
              <div class="flex h-20 w-full items-end"><div class="w-full rounded-4" :class="barClass(w.week)" :style="{ height: barHeight(w) }" /></div>
              <span class="text-xs text-ink-gray-6 max-md:text-[10px]"><span class="max-md:hidden">W</span>{{ w.week }}</span>
            </li>
          </ol>
        </div>

        <div v-if="g.goals.length" class="flex flex-col" data-cycle-goal-list>
          <div class="grid grid-cols-[minmax(0,1.1fr)_minmax(0,1.3fr)_auto_3.5rem] gap-3 border-b border-outline-gray-1 pb-1.5 text-sm text-ink-gray-6 max-md:hidden">
            <span>Goal</span><span>Lead action {{ g.current_week ? 'this week' : '' }}</span><span>Ticks</span><span class="text-right" /></div>
          <div v-for="goal in g.goals" :key="goal.name" class="grid grid-cols-[minmax(0,1.1fr)_minmax(0,1.3fr)_auto_3.5rem] items-center gap-x-3 gap-y-1 border-b border-outline-gray-1 py-2.5 last:border-b-0 max-md:grid-cols-[minmax(0,1fr)_auto]"
            data-cycle-goal :data-goal="goal.name">
            <div class="min-w-0 max-md:col-span-2">
              <RouterLink class="break-words text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="`/goals/${goal.name}`">{{ goal.title }}</RouterLink>
              <RouterLink v-if="goal.serves_title" class="block truncate text-sm text-ink-gray-6 hover:underline focus-visible:focus-ring" :to="`/goals/${goal.serves}`" data-grid-serves>Serves {{ goal.serves_title }}{{ goal.serves_progress ? ' · ' + goal.serves_progress.label : '' }}</RouterLink>
            </div>
            <template v-if="lead(goal)">
              <span class="min-w-0 truncate text-ink-gray-8" data-lead-action>{{ lead(goal).title }}<span class="text-ink-gray-6"> · {{ lead(goal).per_week }}/wk</span></span>
              <span class="flex gap-1" role="group" :aria-label="`Ticks for ${lead(goal).title}`">
                <button v-for="i in lead(goal).per_week" :key="i" type="button" class="size-[22px] rounded-4 border focus-visible:focus-ring max-md:size-8"
                  :class="i <= count(lead(goal)) ? 'border-outline-gray-9 bg-surface-gray-9' : 'border-outline-gray-3 bg-surface-base'" :disabled="!canTick"
                  :aria-pressed="i <= count(lead(goal))" :aria-label="`${lead(goal).title}, tick ${i} of ${lead(goal).per_week}`" data-tick @click="tap(lead(goal), i)" />
              </span>
              <span class="text-right text-sm tabular-nums text-ink-gray-6" data-tick-count>{{ count(lead(goal)) }} of {{ lead(goal).per_week }}</span>
            </template>
            <span v-else class="col-span-3 text-sm text-ink-gray-6 max-md:col-span-1">No action yet</span>
          </div>
        </div>
        <Empty v-else title="No goals in this cycle yet." hint="Add a goal with its weekly actions. Each week you tick what you did, and the score follows."><Button v-if="canEdit" class="mt-3" variant="solid" label="Cycle goals" @click="goalsOpen = true" /></Empty>

        <div class="flex flex-wrap items-center justify-between gap-3 rounded-5 bg-surface-gray-1 px-4 py-3 text-sm text-ink-gray-7" data-cycle-footer>
          <p class="min-w-0 flex-1">
            <template v-if="g.current_week">This week so far: <b data-week-so-far>{{ pct(week.percent) }}</b>. The score is locked in {{ reviewDay }}'s review. </template>
            <template v-else-if="closed">Final score {{ pct(g.cycle.final_score) }}. </template>
            <template v-else-if="g.cycle.status === 'Planned'">This cycle has not started: it begins {{ long(g.cycle.start_date) }}. </template>
            <span data-next-cycle>Planning for the next cycle opens on {{ long(g.next.plan_opens) }}<template v-if="g.next.break_week">; the break week is {{ short(g.next.break_week[0]) }} – {{ short(g.next.break_week[1]) }}</template>.</span>
          </p>
          <Button v-if="g.current_week" label="Score this week" route="/today/week?view=review" />
        </div>
      </template>
      <Empty v-else-if="loaded" title="No 12 Week Year yet." hint="A cycle is twelve weeks of goals with weekly actions. Each week you tick what you did, and the score follows.">
        <Button v-if="writable" class="mt-3" variant="solid" label="Start a cycle next Monday" data-create-cycle @click="createCycle" /></Empty>
    </Card>

    <!-- right: this month's goals (goals with the Month horizon) and its habits -->
    <Card v-if="mp" class="flex min-w-0 flex-col gap-4 !p-4 md:!p-5" data-month-card>
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 class="text-lg-semibold text-ink-gray-9" data-month-title>{{ MONTHS[mp.month - 1] }} goals</h2>
        <span v-if="goals.length" class="text-sm text-ink-gray-6">{{ goals.length }} month goal{{ goals.length === 1 ? '' : 's' }} · {{ closedCount }} done or closed</span>
      </div>
      <ol v-if="goals.length" class="flex flex-col">
        <li v-for="(m, i) in goals" :key="m.row" class="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-outline-gray-1 py-2.5 last:border-b-0" data-month-goal :data-goal="m.row">
          <span class="w-5 flex-none text-center text-sm tabular-nums text-ink-gray-6" aria-hidden="true">{{ i + 1 }}</span>
          <RouterLink class="min-w-0 flex-1 break-words hover:underline focus-visible:focus-ring" :class="m.status === 'Done' || m.status === 'Dropped' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'" :to="`/goals/${m.row}`">{{ m.title }}</RouterLink>
          <Badge v-if="m.area_name" :label="m.area_name" />
          <Badge :theme="statusOf(m).theme" :label="statusOf(m).label" data-month-status />
        </li>
      </ol>
      <Empty v-else title="No goals this month." hint="A month goal is a goal with the Month horizon. Add one with + Goal.">
        <Button v-if="writable" class="mt-3" variant="solid" label="Goal" @click="newOpen = true" /></Empty>

      <div v-if="mp.habits.habits.length" data-month-habits>
        <h3 class="mb-2 text-sm text-ink-gray-6">Habits this month</h3>
        <div v-for="h in mp.habits.habits" :key="h.habit" class="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] items-center gap-3 py-1.5 max-md:grid-cols-[minmax(0,1fr)_auto]" data-month-habit>
          <span class="min-w-0 truncate text-ink-gray-9">{{ h.title }} <span class="text-ink-gray-6">{{ h.days_per_week >= 7 ? 'daily' : `${h.days_per_week} a week` }}</span></span>
          <div class="max-md:col-span-2 max-md:order-3"><Progress size="sm" :value="h.percent" /></div>
          <span class="text-sm tabular-nums text-ink-gray-6">{{ h.done }} of {{ h.target }}</span>
        </div>
      </div>
    </Card>
   </div>
  </div>

  <CycleGoalsDialog v-if="g" v-model="goalsOpen" :grid="g" :writable="canEdit" @changed="load" />
  <NewGoalDialog v-model="newOpen" @saved="load" @habit="loadMonth" />
</template>
<script setup>
// Goals > Cycles (issue 45): the 12 Week Year on the left (week bars, each cycle goal's lead action and this week's ticks) and this
// month's plan on the right. It moves the Plan section's screens; the records, the API and the scores are the same.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dropdown, Progress, toast } from 'frappe-ui'
import PageHead from '@/components/PageHead.vue'
import Card from '@/components/ui/Card.vue'
import Empty from '@/components/Empty.vue'
import Md from '@/components/Md.vue'
import CycleGoalsDialog from '@/components/goals/CycleGoalsDialog.vue'
import NewGoalDialog from '@/components/goals/NewGoalDialog.vue'
import { errorText, tryCall } from '@/lib/api'
import { goalsData } from '@/data/goals'
import { canWrite, store } from '@/lib/store'
import { onRecordChanged } from '@/lib/pane'
import { areaName, loadLookups } from '@/lib/lookups'
import { MONTHS, long, short } from '@/lib/dates'

const route = useRoute()
const router = useRouter()
const g = ref(null)
const mp = ref(null)
const loaded = ref(false)
const goalsOpen = ref(false)
const newOpen = ref(false)
const reviewsDue = ref([])
const pct = (n) => Math.round(n || 0) + '%'
const closed = computed(() => g.value?.cycle.status === 'Closed')
const writable = computed(() => canWrite() && !store.isAgent)
const canEdit = computed(() => writable.value && !closed.value)
// a tick can be set on this week, in a cycle that is open
const canTick = computed(() => canEdit.value && !!g.value?.current_week)
const week = computed(() => g.value.weeks[(g.value.current_week || 1) - 1])
const reviewDay = computed(() => store.settings?.weekly_review_day || 'Sunday')
const range = computed(() => `${short(g.value.cycle.start_date)} – ${short(g.value.cycle.end_date)}`)
const line = computed(() => {
  const c = g.value
  if (c.cycle.status === 'Closed') return `closed · final score ${pct(c.cycle.final_score)} · target ${c.target}%`
  if (!c.current_week) return `${c.cycle.status === 'Planned' ? 'starts ' + long(c.cycle.start_date) : 'finished'} · target ${c.target}%`
  return `week ${c.current_week} of 12 · average ${pct(c.average)} · target ${c.target}%`
})
const cycleOptions = computed(() => g.value.cycles.map((c) => ({ label: `${c.title} · ${c.status}`, onClick: () => router.push({ query: { ...route.query, cycle: c.name } }) })))

// a past week's bar is solid, this week's is "so far" (hatched), the rest are empty; a closed cycle's weeks are all past
function state(w) {
  if (closed.value) return 'past'
  const cur = g.value.current_week
  if (!cur) return g.value.past_end ? 'past' : 'future'
  return w < cur ? 'past' : w === cur ? 'now' : 'future'
}
const barClass = (w) => ({ past: 'bg-surface-gray-9', now: 'bar-sofar', future: 'bg-surface-gray-2' })[state(w)]
const barHeight = (w) => (state(w.week) === 'future' ? '24%' : `${Math.max(w.percent, 6)}%`)

// each cycle goal's lead action: the first open one
const lead = (goal) => goal.actions.find((a) => a.status === 'Open') || null
const count = (a) => (g.value.current_week && a.ticks[String(g.value.current_week)]) || 0
async function tap(a, i) {
  const w = g.value.current_week
  const before = count(a)
  const next = i === before ? i - 1 : i
  a.ticks[String(w)] = next
  try {
    const score = await goalsData.goals.tick({ action: a.name, week: w, count: next })
    Object.assign(g.value.weeks[w - 1], score)
    const scores = g.value.weeks.slice(0, w).map((x) => x.percent)
    g.value.average = scores.reduce((x, y) => x + y, 0) / scores.length
  } catch (e) {
    a.ticks[String(w)] = before
    toast.error(errorText(e))
  }
}

// this month's goals
const goals = computed(() => (mp.value?.goals || []).map((m) => ({ ...m, area_name: m.area_name || areaName(m.area) })))
const closedCount = computed(() => goals.value.filter((m) => m.status !== 'Open').length)
function statusOf(m) {
  if (m.status === 'Done') return { label: 'Done', theme: 'green' }
  if (m.status === 'Dropped') return { label: 'Dropped', theme: 'gray' }
  if (m.status === 'Carried') return { label: 'Carried forward', theme: 'gray' }
  if (m.carried_from) return { label: m.carried_from_month ? `Carried from ${MONTHS[m.carried_from_month - 1].slice(0, 3)}` : 'Carried from last month', theme: 'orange' }
  if (m.tasks_counted) return { label: `${m.tasks_done} of ${m.tasks_counted}`, theme: 'green' }
  return { label: 'In progress', theme: 'green' }
}
async function createCycle() {
  if (await tryCall(() => goalsData.goals.create_cycle({ space: store.space }), 'Cycle created.')) load()
}

async function loadGrid() {
  const res = await tryCall(() => goalsData.goals.grid({ space: store.space, cycle: route.query.cycle || undefined, area: store.lensArea || undefined }))
  g.value = res || null
}
async function loadMonth() {
  const res = await tryCall(() => goalsData.goals.this_month({ space: store.space, area: store.lensArea || undefined }))
  if (res) mp.value = res
}
// the monthly and the 12-week review, when one is due (issue 47)
async function loadDue() {
  const res = writable.value ? await tryCall(() => goalsData.periodic.due({ space: store.space })) : null
  reviewsDue.value = (res?.due || []).filter((r) => r.kind !== 'weekly')
}
async function load() {
  await Promise.all([loadLookups(), loadGrid(), loadMonth(), loadDue()])
  loaded.value = true
}
watch(() => [store.space, store.lensArea, route.query.cycle], load)
onRecordChanged(load)
onMounted(load)
</script>
<style scoped>
/* the week still being lived: a hatched bar */
.bar-sofar { background: repeating-linear-gradient(45deg, var(--ink-gray-9, #171717) 0 3px, var(--surface-gray-4, #c4c4c4) 3px 6px); }
</style>
