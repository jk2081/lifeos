<template>
  <ListView ref="list" title="Goals" noun="goals" screen="goals" doctype="Life Goal" :spec="SPEC" :tabs="TABS" :quick="['goal_type', 'area', 'cycle']"
    :synthetic="SYNTHETIC" :hidden="HIDDEN" :fetch="fetch" :row-ref="(r) => 'goal:' + r.name" :watch-keys="['by']"
    :empty-title="EMPTY[tab] || 'No goals here.'" empty-hint="A goal can sit in a 12 Week cycle, have a year-end date, or be open-ended. Projects are open-ended goals with tasks. Add one with New goal."
    @loaded="(res) => (line = res.summary_line || line)">
    <template #sub><span data-goals-sub>{{ line ? `${line.in_progress} in progress · ${line.tasks_done} of ${line.tasks_counted} tasks done across the goals shown` : store.space }}</span></template>
    <template #actions><Button v-if="canWrite()" variant="solid" icon-left="lucide-plus" label="New goal" data-new-goal @click="newOpen = true" /></template>
    <template #bar>
      <Select class="w-44" :model-value="route.query.by === 'completion' ? 'completion' : ''" :options="ORDERS" aria-label="Order" data-goal-order
        @update:model-value="(v) => router.push({ query: { ...route.query, by: v || undefined } })" />
    </template>
    <template #cell-title="{ row }"><div class="min-w-0"><div class="break-words font-medium text-ink-gray-9">{{ row.title }}</div>
      <div v-if="row.serves_title" class="truncate text-sm text-ink-gray-6" data-goal-serves-line>Serves {{ row.serves_title }}</div></div></template>
    <template #cell-goal_type="{ row }"><Badge :theme="row.goal_type === '12 Week Year' ? 'blue' : 'gray'" :label="row.goal_type" /></template>
    <template #cell-area="{ row }"><RouterLink v-if="row.area" class="relative truncate text-ink-blue-8 hover:underline" :to="{ query: { ...route.query, area: row.area, open: undefined } }"
      :title="'Focus on ' + row.area_name">{{ row.area_name }}</RouterLink></template>
    <template #cell-_when="{ row }"><span class="truncate">{{ when(row) }}</span></template>
    <template #cell-_tasks="{ row }"><GoalTasks :row="row" /></template>
    <template #cell-_score="{ row }"><span class="tabular-nums" data-goal-score>{{ row.score === null || row.score === undefined ? '' : Math.round(row.score) + '%' }}</span></template>
    <template #cell-_outcome="{ row }"><Badge :theme="row.on_hold && row.outcome === 'In Progress' ? 'amber' : OUTCOME_THEME[row.outcome] || 'gray'"
      :label="row.outcome === 'In Progress' ? (row.on_hold ? 'On hold' : 'In progress') : row.outcome" /></template>
    <template #stack="{ row }">
      <div class="flex flex-col gap-1">
        <div class="flex items-start gap-2"><div class="min-w-0 flex-1 break-words text-base-medium text-ink-gray-9">{{ row.title }}</div>
          <span v-if="row.score !== null && row.score !== undefined" class="text-sm tabular-nums text-ink-gray-8">{{ Math.round(row.score) }}%</span></div>
        <div class="text-sm text-ink-gray-6">{{ [row.area_name, row.goal_type, when(row), row.on_hold && row.outcome === 'In Progress' ? 'on hold' : '', row.serves_title && 'serves ' + row.serves_title].filter(Boolean).join(' · ') }}</div>
        <GoalTasks :row="row" />
      </div>
    </template>
  </ListView>
  <NewRecord v-model="newOpen" title="New goal" action="Add goal" :fields="fields" :initial="{ goal_type: 'Open' }" :save="create" @saved="list?.reload()" />
</template>
<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, Button, Progress, Select } from 'frappe-ui'
import ListView from '@/components/ListView.vue'
import NewRecord from '@/components/NewRecord.vue'
import { api } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { areaOptions, loadLookups, lookups } from '@/lib/lookups'
import { openRef } from '@/lib/pane'
import { askScope } from '@/lib/ask'

// The state tabs, on status=: In progress (default), Achieved, Closed (Partly Achieved, Not Achieved, Carried, Dropped), All
const TABS = { key: 'status', field: 'outcome', label: 'Goal state', items: [{ value: 'in_progress', label: 'In progress' }, { value: 'achieved', label: 'Achieved' },
  { value: 'closed', label: 'Closed' }, { value: 'someday', label: 'Someday' }, { value: 'all', label: 'All' }] }
const EMPTY = { in_progress: 'No goals in progress.', achieved: 'No achieved goals.', closed: 'No closed goals.' }
const SPEC = [{ key: 'status', field: 'outcome', kind: 'value' }, { key: 'type', field: 'goal_type', kind: 'value', label: 'Type' }, { key: 'area', field: 'area', kind: 'link' },
  { key: 'cycle', field: 'cycle', kind: 'link' }, { key: 'serves', field: 'serves', kind: 'link' },
  { key: 'target_from', field: 'target_date', kind: 'from' }, { key: 'target_to', field: 'target_date', kind: 'to' }]
const SYNTHETIC = [{ key: '_when', label: 'When', width: '10rem', place: 'end' }, { key: '_tasks', label: 'Tasks', width: '12rem', place: 'end' },
  { key: '_score', label: 'Score', width: '5rem', align: 'right', place: 'end' }, { key: '_outcome', label: 'Outcome', width: '9rem', place: 'end' }]
const HIDDEN = ['actions', 'sort_order', 'final_score', 'carried_from', 'result_note', 'notes_md', 'archived_on', 'completed_on']
const ORDERS = [{ label: 'Default order', value: '' }, { label: 'Task completion', value: 'completion' }]
const OUTCOME_THEME = { 'In Progress': 'blue', Achieved: 'green', 'Partly Achieved': 'amber', 'Not Achieved': 'red' }
const route = useRoute()
const router = useRouter()
const list = ref(null)
const line = ref(null)
const newOpen = ref(false)
const tab = computed(() => list.value?.tab || 'in_progress')
const when = (r) => (r.goal_type === '12 Week Year' ? r.cycle_title : r.target_date ? 'by ' + short(r.target_date, true) : '')

// "6 of 10 tasks" with a bar, or "No tasks yet". The figure opens the Tasks screen filtered to the goal.
const GoalTasks = (props) => {
  const r = props.row
  if (!r.tasks_counted) return h('span', { class: 'text-sm text-ink-gray-6', 'data-goal-tasks': '' }, 'No tasks yet')
  return h('div', { class: 'flex min-w-0 items-center gap-2', 'data-goal-tasks': '' }, [
    h('div', { class: 'w-16 shrink-0' }, h(Progress, { size: 'sm', value: Math.round((100 * r.tasks_done) / r.tasks_counted) })),
    h('span', { class: 'truncate text-sm tabular-nums text-ink-gray-8' }, `${r.tasks_done} of ${r.tasks_counted} tasks`),
  ])
}
GoalTasks.props = ['row']

const cycles = ref([])
const fields = computed(() => [
  { name: 'title', label: 'Goal', required: true },
  { name: 'goal_type', label: 'Type', required: true, options: ['Open', 'Annual', '12 Week Year'] },
  { name: 'area', label: 'Area', options: areaOptions() },
  { name: 'done_when', label: 'Done when (optional)', help: 'What will be true when this goal is reached.' },
  { name: 'serves', label: 'Serves (optional)', options: (lookups.goals || []).map((g) => ({ label: `${g.goal_type} · ${g.title}`, value: g.name })), help: 'The longer goal this goal serves.' },
  { name: 'target_date', label: 'Target date', type: 'date', help: 'Needed for an annual goal.' },
  { name: 'cycle', label: '12 Week Year (for that type only)', options: cycles.value.map((c) => ({ label: `${c.title} (${c.status.toLowerCase()})`, value: c.name })) },
])
async function create(v) {
  const g = await api('goals.create', { space: store.space, ...v, cycle: v.goal_type === '12 Week Year' ? v.cycle : undefined })
  openRef('goal:' + g.name)
}
async function fetch({ params: p, tab: t, filters, order_by, summary, start, page_length }) {
  const res = await api('goals.list', { space: store.space, state: t, goal_type: p.type, area: p.area, cycle: p.cycle, serves: p.serves, target_from: p.target_from, target_to: p.target_to,
    filters, order_by: route.query.by === 'completion' ? 'completion desc' : order_by, summary, start, page_length })
  return summary ? res : { rows: res.goals, total: res.total, tabs: res.tabs, summary_line: res.summary_line }
}
onMounted(async () => {
  loadLookups()
  cycles.value = (await api('goals.cycles', { space: store.space })) || []
})
askScope({ kind: 'goals', label: 'All goals' })
</script>
