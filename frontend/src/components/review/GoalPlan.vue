<template>
  <section class="flex flex-col gap-4 rounded-4 border border-outline-gray-2 p-3" data-goal-plan :data-goal="goal">
    <div class="text-base-medium text-ink-gray-9">This week's plan</div>
    <Skeleton v-if="!d" class="h-64 w-full" />
    <div v-else class="flex flex-col gap-4">
      <!-- "Needs a finish line" opens here, at set 7's Done when… choice -->
      <section v-if="d.needs_finish_line || focus === 'finish'" class="flex flex-col gap-2 rounded-4 bg-surface-amber-1 p-3" data-goal-finish-line>
        <div class="text-base-medium text-ink-amber-9">Needs a finish line</div>
        <DoneWhen :model-value="measure" :title="d.title" :space="store.space" @update:model-value="(m) => Object.assign(measure, m)" />
        <div><Button label="Save the finish line" :disabled="!!measureProblem(measure)" data-goal-finish-save @click="saveMeasure" /></div>
      </section>
      <section v-if="readings.length" class="flex flex-col gap-1" data-goal-readings>
        <div class="text-base-medium text-ink-gray-9">{{ readings.length }} reading{{ readings.length === 1 ? '' : 's' }} to confirm</div>
        <SuggestedReadings :rows="readings" writable @changed="reloadReadings" />
      </section>
      <template v-if="d.plan.skip">
        <Alert theme="amber" title="Skipped this week" :description="d.plan.skip" data-goal-skipped />
        <div><Button label="Plan it after all" data-goal-unskip @click="unskip" /></div>
      </template>
      <template v-else>
        <div class="flex flex-col gap-1">
          <FormControl v-model="v.next_action" label="Next action" placeholder="One concrete step" data-goal-next />
          <div class="text-sm text-ink-gray-6">{{ d.plan.source === 'assistant' && d.plan.by ? 'Suggested by ' + d.plan.by + '.' : SOURCE[d.plan.source] || '' }}
            <Dropdown v-if="d.tasks.length" :options="d.tasks.map((t) => ({ label: t.title, onClick: () => { v.next_action = t.title; v.task = t.name } }))">
              <Button variant="ghost" size="sm" class="!text-ink-blue-8" :label="`other open tasks (${d.tasks.length})`" data-goal-other-tasks />
            </Dropdown>
          </div>
        </div>
        <div class="grid grid-cols-[1fr_120px] gap-3">
          <DateTimePicker v-model="v.slot" label="When" placeholder="No set time" data-goal-when />
          <FormControl v-model="v.minutes" type="number" label="Length (min)" data-goal-length />
        </div>
        <div class="flex flex-col gap-1.5">
          <span class="text-sm text-ink-gray-7">Free slots that fit</span>
          <div class="flex flex-wrap gap-2" data-goal-slots>
            <Button v-for="s in d.slots" :key="s" :variant="sameSlot(s) ? 'solid' : 'subtle'" :label="slotLabel(s)" @click="v.slot = s + ':00'" />
            <Button :variant="!v.slot ? 'solid' : 'subtle'" label="No set time" @click="v.slot = ''" />
          </div>
        </div>
        <div class="flex flex-col gap-1.5">
          <span class="text-sm text-ink-gray-7">Who</span>
          <div class="flex flex-wrap gap-2" data-goal-who>
            <Button :variant="isMe ? 'solid' : 'subtle'" label="Me" @click="v.who = 'Me'" />
            <Button v-for="p in d.people" :key="p" :variant="v.who === p ? 'solid' : 'subtle'" :label="p" @click="v.who = p" />
            <Button :variant="other ? 'solid' : 'subtle'" label="Someone else…" @click="other = true; v.who = ''" />
          </div>
          <TextInput v-if="other" v-model="v.who" placeholder="Who does it" aria-label="Someone else" data-goal-who-other />
        </div>
        <FormControl v-model="v.note" type="textarea" :rows="3" label="What is needed" placeholder="What has to be ready for it" data-goal-note />
        <Checkbox :model-value="d.star" label="One of this week's top three" data-goal-star @update:model-value="star" />
      </template>
    </div>
    <div v-if="d" class="flex flex-wrap items-center gap-3 border-t border-outline-gray-1 pt-3" data-goal-plan-footer>
    <template v-if="d && !d.plan.skip">
      <Button v-if="!skipping" label="Skip this goal this week" data-goal-skip @click="skipping = true" />
      <template v-else>
        <TextInput v-model="reason" class="min-w-0 flex-1" placeholder="Why, in a few words (required)" aria-label="Why skip" data-goal-skip-reason />
        <Button label="Skip" :disabled="!reason.trim()" data-goal-skip-confirm @click="skip" />
      </template>
    </template>
    <span class="flex-1" />
    <Button v-if="d && !d.plan.skip" variant="solid" label="Save" data-goal-save @click="save" />
    </div>
  </section>
</template>
<script setup>
// The weekly review's plan for one goal, shown at the top of the goal's Drawer layer when the goal is opened from the review (board 32):
// its next action (or one of its other open tasks), when and how long, the free slots that fit, who, what is needed, the top-three star,
// Skip this goal this week (with a reason) and Save. Reads and writes through the review on screen (lib/review.js).
import { computed, reactive, ref, watch } from 'vue'
import { Alert, Button, Checkbox, DateTimePicker, Dropdown, FormControl, Skeleton, TextInput } from 'frappe-ui'
import DoneWhen from '@/components/goals/DoneWhen.vue'
import SuggestedReadings from '@/components/goals/SuggestedReadings.vue'
import { tryCall } from '@/lib/api'
import { reviewData } from '@/data/review'
import { emptyMeasure, measureArgs, measureProblem } from '@/lib/goals'
import { weeklyAct, weeklyRead } from '@/lib/review'
import { store } from '@/lib/store'
import { time, weekday } from '@/lib/dates'

const props = defineProps({ goal: String, focus: String })
const emit = defineEmits(['changed', 'done'])
const SOURCE = { review: 'Made earlier in this review.', oldest: 'The goal\'s oldest open task.', assistant: 'Suggested by the assistant.', owner: '' }
const d = ref(null)
const v = reactive({ next_action: '', task: null, slot: '', minutes: 60, who: 'Me', note: '' })
const other = ref(false)
const skipping = ref(false)
const reason = ref('')
const measure = reactive(emptyMeasure())
const readings = ref([])
const isMe = computed(() => !other.value && (!v.who || v.who === 'Me'))

async function load() {
  const x = await tryCall(() => weeklyRead('goal', { goal: props.goal }))
  if (!x) return
  d.value = x
  Object.assign(v, { next_action: x.plan.next_action || '', task: x.plan.task || null, slot: x.plan.slot ? x.plan.slot + ':00' : '', minutes: x.plan.minutes || 60,
    who: x.plan.who || 'Me', note: x.plan.note || '' })
  other.value = !!v.who && v.who !== 'Me' && !x.people.includes(v.who)
  skipping.value = false
  reason.value = ''
  Object.assign(measure, emptyMeasure(x.measure))
  loadReadings()
}
// Only a change of the plan reads the goal again: telling the parent "changed" after reading the readings looped (the set 8 bug, DECISIONS.md)
async function reread() {
  d.value = await weeklyRead('goal', { goal: props.goal })
}
const slotLabel = (s) => `${weekday(s, 3)} ${time(s)}`
const sameSlot = (s) => (v.slot || '').slice(0, 16) === s
async function loadReadings() {
  readings.value = (await tryCall(() => reviewData.goals.goal_readings({ goal: props.goal })))?.suggested || []
}
// after a reading is confirmed or dismissed: the goal's progress changed, so the row and the plan read it again
async function reloadReadings() {
  await loadReadings()
  await reread()
  emit('changed')
}
async function saveMeasure() {
  if (await tryCall(() => reviewData.goals.update({ goal: props.goal, values: measureArgs(measure) }), 'Finish line saved.')) { await reread(); emit('changed') }
}
async function act(method, args, ok) {
  if (!(await weeklyAct(method, { goal: props.goal, ...args }, ok))) return false
  emit('changed')
  return true
}
async function save() {
  // with a task the next action renames it at Lock; without one a task is made
  if (await act('goal_save', { values: { next_action: v.next_action, task: v.task || null,
    slot: v.slot ? String(v.slot).slice(0, 16) : '', minutes: Number(v.minutes) || 60, who: isMe.value ? 'Me' : v.who, note: v.note } }, 'Saved.')) emit('done')
}
async function skip() {
  if (await act('goal_skip', { reason: reason.value }, 'Skipped this week.')) emit('done')
}
async function unskip() {
  if (await act('goal_skip', { undo: 1 })) reread()
}
async function star(on) {
  if (await act('goal_star', { on: on ? 1 : 0 })) reread()
}
watch(() => props.goal, load, { immediate: true })
</script>
