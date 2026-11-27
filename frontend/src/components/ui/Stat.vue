<template>
  <Card :tint="tint" class="flex flex-col gap-0.5" :class="[compact && 'max-md:!px-3 max-md:!py-2.5', open && 'relative']" data-stat>
    <button v-if="open" type="button" class="absolute inset-0 rounded-5 focus-visible:focus-ring" :aria-label="`${label}: ${value}`" data-stat-open @click="openRef(open)" />
    <span class="text-sm text-ink-gray-6" :class="compact && 'max-md:order-2 max-md:truncate max-md:text-xs'">{{ label }}</span>
    <b class="text-3xl-semibold tabular-nums" :class="[warn ? 'text-ink-amber-9' : 'text-ink-gray-9', compact ? 'max-md:text-xl-semibold' : 'max-md:text-2xl-semibold']" data-stat-value><slot>{{ value }}</slot></b>
    <span v-if="$slots.sub || sub" class="text-sm text-ink-gray-6" :class="compact && 'max-md:hidden'"><slot name="sub">{{ sub }}</slot></span>
  </Card>
</template>
<script setup>
// One number with its label, 0 included: a card never shows a sentence instead of its number. `compact`: on a phone the number sits over a small
// label and the line under it is left out. `open` is a pane reference the whole card opens (links and buttons in the `sub` slot need the class
// `relative` to sit above it). `warn` colours the number amber. `tint` is the grey card of Today.
import Card from './Card.vue'
import { openRef } from '@/lib/pane'
defineProps({ label: String, value: { type: [String, Number], default: '' }, sub: String, compact: Boolean, tint: Boolean, warn: Boolean, open: { type: String, default: null } })
</script>
