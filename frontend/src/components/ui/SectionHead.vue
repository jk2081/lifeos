<template>
  <h2 class="mb-2 flex min-h-7 items-center gap-2 text-sm-medium text-ink-gray-7" data-section>
    <slot />
    <CountLink v-if="count !== null && count !== undefined && to" :to="to" data-section-count :data-door="door">{{ count }}</CountLink>
    <span v-else-if="count !== null && count !== undefined" class="tabular-nums text-ink-gray-6">{{ count }}</span>
    <span v-if="$slots.action" class="ml-auto font-medium"><slot name="action" /></span>
  </h2>
</template>
<script setup>
// The small heading above a section, with an optional count that links to the list it counts.
import CountLink from '@/components/ui/CountLink.vue'
defineProps({ count: { type: [Number, String], default: null }, to: { type: [Object, String], default: null }, door: String })
</script>
