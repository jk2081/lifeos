<template>
  <Teleport to="#jr-actions">
    <Dropdown v-if="g && g.cycles.length > 1" :options="cycleOptions"><button class="bt s" type="button">{{ g.cycle.title }} ▾</button></Dropdown>
    <template v-if="g && writable">
      <button v-if="g.cycle.status === 'Planned'" class="bt s" type="button" @click="startCycle">Start this cycle</button>
      <RouterLink v-if="g.cycle.status === 'Active' && g.past_end" class="bt s" to="/journal/goals">Close cycle</RouterLink>
      <button v-if="g.cycle.status !== 'Closed'" class="bt s" type="button" @click="editGoal(null)">Add goal</button>
    </template>
    <RouterLink class="bt p" to="/journal/review" style="color: var(--bg)">Weekly review</RouterLink>
  </Teleport>

  <div v-if="g" class="bd">
    <div class="stats three">
      <div class="cd st"><span class="mt">{{ g.current_week ? `This week, week ${g.current_week}` : g.cycle.status === 'Closed' ? 'Final score' : 'Week score' }}</span>
        <b data-week-score>{{ g.current_week ? pct(week.percent) : g.cycle.status === 'Closed' ? pct(g.cycle.final_score) : '—' }}</b>
        <span class="mt">{{ g.current_week ? `${week.done} of ${week.planned} ticks so far` : g.cycle.status }}</span></div>
      <div class="cd st"><span class="mt">{{ g.cycle.status === 'Closed' ? 'Cycle average' : 'Average so far' }}</span><b>{{ pct(g.average) }}</b><span class="mt">Target {{ g.target }}%</span></div>
      <div class="cd st"><span class="mt">Weeks left</span><b>{{ g.cycle.status === 'Closed' ? 0 : g.weeks_left }}</b><span class="mt">Cycle ends {{ long(g.cycle.end_date) }}</span></div>
    </div>

    <div v-if="g.goals.length" class="tblwrap"><div class="tblscroll">
      <div class="grid">
        <div class="gr hdr">
          <div class="gcol" style="padding: 8px 12px; font-size: 12.5px; color: var(--mut)">Goal and action</div>
          <div v-for="w in 12" :key="w" class="gh" :class="{ cur: w === g.current_week }">{{ w }}</div>
        </div>
        <template v-for="goal in g.goals" :key="goal.name">
          <div class="gr gline">
            <div class="gcol gl">
              <RouterLink :to="`/journal/goals/${goal.name}`" style="color: var(--ink)">{{ goal.title }}</RouterLink>
              <span v-if="goal.area_name" class="pl n">{{ goal.area_name }}</span>
              <button v-if="canEdit" class="edit" type="button" :aria-label="`Edit ${goal.title}`" @click="editGoal(goal)">Edit</button>
            </div>
          </div>
          <div v-for="a in goal.actions" :key="a.name" class="gr">
            <div class="gcol ac" :class="{ fin: a.status !== 'Open' }">
              <Dropdown v-if="canEdit" :options="actionMenu(a)"><button class="acbtn" type="button" :class="{ fin: a.status !== 'Open' }">{{ a.title }}<span
                v-if="a.per_week > 1" class="mt"> ×{{ a.per_week }}</span></button></Dropdown>
              <span v-else>{{ a.title }}</span>
            </div>
            <div v-for="w in 12" :key="w" class="wc">
              <button class="wk" :class="cellClass(a, w)" type="button" :disabled="!canEdit || cellClass(a, w) === 'na'"
                :aria-label="`${a.title}, week ${w}, ${count(a, w)} of ${a.per_week}`" @click="tap(a, w)">
                <template v-if="count(a, w) >= a.per_week">
                  <svg v-if="a.per_week === 1" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true"><path d="m5 12 5 5 9-10" /></svg>
                  <template v-else>{{ count(a, w) }}</template>
                </template>
                <template v-else-if="count(a, w) > 0">{{ count(a, w) }}</template>
                <template v-else-if="g.current_week && w < g.current_week || !g.current_week && g.cycle.status === 'Closed'">–</template>
              </button>
            </div>
          </div>
        </template>
        <div class="gr foot">
          <div class="gcol" style="padding: 10px 12px; font-weight: 600">Week score</div>
          <div v-for="w in g.weeks" :key="w.week" class="sc">{{ showScore(w.week) ? pct(w.percent) : '' }}</div>
        </div>
      </div>
    </div></div>
    <div v-else class="cd"><Empty title="No goals in this cycle yet." hint="Add a goal with its weekly actions. Each week you tick what you did, and the score follows." /></div>

    <div class="mt legend">
      <span><i class="sw" style="background: var(--ink)"></i>Done</span><span><i class="sw" style="background: var(--fill)"></i>Missed</span>
      <span><i class="sw" style="border: 2px solid var(--accent)"></i>This week, tap to tick</span>
      <span>A struck-through action is finished and no longer counts. Tap an action's name to finish or drop it.</span>
    </div>
  </div>
  <div v-else-if="loaded" class="bd"><div class="cd">
    <Empty title="No 12 Week Year yet." hint="A cycle is twelve weeks of goals with weekly actions." />
    <button v-if="canWrite()" class="bt p" type="button" @click="createCycle">Start a cycle next Monday</button></div></div>
  <GoalDialog v-model="goalOpen" :cycle="g && g.cycle.name" :goal="editing" @saved="load()" />
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Dropdown, toast } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
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
  const res = await tryCall(() => api('journal.grid', { space: store.space, cycle: route.query.cycle || undefined }))
  g.value = res || null
  loaded.value = true
  emit('sub', res ? `${res.cycle.title} · ${long(res.cycle.start_date)} to ${long(res.cycle.end_date)}` : 'The 12 Week Year')
}
onMounted(load)
</script>
<style scoped>
.stats.three { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.grid { min-width: 760px; }
.gr { display: grid; grid-template-columns: minmax(250px, 1.7fr) repeat(12, minmax(36px, 1fr)); align-items: center; }
.gr.hdr { background: var(--side); border-bottom: 1px solid var(--line); }
.gr.foot { background: var(--side); border-top: 1px solid var(--line); }
.gcol { position: sticky; left: 0; background: var(--bg); z-index: 1; min-width: 0; }
.gr.hdr .gcol, .gr.foot .gcol { background: var(--side); }
.gh { font-size: 12px; color: var(--mut); text-align: center; padding: 8px 0; font-variant-numeric: tabular-nums; }
.gh.cur { color: var(--accent); font-weight: 600; }
.gline { border-top: 1px solid var(--line); }
.gline:first-of-type { border-top: 0; }
.gl { display: flex; align-items: center; gap: 8px; padding: 12px 12px 6px; font-weight: 600; flex-wrap: wrap; grid-column: 1 / -1; position: static; }
.gl .edit { border: 0; background: none; color: var(--mut); font-size: 12px; cursor: pointer; opacity: 0; }
.gline:hover .edit, .edit:focus { opacity: 1; }
.ac { padding: 5px 12px 5px 24px; color: var(--ink2); }
.acbtn { border: 0; background: none; padding: 0; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.fin, .acbtn.fin { text-decoration: line-through; color: var(--mut); }
.wc { display: grid; place-items: center; padding: 3px 0; }
.wk { width: 28px; height: 28px; border-radius: 7px; border: 1px solid var(--line3); background: var(--bg); color: var(--ink); font: 600 13px Inter, system-ui, sans-serif; cursor: pointer; padding: 0; display: grid; place-items: center; }
.wk.done { background: var(--ink); border-color: var(--ink); color: var(--bg); }
.wk.miss { background: var(--fill); border-color: var(--fill); color: var(--mut); }
.wk.part { background: var(--fill); border-color: var(--line4); }
.wk.cur { border: 2px solid var(--accent); }
.wk.curdone { background: var(--accent); border-color: var(--accent); color: var(--bg); }
.wk.na { visibility: hidden; }
.wk:disabled { cursor: default; }
.sc { font-size: 12.5px; font-weight: 600; text-align: center; padding: 10px 0; font-variant-numeric: tabular-nums; }
.legend { display: flex; gap: 6px 18px; flex-wrap: wrap; align-items: center; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 14px; height: 14px; border-radius: 4px; display: inline-block; box-sizing: border-box; }
@media (max-width: 800px) {
  .grid { min-width: 0; width: max-content; }
  .gr { grid-template-columns: 150px repeat(12, 48px); }
  .wk { width: 40px; height: 40px; border-radius: 9px; }
  .ac { padding: 5px 8px 5px 12px; font-size: 13.5px; }
  .gl { padding: 12px 8px 6px; }
  .gl .edit { opacity: 1; }
  .stats.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .stats.three .mt:last-child { display: none; }
}
</style>
