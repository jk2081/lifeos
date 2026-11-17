<template>
  <div class="flex flex-col gap-1" data-reading-chart>
    <div v-if="target !== null" class="flex justify-end text-xs tabular-nums text-ink-gray-6"><span class="inline-flex items-center gap-1.5"><svg class="h-1 w-4" viewBox="0 0 16 4" aria-hidden="true">
      <line x1="0" x2="16" y1="2" y2="2" stroke="var(--ink-green-6)" stroke-width="2" stroke-dasharray="4 3" /></svg>Target {{ fmt(target) }}{{ unit ? ' ' + unit : '' }}</span></div>
    <div class="flex gap-2">
      <div class="flex w-10 shrink-0 flex-col justify-between py-0.5 text-right text-xs tabular-nums text-ink-gray-6" aria-hidden="true"><span>{{ fmt(range[1]) }}</span><span>{{ fmt(range[0]) }}</span></div>
      <div class="relative h-28 min-w-0 flex-1" @mouseleave="hover = -1" @mousemove="move" @touchstart.passive="move" @touchmove.passive="move">
        <svg class="absolute inset-0 size-full" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" :aria-label="label">
          <line x1="0" x2="100" y1="100" y2="100" stroke="var(--outline-gray-2)" stroke-width="1" vector-effect="non-scaling-stroke" />
          <line v-if="target !== null" x1="0" x2="100" :y1="sy(target)" :y2="sy(target)" stroke="var(--ink-green-6)" stroke-width="1.5" stroke-dasharray="4 3" vector-effect="non-scaling-stroke" />
          <polyline :points="points.map((p, i) => `${sx(i)},${sy(p.value)}`).join(' ')" fill="none" stroke="var(--ink-blue-7)" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
          <!-- a zero-length line with round caps draws a round dot that the stretched view box does not squash -->
          <line v-for="(p, i) in points" :key="i" :x1="sx(i)" :x2="sx(i)" :y1="sy(p.value)" :y2="sy(p.value)" stroke="var(--ink-blue-7)" stroke-linecap="round"
            :stroke-width="hover === i ? 11 : 8" vector-effect="non-scaling-stroke" />
        </svg>
        <div v-if="hover >= 0" class="pointer-events-none absolute top-0 z-[2] flex -translate-x-1/2 flex-col gap-0.5 whitespace-nowrap rounded-4 border border-outline-gray-2 bg-surface-base px-2 py-1.5 text-xs text-ink-gray-9 shadow-lg"
          :style="`left: ${Math.min(Math.max(sx(hover), 18), 82)}%`">
          <b>{{ short(points[hover].date, true) }}</b><span>{{ fmt(points[hover].value) }}{{ unit ? ' ' + unit : '' }}</span>
        </div>
      </div>
    </div>
    <div class="ml-12 flex items-center justify-between gap-2 text-xs tabular-nums text-ink-gray-6">
      <span>{{ short(points[0].date) }}</span><span>{{ short(points[points.length - 1].date) }}</span>
    </div>
  </div>
</template>
<script setup>
// The confirmed readings of a number goal over time (set 7), with its target as a dashed line. The drawing stretches to its
// box (lines keep their width, dots stay round); the labels are text around it, so they stay readable at every width.
import { computed, ref } from 'vue'
import { short } from '@/lib/dates'

const props = defineProps({ readings: Array, start: Number, target: Number, unit: String, label: String })
const PAD = 6 // per cent of the box kept free above and below, and at each side
const hover = ref(-1)
const points = computed(() => props.readings || [])
const target = computed(() => (props.target === null || props.target === undefined ? null : Number(props.target)))
const range = computed(() => {
  const vals = [...points.value.map((p) => Number(p.value)), ...(target.value !== null ? [target.value] : []), ...(props.start != null ? [Number(props.start)] : [])]
  let lo = Math.min(...vals), hi = Math.max(...vals)
  if (lo === hi) { lo -= 1; hi += 1 }
  return [lo, hi]
})
const fmt = (v) => { const n = Number(v); return Math.abs(n) >= 100 || Number.isInteger(n) ? String(Math.round(n)) : n.toFixed(1) }
const sx = (i) => (points.value.length < 2 ? 50 : PAD + (i * (100 - 2 * PAD)) / (points.value.length - 1))
const sy = (v) => { const [lo, hi] = range.value; return PAD + ((hi - Number(v)) * (100 - 2 * PAD)) / (hi - lo) }
function move(e) {
  const box = e.currentTarget.getBoundingClientRect()
  const x = (((e.touches ? e.touches[0].clientX : e.clientX) - box.left) / box.width) * 100
  let best = -1, dist = Infinity
  points.value.forEach((p, i) => { const d = Math.abs(sx(i) - x); if (d < dist) { dist = d; best = i } })
  hover.value = best
}
</script>
