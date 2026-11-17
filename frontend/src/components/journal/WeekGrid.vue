<template>
  <Teleport to="#jr-actions">
    <Dropdown v-if="g && g.cycles.length > 1" :options="cycleOptions"><Button :label="g.cycle.title" icon-right="lucide-chevron-down" /></Dropdown>
    <template v-if="g && writable">
      <Button v-if="g.cycle.status === 'Planned'" label="Start this cycle" @click="startCycle" />
      <Button v-if="g.cycle.status === 'Active' && g.past_end" label="Close cycle" route="/plan/year?view=goals" />
      <Button v-if="g.cycle.status !== 'Closed'" label="Add goal" @click="editGoal(null)" />
    </template>
    <Button variant="solid" label="Weekly review" route="/plan/week?view=review" />
  </Teleport>

  <div v-if="g" class="page-body">
    <div class="stats">
      <Stat :label="g.current_week ? `This week, week ${g.current_week}` : g.cycle.status === 'Closed' ? 'Final score' : 'Week score'">
        <span data-week-score>{{ g.current_week ? pct(week.percent) : g.cycle.status === 'Closed' ? pct(g.cycle.final_score) : '—' }}</span>
        <template #sub><span class="max-md:hidden">{{ g.current_week ? `${week.done} of ${week.planned} ticks so far` : g.cycle.status }}</span></template>
      </Stat>
      <Stat :label="g.cycle.status === 'Closed' ? 'Cycle average' : 'Average so far'" :value="pct(g.average)">
        <template #sub><span class="max-md:hidden">Target {{ g.target }}%</span></template>
      </Stat>
      <Stat label="Weeks left" :value="g.cycle.status === 'Closed' ? 0 : g.weeks_left">
        <template #sub><span class="max-md:hidden">Cycle ends {{ long(g.cycle.end_date) }}</span></template>
      </Stat>
    </div>

    <div v-if="g.goals.length" class="overflow-hidden rounded-5 border border-outline-gray-2"><div class="scroll-x">
      <div class="grid-w">
        <div class="gr border-b border-outline-gray-1 bg-surface-gray-1">
          <div class="sticky left-0 z-[1] min-w-0 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-6">Goal and action</div>
          <div v-for="w in 12" :key="w" class="py-2 text-center text-xs tabular-nums" :class="w === g.current_week ? 'font-semibold text-ink-blue-8' : 'text-ink-gray-6'">{{ w }}</div>
        </div>
        <template v-for="(goal, gi) in g.goals" :key="goal.name">
          <div class="group flex flex-wrap items-center gap-2 px-3 pb-1.5 pt-3 max-md:px-2" :class="gi && 'border-t border-outline-gray-1'">
            <RouterLink class="font-semibold text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="`/plan/goals/${goal.name}`">{{ goal.title }}</RouterLink>
            <Badge v-if="goal.area_name" :label="goal.area_name" />
            <span v-if="goal.result && goal.result.kind === 'number'" class="text-sm tabular-nums text-ink-gray-7" data-grid-result>{{ goal.result.label }}</span>
            <RouterLink v-if="goal.serves_title" class="min-w-0 truncate text-sm text-ink-gray-6 hover:underline focus-visible:focus-ring" :to="`/plan/goals/${goal.serves}`"
              data-grid-serves>Serves {{ goal.serves_title }}{{ goal.serves_progress ? ' · ' + goal.serves_progress.label : '' }}</RouterLink>
            <Button v-if="canEdit" class="opacity-0 focus-visible:opacity-100 group-hover:opacity-100 max-md:opacity-100" variant="ghost" size="sm" label="Edit" :aria-label="`Edit ${goal.title}`" @click="editGoal(goal)" />
          </div>
          <div v-for="a in goal.actions" :key="a.name" class="gr">
            <div class="sticky left-0 z-[1] min-w-0 bg-surface-base py-1 pl-4 pr-3 max-md:pl-1 max-md:pr-2" :class="a.status !== 'Open' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-8'">
              <Dropdown v-if="canEdit" :options="actionMenu(a)"><Button class="max-w-full" :class="a.status !== 'Open' && 'line-through'" variant="ghost" size="sm">{{ a.title }}<span
                v-if="a.per_week > 1" class="text-ink-gray-6"> ×{{ a.per_week }}</span></Button></Dropdown>
              <span v-else class="px-2">{{ a.title }}</span>
            </div>
            <div v-for="w in 12" :key="w" class="grid place-items-center py-[3px]">
              <Button class="!size-7 !p-0 tabular-nums max-md:!size-10" :class="cellClass(a, w) === 'na' && 'invisible'" size="sm" v-bind="CELL[cellClass(a, w)]"
                :disabled="!canEdit || cellClass(a, w) === 'na'" :data-week-cell="w" :aria-pressed="count(a, w) >= a.per_week"
                :aria-label="`${a.title}, week ${w}, ${count(a, w)} of ${a.per_week}`" @click="tap(a, w)">
                <template v-if="count(a, w) >= a.per_week">
                  <span v-if="a.per_week === 1" class="lucide-check size-4" aria-hidden="true" />
                  <template v-else>{{ count(a, w) }}</template>
                </template>
                <template v-else-if="count(a, w) > 0">{{ count(a, w) }}</template>
                <template v-else-if="g.current_week && w < g.current_week || !g.current_week && g.cycle.status === 'Closed'">–</template>
              </Button>
            </div>
          </div>
        </template>
        <div class="gr border-t border-outline-gray-1 bg-surface-gray-1">
          <div class="sticky left-0 z-[1] min-w-0 bg-surface-gray-1 px-3 py-2.5 font-semibold text-ink-gray-9">Week score</div>
          <div v-for="w in g.weeks" :key="w.week" class="py-2.5 text-center text-sm font-semibold tabular-nums text-ink-gray-9">{{ showScore(w.week) ? pct(w.percent) : '' }}</div>
        </div>
      </div>
    </div></div>
    <Card v-else><Empty title="No goals in this cycle yet." hint="Add a goal with its weekly actions. Each week you tick what you did, and the score follows." /></Card>

    <div class="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-ink-gray-6">
      <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3.5 rounded-1 bg-surface-gray-9"></i>Done</span>
      <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3.5 rounded-1 bg-surface-gray-2"></i>Missed</span>
      <span class="inline-flex items-center gap-1.5"><i class="inline-block size-3.5 rounded-1 border-2 border-outline-blue-6"></i>This week, tap to tick</span>
      <span>A struck-through action is finished and no longer counts. Tap an action's name to finish or drop it.</span>
    </div>
  </div>
  <div v-else-if="loaded" class="page-body"><Card>
    <Empty title="No 12 Week Year yet." hint="A cycle is twelve weeks of goals with weekly actions." />
    <Button v-if="canWrite()" variant="solid" label="Start a cycle next Monday" @click="createCycle" /></Card></div>
  <GoalDialog v-model="goalOpen" :cycle="g && g.cycle.name" :goal="editing" @saved="load()" />
</template>
<script setup>
// The 12 Week Year grid: one row per action, one cell per week. A cell is a frappe-ui Button; its variant says its state.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Dropdown, toast } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import Stat from '@/components/ui/Stat.vue'
import GoalDialog from './GoalDialog.vue'
import { api, errorText, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long } from '@/lib/dates'

const emit = defineEmits(['sub'])
const route = useRoute()
const router = useRouter()
const g = ref(null)
const loaded = ref(false)
const goalOpen = ref(false)
const editing = ref(null)
const pct = (n) => Math.round(n || 0) + '%'
const writable = computed(() => store.spaces.find((s) => s.name === g.value?.cycle.space)?.access === 'Write')
const canEdit = computed(() => writable.value && g.value.cycle.status !== 'Closed')
const week = computed(() => g.value.weeks[(g.value.current_week || 1) - 1])
const cycleOptions = computed(() => g.value.cycles.map((c) => ({ label: `${c.title} · ${c.status}`, onClick: () => router.push({ query: { cycle: c.name } }).then(() => load()) })))
const count = (a, w) => a.ticks[String(w)] || 0
const showScore = (w) => g.value.cycle.status === 'Closed' || (g.value.current_week && w <= g.value.current_week)
// the Button that draws each state of a cell: done is solid, this week is blue, missed or part done is filled, not yet is outlined
const CELL = {
  done: { variant: 'solid' }, curdone: { variant: 'solid', theme: 'blue' }, cur: { variant: 'outline', theme: 'blue', class: '!border-outline-blue-6 !text-ink-blue-8' },
  miss: { variant: 'subtle' }, part: { variant: 'subtle' }, na: { variant: 'outline' }, '': { variant: 'outline' },
}

function planned(a, w) {
  if (a.status === 'Dropped') return 0
  if (a.status === 'Done') return w <= (a.done_week || 12) ? a.per_week : 0
  return a.per_week
}
function cellClass(a, w) {
  if (!planned(a, w)) return 'na'
  const cur = g.value.current_week
  const done = count(a, w) >= a.per_week
  if (cur && w === cur) return done ? 'curdone' : 'cur'
  if (done) return 'done'
  if ((cur && w < cur) || (!cur && g.value.cycle.status === 'Closed')) return count(a, w) ? 'part' : 'miss'
  return count(a, w) ? 'part' : ''
}
function recalc(w) {
  let done = 0, plannedSum = 0
  for (const goal of g.value.goals) for (const a of goal.actions) {
    const p = planned(a, w)
    plannedSum += p
    done += Math.min(count(a, w), p)
  }
  Object.assign(g.value.weeks[w - 1], { done, planned: plannedSum, percent: plannedSum ? (100 * done) / plannedSum : 0 })
}
// Tap a cell: an action done once a week toggles, others count up to per_week and wrap to zero.
async function tap(a, w) {
  const before = count(a, w)
  const next = before >= a.per_week ? 0 : before + 1
  a.ticks[String(w)] = next
  recalc(w)
  try {
    const score = await api('journal.tick', { action: a.name, week: w, count: next })
    Object.assign(g.value.weeks[w - 1], score)
    refreshAverage()
  } catch (e) {
    a.ticks[String(w)] = before
    recalc(w)
    toast.error(errorText(e))
  }
}
function refreshAverage() {
  const upto = g.value.current_week
  if (!upto) return
  const scores = g.value.weeks.slice(0, upto).map((w) => w.percent)
  g.value.average = scores.reduce((x, y) => x + y, 0) / scores.length
}
function actionMenu(a) {
  const set = (status) => async () => { if (await tryCall(() => api('journal.set_action_status', { action: a.name, status }))) load() }
  const items = []
  if (a.status !== 'Done') items.push({ label: 'Finished for good', onClick: set('Done') })
  if (a.status !== 'Dropped') items.push({ label: 'Drop this action', onClick: set('Dropped') })
  if (a.status !== 'Open') items.push({ label: 'Open again', onClick: set('Open') })
  return items
}
function editGoal(goal) {
  editing.value = goal
  goalOpen.value = true
}
async function startCycle() {
  if (await tryCall(() => api('journal.start_cycle', { cycle: g.value.cycle.name }), 'Cycle started.')) load()
}
async function createCycle() {
  if (await tryCall(() => api('journal.create_cycle', { space: store.space }), 'Cycle created.')) load()
}
async function load() {
  const res = await tryCall(() => api('journal.grid', { space: store.space, cycle: route.query.cycle || undefined, area: store.lensArea || undefined }))
  g.value = res || null
  loaded.value = true
  emit('sub', res ? `${res.cycle.title} · ${long(res.cycle.start_date)} to ${long(res.cycle.end_date)}` : 'The 12 Week Year')
}
onMounted(load)
</script>
<style scoped>
/* geometry only: the columns of the grid (the action name, then twelve weeks) */
.grid-w { min-width: 760px; }
.gr { display: grid; grid-template-columns: minmax(250px, 1.7fr) repeat(12, minmax(36px, 1fr)); align-items: center; }
@media (max-width: 767px) {
  .grid-w { min-width: 0; width: max-content; }
  .gr { grid-template-columns: 150px repeat(12, 48px); }
}
</style>
