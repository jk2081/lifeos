<template>
  <div class="flex min-h-0 flex-1 flex-col" data-review-tasks>
    <div class="page-body !gap-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 class="text-xl-semibold text-ink-gray-9">Your commitments</h2>
          <p class="text-sm text-ink-gray-6">What left your plate this week, then the tasks that are stuck or waiting on someone.</p>
        </div>
        <div v-if="s" class="w-64 max-md:w-full" data-left-to-clear :data-n="s.left">
          <div class="flex items-baseline justify-end gap-2 max-md:justify-start"><span class="text-3xl-semibold tabular-nums text-ink-gray-9">{{ s.left }}</span>
            <span class="text-sm text-ink-gray-7">left to clear</span></div>
          <Progress class="mt-1" size="sm" :value="s.total ? (100 * s.settled) / s.total : 100" :aria-label="`${s.settled} of ${s.total} cleared`" />
          <div class="mt-0.5 text-right text-sm text-ink-gray-6 max-md:text-left">{{ s.settled }} of {{ s.total }} done</div>
        </div>
      </div>
      <section v-if="p" class="flex flex-col gap-2" data-left-your-plate>
        <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 class="text-base-medium text-ink-gray-9">Left your plate · {{ p.out.n }}</h3>
          <span class="text-sm text-ink-gray-6">this period · <CountLink :count="p.in" data-door="review-plate-in" /> came in, <CountLink :count="p.out" /> went out</span>
          <RouterLink class="ml-auto text-base text-ink-blue-8 hover:underline focus-visible:focus-ring" :to="p.outbox" data-open-outbox>Open the Outbox</RouterLink>
        </div>
        <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Card v-for="x in p.piles" :key="x.pile" class="flex flex-col" :data-plate-pile="x.pile">
            <span class="text-sm text-ink-gray-7">{{ x.pile }}</span>
            <CountLink class="text-xl-semibold" :count="x" :count-key="'plate-' + x.pile" :data-door="'review-plate-' + x.pile" />
            <span class="text-sm text-ink-gray-6">{{ x.line }}</span>
          </Card>
        </div>
      </section>
      <PileBoard pkey="tasks" heading="Stuck and waiting, sorted by the assistant" @summary="(v) => (s = v)" />
    </div>
    <ReviewFooter back label="Next: Goals" :disabled="!r.head.done.tasks" :line="line" @back="emit('go', 'library')" @next="emit('go', 'goals')" />
  </div>
</template>
<script setup>
// Tab 2, Tasks (board 30): Left your plate (the Outbox for the period, read only), then Needs you and the three piles for
// existing tasks that are stuck or waiting on others. Next: Goals opens once Needs you and every pile are cleared.
import { computed, onMounted, ref, watch } from 'vue'
import { Progress } from 'frappe-ui'
import Card from '@/components/ui/Card.vue'
import CountLink from '@/components/ui/CountLink.vue'
import PileBoard from './piles/PileBoard.vue'
import ReviewFooter from './ReviewFooter.vue'
import { useReview } from '@/lib/review'

const emit = defineEmits(['go'])
const r = useReview()
const s = ref(null)
const p = ref(null)
const PILES = ['keep', 'park', 'letgo']
const line = computed(() => {
  if (r.head.done.tasks) return 'Needs you and the three piles are cleared'
  if (!s.value) return ''
  const cleared = (s.value.needs_left ? 0 : 1) + PILES.filter((k) => s.value.piles[k].left === 0).length
  return `Opens when Needs you and the three piles are cleared · ${cleared} of 4`
})
async function load() { p.value = await r.read('plate') }
watch(() => r.version, load)
onMounted(load)
</script>
