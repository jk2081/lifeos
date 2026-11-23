<template>
  <Dialog v-model:open="open" title="New goal" size="lg" data-new-goal-dialog
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Add goal', variant: 'solid', loading: busy, onClick: submit }]">
    <div class="flex flex-col gap-3">
      <FormControl v-model="v.title" label="Goal" required placeholder="For example: Ghillidary yield to 1,800 kg/ha" data-goal-title />
      <div class="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <DatePicker v-model="v.target_date" format="D MMM YYYY" clearable label="Target date" :description="dateHelp" @update:model-value="suggest" />
        <FormControl v-model="v.horizon" type="select" label="Horizon" :options="HORIZONS" data-goal-horizon @update:model-value="horizonChosen" />
      </div>
      <div class="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <FormControl v-model="v.area" type="select" label="Area" :required="areaRequired" placeholder="Choose" :options="areaOptions()" @update:model-value="suggestServes" />
        <FormControl v-if="v.horizon === '12 weeks' && !quarters" v-model="v.cycle" type="select" label="12 Week Year" placeholder="Choose"
          :options="cycles.map((c) => ({ label: `${c.title} (${c.status.toLowerCase()})`, value: c.name }))" />
      </div>
      <DoneWhen :model-value="m" :title="v.title" :space="store.space" @habit="toHabit" />
      <FormControl v-model="v.serves" type="select" label="Serves (optional)" placeholder="None" data-goal-serves
        :description="parentHorizon ? `A ${parentHorizon.toLowerCase()} goal is suggested first.` : 'The longer goal this goal serves.'" :options="parentOptions" />
    </div>
  </Dialog>
</template>
<script setup>
// New goal: title, target date, the horizon the date suggests (Year, 12 weeks or Month; changeable), area, "Done when…"
// (a finish line or a number, with Suggest and the habit check), and the goal it serves, one horizon up. Used by Plan > Goals and the New menu.
import { computed, reactive, ref, watch } from 'vue'
import { DatePicker, Dialog, FormControl, toast } from 'frappe-ui'
import DoneWhen from './DoneWhen.vue'
import { errorText, tryCall } from '@/lib/api'
import { goalsData } from '@/data/goals'
import { store } from '@/lib/store'
import { areaOptions, goalOptions, loadLookups, lookups } from '@/lib/lookups'
import { doneWhenRequired, emptyMeasure, makeHabit, measureArgs, measureProblem } from '@/lib/goals'

const props = defineProps({ modelValue: Boolean, areaRequired: Boolean, area: { type: String, default: '' }, horizon: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue', 'saved', 'habit'])
const HORIZONS = ['Year', '12 weeks', 'Month'] // Open (Long term) goals are retired (issue 57)
const UP = { Month: '12 weeks', '12 weeks': 'Year' }
const open = ref(false)
const busy = ref(false)
const quarters = ref(false)
const v = reactive({ title: '', horizon: 'Year', area: '', target_date: '', cycle: '', serves: '' })
const m = reactive(emptyMeasure())
const cycles = ref([])
const parentHorizon = computed(() => UP[v.horizon] || '')
const dateHelp = computed(() => (v.horizon === 'Year' || v.horizon === 'Month' ? 'Needed for this horizon.' : 'Optional.'))
const parentOptions = computed(() => {
  const all = (lookups.goals || []).filter((g) => g.horizon)
  const first = all.filter((g) => g.horizon === parentHorizon.value)
  return [{ label: 'None', value: '' }, ...goalOptions(first, { empty: null }), ...goalOptions(all.filter((g) => !first.includes(g)), { empty: null })]
})
async function suggest() {
  const res = await goalsData.goals.suggest_horizon({ space: store.space, target_date: v.target_date || undefined })
  quarters.value = res.quarters
  if (!props.horizon) v.horizon = res.horizon === 'Long term' ? 'Year' : res.horizon
  if (v.horizon === '12 weeks') pickCycle()
}
function horizonChosen() { v.serves = ''; if (v.horizon === '12 weeks') pickCycle(); suggestServes() }
// a 12 Week Year goal under a focus serves that focus's annual goal (issue 57)
async function suggestServes() {
  if (v.horizon !== '12 weeks' || !v.area || v.serves) return
  const annual = await tryCall(() => goalsData.focus.annual_for({ area: v.area }))
  if (annual && !v.serves) v.serves = annual.name
}
function pickCycle() { if (!v.cycle) v.cycle = cycles.value[0]?.name || '' }
watch(() => props.modelValue, async (o) => {
  open.value = o
  if (!o) return
  Object.assign(v, { title: '', horizon: props.horizon || 'Year', area: props.area || store.lensArea || '', target_date: '', cycle: '', serves: '' })
  Object.assign(m, emptyMeasure())
  loadLookups()
  cycles.value = (await goalsData.goals.cycles({ space: store.space })) || []
  quarters.value = (await goalsData.goals.suggest_horizon({ space: store.space })).quarters
}, { immediate: true })
watch(open, (o) => emit('update:modelValue', o))

async function submit() {
  if (busy.value) return
  const problem = !v.title.trim() ? 'Name the goal.' : props.areaRequired && !v.area ? 'Choose an area.' : measureProblem(m, doneWhenRequired())
  if (problem) return toast.error(problem)
  busy.value = true
  try {
    const g = await goalsData.goals.create({ space: store.space, title: v.title.trim(), horizon: v.horizon, area: v.area || undefined,
      target_date: v.target_date || undefined, cycle: v.horizon === '12 weeks' && !quarters.value ? v.cycle || undefined : undefined, serves: v.serves || undefined, ...measureArgs(m) })
    open.value = false
    await loadLookups(true)
    emit('saved', g)
  } catch (e) {
    toast.error(errorText(e))
  } finally {
    busy.value = false
  }
}
// "Make it a habit": the habit goes into this month's plan and no goal is created
async function toHabit(h) {
  try {
    const r = await makeHabit(h, { area: v.area })
    open.value = false
    emit('habit', r)
  } catch (e) {
    toast.error(errorText(e))
  }
}
</script>
