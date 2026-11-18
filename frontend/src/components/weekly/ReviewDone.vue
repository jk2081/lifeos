<template>
  <div class="page-body items-center" data-review-done>
    <Skeleton v-if="!d" class="h-64 w-full max-w-xl" />
    <Card v-else class="flex w-full max-w-xl flex-col gap-3">
      <div class="flex items-center gap-2">
        <span class="flex size-7 items-center justify-center rounded-full bg-surface-green-7 text-ink-base" aria-hidden="true"><span class="lucide-check size-4" /></span>
        <h2 class="text-xl-semibold text-ink-gray-9" data-review-done-title>Week planned in {{ d.minutes }} minute{{ d.minutes === 1 ? '' : 's' }}</h2>
      </div>
      <ul class="flex flex-col gap-0.5 text-base text-ink-gray-8" data-review-decided>
        <li>{{ d.made.length }} task{{ d.made.length === 1 ? '' : 's' }} planned for your goals, {{ d.scheduled }} with a time</li>
        <li v-if="d.delegated">{{ d.delegated }} delegated, waiting on someone</li>
        <li v-if="d.skipped">{{ d.skipped }} goal{{ d.skipped === 1 ? '' : 's' }} skipped this week</li>
        <li>{{ d.cleared }} stuck and waiting item{{ d.cleared === 1 ? '' : 's' }} cleared</li>
      </ul>
      <div>
        <div class="mb-1 text-sm-medium text-ink-gray-8">Top three</div>
        <div v-for="t in d.top" :key="t.task" class="flex items-center gap-2 border-b border-outline-gray-1 py-1.5 last:border-b-0" data-done-top>
          <span class="lucide-star size-4 shrink-0 text-ink-amber-9" aria-hidden="true" />
          <span class="min-w-0 flex-1 truncate text-base text-ink-gray-9">{{ t.title }}</span>
          <span class="text-sm tabular-nums text-ink-gray-6">{{ t.slot ? `${weekday(t.slot, 3)} ${time(t.slot)}` : 'No set time' }}</span>
        </div>
      </div>
      <p class="text-sm text-ink-gray-7" data-review-next-date>Next review: {{ weekday(d.next.date) }} {{ long(d.next.date) }}, {{ d.next.time }}</p>
      <div class="flex flex-wrap gap-2">
        <Button variant="solid" label="Go to Today" route="/" data-done-today />
        <Button label="See the week" :route="{ path: '/plan/week', query: { view: 'calendar' } }" data-done-week />
      </div>
    </Card>
  </div>
</template>
<script setup>
// The done screen after Lock the week: the time it took, what was decided, the top three, Go to Today and See the week.
import { onMounted, ref } from 'vue'
import { Button, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import { useReview } from '@/lib/review'
import { long, time, weekday } from '@/lib/dates'

const r = useReview()
const d = ref(null)
onMounted(async () => { d.value = await r.read('done') })
</script>
