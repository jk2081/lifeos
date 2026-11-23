<template>
  <div class="page-body items-center" data-review-done>
    <Skeleton v-if="!d" class="h-64 w-full max-w-xl" />
    <Card v-else class="flex w-full max-w-xl flex-col gap-3">
      <div class="flex items-center gap-2">
        <span class="flex size-7 items-center justify-center rounded-full bg-surface-green-7 text-ink-base" aria-hidden="true"><span class="lucide-check size-4" /></span>
        <h2 class="text-xl-semibold text-ink-gray-9" data-review-done-title>{{ monthly ? `${d.next} planned in ${d.minutes} minute${d.minutes === 1 ? '' : 's'}` : `Cycle closed in ${d.minutes} minute${d.minutes === 1 ? '' : 's'}` }}</h2>
      </div>
      <ul v-if="monthly" class="flex flex-col gap-0.5 text-base text-ink-gray-8" data-review-decided>
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
      <div class="flex flex-wrap gap-2">
        <Button variant="solid" :label="monthly ? 'See the plan' : 'See the cycles'" :route="'/goals/cycles'" data-done-cycles />
        <Button label="Go to Today" route="/" data-done-today />
      </div>
    </Card>
  </div>
</template>
<script setup>
// The done screen after Lock: what was decided, and where to see it (Goals > Cycles).
import { computed, onMounted, ref } from 'vue'
import { Button, Skeleton } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import { useReview } from '@/lib/review'
import { long } from '@/lib/dates'

const r = useReview()
const d = ref(null)
const monthly = computed(() => r.head?.slug === 'monthly')
onMounted(async () => { d.value = await r.read('done') })
</script>
