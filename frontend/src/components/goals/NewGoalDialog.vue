<template>
  <Dialog v-model:open="open" title="New goal" size="lg" data-new-goal-dialog
    :actions="[{ label: 'Cancel', onClick: ({ close }) => close() }, { label: 'Add goal', variant: 'solid', loading: busy, onClick: submit }]">
    <div class="flex flex-col gap-3">
      <FormControl v-model="v.title" label="Goal" required placeholder="For example: Ghillidary yield to 1,800 kg/ha" data-goal-title />
      <div class="grid grid-cols-2 gap-2 max-sm:grid-cols-1">
        <FormControl v-model="v.goal_type" type="select" label="Type" :options="typeOptions" />
        <FormControl v-model="v.area" type="select" label="Area" :required="areaRequired" placeholder="Choose" :options="areaOptions()" />
      </div>
      <FormControl v-if="v.goal_type === '12 Week Year'" v-model="v.cycle" type="select" label="12 Week Year" placeholder="Choose"
        :options="cycles.map((c) => ({ label: `${c.title} (${c.status.toLowerCase()})`, value: c.name }))" />
      <DatePicker v-if="v.goal_type === 'Annual' || v.goal_type === 'Open'" v-model="v.target_date" format="D MMM YYYY" clearable label="Target date"
        :description="v.goal_type === 'Annual' ? 'Needed for an annual goal.' : 'Optional.'" />
      <DoneWhen :model-value="m" :title="v.title" :space="store.space" @habit="toHabit" />
      <FormControl v-model="v.serves" type="select" label="Serves (optional)" placeholder="None" description="The longer goal this goal serves."
        :options="[{ label: 'None', value: '' }, ...goalOptions(lookups.goals || [], { empty: null })]" />
    </div>
  </Dialog>
</template>
<script setup>
// New goal (set 7): title, type, area, "Done when…" (a finish line or a number, with Suggest and the habit check), the goal
// it serves, and the target date or cycle its type needs. Used by Plan > Goals and the New menu.
import { computed, reactive, ref, watch } from 'vue'
import { DatePicker, Dialog, FormControl, toast } from 'frappe-ui'
import DoneWhen from './DoneWhen.vue'
import { api, errorText } from '@/lib/api'
import { store } from '@/lib/store'
import { areaOptions, goalOptions, loadLookups, lookups } from '@/lib/lookups'
import { emptyMeasure, makeHabit, measureArgs, measureProblem } from '@/lib/goals'

const props = defineProps({ modelValue: Boolean, types: { type: Array, default: () => ['Open', 'Annual', '12 Week Year'] }, areaRequired: Boolean, area: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue', 'saved', 'habit'])
const open = ref(false)
const busy = ref(false)
const v = reactive({ title: '', goal_type: 'Open', area: '', target_date: '', cycle: '', serves: '' })
const m = reactive(emptyMeasure())
const cycles = ref([])
const typeOptions = computed(() => props.types.map((t) => ({ label: t === 'Open' ? 'Open-ended' : t, value: t })))
watch(() => props.modelValue, async (o) => {
  open.value = o
  if (!o) return
  Object.assign(v, { title: '', goal_type: props.types[0], area: props.area || store.lensArea || '', target_date: '', cycle: '', serves: '' })
  Object.assign(m, emptyMeasure())
  loadLookups()
  if (props.types.includes('12 Week Year')) {
    cycles.value = (await api('goals.cycles', { space: store.space })) || []
    v.cycle = cycles.value[0]?.name || ''
  }
}, { immediate: true })
watch(open, (o) => emit('update:modelValue', o))

async function submit() {
  if (busy.value) return
  const problem = !v.title.trim() ? 'Name the goal.' : props.areaRequired && !v.area ? 'Choose an area.' : measureProblem(m)
  if (problem) return toast.error(problem)
  busy.value = true
  try {
    const g = await api('goals.create', { space: store.space, title: v.title.trim(), goal_type: v.goal_type, area: v.area || undefined,
      target_date: v.target_date || undefined, cycle: v.goal_type === '12 Week Year' ? v.cycle : undefined, serves: v.serves || undefined, ...measureArgs(m) })
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
