<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-reflect>
    <div class="page-body !gap-4">
      <div>
        <h2 class="text-xl-semibold text-ink-gray-9">What did you learn this week?</h2>
        <p class="text-sm text-ink-gray-6">In your own words. One line is enough; it is what you will read back at the 12-week review.</p>
      </div>
      <Skeleton v-if="!d" class="h-80 w-full" />
      <div v-else class="grid grid-cols-[minmax(0,1fr)] items-start gap-4 md:grid-cols-[minmax(0,1.45fr)_minmax(300px,1fr)]">
        <div class="flex min-w-0 flex-col gap-4">
          <FormControl v-model="wentWell" type="textarea" :rows="3" label="What went well?" placeholder="One line or more" data-went-well @update:model-value="queue" />
          <FormControl v-model="differently" type="textarea" :rows="3" label="What will you do differently? (optional)"
            placeholder="For example: no goal work after 17:00; it never happens." data-do-differently @update:model-value="queue" />
          <Card tint class="flex flex-col gap-2" data-week-numbers>
            <SectionHead>The week in numbers</SectionHead>
            <p class="text-sm text-ink-gray-7">{{ numbersLine }}</p>
            <p v-if="d.last" class="text-sm text-ink-gray-7" data-playback>Last week you wrote: <i>“{{ d.last.line }}”</i><template v-if="d.last.check"> {{ d.last.check }}</template></p>
          </Card>
        </div>
        <Card class="flex flex-col gap-2" data-lock-preview>
          <SectionHead>When you lock the week</SectionHead>
          <div class="text-sm-medium text-ink-gray-8">Top three</div>
          <Row bare v-for="t in d.preview.top" :key="t.goal" class="flex items-center gap-2 py-1.5" data-lock-top>
            <span class="lucide-star size-4 shrink-0 text-ink-amber-9" aria-hidden="true" />
            <span class="min-w-0 flex-1 truncate text-base text-ink-gray-9">{{ t.title }}</span>
            <span class="text-sm tabular-nums text-ink-gray-6">{{ t.slot ? `${weekday(t.slot, 3)} ${time(t.slot)}` : 'No set time' }}</span>
          </Row>
          <ul class="mt-1 flex flex-col gap-0.5 text-sm text-ink-gray-7">
            <li>· {{ d.preview.planned }} task{{ d.preview.planned === 1 ? '' : 's' }} planned, {{ d.preview.scheduled }} with a time, shown on Today</li>
            <li v-if="d.preview.delegated.length">· {{ d.preview.delegated.length }} delegated ({{ d.preview.delegated.map((x) => x.who).join(', ') }}, waiting)</li>
            <li>· Top three pinned to Today all week</li>
            <li>· Next review: {{ weekday(d.preview.next.date) }} {{ long(d.preview.next.date) }}, {{ d.preview.next.time }}</li>
          </ul>
          <p class="rounded-4 bg-surface-gray-1 p-2 text-sm text-ink-gray-7">Calendar blocks arrive with set 9; until then the times live in Life OS.</p>
        </Card>
      </div>
    </div>
    <ReviewFooter back label="Lock the week" :disabled="!wentWell.trim()" :loading="locking" line="What went well is required · the rest is optional"
      @back="emit('go', 'goals')" @next="lock" />
  </div>
</template>
<script setup>
import Row from '@/components/ui/Row.vue'
import SectionHead from '@/components/ui/SectionHead.vue'
// Tab 4, Reflect (board 33): what went well (required) and what to do differently, the week in numbers, last week's note
// played back, and what Lock will do. Lock the week shows the done screen.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { FormControl, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import ReviewFooter from '@/components/review/ReviewFooter.vue'
import { useReview } from '@/lib/review'
import { refreshCounts } from '@/lib/store'
import { long, time, weekday } from '@/lib/dates'

const emit = defineEmits(['go'])
const r = useReview()
const d = ref(null)
const wentWell = ref('')
const differently = ref('')
const locking = ref(false)
let timer = null
const numbersLine = computed(() => {
  const n = d.value.numbers
  return [n.score != null ? `Score ${Math.round(n.score)}% against ${n.target}%` : 'No 12 Week Year score', `${n.came_in} came in, ${n.went_out} went out`,
    `${n.findings_acted} revelation${n.findings_acted === 1 ? '' : 's'} acted on, ${n.findings_dismissed} dismissed`, `${n.items_cleared} stuck and waiting items cleared`,
    `${n.goals_planned} goal${n.goals_planned === 1 ? '' : 's'} planned, ${n.goals_skipped} skipped`].join(' · ')
})
async function load() {
  d.value = await r.read('reflect')
  wentWell.value = d.value.went_well
  differently.value = d.value.do_differently
}
function queue() {
  clearTimeout(timer)
  timer = setTimeout(save, 1200)
}
async function save() {
  if (r.readOnly || locking.value || r.head?.status === 'Locked') return
  await r.act('reflect_save', { went_well: wentWell.value, do_differently: differently.value })
}
async function lock() {
  clearTimeout(timer)
  locking.value = true
  try {
    await r.act('lock', { went_well: wentWell.value, do_differently: differently.value })
    refreshCounts() // Review joins the sidebar after the first locked review (issue 14)
  } catch (e) { locking.value = false }
}
onMounted(load)
onBeforeUnmount(() => clearTimeout(timer))
</script>
