<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-reflect>
    <div class="page-body !gap-4">
      <div>
        <h2 class="text-xl-semibold text-ink-gray-9">{{ monthly ? 'What did the month teach you?' : 'What did the cycle teach you?' }}</h2>
        <p class="text-sm text-ink-gray-6">In your own words. A line or two is enough.</p>
      </div>
      <Skeleton v-if="!d" class="h-80 w-full" />
      <div v-else class="grid items-start gap-4 md:grid-cols-[minmax(0,1.45fr)_minmax(300px,1fr)]">
        <div class="flex min-w-0 flex-col gap-4">
          <FormControl v-model="wentWell" type="textarea" :rows="3" label="What went well?" placeholder="One line or more" data-went-well @update:model-value="queue" />
          <FormControl v-if="monthly" v-model="notWell" type="textarea" :rows="3" label="What did not go well?" data-not-well @update:model-value="queue" />
          <FormControl v-if="monthly" v-model="change" type="textarea" :rows="2" label="One change for next month (optional)" data-change @update:model-value="queue" />
        </div>
        <Card class="flex flex-col gap-2" data-lock-preview>
          <h3 class="text-base-medium text-ink-gray-9">{{ monthly ? 'When you lock the month' : 'When you lock the cycle' }}</h3>
          <ul v-if="p" class="flex flex-col gap-0.5 text-sm text-ink-gray-7">
            <template v-if="monthly">
              <li>· {{ p.goals.length }} goal{{ p.goals.length === 1 ? '' : 's' }} in {{ p.title }}, {{ p.goals.filter((g) => g.carried_from).length }} carried, in the order you gave</li>
              <li>· {{ p.habits.length }} habit{{ p.habits.length === 1 ? '' : 's' }} for the month</li>
              <li>· The goals you dropped are marked dropped, with your reasons</li>
            </template>
            <template v-else>
              <li>· This cycle closes with its final score</li>
              <li>· {{ p.goals.length }} goal{{ p.goals.length === 1 ? '' : 's' }} in the next cycle, starting {{ long(p.dates.start) }}</li>
              <li>· Carried goals keep their history; dropped ones keep your reasons</li>
            </template>
          </ul>
        </Card>
      </div>
    </div>
    <ReviewFooter back :label="monthly ? 'Lock the month' : 'Lock the cycle'" :disabled="!wentWell.trim()" :loading="locking" line="What went well is required" @back="emit('go', 'plan')" @next="lock" />
  </div>
</template>
<script setup>
// Tab 4, Reflect, and Lock: what went well (required), what did not and one change (monthly). Lock writes next month's plan or
// closes the cycle and makes the next one.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { FormControl, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import ReviewFooter from '@/components/review/ReviewFooter.vue'
import { useReview } from '@/lib/review'
import { refreshCounts } from '@/lib/store'
import { long } from '@/lib/dates'

const emit = defineEmits(['go'])
const r = useReview()
const d = ref(null)
const p = ref(null)
const wentWell = ref('')
const notWell = ref('')
const change = ref('')
const locking = ref(false)
const monthly = computed(() => r.head?.slug === 'monthly')
let timer = null
async function load() {
  d.value = await r.read('reflect')
  p.value = await r.read('plan')
  wentWell.value = d.value.went_well
  notWell.value = d.value.not_well
  change.value = d.value.change
}
const words = () => ({ went_well: wentWell.value, not_well: notWell.value, change: change.value })
function queue() {
  clearTimeout(timer)
  timer = setTimeout(save, 1200)
}
async function save() {
  if (r.readOnly || locking.value || r.head?.status === 'Locked') return
  await r.act('reflect_save', words())
}
async function lock() {
  clearTimeout(timer)
  locking.value = true
  try {
    await r.act('lock', words())
    refreshCounts()
  } catch (e) { locking.value = false }
}
onMounted(load)
onBeforeUnmount(() => clearTimeout(timer))
</script>
