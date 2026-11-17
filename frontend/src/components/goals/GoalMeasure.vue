<template>
  <div class="flex flex-col gap-3" data-goal-measure :data-measure-kind="g.measure_kind || 'none'">
    <template v-if="!editing">
      <template v-if="g.measure_kind === 'Number'">
        <ResultBar :progress="g.progress" />
        <div v-if="g.progress.reached && writable && g.outcome === 'In Progress'" class="flex flex-wrap items-center gap-2" data-goal-reached>
          <Badge theme="green" label="Target reached" />
          <Button v-if="g.goal_type !== '12 Week Year'" variant="solid" label="Mark achieved" data-mark-achieved @click="markAchieved" />
          <span v-else class="text-sm text-ink-gray-6">It closes with its cycle.</span>
        </div>
        <ReadingChart v-if="readings.length > 1" :readings="readings" :start="g.start_value" :target="g.target_value" :unit="g.unit"
          :label="`${g.measure} over time, ${readings.length} readings`" />
        <div v-if="writable && g.outcome === 'In Progress'" class="flex flex-wrap items-end gap-2" data-add-reading>
          <FormControl v-model="add.value" class="w-32" type="number" :label="`${g.measure}${g.unit ? ' (' + g.unit + ')' : ''}`" data-add-reading-value />
          <DatePicker v-model="add.date" class="w-40" format="D MMM YYYY" label="On" />
          <Button label="Add reading" data-add-reading-save @click="addReading" />
        </div>
      </template>
      <div v-else-if="g.measure_kind === 'Milestone' || g.done_when" class="text-base text-ink-gray-8" data-goal-finish-line>
        <span class="text-sm text-ink-gray-6">Done when </span>{{ g.done_when }}</div>
      <Alert v-else theme="amber" title="Needs a finish line" description="Say how you will know this goal is done: a finish line or a number." data-needs-finish-line />
      <Button v-if="writable" class="self-start" size="sm" variant="ghost" icon-left="lucide-pencil" :label="g.measure_kind || g.done_when ? 'Change how it is measured' : 'Set the finish line'"
        data-measure-edit @click="startEdit" />
    </template>
    <template v-else>
      <DoneWhen :model-value="m" :title="g.title" :notes="g.notes_md" :space="space" @habit="toHabit" />
      <div class="flex justify-end gap-2"><Button label="Cancel" @click="editing = false" /><Button variant="solid" label="Save" data-measure-save @click="save" /></div>
    </template>
    <section v-if="g.measure_kind === 'Number' && suggested.length" class="flex flex-col gap-1.5" data-goal-suggested>
      <div class="text-sm-medium text-ink-gray-7">Suggested readings to confirm</div>
      <SuggestedReadings :rows="suggested.map((r) => ({ ...r, unit: g.unit }))" :writable="writable" @changed="emit('changed')" />
    </section>
  </div>
</template>
<script setup>
// A goal's key result (set 7), for the goal page and the goal pane: a number goal's result bar, the chart of its confirmed
// readings, the readings waiting to be confirmed, a reading added by hand and Mark achieved once the target is reached; a
// milestone goal's finish line; and the "Done when…" editor.
import { reactive, ref } from 'vue'
import { Alert, Badge, Button, DatePicker, FormControl, toast } from 'frappe-ui'
import DoneWhen from './DoneWhen.vue'
import ResultBar from './ResultBar.vue'
import ReadingChart from './ReadingChart.vue'
import SuggestedReadings from './SuggestedReadings.vue'
import { api, tryCall } from '@/lib/api'
import { store } from '@/lib/store'
import { emptyMeasure, makeHabit, measureArgs, measureProblem } from '@/lib/goals'

const props = defineProps({ g: { type: Object, required: true }, readings: { type: Array, default: () => [] }, suggested: { type: Array, default: () => [] },
  space: String, writable: Boolean })
const emit = defineEmits(['changed'])
const editing = ref(false)
const m = reactive(emptyMeasure())
const add = reactive({ value: '', date: store.today || '' })
function startEdit() {
  Object.assign(m, emptyMeasure(props.g))
  editing.value = true
}
async function save() {
  const problem = measureProblem(m)
  if (problem) return toast.error(problem)
  const a = measureArgs(m)
  const values = { measure_kind: a.measure_kind, done_when: a.done_when ?? props.g.done_when ?? null }
  if (a.measure_kind === 'Number') Object.assign(values, { measure: a.measure, unit: a.unit, start_value: a.start_value, target_value: a.target_value })
  if (await tryCall(() => api('goals.update', { goal: props.g.name, values }), 'Saved')) {
    editing.value = false
    emit('changed')
  }
}
async function addReading() {
  if (add.value === '' || add.value === null) return toast.error('Type the value.')
  if (await tryCall(() => api('goals.add_reading', { goal: props.g.name, value: add.value, date: add.date || undefined }), 'Reading added')) {
    add.value = ''
    emit('changed')
  }
}
async function markAchieved() {
  if (await tryCall(() => api('goals.close', { goal: props.g.name, outcome: 'Achieved', result_note: props.g.progress.label }), 'Marked achieved')) emit('changed')
}
async function toHabit(h) {
  if (await tryCall(() => makeHabit(h, { area: props.g.area, space: props.space }))) editing.value = false
}
</script>
