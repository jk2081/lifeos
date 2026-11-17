<template>
  <div class="flex flex-col gap-3" data-goal-work>
    <div v-if="loading" class="flex flex-col gap-2"><Skeleton class="h-24 w-full" /><Skeleton class="h-24 w-full" /></div>
    <template v-else-if="p">
      <p class="text-sm text-ink-gray-6">For each goal: the next action, when, for how long, who does it and what is needed. Add makes it a task under the goal at that time.
        Working hours: {{ hoursText }} (Settings, Rhythms).</p>
      <Card v-for="c in shown" :key="c.goal" class="flex flex-col gap-3" data-goal-card :data-goal="c.goal" :data-card-state="c.state">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <RouterLink class="break-words text-base-medium text-ink-gray-9 hover:underline focus-visible:focus-ring" :to="`/plan/goals/${c.goal}`">{{ c.title }}</RouterLink>
          <span class="text-sm text-ink-gray-6">{{ c.goal_type === '12 Week Year' ? c.cycle_title || '12 Week Year' : c.goal_type === 'Open' ? 'Open-ended goal' : 'Annual goal' }}</span>
        </div>
        <div v-if="c.planned.length" class="flex flex-col gap-1" data-card-planned>
          <div v-for="t in c.planned" :key="t.task" class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-7">
            <span class="lucide-calendar-check size-4 text-ink-green-7" aria-hidden="true" />
            <span class="min-w-0 break-words">{{ t.title }}</span>
            <span class="text-ink-gray-6">· {{ t.scheduled_at ? when(t.scheduled_at) : 'no set time' }}, {{ t.duration_min }} min{{ t.status === 'Waiting' ? ' · waiting on ' + t.waiting_on : '' }}</span>
          </div>
        </div>
        <template v-if="c.state === 'open' && canWrite()">
          <div class="grid grid-cols-[minmax(0,1fr)_14rem_7rem] items-start gap-2 max-md:grid-cols-1">
            <FormControl v-model="c.next_action" label="Next action" :placeholder="c.suggested ? '' : 'What is the next step?'" data-card-action
              :description="c.suggested ? 'Suggested by the assistant.' : c.task ? 'The oldest open task under this goal.' : ''" />
            <div class="flex flex-col gap-1">
              <DateTimePicker v-if="!c.no_time" v-model="c.slot" label="When" data-card-when />
              <FormControl v-else type="text" label="When" model-value="No set time" disabled />
              <Button class="self-start" size="sm" variant="ghost" :label="c.no_time ? 'Pick a time' : 'No set time'" data-card-no-time @click="c.no_time = !c.no_time" />
            </div>
            <FormControl v-model="c.minutes" type="select" label="Length" :options="LENGTHS" data-card-length />
          </div>
          <div class="grid grid-cols-[14rem_minmax(0,1fr)_auto] items-end gap-2 max-md:grid-cols-1">
            <div class="flex flex-col gap-1.5">
              <FormControl v-model="c.who" type="select" label="Who" :options="whoOptions" data-card-who />
              <FormControl v-if="c.who === OTHER" v-model="c.who_name" label="Their name" placeholder="Who will do it" data-card-who-name />
            </div>
            <FormControl v-model="c.note" label="What is needed" placeholder="For example: the soil report" data-card-note />
            <div class="flex justify-end gap-2"><Button label="Skip" data-card-skip @click="c.state = 'skipped'" />
              <Button variant="solid" label="Add" :loading="c.busy" data-card-add @click="add(c)" /></div>
          </div>
        </template>
        <div v-else-if="c.state === 'skipped'" class="flex items-center justify-between gap-2 text-sm text-ink-gray-6">
          <span>Skipped for this week.</span><Button size="sm" variant="ghost" label="Undo" @click="c.state = 'open'" /></div>
      </Card>
      <Card v-if="!p.cards.length"><Empty title="No active goals." hint="Goals in progress that are not on hold show here, the current cycle's first." /></Card>
      <div class="flex flex-wrap items-center gap-x-2 rounded-5 border border-outline-gray-2 bg-surface-gray-1 px-4 py-2.5 text-base text-ink-gray-8" data-goal-work-footer
        :data-planned-minutes="plannedMinutes" :data-free-minutes="p.free_minutes">
        <span class="lucide-clock size-4 text-ink-gray-6" aria-hidden="true" />
        <span>Planned <b class="font-semibold">{{ hrs(plannedMinutes) }}</b> of goal work; {{ hrs(p.free_minutes) }} free in working hours in the next seven days.</span>
      </div>
    </template>
  </div>
</template>
<script setup>
// The weekly review's step 3 (set 7): goal work for the coming week. One card per active goal in the lens; Add creates or
// updates the task under the goal with its time and length (Waiting on someone else when "who" is not you). The footer adds up
// the planned time against the free working time.
import { computed, onMounted, ref } from 'vue'
import { Button, DateTimePicker, FormControl, Skeleton } from 'frappe-ui'
import Card from '../ui/Card.vue'
import Empty from '../Empty.vue'
import { api, tryCall } from '@/lib/api'
import { canWrite, store } from '@/lib/store'
import { loadLookups, lookups } from '@/lib/lookups'
import { weekday } from '@/lib/dates'

const OTHER = '__other'
const LENGTHS = [15, 30, 45, 60, 90, 120].map((n) => ({ label: n < 60 ? `${n} min` : `${n / 60} h`.replace('1.5 h', '1½ h'), value: n }))
const p = ref(null)
const loading = ref(true)
const added = ref(0)
const whoOptions = computed(() => [{ label: 'Me', value: 'Me' }, ...(lookups.people || []).filter((x) => x.relation !== 'Self').map((x) => ({ label: x.full_name, value: x.full_name })),
  { label: 'Someone else…', value: OTHER }])
const shown = computed(() => p.value?.cards || [])
const plannedMinutes = computed(() => (p.value?.planned_minutes || 0) + added.value)
const hoursText = computed(() => {
  const h = p.value.hours
  const pad = (x) => String(x).padStart(2, '0')
  const days = h.days.length === 7 ? 'every day' : h.days.length === 6 && !h.days.includes('Sunday') ? 'Monday to Saturday' : h.days.length === 5 && !h.days.includes('Saturday') && !h.days.includes('Sunday') ? 'Monday to Friday' : h.days.map((d) => d.slice(0, 3)).join(', ')
  return `${days}, ${pad(h.start[0])}:${pad(h.start[1])} to ${pad(h.end[0])}:${pad(h.end[1])}`
})
const hrs = (m) => (m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} h`)
const when = (s) => `${weekday(s.slice(0, 10), 3)} ${s.slice(11, 16)}`

async function load() {
  loading.value = true
  loadLookups()
  const res = await tryCall(() => api('week.goal_plan', { space: store.space, area: store.lensArea || undefined }))
  if (res) {
    for (const c of res.cards) Object.assign(c, { state: 'open', who: 'Me', who_name: '', note: '', no_time: !c.slot, busy: false })
    p.value = res
    added.value = 0
  }
  loading.value = false
}
async function add(c) {
  const who = c.who === OTHER ? (c.who_name || '').trim() : c.who
  if (!(c.next_action || '').trim()) return tryCall(() => Promise.reject(new Error('Write the next action.')))
  c.busy = true
  const res = await tryCall(() => api('week.add_goal_work', { goal: c.goal, task: c.task || undefined, title: c.next_action, scheduled_at: c.no_time ? '' : c.slot,
    duration_min: Number(c.minutes), who: who === 'Me' ? '' : who, note: c.note }), who && who !== 'Me' ? `Added, waiting on ${who}` : 'Added to the week')
  c.busy = false
  if (!res) return
  const prev = c.planned.find((t) => t.task === res.task)
  if (prev) c.planned.splice(c.planned.indexOf(prev), 1)
  if (res.scheduled_at) added.value += res.duration_min - (prev ? prev.duration_min : 0)
  c.planned.push({ task: res.task, title: res.title, scheduled_at: res.scheduled_at || '', duration_min: res.duration_min, status: res.status, waiting_on: res.waiting_on })
  c.task = res.task
  c.state = 'added'
}
onMounted(load)
defineExpose({ load })
</script>
