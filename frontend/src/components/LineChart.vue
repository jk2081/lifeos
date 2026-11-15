<template>
  <div class="relative" @mouseleave="hover = -1">
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="label" @mousemove="move" @touchstart.passive="move" @touchmove.passive="move">
      <g v-for="y in [0, 5, 10]" :key="y">
        <line :x1="PL" :x2="W - PR" :y1="sy(y)" :y2="sy(y)" stroke="var(--outline-gray-1)" stroke-width="1" />
        <text :x="PL - 6" :y="sy(y) + 3.5" text-anchor="end" class="ax">{{ y }}</text>
      </g>
      <text v-for="(p, i) in points" v-show="i === 0 || i === points.length - 1" :key="'d' + i" :x="sx(i)" :y="H - 4"
        :text-anchor="i === 0 ? 'start' : 'end'" class="ax">{{ short(p.date) }}</text>
      <line v-if="hover >= 0" :x1="sx(hover)" :x2="sx(hover)" :y1="PT" :y2="H - PB" stroke="var(--outline-gray-3)" stroke-width="1" />
      <g v-for="s in SERIES" :key="s.key">
        <path :d="path(s.key)" fill="none" :stroke="`var(${s.color})`" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
        <template v-for="(p, i) in points" :key="i">
          <circle v-if="p[s.key] != null" :cx="sx(i)" :cy="sy(p[s.key])" :r="hover === i ? 5 : 4" :fill="`var(${s.color})`" stroke="var(--surface-base)" stroke-width="2" />
        </template>
      </g>
    </svg>
    <div v-if="hover >= 0" class="pointer-events-none absolute top-0 z-[2] flex -translate-x-1/2 flex-col gap-0.5 whitespace-nowrap rounded-4 border border-outline-gray-2 bg-surface-base px-2 py-1.5 text-xs text-ink-gray-9 shadow-lg"
      :style="`left: ${Math.min(Math.max((sx(hover) / W) * 100, 18), 82)}%`">
      <b>{{ short(points[hover].date, true) }}</b>
      <span v-for="s in SERIES" :key="s.key" class="inline-flex items-center gap-1.5">
        <svg class="size-2" viewBox="0 0 8 8" aria-hidden="true"><circle cx="4" cy="4" r="4" :fill="`var(${s.color})`" /></svg>{{ s.label }} {{ points[hover][s.key] ?? '—' }}</span>
    </div>
  </div>
</template>
<script setup>
// A small two-series line chart on one 0 to 10 axis: habits and situation for one check-in dimension.
import { ref } from 'vue'
import { short } from '@/lib/dates'

const props = defineProps({ points: Array, label: String })
const SERIES = [{ key: 'habits', label: 'Habits', color: '--ink-blue-7' }, { key: 'situation', label: 'Situation', color: '--ink-amber-7' }]
const W = 320, H = 132, PL = 22, PR = 8, PT = 8, PB = 20
const hover = ref(-1)
const sx = (i) => (props.points.length < 2 ? (PL + W - PR) / 2 : PL + (i * (W - PL - PR)) / (props.points.length - 1))
const sy = (v) => PT + ((10 - v) * (H - PT - PB)) / 10
function path(key) {
  let d = '', pen = false
  props.points.forEach((p, i) => {
    if (p[key] == null) { pen = false; return }
    d += `${pen ? 'L' : 'M'}${sx(i).toFixed(1)} ${sy(p[key]).toFixed(1)} `
    pen = true
  })
  return d
}
function move(e) {
  const box = e.currentTarget.getBoundingClientRect()
  const x = (((e.touches ? e.touches[0].clientX : e.clientX) - box.left) / box.width) * W
  let best = -1, dist = Infinity
  props.points.forEach((p, i) => { const dd = Math.abs(sx(i) - x); if (dd < dist) { dist = dd; best = i } })
  hover.value = best
}
</script>
<style scoped>
/* drawing code only: the SVG fills its box, and its axis text reads a token variable */
svg { width: 100%; height: auto; display: block; }
.ax { font-size: 10px; fill: var(--ink-gray-6); font-variant-numeric: tabular-nums; }
</style>
