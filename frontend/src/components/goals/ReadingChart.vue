<template>
  <div class="relative" data-reading-chart @mouseleave="hover = -1">
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="label" @mousemove="move" @touchstart.passive="move" @touchmove.passive="move">
      <g v-for="y in ticks" :key="y">
        <line :x1="PL" :x2="W - PR" :y1="sy(y)" :y2="sy(y)" stroke="var(--outline-gray-1)" stroke-width="1" />
        <text :x="PL - 6" :y="sy(y) + 3.5" text-anchor="end" class="ax">{{ fmt(y) }}</text>
      </g>
      <line v-if="target !== null" :x1="PL" :x2="W - PR" :y1="sy(target)" :y2="sy(target)" stroke="var(--ink-green-6)" stroke-width="1.5" stroke-dasharray="4 3" />
      <text v-for="(p, i) in points" v-show="i === 0 || i === points.length - 1" :key="'d' + i" :x="sx(i)" :y="H - 4"
        :text-anchor="points.length === 1 ? 'middle' : i === 0 ? 'start' : 'end'" class="ax">{{ short(p.date) }}</text>
      <path :d="path" fill="none" stroke="var(--ink-blue-7)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
      <circle v-for="(p, i) in points" :key="i" :cx="sx(i)" :cy="sy(p.value)" :r="hover === i ? 5 : 4" fill="var(--ink-blue-7)" stroke="var(--surface-base)" stroke-width="2" />
    </svg>
    <div v-if="hover >= 0" class="pointer-events-none absolute top-0 z-[2] flex -translate-x-1/2 flex-col gap-0.5 whitespace-nowrap rounded-4 border border-outline-gray-2 bg-surface-base px-2 py-1.5 text-xs text-ink-gray-9 shadow-lg"
      :style="`left: ${Math.min(Math.max((sx(hover) / W) * 100, 18), 82)}%`">
      <b>{{ short(points[hover].date, true) }}</b><span>{{ fmt(points[hover].value) }}{{ unit ? ' ' + unit : '' }}</span>
    </div>
  </div>
</template>
<script setup>
// The confirmed readings of a number goal over time (set 7), with its target as a dashed line. Drawing code: token variables only.
import { computed, ref } from 'vue'
import { short } from '@/lib/dates'

const props = defineProps({ readings: Array, start: Number, target: Number, unit: String, label: String })
const W = 320, H = 132, PL = 34, PR = 8, PT = 8, PB = 20
const hover = ref(-1)
const points = computed(() => props.readings || [])
const target = computed(() => (props.target === null || props.target === undefined ? null : Number(props.target)))
const range = computed(() => {
  const vals = [...points.value.map((p) => Number(p.value)), ...(target.value !== null ? [target.value] : []), ...(props.start != null ? [Number(props.start)] : [])]
  let lo = Math.min(...vals), hi = Math.max(...vals)
  if (lo === hi) { lo -= 1; hi += 1 }
  const pad = (hi - lo) * 0.1
  return [lo - pad, hi + pad]
})
const ticks = computed(() => { const [lo, hi] = range.value; return [lo, (lo + hi) / 2, hi] })
const fmt = (v) => { const n = Number(v); return Math.abs(n) >= 100 || Number.isInteger(n) ? String(Math.round(n)) : n.toFixed(1) }
const sx = (i) => (points.value.length < 2 ? (PL + W - PR) / 2 : PL + (i * (W - PL - PR)) / (points.value.length - 1))
const sy = (v) => { const [lo, hi] = range.value; return PT + ((hi - Number(v)) * (H - PT - PB)) / (hi - lo) }
const path = computed(() => points.value.map((p, i) => `${i ? 'L' : 'M'}${sx(i).toFixed(1)} ${sy(p.value).toFixed(1)}`).join(' '))
function move(e) {
  const box = e.currentTarget.getBoundingClientRect()
  const x = (((e.touches ? e.touches[0].clientX : e.clientX) - box.left) / box.width) * W
  let best = -1, dist = Infinity
  points.value.forEach((p, i) => { const d = Math.abs(sx(i) - x); if (d < dist) { dist = d; best = i } })
  hover.value = best
}
</script>
<style scoped>
/* drawing code only: the SVG fills its box, and its axis text reads a token variable */
svg { width: 100%; height: auto; display: block; }
.ax { font-size: 10px; fill: var(--ink-gray-6); font-variant-numeric: tabular-nums; }
</style>
