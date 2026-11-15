<template>
  <Card class="flex flex-col gap-0.5" data-stat>
    <span class="text-sm text-ink-gray-6">{{ label }}</span>
    <b class="text-3xl-semibold tabular-nums text-ink-gray-9 max-md:text-2xl-semibold"><slot>{{ value }}</slot></b>
    <span v-if="$slots.sub || sub" class="text-sm text-ink-gray-6"><slot name="sub">{{ sub }}</slot></span>
  </Card>
</template>
<script setup>
import Card from './Card.vue'
defineProps({ label: String, value: { type: [String, Number], default: '' }, sub: String })
</script>
