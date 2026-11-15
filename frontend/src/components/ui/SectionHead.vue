<template>
  <h2 class="mb-2 flex items-center gap-2 text-sm-medium text-ink-gray-7" data-section>
    <slot />
    <NumLink v-if="count !== null && count !== undefined && to" :to="to" data-section-count :data-door="door">{{ count }}</NumLink>
    <span v-else-if="count !== null && count !== undefined" class="tabular-nums text-ink-gray-6">{{ count }}</span>
    <span v-if="$slots.action" class="ml-auto font-medium"><slot name="action" /></span>
  </h2>
</template>
<script setup>
// The small heading above a section, with an optional count that links to the list it counts.
import NumLink from './NumLink.vue'
defineProps({ count: { type: [Number, String], default: null }, to: { type: [Object, String], default: null }, door: String })
</script>
