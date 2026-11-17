<template>
  <div class="flex flex-col gap-2" data-inout-chart>
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-gray-6">
      <span class="inline-flex items-center gap-1.5"><svg class="size-2.5" viewBox="0 0 8 8" aria-hidden="true"><rect width="8" height="8" rx="1.5" fill="var(--ink-gray-4)" /></svg>In</span>
      <span class="inline-flex items-center gap-1.5"><svg class="size-2.5" viewBox="0 0 8 8" aria-hidden="true"><rect width="8" height="8" rx="1.5" fill="var(--ink-blue-7)" /></svg>Out</span>
      <span class="ml-auto">Last {{ weeks.length }} weeks</span>
    </div>
    <svg class="chart" :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="label">
      <line :x1="0" :x2="W" :y1="H - PB" :y2="H - PB" stroke="var(--outline-gray-2)" stroke-width="1" />
      <g v-for="(w, i) in weeks" :key="w.week_of">
        <rect :x="x(i)" :y="y(w.in)" :width="BW" :height="H - PB - y(w.in)" rx="2" fill="var(--ink-gray-4)"><title>Week of {{ short(w.week_of, true) }}: {{ w.in }} in</title></rect>
        <rect :x="x(i) + BW + 2" :y="y(w.out)" :width="BW" :height="H - PB - y(w.out)" rx="2" fill="var(--ink-blue-7)"><title>Week of {{ short(w.week_of, true) }}: {{ w.out }} out</title></rect>
      </g>
    </svg>
    <div class="grid text-center text-xs tabular-nums text-ink-gray-6" :style="`grid-template-columns: repeat(${weeks.length || 1}, minmax(0, 1fr))`">
      <span v-for="w in weeks" :key="w.week_of" class="truncate">{{ short(w.week_of) }}</span>
    </div>
  </div>
</template>
<script setup>
// In against out for each of the last weeks (set 7): two bars a week, grey for what came in, blue for what left.
import { computed } from 'vue'
import { short } from '@/lib/dates'

const props = defineProps({ weeks: { type: Array, default: () => [] } })
const W = 960, H = 150, PB = 2, PT = 8
const slot = computed(() => W / Math.max(props.weeks.length, 1))
const BW = 14
const max = computed(() => Math.max(1, ...props.weeks.flatMap((w) => [w.in, w.out])))
const x = (i) => i * slot.value + slot.value / 2 - BW - 1
const y = (v) => PT + (H - PB - PT) * (1 - v / max.value)
const label = computed(() => props.weeks.map((w) => `week of ${w.week_of}: ${w.in} in, ${w.out} out`).join('; '))
</script>
<style scoped>
/* drawing code only */
.chart { width: 100%; height: auto; max-height: 11rem; display: block; }
</style>
