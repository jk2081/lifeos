<template>
  <template v-if="d">
    <div class="flex flex-wrap items-center gap-2"><Badge :theme="d.goal.outcome === 'In Progress' ? 'blue' : 'gray'" :label="d.goal.outcome" />
      <span class="text-sm text-ink-gray-6">{{ headline }}</span></div>
    <div v-if="writable && !d.cycle" class="flex flex-wrap items-center gap-2" data-goal-actions>
      <Button v-if="d.goal.outcome === 'In Progress'" label="Close goal" data-close-goal @click="closeOpen = true" />
      <Button v-else label="Reopen" @click="reopen" />
      <Button v-if="d.goal.outcome === 'In Progress' && d.cycles.length" label="Add to a 12 Week Year" data-add-to-cycle @click="moveOpen = true" />
    </div>
    <template v-if="on('actions')">
      <section v-if="d.goal.result_note"><SectionHead>Result</SectionHead><Card class="text-base text-ink-gray-8">{{ d.goal.result_note }}</Card></section>
      <section><SectionHead>Actions</SectionHead>
        <Card flush><Row v-for="a in d.goal.actions" :key="a.name">
          <div class="min-w-0 flex-1"><div class="break-words text-base-medium" :class="a.status !== 'Open' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ a.title }}</div>
            <div class="text-sm text-ink-gray-6">{{ a.per_week }} a week · {{ Object.values(a.ticks).reduce((x, y) => x + y, 0) }} ticks so far</div></div>
          <Badge v-if="a.status !== 'Open'" :theme="a.status === 'Done' ? 'green' : 'gray'" :label="a.status" /></Row>
          <Empty v-if="!d.goal.actions.length" title="No actions." hint="Edit the goal on the grid to add weekly actions." /></Card>
      </section>
    </template>
    <section v-if="on('tasks')" class="flex flex-col gap-3">
      <Card v-if="!d.cycle && d.goal.result_note" class="text-base text-ink-gray-8">{{ d.goal.result_note }}</Card>
      <div class="flex items-center gap-2.5" data-goal-figure>
        <template v-if="d.tasks_counted"><div class="min-w-0 flex-1"><Progress size="sm" :value="Math.round((100 * d.tasks_done) / d.tasks_counted)" /></div>
          <span class="text-sm tabular-nums text-ink-gray-8">{{ d.tasks_done }} of {{ d.tasks_counted }} tasks</span></template>
        <span v-else class="text-sm text-ink-gray-6">No tasks yet</span>
        <NumLink class="ml-auto text-sm" :to="{ path: '/tasks', query: { goal: d.goal.name, status: 'all', view: 'list' } }" data-door="goal-tasks">Open in Tasks</NumLink>
      </div>
      <Card flush>
        <Row v-for="t in d.tasks" :key="t.name" :pane="'task:' + t.name" :label="t.title"><div class="min-w-0 flex-1">
          <div class="break-words text-base-medium" :class="['Done', 'Dropped', 'Carried'].includes(t.status) ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ t.title }}</div>
          <div class="text-sm text-ink-gray-6">{{ t.status }}{{ t.due_date ? ' · due ' + short(t.due_date) : '' }}{{ t.is_archived ? ' · archived' : '' }}</div></div></Row>
        <Empty v-if="!d.tasks.length" title="No tasks for this goal." hint="Add one below, or file a task under this goal from its pane." />
        <Row v-if="writable && d.goal.outcome === 'In Progress'"><TextInput v-model="quick" class="flex-1" placeholder="Add a task under this goal" aria-label="Add a task under this goal"
          data-goal-quick @keydown.enter="addTask" /></Row>
      </Card>
    </section>
    <section v-if="on('history')">
      <Card flush><Row v-for="h in d.history" :key="h.name" class="!items-center" :pane="h.name !== d.goal.name ? 'goal:' + h.name : null" :label="h.cycle_title">
        <div class="min-w-0 flex-1"><div class="break-words text-base-medium text-ink-gray-9">{{ h.cycle_title }}</div><div class="text-sm text-ink-gray-6">{{ h.cycle_status }}{{ h.result_note ? ' · ' + h.result_note : '' }}</div></div>
        <span class="w-10 text-right tabular-nums text-ink-gray-8">{{ Math.round(h.score) }}%</span><Badge :label="h.outcome" /></Row></Card>
    </section>
    <Backlinks v-if="on('links')" tab doctype="Life Goal" :name="d.goal.name" :items="links" />

    <Dialog v-model:open="closeOpen" title="Close goal" size="sm" :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Close goal', variant: 'solid', onClick: closeGoal }]">
      <div class="flex flex-col gap-3">
        <Select v-model="outcome" :options="OUTCOMES" aria-label="Outcome" data-goal-outcome />
        <Textarea v-model="note" :rows="3" placeholder="Result note (optional)" aria-label="Result note" />
      </div>
    </Dialog>
    <Dialog v-model:open="moveOpen" title="Add to a 12 Week Year" size="sm" :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Add', variant: 'solid', onClick: moveToCycle }]">
      <div class="flex flex-col gap-2">
        <Select v-model="cycle" :options="d.cycles.map((c) => ({ label: `${c.title} (${c.status.toLowerCase()})`, value: c.name }))" aria-label="Cycle" data-goal-cycle />
        <p class="text-sm text-ink-gray-6">It becomes a 12 Week Year goal in that cycle and keeps its tasks. Add its weekly actions on the grid.</p>
      </div>
    </Dialog>
  </template>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Dialog, Progress, Select, TextInput, Textarea, toast } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import NumLink from '../ui/NumLink.vue'
import SectionHead from '../ui/SectionHead.vue'
import Empty from '../Empty.vue'
import Backlinks from '../Backlinks.vue'
import { api, tryCall } from '@/lib/api'
import { loadBacklinks } from '@/lib/links'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'

const OUTCOMES = ['Achieved', 'Partly Achieved', 'Not Achieved', 'Dropped']
const props = defineProps({ name: String, type: String, tab: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
// The pane's tabs: Actions (with the result note at the top), Tasks, History across cycles, Links. Annual and open goals
// have no weekly actions and no cycles, so they have Tasks and Links only.
const on = (t) => !props.tab || props.tab === t
const d = ref(null)
const links = ref([])
const quick = ref('')
const closeOpen = ref(false)
const moveOpen = ref(false)
const outcome = ref('Achieved')
const note = ref('')
const cycle = ref('')
const writable = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write' && !store.isAgent)
const headline = computed(() => {
  const x = d.value
  if (x.cycle) return `${x.cycle.title} · ${Math.round(x.goal.percent)}% of ticks done`
  return [x.goal_type + ' goal', x.target_date && 'by ' + short(x.target_date, true), x.closed_on && 'closed ' + short(x.closed_on, true)].filter(Boolean).join(' · ')
})
async function load() {
  try {
    ;[d.value, links.value] = await Promise.all([api('journal.goal', { goal: props.name }), loadBacklinks('Life Goal', props.name)])
    const x = d.value
    const g = x.goal
    if (x.cycles?.length && !cycle.value) cycle.value = x.cycles[0].name
    const tabs = x.cycle
      ? [{ value: 'actions', label: 'Actions', count: g.actions.length, noun: 'actions' }, { value: 'tasks', label: 'Tasks', count: x.tasks.length, noun: 'tasks' },
          { value: 'history', label: 'History across cycles', count: x.history.length, noun: 'cycles' }]
      : [{ value: 'tasks', label: 'Tasks', count: x.tasks.length, noun: 'tasks' }]
    emit('meta', { title: g.title, area: g.area, area_name: g.area_name, project: g.project, fullPage: `/journal/goals/${g.name}`,
      sub: x.is_someday ? 'On the Someday list' : x.cycle ? `${g.actions.length} action${g.actions.length === 1 ? '' : 's'}` : x.goal_type + ' goal',
      someday: canWrite() && g.outcome === 'In Progress' && !x.is_someday ? { doctype: 'Life Goal', name: g.name } : null,
      tabs: [...tabs, { value: 'links', label: 'Links', count: links.value.length, noun: 'linked records' }] })
  } catch (e) {
    emit('missing')
  }
}
async function addTask() {
  const text = quick.value.trim()
  if (!text) return
  quick.value = ''
  if (await tryCall(() => api('tasks.quick_add', { text, space: d.value.space, area: d.value.goal.area || undefined, goal: d.value.goal.name }))) {
    await load()
    emit('changed')
  } else quick.value = text
}
async function closeGoal() {
  closeOpen.value = false
  if (await tryCall(() => api('goals.close', { goal: props.name, outcome: outcome.value, result_note: note.value }), 'Goal closed')) { await load(); emit('changed') }
}
async function reopen() {
  if (await tryCall(() => api('goals.close', { goal: props.name, outcome: 'In Progress' }), 'Reopened')) { await load(); emit('changed') }
}
async function moveToCycle() {
  moveOpen.value = false
  if (await tryCall(() => api('goals.add_to_cycle', { goal: props.name, cycle: cycle.value }), 'Added to the 12 Week Year')) {
    toast.info('Add its weekly actions on the 12 Week Year grid.')
    await load()
    emit('changed')
  }
}
onMounted(load)
</script>
