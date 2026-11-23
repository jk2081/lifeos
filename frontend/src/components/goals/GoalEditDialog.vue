<template>
  <Dialog v-model:open="open" title="Edit goal" size="lg" data-goal-edit-dialog
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Save goal', variant: 'solid', loading: busy, onClick: save }]">
    <div class="flex flex-col gap-3">
      <FormControl v-model="v.title" label="Goal" required data-edit-title />
      <div class="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <FormControl v-model="v.area" type="select" label="Area and part" placeholder="Choose" :options="areas" data-edit-area />
        <FormControl v-model="v.horizon" type="select" label="Type" :options="TYPES" data-edit-type @update:model-value="typeChosen" />
      </div>
      <div class="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <FormControl v-if="v.horizon === '12 weeks' && !quarters" v-model="v.cycle" type="select" label="12 Week Year" placeholder="Choose" :options="cycleOptions" data-edit-cycle />
        <DatePicker v-model="v.target_date" format="D MMM YYYY" clearable label="Target date" :description="v.horizon === 'Year' || v.horizon === 'Month' ? 'Needed for this type.' : 'Optional.'" />
      </div>
      <DoneWhen :model-value="m" :title="v.title" :goal="goal.name" :horizon="v.horizon" :space="space" no-habit />
      <FormControl v-model="v.serves" type="select" label="Serves (optional)" placeholder="None" :options="[{ label: 'None', value: '' }, ...parentOptions(goal)]" data-edit-serves />
      <div v-if="v.horizon === '12 weeks'" data-edit-actions>
        <div class="mb-1.5 text-sm text-ink-gray-6">Weekly actions, and how many times a week</div>
        <div v-for="(a, i) in actions" :key="a.key" class="mb-2 flex flex-wrap items-center gap-2" data-edit-action :data-retired="a.retired ? 1 : 0">
          <TextInput v-model="a.title" class="min-w-0 flex-1 max-sm:basis-full" :aria-label="`Action ${i + 1}`" placeholder="Action" :class="a.retired ? 'opacity-60' : ''" />
          <TextInput v-model.number="a.per_week" class="w-16" type="number" min="1" max="7" :aria-label="`Times a week for action ${i + 1}`" />
          <Button size="sm" variant="ghost" icon="lucide-arrow-up" label="Move up" :disabled="i === 0" @click="move(i, -1)" />
          <Button size="sm" variant="ghost" icon="lucide-arrow-down" label="Move down" :disabled="i === actions.length - 1" @click="move(i, 1)" />
          <Button v-if="a.name" size="sm" variant="outline" :label="a.retired ? 'Bring back' : 'Retire'" data-edit-retire @click="a.retired = !a.retired" />
          <Button v-else size="sm" variant="ghost" icon="lucide-x" label="Remove action" @click="actions.splice(i, 1)" />
        </div>
        <Button size="sm" variant="outline" icon-left="lucide-plus" label="action" data-edit-add-action @click="addAction" />
      </div>
    </div>
  </Dialog>
</template>
<script setup>
// Edit goal: one form for everything a person changes on a goal: title, area and part, type, cycle, target date, "Done when"
// (with Suggest), the goal it serves, and for a 12 Week Year goal its weekly actions (add, rename, retire, reorder). It saves
// through goals.edit, so a rename keeps every link and the cycle grid shows the same actions.
import { computed, reactive, ref, watch } from 'vue'
import { DatePicker, Dialog, FormControl, TextInput, Button, toast } from 'frappe-ui'
import DoneWhen from './DoneWhen.vue'
import { api, errorText } from '@/lib/api'
import { store } from '@/lib/store'
import { areaOptions, loadLookups, parentOptions } from '@/lib/lookups'
import { emptyMeasure, measureArgs, measureProblem } from '@/lib/goals'

// `goal` is the goals.get goal; `actions` the goal's weekly actions as goals.detail gives them
const props = defineProps({ modelValue: Boolean, goal: { type: Object, required: true }, weeklyActions: { type: Array, default: () => [] }, space: String })
const emit = defineEmits(['update:modelValue', 'saved'])
const BASE_TYPES = [{ label: '12 Week Year', value: '12 weeks' }, { label: 'Year', value: 'Year' }, { label: 'Month', value: 'Month' }]
// an Open goal keeps its type here until it is sorted; no goal can be made Open (issue 57)
const TYPES = computed(() => (v.horizon === 'Long term' ? [...BASE_TYPES, { label: 'Long term (open, to sort)', value: 'Long term' }] : BASE_TYPES))
const open = ref(false)
const busy = ref(false)
const quarters = ref(false)
const cycles = ref([])
const v = reactive({ title: '', area: '', horizon: 'Long term', cycle: '', target_date: '', serves: '' })
const m = reactive(emptyMeasure())
const actions = ref([])
let keys = 0
const areas = computed(() => {
  const list = areaOptions()
  return props.goal.area && !list.some((o) => o.value === props.goal.area) ? [...list, { value: props.goal.area, label: props.goal.area_name || props.goal.area }] : list
})
const cycleOptions = computed(() => {
  const list = cycles.value.map((c) => ({ label: `${c.title} (${c.status.toLowerCase()})`, value: c.name }))
  return props.goal.cycle && !list.some((o) => o.value === props.goal.cycle) ? [...list, { label: props.goal.cycle_title || props.goal.cycle, value: props.goal.cycle }] : list
})
watch(() => props.modelValue, async (o) => {
  open.value = o
  if (!o) return
  const g = props.goal
  Object.assign(v, { title: g.title, area: g.area || '', horizon: g.horizon, cycle: g.cycle || '', target_date: g.target_date || '', serves: g.serves || '' })
  Object.assign(m, emptyMeasure(g), g.measure_kind || !g.done_when ? {} : { measure_kind: 'Milestone' })
  actions.value = props.weeklyActions.map((a) => ({ key: keys++, name: a.name, title: a.title, per_week: a.per_week, retired: a.status === 'Dropped', status: a.status }))
  loadLookups()
  cycles.value = (await api('goals.cycles', { space: props.space || store.space })) || []
  quarters.value = (await api('goals.suggest_horizon', { space: props.space || store.space })).quarters
}, { immediate: true })
watch(open, (o) => emit('update:modelValue', o))

function typeChosen(t) {
  if (t === '12 weeks' && !v.cycle && !quarters.value) v.cycle = cycles.value[0]?.name || ''
  if (t !== '12 weeks') v.cycle = ''
}
const addAction = () => actions.value.push({ key: keys++, title: '', per_week: 3 })
function move(i, by) {
  const list = actions.value
  const [a] = list.splice(i, 1)
  list.splice(i + by, 0, a)
}
async function save() {
  if (busy.value) return
  if (!v.title.trim()) return toast.error('Name the goal.')
  // a goal that already lacks a finish line may be saved as it is; one that has a kind chosen must be complete
  const problem = measureProblem(m, !!m.measure_kind)
  if (problem) return toast.error(problem)
  const values = { title: v.title.trim(), area: v.area || null, horizon: v.horizon, cycle: v.horizon === '12 weeks' && !quarters.value ? v.cycle || null : null,
    target_date: v.target_date || null, serves: v.serves || null }
  if (m.measure_kind) {
    const a = measureArgs(m)
    Object.assign(values, { measure_kind: a.measure_kind, done_when: a.done_when ?? null, measure: a.measure ?? null, unit: a.unit ?? null,
      start_value: a.start_value ?? null, target_value: a.target_value ?? null })
  }
  busy.value = true
  try {
    const out = await api('goals.edit', { goal: props.goal.name, values, actions: v.horizon === '12 weeks' ? actions.value.map((a) => ({ name: a.name, title: a.title, per_week: a.per_week, retired: a.retired })) : undefined })
    open.value = false
    toast.success('Goal saved.')
    await loadLookups(true)
    emit('saved', out)
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}
</script>
