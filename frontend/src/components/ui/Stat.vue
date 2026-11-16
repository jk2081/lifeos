<template>
  <Card class="flex flex-col gap-0.5" :class="compact && 'max-md:!px-3 max-md:!py-2.5'" data-stat>
    <span class="text-sm text-ink-gray-6" :class="compact && 'max-md:order-2 max-md:truncate max-md:text-xs'">{{ label }}</span>
    <b class="text-3xl-semibold tabular-nums text-ink-gray-9" :class="compact ? 'max-md:text-xl-semibold' : 'max-md:text-2xl-semibold'"><slot>{{ value }}</slot></b>
    <span v-if="$slots.sub || sub" class="text-sm text-ink-gray-6" :class="compact && 'max-md:hidden'"><slot name="sub">{{ sub }}</slot></span>
  </Card>
</template>
<script setup>
// One number with its label. `compact`: on a phone the number sits over a small label and the line under it is left out.
import Card from './Card.vue'
defineProps({ label: String, value: { type: [String, Number], default: '' }, sub: String, compact: Boolean })
</script>
