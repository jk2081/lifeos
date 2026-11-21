<template>
  <Drawer :open="!!goal" name="goal" :title="d?.title || 'Goal'" @close="emit('close')">
    <template #sub><span v-if="d" data-goal-drawer-sub>{{ subLine }}</span></template>
    <Skeleton v-if="!d" class="h-64 w-full" />
    <div v-else class="flex flex-col gap-4" data-goal-drawer :data-goal="d.goal">
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
        <div><Button label="Plan it after all" data-goal-unskip @click="emit('unskip', d.goal)" /></div>
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
        <Checkbox :model-value="d.star" label="One of this week's top three" data-goal-star @update:model-value="(on) => emit('star', d.goal, on)" />
      </template>
    </div>
    <template #footer>
      <template v-if="d && !d.plan.skip">
        <Button v-if="!skipping" label="Skip this goal this week" data-goal-skip @click="skipping = true" />
        <template v-else>
          <TextInput v-model="reason" class="min-w-0 flex-1" placeholder="Why, in a few words (required)" aria-label="Why skip" data-goal-skip-reason />
          <Button label="Skip" :disabled="!reason.trim()" data-goal-skip-confirm @click="emit('skip', d.goal, reason)" />
        </template>
      </template>
      <span class="flex-1" />
      <Button v-if="d && !d.plan.skip" variant="solid" label="Save" data-goal-save @click="save" />
    </template>
  </Drawer>
</template>
<script setup>
// A goal opened from the Goals tab (board 32): its next action (or one of its other open tasks), when and how long, the
// free slots that fit, who, what is needed, the top-three star, Skip this goal this week (with a reason) and Save.
import { computed, reactive, ref, watch } from 'vue'
import { Alert, Button, Checkbox, DateTimePicker, Dropdown, FormControl, Skeleton, TextInput } from 'frappe-ui'
import Drawer from '@/components/ui/Drawer.vue'
import DoneWhen from '@/components/goals/DoneWhen.vue'
import SuggestedReadings from '@/components/goals/SuggestedReadings.vue'
import { api, tryCall } from '@/lib/api'
import { emptyMeasure, measureArgs, measureProblem } from '@/lib/goals'
import { store } from '@/lib/store'
import { time, weekday } from '@/lib/dates'

const props = defineProps({ goal: String, d: Object, focus: String })
const emit = defineEmits(['close', 'save', 'skip', 'unskip', 'star', 'changed'])
const SOURCE = { review: 'Made earlier in this review.', oldest: 'The goal\'s oldest open task.', assistant: 'Suggested by the assistant.', owner: '' }
const v = reactive({ next_action: '', task: null, slot: '', minutes: 60, who: 'Me', note: '' })
const other = ref(false)
const skipping = ref(false)
const reason = ref('')
const measure = reactive(emptyMeasure())
const readings = ref([])
const isMe = computed(() => !other.value && (!v.who || v.who === 'Me'))
watch(() => props.d, (d) => {
  if (!d) return
  Object.assign(v, { next_action: d.plan.next_action || '', task: d.plan.task || null, slot: d.plan.slot ? d.plan.slot + ':00' : '', minutes: d.plan.minutes || 60,
    who: d.plan.who || 'Me', note: d.plan.note || '' })
  other.value = !!v.who && v.who !== 'Me' && !d.people.includes(v.who)
  skipping.value = false
  reason.value = ''
  Object.assign(measure, emptyMeasure(d.measure))
  loadReadings()
}, { immediate: true })
const subLine = computed(() => {
  const d = props.d
  return [d.in_cycle ? '12 Weeks' : d.goal_type, d.area_name, d.finish_line ? `finish line: ${d.finish_line}` : 'needs a finish line', d.progress.label, d.mark].filter(Boolean).join(' · ')
})
const slotLabel = (s) => `${weekday(s, 3)} ${time(s)}`
const sameSlot = (s) => (v.slot || '').slice(0, 16) === s
// Opening the drawer only reads the suggested readings. Telling the parent "changed" here made it read the goal again, which
// gave the drawer new data, which read the readings again: a loop that refreshed the open drawer and wiped what was typed.
async function loadReadings() {
  if (!props.d) return
  readings.value = (await tryCall(() => api('goals.goal_readings', { goal: props.d.goal })))?.suggested || []
}
// after a reading is confirmed or dismissed: the goal's progress changed, so the row and the drawer read it again
async function reloadReadings() {
  await loadReadings()
  emit('changed')
}
async function saveMeasure() {
  if (await tryCall(() => api('goals.update', { goal: props.d.goal, values: measureArgs(measure) }), 'Finish line saved.')) emit('changed')
}
function save() {
  // with a task the next action renames it at Lock; without one a task is made
  emit('save', props.d.goal, { next_action: v.next_action, task: v.task || null,
    slot: v.slot ? String(v.slot).slice(0, 16) : '', minutes: Number(v.minutes) || 60, who: isMe.value ? 'Me' : v.who, note: v.note })
}
</script>
