<template>
  <Teleport to="#jr-actions">
    <Button label="All goals" icon-right="lucide-arrow-right" :route="{ path: '/goals', query: { status: 'all' } }" data-all-goals />
    <template v-if="active && canWrite()">
      <Button v-if="active.past_end" label="Close cycle" @click="openClose" />
      <Button label="Plan next cycle" @click="openPlan" />
      <Button variant="solid" label="Add goal" @click="goalOpen = true" />
    </template>
  </Teleport>
  <div class="page-body">
    <div v-if="d && d.areas.length" class="scroll-x">
      <TabButtons :model-value="area || ALL" :options="[{ label: 'All areas', value: ALL }, ...d.areas.map((a) => ({ label: a.area_name, value: a.name }))]"
        @update:model-value="(v) => setArea(v === ALL ? '' : v)" />
    </div>
    <div v-if="d && d.cycles.length" class="overflow-hidden rounded-5 border border-outline-gray-2"><div class="scroll-x"><div class="min-w-[720px]">
      <div class="gr bg-surface-gray-1 px-4 py-2 text-xs text-ink-gray-6"><div>Goal</div><div>Area</div><div>Actions</div><div>Ticks done</div><div>Outcome</div></div>
      <template v-for="c in d.cycles" :key="c.name">
        <div class="flex flex-wrap items-center gap-2.5 border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-3">
          <b class="font-semibold text-ink-gray-9">{{ c.title }}</b>
          <Badge :theme="c.status === 'Active' ? 'blue' : 'gray'" :label="c.status === 'Active' ? (c.current_week ? `Active · week ${c.current_week}` : 'Active') : c.status" />
          <span class="text-sm text-ink-gray-6">{{ cycleNote(c) }}</span>
          <Button class="ml-auto" variant="ghost" size="sm" label="Open grid" :route="`/journal?cycle=${c.name}`" />
        </div>
        <div v-for="g in c.goals" :key="g.name" class="gr border-t border-outline-gray-1 px-4 py-2.5">
          <div><RouterLink class="font-medium text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="`/journal/goals/${g.name}`">{{ g.title }}</RouterLink>
            <div v-if="goalNote(g, c)" class="text-sm text-ink-gray-6">{{ goalNote(g, c) }}</div></div>
          <div><Badge v-if="g.area_name" :label="g.area_name" /></div>
          <div>{{ g.actions }}</div>
          <div v-if="c.status === 'Planned'" class="text-sm text-ink-gray-6">Not started</div>
          <div v-else><div class="flex items-center gap-2"><div class="min-w-0 flex-1"><Progress size="sm" :value="Math.round(g.percent)" /></div><span class="w-9 text-right tabular-nums">{{ Math.round(g.percent) }}%</span></div>
            <div class="text-sm text-ink-gray-6" data-goal-tasks>{{ g.tasks_counted ? `${g.tasks_done} of ${g.tasks_counted} tasks` : 'No tasks yet' }}</div></div>
          <div><Badge :theme="OUTCOME[c.status === 'Planned' ? 'Draft' : g.outcome]" :label="c.status === 'Planned' ? 'Draft' : g.outcome === 'In Progress' ? 'In progress' : g.outcome" /></div>
        </div>
        <div v-if="!c.goals.length" class="border-t border-outline-gray-1 px-4 py-2.5 text-sm text-ink-gray-6">No goals{{ area ? ' in this area' : '' }} in this cycle.</div>
      </template>
    </div></div></div>
    <Card v-else-if="d"><Empty title="No goals yet." hint="Goals belong to a 12 Week Year. Open the 12 Week Year tab to start a cycle and add goals." /></Card>
  </div>

  <GoalDialog v-model="goalOpen" :cycle="active && active.name" :goal="null" @saved="load" />

  <Dialog v-model:open="planOpen" title="Plan next cycle" size="lg" :actions="[{ label: 'Cancel', onClick: ({ close }) => close() },
    { label: carry.length ? `Carry ${carry.length} goal${carry.length === 1 ? '' : 's'}` : 'Create the next cycle', variant: 'solid', onClick: plan }]">
    <p class="mb-2.5 text-sm text-ink-gray-6">The next cycle starts the Monday after {{ active && long(active.end_date) }}. Pick the goals to carry. Each is copied with its open actions.</p>
    <Row v-for="g in (active ? active.goals : [])" :key="g.name" class="!items-center">
      <Checkbox :model-value="carry.includes(g.name)" :disabled="g.outcome === 'Carried'" @update:model-value="(v) => setCarry(g.name, v)">
        <template #label>{{ g.title }} <span class="text-sm text-ink-gray-6">{{ g.outcome === 'Carried' ? '· already carried' : `· ${Math.round(g.percent)}%` }}</span></template>
      </Checkbox>
    </Row>
  </Dialog>

  <Dialog v-model:open="closeOpen" title="Close cycle" size="2xl" :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Close cycle', variant: 'solid', onClick: closeCycle }]">
    <p class="mb-2.5 text-sm text-ink-gray-6">Give each goal an outcome and a note. The final score is stored and the cycle becomes read-only.</p>
    <Row v-for="o in outcomes" :key="o.goal" class="flex-wrap !items-center">
      <div class="flex-[1_1_180px] font-medium text-ink-gray-9">{{ o.title }} <span class="text-sm font-normal text-ink-gray-6">{{ Math.round(o.percent) }}%</span></div>
      <Select v-model="o.outcome" class="w-44" :options="OUTCOMES" :aria-label="`Outcome for ${o.title}`" />
      <TextInput v-model="o.result_note" class="flex-[2_1_200px]" placeholder="Note" :aria-label="`Note for ${o.title}`" />
    </Row>
  </Dialog>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Checkbox, Dialog, Progress, Select, TabButtons, TextInput, toast } from 'frappe-ui'
import Empty from '@/components/Empty.vue'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import GoalDialog from './GoalDialog.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { long } from '@/lib/dates'

const emit = defineEmits(['sub'])
const OUTCOME = { 'In Progress': 'blue', Achieved: 'green', 'Partly Achieved': 'green', 'Not Achieved': 'red', Carried: 'amber', Dropped: 'red', Draft: 'gray' }
const OUTCOMES = ['Achieved', 'Partly Achieved', 'Not Achieved', 'Carried', 'Dropped']
const ALL = '__all__' // the "All areas" choice of the area switch
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
  if (g.serves_title) return `Serves ${g.serves_title}`
  if (g.actions_done) return `${g.actions_done} of ${g.actions} actions finished`
  return c.status === 'Closed' ? g.result_note : ''
}
async function load() {
  const res = await tryCall(() => api('journal.goals', { space: store.space, area: area.value || store.lensArea || undefined }))
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
function setCarry(name, on) {
  carry.value = on ? [...carry.value.filter((x) => x !== name), name] : carry.value.filter((x) => x !== name)
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
/* geometry only: the five columns of the goals table */
.gr { display: grid; grid-template-columns: minmax(230px, 2fr) 150px 80px minmax(170px, 1.2fr) 130px; gap: 0 12px; align-items: center; }
</style>
