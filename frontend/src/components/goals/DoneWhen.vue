<template>
  <div class="flex flex-col gap-3" data-done-when>
    <div class="flex flex-wrap items-center justify-between gap-2">
      <span class="text-sm text-ink-gray-6">Done when…<span v-if="by" class="text-ink-gray-5" data-measure-by> · Suggested by {{ by }}</span><span v-else-if="nothing" class="text-ink-gray-5" data-measure-none> · No suggestion. Write it yourself.</span></span>
      <Button v-if="title && !hideSuggest" size="sm" variant="ghost" icon-left="lucide-sparkles" label="Suggest" :loading="busy" data-measure-suggest @click="suggest" />
    </div>
    <div v-if="examples.length" class="flex flex-col gap-1.5 rounded-md bg-surface-gray-1 p-2.5" data-measure-examples>
      <span class="text-sm text-ink-gray-6">Two examples for this kind of goal. Tap one to start from it.</span>
      <LinkButton v-for="(x, i) in examples" :key="i" class="text-sm !text-ink-gray-8" data-measure-example @click="useExample(x)">{{ x }}</LinkButton>
    </div>
    <TabButtons :model-value="m.measure_kind || ''" :options="KINDS" data-measure-kind @update:model-value="setKind" />
    <FormControl v-if="m.measure_kind === 'Milestone'" v-model="m.done_when" type="textarea" :rows="2" label="Finish line" :disabled="disabled"
      placeholder="What will be true when this goal is done" data-measure-done-when />
    <template v-else-if="m.measure_kind === 'Number'">
      <div class="grid grid-cols-[1fr_8rem] gap-2 max-sm:grid-cols-1">
        <FormControl v-model="m.measure" label="What is measured" placeholder="For example: Ghillidary yield" :disabled="disabled" data-measure-name />
        <FormControl v-model="m.unit" label="Unit" placeholder="kg/ha" :disabled="disabled" data-measure-unit />
      </div>
      <div class="grid grid-cols-2 gap-2">
        <FormControl v-model="m.start_value" type="number" label="Start" :disabled="disabled" data-measure-start />
        <FormControl v-model="m.target_value" type="number" label="Target" :disabled="disabled" data-measure-target />
      </div>
      <p v-if="direction" class="text-sm text-ink-gray-6">{{ direction }}</p>
    </template>
    <Alert v-if="habit && !habitDismissed && !noHabit" theme="blue" title="This looks like a habit" data-habit-hint
      :description="`“${habit.title}” reads as something you do ${habit.days_per_week === 7 ? 'every day' : habit.days_per_week + ' times a week'}. A habit is ticked each day; a goal has a finish line.`">
      <template #actions><div class="flex gap-2">
        <Button label="Keep as a goal" @click="habitDismissed = true" />
        <Button variant="solid" label="Make it a habit" data-make-habit @click="emit('habit', habit)" />
      </div></template>
    </Alert>
  </div>
</template>
<script setup>
import LinkButton from '@/components/ui/LinkButton.vue'
// "Done when…" (set 7): how a goal will be known to be done. A finish line (Milestone, `done_when`) or a number (Number:
// what is measured, its unit, a start and a target). Suggest asks the assistant (or simple rules without a key). A title or
// finish line that reads as a frequency ("daily", "3 times a week") offers Make it a habit instead.
import { computed, ref, watch } from 'vue'
import { Alert, Button, FormControl, TabButtons } from 'frappe-ui'
import { tryCall } from '@/lib/api'
import { goalsData } from '@/data/goals'
import { store } from '@/lib/store'

const props = defineProps({ modelValue: { type: Object, required: true }, title: String, notes: String, space: String, disabled: Boolean, hideSuggest: Boolean, goal: String, horizon: String, noHabit: Boolean })
const emit = defineEmits(['update:modelValue', 'habit'])
const KINDS = [{ label: 'A finish line', value: 'Milestone' }, { label: 'A number', value: 'Number' }]
const m = props.modelValue
const busy = ref(false)
const by = ref('')
const nothing = ref(false)
const examples = ref([])
const habitDismissed = ref(false)
const suggestedHabit = ref(null)

// a frequency in the title or the finish line, read in the browser as the server does (lifeos/goals/readings.py FREQUENCY)
const FREQ = /\b(daily|every\s?day|each\s?day|every\s+(morning|evening|night|week|weekday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|weekly|nightly|(\d+|once|twice|two|three|four|five|six)\s*(x|times?)?\s*(a|per|each|every)\s+(day|week)|(once|twice)\s+(a|per)\s+(day|week))\b/i
const WORDS = { once: 1, twice: 2, two: 2, three: 3, four: 4, five: 5, six: 6 }
function habitOf(text) {
  const hit = (text || '').match(FREQ)
  if (!hit) return null
  const w = hit[0].toLowerCase()
  const n = w.match(/(\d+|once|twice|two|three|four|five|six)\s*(x|times?)?\s*(a|per|each|every)\s+week/)
  const days = n ? (Number(n[1]) || WORDS[n[1]]) : /weekly|every\s+week|every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)/.test(w) ? 1 : /weekday/.test(w) ? 5 : 7
  return { title: (props.title || text).trim().slice(0, 140), days_per_week: Math.max(1, Math.min(7, days)) }
}
const habit = computed(() => suggestedHabit.value || habitOf(props.title) || habitOf(m.measure_kind === 'Milestone' ? m.done_when : ''))
watch(() => props.title, () => { suggestedHabit.value = null; habitDismissed.value = false })

const direction = computed(() => {
  const s = Number(m.start_value), t = Number(m.target_value)
  if (m.start_value === '' || m.target_value === '' || m.start_value == null || m.target_value == null || Number.isNaN(s) || Number.isNaN(t) || s === t) return ''
  return `${s < t ? 'Goes up' : 'Goes down'} from ${s} to ${t}${m.unit ? ' ' + m.unit : ''}.`
})
function useExample(text) {
  m.measure_kind = 'Milestone'
  m.done_when = text
  examples.value = []
  emit('update:modelValue', m)
}
function setKind(v) {
  m.measure_kind = v
  emit('update:modelValue', m)
}
async function suggest() {
  busy.value = true
  examples.value = []
  const r = await tryCall(() => goalsData.goals.suggest_measure({ title: props.title, notes: props.notes || undefined, space: props.space || store.space, goal: props.goal || undefined, horizon: props.horizon || undefined }))
  busy.value = false
  if (!r) return
  by.value = r.by || ''
  nothing.value = !r.kind
  if (r.habit) { suggestedHabit.value = r.habit; habitDismissed.value = false }
  if (!r.kind) { examples.value = r.examples || []; return }
  m.measure_kind = r.kind
  if (r.kind === 'Number') {
    for (const k of ['measure', 'unit', 'target_value', 'start_value']) if (r[k] !== null && r[k] !== undefined) m[k] = r[k]
  } else if (r.done_when && !(m.done_when || '').trim()) m.done_when = r.done_when
  if (r.habit) { suggestedHabit.value = r.habit; habitDismissed.value = false }
  emit('update:modelValue', m)
}
</script>
