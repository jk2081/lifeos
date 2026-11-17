<template>
  <div class="flex flex-col gap-1.5" data-result-bar :data-result-percent="p.percent ?? ''">
    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
      <span class="text-base-medium text-ink-gray-9" data-result-current>{{ current }}</span>
      <span class="text-sm text-ink-gray-6">{{ p.current_on ? 'on ' + short(p.current_on, true) : 'no reading yet' }}</span>
    </div>
    <Progress :size="size" :value="Math.round(p.percent || 0)" />
    <div class="flex justify-between gap-2 text-sm tabular-nums text-ink-gray-6">
      <span>Start {{ fmt(p.start) }}{{ unit }}</span>
      <span>{{ Math.round(p.percent || 0) }}%</span>
      <span>Target {{ fmt(p.target) }}{{ unit }}</span>
    </div>
  </div>
</template>
<script setup>
// A number goal's result (set 7): start, current value with its date, target and unit, and the share of the way covered.
// Progress is (current − start) / (target − start), clamped to 0 to 100, so a goal that goes down (84 → 78 kg) fills too.
import { computed } from 'vue'
import { Progress } from 'frappe-ui'
import { short } from '@/lib/dates'

const props = defineProps({ progress: { type: Object, required: true }, size: { type: String, default: 'md' } })
const p = computed(() => props.progress)
const fmt = (v) => (v === null || v === undefined ? '—' : Number.isInteger(Number(v)) ? String(Number(v)) : String(Number(Number(v).toFixed(2))))
const unit = computed(() => (p.value.unit ? ' ' + p.value.unit : ''))
const current = computed(() => (p.value.current === null || p.value.current === undefined ? `${p.value.measure || 'Value'}: no reading yet`
  : `${p.value.measure ? p.value.measure + ': ' : ''}${fmt(p.value.current)}${unit.value}`))
</script>
