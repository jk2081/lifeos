<template>
  <Dialog v-model:open="open" :title="`Cycle goals · ${grid.cycle.title}`" size="2xl">
    <div class="flex flex-col gap-3" data-cycle-goals-body>
      <p v-if="!writable" class="text-sm text-ink-gray-6">This cycle is read-only.</p>
      <div v-for="goal in grid.goals" :key="goal.name" class="rounded-5 border border-outline-gray-2 p-3" data-cg-goal>
        <div class="flex flex-wrap items-center gap-2">
          <RefLink class="min-w-0 flex-1 break-words text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="`goal:${goal.name}`">{{ goal.title }}</RefLink>
          <Badge v-if="goal.area_name" :label="goal.area_name" />
          <Button v-if="writable" size="sm" label="Edit" :aria-label="`Edit ${goal.title}`" @click="edit(goal)" />
        </div>
        <ul class="mt-2 flex flex-col gap-1">
          <li v-for="a in goal.actions" :key="a.name" class="flex items-center gap-2 text-sm" :class="a.status !== 'Open' && 'text-ink-gray-6 line-through'">
            <span class="min-w-0 flex-1 truncate">{{ a.title }} · {{ a.per_week }}/wk</span>
            <Dropdown v-if="writable" :options="menu(a)"><Button size="sm" variant="ghost" icon="lucide-ellipsis" :label="`Actions for ${a.title}`" /></Dropdown>
          </li>
          <li v-if="!goal.actions.length" class="text-sm text-ink-gray-6">No actions yet.</li>
        </ul>
      </div>
      <EmptyState line="No goals in this cycle yet. Add a goal with its weekly actions." v-if="!grid.goals.length" />
    </div>
    <template #actions><div class="flex flex-wrap justify-between gap-2">
      <div class="flex flex-wrap gap-2">
        <Button v-if="writable && grid.cycle.status === 'Planned'" label="Start this cycle" @click="start" />
        <Button label="Close the cycle or plan the next" :route="{ path: '/today/year', query: { view: 'goals' } }" />
      </div>
      <div class="flex gap-2"><Button label="Done" @click="open = false" /><Button v-if="writable" variant="solid" label="Add goal" data-cg-add @click="edit(null)" /></div></div></template>
  </Dialog>
  <GoalDialog v-model="goalOpen" :cycle="grid.cycle.name" :goal="editing" @saved="emit('changed')" />
</template>
<script setup>
import RefLink from '@/components/ui/RefLink.vue'
// "Cycle goals" on Goals > Cycles: the cycle's goals with their actions, for editing (the goal dialog, finishing or dropping an action).
import { ref } from 'vue'
import { Badge, Button, Dialog, Dropdown } from 'frappe-ui'
import EmptyState from '@/components/ui/EmptyState.vue'
import GoalDialog from '@/components/goals/GoalDialog.vue'
import { tryCall } from '@/lib/api'
import { goalsData } from '@/data/goals'

const open = defineModel({ type: Boolean })
const props = defineProps({ grid: Object, writable: Boolean })
const emit = defineEmits(['changed'])
const goalOpen = ref(false)
const editing = ref(null)
function edit(goal) {
  editing.value = goal
  goalOpen.value = true
}
function menu(a) {
  const set = (status) => async () => { if (await tryCall(() => goalsData.goals.set_action_status({ action: a.name, status }))) emit('changed') }
  const items = []
  if (a.status !== 'Done') items.push({ label: 'Finished for good', onClick: set('Done') })
  if (a.status !== 'Dropped') items.push({ label: 'Drop this action', onClick: set('Dropped') })
  if (a.status !== 'Open') items.push({ label: 'Open again', onClick: set('Open') })
  return items
}
async function start() {
  if (await tryCall(() => goalsData.goals.start_cycle({ cycle: props.grid.cycle.name }), 'Cycle started.')) emit('changed')
}
</script>
