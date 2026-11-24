<template>
  <template v-if="d">
    <div class="flex flex-wrap items-center gap-2"><Badge :theme="info?.goal.on_hold && d.goal.outcome === 'In Progress' ? 'amber' : d.goal.outcome === 'In Progress' ? 'blue' : 'gray'"
      :label="info?.goal.on_hold && d.goal.outcome === 'In Progress' ? 'On hold' : d.goal.outcome" />
      <span class="text-sm text-ink-gray-6">{{ headline }}</span>
      <Button v-if="writable && info && !info.goal.is_archived" class="ml-auto" size="sm" icon-left="lucide-pencil" label="Edit" data-pane-goal-edit @click="editOpen = true" /></div>
    <!-- what this goal serves and what serves it (UX fixes, set 6) -->
    <div v-if="info" class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6" data-pane-serves>
      <span>Serves</span>
      <Pick :model-value="info.goal.serves || null" :options="servesOptions" placeholder="Choose a longer goal" :disabled="!writable" @update:model-value="saveServes" />
      <span v-if="info.serves" class="tabular-nums" data-pane-serves-progress>{{ info.serves.progress.label }}</span>
    </div>
    <div v-if="info?.served_by.length" class="flex flex-col gap-1" data-pane-served-by-list>
      <span class="text-sm text-ink-gray-6">Served by</span>
      <div v-for="s in info.served_by" :key="s.name" class="flex min-w-0 items-center gap-2">
        <Button class="min-w-0" size="sm" variant="ghost" :label="s.title" data-pane-served-by @click="openRef('goal:' + s.name)" />
        <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-6">{{ [s.horizon === '12 weeks' ? s.cycle_title || '12 weeks' : s.horizon, s.progress.label].join(' · ') }}</span>
        <div class="w-14 shrink-0"><Progress size="sm" :value="Math.round(s.progress.percent || 0)" /></div>
      </div>
    </div>
    <GoalMeasure v-if="info" :g="info.goal" :readings="info.readings" :suggested="info.suggested" :space="info.space" :writable="writable && !info.goal.is_archived"
      data-pane-measure @changed="async () => { await load(); emit('changed') }" />
    <div v-if="writable && !d.cycle" class="flex flex-wrap items-center gap-2" data-goal-actions>
      <Button v-if="d.goal.outcome === 'In Progress' && d.horizon === 'Long term'" :label="info?.goal.on_hold ? 'Resume' : 'Put on hold'" data-goal-hold
        @click="setStatus(info?.goal.on_hold ? 'Active' : 'On Hold')" />
      <Button v-if="d.goal.outcome === 'In Progress'" label="Close goal" data-close-goal @click="closeOpen = true" />
      <Button v-else label="Reopen" @click="reopen" />
      <Button v-if="d.goal.outcome === 'In Progress' && d.cycles.length" label="Add to a 12 Week Year" data-add-to-cycle @click="moveOpen = true" />
    </div>
    <template v-if="on('actions')">
      <section v-if="d.goal.result_note"><SectionHead>Result</SectionHead><Card class="text-base text-ink-gray-8">{{ d.goal.result_note }}</Card></section>
      <section><SectionHead>Actions</SectionHead>
        <Card flush><Row v-for="a in d.goal.actions" :key="a.name">
          <div class="min-w-0 flex-1"><div class="break-words text-base-medium" :class="a.status !== 'Open' ? 'text-ink-gray-6 line-through' : 'text-ink-gray-9'">{{ a.title }}</div>
            <div class="text-sm text-ink-gray-6">{{ a.per_week }} a week · {{ plural(Object.values(a.ticks).reduce((x, y) => x + y, 0), 'tick') }} so far</div></div>
          <Badge v-if="a.status !== 'Open'" :theme="a.status === 'Done' ? 'green' : 'gray'" :label="a.status" /></Row>
          <Empty v-if="!d.goal.actions.length" title="No actions." hint="Edit the goal under Cycle goals on Goals > Cycles to add weekly actions." /></Card>
      </section>
    </template>
    <section v-if="on('tasks')" class="flex flex-col gap-3">
      <Card v-if="!d.cycle && d.goal.result_note" class="text-base text-ink-gray-8">{{ d.goal.result_note }}</Card>
      <div class="flex items-center gap-2.5" data-goal-figure>
        <template v-if="d.tasks_counted"><div class="min-w-0 flex-1"><Progress size="sm" :value="Math.round((100 * d.tasks_done) / d.tasks_counted)" /></div>
          <span class="text-sm tabular-nums text-ink-gray-8">{{ d.tasks_done }} of {{ d.tasks_counted }} tasks</span></template>
        <span v-else class="text-sm text-ink-gray-6">No tasks yet</span>
        <CountLink class="ml-auto text-sm" :to="{ path: '/goals/tasks', query: { goal: d.goal.name, status: 'all', view: 'list' } }" data-door="goal-tasks">Open in Tasks</CountLink>
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

    <GoalEditDialog v-if="info && writable" v-model="editOpen" :goal="info.goal" :weekly-actions="d.goal.actions || []" :space="info.space" @saved="async () => { await load(); emit('changed') }" />
    <Dialog v-model:open="closeOpen" title="Close goal" size="sm" :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Close goal', variant: 'solid', onClick: closeGoal }]">
      <div class="flex flex-col gap-3">
        <Select v-model="outcome" :options="OUTCOMES" aria-label="Outcome" data-goal-outcome />
        <Textarea v-model="note" :rows="3" placeholder="Result note (optional)" aria-label="Result note" />
      </div>
    </Dialog>
    <Dialog v-model:open="moveOpen" title="Add to a 12 Week Year" size="sm" :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Add', variant: 'solid', onClick: moveToCycle }]">
      <div class="flex flex-col gap-2">
        <Select v-model="cycle" :options="d.cycles.map((c) => ({ label: `${c.title} (${c.status.toLowerCase()})`, value: c.name }))" aria-label="Cycle" data-goal-cycle />
        <p class="text-sm text-ink-gray-6">It becomes a 12 Week Year goal in that cycle and keeps its tasks. Add its weekly actions under Cycle goals on Goals > Cycles.</p>
      </div>
    </Dialog>
  </template>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Dialog, Progress, Select, TextInput, Textarea, toast } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import Row from '@/components/ui/Row.vue'
import CountLink from '@/components/ui/CountLink.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
import Empty from '@/components/Empty.vue'
import Backlinks from '@/components/Backlinks.vue'
import Pick from '@/components/Pick.vue'
import GoalMeasure from '@/components/goals/GoalMeasure.vue'
import GoalEditDialog from '@/components/goals/GoalEditDialog.vue'
import { tryCall } from '@/lib/api'
import { itemData } from '@/data/item'
import { loadBacklinks } from '@/lib/links'
import { canWrite, store } from '@/lib/store'
import { short } from '@/lib/dates'
import { plural } from '@/lib/plural'
import { loadLookups, lookups, parentOptions } from '@/lib/lookups'
import { openRef } from '@/lib/pane'

const OUTCOMES = ['Achieved', 'Partly Achieved', 'Not Achieved', 'Dropped']
const props = defineProps({ name: String, type: String, tab: String })
const emit = defineEmits(['meta', 'missing', 'changed', 'close'])
// The pane's tabs: Actions (with the result note at the top), Tasks, History across cycles, Links. Annual and open goals
// have no weekly actions and no cycles, so they have Tasks and Links only.
const on = (t) => !props.tab || props.tab === t
const d = ref(null)
const info = ref(null) // goals.get: serves, served by, on hold, done when
const links = ref([])
const quick = ref('')
const closeOpen = ref(false)
const editOpen = ref(false)
const moveOpen = ref(false)
const outcome = ref('Achieved')
const note = ref('')
const cycle = ref('')
const writable = computed(() => store.spaces.find((s) => s.name === d.value?.space)?.access === 'Write' && !store.isAgent)
const headline = computed(() => {
  const x = d.value
  if (x.cycle) return `${x.cycle.title} · ${Math.round(x.goal.percent)}% of ticks done`
  return [x.horizon + ' goal', x.target_date && 'by ' + short(x.target_date, true), x.closed_on && 'closed ' + short(x.closed_on, true)].filter(Boolean).join(' · ')
})
async function load() {
  try {
    ;[d.value, links.value, info.value] = await Promise.all([itemData.goals.detail({ goal: props.name }), loadBacklinks('Life Goal', props.name),
      itemData.goals.get({ goal: props.name })])
    loadLookups()
    const x = d.value
    const g = x.goal
    if (x.cycles?.length && !cycle.value) cycle.value = x.cycles[0].name
    const tabs = x.cycle
      ? [{ value: 'actions', label: 'Actions', count: g.actions.length, noun: 'actions' }, { value: 'tasks', label: 'Tasks', count: x.tasks.length, noun: 'tasks' },
          { value: 'history', label: 'History across cycles', count: x.history.length, noun: 'cycles' }]
      : [{ value: 'tasks', label: 'Tasks', count: x.tasks.length, noun: 'tasks' }]
    emit('meta', { title: g.title, area: g.area, area_name: g.area_name, fullPage: `/goals/${g.name}`,
      sub: x.is_someday ? 'On the Someday list' : x.cycle ? `${g.actions.length} action${g.actions.length === 1 ? '' : 's'}` : x.horizon + ' goal',
      someday: canWrite() && g.outcome === 'In Progress' && !x.is_someday ? { doctype: 'Life Goal', name: g.name } : null,
      tabs: [...tabs, { value: 'links', label: 'Links', count: links.value.length, noun: 'linked records' }] })
  } catch (e) {
    emit('missing')
  }
}
const servesOptions = computed(() => [{ label: 'None', value: '' },
  ...parentOptions({ name: props.name, horizon: info.value?.goal.horizon }),
  ...(info.value?.goal.serves && !(lookups.goals || []).some((x) => x.name === info.value.goal.serves) ? [{ label: info.value.goal.serves_title, value: info.value.goal.serves }] : [])])
async function saveServes(v) {
  if (await tryCall(() => itemData.goals.update({ goal: props.name, values: { serves: v || null } }))) { await load(); emit('changed') }
}
async function setStatus(status) {
  if (await tryCall(() => itemData.goals.set_status({ goal: props.name, status }), status === 'On Hold' ? 'On hold' : 'Resumed')) { await load(); emit('changed') }
}
async function addTask() {
  const text = quick.value.trim()
  if (!text) return
  quick.value = ''
  if (await tryCall(() => itemData.tasks.quick_add({ text, space: d.value.space, area: d.value.goal.area || undefined, goal: d.value.goal.name }))) {
    await load()
    emit('changed')
  } else quick.value = text
}
async function closeGoal() {
  closeOpen.value = false
  if (await tryCall(() => itemData.goals.close({ goal: props.name, outcome: outcome.value, result_note: note.value }), 'Goal closed')) { await load(); emit('changed') }
}
async function reopen() {
  if (await tryCall(() => itemData.goals.close({ goal: props.name, outcome: 'In Progress' }), 'Reopened')) { await load(); emit('changed') }
}
async function moveToCycle() {
  moveOpen.value = false
  if (await tryCall(() => itemData.goals.add_to_cycle({ goal: props.name, cycle: cycle.value }), 'Added to the 12 Week Year')) {
    toast.info('Add its weekly actions on the 12 Week Year grid.')
    await load()
    emit('changed')
  }
}
onMounted(load)
</script>
