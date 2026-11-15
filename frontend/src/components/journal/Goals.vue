<template>
  <Teleport to="#jr-actions">
    <template v-if="active && canWrite()">
      <button v-if="active.past_end" class="bt s" type="button" @click="openClose">Close cycle</button>
      <button class="bt s" type="button" @click="openPlan">Plan next cycle</button>
      <button class="bt p" type="button" @click="goalOpen = true">Add goal</button>
    </template>
  </Teleport>
  <div class="bd">
    <div v-if="d && d.areas.length" class="chips">
      <button class="ch" :class="{ on: !area }" type="button" @click="setArea('')">All areas</button>
      <button v-for="a in d.areas" :key="a.name" class="ch" :class="{ on: area === a.name }" type="button" @click="setArea(a.name)">{{ a.area_name }}</button>
    </div>
    <div v-if="d && d.cycles.length" class="tblwrap"><div class="tblscroll"><div style="min-width: 720px">
      <div class="gr hdr"><div>Goal</div><div>Area</div><div>Actions</div><div>Ticks done</div><div>Outcome</div></div>
      <template v-for="c in d.cycles" :key="c.name">
        <div class="cy">
          <b>{{ c.title }}</b>
          <span class="pl" :class="c.status === 'Active' ? 'b' : 'n'">{{ c.status === 'Active' ? (c.current_week ? `Active · week ${c.current_week}` : 'Active') : c.status }}</span>
          <span class="mt">{{ cycleNote(c) }}</span>
          <RouterLink :to="`/journal?cycle=${c.name}`" style="margin-left: auto; font-weight: 500">Open grid</RouterLink>
        </div>
        <div v-for="g in c.goals" :key="g.name" class="gr">
          <div><RouterLink :to="`/journal/goals/${g.name}`" style="font-weight: 500">{{ g.title }}</RouterLink>
            <div v-if="goalNote(g, c)" class="mt">{{ goalNote(g, c) }}</div></div>
          <div><span v-if="g.area_name" class="pl n">{{ g.area_name }}</span></div>
          <div>{{ g.actions }}</div>
          <div v-if="c.status === 'Planned'" class="mt" style="font-size: 13.5px">Not started</div>
          <div v-else class="pg"><div class="br"><i :style="`width: ${g.percent}%`"></i></div><span>{{ Math.round(g.percent) }}%</span></div>
          <div><span class="pl" :class="OUTCOME[c.status === 'Planned' ? 'Draft' : g.outcome]">{{ c.status === 'Planned' ? 'Draft' : g.outcome === 'In Progress' ? 'In progress' : g.outcome }}</span></div>
        </div>
        <div v-if="!c.goals.length" class="gr"><div class="mt" style="grid-column: 1 / -1">No goals{{ area ? ' in this area' : '' }} in this cycle.</div></div>
      </template>
    </div></div></div>
    <div v-else-if="d" class="cd"><Empty title="No goals yet." hint="Goals belong to a 12 Week Year. Open the 12 Week Year tab to start a cycle and add goals." /></div>
  </div>

  <GoalDialog v-model="goalOpen" :cycle="active && active.name" :goal="null" @saved="load" />

  <Dialog v-model="planOpen" title="Plan next cycle" size="lg">
    <p class="mt" style="margin: 0 0 10px">The next cycle starts the Monday after {{ active && long(active.end_date) }}. Pick the goals to carry. Each is copied with its open actions.</p>
    <label v-for="g in (active ? active.goals : [])" :key="g.name" class="rw" style="align-items: center; cursor: pointer">
      <input v-model="carry" type="checkbox" class="ck" style="margin: 0" :value="g.name" :disabled="g.outcome === 'Carried'" />
      <span class="grow">{{ g.title }} <span class="mt">{{ g.outcome === 'Carried' ? '· already carried' : `· ${Math.round(g.percent)}%` }}</span></span>
    </label>
    <template #actions><div style="display: flex; gap: 8px; justify-content: flex-end">
      <button class="bt s" type="button" @click="planOpen = false">Cancel</button>
      <button class="bt p" type="button" @click="plan">{{ carry.length ? `Carry ${carry.length} goal${carry.length === 1 ? '' : 's'}` : 'Create the next cycle' }}</button></div></template>
  </Dialog>

  <Dialog v-model="closeOpen" title="Close cycle" size="2xl">
    <p class="mt" style="margin: 0 0 10px">Give each goal an outcome and a note. The final score is stored and the cycle becomes read-only.</p>
    <div v-for="o in outcomes" :key="o.goal" class="rw" style="flex-wrap: wrap; align-items: center">
      <div style="flex: 1 1 180px; font-weight: 500">{{ o.title }} <span class="mt">{{ Math.round(o.percent) }}%</span></div>
      <select v-model="o.outcome" class="inp" :aria-label="`Outcome for ${o.title}`"><option v-for="x in OUTCOMES" :key="x">{{ x }}</option></select>
      <input v-model="o.result_note" class="inp" style="flex: 2 1 200px" placeholder="Note" :aria-label="`Note for ${o.title}`" />
    </div>
    <template #actions><div style="display: flex; gap: 8px; justify-content: flex-end">
      <button class="bt s" type="button" @click="closeOpen = false">Cancel</button><button class="bt p" type="button" @click="closeCycle">Close cycle</button></div></template>
  </Dialog>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { Dialog, toast } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
import GoalDialog from './GoalDialog.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long } from '@/lib/dates'

const emit = defineEmits(['sub'])
const OUTCOME = { 'In Progress': 'b', Achieved: 'g', 'Partly Achieved': 'g', 'Not Achieved': 'r', Carried: 'o', Dropped: 'r', Draft: 'n' }
const OUTCOMES = ['Achieved', 'Partly Achieved', 'Not Achieved', 'Carried', 'Dropped']
const d = ref(null)
const area = ref('')
const goalOpen = ref(false)
const planOpen = ref(false)
const closeOpen = ref(false)
const carry = ref([])
const outcomes = ref([])
const all = ref(null) // unfiltered, for the dialogs
const active = computed(() => (all.value || d.value)?.cycles.find((c) => c.status === 'Active'))

function cycleNote(c) {
  if (c.status === 'Planned') return `Starts ${long(c.start_date)} · goals carried from the current cycle show here until you start it`
  if (c.status === 'Active') return `Average score ${Math.round(c.average)}% · target ${d.value.target}%`
  return `Final score ${Math.round(c.average)}% · closed cycles are read-only`
}
function goalNote(g, c) {
  if (g.carried_from_cycle) return `Carried from ${g.carried_from_cycle}`
  if (g.carried_into_cycle) return `Carried into ${g.carried_into_cycle}`
  if (g.project_title) return `Linked to project ${g.project_title}`
  if (g.actions_done) return `${g.actions_done} of ${g.actions} actions finished`
  return c.status === 'Closed' ? g.result_note : ''
}
async function load() {
  const res = await tryCall(() => api('journal.goals', { space: store.space, area: area.value || undefined }))
  if (res) {
    d.value = res
    if (!area.value) all.value = res
  }
}
function setArea(a) {
  area.value = a
  load()
}
function openPlan() {
  carry.value = []
  planOpen.value = true
}
async function plan() {
  const res = await tryCall(() => api('journal.plan_next_cycle', { cycle: active.value.name, goals: carry.value }))
  if (res) {
    toast.success(`${res.title} is planned, starting ${long(res.start_date, true)}.`)
    planOpen.value = false
    area.value = ''
    load()
  }
}
function openClose() {
  outcomes.value = active.value.goals.map((g) => ({ goal: g.name, title: g.title, percent: g.percent, outcome: g.outcome === 'In Progress' ? (g.percent >= d.value.target ? 'Achieved' : 'Partly Achieved') : g.outcome, result_note: g.result_note || '' }))
  closeOpen.value = true
}
async function closeCycle() {
  const res = await tryCall(() => api('journal.close_cycle', { cycle: active.value.name, outcomes: outcomes.value }))
  if (res) {
    toast.success(`Cycle closed with a final score of ${Math.round(res.final_score)}%.`)
    closeOpen.value = false
    area.value = ''
    load()
  }
}
onMounted(() => {
  emit('sub', 'Every goal, across every 12 Week Year')
  load()
})
</script>
<style scoped>
.gr { display: grid; grid-template-columns: minmax(230px, 2fr) 150px 80px minmax(170px, 1.2fr) 130px; gap: 0 12px; align-items: center; padding: 10px 16px; border-top: 1px solid var(--outline-gray-1); }
.gr.hdr { border-top: 0; background: var(--surface-gray-1); font-size: 12px; color: var(--ink-gray-6); padding: 8px 16px; }
.cy { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 16px; border-top: 1px solid var(--outline-gray-1); background: var(--surface-gray-1); }
.cy b { font-weight: 600; }
.pg { display: flex; align-items: center; gap: 8px; }
.pg span { width: 36px; text-align: right; font-variant-numeric: tabular-nums; }
</style>
