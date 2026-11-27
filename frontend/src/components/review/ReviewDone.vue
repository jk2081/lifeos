<template>
  <div class="page-body items-center" data-review-done>
    <Skeleton v-if="!d" class="h-64 w-full max-w-xl" />
    <Card v-else class="flex w-full max-w-xl flex-col gap-3">
      <div class="flex items-center gap-2">
        <span class="flex size-7 items-center justify-center rounded-full bg-surface-green-7 text-ink-base" aria-hidden="true"><span class="lucide-check size-4" /></span>
        <h2 class="text-xl-semibold text-ink-gray-9" data-review-done-title>{{ title }}</h2>
      </div>
      <ul v-if="kind === 'weekly'" class="flex flex-col gap-0.5 text-base text-ink-gray-8" data-review-decided>
        <li>{{ d.made.length }} task{{ d.made.length === 1 ? '' : 's' }} planned for your goals, {{ d.scheduled }} with a time</li>
        <li v-if="d.delegated">{{ d.delegated }} delegated, waiting on someone</li>
        <li v-if="d.skipped">{{ d.skipped }} goal{{ d.skipped === 1 ? '' : 's' }} skipped this week</li>
        <li>{{ d.cleared }} stuck and waiting item{{ d.cleared === 1 ? '' : 's' }} cleared</li>
      </ul>
      <ul v-else-if="kind === 'monthly'" class="flex flex-col gap-0.5 text-base text-ink-gray-8" data-review-decided>
        <li>{{ d.made.length }} goal{{ d.made.length === 1 ? '' : 's' }} in the plan, {{ d.made.filter((g) => g.carried).length }} carried</li>
        <li v-if="d.piles.finish">{{ d.piles.finish }} to finish, with dates</li>
        <li v-if="d.piles.drop">{{ d.piles.drop }} dropped</li>
        <li>{{ d.habits }} habit{{ d.habits === 1 ? '' : 's' }} for the month</li>
      </ul>
      <ul v-else class="flex flex-col gap-0.5 text-base text-ink-gray-8" data-review-decided>
        <li>Final score {{ Math.round(d.final_score) }}%</li>
        <li>{{ d.piles.done }} done, {{ d.piles.carry }} carried, {{ d.piles.drop }} dropped</li>
        <li>{{ d.next_title }} starts {{ long(d.next_start) }} with {{ d.made.length }} goal{{ d.made.length === 1 ? '' : 's' }}</li>
      </ul>
      <div v-if="kind === 'weekly'">
        <div class="mb-1 text-sm-medium text-ink-gray-8">Top three</div>
        <Row bare v-for="t in d.top" :key="t.task" class="flex items-center gap-2 py-1.5" data-done-top>
          <span class="lucide-star size-4 shrink-0 text-ink-amber-9" aria-hidden="true" />
          <span class="min-w-0 flex-1 truncate text-base text-ink-gray-9">{{ t.title }}</span>
          <span class="text-sm tabular-nums text-ink-gray-6">{{ t.slot ? `${weekday(t.slot, 3)} ${time(t.slot)}` : 'No set time' }}</span>
        </Row>
      </div>
      <p v-if="kind === 'weekly'" class="text-sm text-ink-gray-7" data-review-next-date>Next review: {{ weekday(d.next.date) }} {{ long(d.next.date) }}, {{ d.next.time }}</p>
      <div class="flex flex-wrap gap-2">
        <template v-if="kind === 'weekly'">
          <Button variant="solid" label="Go to Today" route="/" data-done-today />
          <Button label="See the week" :route="{ path: '/today/week', query: { view: 'calendar' } }" data-done-week />
        </template>
        <template v-else>
          <Button variant="solid" :label="kind === 'monthly' ? 'See the plan' : 'See the cycles'" route="/goals/cycles" data-done-cycles />
          <Button label="Go to Today" route="/" data-done-today />
        </template>
      </div>
    </Card>
  </div>
</template>
<script setup>
import Row from '@/components/ui/Row.vue'
// The done screen after Lock, for the weekly, monthly and cycle review: the time it took, what was decided, and where to see it
// (the week: the top three, Go to Today and See the week; the month and the cycle: Goals > Cycles).
import { computed, onMounted, ref } from 'vue'
import { Button, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import { useReview } from '@/lib/review'
import { long, time, weekday } from '@/lib/dates'

const r = useReview()
const d = ref(null)
const props = defineProps({ weekly: Boolean })
const kind = computed(() => (props.weekly ? 'weekly' : r.head?.slug === 'monthly' ? 'monthly' : 'cycle'))
const minutes = computed(() => `${d.value.minutes} minute${d.value.minutes === 1 ? '' : 's'}`)
const title = computed(() => ({ weekly: `Week planned in ${minutes.value}`, monthly: `${d.value.next} planned in ${minutes.value}`, cycle: `Cycle closed in ${minutes.value}` })[kind.value])
onMounted(async () => { d.value = await r.read('done') })
</script>
