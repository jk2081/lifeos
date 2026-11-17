<template>
  <div class="flex flex-col gap-4" data-key-results>
    <section data-review-readings>
      <SectionHead :count="k.readings.length">Readings to confirm</SectionHead>
      <Card flush>
        <SuggestedReadings :rows="k.readings" with-goal :writable="canWrite()" @changed="emit('changed')" />
        <Empty v-if="!k.readings.length" title="No readings waiting." hint="Values the assistant or an agent reads from your captures and chats wait here for you to confirm." />
      </Card>
    </section>
    <section v-if="k.needs_finish_line.length" data-review-finish-lines>
      <SectionHead :count="k.needs_finish_line.length">Needs a finish line</SectionHead>
      <Card flush>
        <Row v-for="g in k.needs_finish_line" :key="g.name" class="!block" data-review-finish-line :data-goal="g.name">
          <div class="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <RouterLink class="break-words text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="`/plan/goals/${g.name}`">{{ g.title }}</RouterLink>
            <span class="text-sm text-ink-gray-6">{{ g.goal_type }} goal</span>
          </div>
          <DoneWhen :model-value="measure(g)" :title="g.title" :notes="g.notes_md" :disabled="!canWrite()" @habit="(h) => toHabit(g, h)" />
          <div v-if="canWrite()" class="mt-2 flex justify-end"><Button variant="solid" label="Save finish line" data-review-finish-save @click="saveLine(g)" /></div>
        </Row>
      </Card>
    </section>
    <section v-if="k.stale.length" data-review-stale>
      <SectionHead :count="k.stale.length">No reading for two weeks</SectionHead>
      <Card flush>
        <Row v-for="g in k.stale.filter((x) => !skipped.has(x.name))" :key="g.name" class="flex-wrap !items-end" data-review-stale-goal :data-goal="g.name">
          <div class="min-w-0 flex-[1_1_220px]">
            <div class="break-words text-base-medium text-ink-gray-9">Where is {{ g.measure }} now?</div>
            <div class="text-sm text-ink-gray-6">{{ g.title }} · {{ g.progress.label }}{{ g.last_reading_on ? ' · last read ' + short(g.last_reading_on, true) : '' }}</div>
          </div>
          <div v-if="canWrite()" class="flex flex-wrap items-end gap-2">
            <FormControl v-model="values[g.name]" class="w-32" type="number" :label="g.unit || 'Value'" data-review-stale-value />
            <Button label="Skip" @click="skipped.add(g.name)" /><Button variant="solid" label="Save" data-review-stale-save @click="addReading(g)" />
          </div>
        </Row>
      </Card>
    </section>
  </div>
</template>
<script setup>
// The weekly review's step 1 (set 7), after the score: readings to confirm (Confirm, Edit and confirm, Reject), goals that
// need a finish line (the "Done when…" choice inline), and number goals with no reading in two weeks ("Where is X now?").
import { reactive } from 'vue'
import { Button, FormControl, toast } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Row from '../ui/Row.vue'
import SectionHead from '../ui/SectionHead.vue'
import Empty from '../Empty.vue'
import DoneWhen from '../goals/DoneWhen.vue'
import SuggestedReadings from '../goals/SuggestedReadings.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite } from '@/lib/store'
import { short } from '@/lib/dates'
import { emptyMeasure, makeHabit, measureArgs, measureProblem } from '@/lib/goals'

const props = defineProps({ k: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const measures = reactive({})
const values = reactive({})
const skipped = reactive(new Set())
const measure = (g) => (measures[g.name] ||= reactive(emptyMeasure()))
async function saveLine(g) {
  const m = measure(g)
  const problem = measureProblem(m)
  if (problem) return toast.error(problem)
  const a = measureArgs(m)
  if (await tryCall(() => api('goals.update', { goal: g.name, values: a }), 'Finish line saved')) emit('changed')
}
async function addReading(g) {
  const v = values[g.name]
  if (v === '' || v === undefined || v === null) return toast.error('Type the value, or Skip.')
  if (await tryCall(() => api('goals.add_reading', { goal: g.name, value: v }), 'Reading added')) emit('changed')
}
async function toHabit(g, h) {
  if (await tryCall(() => makeHabit(h, { area: g.area }))) emit('changed')
}
</script>
